"""Bounded policy references and nested literal facts; never reads evaluation labels.

This resolver works on the complete source unit before legacy child decisions lose
its shared predicate. Every returned fact is composed only of original intervals.
"""
import copy,re,hashlib
from ..公共工具.identifiers import ident
from ..主体与国家归属.national_scope import evidence

COUNTRIES=r'沙特阿拉伯|印度尼西亚|大韩民国|加拿大|俄罗斯|澳大利亚|意大利|阿根廷|墨西哥|南非|土耳其|巴西|沙特|印尼|中国|美国|日本|韩国|法国|德国|英国|印度|欧盟'
ALIASES={'沙特':'沙特阿拉伯','印尼':'印度尼西亚','大韩民国':'韩国'}
def cs(t):return {ALIASES.get(m.group(),m.group()) for m in re.finditer(COUNTRIES,t)}
def previous_sentences(full,a,limit=2000):
 lo=max(0,a-limit)
 return [dict(start=lo+m.start(),end=lo+m.end(),text=m.group()) for m in re.finditer(r'[^。｡！？\n]+[。｡！？]*',full[lo:a])]
def public_link(r,full,a,keyword,action=r'公布|发布|敲定|通过|颁布|宣布|发出'):
 for x in reversed(previous_sentences(full,a)):
  t=x['text'];acts=list(re.finditer(action,t))
  if not re.search(keyword,t) or not acts:continue
  if re.search(r'候选人|候任总统|竞选计划|竞选纲领',t):continue
  usable=[]
  for m in acts:
   prefix=t[max(0,m.start()-18):m.start()]
   completed_subclause=bool(re.search(r'自[^，。]{0,25}$',prefix) and re.search(r'^(?:敲定|公布|发布|通过)[^，。]{0,35}(?:以来|之后)',t[m.start():]))
   denied=bool(re.search(r'如果|假如|尚未|未曾|建议|计划于|草案',prefix))
   future=bool('将' in prefix and not completed_subclause)
   if not denied and not future:usable.append(m)
  if not usable:continue
  pubs=[m for m in r.mentions(t,x['start']) if m.get('public') and m.get('level')!='local' and m.get('role') not in {'target','private_or_context','location'}]
  countries={m['country'] for m in pubs}
  if len(countries)!=1:continue
  if re.search(r'任[^，。]{0,15}(?:省委书记|省长|州长|市长)|在[^，。]{0,10}(?:地方|浙江)工作期间',t) and not re.search(r'国务院|联邦政府|中央政府',t):continue
  # The institution must be the publisher, not the reporter of a company's act.
  if not any(v['end']<=x['start']+m.start() and not re.search(r'公司|企业|集团|厂商',t[v['end']-x['start']:m.start()]) for v in pubs for m in usable):continue
  # A company saying something about a public institution is not its publication.
  if re.search(r'(?:公司|企业)[^。]{0,12}(?:公布|发布)',t) and not re.search(r'政府[^。]{0,12}(?:公布|发布)',t):continue
  return dict(countries=sorted(countries),actors=pubs,connection=[x],kind='linked',basis='同名政策/同一公共安排的有界原文连接')
 return None

