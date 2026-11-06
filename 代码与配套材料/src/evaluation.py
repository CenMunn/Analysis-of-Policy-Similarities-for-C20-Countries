"""第五部分：固定参考配对、词数覆盖标准与来源组重抽样。"""
from pathlib import Path
from collections import defaultdict,Counter
import hashlib,math,json
import numpy as np
from scipy import sparse
from scipy.stats import spearmanr
from .common import *
from .country_analysis import read_vectors,aggregate_country_vectors

def rho(x,y):
    if len(x)<3 or len(set(x))<2 or len(set(y))<2:return None
    return float(spearmanr(x,y).statistic)

def exact_quantile(values,coverage=.95):
    return int(np.sort(values)[math.ceil(coverage*len(values)-1e-12)-1])

def grouped_bootstrap(needs,groups,strata,repetitions,seed):
    names=sorted(groups);where={g:i for i,g in enumerate(names)};hist=np.zeros((len(names),int(needs.max())+1),dtype=np.int64)
    for g,ix in groups.items():hist[where[g]]=np.bincount(needs[ix],minlength=hist.shape[1])
    strata_ix=[np.array([where[g] for g in strata[s]]) for s in sorted(strata)]
    rng=np.random.default_rng(seed);result=[]
    for start in range(0,repetitions,200):
        n=min(200,repetitions-start);sample=np.zeros((n,hist.shape[1]),dtype=np.int64)
        for ix in strata_ix:
            counts=rng.multinomial(len(ix),np.full(len(ix),1/len(ix)),size=n);sample+=counts@hist[ix]
        total=sample.sum(axis=1);threshold=np.ceil(.95*total-1e-12).astype(int)
        result.extend(np.argmax(np.cumsum(sample,axis=1)>=threshold[:,None],axis=1).tolist())
    return np.array(result)

def word_count_experiment(output):
    out=Path(output);cfg=read_json(ROOT/'config.json');summary=[];curves=[];details=[];boot=[];countries=[]
    for vi,view in enumerate(['main','main_extended']):
        folder=out/f'02_分词与TFIDF/article_policy/{view}'
        ds=parse_docs(folder/'元数据.csv');w=sparse.load_npz(folder/'未规范化权重.npz').tocsr()
        ix=np.flatnonzero(np.diff(w.indptr)>0);valid=[ds[i] for i in ix];maximum=int(np.diff(w.indptr).max())
        mass=np.zeros((len(ix),maximum+1));needed=[];types=[]
        for j,i in enumerate(ix):
            values=np.sort(w.data[w.indptr[i]:w.indptr[i+1]])[::-1];c=np.cumsum(values)/values.sum()
            mass[j,1:len(c)+1]=c;mass[j,len(c)+1:]=1;needed.append(int(np.searchsorted(c,.99-1e-12)+1));types.append(len(c))
        needed=np.array(needed);types=np.array(types);k=exact_quantile(needed)
        assert np.mean(needed<=k)>=.95 and np.mean(needed<=k-1)<.95
        ar=aggregate_country_vectors(w,ds,mode='group_equal',country_universe=cfg['country_universe'])
        groups=defaultdict(list);strata=defaultdict(list)
        for j,d in enumerate(valid):groups[ar['group_membership'][d['analysis_doc_id']]].append(j)
        for g,ii in sorted(groups.items()):strata['|'.join(sorted({c for j in ii for c in valid[j]['countries']}))].append(g)
        replicates=grouped_bootstrap(needed,groups,strata,cfg['bootstrap'],cfg['seed']+vi)
        low,high=np.quantile(replicates,[.025,.975],method='inverted_cdf').astype(int)
        summary.append(dict(view=view,valid_texts=len(ix),groups=len(groups),K95=k,ci_low=int(low),ci_high=int(high),
                            practical_roundup=math.ceil(high/10)*10,success=float(np.mean(needed<=k)),
                            mean_mass=float(mass[:,k].mean()),singleton_strata=sum(len(v)==1 for v in strata.values())))
        for kk in range(1,maximum+1):curves.append(dict(view=view,K=kk,fraction_99_mass=float(np.mean(needed<=kk)),mean_mass=float(mass[:,kk].mean()),truncated=int(np.sum(types>kk))))
        for j,d in enumerate(valid):details.append(dict(view=view,analysis_doc_id=d['analysis_doc_id'],unique_types=int(types[j]),K99=int(needed[j]),group=ar['group_membership'][d['analysis_doc_id']]))
        boot.extend(dict(view=view,replicate=i+1,K95=int(v)) for i,v in enumerate(replicates))
        for c in cfg['country_universe']:
            ii=[j for j,d in enumerate(valid) if c in d['countries']]
            countries.append(dict(view=view,country=c,n=len(ii),K95=exact_quantile(needed[ii]) if ii else None,
                at_global=float(np.mean(needed[ii]<=k)) if ii else None,low_coverage=len(ii)<20))
    for name,rows in [('词数精细估计',summary),('逐整数K曲线',curves),('逐文本所需K',details),('重抽样逐次记录',boot),('各国词数覆盖',countries)]:write_csv(out/f'05_评价/{name}.csv',rows)
    write_json(out/'05_评价/词数协议.json',dict(coverage=.95,mass=.99,repetitions=cfg['bootstrap'],seed=cfg['seed'],
        resampling='按来源关联连通组，组国家集合分层，组内文本共同抽取',
        interpretation='固定语料K为精确描述量；区间仅为同类来源可交换假设下条件性95%百分位区间，非语义正确率',
        fixed_vocabulary_and_idf=True,labels_used=False))

