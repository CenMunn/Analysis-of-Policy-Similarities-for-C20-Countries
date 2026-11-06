"""Final literal fact audit. No sample IDs, reference labels, or vector scores are used.

This layer checks policy publicness independently from inherited country evidence,
supports bounded links to issued policy tasks, and archives every unused character.
"""
import copy,re
from ..主体与国家归属.national_scope import G20,evidence
from ..公共工具.identifiers import ident
from ..政策内容判定.current_assertion_guard import assertion_exclusion
from ..事实修补与补漏.nested_policy_recall import nested_recoveries

VERSION='literal-policy-refiner-20261026.6.9'
COUNTRY=r'沙特阿拉伯|印度尼西亚|大韩民国|加拿大|俄罗斯|澳大利亚|意大利|阿根廷|墨西哥|南非|土耳其|巴西|沙特|印尼|中国|美国|日本|韩国|法国|德国|英国|印度|欧盟'
TOPIC=re.compile(r'双碳|绿色新政|绿色增长战略|绿色成长战略|绿色创新基金|加氢站|加氢基础设施|氢项目|甲烷排放|CCS|京都议定书|充电桩|充电设施|碳中和|碳达峰|碳排放|碳成本|温室气体|碳税|碳定价|碳配额|减排|净零|零排放|气候|全球变暖|能源转型|能源使用|上网电价|汽油和柴油汽车|巴黎协定|巴黎气候协定|低碳|脱碳|清洁能源|清洁电力|可再生|新能源|太阳能|光伏|风电|风能|风力|核电|核能|煤炭|煤电|燃煤|氢能|氢经济|氢动力|氢气|氨能|氢和|氢、|清洁氢|制氢|碳捕获|碳捕集|CCUS|节能|能效|能源效率|能源消耗|能源价格|电动汽车|电动车|燃油车|混合动力车|燃油排放|燃油经济性|燃料电池|储能|生物燃料|森林碳汇')
POLICY=re.compile(r'政策|计划|战略|规划|法案|法律|法规|标准|方案|路线图|目标|倡议|愿景|协定|协议|补贴|税收|关税|征税|抵免|招标|拨款|配额|监管|能源部|能源局')
ACTION=re.compile(r'公布|发布|制定|出台|通过|批准|颁布|签署|设定|决定|宣布|承诺|要求|规定|授权|允许|实施|停止|取消|废除|关停|关闭|暂缓|叫停|拨款|征收|提供|补贴|投资|投入|支持|将|计划|力争')
PUBLIC=re.compile(r'政府|总统|首相|总理|国会|内阁|国务院|白宫|国家发改委|国家发展改革委|国家能源局|外交部|委员会|能源部|产业部|经济产业省|经济产业大臣|国务会议|METI|环境部|能工矿部|新能源项目办公室|最高法院|高等法院|联邦宪法法院|习近平|文在寅|奥巴马|拜登|特朗普|马克龙|默克尔|菅义伟|萨勒曼|王储')
PRIVATE=re.compile(r'佳能|雷诺|特斯拉|苹果|谷歌|微软|亚马逊|远景|晶科|东芝|通用汽车|SolarReserve|UniCredit|ReNew|Fluence|某公司|该公司|企业|公司|集团|厂商|制造商')
FORMAL=re.compile(r'公布|发布|制定|出台|通过|批准|颁布|签署|设定|宣布|决定|承诺|发表|敲定|发出')
TASK=re.compile(r'拨款|构建|培育|推广|扩充|导入|确保|划定|设立|完善|加大|支持|提高|降低|开发|建成|投资|输送|实现|减少|淘汰|关闭|保留|适用于|不包括|不得|必须|只有|筹备|调查|征收期|供应|回收|商用化|定下|寻求|披露|规定|建设')
PLANNED=re.compile(r'计划|目标|战略|规划|方案|路线图|标准|法案|法律|法规|倡议|愿景|3\+1|新政')
LOCAL=re.compile(r'(?:省|州|市|县|地方)政府|市议会|州议会|桑德兰|格尔木|柯林斯堡')
CANON={'沙特':'沙特阿拉伯','印尼':'印度尼西亚','大韩民国':'韩国'}

def canon(c):return CANON.get(c,c)
def is_keep(e):return e.get('route','').startswith('main_')
def topics(t):return {k for k,p in {'hydrogen':r'氢','solar':r'光伏|太阳能','wind':r'风能|风电','nuclear':r'核电|核能','coal':r'煤','vehicles':r'汽车|车辆|电动车','efficiency':r'节能|能效|能源效率','carbon':r'碳|气候','renewable':r'可再生|新能源'}.items() if re.search(p,t)}