def resolve(r,events,record,full,doc):
 if not events or any(e.get('decision_origin')=='fixed_review_input' for e in events):return None
 a,b=record['start'],record['end'];t=full[a:b];before=full[max(0,a-2000):a];props=[]
 def add(parts,state,rule,reason,owner,extra=None):
  if owner and parts:
   assert all(a<=x<y<=b for x,y in parts)
   props.append(dict(parts=parts,state=state,rule=rule,reason=reason,owner=owner,extra=extra or {}))
 def own(countries,basis,links=None,kind='linked',actors=None):return dict(countries=sorted(countries),actors=actors or [],connection=links or [],kind=kind,basis=basis)
 # An inventory of different agreements is not one shared policy. Do not invent
 # which ministry/company signed which agreement or duplicate it per country.
 portfolio=re.search('(?P<home>'+COUNTRIES+r')政府和相关企业已与(?P<partners>[^。]{3,160})等多国签署了(?P<theme>[^。]{0,30}(?:合作协议|合作备忘录))',t)
 if portfolio:
  z=copy.deepcopy(events[0]);z.pop('text_parts',None);pid=ident('PORTFOLIO-',(record['file_id'],a,b))
  partner_re=COUNTRIES+r'|智利|摩洛哥|阿联酋'
  partners=[dict(country=ALIASES.get(m.group(),m.group()),start=a+portfolio.start('partners')+m.start(),end=a+portfolio.start('partners')+m.end(),text=m.group(),role='合作对象称谓；单份协议签约身份未证实',counterparty_verified=False) for m in re.finditer(partner_re,portfolio['partners'])]
  z.update(event_id=pid,start=a,end=b,text=t,file_id=record['file_id'],route='cooperation_summary',countries=sorted(cs(portfolio['home'])),policy_level='national',policy_state='reported_agreement_portfolio',event_type='agreement_portfolio',cooperation_portfolio=dict(portfolio_id=pid,reporting_actor=portfolio['home']+'政府和相关企业',partners=partners,single_agreement_identity_verified=False,policy_count_eligible=False,analysis_eligible=False),reason='多个国家、多份协议与政府/企业签约混合的汇总；保留公共合作线索和伙伴证据，暂不作为单份政策或国家向量输入',final_fact_rule='agreement_portfolio_separation',evidence=[evidence(full,a,b,'多协议汇总原文')],connection_path=[])
  return [z]
 # Existing public rules nested inside retrospective statistics; the trade
 # association's separate target is deliberately not recovered.
 if re.search(r'政府[^。｡]{0,25}停止了相关补贴',t) and re.search(r'固定价格收购制度',t) and len(cs(t))==1:
  c=cs(t);idx=re.search(COUNTRIES,t);link=dict(start=a+idx.start(),end=a+idx.end(),text=idx.group())
  owner=own(c,'同段唯一国家称谓及政府取消补贴动作',[link])
  m=re.search(r'旨在推动普及可再生能源的["“]固定价格收购制度["”]即将实施',t)
  if m and not re.search(r'如果|假如|拟|建议',t[max(0,m.start()-12):m.start()]):add([(a+m.start(),a+m.end())],'scheduled_implementation','existing_rule_inside_statistics','统计中的既有制度将实施事实单独保留，不纳入协会目标',owner)
  m=re.search(r'政府从[0-9０-９]{4}财年起停止了相关补贴',t)
  if m:add([(a+m.start(),a+m.end())],'cancelled_or_withdrawn','public_subsidy_stop_inside_statistics','保留政府停止补贴及原文起始财年，统计结果另存',owner)
 # Same intention letter, same project count, literal capacities; do not use a
 # generic solar-policy anchor to attach an unrelated company's project list.
 m=re.search(r'意向书披露的(?P<n>\d+)个太阳能项目总装机量[^。｡]+',t)
 if m:
  owner=public_link(r,full,a,r'新能源项目办公室[^。]{0,60}开发意向书')
  if owner and re.search(m['n']+r'个太阳能',owner['connection'][0]['text']):
   end=m.end();effect=re.search(r'[，,]可提供[^。]{0,30}(?:户|居民)',t[m.start():end])
   if effect:end=m.start()+effect.start()
   add([(a+m.start(),a+end)],'announced_plan','intention_letter_project_details','同一公共开发意向书的项目数量、名单和容量；居民用电预测另存',owner)
 # Shared policy predicate with elliptical country-specific dates.
 header=re.search(r'(?:多个|各|一些)国家[^，。]{0,6}(?:均|已)?宣布了?(?P<policy>禁售燃油车的?时间表)',t)
 if header and not re.search(r'如果|假如|建议|或许',t):
  for m in re.finditer('(?P<c>'+COUNTRIES+r')则定在20\d\d年[。]?',t):
   add([(a+header.start('policy'),a+header.end('policy')),(a+m.start(),a+m.end())],'announced_phaseout','elliptic_country_schedule','共享禁售谓词与本国年份组成一条事件，不带入其他国家目标',own(cs(m['c']),'同句国家及共享禁售时间表',kind='explicit'))
 # The claim of contradiction is commentary. A nominal describing the issued
 # strategy can still be a factual reference to its contents.
 m=re.search(r'(?:新|该)战略中提出的[^。｡]{2,100}?(?=自相矛盾|存在矛盾|受到批评)',t)
 if m:
  owner=public_link(r,full,a,r'新战略',r'敲定|公布|发布|通过')
  if owner and re.search(r'核燃料|核电|减排|能源',m.group()):add([(a+m.start(),a+m.end())],'announced_strategy','issued_strategy_inside_critique','仅恢复已公布同战略的具体任务；矛盾评价不是政策措施',owner)
 # Government-issued zone development plan -> only its energy component.
 zone=re.search(r'(?:这片|该)(?:被称为[A-Za-z0-9-]+的)?园区[^。｡]{0,150}?(?=[，,]将集中发展)',t)
 energy=re.search(r'将集中发展新能源',t)
 if zone and energy:
  owner=public_link(r,full,a,r'(?:宣布|公布)[^。]{0,100}(?:建设|新建)[^。]{0,50}园区')
  if owner:add([(a+zone.start(),a+zone.end()),(a+energy.start(),a+energy.end())],'announced_plan','national_zone_energy_component','同一政府园区计划的身份和能源任务；其他商业行业另存，不将邻国位置当主体',owner,dict(event_subtype='national_plan_energy_component'))
 # Only the green pillar of the very same issued policy; the digital pillar is
 # background for this task and is not copied into the retained text.
 pillar=re.search(r'另一项(?:便)?是[^。｡]{0,80}(?:低碳经济|绿色产业)[^。｡]{0,60}[“"]绿色新政[”"][。]?',t)
 if pillar and re.search(r'[“"]新政[”"]',t):
  owner=public_link(r,full,a,r'[“"]新政[”"]')
  if owner:add([(a+pillar.start(),a+pillar.end())],'announced_strategy','named_policy_green_pillar','连接同名已发布新政，只保留绿色产业与低碳支柱',owner)
 # A public framework can be announced without having been implemented.
 framework=re.search('在这一框架下[，,](?P<c>'+COUNTRIES+r')提出了一些倡议[^。｡]+[。]?',t)
 if framework and re.search(r'碳吸存|碳捕获|碳捕集|造林',framework.group()):
  prior=list(re.finditer('(?P<c>'+COUNTRIES+r')(?:气候变化减缓|循环碳经济)计划[^。]{0,170}',before))
  if prior and cs(prior[-1]['c'])==cs(framework['c']):
   q=prior[-1];link=dict(start=a-len(before)+q.start(),end=a-len(before)+q.end(),text=q.group());extra={}
   pending=list(re.finditer(r'[^。｡]{0,80}(?:还没有|尚未)付诸实施[^。｡]{0,80}',before))
   if pending:
    z=pending[-1];link2=dict(start=a-len(before)+z.start(),end=a-len(before)+z.end(),text=z.group());links=[link,link2];extra=dict(implementation_claim='公开策略倡议；前文明确未实施，不能写成已经实施',implementation_status='尚未实施')
   else:links=[link]
   add([(a+framework.start(),a+framework.end())],'announced_plan','announced_framework_tasks','国家已公开框架的造林与CCUS任务；不把未实施条件丢掉',own(cs(framework['c']),'当前国家提出及同一框架',links),extra)
 # Reporter summary is a separate, qualified extension of an issued plan, not a
 # newly invented public decision and not an official verbatim quotation.
 if re.match(r'因此[，,]他的政策会以',t) and re.search(r'减少使用污染能源',t) and re.search(r'洁净能源|清洁能源',t) and re.search(r'节约用能',t):
  owner=public_link(r,full,a,r'一揽子计划')
  if owner and any(m.get('text') and re.search(r'总统|奥巴马|首相|总理',m['text']) for m in owner['actors']):add([(a,b)],'reported_strategy_summary','reported_strategy_summary','连接已公布计划的报道归纳；仅入扩展，不作为独立新措施或官方逐字引文',owner,dict(assertion_type='报道归纳',official_verbatim=False))
 # Federal authorization condition, not California's independently chosen
 # numerical standard. Preserve the beneficiary and EPA approval prerequisite.
 basis=re.search(r'根据(?:19|20)\d\d年修订的《清洁空气法》',t)
 condition=re.search(r'并获得每项法规在获得EPA批准后即可实施的权限[。]?',t)
 if basis and condition and '加州' in t and re.search(r'CO2|CAFE|燃油|排放',before+t):
  beneficiary=t.index('加州');add([(a+beneficiary,a+beneficiary+2),(a+basis.start(),a+basis.end()),(a+condition.start(),a+condition.end())],'execution_requirement','federal_delegation_condition','联邦法对地方标准的授权及EPA批准前提；加州自主标准和市场统计不进入国家文本',own({'美国'},'清洁空气法及EPA联邦审批关系',kind='explicit',actors=[dict(country='美国',text='EPA',start=a+t.index('EPA'),end=a+t.index('EPA')+3,public=True,level='national')]))
 # Treaty anaphor must connect to its actual notice, not to a nearby country's
 # election platform. Do not infer jurisdiction merely from the source folder.
 if re.search(r'根据《协定》的规定[，,]退出将于通知书送达后一年生效',t):
  notices=list(re.finditer('(?P<c>'+COUNTRIES+r')(?:正式|已经|已)?提交了?退出(?P<name>《[^》]{2,30}协定》)的通知',before))
  if notices:
   m=notices[-1]
   if not re.search(r'将|拟|如果|尚未|并未',before[max(0,m.start()-12):m.start()]):
    link=dict(start=a-len(before)+m.start(),end=a-len(before)+m.end(),text=m.group());add([(a,b)],'execution_requirement','treaty_notice_effectiveness','该协定→具名条约及已提交通知→提交国家；保留送达一年后条件，不填造生效日期',own(cs(m['c']),'已提交退约通知的直接关系',[link]))
 # "Both countries" inherits two public commitment subjects, while "the
 # agreement" separately resolves a named treaty. These are different links.
 if re.search(r'两国都?已经承诺将于今年内?正式批准该协议',t):
  prev=previous_sentences(full,a)
  if prev:
   x=prev[-1];pair=cs(x['text']);pubs=[v for v in r.mentions(x['text'],x['start']) if v.get('public') and v.get('level')!='local']
   treaties=list(re.finditer(r'(?:《[^》]{0,12})?巴黎(?:气候)?(?:协定|协议)(?:》)?',before))
   if len(pair)==2 and len(re.findall(r'承诺',x['text']))>=2 and pubs and treaties and not re.search(r'公司|企业|如果|假如|可能',x['text']):
    m=treaties[-1];name=dict(start=a-len(before)+m.start(),end=a-len(before)+m.end(),text=m.group())
    add([(a,b)],'announced_ratification','joint_ratification_pledge','两国→前句两公共承诺主体；该协议→巴黎协议；保留将于年内批准而非已批准',own(pair,'两个实际国家承诺主体及同一条约',[x,name],kind='joint',actors=pubs),dict(shared_event=True,ratification_completed=False))
 if not props:return None
 result=r.emit(record,events,full,props,archive_route='background',reason='当前政策事实之外的统计、评价、其他行业或连接语')
 if result:
  by={p['rule']:p for p in props}
  for e in result:
   p=by.get(e.get('final_fact_rule'))
   if p:
    e.update(p['extra']);e['linked_resolution_version']='bounded-policy-links-6.10'
    e['policy_reference_chain']=dict(current_expression=e['text'],policy_or_authorization_evidence=p['owner']['connection'],public_actor_mentions=p['owner']['actors'],countries=p['owner']['countries'],basis=p['owner']['basis'])
   elif '加州制定' in e['text']:e.update(route='local_policy',reason='地方自主标准另存；国家授权前提已经单独抽取')
 return result