def run_evaluation(output):
    out=Path(output);refs=read_json(ROOT/'resources/evaluation/参考配对.json')
    prior=read_csv(ROOT/'resources/evaluation/版本对照记录.csv')
    subsets={}
    for r in prior:
        if r['input_version']=='new' and r['method']=='TFIDF':subsets[r['sample'],r['scope'],r['axis']]=json.loads(r['pair_ids'])
    cache={};pred=[];display_checks=[]
    for view in ['main','main_extended']:
        docs=parse_docs(out/f'02_分词与TFIDF/event/{view}/元数据.csv');ix={d['analysis_doc_id']:i for i,d in enumerate(docs)}
        for method in ['TFIDF','FastText','BGE_complete','FastText_center']:
            x=read_vectors(out,'event',view,method)
            for r in refs:
                if r['view']!=view or not r['active_pair']:continue
                ia=ix['E-'+r['new_events_a'][0]];ib=ix['E-'+r['new_events_b'][0]]
                for pos,side in [(ia,'a'),(ib,'b')]:
                    actual=docs[pos]['text'];reference=r['new_text_'+side]
                    # The reference form joins disjoint source spans with a visible ellipsis;
                    # the encoder input joins those same spans with a newline.
                    accepted=actual==reference or actual==reference.replace(' … ','\n')
                    assert accepted,(r['pair_id'],side,'分析文本与参考文本语义不一致')
                    if actual!=reference:display_checks.append(dict(pair_id=r['pair_id'],side=side,
                        change='仅把展示用跨度分隔符替换成编码用换行',actual_text=actual,reference_text=reference))
                value=float(x[ia].multiply(x[ib]).sum()) if sparse.issparse(x) else float(x[ia]@x[ib])
                cache[r['pair_id'],method]=value
                pred.append(dict(pair_id=r['pair_id'],view=view,method=method,cosine=value))
    by={r['pair_id']:r for r in refs};metrics=[]
    for (sample,scope,axis),ids in subsets.items():
        selected=[i for i in ids if by[i]['active_pair'] and isinstance(by[i][axis],int)]
        assert len(selected)==len(ids)
        for method in ['TFIDF','FastText','BGE_complete','FastText_center']:
            value=rho([cache[i,method] for i in selected],[by[i][axis] for i in selected])
            metrics.append(dict(sample=sample,scope=scope,axis=axis,method=method,n=len(selected),spearman=value,
                                pair_ids=selected,label_origin='大模型辅助参考，非独立真人逐条验收'))
            old=next(r for r in prior if r['sample']==sample and r['scope']==scope and r['axis']==axis and r['input_version']=='new' and r['method']==('FastText_center_newmean' if method=='FastText_center' else method))
            assert abs(float(old['spearman'])-value)<1e-10,(sample,method,axis,value,old['spearman'])
    write_csv(out/'05_评价/方法对照.csv',metrics);write_csv(out/'05_评价/文本对预测.csv',pred)
    write_csv(out/'05_评价/参考展示文本核验.csv',display_checks,['pair_id','side','change','actual_text','reference_text'])
    write_json(out/'05_评价/评价范围.json',dict(registered_pairs=len(refs),active_pairs=sum(r['active_pair'] for r in refs),
        inactive_pairs=sum(not r['active_pair'] for r in refs),label_source='大模型辅助参考，用户整体确认',
        independent_human=False,whole_corpus_precision=None,whole_corpus_recall=None,whole_corpus_F_measure=None,
        warning='专项样本和框内随机分别报告；失效配对保留去向，不以相关系数当准确率。'))
    examples=[];events={e['event_record_id']:e for e in read_events(out/'01_数据清洗/最终分析输入/全部事件记录.jsonl')}
    # Explanatory examples only; never added to the scoring sample.
    for key,kind in [('DEV-031','主题及投资措施相近'),('DEV-047','同主题而措施方向相反'),('DEV-050','同一战略的不同版本')]:
        r=by[key]
        examples.append(dict(pair_id=key,case_type=kind,text_a=r['new_text_a'],text_b=r['new_text_b'],
            event_ids_a=r['new_events_a'],event_ids_b=r['new_events_b'],
            sources_a=[events[k]['sources'] for k in r['new_events_a']],sources_b=[events[k]['sources'] for k in r['new_events_b']],
            reference_topic=r['topic'],reference_measure=r['measure'],reference_direction=r['direction'],reference_state=r['state'],
            reason=r['reason'],**{m:cache[key,m] for m in ['TFIDF','FastText','BGE_complete','FastText_center']}))
    write_csv(out/'05_评价/课堂真实案例.csv',examples)
    word_count_experiment(out)
