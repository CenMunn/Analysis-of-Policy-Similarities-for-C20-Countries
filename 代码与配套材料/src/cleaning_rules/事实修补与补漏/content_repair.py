"""V7.2 原文区间修补。国家分数不作公共政策判定，所有新增结果仍为候选。"""

import copy,hashlib,re

from ..主体与国家归属.national_scope import TOPIC as OLD_TOPIC,INSTRUMENT,ACTION,AUTHORITIES,evidence

from ..政策内容判定.quality_rules import risk_flags as old_flags

VERSION='policy-remediation-20261023.7.2.2'

TOPIC=re.compile(OLD_TOPIC.pattern+r'|生物燃料|生物质|减少用电|低能耗|碳管理|碳强度|CO2|二氧化碳零排放|先进技术汽车制造|电池制造|电池生产|摆脱.{0,8}石油.{0,5}依赖')

MEASURE=re.compile(INSTRUMENT.pattern+r'|零排放|加收|贷款|资助|关停|指导方针|行动计划|城中城|退役|节约.{0,10}电力|基础设施|技术攻关|光伏电站|加快|推广|加氢站')

FORMAL=re.compile(r'宣布|发布|公布|批准|通过|签署|签订|制定|设定|确定|决定|规定|提出|承诺|提供|启动|实施|推行|调整|征收|加收|计划|要求|投入|投资|支持|关停|停止|结束|结束|加快|加强|提高|降低|减少|选定|包括')

OFFICIAL=re.compile(r'政府|总统|首相|总理|国会|议会|内阁|能源部|环境部|环境省|经济产业省|农林水产省|财政部|白宫|国务院|王储|国家主席|联邦经济部|REPDO')

EXTRA={'中国':['胡锦涛'],'韩国':['朴槿惠','韩国能源部'],'日本':['农林水产省'],
       '德国':['联邦经济部'],'沙特阿拉伯':['沙特可再生能源项目开发办公室','REPDO','沙特王储','Mohammed Bin Salman']}

BAD_STATES={'campaign','draft_or_proposal','discussion','not_adopted'}

def quality_flags(text):
    flags=[x for x in old_flags(text) if x!='只有政策标题，没有措施断言']
    # 匹配一对完整书名号，而不是任意开引号与闭书名号。
    if re.fullmatch(r'\s*《[^《》]+》[。；;]?\s*',text):
        flags.append('只有政策标题，没有措施断言')
    return flags

def fact_parts(t):
    """返回覆盖完整原文的互不重叠区间；删除片段也单独归档。"""
    cuts={0,len(t)};forced=[]
    m=re.search(r'^[^。；]{0,60}[（(]图片来源[：:][^）)]{1,100}[）)]',t)
    if m:cuts.add(m.end());forced.append((0,m.end(),'noise'))
    m=re.match(r'^\s*(?:\|\|+|摘要[：:]|中国经济周刊-经济网讯\s*据央视财经[，,]?)\s*',t)
    if m:cuts.add(m.end());forced.append((0,m.end(),'introduction'))
    tail=re.search(r'[，,](?=(?:分析师|分析人士|专家(?:认为|预计)|支持者(?:则)?认为|研究人员认为|意味着|这将(?:带动|导致)|有望(?:带动|通过)|预计(?:将)?(?:创造|带动|增加就业)))',t)
    if tail and FORMAL.search(t[:tail.start()]):
        cuts.add(tail.start());forced.append((tail.start(),len(t),'commentary'))
    points=sorted(cuts)
    return [(a,b,next((kind for x,y,kind in forced if x<=a and b<=y),None)) for a,b in zip(points,points[1:]) if a<b]

