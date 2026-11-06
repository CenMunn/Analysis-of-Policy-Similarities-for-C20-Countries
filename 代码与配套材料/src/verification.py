"""交付核验：数量、ID、范数、来源及固定实验口径。"""
from pathlib import Path
import json,platform,sys,importlib.metadata
import numpy as np
from scipy import sparse
from .common import *

def verify(output):
    out=Path(output);checks=[]
    def check(name,test,details=''):
        checks.append(dict(check=name,passed=bool(test),details=details))
        if not test:raise AssertionError((name,details))
    cleaning=read_json(out/'01_数据清洗/阶段摘要.json')
    check('原始文档数量',cleaning['raw_documents']==2989)
    check('最终事件分层',cleaning['final_event_records']==5965 and cleaning['layers']=={'主分析候选':782,'扩展候选':5183},cleaning['layers'])
    ev=read_events(out/'01_数据清洗/最终分析输入/全部事件记录.jsonl')
    check('事件ID唯一',len({e['event_record_id'] for e in ev})==len(ev))
    check('固定处置重现',canonical(ev)==read_json(ROOT/'resources/cleaning/分析处置.json')['expected_canonical_sha256'])
    main=read_csv(out/'01_数据清洗/主分析候选.csv');extended=read_csv(out/'01_数据清洗/扩展候选.csv')
    m_ids={r['event_record_id'] for r in main};e_ids={r['event_record_id'] for r in extended}
    check('主扩单列且不混淆',len(main)==782 and len(extended)==5183 and not m_ids&e_ids and len(m_ids|e_ids)==5965)
    for r in read_csv(out/'01_数据清洗/最终国家统计.csv'):
        a=read_csv(out/f"01_数据清洗/按国家/main/{r['country']}.csv")
        b=read_csv(out/f"01_数据清洗/按国家/extended/{r['country']}.csv")
        c=read_csv(out/f"01_数据清洗/按国家/main_extended/{r['country']}.csv")
        check(r['country']+' 事件导出对账',len(a)==int(r['main_events']) and len(b)==int(r['extended_events'])
              and len(c)==int(r['total_event_records']) and len(c)==len(a)+len(b))
    meta={}
    for u in ['event','article_policy']:
      for v in ['main','main_extended']:
        ds=parse_docs(out/f'02_分词与TFIDF/{u}/{v}/元数据.csv');meta[u,v]=ds
        check(f'{u}/{v} 文档ID唯一',len({d['analysis_doc_id'] for d in ds})==len(ds))
        for k in [50,100,200,'all']:
            x=sparse.load_npz(out/f'02_分词与TFIDF/{u}/{v}/TFIDF_{k}.npz')
            check(f'{u}/{v}/{k} 稀疏维度',x.shape==(len(ds),11258))
            n=np.asarray(x.multiply(x).sum(axis=1)).ravel()
            check(f'{u}/{v}/{k} L2规范',np.all((n<1e-12)|(np.abs(n-1)<1e-6)))
            ft=np.load(out/f'03_词向量/{u}/{v}/FastText_{k}.npy')
            check(f'{u}/{v}/{k} fastText对齐',ft.shape==(len(ds),300) and np.isfinite(ft).all())
        bg=np.load(out/f'03_词向量/{u}/{v}/BGE_complete_all.npy')
        check(f'{u}/{v} BGE对齐',bg.shape==(len(ds),512) and np.isfinite(bg).all())
    ki=read_csv(out/'02_分词与TFIDF/K输入诊断.csv')
    for v,n in [('main',597),('main_extended',1868)]:
        r=next(r for r in ki if r['unit']=='article_policy' and r['view']==v and r['K']=='all')
        check(f'{v} 有效文章数',int(r['valid'])==n)
    estimated=read_csv(out/'05_评价/词数精细估计.csv')
    for r in estimated:
        expected=(52,47,64) if r['view']=='main' else (144,132,157)
        check(r['view']+' 最小K及条件区间',tuple(int(r[k]) for k in ['K95','ci_low','ci_high'])==expected)
    cov=read_csv(out/'04_国家关系/国家覆盖.csv')
    for v,n in [('main',13),('main_extended',18)]:
        a=[r for r in cov if r['unit']=='article_policy' and r['view']==v and r['method']=='TFIDF' and r['scheme']=='国家']
        check(v+' 国家覆盖',len(a)==20 and sum(int(r['n_unique_texts'])>0 for r in a)==n)
    # Every exported CSV must decode strictly with uniform Unicode headers.
    paths=list(out.rglob('*.csv'));totalrows=0
    for p in paths:totalrows+=len(read_csv(p))
    write_json(out/'核验/环境.json',dict(python=sys.version,platform=platform.platform(),
        packages={p:importlib.metadata.version(p) for p in ['numpy','scipy','scikit-learn','jieba','matplotlib']}))
    write_csv(out/'核验/检查明细.csv',checks)
    result=dict(passed=True,checks=len(checks),csv_files=len(paths),csv_rows=totalrows,
        original_data_preserved=True,independent_semantic_acceptance=False,
        scope='工程重现及与冻结实验一致；不替代人工语义验收')
    write_json(out/'核验/运行核验.json',result);return result

def freeze(output):
    out=Path(output)
    files={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for folder in ['src','resources','输入'] for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    for name in ['config.json','运行实验.py','一键运行.cmd','requirements.txt','requirements-bge.txt']:
        files[name]=sha(ROOT/name)
    write_json(out/'核验/输入代码资源校验.json',files)
    write_json(out/'核验/输出校验.json',{str(p.relative_to(out)).replace('\\','/'):sha(p) for p in out.rglob('*') if p.is_file() and '运行缓存' not in p.parts and p.name!='输出校验.json'})

