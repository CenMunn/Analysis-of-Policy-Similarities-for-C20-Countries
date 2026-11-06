"""从原始 ZIP 读取正文并关联元数据，不解压、不覆盖原文件。

source_country 只表示元数据中的来源分类，并不是经过核验的政策主体。
损坏元数据保留原始字节证据；无法确认的字段留空，交给后续复核。
"""

from __future__ import annotations

import base64

from collections import defaultdict

import csv

import io

from pathlib import Path

import re

import zipfile

COUNTRY_ALIASES = {"印尼": "印度尼西亚", "沙特": "沙特阿拉伯"}

def normalize_id(value: str) -> str:
    value = str(value).strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
    if value.startswith("text_"):
        value = value[5:]
    if value.endswith(".txt"):
        value = value[:-4]
    return value.replace("-", "")

def normalize_country(value: str) -> str:
    value = str(value or "").strip()
    return COUNTRY_ALIASES.get(value, value)

def decode_zip_path(item: zipfile.ZipInfo) -> tuple[str, str]:
    if item.flag_bits & 0x800:
        return item.filename.replace("\\", "/"), "utf-8"
    try:
        raw_name = item.filename.encode("cp437")
    except UnicodeEncodeError:
        return item.filename.replace("\\", "/"), "unicode"
    if raw_name.isascii():
        return item.filename.replace("\\", "/"), "ascii"
    return raw_name.decode("gb18030").replace("\\", "/"), "gb18030"

def decode_text(data: bytes) -> tuple[str, str]:
    encodings = ["utf-8-sig"]
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ["utf-16"] + encodings
    encodings.append("gb18030")
    errors = []
    for encoding in encodings:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    raise UnicodeError("; ".join(errors))

def _issue(issues, issue_type, source_path, detail, file_id="", severity="review"):
    issues.append({
        "file_id": file_id,
        "source_path": source_path,
        "issue_type": issue_type,
        "severity": severity,
        "detail": detail,
    })

def _group(source_path: str) -> str:
    parts = source_path.split("/")
    return parts[1] if len(parts) > 2 else parts[0]

def _malformed_rows(data: bytes, source_path: str, issues: list) -> list[dict]:
    """只恢复能独立确认边界的字段，不用损坏后的列位置猜测国家。"""
    rows = []
    for line_number, raw_line in enumerate(data.splitlines(), 1):
        if line_number == 1 and raw_line.lstrip(b"\xef\xbb\xbf").startswith(b"fileId,"):
            continue
        if not raw_line.strip():
            continue
        raw_id = raw_line.split(b",", 1)[0]
        try:
            file_id = raw_id.decode("ascii").strip()
        except UnicodeDecodeError:
            file_id = ""
        if not re.fullmatch(r"(?:text_)?[0-9a-fA-F-]+(?:\.txt)?", file_id):
            file_id = ""
        urls = []
        url_matches = list(re.finditer(rb"https?://[^\s,\"<>]+", raw_line))
        for match in url_matches:
            try:
                url = match.group().decode("ascii")
            except UnicodeDecodeError:
                continue
            if url not in urls:
                urls.append(url)
        title = ""
        if file_id and url_matches:
            prefix = raw_line[len(raw_id) + 1:url_matches[0].start()].rstrip(b', "')
            try:
                title = prefix.decode("utf-8")
            except UnicodeDecodeError:
                pass
        date_candidates = sorted(set(
            match.decode("ascii")
            for match in re.findall(rb"(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}", raw_line)
        ))
        row = {
            "file_id": file_id,
            "normalized_id": normalize_id(file_id),
            "source_country": "",
            "title": title,
            "url": urls[0] if len(urls) == 1 else "",
            "published_at": "",
            "metadata_path": source_path,
            "metadata_row": line_number,
            "metadata_encoding": "damaged-utf8-or-unknown",
            "metadata_status": "malformed",
            "raw_metadata": {},
            "raw_record_base64": base64.b64encode(raw_line).decode("ascii"),
            "raw_record_preview": raw_line.decode("utf-8", errors="backslashreplace"),
            "recovered_url_candidates": urls,
            "recovered_date_candidates": date_candidates,
            "field_provenance": {
                "file_id": "ASCII first field; only accepted if identifier format is intact",
                "url": "ASCII URL extracted independently; filled only if unique",
                "title": "prefix before URL, only when strict UTF-8 decoding succeeds",
                "source_country": "not recovered: invalid encoding and shifted columns",
                "published_at": "not recovered: date candidates are not a verified publication field",
            },
        }
        rows.append(row)
        _issue(
            issues, "metadata_malformed_row", source_path,
            f"第 {line_number} 行编码或列结构损坏；保留原字节，未猜测国家与日期。",
            file_id,
        )
    return rows