def state_signal(t,context=''):
    actual=re.search(r'已经|已于|已在|正式|开始|目前仍|目前已|此前曾',t)
    adopted=re.search(r'(?:已经|已|正式)?(?:宣布|批准|通过|签署|签订|公布|发布|制定|决定)',t)
    if re.search(r'竞选|候选人|若当选|如果当选|候任|辩论中',t):return 'campaign'
    if re.search(r'竞选期间|竞选团队|选举团队|竞选宣言|一旦当选|(?:计划|打算|承诺|将)在.{0,8}上任头[一二三十百\d]+天',context) and not re.search(r'就任后|上台后|上任后.{0,8}(?:已|正式)|政府(?:宣布|公布|发布)',t):return 'campaign'
    if re.search(r'(?:正在考虑|正探索制定|考虑将|研究三种|备选方案)|主张.{0,55}(?:必须要有|碳税)',t) and not re.search(r'已(?:通过|批准|决定|实施)',t):return 'discussion'
    if re.search(r'将(?:于[^，。；]{0,15})?(?:正式)?(?:签署|签订|取消|撤销|废除|公布|发布)',t) and not re.search(r'(?:已|正式)(?:宣布|决定|批准)|政府宣布|总统宣布',t):return 'draft_or_proposal'
    if re.search(r'将于[^，。；]{0,16}(?:开始)?(?:实施|生效|施行)',t):return 'scheduled_implementation'
    if all(re.search(p,t) for p in ['检讨|审查','撤销|废除','暂停|冻结']):return 'multiple_action_states'
    if re.search(r'规定.{0,20}(?:如果|若|符合)|(?:如果|若)(?:符合|未满足|满足).{0,40}(?:补贴|申请|不得|可获)',t):return 'conditional_arrangement'
    if re.search(r'如果|倘若|假设|情景[一二三四\d]|备选路径',t):return 'discussion'
    if re.search(r'(?:政府|内阁|总统|首相|能源部).{0,16}(?:仍未决定|尚未决定|未决定)|没有(?:通过|采纳|宣布)|尚未(?:批准|通过|生效)|仍未(?:批准|通过)',t):return 'not_adopted'
    if re.search(r'(?:国会|议会|参议院|众议院).{0,12}(?:已经|已|正式)?通过',t) and not re.search(r'委员会|预计|计划|如果|尚未|拟',t):return 'legislative_passage'
    if re.search(r'起草|研拟|草案|征求意见|通知草案|提交.{0,18}法案|委员会.{0,18}(?:推进|提出)|尚待.{0,15}批准',t):return 'draft_or_proposal'
    if '提案' in t and not re.search(r'批准|已通过|正式生效',t):return 'draft_or_proposal'
    if re.search(r'方案|协议|战略|目标|计划|标准',t) and re.search(r'内阁.{0,12}(?:预计|将).{0,12}批准|尚待.{0,12}批准|形成通知草案|将于周.{0,5}公布(?:该|这一|战略)|如果获批',context):return 'draft_or_proposal'
    if re.search(r'要求.{0,18}(?:重新审查|重新审核|评估|修改或废除)|研究.{0,10}(?:路径|选项)',t):return 'announced_review'
    if re.search(r'(?:宣布|决定|承诺).{0,12}退出',t):return 'announced_withdrawal'
    if re.search(r'(?:宣布|决定|已).{0,8}(?:重返|重新加入)',t):return 'announced_reentry'
    if re.search(r'(?:将于|计划在|计划到|将在)[^。；]{0,22}(?:结束|停止|关闭|退役|淘汰)|(?:停止|结束).{0,20}(?:新资金|补贴)|(?:禁售|禁止销售).{0,15}燃油',t):return 'announced_phaseout'
    if re.search(r'(?:已经|已|正式).{0,12}(?:取消|废除|撤销|退出|终止)',t):return 'cancelled_or_withdrawn'
    if re.search(r'暂停|暂缓|冻结',t):return 'suspended'
    if re.search(r'(?:已经|已|正式|开始).{0,16}(?:生效|施行|实施|执行)|自.{0,12}起施行|(?:已|已经)投资|目前已建成',t):return 'implementation'
    if re.search(r'将[^。；]{0,15}(?:公布|宣布|出台|发布)|拟(?:取消|废除|退出)',t) and not adopted:
        if re.search(r'(?:总统|首相|总理|政府).{0,30}(?:演讲|公开).{0,12}表示',t) and re.search(r'加强|增加|支持|减排|研发',t):return 'announced_plan'
        return 'discussion'
    if re.search(r'建议|呼吁|力劝|研究显示|估算|预计|有望|可能|敦促',t) and not adopted and not re.search(r'根据.{0,30}(?:政府|规划|计划)|政府计划|总统.{0,20}(?:计划|提供)',t):return 'discussion'
    if re.search(r'投资|基金|贷款担保|拨款|财政支出',t) and (adopted or re.search(r'政府计划|总统',t)):
        return 'announced_funding_plan'
    if re.search(r'申请|符合条件|每户|每辆|不适用于|配额|有义务',t):return 'execution_requirement'
    if re.search(r'(?:到|在)20\d\d年[^。；]{0,35}(?:达到|实现|提高|增加|减少|占比|安装)|目标|碳中和|净零|零排放',t):return 'announced_goal'
    if re.search(r'战略|愿景',t) and adopted:return 'announced_strategy'
    if re.search(r'计划|规划|路线图|方案',t):return 'announced_plan'
    return 'announced_or_adopted'

