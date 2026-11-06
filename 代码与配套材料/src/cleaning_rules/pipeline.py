"""CM-PACE 原始 ZIP 完整入口；不读取历史清洗结果或评价标签。"""
import copy,json,re,time,platform
from collections import Counter,defaultdict
from pathlib import Path
from .读取与规范化.ingest import load_archive
from .读取与规范化.cleaning import clean_document
from .读取与规范化.template_cleaning import _refinement_clean
from .读取与规范化.text_normalization import to_simplified
from .主体与国家归属.entities import EntityMentions
from .政策内容判定.semantic_scope import ReleaseScope71
from .事实修补与补漏.content_repair import RepairEngine
from .事实修补与补漏.recall_rules import RecallEngine
from .事实修补与补漏.fact_correction import Corrector
from .事实修补与补漏.fact_revision import RevisionEngine
from .事实修补与补漏.coverage_repair import CoverageRepair
from .事实修补与补漏.focused_review import FocusedReview
from .主体与国家归属.national_scope import G20,competition_scores
from .上下文与证据连接.evidence_scope import grade
from .公共工具.identifiers import ident
from .公共工具.io_utils import sha256,read_jsonl,write_json,write_jsonl,write_csv,manifest

def retained(e):return e.get('route','').startswith('main_')

def structural_risk(text):
    """仍混有导航/机器时间/摘要元数据的候选整体隔离，不猜正文截断点。"""
    if re.search(r'(?:首页|网站首页)\|(?:[^。]{0,20}\|){3,}',text):return '事实仍混有网站导航，未作为纯政策文本交付'
    if re.search(r'(?:\|{2,}|时间[：:]).{0,100}摘要[：:]|(?:19|20)\d\d[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}:\d{2}',text[:180]):return '标题/网页时间/摘要与正文黏连，先隔离而不猜测事实边界'
    return ''

def source_units(doc,decisions):
    """按原文句界切分，固定处置覆盖部分从自动分析中扣除；全部文字仍保留。"""
    text=doc['analysis_text'];covered=[]
    for e in decisions:
        parts=e.get('text_parts') or [e]
        for p in parts:
            a,b=p['start'],p['end']
            if text[a:b]!=p['text']:raise ValueError('固定处置原文不一致 '+e['event_id'])
            covered.append((a,b))
    cuts={0,len(text)}
    for m in re.finditer(r'[。！？\n][”’」』]*',text):cuts.add(m.end())
    title=doc.get('analysis_title','').strip()
    if title and text.startswith(title):cuts.add(len(title))
    noise_spans=[]
    for m in re.finditer(r'【[^】]{0,100}(?:关注|订阅|扫码|点击)[^】]{0,50}】|(?:转自|来源)[：:][^。\n]{1,25}?(?=周[一二三四五六日天]|据|近日|日前|(?:19|20)\d\d)',text):
        cuts.update((m.start(),m.end()));noise_spans.append((m.start(),m.end()))
    for a,b in covered:cuts.update((a,b))
    ps=sorted(cuts);out=[]
    for a,b in zip(ps,ps[1:]):
        if any(x<=a and b<=y for x,y in covered):continue
        out.append(dict(unit_id=ident('U-',(doc['file_id'],a,b)),file_id=doc['file_id'],start=a,end=b,text=text[a:b],
                        source_country=doc['source_country'],source_url=doc['url'],title=doc['title'],published_at=doc['published_at'],
                        template_noise=any(x<=a and b<=y for x,y in noise_spans)))
    return out

def apply_correction(e,d,full):
    """把动作状态修补结果转为原文字面切片，余文归档。"""
    if not d:return [e]
    a,b=e['start'],e['end'];out=[]
    if d['kind']=='exclude':
        z=copy.deepcopy(e);z.update(route=d['route'],reason=d['reason'],policy_state=d['policy_state'],countries=[])
        z['event_id']=ident('C-',(e['event_id'],d['route']));return [z]
    x,y=d['start'],d['end']
    for u,v,route in [(a,x,d.get('remainder_route','commentary')),(x,y,'main_explicit'),(y,b,d.get('remainder_route','commentary'))]:
        if u==v:continue
        z=copy.deepcopy(e);z.update(event_id=ident('C-',(e['event_id'],u,v,route)),start=u,end=v,text=full[u:v],route=route,reason=d['reason'])
        if route=='main_explicit':
            z.update(countries=d['countries'],policy_state=d['policy_state'],policy_level='national',delivery_layer='扩展候选',newly_recovered=True,
                     country_basis=d['evidence_grade'],evidence=d['evidence'],connection_path=[{'from_text':d['text'],'to_text':v['text'],'relation':d['reason']} for v in d['evidence'][1:]])
        else:z.update(countries=[],policy_state='',delivery_layer='隔离归档')
        out.append(z)
    assert ''.join(z['text'] for z in out)==e['text']
    return out