def _metadata(data: bytes, source_path: str, issues: list) -> list[dict]:
    try:
        text, encoding = decode_text(data)
    except UnicodeError as exc:
        _issue(issues, "metadata_decode_error", source_path, str(exc), severity="error")
        return _malformed_rows(data, source_path, issues)

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as exc:
        _issue(issues, "metadata_invalid_header", source_path, str(exc), severity="error")
        return _malformed_rows(data, source_path, issues)
    names = [name.strip().lstrip("\ufeff") for name in header]
    if not {"fileId", "title", "url", "area"}.issubset(names):
        _issue(issues, "metadata_invalid_header", source_path,
               "缺少 fileId、title、url 或 area 字段。", severity="error")
        return _malformed_rows(data, source_path, issues)
    rows = []
    try:
        for values in reader:
            if not values or not any(values):
                continue
            line_number = reader.line_num
            fields = {
                name: values[index] if index < len(values) else ""
                for index, name in enumerate(names) if name
            }
            file_id = fields.get("fileId", "").strip()
            required_last = max(names.index(name) for name in ("fileId", "title", "url", "area"))
            malformed = len(values) <= required_last or (
                len(values) > len(names) and any(values[len(names):])
            )
            if not file_id:
                malformed = True
            row = {
                "file_id": file_id,
                "normalized_id": normalize_id(file_id),
                "source_country": "" if malformed else normalize_country(fields.get("area", "")),
                "title": "" if malformed else fields.get("title", "").strip(),
                "url": "" if malformed else fields.get("url", "").strip(),
                "published_at": "" if malformed else fields.get("date", "").strip(),
                "metadata_path": source_path,
                "metadata_row": line_number,
                "metadata_encoding": encoding,
                "metadata_status": "malformed" if malformed else "parsed",
                "raw_metadata": fields,
                "raw_values": values,
                "raw_headers": header,
                "raw_record_base64": "",
                "raw_record_preview": "",
                "recovered_url_candidates": [],
                "recovered_date_candidates": [],
                "field_provenance": "CSV column names; strict decoding; country alias/whitespace normalization",
            }
            rows.append(row)
            if malformed:
                _issue(issues, "metadata_malformed_row", source_path,
                       f"第 {line_number} 行字段数与表头不一致或 fileId 为空。", file_id)
    except csv.Error as exc:
        # 整表无法可靠分行时，保留所有字节行作为损坏记录，避免只交付成功读取的前半段。
        _issue(issues, "metadata_csv_error", source_path, str(exc), severity="error")
        return _malformed_rows(data, source_path, issues)
    return rows

