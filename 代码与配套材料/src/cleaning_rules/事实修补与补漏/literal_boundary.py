"""Final literal-only removal of recommendation blocks, assessments and repeated headers.

This stage never creates a country assignment, replaces facts, or reads evaluation labels.
"""
import copy,re
from difflib import SequenceMatcher
from ..公共工具.identifiers import ident
from ..政策内容判定.assertion_revision import COUNTRY,keep


def owner(event):
    links=[]
    for e in event.get('evidence',[]):
        if e.get('role')=='同政策发布与主体连接':links.append({k:e[k] for k in ['start','end','text']})
    return dict(countries=event['countries'],actors=event.get('roles',{}).get('actors',[]),connection=links,
                basis=event.get('country_basis','')+'；末端仅收窄文字边界',
                kind='joint' if event.get('event_type')=='joint_policy' else 'linked' if links else 'explicit')


def emit(ref,record,events,full,parts,base,rule,reason,archive='commentary'):
    result=ref.emit(record,events,full,[dict(parts=parts,owner=owner(base),state=base['policy_state'],rule=rule,reason=reason)],archive_route=archive)
    if result:
        for e in result:e['literal_boundary_version']='literal-boundary-6.17'
    return result


def refine(events,record,full,ref):
    if any(e.get('decision_origin')=='fixed_review_input' for e in events):return events
    kept=[e for e in events if keep(e)]
    if not kept:return events
    a,b=record['start'],record['end'];t=full[a:b]
    marker=t.find('相关推荐')
    if marker>=0:
        head=t[:marker]
        starts=list(re.finditer(r'(?:'+COUNTRY+r')(?:拜登|特朗普|奥巴马)?政府(?=宣布)',head))
        if starts:
            start=a+starts[-1].start();end=a+marker
            selected=next((e for e in kept if e['start']<=start<e['end']),None)
            if selected and re.search(r'碳|风能|风电|太阳能|能源|减排',full[start:end]):
                result=emit(ref,record,events,full,[(start,end)],selected,'recommendations_after_policy_header','保留推荐区前完整政策标题的一次出现；推荐文章和金融行情归噪声','noise')
                if result:return result
    clauses=list(re.finditer(r'([^；;。]{18,100})[；;]',t))
    repeated=[m[1] for m in clauses if t.count(m[1])>=2]
    body=re.search(r'据[^。；;]{1,20}报道[，,][^。]+',t)
    if body and repeated and re.search(r'政府|白宫|国务院',body[0]) and re.search(r'宣布|发布|恢复',body[0]):
        # Only remove repeated headers when the dated body contains their long
        # literal policy core; no cross-document or approximate policy merging.
        if any(SequenceMatcher(None,q,body[0],autojunk=False).find_longest_match().size>=16 for q in repeated):
            base=next((e for e in kept if e['start']<=a+body.start()<e['end']),kept[-1])
            result=emit(ref,record,events,full,[(a+body.start(),a+body.end())],base,'duplicate_headers_before_full_announcement','重复标题归档，仅保留含来源和报道时间的完整政策声明一次','noise')
            if result:return result
    out=[]
    for e in events:
        if not keep(e) or e.get('text_parts'):
            out.append(e);continue
        x,y=e['start'],e['end'];q=full[x:y];parts=None;rule='';reason=''
        if re.search(r'(?:该|这一)成本将影响[^。]{0,65}政策制定',q) and re.search(r'抬升|优势|影响',q):
            z=copy.deepcopy(e);z.update(route='commentary',countries=[],policy_state='',policy_level='unknown',delivery_layer='隔离归档',event_id=ident('LB17-',(e['event_id'],'commentary')),reason='成本对政策制定及产业优势的影响预测，不是已采纳措施',literal_boundary_version='literal-boundary-6.17');out.append(z);continue
        m=re.search(r'[，,]被看作是[^。]{0,30}行政障碍来自([^，。]+)[，,](该局要[^。]+)',q)
        if m:
            parts=[(x,x+m.start()),(x+m.start(1),x+m.end(1)),(x+m.start(2),x+m.end(2))]
            rule='review_and_permit_without_assessment';reason='审查动作、负责机构和许可义务保留，最有挑战的行政障碍评价另存'
        if re.search(r'煤炭产量[^。]{0,30}达到顶峰',q):
            m=re.search(r'(?:19|20)\d{2}年[，,][^，。]{0,18}政府暂停[^。]+',q)
            if m:parts=[(x+m.start(),x+m.end())];rule='dated_suspension_without_statistics';reason='保留有日期的政府暂停动作，前部产量统计和概述归档'
        m=re.search(r'((?:'+COUNTRY+r')将对[^，。]{3,45}征收\d+(?:\.\d+)?%)',q)
        if m and re.search(r'商会|协会',q[:m.start()]) and re.search(r'生产商将无法|企业将无法',q[m.end():]):
            parts=[(x+m.start(1),x+m.end(1))];rule='tariff_fact_inside_industry_reaction';reason='保留协会转述的关税措施，企业出口后果另存，金额和未来状态不改写'
        if '签署了实施ACE的文件' in q:
            actor=re.search(r'美国环保署',q);assessment=re.search(r'[，,]并强调[^。]{0,85}[“"]高级版本[”"]',q)
            if actor and assessment:
                parts=[(x+actor.start(),x+assessment.start()),(x+assessment.end(),y)];rule='signed_rule_without_promotional_assessment';reason='保留签署与州权限、燃煤厂条件，去除倒退及高级版本评价'
        if parts:
            child=dict(record,start=x,end=y,text=q)
            result=emit(ref,child,[e],full,parts,e,rule,reason)
            out.extend(result or [e])
        else:out.append(e)
    return out