class FinalFactRefiner:
 def __init__(self,roles,params=None):self.roles=roles;self.params=params or {};self._profiles={};self.quality_reviews=[]

 def mentions(self,t,a):
  values=self.roles.mentions(t,a)
  for m in re.finditer(r'野田政府|安倍政府',t):
   values.append(dict(country='日本',text=m.group(),start=a+m.start(),end=a+m.end(),public=True,level='national',role='public_actor',basis='本层政府别名；不修改旧内容引擎'))
  cs={canon(m.group()) for m in re.finditer(COUNTRY,t)}
  if len(cs)==1:
   for m in re.finditer(r'能工矿部|新能源项目办公室',t):
    values.append(dict(country=next(iter(cs)),text=m.group(),start=a+m.start(),end=a+m.end(),public=True,level='national',role='public_actor',basis='同句唯一国名及部委下属机构'))
  for m in re.finditer(r'\bMETI\b',t):
   values.append(dict(country='日本',text=m.group(),start=a+m.start(),end=a+m.end(),public=True,level='national',role='public_actor',basis='日本经济产业省的官方英文简称'))
  for m in re.finditer(r'日本经济产业大臣[^，。]{0,10}|韩国国务会议',t):
   values.append(dict(country='日本' if m.group().startswith('日本') else '韩国',text=m.group(),start=a+m.start(),end=a+m.end(),public=True,level='national',role='public_actor',basis='当前国家部级公共机构称谓'))
  for m in re.finditer(r'美国(?:最高|高等|联邦)?法院|德国联邦宪法法院',t):
   values.append(dict(country='美国' if m.group().startswith('美国') else '德国',text=m.group(),start=a+m.start(),end=a+m.end(),public=True,level='national',role='public_actor'))
  return values

 def profile(self,full):
  if full in self._profiles:return self._profiles[full]
  # One document at a time; do not retain a corpus-sized text cache.
  self._profiles.clear();anchors=[]
  for s in re.finditer(r'[^。！？\n]+[。！？\n]*',full):
   t=s.group()
   country_public=bool(re.search('('+COUNTRY+r')(?:政府)?[^。]{0,25}(?:宣布|计划到)[^。]{0,65}(?:绿色计划|碳中和|可再生能源)',t))
   implemented=bool(re.search(r'(?:政府|内阁|部委|工业省)[^。]{0,35}(?:已|去年)?实施[^。]{0,30}(?:法律|法规|计划)|政府[^。]{0,10}(?:说|表示)[，,][^。]{0,25}(?:禁售|淘汰|停止)',t))
   if len(t)>1200 or not TOPIC.search(t) or (not FORMAL.search(t) and not country_public and not implemented) or (not PUBLIC.search(t) and not country_public):continue
   if re.search(r'草案|尚未|未获|未能|未通过|建议|候任|计划(?:于|在)?.{0,12}(?:公布|发布)',t):continue
   if '竞选' in t and not re.search(r'(?:政府|总统)[^。]{0,25}宣布[^。]{0,160}(?:兑现|履行)竞选承诺',t):continue
   ms=[m for m in self.mentions(t,s.start()) if m.get('public') and m.get('level')!='local' and m.get('role') not in {'target','private_or_context','location'}]
   countries={m['country'] for m in ms}&G20
   if not countries and country_public:
    countries={canon(m.group()) for m in re.finditer(COUNTRY,t)}
   if countries:
    anchors.append(dict(start=s.start(),end=s.end(),text=t,countries=sorted(countries),actors=ms,topics=topics(t),policy=bool(PLANNED.search(t) or re.search(r'禁售|禁用|禁令',t))))
  profile=dict(anchors=anchors,campaign_people=set(),coalition=False)
  for name in ['拜登','特朗普']:
   early=full[:6000]
   if re.search(r'(?:竞选|候选人|当选总统|候任总统)[^。]{0,35}'+name+'|'+name+r'[^。]{0,45}(?:竞选|候任|尚未上任|上任在即|当选总统|胜选机会|赢得白宫)',early):profile['campaign_people'].add(name)
  if re.search(r'联合执政协议|组阁协议|三党.{0,10}(?:协议|组阁)',full) and re.search(r'尚需|有望.{0,15}上台|各自.{0,15}批准|新政府尚未',full):profile['coalition']=True
  self._profiles[full]=profile;return profile

 def publication_status(self,t,a,full):
  if re.search(r'即使|如果|假如|若(?:当选|胜选|政策落地)|一旦',t[:30]) and not re.search(r'法案规定|法律规定|该标准|根据.*(?:政策|标准)|符合条件',t):return 'discussion','conditional_hypothesis','条件假设，未声称当前采纳'
  if re.search(r'(?:正考虑|正在考虑|将考虑|仍在探索|威胁要|建议|呼吁|希望政府|应站出来|政府应推进|有意增加)',t):return 'discussion','proposed_change','考虑、建议或威胁，不升级为已采纳'
  if re.search(r'将(?:在|于)?[^，。]{0,20}(?:首次施政演说|下周|明天|很快宣布|推出历来)|下周[^。]{0,20}计划承诺|将很快宣布',t):return 'discussion','announcement_preview','仅预告将宣布，尚未公布措施'
  if re.search(r'计划(?:于|在)?(?:本月|下月|近期|未来几周|20\d\d年[^，。]{0,8})[^，。]{0,10}敲定|(?:增长战略|能源战略)[^。]{0,20}尚待敲定',t):return 'draft','not_finalized_strategy','尚待敲定的战略及将提出的目标单列，不当已经公布的战略'
  if re.search(r'(?:政府|内阁|国会|委员会)[^。]{0,25}(?:正在讨论|正讨论|正在审议|仍在审议)[^。]{0,30}(?:能源法|气候法|法案|法律|法规)',t):return 'draft','draft_or_proposal','正在讨论或审议的法律，未来实施计划不能当成已实施'
  if re.search(r'草案|尚未通过|未能通过|无望.{0,15}通过|未获.{0,12}(?:通过|批准)|未通过|仍在准备阶段',t):return 'draft','draft_or_proposal','待批准草案或尚未通过安排'
  before=full[max(0,a-1800):a];after=full[a+len(t):a+len(t)+1400]
  if re.search(r'支出法案|一揽子支出|税收和支出计划|支出计划|补充预算|拟放宽|正计划放宽',t) and re.search(r'草案|国会.{0,25}(?:投票|审议)|无望.{0,12}通过|尚待.{0,10}通过|提案将|将征求|未能通过',t+after):
   return 'draft','draft_or_proposal','同一支出/税收/监管方案上下文仍待立法或征求意见'
  if self.profile(full)['coalition'] and re.search(r'上述协议|基金将|德国将在|联合执政',t):return 'draft','coalition_platform','尚待党内批准及就职的组阁平台'
  campaign=self.profile(full)['campaign_people']
  if campaign and re.search(r'将|计划|支持|要求|承诺|创造|升级|投入|建立|确保',t):
   # A past act or an incumbent's completed decision in the same article stays eligible.
   old_actor=('奥巴马' in t and '奥巴马' not in campaign) or bool(re.search(r'201[0-9]年.{0,25}(?:通过|制定|提供|签署|公布)|已经|已签署|已批准|上任后|就任后|就职后|上任以来',t))
   incumbent_decision=bool(re.search(r'(?:拜登|特朗普)政府(?:已经|正式|已|于[0-9年月日]+)?(?:宣布|发布|签署|批准|决定)|20\d\d年[^。]{0,15}(?:特朗普|拜登)(?:总统)?(?:正式|已经|已)?宣布',t)) and not re.search(r'候选人|候任|如果|若当选|将宣布|会宣布|未曾|尚未',t)
   incumbent_report=bool(re.search(r'美国总统[^，。]{0,20}(?:签署了|在白宫宣布|正式宣布)|(?:拜登|特朗普)政府(?:就|还|已)?宣布拨款',t)) and not re.search(r'当选总统|候任|候选人|如果|尚未|将签署|将宣布',t)
   old_actor=old_actor or incumbent_decision or incumbent_report
   current_inaug=bool(re.search(r'(?:拜登|特朗普)[^。]{0,12}(?:已经|正式)(?:就职|宣誓|就任)|(?:上任后|就职后)(?:已|已经|正式)',before[-400:]))
   addressed=any(n in t for n in campaign) or bool(re.search(r'美国(?:政府)?将',t)) or bool(re.match(r'(?:[（(]?\d+[)）、.．]|第二|第三|建筑减排|在需求端|要求全世界|制定有针对性)',t.strip()))
   if addressed and not old_actor and not current_inaug:return 'campaign','campaign','同一竞选/候任平台；未连接到已就职后的公共决定'
  if re.search(r'这项法案|该法案|法案',t) and re.search(r'前景不明|无望.{0,15}通过|不(?:会)?投票支持',t+before[-700:]):return 'draft','draft_or_proposal','同名法案尚待批准，当前条款不能当现行措施'
  proposed=re.search(r'政府[^。]{0,20}提出(20\d\d)[^。]{0,30}新目标',full[:240])
  if proposed and re.search(r'汇总出了.{0,8}建议',full) and re.search(r'计划把此次提出的目标|还将在.{0,20}公布',full) and (proposed[1] in t or '这一目标' in t):return 'draft','not_adopted','同一目标来自待采纳建议，正式提交公布尚待未来'
  return None

 def anchor(self,t,a,full):
  xs=[x for x in self.profile(full)['anchors'] if x['start']<a and x['end']<=a and a-x['end']<=self.params.get('link_chars',1800)]
  current_countries={canon(m.group()) for m in re.finditer(COUNTRY,t)}
  for x in reversed(xs):
   bridge=full[x['end']:a]
   if re.search(r'以下(?:是|为).{0,15}(?:建议|评论)|观点如下|竞选计划如下|公司介绍自己的计划',bridge):break
   if re.search(r'产业界也正展开行动|(?:公司|集团|巨头)[A-Za-z0-9]*的[^。]{0,20}(?:项目|工厂)|(?:公司|集团)[^。]{0,20}(?:宣布|启动|研发)',bridge) and not re.search(r'政府.{0,30}(?:资助|委托|要求)|经济产业省.{0,30}援助',bridge):continue
   if current_countries and not current_countries&set(x['countries']):continue
   tx=topics(t)
   if tx and x['topics'] and not tx&x['topics'] and not ('carbon' in x['topics'] or x['policy']):continue
   competing=[v for v in xs if x['end']<=v['start']<a and set(v['countries'])!=set(x['countries'])]
   if competing:continue
   if not x['policy'] and not re.search(r'该|这些|上述|根据|同时|首先|其次|一是|二是|将建造',t):continue
   return x
  return None

 def ownership(self,t,a,full,old=None,explicit=None):
  ms=self.mentions(t,a);pub=[m for m in ms if m.get('public') and m.get('level')!='local' and m.get('role') not in {'target','private_or_context','location'}]
  if any(m.get('level')=='local' for m in ms) and not pub and LOCAL.search(t):return None
  # Country mentions in a past-policy nominal are not necessarily the report's current actor.
  if re.search(r'531新政',t) and not re.search(r'(?:美国|日本|韩国|德国|法国)政府[^。]{0,10}(?:发布|公布|制定)',t):return dict(countries=['中国'],actors=pub,connection=[],basis='已核对的国家政策名称：531新政',kind='named_policy')
  if explicit:return dict(countries=sorted(explicit),actors=pub,connection=[],basis='当前并列国家及动作',kind='explicit')
  # Keep both actual public counterparties of a signed/established common arrangement.
  pc={m['country'] for m in pub}&G20
  if len(pc)>1 and re.search(r'与|和|双方|两国|共同',t) and re.search(r'达成.{0,12}协议|签署|建立.{0,15}对话|联合(?:发布|宣布)',t):
   return dict(countries=sorted(pc),actors=pub,connection=[],basis='同一签署/建立动作的公共参与方',kind='joint')
  if len(pc)==1:return dict(countries=sorted(pc),actors=pub,connection=[],basis='当前字面公共主体',kind='explicit')
  country_subjects=[]
  for m in re.finditer('('+COUNTRY+r')(?:政府)?(?:的)?(?:(?:今年|近日|此前|最初|于20\d\d年|在20\d\d年))?(?:将|则|计划|承诺|已经|已|宣布|设定|制定|正在|在\d|最初计划|于\d)',t):country_subjects.append(canon(m[1]))
  if len(set(country_subjects))==1:
   c=country_subjects[0];return dict(countries=[c],actors=pub,connection=[],basis='当前国家称谓与具体政策动作',kind='country_statement')
  plan=re.search('('+COUNTRY+r')(?:的)?(?:气候变化减缓|碳中和|能源转型|可再生能源)[^，。]{0,10}(?:计划|战略|规划)(?:基于|包括|提出|明确)',t)
  if plan:return dict(countries=[canon(plan[1])],actors=pub,connection=[],basis='原文明示国家所属政策结构',kind='country_statement')
  anchor=self.anchor(t,a,full)
  if anchor:return dict(countries=anchor['countries'],actors=anchor['actors'],connection=[anchor],basis='同一已发布政策的有界上下文连接',kind='linked')
  if old and is_keep(old) and old.get('countries') and old.get('policy_level')=='national':
   if pub and len(pc)>1:return None
   explicit_c={m['country'] for m in ms if m.get('role') not in {'target','private_or_context','location'}}
   if explicit_c-set(old['countries']):return None
   return dict(countries=old['countries'],actors=old.get('roles',{}).get('actors',[]),connection=[],basis='原已保留归属；本轮仅校核当前具体措施范围',kind='preserved')
  return None

 def state(self,t,old='announced_or_adopted'):
  if re.search(r'法院.{0,20}(?:暂时叫停|暂缓实施|暂停|叫停)',t) or re.search(r'被.{0,8}法院.{0,8}暂缓',t):return 'suspended_by_court'
  if re.search(r'法院.{0,20}(?:投票否决|否决|判.{0,6}不合法|裁定.{0,15}违宪)',t):return 'judicial_rejection'
  if re.search(r'法院.{0,12}裁定',t):return 'judicial_ruling'
  if re.search(r'将进一步提高.{0,25}(?:减排目标|国家温室气体)|承诺.{0,10}将加强.{0,15}国家自主贡献',t):return 'announced_review'
  if re.search(r'批准.{0,20}(?:战略|愿景|构想)',t):return 'approved_strategy'
  if re.search(r'已.{0,5}投入|累计投入|已经.{0,10}(?:提高|拨款|发放)|在去年.{0,8}将.{0,15}补贴提高|开始实施|已实施|已经于.{0,15}实施|正式实施',t):return 'implementation'
  if re.search(r'已经|正式',t) and re.search(r'重返|重新加入',t):return 'implemented_reentry'
  if re.search(r'(?:宣布|决定)(?:将|要)?退出[^。]{0,35}(?:协定|协议)|将退出[^。]{0,35}《[^》]*(?:协定|协议)》',t):return 'announced_withdrawal'
  if re.search(r'签署|签订|达成.{0,12}协议',t):return 'agreement_signed'
  if re.search(r'取消|废除|解除.{0,8}禁令|停止了.{0,10}补贴|正式退出',t) and not re.search(r'将|计划|承诺|建议',t[:max(0,min([m.start() for m in re.finditer(r'取消|废除|停止|退出',t)] or [0]))]):return 'cancelled_or_withdrawn'
  if re.search(r'将(?:全面)?取消|计划.{0,12}(?:取消|淘汰|关闭)|不再批准|终止所有建设',t):return 'announced_phaseout'
  if re.search(r'批准',t):return 'announced_or_adopted'
  if re.search(r'关停|关闭|暂停',t) and re.search(r'将|计划|宣布',t):return 'announced_suspension'
  if PUBLIC.search(t) and re.search(r'计划(?:参考|比较|研究)|对[^。]{0,20}进行整体评估',t) and not re.search(r'已颁布|已经实施|正式公布',t):return 'announced_review'
  if re.search(r'该标准|规定|适用于|不包括|必须|不得|征收期',t):return 'execution_requirement'
  # A different actor-action pair cannot inherit the preceding event's withdrawal/signature.
  if old in {'announced_withdrawal','cancelled_or_withdrawn','agreement_signed'} and re.search(r'(?:政府|内阁|委员会)[^，。]{0,12}(?:公布|发布)[^。]{0,65}(?:政策|计划|战略|规划)',t):return 'announced_plan'
  return old or 'announced_or_adopted'

 def nonpolicy(self,t,a,full):
  # Concrete existing-rule extraction happens before this guard.
  guard=assertion_exclusion(t)
  if guard:return guard
  if re.search(r'(?:反对者|批评者|批评人士|反对人士)(?:称|认为|表示)[^。]{0,100}(?:宣战|对抗|打击|扼杀|灾难)',t):return 'commentary','','反对者的比喻或价值判断，不把转述的政策名称当成措施'
  status=self.publication_status(t,a,full)
  if status:return status
  if re.search(r'疫苗|新冠接种|NFT|波场基金|Apple Watch|机器人|珠宝展',t) and not TOPIC.search(t):return 'out_of_scope','','当前动作没有双碳主题，不能继承相邻主题'
  if re.search(r'版权|责任编辑|发表评论|返回搜狐|收藏政府信息|全球周报.*全球周报|篇数：|点击排行',t):return 'noise','','网页组件、推荐串接或页脚'
  if re.search(r'(?:根据|据).{0,35}(?:数据|统计)|数据显示',t) and re.search(r'去年|目前|截至|累计|上年',t) and not re.search(r'目标|规划|计划|规定|决定|拨款|政府累计投入',t):return 'background','','统计陈述不当作措施'
  if re.search(r'(?:缩写|简称|是一种|是一项)[^。]{0,100}(?:技术|概念)|(?:技术|概念)(?:是指|指的是)',t) and not (PUBLIC.search(t) and FORMAL.search(t)):return 'background','','技术定义不继承前文措施主体'
  if re.search(r'提前实现|已实现|完成了|提前完成',t) and re.search(r'(?:此前|20\d\d年)(?:设定|提出|制定)的.{0,20}目标|规划目标',t):return 'background','','既有目标完成情况，不能借前文外国主体生成新措施'
  if re.search(r'认为|指出|表示',t) and re.search(r'发挥.{0,12}(?:作用|影响)|导致.{0,15}无法|现实情况|竞争优势',t) and not (PUBLIC.search(t) and FORMAL.search(t)):return 'commentary','','机构或企业评价及结果解释，不是政策执行任务'
  company=re.search(r'公司|企业|制造商|厂商|丰田|本田|佳能|远景|该公司|某公司|UniCredit|ReNew|Fluence',t[:65]);public=PUBLIC.search(t)
  if company and (not public or public.start()>company.start()) and re.search(r'投资|投入|建设|建立|供货|供应|合作|取消|生产|开发|研发|支持|反对|提供',t) and not re.search(r'政府.{0,30}(?:拨款|资助|采购|批准|委托|激励计划)|国家.{0,10}批准|总统.{0,15}签署',t):
   return 'private_project','','本句企业自主动作，不继承上句政府主体'
  if re.search(r'总统|总理|首相|王储|部长|马克龙|默克尔|拜登|文在寅',t) and re.search(r'见证.{0,20}合作|合作将加速|非常需要.{0,20}合作伙伴|具有里程碑意义|重要.{0,8}平台|只是.{0,10}愿景的序幕',t) and not re.search(r'拨款|资助|批准建设|正式签署|制定.{0,8}要求',t):return 'commentary','','公共人物对合作或政策意义的评价，不等于新措施'
  if re.search(r'雄心.{0,50}一致|计划.{0,25}一致|与.{0,30}努力.{0,8}一致|更加坚定|必要措施|最有效途径|减排.{0,10}潜力|有望|预计|相信|估计|分析师|自我孤立|无赖|空头支票',t) and not re.search(r'公布|发布|宣布|颁布|批准|制定|设定|规定|正式退出|宣布退出',t):return 'commentary','','效果、必要性或立场评价；没有当前公共决定'
  if re.search(r'没有表示|尚未表示|未承诺',t):return 'discussion','not_committed','没有承诺不等于决定取消措施'
  if re.search(r'加剧.{0,10}竞争|推动.{0,10}经济.{0,10}增长|迅速兑现.{0,20}承诺|必须.*思维能力|系统观念贯穿',t) and not re.search(r'公布|出台|批准|规定|资助|拨款',t):return 'commentary','','一般评价或引导，没有具体措施'
  if re.search(r'将解决.{0,25}难题|历经屡次拖期|预计实现|预测.{0,15}实现',t):return 'commentary','','项目效果、进度或研究情景，不是当前公共措施'
  if re.search(r'期待.{0,70}(?:支持|推进)|关键需要|补贴力度不足|缺乏长期.{0,15}政策|缺乏充电站|态度.{0,10}坚定|将保持平衡|不是轻易|努力是一致|将使.{0,20}实现净零|从根本上改变.{0,20}政策|支持进一步推广',t):return 'commentary','','外部期待、必要性、支持立场或效果分析，未交代已采纳工具'
  if re.search(r'制造业的工作要留给|采取更有力度的行动|合力孵化.{0,15}黑马|环保累计投入|在欧盟宣布.{0,25}之前|已有30多个国家',t):return 'background','','泛立场、汇总或未区分双碳用途的背景，不是可识别国家措施'
  if re.search(r'世界银行.{0,30}批准.{0,30}贷款',t):return 'international_framework','','国际金融机构为施策方，不能仅凭受益地归入国家公共措施'
  if re.search(r'进一步加强了这些计划|主要讨论.{0,15}(?:不同|备选)方案|讨论.{0,12}不同方案|认为.{0,65}运行良好',t):return 'commentary','','政策影响评价或未选择的备选方案，不当作采纳措施'
  if re.search(r'考虑(?:使用|采取|征收|实行|提供)',t) and not re.search(r'要求|下令|部署|决定.{0,12}研究',t):return 'discussion','proposed_change','正在考虑工具选择，尚未决定采用'
  if re.search('(?:'+COUNTRY+r')计划在首都[^。]{0,20}投资',t) and not re.search(r'政府|内阁|能源部|国家预算|国家规划',t):return 'level_unknown','unknown','城市项目未明确国家出资或国家执行关联，层级待核'
  if re.search(r'关键字[:：]|阅读量|摘要[:：]|股价|股票|个股|股市',t) and not (PUBLIC.search(t) and FORMAL.search(t) and re.search(r'拨款|补贴|关税|税收|核准',t)):return 'noise','','网页标题、市场串接或摘要不替代独立政策正文'
  if re.search(r'该研究报告发布之前',t) and re.search(r'国会.{0,20}(?:仍在|正在|制定)|仍由国会制定',full[a:a+len(t)+1200]):return 'quality_unknown','','研究情景与未完成法案的目标状态混杂，保留疑点'
  if re.match(r'\s*(?:根据计划[，,])?(?:此项目|该项目|该公司|我们)',t):
   bridge=full[max(0,a-450):a]
   if re.search(r'产业界也正展开行动|(?:公司|集团|巨头)[A-Za-z0-9]*的[^。]{0,20}(?:项目|工厂)',bridge) and not re.search(r'政府.{0,30}(?:资助|委托|要求)|经济产业省.{0,30}援助',bridge):return 'private_project','','最近指代已切换到企业自主项目，不能继承更早国家目标'
  return None

 def emit(self,record,events,full,proposals,archive_route='commentary',reason='事实之外的评论、背景或连接语'):
  output=[];covered=[];base=next((e for e in events if is_keep(e)),events[0] if events else record)
  for j,p in enumerate(proposals):
   spans=p['parts'];text=' … '.join(full[a:b] for a,b in spans);old=next((e for e in events if is_keep(e) and e['start']<=spans[0][0]<e['end']),base)
   owner=p.get('owner') or self.ownership(text,spans[0][0],full,old)
   if not owner or not owner['countries']:continue
   z=copy.deepcopy(old);parts=[dict(start=a,end=b,text=full[a:b]) for a,b in spans]
   for k in ['text_parts','optimized_attribution','s_scores','legacy_s_scores','policy_content_contract','joint_participants']:z.pop(k,None)
   z.update(event_id=ident('F69-',(record['file_id'],spans,owner['countries'],p['state'])),start=spans[0][0],end=spans[-1][1],text=text,
    file_id=record['file_id'],route='main_explicit',countries=owner['countries'],policy_level='national',policy_state=p['state'],
    reason='FINAL_FACT：'+p['reason'],country_basis=owner['basis'],annotation_origin='程序自动处理',final_fact_version=VERSION,
    final_fact_rule=p['rule'],newly_recovered=not (is_keep(old) and old.get('delivery_layer')=='主分析候选' and owner['kind']=='explicit'),delivery_layer='扩展候选',event_type='joint_policy' if owner['kind']=='joint' else 'single_policy',
    connection_path=[],evidence=[evidence(full,a,b,'本句政策事实字面区间') for a,b in spans],previous_event_ids=[e.get('event_id','') for e in events],
    roles=dict(actors=owner['actors'],actions=[],targets=[],measures=parts))
   if len(parts)>1:z['text_parts']=parts;z['text_display_note']='省略号仅为展示，原文区间见text_parts'
   if owner['kind']=='joint':z['joint_participants']=owner['countries']
   for link in owner['connection']:
    ev=evidence(full,link['start'],link['end'],'同政策发布与主体连接');z['evidence'].append(ev)
    z['connection_path'].append(dict(from_text=text,to_text=link['text'],relation='当前执行条款→已发布政策→公共主体→国家',start=link['start'],end=link['end']))
   output.append(z);covered.extend(spans)
  if not output:return None
  merged=[]
  for a,b in sorted(covered):
   if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
   else:merged.append([a,b])
  cur=record['start']
  for a,b in merged+[[record['end'],record['end']]]:
   if cur<a:
    z=copy.deepcopy(base)
    for k in ['text_parts','optimized_attribution','s_scores','joint_participants']:z.pop(k,None)
    z.update(event_id=ident('F69-REM-',(record['file_id'],cur,a)),start=cur,end=a,text=full[cur:a],route=archive_route,countries=[],policy_state='',policy_level='unknown',connection_path=[],
     roles=dict(actors=[],actions=[],targets=[],measures=[]),evidence=[evidence(full,cur,a,reason)],reason=reason,final_fact_version=VERSION,final_fact_rule='remainder')
    output.append(z)
   cur=max(cur,b)
  return sorted(output,key=lambda e:(e['start'],e['end']))

 def refine(self,events,record,full,doc):
  from ..上下文与证据连接.linked_policy_resolution import resolve,apply_quality_reviews
  from ..政策内容判定.assertion_revision import recovery,audit
  from ..事实修补与补漏.literal_boundary import refine as literal_boundaries
  recovered=recovery(self,events,record,full,doc)
  if recovered is not None:return apply_quality_reviews(literal_boundaries(audit(recovered,full,self,doc),record,full,self),record,full,doc,self.quality_reviews)
  resolved=resolve(self,events,record,full,doc)
  if resolved is not None:return apply_quality_reviews(literal_boundaries(audit(resolved,full,self,doc),record,full,self),record,full,doc,self.quality_reviews)
  out=[]
  for e in events:
   # Range-only cleanup of unequivocal assessments also applies to old protected facts.
   # Preserve all prior ownership evidence; archive the literal remainder separately.
   if is_keep(e) and not e.get('text_parts'):
    tail=re.search(r'[，,](?=时机之巧妙|这无疑|吸引了)',e['text'])
    if tail and not re.search(r'如果|除非|只有|尚未',e['text'][:tail.start()]):
     cut=e['start']+tail.start();z=copy.deepcopy(e)
     z.update(event_id=ident('F69-TRIM-',(e['file_id'],e['start'],cut)),end=cut,text=full[e['start']:cut],final_fact_rule='literal_assessment_tail',final_fact_version=VERSION,previous_event_ids=[e['event_id']],reason=e.get('reason','')+'；单独归档明确评价/结果尾句')
     z['evidence']=[evidence(full,z['start'],z['end'],'保留的政策事实原文')]+e.get('evidence',[])
     rem=copy.deepcopy(e)
     for key in ['text_parts','optimized_attribution','s_scores','joint_participants']:rem.pop(key,None)
     rem.update(event_id=ident('F69-TAIL-',(e['file_id'],cut,e['end'])),start=cut,text=full[cut:e['end']],route='commentary',countries=[],policy_state='',policy_level='unknown',connection_path=[],roles=dict(actors=[],actions=[],targets=[],measures=[]),evidence=[evidence(full,cut,e['end'],'评价/效果原文')],reason='明确评价/效果尾句独立归档，不作为公共措施',final_fact_rule='literal_assessment_remainder',final_fact_version=VERSION)
     out.extend([z,rem]);continue
   if e.get('text_parts') and is_keep(e) and not e.get('fact_extraction_rule') and re.search(r'图\d+.{0,80}税费|法案草稿|拟订修改|正在讨论最新的.{0,15}法',e['text']):
    z=copy.deepcopy(e);z.update(route='draft',countries=[],policy_state='draft_or_proposal',policy_level='unknown',reason='FINAL_FACT：旧多片段仍含图注/明确法案草稿，保存原片段而从分析集隔离',final_fact_version=VERSION,final_fact_rule='legacy_multipart_draft_audit',previous_route=e['route']);out.append(z);continue
   # Preserve already verified multi-part facts and explicit national-local coordination.
   if e.get('text_parts') or (is_keep(e) and (e.get('fact_extraction_rule') in {'forecast_vs_published_target','own_country_quoted_commitment','reported_withdrawal_with_named_treaty'} or e.get('event_type')=='joint_policy' or e.get('coordination_scope') or e.get('national_policy_links'))):
    out.append(e);continue
   child=dict(record,start=e['start'],end=e['end'],text=full[e['start']:e['end']])
   out.extend(self._refine_piece([e],child,full,doc))
  return apply_quality_reviews(literal_boundaries(audit(out,full,self,doc),record,full,self),record,full,doc,self.quality_reviews)

 def _refine_piece(self,events,record,full,doc):
  if not events:return events
  if any(e.get('decision_origin')=='fixed_review_input' for e in events):return events
  a,b=record['start'],record['end'];t=full[a:b];before=full[max(0,a-1800):a];keep=any(map(is_keep,events))
  if not t.strip() or (not keep and not TOPIC.search(t) and not POLICY.search(t) and not re.search(r'该标准|这些地区|首先|其次|再次|最后|^同时|^我们也',t.strip())):return events
  proposals=[]
  # Existing law within an advice/campaign sentence: the outer recommendation is not adopted.
  m=re.search(r'((?:19|20)\d\d年的?(?:一项名为)?《[^》]{2,40}》(?:[（(][^）)]{1,35}[）)])?的?(?:法规|法律|法案))[^。]*?[，,](该法案规定[^。]+[。]?)',t)
  if m and TOPIC.search(m[2]):
   owner=self.ownership(m[1]+'，'+m[2],a+m.start(),full)
   jurisdiction={v['country'] for v in self.mentions(full[max(0,a-1200):a],max(0,a-1200)) if v.get('public') and v.get('level')!='local'}
   if not owner and re.search(r'联邦机构',m[2]) and ('美国' in full[:a] or jurisdiction=={'美国'}):owner=dict(countries=['美国'],actors=[],connection=[],basis='同篇美国联邦法案与机构的明确上下文',kind='linked')
   if owner:proposals.append(dict(parts=[(a+m.start(1),a+m.end(1)),(a+m.start(2),a+m.end(2))],state='execution_requirement',owner=owner,rule='existing_law_inside_advice',reason='恢复既有法律的规范条款，外层建议归档；条件与问责要求完整保留'))
  # A plainly stated tariff duration remains policy execution even inside an analyst's comparison.
  m=re.search(r'关税征收期为\d+年',t)
  if not proposals and m and re.search(r'美国.{0,100}关税|特朗普.{0,100}关税',full[:a],re.S):
   proposals.append(dict(parts=[(a+m.start(),a+m.end())],state='execution_requirement',owner=dict(countries=['美国'],actors=[],connection=[],basis='同篇美国光伏关税及本句征收期限',kind='linked'),rule='tariff_duration',reason='单独保留已经说明的关税期限，不纳入企业竞争预测'))
  if proposals:return self.emit(record,events,full,proposals) or events
  proposals=nested_recoveries(self,events,record,full,doc,COUNTRY)
  if proposals:return self.emit(record,events,full,proposals) or events
  if not keep and events[0]['route'] in {'noise','quality_unknown','local_policy','local_execution','campaign','draft','discussion','commentary','private_reaction','background'}:
   anchor=self.anchor(t,a,full)
   pure_execution=bool(anchor and TASK.search(t) and re.search(r'该标准|该法案|这些地区|根据该规划|根据计划|^(?:\s*首先|\s*其次|\s*再次|\s*最后|\s*一是|\s*二是|\s*我们也寻求)',t))
   court=bool(re.search(r'法院.{0,20}(?:暂时叫停|暂缓实施|否决|裁定)',t) and TOPIC.search(t))
   current_rel=self.roles.relation(t,a) if PUBLIC.search(t) and FORMAL.search(t) and TOPIC.search(t) else {'events':[]}
   current_published=bool(current_rel['events'] and not self.nonpolicy(t,a,full))
   current_incumbent=bool(re.search(r'(?:政府|总统)[^。]{0,25}宣布[^。]{0,160}(?:兑现|履行)竞选承诺|(?:总统|政府)[^。]{0,15}上任以来[^。]{0,25}实施',t) and not self.nonpolicy(t,a,full))
   if not pure_execution and not court and not current_published and not current_incumbent:return events
  # Evaluate each existing literal child, including previously rejected public task clauses.
  candidates=events
  changes=False;archive_decision=None
  for child in candidates:
   if child.get('text_parts'):continue
   x,y=child['start'],child['end'];text=full[x:y]
   # Strip only observable media introductions, title copies, metadata and signatures.
   prefixes=list(re.finditer(r'【[^】]{0,80}(?:报道|消息|日讯)[^】]{0,60}】|(?:新华社[^。]{0,35}电[（(][^）)]{0,20}[）)]|据(?:新华社|路透社|世界天然气|美国有线电视新闻网)[^，。]{0,30}(?:报道|消息称)|韩联社[^，。]{0,20}消息|北极星[^，。]{0,15}网讯)[，,：:]?',text))
   if prefixes and prefixes[0].start()<80:x+=prefixes[0].end();text=full[x:y];changes=True
   title=doc.get('analysis_title',doc.get('title','')).strip()
   if len(title)>7 and text.startswith(title):x+=len(title);text=full[x:y];changes=True
   if not text.strip() and changes:archive_decision=('introduction','','标题或媒体前缀单独归档，不能代替正文政策证据');continue
   # Locate an explicit policy actor after a noisy headline/lead, not after a condition.
   lead=re.search('('+COUNTRY+r')(?:政府|总统|国会|内阁|能源部|经济产业省|首相|总理)',text)
   if lead and lead.start()>0 and re.search(r'原标题|来源|\||#|讯|标题|计划.*计划',text[:lead.start()]) and not re.search(r'如果|除非|不再|只有',text[:lead.start()]):x+=lead.start();text=full[x:y];changes=True
   # Separate opposite public actions; the second action may inherit the same explicit actor.
   split=[m.start() for m in re.finditer(r'[，,](?=(?:还|并|同时)?(?:批准了|批准|承诺|正式退出|取消了|废除了|解除禁止|中国则|日本在|美国自|美国和中国))',text)]
   # A closing policy title followed immediately by a different dated public act is
   # an observable source splice. Retain both literal facts separately, with no invented date.
   glued=[m.end() for m in re.finditer(r'》(?=(?:20\d\d年)?\d{1,2}月\d{1,2}日[，,](?:[^。]{0,12}政府|'+COUNTRY+r'(?:总统|首相|总理))[^。]{0,15}(?:公布|发布|宣布))',text)]
   boundaries=sorted([(p,1) for p in split]+[(p,0) for p in glued])
   chunks=[];cur=0
   for point,skip in boundaries+[(len(text),0)]:chunks.append((cur,point));cur=point+skip
   last_owner=None
   for lo,hi in chunks:
    sub=text[lo:hi];sx=x+lo;sy=x+hi
    if not sub.strip():continue
    block=self.nonpolicy(sub,sx,full)
    # Specific already-adopted goal inside an effect comparison.
    gm=re.search(r'(?:此前)?(?:奥巴马|[^，。]{1,8})政府制定的20\d\d年减排\d+[%％]的计划',sub)
    if block and gm:
     owner=self.ownership(gm.group(),sx+gm.start(),full,child)
     if owner:proposals.append(dict(parts=[(sx+gm.start(),sx+gm.end())],state='announced_goal',owner=owner,rule='prior_goal_inside_forecast',reason='比较中的已制定政府目标单独保留，媒体预测不保留'));changes=True
     continue
    if block:archive_decision=block;changes=True;continue
    # Forecast/market/comparison tails are not part of the adopted measure.
    tail=re.search(r'[，,；;](?=(?:有望|预计|吸引了|时机之巧妙|这无疑|使得(?![^，。]{0,22}(?:有资格|符合条件|抵免|税率|补贴金额))|并创造|这将|而这|时机之|几乎翻了|引起轩然|给世人|行业装机量|政策有望|从而为企业|带动.{0,8}就业|分析师|专家认为|相信拜登|导致(?:某|该|一家)?(?:公司|企业)))',sub)
    if tail and not re.search(r'如果|除非|只有|在不影响',sub[:tail.start()]):sy=sx+tail.start();sub=full[sx:sy];changes=True
    if re.search(r'特朗普政府还试图撤销|国会拒绝|提出了负担得起',sub) and not FORMAL.search(sub):archive_decision=('draft','draft_or_proposal','未采纳的替代/削减安排');changes=True;continue
    owner=self.ownership(sub,sx,full,child) or last_owner
    anchor=self.anchor(sub,sx,full)
    rel=self.roles.relation(sub,sx) if PUBLIC.search(sub) and TOPIC.search(sub) else {'events':[]}
    direct=bool(PUBLIC.search(sub) and ((FORMAL.search(sub) and rel['events']) or re.search(r'法院.{0,20}(?:叫停|暂缓|暂停|否决|裁定)|发表.{0,12}碳中和宣言|(?:表示|声明称)[，,：:]?(?:政府)?将.{0,20}(?:扶持|支持|投资|关闭|拨款|投入)|由国务院.{0,70}共同出资组建|正式通过|国务会议[^。]{0,25}确定|发出.{0,20}开发意向书|(?:总统|政府)[^。]{0,15}上任以来[^。]{0,25}实施|根据.{0,12}政府规划',sub)) and TOPIC.search(sub))
    named=bool(re.search(r'政府制定的|政府发布的|政府最重要的.{0,12}(?:政策|扶持)|政府的激励计划|政府通过提供税收优惠',sub) and TOPIC.search(sub))
    country_plan=bool(re.search('('+COUNTRY+r')(?:政府)?(?:(?:今年|近日|此前|于20\d\d年|在20\d\d年))?(?:将|正在|计划|承诺|制定|设定|宣布)',sub) and TOPIC.search(sub) and ACTION.search(sub))
    execution=bool(anchor and TASK.search(sub) and (TOPIC.search(sub) or re.search(r'该标准|这些地区|该项目|根据该规划|根据计划|我们也寻求|将保留|有资格|根据.+政府规划',sub)))
    linked_declaration=bool(anchor and PUBLIC.search(sub) and FORMAL.search(sub) and re.search(r'这项计划|该计划|这一战略|上述方案',sub))
    country_structure=bool(re.search('(?:'+COUNTRY+r')(?:的)?(?:气候变化减缓|碳中和|能源转型|可再生能源)[^，。]{0,10}(?:计划|战略|规划)(?:基于|包括|提出|明确)',sub))
    kept_specific=bool(keep and TOPIC.search(sub) and (FORMAL.search(sub) or re.search(r'法规|补贴|拨款|税收抵免|关税|标准|目标|政策|战略|规划|计划|声明包括|共同出资组建',sub)))
    if LOCAL.search(sub) and not (owner and (any(m.get('public') and m.get('level')=='national' for m in owner['actors']) or re.search(r'联邦政府(?:机构|层面)?[^。]{0,100}(?:出台|授权|签署|制定)|指示联邦政府机构',sub))):archive_decision=('local_policy','','地方自主政策单列');changes=True;continue
    if (direct or named or country_plan or execution or kept_specific or linked_declaration or country_structure) and owner:
     st=self.state(sub,next((e.get('policy_state','') for e in events if is_keep(e)),'announced_plan'))
     if st!='announced_review' and re.search(r'该标准|适用于|不包括|必须|不得|征收期',sub):st='execution_requirement'
     proposals.append(dict(parts=[(sx,sy)],owner=owner,state=st,rule='current_fact_or_published_execution',reason='当前具体公共动作或已发布同政策的执行任务；状态与本动作绑定'))
     last_owner=owner
    elif keep and not TOPIC.search(sub) and events[0].get('policy_content_contract',{}).get('public_fact') and not block:
     return events
    elif keep and (PRIVATE.search(sub) or not TOPIC.search(sub) or re.search(r'表示|认为|目标|政策|战略',sub)):
     archive_decision=('content_uncertain','','原保留记录缺少当前具体公共措施；不以旧国家证据替代内容');changes=True
    elif not keep:continue
  if proposals:
   # Only replace the old chain when text/state/country improved or an omitted fact is recovered.
   oldkept=[e for e in events if is_keep(e)]
   same=len(proposals)==len(oldkept) and all(p['parts']==[(e['start'],e['end'])] and p['state']==e['policy_state'] and p['owner']['countries']==e['countries'] for p,e in zip(proposals,oldkept))
   if same and not changes:return events
   return self.emit(record,events,full,proposals,archive_decision[0] if archive_decision else 'commentary') or events
  if archive_decision and keep:
   route,state,why=archive_decision;out=[]
   for e in events:
    z=copy.deepcopy(e)
    if is_keep(z):z.update(route=route,policy_state=state,countries=[],policy_level='unknown',reason='FINAL_FACT：'+why,final_fact_version=VERSION,final_fact_rule='content_rejection')
    out.append(z)
   return out
  return events