def load_archive(path) -> tuple[list[dict], list[dict], list[dict]]:
    documents = []
    metadata_rows = []
    issues = []
    with zipfile.ZipFile(Path(path)) as archive:
        for item in archive.infolist():
            if item.is_dir():
                continue
            try:
                source_path, path_encoding = decode_zip_path(item)
            except UnicodeError as exc:
                source_path = item.filename.replace("\\", "/")
                path_encoding = "unresolved"
                _issue(issues, "zip_filename_decode_error", source_path,
                       str(exc), severity="error")
            suffix = source_path.lower().rsplit(".", 1)[-1]
            if suffix not in {"txt", "csv"}:
                continue
            data = archive.read(item)
            if suffix == "csv":
                metadata_rows.extend(_metadata(data, source_path, issues))
                continue
            file_id = source_path.rsplit("/", 1)[-1]
            raw_bytes = ""
            try:
                raw_text, encoding = decode_text(data)
            except UnicodeError as exc:
                raw_text, encoding = "", "undecodable"
                raw_bytes = base64.b64encode(data).decode("ascii")
                _issue(issues, "text_decode_error", source_path,
                       str(exc), file_id, severity="error")
            documents.append({
                "file_id": file_id,
                "normalized_id": normalize_id(file_id),
                "source_path": source_path,
                "raw_text": raw_text,
                "text_encoding": encoding,
                "path_encoding": path_encoding,
                "raw_bytes_base64": raw_bytes,
                "source_country": "",
                "source_country_candidates": [],
                "title": "",
                "url": "",
                "published_at": "",
                "metadata_status": "unmatched",
                "metadata_path": "",
                "metadata_references": [],
                "source_group": _group(source_path),
            })

    text_index = defaultdict(list)
    metadata_index = defaultdict(list)
    for doc in documents:
        text_index[doc["normalized_id"]].append(doc)
    for row in metadata_rows:
        if row["normalized_id"]:
            metadata_index[row["normalized_id"]].append(row)
        row["matched_document_count"] = len(text_index.get(row["normalized_id"], []))
        if not row["matched_document_count"]:
            _issue(issues, "metadata_without_text", row["metadata_path"],
                   f"元数据第 {row['metadata_row']} 行没有对应 TXT。",
                   row["file_id"])
    for normalized_id, docs in text_index.items():
        if len(docs) > 1:
            _issue(issues, "duplicate_text_identifier", docs[0]["source_path"],
                   f"{normalized_id} 对应 {len(docs)} 个 TXT，全部保留；"
                   + " | ".join(doc["source_path"] for doc in docs),
                   docs[0]["file_id"], severity="error")

    for doc in documents:
        matches = metadata_index.get(doc["normalized_id"], [])
        if not matches:
            _issue(issues, "metadata_unmatched", doc["source_path"],
                   "找不到对应元数据；source_group 仅保留目录分类，不据此推定政策国家。",
                   doc["file_id"])
            continue
        valid = [row for row in matches if row["metadata_status"] == "parsed"]
        countries = sorted({row["source_country"] for row in valid if row["source_country"]})
        doc["source_country_candidates"] = countries
        doc["metadata_path"] = " | ".join(sorted({row["metadata_path"] for row in matches}))
        doc["metadata_references"] = [
            {"path": row["metadata_path"], "row": row["metadata_row"]} for row in matches
        ]
        if len(matches) > 1:
            _issue(issues, "duplicate_metadata_identifier", doc["source_path"],
                   f"同一规范化 ID 对应 {len(matches)} 条元数据，未覆盖任何记录。",
                   doc["file_id"])
        signatures = {
            (row["source_country"], row["title"], row["url"], row["published_at"])
            for row in valid
        }
        if len(signatures) > 1:
            doc["metadata_status"] = "conflict"
            # 冲突字段不选第一条。各候选仍完整保存在 metadata_rows 中。
            _issue(issues, "metadata_conflict", doc["source_path"],
                   "同一 ID 的多条元数据在国家、标题、URL 或日期上存在差异。",
                   doc["file_id"])
        else:
            selected = valid[0] if valid else matches[0]
            doc["metadata_status"] = "matched" if valid else "malformed"
            for field in ("source_country", "title", "url", "published_at"):
                doc[field] = selected[field]
    return documents, metadata_rows, issues