def complete_fields(e,doc,scope):
    """重新计算当前事实的四维证据和竞争分；未校准，不用综合分覆盖硬条件。"""
    e.setdefault('roles',{'actors':[],'actions':[],'measures':[],'targets':[]})
    e.setdefault('evidence',[]);e.setdefault('connection_path',[]);e.setdefault('countries',[])
    e.setdefault('policy_names',[]);e.setdefault('policy_state','unknown');e.setdefault('policy_level','unknown')
    risk=structural_risk(e['text'])
    if retained(e) and risk:e.update(route='quality_unknown',reason=risk,structural_quality_risk=risk)
    e.update(source_url=doc['url'],reported_at=doc['published_at'],source_country=doc['source_country'],title=doc['title'])
    if any(p['start']<=e['start']<p['end'] for p in doc.get('related_policy_excerpt_ranges',[])):
        e.update(reported_at='',source_excerpt_kind='related_news_excerpt',newly_recovered=True,
                 source_excerpt_note='页脚后的完整关联新闻政策摘录；原页面标题、国家文件夹及报道日期不属于该摘录，日期留空，单列扩展候选')
    e['countries']=sorted(set(e['countries'])&G20)
    if retained(e) and not e['countries']:e.update(route='subject_unknown',reason='政策性质候选但无可解释G20归属',delivery_layer='隔离归档')
    for v in e['evidence']:v.setdefault('file_id',e['file_id'])
    if not e['evidence']:
        e['evidence']=[dict(file_id=e['file_id'],start=p['start'],end=p['end'],text=p['text'],role='字面原文') for p in e.get('text_parts') or [e]]
    g=grade(e);e['evidence_grade']=g
    fixed=e.get('decision_origin')=='fixed_review_input'
    if not retained(e):e['delivery_layer']='隔离归档'
    elif fixed or e.get('newly_recovered') or e['route']=='main_source_inferred':e['delivery_layer']='扩展候选'
    else:e['delivery_layer']='主分析候选' if g['tier']=='A' else '扩展候选'
    e['evidence_dimensions']={k:{'score':g['dimensions'].get(k),'reason':str(e.get({'content':'reason','country':'country_basis','level':'policy_level','state':'policy_state'}[k],''))} for k in ['content','country','level','state']}
    ms=scope.mentions(e['text'],e['start']);actors=e['roles'].get('actors',[])
    legacy=competition_scores(e['text'],e['start'],ms,actors,doc['source_country'],bool(e['connection_path']))
    if e.get('optimized_attribution'):
        e['legacy_s_scores']=legacy;e['s_scores']=e['optimized_attribution']['scores']
        e['s_formula_version']=e['optimized_attribution']['version']
    else:e['s_scores']=legacy
    e['score_is_probability']=False;e['independent_human']=False
    e.setdefault('annotation_origin','历史辅助建议、用户整体确认，非独立标注' if fixed else '程序自动处理')
    return e

def build_components(root,config):
    """原内容scope冻结在增强别名之前；新归属类没有assess接口，不能传进补漏。"""
    root=Path(root);aliases=json.loads((root/config['entity_aliases']).read_text('utf8'))
    from .主体与国家归属 import national_scope
    national_scope.WEIGHTS=dict(config['country_weights'])
    authority=json.loads((root/config['authority_aliases']).read_text('utf8'))
    national_scope.AUTHORITIES=copy.deepcopy(authority['national']);national_scope.REGIONS=authority['local']
    raw=EntityMentions(aliases).mentions;scope=ReleaseScope71(raw)
    repair=RepairEngine(scope);recall=RecallEngine(scope)
    components=dict(scope=scope,repair=repair,recall=recall,correct=Corrector(),revision=RevisionEngine(),coverage=CoverageRepair(),focused=FocusedReview(),boundary=None)
    optimization=config.get('attribution_optimization',{})
    if optimization.get('enabled'):
        from .主体与国家归属.scoped_roles import ScopedAttribution
        from .政策内容判定.policy_boundary import PolicyBoundary
        extras=json.loads((root/optimization['authority_supplement']).read_text('utf8'))
        for c,values in extras.items():national_scope.AUTHORITIES.setdefault(c,[]).extend(n for n in values if n not in national_scope.AUTHORITIES[c])
        roles=ScopedAttribution(raw,optimization)
        components['boundary']=PolicyBoundary(scope,roles)
        from .事实修补与补漏.final_fact_refiner import FinalFactRefiner
        components['final_refiner']=FinalFactRefiner(roles,config.get('final_fact_refiner',{}))
        if config.get('policy_lifecycle_checks'):
            components['final_refiner'].lifecycle_checks=json.loads((root/config['policy_lifecycle_checks']).read_text('utf8'))
        if config.get('source_quality_reviews'):
            components['final_refiner'].quality_reviews=json.loads((root/config['source_quality_reviews']).read_text('utf8'))
    return components

