"""统一 UTF-8-SIG CSV、UTF-8 JSON 和稳定标识。"""
import csv,hashlib,json
from pathlib import Path

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def read_jsonl(path):
    with Path(path).open(encoding='utf8') as f:return [json.loads(s) for s in f if s.strip()]

def write_json(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')

def write_jsonl(path,rows):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf8') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')

def write_csv(path,rows,fields=None):
    rows=list(rows);p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    fields=fields or list(dict.fromkeys(k for r in rows for k in r)) or ['说明']
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader()
        for r in rows:w.writerow({k:'' if v is None else json.dumps(v,ensure_ascii=False,separators=(',',':')) if isinstance(v,(dict,list,tuple)) else v for k,v in r.items()})

def manifest(root,exclude=()):
    root=Path(root)
    return {p.relative_to(root).as_posix():sha256(p) for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.relative_to(root).as_posix() not in exclude}
