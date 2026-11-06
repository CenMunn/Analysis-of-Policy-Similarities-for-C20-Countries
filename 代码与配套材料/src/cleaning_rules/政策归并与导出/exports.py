"""保守事件归并、政策家族与版本关联、证据导出和完整性核验。"""
import csv,hashlib,json,re,datetime
from collections import Counter,defaultdict
from pathlib import Path
from ..公共工具.io_utils import write_json,write_jsonl,write_csv,read_jsonl
from ..公共工具.identifiers import ident
from ..政策归并与导出.registry_primitives import norm
from ..主体与国家归属.national_scope import G20

EVENT_FIELDS=['event_record_id','policy_id','version_id','policy_name','identity_status','countries','joint_participants','institutions','policy_fact','policy_level','policy_state','data_layer','source_inference_only','report_dates','decision_date','implementation_date','target_years','date_evidence','event_ids','sources','evidence','connection_path','evidence_dimensions','reasons','annotation_origins','independent_acceptance_completed']
EVENT_FIELDS+=['deduplication_basis','source_fact_variants','fact_attributes','text_display_note']
EVENT_FIELDS+=['scheduled_implementation_date','scheduled_decision_date','state_change_date','relative_dates','policy_periods','date_warnings','date_extraction_status','legacy_policy_id','legacy_version_id','policy_identity_candidates','version_verification_status']

def date_fields(text,reports):
    """兼容旧接口，统一转交带角色、精度和冲突记录的日期提取。"""
    from ..政策归并与导出.policy_registry import extract_dates
    return extract_dates(text,reports)


def policy_identity(text,countries,names,event_id):
    """唯一具名文件按国家归家族；无唯一身份的保留事件占位，不冒称独立政策。"""
    candidates=set(re.findall(r'《([^》]{3,90})》',text))
    candidates|={n for n in names if n in text}
    candidates={n for n in candidates if re.search(r'法律|法案|条例|办法|规划|战略|行动计划|政策|计划|法$',n) and not re.search(r'巴黎|京都|时报|日报|报告|杂志|新闻',n)}
    name=next(iter(candidates)) if len(candidates)==1 else ''
    policy_id=ident('POL-',(countries,name)) if name else ident('UNRESOLVED-',event_id)
    vm=re.search(r'第[一二三四五六七八九十\d]+(?:版|次)|(?:19|20)\d\d[—–\-至]+(?:19|20)\d\d',text)
    version_label=vm.group() if vm else ''
    return policy_id,name,version_label

def aggregate_events(events):
    groups=defaultdict(list)
    for e in events:
        if not e['route'].startswith('main_'):continue
        refs=tuple(sorted(norm(x.get('to_text','')) for x in e.get('connection_path',[]) if x.get('to_text')))
        fact=norm(e['text'])
        if e.get('structured_goal'):
            fact='STRUCTURED_GOAL:'+json.dumps(e['structured_goal'],ensure_ascii=False,sort_keys=True)
            refs=()
        key=(tuple(e['countries']),e['policy_level'],e['policy_state'],fact,refs)
        groups[key].append(e)
    rows=[]
    for key,es in sorted(groups.items(),key=lambda x:str(x[0])):
        first=es[0];eid=ident('ER-',key);pid,name,vl=policy_identity(first['text'],list(key[0]),first.get('policy_names',[]),eid)
        dates=date_fields(first['text'],[e.get('reported_at','') for e in es])
        layer='主分析候选' if any(e['delivery_layer']=='主分析候选' for e in es) else '扩展候选'
        sources=[];evidence=[]
        for e in es:
            sources.append(dict(file_id=e['file_id'],event_id=e['event_id'],start=e['start'],end=e['end'],text_parts=e.get('text_parts',[]),source_url=e.get('source_url',''),reported_at=e.get('reported_at',''),excerpt_kind=e.get('source_excerpt_kind','article_body'),excerpt_note=e.get('source_excerpt_note','')))
            evidence+=e['evidence']
        rows.append(dict(event_record_id=eid,policy_id=pid,version_id=ident('VER-',(pid,vl or eid,first['policy_state'])),policy_name=name,
            identity_status='具名政策家族关联，身份版本未独立核验' if name else '身份未定的事件占位，非独立政策',version_label=vl,
            deduplication_basis='纯国家碳中和目标：同国家、目标年份、宣示状态；非独立政策身份核验' if first.get('structured_goal') else '国家、层级、状态、规范文本及规范上下文一致',
            source_fact_variants=sorted({e['text'] for e in es}),
            fact_attributes=first.get('fact_attributes',{}),text_display_note=first.get('text_display_note',''),
            countries=list(key[0]),joint_participants=sorted({c for e in es for c in e.get('joint_participants',[])}) or (list(key[0]) if first.get('event_type')=='joint_policy' else []),
            institutions=sorted({a['text'] for e in es for a in e['roles'].get('actors',[]) if a.get('public')}),policy_fact=first['text'],policy_level=key[1],policy_state=key[2],data_layer=layer,
            source_inference_only=all(e['route']=='main_source_inferred' for e in es),event_ids=sorted(e['event_id'] for e in es),sources=sources,evidence=evidence,
            connection_path=[p for e in es for p in e['connection_path']],evidence_dimensions=[e['evidence_dimensions'] for e in es],
            reasons=sorted({e['reason'] for e in es}),annotation_origins=sorted({e['annotation_origin'] for e in es}),independent_acceptance_completed=False,**dates))
    from ..政策归并与导出.policy_registry import enrich_records
    return enrich_records(rows)