def apply_quality_reviews(events,record,full,doc,reviews):
 """Transparent, hash-bound source adjudications; no unseen labels or ID hacks."""
 relevant=[x for x in reviews if x['file_id']==record['file_id']]
 if not relevant:return events
 digest=hashlib.sha256(full.encode('utf8')).hexdigest();out=[]
 for e in events:
  e=copy.deepcopy(e)
  for q in relevant:
   if digest!=q['normalized_sha256']:raise ValueError('原文疑点资源哈希不匹配 '+q['review_id'])
   a,b=q['start'],q['end']
   if full[a:b]!=q['original_quote']:raise ValueError('原文疑点引文或范围不匹配 '+q['review_id'])
   if e['route'].startswith('main_') and any(p['start']<b and a<p['end'] for p in e.get('text_parts') or [e]):
    e.update(route='source_quality_quarantine',delivery_layer='隔离归档',source_quality_review=q,reported_policy_state=e.get('policy_state'),policy_state='source_ambiguity',reason=q['disposition_reason'],quality_disposition='歧义原句隔离，关联语料内清晰表述；不改写原文数字和时间',independent_human=False)
  out.append(e)
 return out


def export_resolution_evidence(out,events):
 from ..公共工具.io_utils import write_csv
 portfolios=[];partners=[];source_reviews=[];joint=[];links=[]
 seen=set()
 for e in events:
  common=dict(event_id=e['event_id'],file_id=e['file_id'],start=e['start'],end=e['end'],text=e['text'])
  if e.get('cooperation_portfolio'):
   p=e['cooperation_portfolio'];portfolios.append(dict(common,**p))
   for x in p['partners']:partners.append(dict(event_id=e['event_id'],portfolio_id=p['portfolio_id'],file_id=e['file_id'],**x))
  if e.get('source_quality_review'):
   q=e['source_quality_review']
   if q['review_id'] not in seen:source_reviews.append(dict(common,**q,text=q['original_quote']));seen.add(q['review_id'])
  if e.get('final_fact_rule')=='joint_ratification_pledge':joint.append(dict(common,countries=e['countries'],joint_participants=e.get('joint_participants'),state=e['policy_state'],roles=e['roles'],connection_path=e['connection_path'],counting_note='同一event_id供各国引用；不按参与国另造政策'))
  if e.get('policy_reference_chain'):links.append(dict(common,rule=e['final_fact_rule'],state=e['policy_state'],countries=e['countries'],reference_chain=e['policy_reference_chain'],evidence=e['evidence']))
 write_csv(out/'关系与疑点/多协议汇总.csv',portfolios,fields=['event_id','file_id','start','end','text','portfolio_id','reporting_actor','partners','single_agreement_identity_verified','policy_count_eligible','analysis_eligible'])
 write_csv(out/'关系与疑点/合作对象证据.csv',partners,fields=['event_id','portfolio_id','file_id','country','start','end','text','role','counterparty_verified'])
 write_csv(out/'关系与疑点/原文疑点处置.csv',source_reviews,fields=['event_id','file_id','start','end','text','review_id','normalized_sha256','original_quote','disposition_reason','linked_corpus_evidence','external_references','review_source','human_confirmed','action'])
 write_csv(out/'关系与疑点/共同批准承诺.csv',joint,fields=['event_id','file_id','start','end','text','countries','joint_participants','state','roles','connection_path','counting_note'])
 write_csv(out/'关系与疑点/本轮连接证据.csv',links,fields=['event_id','file_id','start','end','text','rule','state','countries','reference_chain','evidence'])
 return dict(agreement_portfolio_occurrences=len(portfolios),portfolio_partner_mentions=len(partners),source_quality_reviews_applied=len(source_reviews),joint_ratification_occurrences=len(joint),linked_fact_occurrences=len(links))
