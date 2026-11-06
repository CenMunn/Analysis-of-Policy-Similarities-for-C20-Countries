"""证据映射、分析单位、词元和稀疏数值操作。"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path

import jieba
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.preprocessing import normalize


def run_features(output):
    """第二部分：统一词元，复用冻结词表/IDF，重算权重和Top-K。"""
    from .common import ROOT,read_csv,read_events,write_csv,write_json
    output=Path(output);inp=output/'01_数据清洗/最终分析输入'
    events=read_events(inp/'全部事件记录.jsonl')
    index={r['file_id']:r for r in read_csv(inp/'追溯/来源索引.csv')}
    texts={k:(inp/r['normalized_text_file']).read_text(encoding='utf-8-sig') for k,r in index.items()}
    docs,links,errors=build_documents(events,texts,index)
    assert not errors,errors[:3]
    groups={r['file_id']:r['resampling_group'] for r in read_csv(ROOT/'resources/来源组.csv')}
    for d in docs:d['resampling_groups']=sorted({groups[k] for k in d['source_ids']})
    res=ROOT/'resources/tokens';words=lambda n:(res/n).read_text(encoding='utf-8-sig').split()
    tokenizer=Tokenizer(domain_terms={r['term']:int(r['frequency']) for r in read_csv(res/'领域词典.csv')},
        stopwords=words('基础停用词.txt'),protected=words('语义保护词.txt'),country_names=words('国家别名.txt'),
        base_dict=res/'jieba_dict.txt',cache_dir=output/'运行缓存',hmm=False)
    diagnostics=[];cache={};oov=Counter()
    for unit in ['event','article_policy']:
        vocab=read_csv(ROOT/f'resources/tfidf/{unit}.csv');vocab.sort(key=lambda r:int(r['term_id']))
        model={'vocabulary':{r['term']:int(r['term_id']) for r in vocab},'idf':np.array([float(r['idf']) for r in vocab])}
        for view in ['main','main_extended']:
            rows=[d for d in docs if d['unit']==unit and d['view']==view];folder=output/f'02_分词与TFIDF/{unit}/{view}'
            write_csv(folder/'元数据.csv',rows);tokenlists=[]
            for d in rows:
                terms=[]
                for s in d['segments']:
                    text=d['text'][s['start']:s['end']]
                    if text not in cache:cache[text]=[t['term'] for t in tokenizer.tokenize(text) if t['keep']]
                    terms.extend(cache[text])
                tokenlists.append(terms)
            _,weights=transform_tfidf(tokenlists,model)
            sparse.save_npz(folder/'未规范化权重.npz',weights);write_json(folder/'词元.json',tokenlists)
            oov.update(t for ts in tokenlists for t in ts if t not in model['vocabulary'])
            for k in [50,100,200,'all']:
                x,diags=select_top_k(weights,None if k=='all' else k);sparse.save_npz(folder/f'TFIDF_{k}.npz',x)
                valid=[d for d in diags if d['valid']];mass=[]
                for i,d in enumerate(diags):
                    if d['valid']:
                        selected=x.indices[x.indptr[i]:x.indptr[i+1]]
                        mass.append(float(weights[i,selected].sum()/weights[i].sum()))
                diagnostics.append(dict(unit=unit,view=view,K=k,valid=len(valid),total_rows=len(rows),
                    truncated=sum(d['truncated'] for d in valid),identical_to_all=sum(not d['truncated'] for d in valid),
                    mean_weight_mass=float(np.mean(mass))))
    write_csv(output/'02_分词与TFIDF/K输入诊断.csv',diagnostics)
    write_csv(output/'02_分词与TFIDF/词表外词.csv',[dict(term=t,count=n) for t,n in oov.items()],['term','count'])
    write_json(output/'02_分词与TFIDF/阶段摘要.json',dict(fit_scope='冻结main_extended词表与IDF：article N=1873,event N=6042',
        vocabulary_size=len(model['vocabulary']),oov_occurrences=sum(oov.values()),configs=diagnostics))
    return docs


def stable_id(prefix, value):
    return prefix + hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]


def verify_source(fact, source, text):
    """只验证既有范围；逐非空白字符对齐，不搜索或改写事实。"""
    parts = source.get('text_parts') or [source]
    source_chars = []
    last_end = -1
    for p in parts:
        try:
            start, end = int(p['start']), int(p['end'])
        except (ValueError, KeyError, TypeError):
            return None
        if start < 0 or end < start or end > len(text) or start < last_end:
            return None
        if p.get('file_id', source['file_id']) != source['file_id']:
            return None
        last_end = end
        if 'text' in p and p['text'] != text[start:end]:
            return None
        source_chars.extend((c, i) for i, c in enumerate(text[start:end], start) if not c.isspace())
    fact_chars = [(c, i) for i, c in enumerate(fact) if not c.isspace()]
    if not fact_chars or [c for c,_ in fact_chars] != [c for c,_ in source_chars]:
        return None
    spans = []
    for (_, a), (_, s) in zip(fact_chars, source_chars):
        if spans and spans[-1]['fact_end'] == a and spans[-1]['source_end'] == s:
            spans[-1]['fact_end'] += 1
            spans[-1]['source_end'] += 1
        else:
            spans.append({'fact_start':a,'fact_end':a+1,'file_id':source['file_id'],
                          'source_start':s,'source_end':s+1})
    return spans


def prepare_source(fact, source, text, display_note=''):
    """仅显式展示省略号可由已验证原文片段重建；不模糊匹配或改写事实。"""
    spans = verify_source(fact, source, text)
    if spans is not None:
        return fact, spans
    parts = source.get('text_parts', [])
    # 字段备注并不统一；结构化片段必须逐段含字面text，并精确组成展示串。
    # 此条件不允许猜测省略号的位置，也不移除原文自身的省略号。
    if len(parts) < 2 or not all(isinstance(p,dict) and 'text' in p for p in parts):
        return None
    values = []
    for part in parts:
        try:
            a, b = int(part['start']), int(part['end'])
        except (KeyError, TypeError, ValueError):
            return None
        if a < 0 or b <= a or b > len(text):
            return None
        values.append(text[a:b])
    expected = ' … '.join(values)
    if ''.join(expected.split()) != ''.join(fact.split()):
        return None
    analysis_text = '\n'.join(values)
    spans = verify_source(analysis_text, source, text)
    return (analysis_text, spans) if spans is not None else None


def build_documents(events, source_texts, source_index):
    """每个事件唯一代表来源；两个单位、两视图，保留所有事件去向。"""
    ids = [r['event_record_id'] for r in events]
    if len(ids) != len(set(ids)):
        raise ValueError('event_record_id重复，不能静默去重')
    prepared, anomalies = [], []
    for event in sorted(events, key=lambda r:r['event_record_id']):
        candidates = []
        for s in event.get('sources', []):
            if s['file_id'] not in source_texts:
                continue
            prepared_source = prepare_source(event['policy_fact'], s, source_texts[s['file_id']],
                                             event.get('text_display_note', ''))
            if prepared_source is not None:
                analysis_text, spans = prepared_source
                candidates.append((s, spans, analysis_text))
        candidates.sort(key=lambda pair:(pair[0]['file_id'], int(pair[0]['start']),pair[0].get('event_id','')))
        representative, spans, analysis_text = candidates[0] if candidates else (None, [], event['policy_fact'])
        if representative is None:
            anomalies.append({'event_record_id':event['event_record_id'], 'reason':'无可验证代表来源；保留为独立分析单位'})
        countries = sorted(set(event.get('countries',[])))
        scope = json.dumps(countries,ensure_ascii=False,separators=(',',':'))
        key = (representative['file_id']+'|'+scope) if representative else 'orphan|'+event['event_record_id']
        prepared.append({'event':event,'representative':representative,'spans':spans,
                         'analysis_text':analysis_text,
                         'candidate_count':len(candidates),'article_id':stable_id('AP-',key)})
    grouped = defaultdict(list)
    for p in prepared:
        grouped[('event', 'E-'+p['event']['event_record_id'])].append(p)
        grouped[('article_policy',p['article_id'])].append(p)
    docs, mappings = [], []
    for (unit, doc_id), items in sorted(grouped.items()):
        items.sort(key=lambda p: (int(p['representative']['start']) if p['representative'] else 0,
                                  p['event']['event_record_id']))
        source_ids = sorted({s['file_id'] for p in items for s in p['event'].get('sources',[])})
        near_groups = sorted({source_index.get(fid,{}).get('near_duplicate_group','') for fid in source_ids}-{''})
        source_groups = sorted({source_index.get(fid,{}).get('source_group','') for fid in source_ids}-{''})
        countries = sorted({c for p in items for c in p['event'].get('countries',[])})
        def joint_label(e):
            if len(e.get('countries',[]))<=1:
                return '单国记录'
            if len(e.get('joint_participants',[]))>1:
                return '输入声明多方参与，未独立核验'
            return '多国归属待解释；无共同参与声明，未独立核验'
        joint_status = '；'.join(sorted({joint_label(p['event']) for p in items}))
        for p in items:
            e, rep = p['event'], p['representative']
            mappings.append({'unit':unit,'analysis_doc_id':doc_id,'event_record_id':e['event_record_id'],
                'data_layer':e['data_layer'],'representative_source':rep,'source_spans':p['spans'],
                'all_sources':e.get('sources',[]),'verified_source_count':p['candidate_count'],
                'display_text':e['policy_fact'],'analysis_text':p['analysis_text'],
                'representative_reason':'既有范围复原一致后按file_id/start/event_id固定排序' if rep else '无法验证，独立保留',
                'countries':e.get('countries',[]),'joint_participants':e.get('joint_participants',[]),
                'joint_status':joint_label(e)})
        for view in ['main','main_extended']:
            included = [p for p in items if view=='main_extended' or p['event']['data_layer']=='主分析候选']
            offset, segments, texts = 0, [], []
            for p in included:
                e = p['event']; fact=p['analysis_text']
                if texts:
                    offset += 1
                segments.append({'event_record_id':e['event_record_id'],'start':offset,'end':offset+len(fact),
                                 'source_spans':p['spans'],'data_layer':e['data_layer']})
                texts.append(fact); offset += len(fact)
            attributes = [{k:v for k,v in p['event'].items() if k not in
                           {'sources','policy_fact'}} for p in included]
            docs.append({'analysis_doc_id':doc_id,'unit':unit,'view':view,'text':'\n'.join(texts),
                'display_text':'\n'.join(p['event']['policy_fact'] for p in included),
                'event_ids':[p['event']['event_record_id'] for p in included],
                'countries':countries,'source_ids':source_ids,'source_groups':source_groups,
                'near_duplicate_groups':near_groups,'joint_status':joint_status,
                'policy_states':sorted({p['event'].get('policy_state','') for p in included}),
                'segments':segments,'event_attributes':attributes,'has_content':bool(texts)})
    return docs, mappings, anomalies


class Tokenizer:
    """保持原文偏移；过滤仅改变词元的keep标记。"""
    def __init__(self, domain_terms=None, stopwords=None, protected=None, country_names=None,
                 keep_countries=False, base_dict=None, hmm=False, cache_dir=None):
        self.stopwords=set(stopwords or [])
        self.protected=set(protected or [])
        self.country_names=set(country_names or [])
        self.keep_countries=keep_countries
        self.hmm=hmm
        self.segmenter=jieba.Tokenizer(str(base_dict) if base_dict else None)
        if cache_dir:
            Path(cache_dir).mkdir(parents=True,exist_ok=True)
            self.segmenter.tmp_dir=str(cache_dir)
            self.segmenter.cache_file='jieba-fixed-base.cache'
        self.segmenter.initialize()
        frequencies=domain_terms if isinstance(domain_terms,dict) else {t:1000000 for t in (domain_terms or [])}
        for term in sorted(frequencies):
            frequency=int(frequencies[term])
            if frequency<=0:
                raise ValueError('领域词典控制频次必须大于0：'+term)
            self.segmenter.add_word(term,freq=frequency)

    def tokenize(self, text):
        rows=[]
        pieces=[]
        institution_suffixes={'政府','总统','总理','首相','国会','议会','能源部','财政部','环保署','委员会'}
        for token,start,end in self.segmenter.tokenize(text,HMM=self.hmm):
            country=next((c for c in sorted(self.country_names,key=lambda c:(-len(c),c))
                          if len(c)>=2 and token.startswith(c) and token[len(c):] in institution_suffixes),None)
            if country:
                middle=start+len(country)
                pieces.extend([(country,start,middle),(token[len(country):],middle,end)])
            else:
                pieces.append((token,start,end))
        for token,start,end in pieces:
            term=token.lower() if token.isascii() else token
            if token.isspace():
                keep,reason=False,'空白'
            elif all(unicodedata.category(c)[0] in 'PS' for c in token):
                keep,reason=False,'标点或符号'
            elif re.fullmatch(r'[0-9０-９]+(?:[.,．][0-9０-９]+)*',token):
                keep,reason=False,'纯数字；原文及元数据保留'
            elif not self.keep_countries and term in self.country_names:
                keep,reason=False,'完整国家名词元；原文及元数据保留'
            elif term in self.protected:
                keep,reason=True,'领域或语义保护'
            elif term in self.stopwords:
                keep,reason=False,'基础停用词'
            else:
                keep,reason=True,'有效词'
            rows.append({'token':token,'term':term,'start':start,'end':end,'keep':keep,'reason':reason})
        return rows


def count_matrix(token_lists, vocabulary):
    indptr=[0]; indices=[]; values=[]
    for tokens in token_lists:
        counts=Counter(tokens)
        for term in sorted(counts, key=lambda t:vocabulary.get(t,len(vocabulary))):
            if term in vocabulary:
                indices.append(vocabulary[term]); values.append(counts[term])
        indptr.append(len(indices))
    return sparse.csr_matrix((np.array(values,dtype=np.float64),np.array(indices,dtype=np.int32),
                              np.array(indptr,dtype=np.int32)),shape=(len(token_lists),len(vocabulary)))


def fit_tfidf(token_lists, sublinear=True):
    vocabulary={t:i for i,t in enumerate(sorted({t for row in token_lists for t in row}))}
    counts=count_matrix(token_lists,vocabulary)
    valid=np.diff(counts.indptr)>0
    n=int(valid.sum())
    if not n:
        raise ValueError('参考语料没有有效词，不能拟合TF-IDF')
    transformer=TfidfTransformer(norm=None,smooth_idf=True,sublinear_tf=sublinear)
    transformer.fit(counts[valid])
    weights=sparse.csr_matrix(transformer.transform(counts))
    df=np.asarray((counts[valid]>0).sum(axis=0)).ravel().astype(int)
    return {'vocabulary':vocabulary,'idf':transformer.idf_.copy(),'df':df,'fit_n':n,
            'counts':counts,'weights':weights,'transformer':transformer}


def transform_tfidf(token_lists, model, sublinear=True):
    counts=count_matrix(token_lists,model['vocabulary'])
    weights=counts.copy()
    if sublinear:
        weights.data=1+np.log(weights.data)
    weights=weights.multiply(model['idf']).tocsr()
    return counts,weights


def select_top_k(weights, k):
    weights=sparse.csr_matrix(weights)
    out=weights.copy(); out.data=out.data.copy()
    diagnostics=[]
    for i in range(weights.shape[0]):
        left,right=weights.indptr[i:i+2]
        ids=weights.indices[left:right]; values=weights.data[left:right]
        positive=values>0
        order=np.lexsort((ids,-values))
        order=order[positive[order]]
        take=order if k is None else order[:k]
        mask=np.zeros(right-left,dtype=bool); mask[take]=True
        out.data[left:right][~mask]=0
        total=float(np.dot(values,values))
        retained=float(np.dot(values[take],values[take]))
        rho=retained/total if total else None
        diagnostics.append({'selected_types':len(take),'unique_types':len(order),'valid':bool(total),
                            'truncated':len(take)<len(order),'retained_energy':rho,
                            'cosine_to_all':math.sqrt(rho) if rho is not None else None})
    out.eliminate_zeros()
    if out.nnz:
        out=sparse.csr_matrix(normalize(out,norm='l2',copy=False))
    return out,diagnostics
