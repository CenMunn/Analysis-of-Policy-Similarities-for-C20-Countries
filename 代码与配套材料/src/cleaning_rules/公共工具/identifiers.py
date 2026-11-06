import json,hashlib
def ident(prefix,data):return prefix+hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:20]
