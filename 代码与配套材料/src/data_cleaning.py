"""第一部分：从原始ZIP清洗，再应用显式、可追溯的固定处置。"""
from pathlib import Path
import json,shutil
from collections import Counter
from .common import *
from .cleaning_rules.pipeline import run_pipeline
from .text_features import build_documents

def run(out,reuse=False):
    out=Path(out);auto=out/'01_数据清洗/自动分流'
    cfg=read_json(ROOT/'config.json')
    summary=run_pipeline(ROOT/cfg['raw'],auto,ROOT/'resources/cleaning/config.json',reuse_result=ROOT/'resources/识别检查点' if reuse else None)
    rows=read_events(auto/'全部事件记录.jsonl');lookup={e['event_record_id']:e for e in rows}
    ledger=read_json(ROOT/'resources/cleaning/分析处置.json')
    assert len(rows)==ledger['input_count'],('基础规则数量变化',len(rows),ledger['input_count'])
    archive=[]
    for decision in ledger['remove']:
        key=decision['event_record_id'];old=lookup[key]
        assert canonical(old)==decision['before_sha256'],('处置前记录变化',key)
        archive.append(dict(decision=decision,record=old));del lookup[key]
    for decision in ledger['upsert']:
        key=decision['event_record_id']
        if decision['before_sha256'] is not None:
            assert canonical(lookup[key])==decision['before_sha256'],('属性修订前记录变化',key)
        lookup[key]=decision['record']
    final=[lookup[k] for k in ledger['final_order']]
    assert len(final)==ledger['expected_count'] and len(lookup)==len(final)
    assert canonical(final)==ledger['expected_canonical_sha256']
    index={r['file_id']:r for r in read_csv(auto/'追溯/来源索引.csv')}
    texts={f:(auto/r['normalized_text_file']).read_text(encoding='utf-8-sig') for f,r in index.items()}
    docs,links,errors=build_documents(final,texts,index)
    assert not errors,errors[:3]
    target=out/'01_数据清洗/最终分析输入';target.mkdir(parents=True)
    (target/'全部事件记录.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in final),encoding='utf-8')
    (target/'追溯').mkdir()
    shutil.copy2(auto/'追溯/来源索引.csv',target/'追溯/来源索引.csv')
    shutil.copytree(auto/'追溯/规范正文',target/'追溯/规范正文')
    write_json(out/'01_数据清洗/后续隔离证据.json',archive)
    simple=[dict(event_record_id=e['event_record_id'],policy_id=e['policy_id'],version_id=e.get('version_id',''),
                 identity_status=e.get('identity_status',''),version_verification_status=e.get('version_verification_status',''),
                 countries=e['countries'],joint_participants=e.get('joint_participants',[]),source_inference_only=e.get('source_inference_only',False),
                 institutions=e['institutions'],policy_fact=e['policy_fact'],policy_level=e['policy_level'],
                 policy_state=e['policy_state'],data_layer=e['data_layer'],decision_date=e.get('decision_date',''),
                 implementation_date=e.get('implementation_date',''),report_dates=e.get('report_dates',[]),
                 target_years=e.get('target_years',[]),date_evidence=e.get('date_evidence',[]),date_warnings=e.get('date_warnings',[]),
                 sources=e['sources'],reasons=e.get('reasons',[]),evidence_dimensions=e.get('evidence_dimensions',[]),
                 connection_path=e.get('connection_path',[]),annotation_origins=e.get('annotation_origins',[])) for e in final]
    for view in ['main','extended','main_extended']:
        subset=[r for r in simple if view=='main_extended' or r['data_layer']==('主分析候选' if view=='main' else '扩展候选')]
        for country in cfg['country_universe']:
            write_csv(out/f'01_数据清洗/按国家/{view}/{country}.csv',[r for r in subset if country in r['countries']],list(simple[0]))
    for name,subset in [('主分析候选',[r for r in simple if r['data_layer']=='主分析候选']),
                        ('扩展候选',[r for r in simple if r['data_layer']=='扩展候选']),
                        ('来源推定单列',[r for r in simple if r['source_inference_only']])]:
        write_csv(out/f'01_数据清洗/{name}.csv',subset,list(simple[0]))
    stats=[]
    for country in cfg['country_universe']:
        es=[e for e in final if country in e['countries']]
        stats.append(dict(country=country,main_events=sum(e['data_layer']=='主分析候选' for e in es),
            extended_events=sum(e['data_layer']=='扩展候选' for e in es),total_event_records=len(es),
            distinct_source_documents=len({s['file_id'] for e in es for s in e['sources']}),
            source_inferred_records=sum(bool(e.get('source_inference_only')) for e in es),
            independent_policy_count='',note='共同事件可被多国引用；分国行数不能相加当成全局独立事件数'))
    write_csv(out/'01_数据清洗/最终国家统计.csv',stats)
    write_csv(out/'01_数据清洗/事件表.csv',simple)
    write_csv(out/'01_数据清洗/原文映射核验.csv',links)
    summary=dict(raw_documents=summary['raw_documents'],source_units=summary['source_units'],
        automatic_retained_occurrences=summary['retained_event_occurrences'],automatic_exact_events=len(rows),
        final_event_records=len(final),layers=dict(Counter(e['data_layer'] for e in final)),
        fixed_removed=len(ledger['remove']),fixed_added_or_revised=len(ledger['upsert']),
        independent_policy_count=None,independent_semantic_acceptance=False,raw_recomputed=True,full_recognition_rerun=not reuse,
        final_events_canonical_sha256=canonical(final))
    write_json(out/'01_数据清洗/阶段摘要.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    return target