def candidate_gate(t,context=''):
    if not t.strip() or len(t)>3000:return False
    topic=bool(TOPIC.search(t))
    # 门只找待判候选，不在此归国或判通过。
    return bool((topic and (MEASURE.search(t) or FORMAL.search(t))) or
                (TOPIC.search(context) and re.search(r'该(?:计划|项目|公司|措施)|这(?:一|项)|根据|补贴|贷款|生物燃料|减少用电',t) and (MEASURE.search(t) or FORMAL.search(t))))

def content_veto(t,state,context=''):
    if re.search(r'下列句子|标点符号|选择题|\(\d+分\)|产业全球周报|微信公众号|点击量|^相关阅读',t):return 'noise','题库、导航或网页模板'
    if re.search(r'这些城市|市长|地方政府|州政府|威尼斯政府',t) and not re.search(r'联邦政府|中央政府|落实国家|(?:中国|日本|韩国|美国|德国|法国|英国)政府.{0,70}(?:与地方|和地方|地方政府)',t):return 'local_policy','地方自主承诺或措施'
    if re.search(r'金融机构将停止|银行宣布停止',t) and not re.search(r'政府(?:规定|要求|禁止)|央行(?:规定|要求)',t):return 'private_project','金融企业自主投融资安排，没有公共强制要求'
    if re.search(r'可以预计|可能还只是一个开始|让市场普遍担忧|发展步伐已明显加快|政策启示|政策经过多年的发展|应该能鼓励|研究也不足以满足',t):return 'commentary','政策启示、概括评价或预测，非当前公共措施断言'
    if re.search(r'^科学常见问题|唿吁美国减少碳排放当全球',t):return 'quality_unknown','栏目串入正文且句子截断，保留原文待恢复'
    if re.search(r'远程医疗|电子信息供应商|核武器|钚库存|核武研究',t) and not re.search(r'节能|减碳|减排|脱碳|清洁能源|可再生能源',t):return 'out_of_scope','当前条款是医疗、一般数字化或核安保，不能继承邻近气候条款'
    if state in BAD_STATES:
        return ('campaign' if state=='campaign' else 'draft' if state=='draft_or_proposal' else 'discussion'),'待采纳、竞选、假设或讨论状态单列'
    if re.search(r'(?:专家|分析师|智库|咨询机构|公司|企业).{0,35}(?:认为|建议|呼吁|力劝|预计|估算)|(?:公司|企业).{0,18}发表声明',t) and not re.search(r'政府.{0,15}(?:已经|已)(?:采纳|批准)',t):return 'commentary','第三方建议、评论或预测，没有政府采纳断言'
    if re.search(r'委员会.{0,40}发布报告|引发.{0,10}(?:竞争|争议)|加剧.{0,15}竞争|是.{0,12}(?:有力手段|主要途径)|带来.{0,12}压力|创造.{0,10}工作岗位|预计.{0,12}销量|意味着|杂志认为|最高碳排放强度降幅',t):return 'commentary','主断言是报告建议、解释或效果评价'
    if re.search(r'全球.{0,20}气温|要求各国制定|缔约方大会确定',t) and not re.search(r'政府|签订|签署|退出|批准|加入',t):return 'international_framework','全球框架不分配为某一国家政策'
    if re.search(r'碳中和元年|演讲要点$|作者[：:]|参观.{0,30}(?:公司|业务)|计划前往',t):return 'introduction','标题、人物行程或引导概述'
    return None,''