def group_documents(docs):
    """完整正文/同URL先分组；分块指纹召回并经shingle Jaccard核验近重复。"""
    parent={d['file_id']:d['file_id'] for d in docs};buckets=defaultdict(list);sets={};texts={};links=[]
    def root(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    def join(a,b,why,sim):
        x,y=root(a),root(b)
        if x!=y:parent[max(x,y)]=min(x,y)
        links.append(dict(file_a=a,file_b=b,basis=why,similarity=sim))
    exact={};url={}
    for d in docs:
        fid=d['file_id'];t=norm(d['analysis_text']);texts[fid]=t
        if not t:continue
        h=hashlib.sha256(t.encode()).hexdigest()
        if h in exact:join(fid,exact[h],'完整规范正文相同',1)
        else:exact[h]=fid
        if d['url']:
            if d['url'] in url:join(fid,url[d['url']],'相同来源URL',None)
            else:url[d['url']]=fid
        sh={t[i:i+8] for i in range(0,max(0,len(t)-7),4)};sets[fid]=sh
        if len(sh)<10:continue
        hashes=sorted(int.from_bytes(hashlib.blake2b(s.encode(),digest_size=8).digest(),'big') for s in sh)
        candidates=set()
        for h in hashes[:12]:candidates.update(buckets[h])
        for other in candidates:
            if min(len(texts[other]),len(t))/max(len(texts[other]),len(t))<.75:continue
            a=sets[other];sim=len(a&sh)/len(a|sh)
            if sim>=.85:join(fid,other,'8字shingle近重复候选（步长4，Jaccard≥0.85）',round(sim,6))
        for h in hashes[:12]:buckets[h].append(fid)
    for d in docs:d['near_duplicate_group']=ident('DG-',root(d['file_id']))
    return links

def export_results(out,docs,events,units,metadata,issues,cleaning_log,fixed_log,config):
    rows=aggregate_events(events);bydoc={d['file_id']:d for d in docs};group_links=group_documents(docs)
    for e in events:e['near_duplicate_group']=bydoc[e['file_id']]['near_duplicate_group']
    write_jsonl(out/'追溯/事件处置账本.jsonl',events);write_csv(out/'追溯/事件处置账本.csv',events,['event_id','file_id','start','end','text','text_parts','route','delivery_layer','countries','policy_level','policy_state','reason','s_scores','annotation_origin','coverage_repair_rule','coverage_previous_route','coverage_parent_span','focused_rule','focused_previous_route','focused_parent_span'])
    write_csv(out/'追溯/内容接口与动作角色.csv',[e for e in events if e.get('interface_trace')],
        ['event_id','file_id','start','end','text','route','delivery_layer','countries','policy_state','policy_content_contract','interface_trace','optimized_attribution','roles','connection_path','evidence'])
    write_jsonl(out/'全部事件记录.jsonl',rows);write_csv(out/'全部事件记录.csv',rows,EVENT_FIELDS)
    for layer,folder in [('主分析候选','主分析集'),('扩展候选','扩展集')]:
        selected=[r for r in rows if r['data_layer']==layer];write_csv(out/f'{folder}/全部.csv',selected,EVENT_FIELDS)
        for c in sorted(G20):write_csv(out/f'{folder}/按国家/{c}.csv',[r for r in selected if c in r['countries']],EVENT_FIELDS)
    write_csv(out/'扩展集/来源推定单列.csv',[r for r in rows if r['source_inference_only']],EVENT_FIELDS)
    for route in sorted({e['route'] for e in events if not e['route'].startswith('main_')}):
        write_csv(out/f'分类归档/{route}.csv',[e for e in events if e['route']==route],['event_id','file_id','start','end','text','text_parts','route','reason','countries','policy_level','policy_state','annotation_origin'])
    summaries=[]
    for c in sorted(G20):
        rs=[r for r in rows if c in r['countries']];ids={s['file_id'] for r in rs for s in r['sources']};source_count=sum(d['source_country']==c for d in docs)
        summaries.append(dict(country=c,source_documents=source_count,documents_with_retained_events=len(ids),retained_event_occurrences=sum(len(r['event_ids']) for r in rs),exact_event_records=len(rs),
            main_records=sum(r['data_layer']=='主分析候选' for r in rs),extended_records=sum(r['data_layer']=='扩展候选' for r in rs),source_inferred_records=sum(r['source_inference_only'] for r in rs),
            identity_group_placeholders=len({r['policy_id'] for r in rs}),independent_policy_count='',coverage_note='无保留材料' if not rs else '少于10个去重事件，仅探索' if len(rs)<10 else '材料量不均，不能据数量推断政策力度'))
    write_csv(out/'国家数据统计.csv',summaries)
    docrows=[]
    for d in docs:
        clean_file='追溯/规范正文/'+d['file_id'];p=out/clean_file;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(d['analysis_text'],encoding='utf8')
        dr={k:d[k] for k in ['file_id','source_path','source_country','source_group','title','url','published_at','metadata_status','raw_sha256','analysis_sha256','near_duplicate_group']}
        dr.update(normalized_text_file=clean_file,raw_chars=len(d['raw_text']),normalized_chars=len(d['analysis_text']),normalization_empty=not bool(d['analysis_text'].strip()),clean_flags=d['clean_flags'])
        docrows.append(dr)
    write_csv(out/'追溯/来源索引.csv',docrows);write_csv(out/'追溯/元数据关联.csv',metadata);write_csv(out/'追溯/读取与关联异常.csv',issues)
    write_csv(out/'追溯/清理删除证据.csv',cleaning_log);write_csv(out/'追溯/近重复文档组.csv',group_links);write_csv(out/'追溯/固定处置应用.csv',fixed_log)
    write_csv(out/'追溯/空正文清单.csv',[r for r in docrows if r['normalization_empty']],list(docrows[0]))
    policies=defaultdict(list)
    for r in rows:policies[r['policy_id']].append(r)
    families=[];versions=[];relations=[]
    for pid,rs in sorted(policies.items()):
        families.append(dict(policy_id=pid,countries=rs[0]['countries'],policy_name=rs[0]['policy_name'],identity_status=rs[0]['identity_status'],event_record_ids=[r['event_record_id'] for r in rs],source_documents=len({s['file_id'] for r in rs for s in r['sources']})))
        for r in rs:versions.append({k:r.get(k,'') for k in ['policy_id','event_record_id','version_id','version_label','policy_state','decision_date','implementation_date','target_years','identity_status']})
        for a,b in zip(rs,rs[1:]):
            rel='同政策家族不同状态，保留关联' if a['policy_state']!=b['policy_state'] else '同政策家族补充条款或重复表述候选，保留原文'
            if a['version_label'] and b['version_label'] and a['version_label']!=b['version_label']:rel='同政策家族不同原文版本线索'
            relations.append(dict(policy_id=pid,from_record=a['event_record_id'],to_record=b['event_record_id'],relation=rel,chronological_order_confirmed=False,independently_verified=False))
    write_csv(out/'政策归并与版本/身份登记.csv',families);write_csv(out/'政策归并与版本/版本记录.csv',versions);write_csv(out/'政策归并与版本/关联关系.csv',relations)
    write_csv(out/'政策归并与版本/共同政策参与关系.csv',[dict(event_record_id=r['event_record_id'],policy_id=r['policy_id'],participant=c,g20_browser_reference=c in r['countries']) for r in rows for c in r['joint_participants']])
    from ..政策归并与导出.policy_registry import export_registry
    registry=export_registry(out,rows)
    return dict(raw_documents=len(docs),source_units=len(units),ledger_records=len(events),retained_event_occurrences=sum(e['route'].startswith('main_') for e in events),exact_event_records=len(rows),
                layers=dict(Counter(r['data_layer'] for r in rows)),routes=dict(Counter(e['route'] for e in events)),empty_normalized_documents=sum(not d['analysis_text'].strip() for d in docs),
                policy_identity_groups=len(families),named_policy_family_groups=sum(bool(r['policy_name']) for r in families),independent_policy_count=None,fixed_dispositions_applied=len(fixed_log),original_files_deleted=0,registry=registry)

def verify_results(out,docs,events):
    by={d['file_id']:d for d in docs};ids=set();errors=[];intervals=defaultdict(list);evidence_count=0
    for e in events:
        if e['event_id'] in ids:errors.append('重复事件ID '+e['event_id'])
        ids.add(e['event_id'])
        for p in e.get('text_parts') or [e]:
            if by[e['file_id']]['analysis_text'][p['start']:p['end']]!=p['text']:errors.append('事件原文错位 '+e['event_id'])
            intervals[e['file_id']].append((p['start'],p['end']))
        for v in e['evidence']:
            if v['file_id'] not in by:continue
            if 'start' in v and 'end' in v:
                evidence_count+=1
                if by[v['file_id']]['analysis_text'][v['start']:v['end']]!=v['text']:errors.append('证据错位 '+e['event_id'])
        if e['route'].startswith('main_') and (not e['countries'] or e['policy_level'] not in {'national','local_execution'}):errors.append('保留缺国家或层级 '+e['event_id'])
    for d in docs:
        end=0
        for a,b in sorted(intervals[d['file_id']]):
            if a>end:errors.append('规范正文覆盖缺口 '+d['file_id']+':'+str(end))
            end=max(end,b)
        if end<len(d['analysis_text']):errors.append('规范正文尾部缺口 '+d['file_id'])
    csv_count=0;row_count=0
    for p in out.rglob('*.csv'):
        with p.open(encoding='utf-8-sig',newline='') as f:
            r=csv.DictReader(f);n=sum(1 for x in r);csv_count+=1;row_count+=n
    rows=read_jsonl(out/'全部事件记录.jsonl');record_ids={r['event_record_id'] for r in rows}
    if len(record_ids)!=len(rows):errors.append('去重事件ID重复')
    source_ids=[i for r in rows for i in r['event_ids']]
    if len(source_ids)!=len(set(source_ids)):errors.append('一个事件出现被重复归并')
    if set(source_ids)!={e['event_id'] for e in events if e['route'].startswith('main_')}:errors.append('事件出现与去重记录无法对账')
    for folder,layer in [('主分析集','主分析候选'),('扩展集','扩展候选')]:
        for c in sorted(G20):
            with (out/f'{folder}/按国家/{c}.csv').open(encoding='utf-8-sig',newline='') as f:actual={r['event_record_id'] for r in csv.DictReader(f)}
            if actual!={r['event_record_id'] for r in rows if r['data_layer']==layer and c in r['countries']}:errors.append('国家文件不一致 '+folder+'/'+c)
    with (out/'国家数据统计.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            selected=[x for x in rows if r['country'] in x['countries']]
            if int(r['exact_event_records'])!=len(selected):errors.append('国家统计不一致 '+r['country'])
    result=dict(passed=not errors,errors=errors,unique_event_ids=len(ids),unique_event_record_ids=len(record_ids),country_files_checked=2*len(G20),evidence_spans_checked=evidence_count,csv_files_read=csv_count,csv_rows_read=row_count,coverage='全部规范正文必须被处置记录覆盖；重复区间仅允许并列政策和固定多部分事实',semantic_acceptance=False)
    if errors:write_json(out/'核验/失败记录.json',result);raise AssertionError(str(errors[:8]))
    return result
