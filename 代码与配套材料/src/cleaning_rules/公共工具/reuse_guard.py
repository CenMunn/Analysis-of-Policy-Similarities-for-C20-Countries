"""课堂识别检查点：核验输入、代码、参数、账本和正文。"""
import json,gzip
from collections import defaultdict
from pathlib import Path
from ..公共工具.io_utils import sha256

def load_verified(root,cache,config,input_hash):
    cache=Path(cache).resolve();package=Path(__file__).resolve().parents[3]
    contract=json.loads((cache/'检查点身份.json').read_text('utf-8'))
    if input_hash!=contract['input_sha256']:raise ValueError('识别检查点原始输入不一致')
    if config!=contract['config']:raise ValueError('识别参数变化，必须完整重跑')
    for rel,h in contract['prefix_files'].items():
        if sha256(package/rel)!=h:raise ValueError('识别代码或资源变化：'+rel)
    for rel,h in contract['checkpoint_files'].items():
        if sha256(cache/rel)!=h:raise ValueError('识别检查点损坏：'+rel)
    grouped=defaultdict(list)
    with gzip.open(cache/'事件识别账本.jsonl.gz','rt',encoding='utf-8') as f:
        for line in f:
            if line.strip():
                e=json.loads(line);grouped[e['file_id']].append(e)
    return grouped,dict(checkpoint=cache.name,input_verified=True,
       protected_prefix_files=len(contract['prefix_files']),source_ledger_sha256=contract['source_ledger_sha256'],
       stage='重读原始ZIP并重新规范化；复用冻结识别账本；重新执行末端处理、去重、日期身份登记及导出',
       full_recognition_rerun=False)