def process_record(record,full,doc,components,doc_records=None):
    """开发对照和正式入口共用此函数，保证两者的实际处理链一致。"""
    scope=components['scope'];boundary=components['boundary'];out=[]
    if record.get('template_noise'):
        return [complete_fields(dict(record,event_id=record['unit_id'],route='noise',reason='有界网页关注/转载引导语单独归档'),doc,scope)]
    for e in scope.assess(record,full,doc,doc_records or [record]):
        e=complete_fields(e,doc,scope)
        for v in components['repair'].revise(e,full,doc):
            recovered=None if retained(v) else components['recall'].recover(v,full,doc);expanded=[v]
            if recovered:
                a,b=v['start'],v['end'];x,y=recovered['start'],recovered['end'];expanded=[]
                for u,w in [(a,x),(y,b)]:
                    if u<w:expanded.append(dict(v,event_id=ident('REM-',(v['event_id'],u,w)),start=u,end=w,text=full[u:w]))
                expanded.append(recovered)
            for z in expanded:
                for q in apply_correction(z,components['correct'].decide(z,full,doc),full):
                    for f in components['revision'].revise(q,full,doc):
                        for c in components['coverage'].revise(f,full,doc):
                            for reviewed in components['focused'].revise(c,full,doc):
                                for final in boundary.apply(reviewed,full,doc) if boundary else [reviewed]:out.append(complete_fields(final,doc,scope))
    if boundary:
        unique={}
        for e in out:
            parts=tuple((p['start'],p['end'],p['text']) for p in e.get('text_parts') or [])
            key=(e['start'],e['end'],e['route'],tuple(e['countries']),e['policy_state'],parts)
            # 同一共同事件被旧层拆成并列记录时合回一条；不同状态/事实不合并。
            if e.get('event_type')=='joint_policy':unique[key]=e
            else:unique[(key,e['event_id'])]=e
        out=list(unique.values())
    if components.get('final_refiner'):
        out=[complete_fields(e,doc,scope) for e in components['final_refiner'].refine(out,record,full,doc)]
    return out

