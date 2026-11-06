"""保守清理网页模板；所有内容删除均记录片段及当时文本中的位置。"""

import html

import re

def _function_end(text, opening):
    depth, quote, escaped, comment = 0, "", False, ""
    i = opening
    while i < len(text):
        char = text[i]
        nxt = text[i:i + 2]
        if comment == "//":
            if char == "\n":
                comment = ""
        elif comment == "/*":
            if nxt == "*/":
                comment = ""
                i += 1
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif nxt in ("//", "/*"):
            comment = nxt
            i += 1
        elif char in "'\"`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None

def clean_document(text, title=""):
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    logs, flags = [], []

    def remove(start, end, rule):
        nonlocal cleaned
        removed = cleaned[start:end]
        logs.append({
            "rule": rule, "stage_start": start, "stage_end": end,
            "removed_chars": len(removed), "removed_text": removed,
        })
        cleaned = cleaned[:start] + cleaned[end:]

    def replace_matches(pattern, rule, regex_flags=0):
        for match in reversed(list(re.finditer(pattern, cleaned, regex_flags))):
            remove(match.start(), match.end(), rule)

    replace_matches(r"<script\b[^>]*>.*?</script\s*>", "closed_script_tag", re.I | re.S)
    functions = list(re.finditer(r"\bfunction\s+[A-Za-z_$]\w*\s*\([^()]{0,200}\)\s*\{", cleaned))
    spans = []
    for match in functions:
        if any(start <= match.start() < end for start, end in spans):
            continue
        end = _function_end(cleaned, match.end() - 1)
        if end is None:
            flags.append("unclosed_script")
        else:
            spans.append((match.start(), end))
    for start, end in reversed(spans):
        remove(start, end, "balanced_javascript_function")
    replace_matches(r"\bwindow\.onload\s*=\s*[A-Za-z_$]\w*\([^;\n]{0,150}\)\s*;",
                    "javascript_onload")
    replace_matches(r"\bmoveAD\(\s*['\"][^'\"]{1,60}['\"]\s*\)\s*;", "javascript_ad_call")

    # 只识别有明确模板边界的尾部，不从文章开头匹配版权。
    footer_patterns = [
        r"北极星[^。\n]{0,15}官方微信(?=\s*特别声明)",
        r"特别声明[：:]北极星转载其他网站内容",
        r"网友评论只代表网友",
        r"热门评论(?=.{0,100}(?:登录|评论|频道))",
        r"版权所有\s*[©Ⓒ]",
        r"Copyright\s*(?:©|\(c\)|\d{4})",
        r"关于(?:我们|北极星)\s*[|｜].{0,100}(?:广告服务|联系我们|网站地图)",
        r"版权声明\s*[|｜].{0,60}(?:原创|未经授权)",
        r"返回搜狐[，,]\s*查看更多",
        r"首页\s*[-－]\s*天下\s*[-－]\s*中国",
        r"[|｜]\s*起运港[|｜\s]+目的港[|｜\s]+船公司[|｜\s]+20GP",
    ]
    boundaries = []
    for pattern in footer_patterns:
        match = re.search(pattern, cleaned, re.I)
        if match:
            if match.start() >= 20:
                boundaries.append((match.start(), pattern))
            else:
                flags.append("footer_before_body")
    if boundaries:
        start, pattern = min(boundaries)
        # A footer may contain a complete related-news policy excerpt. Restore
        # only a bounded, dated national publication with a named policy and
        # an explicit energy/carbon measure; recruitment and link lists stay out.
        tail = cleaned[start:]
        rescued = []
        for m in re.finditer(r'(?:20\d\d年)?\d{1,2}月\d{1,2}日[，,](?:国家发改委|国家发展改革委|国家能源局|国务院|财政部|生态环境部)[^。\n]{0,25}(?:印发|发布|颁布)《[^》\n]{3,65}》[^。\n]{5,350}[。]', tail):
            if re.search(r'储能|碳|绿色发展|能源|电价|节能|光伏', m[0]) and re.search(r'明确|规定|要求|加大|实施|促进', m[0]):
                rescued.append((start+m.start(), start+m.end(), m[0]))
        remove(start, len(cleaned), "known_footer:" + pattern)
        for a,b,excerpt in rescued:
            if excerpt not in cleaned:
                cleaned += '\n' + excerpt
                logs.append(dict(rule='restore_bounded_related_policy_excerpt',stage_start=a,stage_end=b,
                                 removed_chars=0,removed_text='',restored_text=excerpt,
                                 evidence_note='页脚后完整关联新闻摘录，不能沿用正文报道日期'))
                flags.append('related_policy_excerpt_restored')

    # 元数据标题只用于越过明显导航，不假定标题前面的文本全部是垃圾。
    if title and len(title.strip()) >= 6:
        position = cleaned.find(title.strip())
        if 0 < position < 8000:
            prefix = cleaned[:position]
            markers = sum(term in prefix for term in ["网站地图", "立即注册", "频道", "登录", "首页"])
            if markers >= 3 and not re.search(r"[。！？]", prefix):
                remove(0, position, "navigation_before_metadata_title")

    replace_matches(r"(?:文章来源|本文来源)[：:][^\n]{1,60}?(?=原标题[：:])",
                    "source_bounded_by_original_title")
    replace_matches(r"(?:\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?\s*)?浏览[：:]\s*\d+",
                    "page_timestamp_and_view_counter")
    replace_matches(r"来源[：:][^\n。]{1,40}?\s*T\s*大\s*T\s*小", "source_font_controls")
    replace_matches(r"(?:责任编辑|责编|编辑)[：:]\s*[\u4e00-\u9fff·]{2,6}\s*$",
                    "bounded_editor_credit_at_end")
    replace_matches(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]{0,500})?/?>", "html_tag")
    replace_matches(r"(?:京|沪|粤|苏|浙|鲁|陕|闽)?ICP(?:备|证)\s*\d{4,}(?:-\d+)?号?",
                    "registration_number")

    # 只删除整行、独立的短站点标签；不使用“少于20字就删除”的规则。
    navigation_labels = {
        "登录", "注册", "立即注册", "返回首页", "网站地图", "联系我们",
        "查看更多评论", "扫一扫", "关闭", "关闭重播", "广告服务",
    }
    matches = list(re.finditer(r"[^\n]+", cleaned))
    seen = set()
    deletions = []
    for match in matches:
        paragraph = match.group().strip()
        if paragraph in navigation_labels:
            deletions.append((match.start(), match.end(), "standalone_navigation"))
        elif len(paragraph) >= 20 and paragraph in seen:
            deletions.append((match.start(), match.end(), "exact_duplicate_paragraph"))
        else:
            seen.add(paragraph)
    for start, end, rule in reversed(deletions):
        remove(start, end, rule)

    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"[^\S\n]+", " ", cleaned)
    cleaned = "\n".join(line.strip() for line in cleaned.splitlines() if line.strip())
    # 整篇精确拼接两遍的抓取异常；只做一次，并保留删除日志。
    if len(cleaned) % 2 == 0 and len(cleaned) >= 160:
        half = len(cleaned) // 2
        if cleaned[:half] == cleaned[half:]:
            remove(half, len(cleaned), "exact_whole_article_repeated_twice")
    if re.search(r"window\.onload|queryWordAdservice|\$\s*\.\s*ajax|function\s+\w+\s*\(", cleaned):
        flags.append("residual_script")
    ui_markers = [
        "抢先报名", "猎头职位", "扫一扫", "验证码", "立即注册", "相关阅读",
        "相关推荐", "推荐阅读", "发表评论", "网站地图", "登录人民网通行证",
        "股票频道", "港股频道", "更多新闻", "版权所有", "免责声明",
        "欢迎投稿", "添加微信", "扫码关注", "微信公众号", "抢票", "去APP订阅",
        "T 大T 小", "返回搜狐", "版权声明", "分享至", "我要评论",
    ]
    found = [term for term in ui_markers if term in cleaned]
    if found:
        flags.append("residual_web_template")
    if sum(term in cleaned for term in ["频道", "首页", "网站地图", "登录", "论坛"]) >= 3:
        flags.append("dense_navigation")
    if len(cleaned) < 500 and sum(
        term in cleaned for term in ["索引号", "发布机构", "成文日期", "发布日期", "文号"]
    ) >= 3 and cleaned.count("。") < 2:
        flags.append("metadata_only_page")
    raw_nonspace = len(re.sub(r"\s", "", text))
    clean_nonspace = len(re.sub(r"\s", "", cleaned))
    retention = clean_nonspace / raw_nonspace if raw_nonspace else 0.0
    if text.strip() and retention < .35:
        flags.append("large_content_removal")
    return {
        "clean_text": cleaned,
        "removal_log": logs,
        "clean_flags": sorted(set(flags)),
        "residual_noise_markers": found,
        "raw_char_count": len(text),
        "clean_char_count": len(cleaned),
        "content_retention_ratio": round(retention, 6),
        "normalization": "统一换行/空白、HTML实体解码；长度变化不是噪声率",
    }
