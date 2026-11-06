"""Literal terminal boundaries; retain attribution/state and archive removed text."""
import copy
import re
from ..公共工具.identifiers import ident
from ..主体与国家归属.national_scope import evidence

COUNTRIES = '美国|德国|日本|韩国|中国|法国|英国|印度|沙特|印尼|加拿大|俄罗斯|澳大利亚|意大利|巴西|墨西哥|南非|土耳其|阿根廷|欧盟'


def ranges(text):
    if re.search(r'如果|除非|若|尚未|未曾|并未|没有|拟',text):return None
    if '经济引擎随着' in text:
        m=re.search(r'(?:'+COUNTRIES+r')计划在20\d{2}年之前实现碳中和(?:计划)?',text)
        if m:return [(m.start(),m.end())], 'goal_without_assessment_heading'
    if re.search(r'口诛笔伐|市场担忧',text):
        m=re.search(r'(?:(?:今年|去年)\d{1,2}月)?(?:'+COUNTRIES+r')(?:总统|政府)[^，。]{0,15}宣布[^，。]{0,18}将退出《[^》]+》',text)
        if m:return [(m.start(),m.end())], 'withdrawal_without_market_reaction'
    m=re.search(r'[，,]但目前连该目标的[^。]{0,25}都未完成',text)
    if m and re.search(r'原计划[^。]{0,70}(?:减少|降低)\d+(?:\.\d+)?%',text[:m.start()]):
        return [(0,m.start())], 'goal_without_performance_statistics'
    if re.search(r'创造多达[^。]{0,20}工作机会',text):
        m=re.search(r'并实现\s*(20\d{2}\s*年将[^。]{0,85}的目标)',text)
        if m:
            parts=[]
            capacity=re.match(r'容量\s*\d+(?:\.\d+)?\s*(?:GW|MW|吉瓦|兆瓦)',text)
            if capacity:parts.append((0,capacity.end()))
            parts.append((m.start(1),m.end(1)))
            return parts, 'capacity_and_goal_without_jobs_prediction'
    if re.search(r'不得民心|不愿意掏钱',text):
        m=re.search(r'增加电费来补贴可再生能源的政策',text)
        if m:return [(m.start(),m.end())], 'levy_mechanism_without_public_opinion'
    return None


def apply(events, documents):
    result=[];changes=[]
    for old in events:
        if not old['route'].startswith('main_') or old.get('text_parts') or old.get('decision_origin')=='fixed_review_input':
            result.append(old);continue
        found=ranges(old['text'])
        if not found:
            result.append(old);continue
        local,rule=found;full=documents[old['file_id']];origin=old['start']
        spans=[(origin+a,origin+b) for a,b in local]
        assert all(old['start']<=a<b<=old['end'] for a,b in spans)
        parts=[dict(start=a,end=b,text=full[a:b]) for a,b in spans]
        fact=copy.deepcopy(old)
        fact.update(start=spans[0][0],end=spans[-1][1],text=' … '.join(p['text'] for p in parts),
                    text_parts=parts if len(parts)>1 else [],terminal_scope_rule=rule,
                    terminal_scope_version='6.18',previous_event_ids=[old['event_id']],
                    reason=old['reason']+'；末端只收窄文字边界：'+rule)
        # Keep countries, delivery layer, dates, conditions and action state.
        fact['evidence']=old['evidence']+[dict(file_id=old['file_id'],**evidence(full,a,b,'末端保留的政策原文')) for a,b in spans]
        result.append(fact)
        cur=old['start'];removed=[]
        for a,b in spans+[(old['end'],old['end'])]:
            if cur<a:
                z=copy.deepcopy(old)
                z.update(start=cur,end=a,text=full[cur:a],text_parts=[],route='background' if rule=='goal_without_performance_statistics' else 'commentary',
                         countries=[],policy_level='unknown',policy_state='',delivery_layer='隔离归档',joint_participants=[],connection_path=[],
                         roles=dict(actors=[],actions=[],targets=[],measures=[]),evidence=[dict(file_id=old['file_id'],**evidence(full,cur,a,'剥离的统计、预测或评价'))],
                         terminal_scope_rule=rule,terminal_scope_version='6.18',reason='政策事实之外的统计、预测或评价单独归档：'+rule,
                         previous_event_ids=[old['event_id']])
                result.append(z);removed.append(z['text'])
            cur=b
        changes.append(dict(old_event_id=old['event_id'],file_id=old['file_id'],old_text=old['text'],new_text=fact['text'],rule=rule,
                            removed=removed,countries_unchanged=fact['countries']==old['countries'],state_unchanged=fact['policy_state']==old['policy_state'],layer_unchanged=fact['delivery_layer']==old['delivery_layer']))
    return result,changes
