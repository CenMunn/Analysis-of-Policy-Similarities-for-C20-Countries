"""有界的嵌套事实抽取。字面片段与补足语义的证据分开；未抽出的字符全部归档。"""
import copy,re
from ..主体与国家归属.national_scope import evidence
from ..事实修补与补漏.recall_rules import COUNTRIES

VERSION='contextual-fact-parts-6.8.1-local-goal-mapping'

def split_contextual_facts(event,full,roles):
    if event.get('text_parts') or event.get('quality_risks') or event.get('previous_quality_risks'):return None
    if event['route'] not in {'main_explicit','main_context','main_source_inferred','subject_unknown','content_uncertain','commentary','background','level_unknown'}:return None
    t=event['text'];a=event['start'];before=full[max(0,a-600):a]
    proposals=[]
    # 媒体预测与被比较的政府目标。保留主题、目标年及原文政府目标片段；中间的预测不拼入事实。
    subject=re.search('('+COUNTRIES+r')的((?:核电|可再生能源|风电|太阳能)(?:发电)?(?:比例|占比))到(20\d\d)年',t)
    forecast=re.search(r'认为|预计|预测',t)
    goal=re.search(r'([^，。；]{2,14}?政府)((?:19|20)\d\d)年(?:计划|设定|制定)的(\d+(?:\.\d+)?(?:[-—–]\d+(?:\.\d+)?)?[%％])(?:预期|目标)',t)
    if subject and forecast and goal and forecast.start()<subject.start()<subject.end()<=goal.start():
        prefix=t[:subject.start()];between=t[subject.end():goal.start()]
        actors=[m for m in roles.mentions(t,a) if m.get('public') and m.get('level')!='local' and a+goal.start()<=m['start']<m['end']<=a+goal.start(2)]
        # 作用域仅限本模块已匹配到的“政府年份计划的目标”；不修改旧引擎的全局机构表。
        for name,country in roles.params.get('contextual_goal_actors',{}).items():
            start=t.find(name,goal.start(),goal.start(2))
            if start>=0 and not actors:
                actors.append(dict(country=country,text=name,start=a+start,end=a+start+len(name),public=True,role='public_actor',level='national',basis='仅嵌套政府目标抽取的局部机构映射'))
        if actors:between=t[subject.end():actors[0]['start']-a]
        countries={m['country'] for m in actors}
        if len(countries)==1 and subject[1] in countries and re.search(r'不能达到|低于|达不到|难以达到',between) and not re.search(r'如果|假如|拟|草案|建议|尚未|未获|竞选',prefix+t[goal.start():goal.end()]):
            proposals.append(dict(parts=[(subject.start(),subject.end()),(actors[0]['start']-a,goal.end())],actors=actors,countries=sorted(countries),
                state='announced_goal',rule='forecast_vs_published_target',
                action=(goal.start(2)+len(goal[2])+1,goal.start(3)-1),
                reason='媒体预测值归评论；比较句中的国家政府原目标按字面两部分保留，省略号不是原文；不把目标表述成已实现',
                attributes=dict(policy_object=subject[2],target_year=subject[3],target_value=goal[3],plan_reference_year=goal[2]),extra=[]))
    # 明确公共发言人的本国履约承诺；不把外国要求、一般表态或竞选主张变成采纳。
    quote=re.search(r'(做出了?回应|表示|重申)[：:]?[“"]([^”"]+)[”"]',t)
    if not proposals and quote:
        speakers=[m for m in roles.mentions(t,a) if m.get('public') and m.get('level')!='local' and m['end']<=a+quote.start() and re.fullmatch(r'(?:对(?:该|这一|上述)事件)?',t[m['end']-a:quote.start()])]
        body=quote[2]
        commitment=re.search(r'(中国|美国|法国|德国|日本|韩国|英国|俄罗斯)(?:将|仍将|会|仍会)(?:认真|继续|切实|严格)?(履行|执行|遵守)《([^》]{2,30}(?:协定|协议))》',body)
        if speakers and commitment and {m['country'] for m in speakers}=={commitment[1]} and re.search(r'巴黎|气候',commitment[3]) and not re.search(r'若|如果|建议|希望|要求|敦促|尚未|不会|不能|不再',body):
            speaker=speakers[-1];s=speaker['start']-a
            vstart=quote.start(2)+commitment.start(2);vend=quote.start(2)+commitment.end(2)
            proposals.append(dict(parts=[(s,quote.end())],actors=[speaker],countries=[commitment[1]],state='announced_commitment',rule='own_country_quoted_commitment',
                action=(vstart,vend),reason='本国公共发言人作出的本国履约承诺；保留引语中的无论条件，不继承外国退出状态',attributes={},extra=[]))
            # 时间从句中的已宣布退出也是一次报道出现；须有前文同主体及条约的明确证据补足对象。
            withdrawal=re.search(r'([^，。；]{0,14}?)(公布(?:了)?退出决定)',t[:s])
            if withdrawal:
                wms=[m for m in roles.mentions(t[:s],a) if m.get('public') and m['end']==a+withdrawal.start(2)]
                if wms:
                    wm=wms[-1];prior_mentions=[m for m in roles.mentions(before,a-len(before)) if m.get('public') and m['country']==wm['country'] and wm['text'] in m['text']]
                    treaty=re.search('《'+re.escape(commitment[3])+'》',before)
                    if prior_mentions and treaty:
                        pm=prior_mentions[-1];rest=full[pm['end']:a]
                        if re.search(r'退出(?:了)?(?:该|这一|上述|《)',rest) and not re.search(r'如果|若当选|尚未|并未',rest):
                            proposals.append(dict(parts=[(wm['start']-a,withdrawal.end(2))],actors=[wm],countries=[wm['country']],state='announced_withdrawal',rule='reported_withdrawal_with_named_treaty',
                                action=(withdrawal.start(2),withdrawal.end(2)),reason='时间从句明确报告公布退出决定；同主体前文补足条约对象，按事件出现保留，不计为另一个独立政策',
                                attributes={'policy_name':commitment[3]},extra=[(pm['start'],a,'同主体前文的退出事实'),(a-len(before)+treaty.start(),a-len(before)+treaty.end(),'退出对象的条约名称')]))
    if not proposals:return None
    ranges=sorted((x,y) for p in proposals for x,y in p['parts'])
    if any(y>u for (x,y),(u,v) in zip(ranges,ranges[1:])):return None
    output=[]
    for i,p in enumerate(proposals):
        parts=[dict(start=a+x,end=a+y,text=t[x:y]) for x,y in p['parts']]
        z=copy.deepcopy(event)
        for key in ['optimized_attribution','s_scores','structured_goal','policy_content_contract','interface_trace','text_parts','joint_participants']:z.pop(key,None)
        z.update(event_id=event['event_id']+'-PARTS-'+str(i),start=parts[0]['start'],end=parts[-1]['end'],text=' … '.join(v['text'] for v in parts),
            route='main_explicit',countries=p['countries'],policy_level='national',policy_state=p['state'],newly_recovered=True,event_type='single_policy',
            reason=p['reason'],country_basis='字面国家公共主体；非来源推定',fact_extraction_rule=p['rule'],fact_attributes=p['attributes'],
            boundary_parent_span={'start':event['start'],'end':event['end']},connection_path=[],policy_names=[]) 
        if len(parts)>1:z['text_parts']=parts;z['text_display_note']='省略号为抽取展示连接符，原文以text_parts为准'
        z['evidence']=[evidence(full,v['start'],v['end'],'政策事实字面片段') for v in parts]
        for x,y,why in p['extra']:
            z['evidence'].append(evidence(full,x,y,why));z['connection_path'].append(dict(from_text=z['text'],to_text=full[x:y],relation=why,start=x,end=y))
        x,y=p['action'];z['roles']=dict(actors=p['actors'],actions=[evidence(full,a+x,a+y,'当前动作')],targets=[],measures=[dict(v) for v in parts])
        output.append(z)
    cursor=0
    for i,(x,y) in enumerate(ranges+[(len(t),len(t))]):
        if x>cursor:
            z=copy.deepcopy(event)
            z.update(event_id=event['event_id']+'-PARTS-ARCHIVE-'+str(i),start=a+cursor,end=a+x,text=t[cursor:x],route='commentary',countries=[],
                policy_state='',policy_level='unknown',reason='嵌套事实之外的预测、一般表态或连接语归档；未销毁原文',connection_path=[],
                roles=dict(actors=[],actions=[],targets=[],measures=[]),evidence=[evidence(full,a+cursor,a+x,'非事实余文')],fact_extraction_rule='nested_remainder')
            output.append(z)
        cursor=y
    return sorted(output,key=lambda e:(e['start'],e['end']))
