"""Literal, bounded facts inside commentary, rejected proposals, and corporate reactions.

The original sentence is never rewritten. Conditions and numeric clauses belong to
the extracted fact; every remaining character is archived by the caller.
"""
import re

def nested_recoveries(r,events,record,full,doc,country_pattern):
 a,b=record['start'],record['end'];t=full[a:b];old=events[0];out=[]
 def add(parts,state,rule,reason,owner=None,countries=None):
  if not parts:return
  if any(not(a<=x<y<=b) for x,y in parts):raise ValueError('嵌套事实范围越界')
  text=' … '.join(full[x:y] for x,y in parts)
  if owner is None:owner=r.ownership(full[parts[0][0]:parts[-1][1]],parts[0][0],full,old if old['route'].startswith('main_') else None)
  if owner is None and countries:owner=dict(countries=countries,actors=[],connection=[],kind='country_statement',basis='当前原文明示的国家与措施；没有使用来源文件夹覆盖')
  if owner:out.append(dict(parts=parts,state=state,rule=rule,reason=reason,owner=owner))
 # A public speaker's explicit dated target survives an introductory comparison.
 target=re.search(r'时间[，,]?(?:将)?从20\d\d年提前到20\d\d年',t)
 if target and re.search(r'表示|宣布|宣告',t) and re.search(r'净零|碳中和|碳排放',t) and not r.publication_status(t,a,full):
  pubs=[m for m in r.mentions(t,a) if m.get('public') and m.get('level')!='local' and m.get('role') not in {'target','private_or_context','location'}]
  if pubs and len({m['country'] for m in pubs})==1:
   start=min(m['start'] for m in pubs);dates=list(re.finditer(r'(?:在)?20\d\d年\d{1,2}月',t[:start-a]))
   if dates:start=a+dates[-1].start()
   owner=dict(countries=sorted({m['country'] for m in pubs}),actors=pubs,connection=[],kind='explicit',basis='本句公共领导人明确公布目标时间变化')
   add([(start,b)],'announced_goal','official_target_time_change','保留公共讲话中明确目标及前后年份，比较性引导语另存',owner=owner)
 # A causal statement can contain both an assessment and a separate court decision.
 court=re.search(r'(?:因为|由于)(?P<fact>美国(?:最高|高等|联邦)?法院(?:已经|已)?(?:暂时叫停|暂缓|叫停)[^。]+[。]?)',t)
 if court and re.search(r'挫折|打击|影响',t[:court.start()]):
  add([(a+court.start('fact'),a+court.end('fact'))],'suspended_by_court','court_fact_not_assessment','法院叫停事实单独保留，挫折与影响评价归档')
 # Restore eligibility text already separated by an older overly broad "effect" splitter.
 eligible=re.search(r'使得[^。]{0,20}有资格获得[^。]{0,60}(?:税收抵免|补贴)[。]?',t)
 if eligible:
  prefix=full[max(0,a-350):a].rsplit('。',1)[-1]
  if re.search(r'(?:众议院|国会|政府|内阁)[^。]{0,30}通过[^。]{0,60}(?:法案|法律)',prefix) and not re.search(r'尚未|未能|建议|拟',prefix):
   pubs=[m for m in r.mentions(prefix,a-len(prefix)) if m.get('public') and m.get('level')!='local'];cs={m['country'] for m in pubs}
   if len(cs)==1:
    owner=dict(countries=sorted(cs),actors=pubs,connection=[dict(start=a-len(prefix),end=a,text=prefix)],kind='linked',basis='同一句已通过法律及其税收资格条款')
    add([(a+eligible.start(),a+eligible.end())],'execution_requirement','eligibility_not_effect','税额与适用资格属于法案条款，不能按使得一词当效果预测删去',owner=owner)
 # Recover the literal amendment to an existing subsidy ceiling, not the executives' attendance.
 ceiling=re.search(r'价格超过[0-9，,.]+欧元的车辆不补贴原则被废除',t)
 if ceiling:
  owner=r.ownership(ceiling.group(),a+ceiling.start(),full,old)
  if owner and (r.anchor(t,a,full) or old['route'].startswith('main_')):add([(a+ceiling.start(),a+ceiling.end())],'announced_or_adopted','subsidy_ceiling_amendment','保留补贴上限撤销条款；车企高管出席信息不并入政策',owner=owner)
 # Keep the completed public announcement before an explicit effects forecast.
 tail=re.search(r'[，,；;](?=(?:政策有望|有望|预计|此举将|这将|分析师认为))',t)
 if tail:
  head=t[:tail.start()];rel=r.roles.relation(head,a)
  actors=[m for m in r.mentions(head,a) if m.get('public') and m.get('level')!='local']
  if actors and rel['events'] and re.search(r'宣布|公布|发布|批准|颁布|出台|签署',head) and not re.search(r'如果|若当选|竞选|建议|尚未|未曾',head):
   add([(a,a+tail.start())],r.state(head,old.get('policy_state','announced_or_adopted')),'public_announcement_before_effect','公开措施的事实与数字化效果预测分开；不因后半预测而整句漏收')
 # A time clause reports an already published public plan; the corporate reaction is separate.
 m=re.search('(?P<fact>(?:'+country_pattern+r')(?:政府|内阁)[^，。；]{0,18}(?:发布|公布)(?:了)?(?:这项|该项|一项)?[^，。；]{0,35}(?:计划|战略|规划|办法))(?=后[，,]|之后[，,])',t)
 if m and not re.search(r'如果|假如|若|拟|建议|计划于',t[:m.start()]):
  add([(a+m.start('fact'),a+m.end('fact'))],'announced_plan','published_plan_inside_reaction','时间从句明示已发布国家计划；企业关注和预测另存')
 # Completed public action survives a different rejected tax proposal in the same sentence.
 m=re.search(r'(?P<fact>(?:特朗普总统|奥巴马政府|美国政府|中国政府|日本政府|韩国政府)(?:已经|已|正式)?(?:废除了|取消了|颁布了|批准了|公布了)[^。；，]{0,70}《[^》]{2,40}》)',t)
 if m and not re.search(r'如果|假如|尚未|未曾|建议|拟',t[max(0,m.start()-12):m.start()]):
  add([(a+m.start('fact'),a+m.end('fact'))],r.state(m['fact']),'completed_action_inside_proposal','既有正式动作不被其他工具的未通过状态覆盖')
 # A definite reported withdrawal may be nested under an external evaluation.
 m=re.search('(?P<c>'+country_pattern+r')(?P<v>(?:总统)?(?:已经|已|现在|正式|宣布|决定|刚刚){1,3}退出)(?P<obj>《[^》]{0,15}(?:巴黎|气候)[^》]{0,20}(?:协定|协议)》)?',t)
 if m and not re.search(r'如果|假如|即使|若|尚未|未曾|并未',t[max(0,m.start()-20):m.start()]):
  parts=[(a+m.start(),a+m.end())]
  if not m['obj']:
   obj=list(re.finditer(r'《[^》]{0,15}(?:巴黎|气候)[^》]{0,20}(?:协定|协议)》',t[:m.start()]))
   if obj:parts.insert(0,(a+obj[-1].start(),a+obj[-1].end()))
   else:parts=[]
  c={'沙特':'沙特阿拉伯','印尼':'印度尼西亚','大韩民国':'韩国'}.get(m['c'],m['c'])
  add(parts,'cancelled_or_withdrawn' if '正式' in m['v'] else 'announced_withdrawal','reported_withdrawal_inside_evaluation','仅保留明确报道的退出事实及条约对象；评价、支持与反对均归档',countries=[c])
 # GDP intensity targets are national future goals, not retrospective statistics.
 q=re.search('('+country_pattern+r')单位国内生产总值[^。；]{0,70}(?:能耗|二氧化碳排放量)[^。；]{0,15}将分别下降[^。；]+',t)
 if q and not re.search(r'研究|估计|预计|预测|假设|如果|建议',t[:q.start()]) and re.search(r'国家主席|政府|总统|首相|总理|习近平',doc.get('title','')+full[:600]):
  add([(a,b)],'announced_goal','public_gdp_intensity_targets','国家公共讲话中的未来强度目标，保留完整期限、对应指标和全部比例',countries=[q[1]])
 # Existing incentive nominal inside a cancellation idea; do not retain the idea as cancellation.
 credit=re.search(r'向[^。；]{0,60}(?:电动汽车|电动车)[^。；]{0,25}提供的\d+(?:\.\d+)?美元政府税收抵免',t)
 if credit and not re.search(r'建议|如果|拟向|计划向',t[:credit.start()]) and re.search(r'取消|撤销|现有|已经提供',full[max(0,a-700):a+credit.start()]):
  owner=r.ownership(t,a,full,old)
  if not owner:
   pubs=[m for m in r.mentions(full[max(0,a-700):a],max(0,a-700)) if m.get('public') and m.get('level')!='local'];cs={m['country'] for m in pubs}
   if len(cs)==1:owner=dict(countries=sorted(cs),actors=pubs[-1:],connection=[],kind='linked',basis='同一既有政府税收抵免及拟取消讨论的国家主体')
  add([(a+credit.start(),a+credit.end())],'implementation','existing_incentive_inside_cancellation_idea','取消想法仍在探索，原文已提供的税收抵免单独保留',owner=owner)
 # The government scheme is distinct from applicants' autonomous capacity bids.
 scheme=re.search('(?P<fact>(?P<c>'+country_pattern+r')政府的(?:激励|扶持|补贴)计划[，,]该计划[^。；]+)',t)
 if scheme and not re.search(r'草案|拟议|建议|尚未批准',t) and re.search(r'电池|储能|新能源|光伏|氢|风电',t+full[max(0,a-250):a]):
  add([(a+scheme.start('fact'),a+scheme.end('fact'))],'announced_plan','public_scheme_inside_private_bid','保留政府激励工具及目标，不混入企业投标规模',countries=[scheme['c']])
 # Adoption of a national framework can be separate from generic economic commentary.
 approved=re.search(r'(?P<fact>(?:(?:19|20)\d\d年\d+月\d+日[，,])?(?:'+country_pattern+r')(?:内阁|政府)(?:正式|已)?批准[^，。；]{0,25}(?:愿景|战略|规划))',t)
 if approved and re.search(r'碳中和|新能源|可再生能源|能源转型',full[max(0,a-1800):a]) and not re.search(r'如果|建议|尚未',t[:approved.start()]):
  add([(a+approved.start('fact'),a+approved.end('fact'))],'approved_strategy','approved_framework_not_macro_commentary','同一能源转型框架的批准事实保留；其余宏观经济宣传另存')
 # Concrete policy order to study is a public task, not an already changed tariff.
 order=re.search(r'要求[^。；]{0,55}(?:部长|部门)[^。；]{0,20}研究[^。；]{0,40}(?:可再生能源|光伏|风电)[^。；]*',t)
 if order and re.search(r'总统|政府|首相|总理',t[:order.start()]) and not re.search(r'专家建议|如果|希望政府',t[:order.start()]):
  pub=[m for m in r.mentions(t,a) if m.get('public') and m['end']<=a+order.start() and m.get('level')!='local']
  if pub:
   actor=pub[0];parts=[(actor['start'],actor['end']),(a+order.start(),a+order.end())]
   owner=dict(countries=[actor['country']],actors=[actor],connection=[],kind='explicit',basis='国家领导人向公共部门部署明确研究任务')
   add(parts,'announced_review','official_research_task','保留要求研究的任务，不写成已经提高电价或实施研究对象',owner=owner)
 # Fix the government parameter even when the grammatical 将 means "set X at", not a future act.
 parameter=re.search(r'(?:拜登|奥巴马|特朗普)?政府将20\d\d年碳排放社会成本定在[^。；]+',t)
 if parameter and not re.search(r'如果|建议|拟',t[:parameter.start()]):add([(a+parameter.start(),a+parameter.end())],'announced_or_adopted','set_carbon_cost_parameter','将X定在Y是参数设定动作，不是未来预测')
 return out