class RepairEngine:
    def __init__(self,scope):
        self.scope=scope
        for c,aliases in EXTRA.items():
            self.scope.authorities.update({n:c for n in aliases})
        self.scope.ap=re.compile('|'.join(map(re.escape,sorted(self.scope.authorities,key=len,reverse=True))))

    def actors(self,t,offset=0):
        out=[]
        for m in self.scope.mentions(t,offset):
            if not m.get('public') or m.get('level')=='local':continue
            a=m['start']-offset;b=m['end']-offset
            if re.search(r'对|针对|向|来自|效仿',t[max(0,a-4):a]):continue
            tail=t[b:];stop=re.search(r'[。；;]',tail)
            tail=tail[:stop.start()] if stop else tail
            if FORMAL.search(tail[:90]) or re.search(r'的.{0,16}(?:规划|计划|战略|目标)',tail[:25]):out.append(m)
        return out

    def connection(self,t,a,full):
        prior=full[max(0,a-500):a];base=a-len(prior)
        choices=[]
        for m in re.finditer(r'[^。！？\n]+[。！？\n]?',prior):
            s=m.group();acts=self.actors(s,base+m.start());cs=sorted({x['country'] for x in acts})
            if len(cs)!=1 or not TOPIC.search(s) or state_signal(s) in BAD_STATES:continue
            if re.search(r'专家|分析师|竞选|背景介绍|相比之下',s):continue
            choices.append((s,base+m.start(),base+m.end(),acts,cs))
        if not choices:return None
        # 只给显式承接/执行信息继承；邻近本身不是足够条件。
        if not re.search(r'^(?:[“\s]*)(?:该|这|但考虑|要|其中|同时|此外|另外|根据|按照|为了)|补贴|FIT|贷款|根据|负责|碳中和\+',t):return None
        countries={c for s,x,y,acts,cs in choices for c in cs}
        if len(countries)!=1:return None
        return choices[-1]

    def revise(self,old,full,doc):
        if old.get('review_no') is not None:return [copy.deepcopy(old)]
        a,b=old['start'],old['end'];t=full[a:b]
        if old.get('text_parts'):return [copy.deepcopy(old)]
        assert t==old['text']
        out=[]
        for x,y,forced in fact_parts(t):
            e=copy.deepcopy(old);s=t[x:y];start=a+x;end=a+y
            before=full[max(0,start-220):start];after=full[end:end+180]
            context=before+'\n'+after
            e.update(event_id='R72-'+hashlib.sha256(f"{old['file_id']}:{start}:{end}:{old.get('event_id',old.get('segment_id',''))}".encode()).hexdigest()[:20],
                     start=start,end=end,text=s,algorithm_version=VERSION,
                     previous_event_ids=[old.get('event_id',old.get('segment_id',''))],
                     previous_routes=[old.get('route',old.get('category',''))],
                     human_confirmation='',reviewer='',review_provenance='本轮规则重判；未写成人工确认')
            e.setdefault('evidence',[]);e.setdefault('connection_path',[])
            e.setdefault('roles',{'actors':[],'actions':[],'measures':[],'targets':[]})
            e.setdefault('countries',[]);e.setdefault('policy_level','unknown')
            e['evidence']=[evidence(full,start,end,'当前原文，不补写事实')]
            e['split_parent']={'start':a,'end':b,'original_event_id':old.get('event_id',old.get('segment_id',''))}
            if forced:
                e.update(route=forced,reason='V7.2原文拆分：图注/引导或效果尾句单独归档',countries=[]);out.append(e);continue
            state=state_signal(s,context);veto,why=content_veto(s,state,context)
            e['policy_state']=state
            e['implementation_claim']='只保留原文状态；宣布、未来执行、正式实施与撤销分开'
            if veto:
                e.update(route=veto,reason='V7.2内容与状态分流：'+why)
                if veto=='local_policy':e['policy_level']='local'
                out.append(e);continue
            flags=quality_flags(s)
            if flags:
                e.update(route='quality_unknown',reason='V7.2质检：'+'；'.join(flags));out.append(e);continue
            acts=self.actors(s,start);cs=sorted({m['country'] for m in acts})
            topical=bool(TOPIC.search(s));anchor=None
            if len(cs)!=1 or not topical:
                anchor=self.connection(s,start,full)
                if anchor and (not cs or cs==anchor[4]):
                    an,aa,ab,am,ac=anchor;cs=ac;acts=am;topical=topical or bool(TOPIC.search(an))
                    e['connection_path']=[{'from_text':s,'to_text':an,'relation':'同政策承接或执行信息→前文公共主体'},
                                          {'from_text':an,'to_text':'；'.join(cs),'relation':'公共主体→国家'}]
                    e['evidence'].append(evidence(full,aa,ab,'同政策承接锚点'))
            actual_measure=bool(MEASURE.search(s) and FORMAL.search(s))
            prior_keep=old.get('route','').startswith('main_')
            recoverable=old.get('route') in {'content_uncertain','out_of_scope','subject_unknown','discussion','delivery_quarantine','legacy_excluded'}
            if topical and actual_measure and len(cs)==1 and recoverable:
                # 主体是研究者/企业、地方或未采纳状态时，前面的分流已阻断。
                if re.search(r'公司|企业|集团',s[:45]) and not (OFFICIAL.search(s) or re.search(r'根据.{0,35}(?:法案|政策|规定).{0,25}(?:获|贷款|补贴)',s)):
                    e.update(route='private_project',reason='V7.2企业自主安排，无明确公共工具')
                elif old.get('policy_level')=='local':
                    e.update(route='local_policy',reason='沿用地方独立政策层级，不因国家连接提档')
                else:
                    e.update(route='main_explicit',countries=cs,policy_level='national',
                             reason='V7.2补漏：双碳主题＋公共主体动作＋措施/执行内容；保留原状态',
                             country_basis='原文公共主体关系' if not anchor else '带原文区间的同政策承接',
                             delivery_layer='扩展候选',newly_recovered=True)
                    e['roles']['actors']=acts
            elif prior_keep:
                e['route']=old['route'];e['delivery_layer']=old.get('delivery_layer','扩展候选')
                e['reason']='V7.2通过本轮阻断与原文范围检查；'+old.get('reason','')
            elif old.get('route')=='delivery_quarantine':
                e.update(route='content_uncertain',reason='V7.2已修复模板/标题误拦，公共主体或措施证据仍不足')
            else:e.setdefault('route','content_uncertain')
            e['evidence_dimensions_v72']={
                'content':'公共措施候选' if e['route'].startswith('main_') else '未纳入',
                'country':'同政策上下文' if anchor else '原文明确关系' if cs else '沿用待核或未知',
                'level':e['policy_level'],'state':state,
                'confidence_is_calibrated_probability':False}
            out.append(e)
        return out
