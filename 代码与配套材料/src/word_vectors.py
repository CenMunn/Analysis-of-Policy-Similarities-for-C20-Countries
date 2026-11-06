"""Offline BGE encoder worker. Run with torch/transformers environment."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import time
import numpy as np

ENCODING_VERSION='bge-cls-window510-overlap64-newtoken-v1'


def run_vectors(output,reencode=False):
    """第三部分：加权fastText与冻结BGE完整文本表征。"""
    from scipy import sparse
    from sklearn.preprocessing import normalize
    from .common import ROOT,read_csv,parse_docs,write_csv,write_json,read_json,sha
    output=Path(output)
    docs=[]
    for unit in ['event','article_policy']:
        for view in ['main','main_extended']:docs.extend(parse_docs(output/f'02_分词与TFIDF/{unit}/{view}/元数据.csv'))
    cache=ROOT/'resources/vectors/bge_text_vectors.npz'
    identity=read_json(ROOT/'resources/vectors/bge_identity.json');model=ROOT/'resources/models/BGE-small-native'
    assert sha(cache)==identity['embeddings_sha256']
    assert all(sha(model/n)==h for n,h in identity['model_files'].items())
    if reencode:
        write_csv(output/'03_词向量/BGE输入/分析文档.csv',docs)
        encode(output/'03_词向量/BGE输入',model,output/'03_词向量/BGE推理',batch_size=24,device='auto')
        cache=output/'03_词向量/BGE推理/embeddings.npz'
    with np.load(cache) as f:bge={str(t):v for t,v in zip(f['text_sha256'],f['vectors'])}
    with np.load(ROOT/'resources/vectors/fasttext_subset.npz') as f:ft={str(t):v for t,v in zip(f['terms'],f['vectors'])}
    report=[]
    for unit in ['event','article_policy']:
        vocab=read_csv(ROOT/f'resources/tfidf/{unit}.csv');vocab.sort(key=lambda r:int(r['term_id']))
        embedding=np.array([ft[r['term']] for r in vocab]);main_mean=None
        for view in ['main','main_extended']:
            rows=parse_docs(output/f'02_分词与TFIDF/{unit}/{view}/元数据.csv')
            target=output/f'03_词向量/{unit}/{view}';target.mkdir(parents=True)
            for k in [50,100,200,'all']:
                x=sparse.load_npz(output/f'02_分词与TFIDF/{unit}/{view}/TFIDF_{k}.npz')
                v=normalize(np.asarray(x@embedding));np.save(target/f'FastText_{k}.npy',v)
                report.append(dict(unit=unit,view=view,method='FastText',K=k,valid=int((np.linalg.norm(v,axis=1)>1e-10).sum()),
                    dimension=300,weight_coverage=1.0,description='对冻结词表有向量；词表外词见第二部分，不等于语义正确'))
                if k=='all':
                    valid=np.linalg.norm(v,axis=1)>1e-10
                    if view=='main':
                        main_mean=v[valid].mean(axis=0);write_json(output/f'03_词向量/{unit}/去均值参数.json',dict(fit='main非零文本',labels_used=False,mean=main_mean.tolist()))
                    centered=np.zeros_like(v);centered[valid]=normalize(v[valid]-main_mean)
                    np.save(target/'FastText_center_all.npy',centered)
            vv=np.array([bge[hashlib.sha256(d['text'].encode()).hexdigest()] if d['text'] else np.zeros(512) for d in rows])
            np.save(target/'BGE_complete_all.npy',vv)
            report.append(dict(unit=unit,view=view,method='BGE_complete',K='all',valid=int((np.linalg.norm(vv,axis=1)>1e-10).sum()),
                dimension=512,weight_coverage='',description='本轮重新模型推理' if reencode else '按完整文本哈希复用核验过的冻结模型编码'))
    write_csv(output/'03_词向量/向量质量.csv',report)
    write_json(output/'03_词向量/阶段摘要.json',dict(bge_reencoded=reencode,models_trained=False,
       models=['fastText cc.zh.300','BAAI/bge-small-zh-v1.5'],reference_labels_used=False))

def resolve_device(requested,cuda_available):
    if requested=='auto':return 'cuda' if cuda_available else 'cpu'
    if requested not in {'cpu','cuda'} or (requested=='cuda' and not cuda_available):
        raise ValueError('Requested inference device unavailable')
    return requested


def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def cache_identity(input_run,model_dir):
    model_dir=Path(model_dir)
    files=['config.json','model.safetensors','tokenizer.json','tokenizer_config.json','special_tokens_map.json','vocab.txt']
    return dict(encoding_version=ENCODING_VERSION,
         analysis_documents_sha256=file_hash(Path(input_run)/'分析文档.csv'),
         model_files={name:file_hash(model_dir/name) for name in files})


def token_windows(tokens, size=510, overlap=64):
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError('Invalid chunk window')
    result=[]
    start=previous_end=0
    while start < len(tokens):
        end=min(start+size,len(tokens))
        result.append((start,end,end-previous_end))
        previous_end=end
        if end==len(tokens):
            break
        start=end-overlap
    return result


def encode(input_run,model_dir,output,batch_size=32,threads=4,device='auto'):
    out=Path(output).resolve()
    if out.exists():raise FileExistsError('拒绝覆盖已有编码目录: '+str(out))
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TOKENIZERS_PARALLELISM']='false'
    import torch
    import transformers
    from transformers import AutoTokenizer,AutoModel
    started=time.perf_counter()
    torch.set_num_threads(threads)
    device=resolve_device(device,torch.cuda.is_available())
    if device=='cuda':
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cudnn.allow_tf32=False
    tokenizer=AutoTokenizer.from_pretrained(model_dir,local_files_only=True)
    model=AutoModel.from_pretrained(model_dir,local_files_only=True).to(device).eval()
    unique={}
    with (Path(input_run)/'分析文档.csv').open(encoding='utf-8-sig',newline='') as handle:
        for row in csv.DictReader(handle):
            if row['has_content']=='True':
                text=row['text']
                key=hashlib.sha256(text.encode('utf-8')).hexdigest()
                unique[key]=text
    keys=sorted(unique)
    dimension=model.config.hidden_size
    sums=np.zeros((len(keys),dimension),dtype=np.float64)
    weights=np.zeros(len(keys),dtype=np.float64)
    records=[]
    pending=[]
    def flush():
        if not pending:
            return
        features=tokenizer.pad([p[2] for p in pending],padding=True,return_tensors='pt')
        features={k:v.to(device) for k,v in features.items()}
        with torch.inference_mode():
            values=model(**features).last_hidden_state[:,0].float()
            values=torch.nn.functional.normalize(values,p=2,dim=1).cpu().numpy()
        for (index,weight,_),value in zip(pending,values):
            sums[index]+=weight*value
            weights[index]+=weight
        pending.clear()
    for index,key in enumerate(keys):
        tokens=tokenizer(unique[key],add_special_tokens=False,truncation=False)['input_ids']
        windows=token_windows(tokens)
        records.append(dict(text_sha256=key,characters=len(unique[key]),tokens=len(tokens),chunks=len(windows),
                            overflow_512=len(tokens)+2>512,covered_tokens=sum(w[2] for w in windows),
                            lost_tokens=0,windows=json.dumps(windows)))
        for start,end,new_weight in windows:
            features=tokenizer.prepare_for_model(tokens[start:end],add_special_tokens=True,
                 truncation=False,return_attention_mask=True,verbose=False)
            pending.append((index,new_weight,features))
            if len(pending)>=batch_size:
                flush()
        if index%500==0:
            print(f'BGE {index}/{len(keys)} chunks covered',flush=True)
    flush()
    norms=np.linalg.norm(sums,axis=1)
    valid=np.isfinite(sums).all(axis=1)&(norms>1e-10)
    sums[valid]/=norms[valid,None]
    sums[~valid]=0
    out.mkdir(parents=True,exist_ok=False)
    np.savez_compressed(out/'embeddings.npz',text_sha256=np.array(keys),vectors=sums.astype(np.float32),valid=valid)
    with (out/'长度与分块.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records)
    summary=dict(model='BAAI/bge-small-zh-v1.5',dimension=dimension,pooling='CLS',normalization='chunk L2 -> newly covered token weighted mean -> document L2',
          instruction='',symmetric_encoding=True,max_model_length=512,content_window=510,overlap=64,
          overflow_handling='all original token IDs covered by overlapping windows; not full-document attention; no discarded suffix',
          model_dir=str(model_dir),texts=len(keys),valid_texts=int(valid.sum()),overflow_texts=sum(r['overflow_512'] for r in records),
          tokens_lost=sum(r['lost_tokens'] for r in records),elapsed_seconds=time.perf_counter()-started,
          torch=torch.__version__,transformers=transformers.__version__,numpy=np.__version__,threads=threads,batch_size=batch_size,
          device=device,precision='float32',gpu_name=torch.cuda.get_device_name(0) if device=='cuda' else '')
    (out/'编码说明.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    identity=cache_identity(input_run,model_dir)
    identity['embeddings_sha256']=file_hash(out/'embeddings.npz')
    (out/'缓存身份.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