def run_pipeline(archive,out,config_path,limit=None,document_ids=None,reuse_result=None):
    begin=time.monotonic();archive=Path(archive).resolve();out=Path(out).resolve();config_path=Path(config_path).resolve();root=config_path.parent
    config=json.loads(config_path.read_text('utf8'))
    if out.exists():raise FileExistsError('输出目录已存在，拒绝覆盖：'+str(out))
    if not archive.is_file():raise FileNotFoundError(archive)
    input_hash=sha256(archive)
    if config.get('strict_input_hash') and input_hash!=config.get('raw_input_expected_sha256'):raise ValueError('原始输入哈希不匹配')
    cached=None;reuse_note=None
    if reuse_result:
        from .公共工具.reuse_guard import load_verified
        cached,reuse_note=load_verified(root,reuse_result,config,input_hash)
    out.mkdir(parents=True);logs=[]
    def log(stage,**counts):
        row=dict(stage=stage,elapsed_seconds=round(time.monotonic()-begin,3));row.update(counts);logs.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True);write_json(out/'核验/运行日志.json',logs)
    docs,metadata,issues=load_archive(archive);log('读取原始ZIP',documents=len(docs),metadata=len(metadata),exceptions=len(issues))
    if document_ids is not None:
        wanted=set(document_ids);docs=[d for d in docs if d['file_id'] in wanted]
        if {d['file_id'] for d in docs}!=wanted:raise ValueError('开发文档ID有未匹配项')
        log('仅开发文档子集_非全量',selected_documents=len(docs))
    if limit:docs=docs[:limit]
    components=build_components(root,config);scope=components['scope'];focused=components['focused'];boundary=components['boundary']
    fixed=defaultdict(list)
    for e in read_jsonl(root/config['fixed_dispositions']):fixed[e['file_id']].append(e)
    events=[];units=[];cleaning_log=[];fixed_log=[]
    for i,doc in enumerate(docs):
        if boundary:boundary.role_scope.clear_document_cache()
        c=_refinement_clean(clean_document(doc['raw_text'],doc['title']));doc.update(c)
        doc['analysis_text']=to_simplified(doc['clean_text']);doc['analysis_title']=to_simplified(doc['title'])
        doc['related_policy_excerpt_ranges']=[]
        for entry in c['removal_log']:
            if entry.get('restored_text'):
                quote=to_simplified(re.sub(r'[^\S\n]+',' ',entry['restored_text']))
                start=doc['analysis_text'].find(quote)
                if start>=0:doc['related_policy_excerpt_ranges'].append(dict(start=start,end=start+len(quote),text=quote))
        doc['raw_sha256']=__import__('hashlib').sha256(doc['raw_text'].encode('utf8')).hexdigest()
        doc['analysis_sha256']=__import__('hashlib').sha256(doc['analysis_text'].encode('utf8')).hexdigest()
        cleaning_log.extend(dict(file_id=doc['file_id'],**x) for x in c['removal_log'])
        fs=copy.deepcopy(fixed[doc['file_id']]);rs=source_units(doc,fs);units+=rs;full=doc['analysis_text']
        if cached is None:
            for r in rs:events.extend(process_record(r,full,doc,components,rs))
        else:
            cached_text=(Path(reuse_result)/'追溯/规范正文'/doc['file_id']).read_text('utf8')
            if full!=cached_text:raise ValueError('复用正文不一致：'+doc['file_id'])
            events.extend(copy.deepcopy(cached[doc['file_id']]))
        for f in fs:
            for reviewed in focused.revise(f,full,doc):
                if cached is None:events.append(complete_fields(reviewed,doc,scope))
            fixed_log.append({k:f.get(k) for k in ['event_id','file_id','review_no','text','route','reason','annotation_origin']})
        if (i+1)%100==0:log('政策识别',processed_documents=i+1,events=len(events),retained=sum(map(retained,events)))
    from .事实修补与补漏.terminal_scope import apply as terminal_scope
    events,terminal_changes=terminal_scope(events,{d['file_id']:d['analysis_text'] for d in docs})
    write_csv(out/'核验/末端边界变更.csv',terminal_changes)
    if reuse_note:write_json(out/'核验/前序复用核验.json',reuse_note)
    # Stable IDs include the outcome and original intervals; same-span parallel countries remain distinct.
    for e in events:e['event_id']=ident('EV-',(e['file_id'],e.get('text_parts') or [dict(start=e['start'],end=e['end'])],e['route'],e['countries'],e['policy_state']))
    unique={}
    for e in events:
        if e['event_id'] in unique and e['text']!=unique[e['event_id']]['text']:raise ValueError('事件ID碰撞')
        unique[e['event_id']]=e
    events=list(unique.values());log('最终分流',events=len(events),retained=sum(map(retained,events)))
    from .政策归并与导出.exports import export_results,verify_results
    summary=export_results(out,docs,events,units,metadata,issues,cleaning_log,fixed_log,config)
    from .上下文与证据连接.linked_policy_resolution import export_resolution_evidence
    summary['linked_resolution']=export_resolution_evidence(out,events)
    summary.update(version=config['version'],source_algorithm=config['source_algorithm'],input_sha256=input_hash,python=platform.python_version(),elapsed_seconds=round(time.monotonic()-begin,2),independent_acceptance_completed=False)
    summary.update(terminal_scope_changes=len(terminal_changes),recognition_reused=bool(reuse_result))
    write_json(out/'运行摘要.json',summary);write_json(out/'核验/参数.json',config)
    verification=verify_results(out,docs,events);write_json(out/'核验/运行核验.json',verification)
    write_json(out/'核验/输入标识.json',{'archive_name':archive.name,'sha256':input_hash,'resources':{p.relative_to(root).as_posix():sha256(p) for p in (root/'resources').rglob('*') if p.is_file()},'config_sha256':sha256(config_path)})
    log('完成',**summary);write_json(out/'结果冻结清单.json',manifest(out,{'结果冻结清单.json'}))
    return summary
