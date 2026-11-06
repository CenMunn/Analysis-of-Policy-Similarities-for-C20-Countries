"""内容合约不含国家或S分数；国别层不能把连接证据当成公共政策证据。"""
from dataclasses import dataclass,asdict
import copy,re
from ..主体与国家归属.national_scope import G20,TOPIC,LOCAL_WORDS,NATIONAL_SCOPE,evidence
from ..主体与国家归属 import national_scope
from ..事实修补与补漏.content_repair import state_signal
from ..主体与国家归属.optimized_attribution import policy_topic,PUBLIC_TOOL,generic_actor,score_candidates,eligible
from ..主体与国家归属.scoped_roles import VERBS,ADVERBS,VERSION as ROLE_VERSION
from ..政策内容判定.current_assertion_guard import assertion_exclusion,platform_context,prediction_tail
from ..事实修补与补漏.event_fact_parts import split_contextual_facts

VERSION='CM-PACE-interface-roles-20261026.6.8-nested-facts'
BAD={'campaign','draft_or_proposal','not_adopted','discussion','proposed_change','conditional_proposal'}
GENERIC_ACT=re.compile(r'(?:联邦政府|中央政府|政府|总统|首相|总理|内阁|能源部|财政部|产业部)[^。；，,]{0,26}(?:宣布|公布|发布|决定|制定|设定|提供|给予|允许|授权|规定|要求|计划|承诺|推出)')
TOOL=re.compile(PUBLIC_TOOL.pattern+r'|关税|碳(?:排放权)?定价|(?:投入|投资|提供|拨付|出资).{0,10}[\d.]+(?:亿|万).{0,4}(?:英镑|美元|韩元|日元|元)|第[\d０-９]+号命令|公共指令|新能源(?:汽车)?(?:发展)?规划|能源(?:转型|基本|发展)?计划|能源方案|绿色增长战略|碳中和.{0,15}目标|净零.{0,15}目标|清洁能源.{0,15}计划|太阳能.{0,20}项目|氢能.{0,15}战略|(?:去碳化|脱碳)路线图')
EXEC=re.compile(r'必须|不得|依法|截止日期|提交.{0,10}注册|有义务|配额|每户|每辆|补贴|税率|抵扣|抵免|认证制度|采购|占比|比例|发电量')
POLICY_REF=re.compile(r'该(?:计划|政策|方案|战略|法律|规定|通知)|这项(?:法律|政策)|根据.{0,25}(?:法案|法律|计划|规划)|按照.{0,25}(?:规定|计划)')
QUANTIFIED_GOAL=re.compile(r'到\s*20\d\d年[^。；;]{0,130}(?:普及|建成|部署|实现|提高|降低|减少|达到)[^。；;]{0,45}\d[\d.]*\s*(?:[%％]|万辆|万座|座|万吨|亿吨|吉瓦|GW)')

def current_plan_confirmation(text,before):
    """只取消被明确现行规划连接覆盖的旧竞选标签，不把候选人自称最新计划当采纳。"""
    return bool(re.match(r'根据[^，。；]{2,22}(?:这份|最新)[^，。；]{0,8}能源计划',text.strip()) and QUANTIFIED_GOAL.search(text)
        and re.search(r'这在该国最新的能源计划中也?得到了体现[。]?\s*$',before)
        and not re.search(r'草案|尚未|仍未|未通过|未批准|未获|拟议',before[-450:])
        and not re.search(r'草案|尚未|若|如果|拟议|竞选|候选人',text))

@dataclass(frozen=True)
class ContentContract:
    public_fact:bool
    topical:bool
    national_evidence:bool
    state:str
    kind:str
    decision:str
    reason:str
    uses_context:bool=False

class PolicyBoundary:
    def __init__(self,content_scope,role_scope):
        self.content_scope=content_scope;self.role_scope=role_scope
        if not hasattr(content_scope,'assess') or hasattr(role_scope,'assess'):raise TypeError('内容与归属接口必须分离')

    def content_contract(self,text,before=''):
        t=text.strip()
        # 明示国家小节切换使旧小节的草案/竞选状态失效，不把日本研究预算传给英国措施。
        headings=list(re.finditer(r'(?:中国|美国|日本|韩国|德国|法国|英国|巴西|印度尼西亚)[：:]',before))
        state_before=before[headings[-1].start():] if headings else before
        same_goal_year=bool(set(re.findall(r'20\d\d',t))&set(re.findall(r'20\d\d',state_before)) and re.search(r'草案|征求意见|尚待批准',state_before) and re.search(r'计划|目标',t))
        linked_goal=bool(QUANTIFIED_GOAL.search(t) and re.search(r'政府.{0,12}(?:计划|规定|要求)',t) and re.search(r'(?:敲定|公布|发布|出台|通过)[^。；;]{0,55}(?:规划|战略|计划|路线图)',state_before[-450:]))
        state_context=state_before if POLICY_REF.search(t) or same_goal_year or linked_goal or re.match(r'^(?:同年[，,]?)?(?:政府|该政府|该国|他|她|我们|计划)',t) else ''
        state=state_signal(t,state_context)
        exclusion=assertion_exclusion(t)
        if exclusion:
            route,status,reason=exclusion
            return ContentContract(False,policy_topic(t),False,status or state,route,route,reason)
        plan_confirmed=current_plan_confirmation(t,before)
        if plan_confirmed and state=='campaign':state=state_signal(t,'')
        rel=self.role_scope.relation(text,0)
        # 引用链接/括号中的宣布不构成外层当前句的公共动作。
        parens=list(re.finditer(r'[（(][^（）()]*[）)]',text))
        current_events=[e for e in rel['events'] if not any(p.start()<=e['action']['start']<p.end() for p in parens)]
        coordination=[e for e in current_events if e.get('national_local_coordination')]
        if any(e.get('independent_current_policy') for e in coordination):
            # 当前句交代另一份已明确内容的具名路线图，不继承邻近经济预算草案状态。
            same_named=any(e.get('policy_name') and e['policy_name'] in before[-900:] for e in coordination) or bool(re.search(r'(?:该|这份|上述)路线图[^。；;]{0,25}(?:草案|尚待批准|尚未通过)',before[-450:]))
            state_context=before if same_named else '';state=state_signal(t,state_context)
        lexical_actors=[m for e in current_events for m in e['actors'] if m.get('public') and m.get('level')!='local']
        action_verbs={e['action']['text'] for e in current_events}
        generic=generic_actor(text)
        local_generic=bool(generic and any(m.get('level')=='local' and m['start']<=generic.start()<m['end'] and any(name in m['text'] for values in national_scope.REGIONS.values() for name in values) for m in rel['mentions']))
        if local_generic:generic=None
        lexical_public=bool(lexical_actors) or bool(generic and GENERIC_ACT.search(text[generic.start():]))
        pronoun_public=bool(re.search(r'(?:^|[，,“”])\s*(?:该国|他|她|我们)(?:还|也|将|公开|正式|一直|正在){0,6}(?:宣布|推行|承诺|规定)',t[:55]) and re.search(r'政府|总统|首相|总理|国会|签署.{0,15}(?:计划|协议)',before))
        lexical_public=lexical_public or pronoun_public
        tooling=bool(TOOL.search(text) or QUANTIFIED_GOAL.search(text) or (coordination and re.search(r'充电(?:桩|站|基础设施)',text)) or re.search(r'(?:国家自主贡献|NDC).{0,30}目标',text))
        tooling=tooling or any(e.get('coordination_kind')=='national_rule_local_execution' for e in coordination)
        tooling=tooling or bool(re.search(r'(?:退出|重返|加入).{0,12}(?:巴黎|气候).{0,12}(?:协定|协议)',t))
        formal_country_plan=any(e['action']['text'] in {'推出','公布','宣布','制定','发布'} and any(m.get('role')=='country_candidate' for m in e['actors']) for e in current_events) and bool(re.search(r'[\u4e00-\u9fff]{2,12}计划',text))
        tooling=tooling or formal_country_plan
        # 真正的当前动作与工具先独立判定；不能通过国家或连接分来改变这些布尔量。
        explicit=lexical_public and tooling and bool(action_verbs or GENERIC_ACT.search(text))
        explicit=explicit or bool(formal_country_plan) or bool(pronoun_public and tooling)
        explicit=explicit or bool(rel['joint'] and rel['events'] and re.search(r'合作|协议|备忘录|倡议',text))
        if re.search(r'七日年化|活期理财|股市.{0,10}涨|(?:每日推荐|要闻频道|股票频道)',text) or (len(re.findall(r'-\s+',text))>=2 and re.search(r'业绩|逆势上扬|市值|半导体',text)):
            return ContentContract(False,False,False,state,'noise','noise','网页推荐/理财标题拼接，不能用其中机构补归属')
        if re.match(r'\s*(?:\d{4}年)?(?:欧洲|欧美|欧元区|欧亚)(?:确定|宣布|实施|推出)',t):
            return ContentContract(False,policy_topic(t),False,state,'unresolved_region_actor','subject_unknown','主语是地理区域，不能继承前文某个国家；需核对具体施策者')
        if re.search(r'(?:政府|总统|首相)[^，,。；]{0,15}(?:宣布|公布)[^，,。；]{0,12}(?:公司|企业|集团)[^，,。；]{0,15}(?:投资|建设|建造|扩建)',t) and not re.search(r'政府.{0,20}(?:拨款|采购|委托|批准|资助)|财政|补贴|税收|关税|授权|许可',t):
            return ContentContract(False,policy_topic(t),False,state,'private_announcement','private_project','官员宣布企业项目不是政府工具，缺公共委托/资助/许可')
        if re.search(r'承办.{0,45}(?:公约|缔约方大会)|(?:先进)?超级计算|量子信息科学|人工智能.{0,12}拨款',t) and not policy_topic(t):
            return ContentContract(False,False,False,state,'other_public_affairs','out_of_scope','大会活动或一般科技预算，不因邻近双碳政策变为双碳措施')
        if re.search(r'此次退出.{0,20}理由|退出.{0,20}理由.{0,15}(?:有损|老调重弹)',t):
            return ContentContract(False,policy_topic(t),False,state,'commentary','commentary','退出的理由分析不等于新增退出措施')
        if re.search(r'有必要.{0,45}(?:做出规划|制定.{0,12}规划)|(?:表示|予以|给予)赞赏|出色合作',t) and not re.search(r'(?:决定|批准|签署|发布|公布|宣布|颁布|已经制定|已制定)',t):
            return ContentContract(False,policy_topic(t),False,state,'commentary','commentary','规划必要性或赞赏表态，没有当前措施的采纳断言')
        if re.match(r'该政策旨在帮助',t) or re.match(r'这些政策举措在内容上',t):
            return ContentContract(False,policy_topic(t),False,state,'background','background','政策目的/工具分类概述单列，不作为新增措施')
        if re.search(r'^(?:各州|公众|企业|协会).{0,12}要求.{0,45}(?:政府|白宫).{0,12}(?:不得|停止|取消|削减)',t) or re.search(r'能源部.{0,12}要求白宫.{0,30}削减',t):
            return ContentContract(False,policy_topic(t),False,'discussion','request','discussion','诉讼请求或部门预算主张，没有采纳断言')
        if re.search(r'特别困难.{0,20}因为.{0,30}没有',t):
            return ContentContract(False,policy_topic(t),False,state,'background','background','解释困难的协议缺失，不是新措施')
        if re.search(r'(?:还在|正在|积极|正)?考虑(?:延长|提高|降低|修改|取消|废除|放宽)',t):
            return ContentContract(False,policy_topic(t),False,'discussion','consideration','discussion','考虑调整的动作尚未采纳，状态不能借已识别国家升级')
        if re.search(r'^(?:[“”\s]*)(?:即便|假如|倘若|假设)',t):
            return ContentContract(False,policy_topic(t),False,'discussion','hypothetical','discussion','让步/假设不证明该动作已发生')
        commentary=bool(re.search(r'^有趣的是|所谓.{0,35}(?:实质|真正)|高度致力.{0,30}最认真|极度不足|减排仍有.{0,10}空间|将帮助该国|将有助于',t))
        thirdparty=re.search(r'^(?:但|而|此外[，,])?[“”\s]*(?:气候行动追踪[^，。；]{0,12}|分析师|专家|咨询公司|环保组织|该工作组|行业协会)[^。；]{0,25}(?:指出|认为|表示)',t)
        if (commentary or thirdparty) and not explicit:
            return ContentContract(False,policy_topic(t),False,state,'commentary','commentary','主断言为第三方评价、效果或预测，没有当前公共措施')
        if re.search(r'必要性.{0,15}迫切|迈出了?[^。；]{0,12}重要一步|迈出的重要一步',t) and not re.search(r'政府.{0,12}(?:宣布|决定|批准)',t):
            return ContentContract(False,policy_topic(t),False,state,'commentary','commentary','措施必要性或意义评价，不是采纳事实')
        if re.search(r'(?:独立报|日报|媒体).{0,40}(?:标题|战火|宣战)',t) and re.search(r'认为|用|比喻',t):
            return ContentContract(False,policy_topic(t),False,state,'commentary','commentary','媒体修辞评价不作为措施事实')
        execution=bool((EXEC.search(t) or (plan_confirmed and QUANTIFIED_GOAL.search(t))) and (POLICY_REF.search(t) or re.search(r'依法|政府规定|截止日期.{0,40}提交|提交.{0,20}注册',t)))
        # 接收公司、受补助企业不等于施策者；法定注册条件优先于企业字面词。
        private_lead=re.search(r'^(?:此外[，,]|另外[，,]|作为[^，]{0,30}[，,])?[^。；]{0,28}(?:公司|企业|集团|丰田|国瑞能|特斯拉)[^。；]{0,45}(?:调整产品|提供.{0,15}解决方案|测试|推广|出货|研发|宣布投资|收购|劝告|劝说)',t)
        if private_lead and not explicit and not execution:
            return ContentContract(False,policy_topic(t),False,state,'private','private_project','企业经营或个人倡议，政策背景不产生政府措施')
        if re.search(r'仅占|占该国.{0,10}电力结构|份额.{0,15}最低|统计显示|数据显示|同比|环比',t) and not explicit and not execution:
            return ContentContract(False,policy_topic(t),False,state,'background','background','现实统计或市场份额，不是新增公共措施')
        if re.search(r'必须被允许|应当被允许',t):
            return ContentContract(False,policy_topic(t),False,'discussion','permission_request','discussion','寻求许可不等于已经授权')
        local=bool(local_generic or LOCAL_WORDS.search(t) or re.search(r'东京都|加州政府|首尔市政府',t))
        if local_generic and not any(e['actors'][0]['start']<next(m['start'] for m in rel['mentions'] if m.get('level')=='local') for e in current_events if e['actors']):
            implementing=bool(re.search(r'依据|按照|落实|执行|根据|贯彻',t) and re.search(r'国家|全国|国务院|中央|联邦|国会',t) and re.search(r'《[^》]+》',t))
            extra=bool(re.search(r'另行|额外|新增|加码|自主|自行|再增加|另外增加',t))
            kind='local_execution' if implementing and not extra else 'local_policy'
            return ContentContract(False,policy_topic(t),False,state,'local_actor',kind,'当前具名地方主体；地方落实另存并保留国家政策题名，不把地方新增要求提升为国家措施')
        national_legal_clause=bool(re.search(r'(?:联邦政府|中央政府)(?:层面)?[^，。；]{0,65}(?:签署|颁布|制定|出台|唯一.{0,10}颁发|有权制定)',t))
        if local and not lexical_public and not national_legal_clause and not (re.search(r'中央政府|联邦政府|国家.{0,12}(?:规定|政策|法律)',t) and execution):
            return ContentContract(False,policy_topic(t),False,state,'local','local_policy','地方自主措施不进入国家主集')
        if re.search(r'尚未(?:批准|通过|签署|公布|生效)|未获(?:批准|许可)|没有.{0,8}(?:批准|通过|授权)|仍未决定',t):state='not_adopted'
        if rel.get('claim_state') and current_events:state=rel['claim_state']
        if re.search(r'(?:局长|部长|发言人).{0,30}(?:表示|宣布)[^。；]{0,45}(?:总统|政府|首相|总理).{0,20}将签署',t):
            state='announced_withdrawal' if re.search(r'取消|撤销|废除',t) else 'announced_plan'
        # 状态连接到同一尚未采纳方案；泛词“计划”不能摆脱前文草案/候任状态。
        current_adopted=bool(re.search(r'(?:政府|总统|首相|内阁|国会|白宫).{0,18}(?:已经|已|正式)(?:批准|通过|签署|公布|发布)|(?:政府|白宫).{0,12}宣布',t))
        if not current_adopted and state_context:
            draft=list(re.finditer(r'草案|征求意见|尚待批准',state_context[-800:]));adopt=list(re.finditer(r'正式公布|正式发布|已经通过|已通过|批准了|正式签署',state_context[-800:]))
            if draft and (not adopt or draft[-1].start()>adopt[-1].start()):state='draft_or_proposal'
            if not plan_confirmed and re.search(r'将在上任后.{0,15}(?:制定|出台|恢复)|竞选团队|候任总统|若当选|如果当选',state_context[-700:]):state='campaign'
        if pronoun_public and re.search(r'候任总统|当选总统|上任后他将',state_before[-900:]) and not current_adopted:state='campaign'
        topic=policy_topic(t) or bool(re.search(r'环保汽车|燃气发电',t))
        linked_goal_topic=bool(not topic and linked_goal and policy_topic(before))
        if linked_goal_topic:topic=True
        context_exec=execution and bool(re.search(r'政府|总统|首相|总理|能源部|国会|部.{0,10}(?:宣布|发布)',before)) and policy_topic(before) and bool(re.search(r'计划|规划|拍卖|法案|条例|政策',before))
        if not topic and context_exec:topic=True
        public=bool(topic and (explicit or context_exec))
        national=bool((lexical_actors and all(m.get('level')!='local' for m in lexical_actors)) or NATIONAL_SCOPE.search(t) or context_exec or formal_country_plan or (pronoun_public and re.search(r'该国',t)) or (generic and policy_topic(before) and re.search(r'政府|总统|首相|国会|能源部',before)))
        if public and not national and self.role_scope.named_policy_owner(text,0):national=True
        if public and state=='announced_goal' and re.search(r'政府(?:根据|依据|按照)[^。；]{1,22}(?:法案|法律)[^。；]{0,35}(?:提供|资助|拨款)',t) and re.search(r'目标|到20\d\d',t):
            state='reported_support_and_goal'
        plan_level_link=False
        if public and not national and linked_goal:
            # 只补已独立成立的目标所属层级；不使用S，也不借机构把评论变政策。
            anchor,_=self.role_scope._context(t,len(before),{'file_id':'level-only'},before+t)
            plan_level_link=bool(anchor and anchor['actors'] and all(m.get('level')=='national' for m in anchor['actors']))
            national=plan_level_link
        kind='national_local_coordination' if explicit and coordination else 'current_public_action' if explicit else 'linked_execution' if context_exec else 'unconfirmed'
        route='confirmed' if public else 'unchanged'
        if public and state in BAD:route='campaign' if state=='campaign' else 'draft' if state in {'draft_or_proposal','not_adopted','proposed_change'} else 'discussion'
        return ContentContract(public,topic,national,state,kind,route,'本句公共动作/执行条款及主题证据独立成立' if public else '本句尚缺独立公共措施证据；国家连接不补造内容',context_exec or plan_level_link or linked_goal_topic)

    def apply(self,event,full,doc):
        # 自动层不能覆盖固定复核输入，也不能从质量/地方/噪声隔离项强行恢复。
        if event.get('decision_origin')=='fixed_review_input':return [event]
        parts=split_contextual_facts(event,full,self.role_scope)
        if parts:return parts
        baseline_keep=event.get('route','').startswith('main_')
        t=event['text'];a=event['start'];b=event['end'];before=full[max(0,a-900):a]
        campaign_reconsider=event.get('route')=='campaign' and current_plan_confirmation(t,before)
        local_reconsider=event.get('route') in {'local_policy','local_execution'} and self.content_contract(t,before).kind=='national_local_coordination'
        if not baseline_keep and event.get('route') not in {'subject_unknown','level_unknown','content_uncertain','out_of_scope','private_project'} and not campaign_reconsider and not local_reconsider:return [event]
        if not baseline_keep and not (policy_topic(t) or ((EXEC.search(t) or QUANTIFIED_GOAL.search(t)) and policy_topic(before))):return [event]
        # 新补入事实不能携带重复标题或前置产量统计；仍按原文切片保留全部字符。
        if not baseline_keep and not event.get('text_parts'):
            cut=0;prefix_route='background';title=doc.get('title','').strip()
            title=re.split(r'\s+',title)[0] if title else ''
            if len(title)>=8 and t.startswith(title) and len(t)>len(title)+8:
                cut=len(title);prefix_route='introduction'
            else:
                gov=re.search(r'政府(?:还|将)?计划',t)
                if gov and gov.start()>0 and re.search(r'目前.{0,35}累计产量.{0,20}\d',t[:gov.start()]) and not re.search(r'如果|除非|只有',t[:gov.start()]):cut=gov.start()
            if cut and self.content_contract(t[cut:],before+t[:cut]).public_fact:
                prefix=copy.deepcopy(event);prefix.update(event_id=eid(event,'PREFIX'),end=a+cut,text=t[:cut],route=prefix_route,countries=[],policy_state='',policy_level='unknown',reason='重复标题/当前产量背景独立归档',connection_path=[],evidence=[evidence(full,a,a+cut,'被剥离的标题/统计')],roles={'actors':[],'actions':[],'targets':[],'measures':[]})
                child=copy.deepcopy(event);child.update(event_id=eid(event,'CLEANFACT'),start=a+cut,text=t[cut:],newly_recovered=True)
                child['evidence']=[evidence(full,a+cut,b,'当前政策事实')]
                child.setdefault('roles',{})['measures']=[evidence(full,a+cut,b,'当前政策事实')]
                result=[prefix]+self.apply(child,full,doc)
                assert ''.join(e['text'] for e in result)==t
                return result
        # 另一个企业主语的反应是独立动作。先核实前半确有公共措施，再按字面范围分开。
        cut=prediction_tail(t) if not event.get('text_parts') else None
        if cut is not None and self.content_contract(t[:cut],before).public_fact:
            fact=copy.deepcopy(event);fact.update(event_id=eid(event,'ASSERTION'),end=a+cut,text=t[:cut],
                policy_state=self.content_contract(t[:cut],before).state,newly_recovered=True)
            fact['evidence']=[evidence(full,a,a+cut,'当前措施，条件、时间和金额按原文保留')]
            fact.setdefault('roles',{})['measures']=[evidence(full,a,a+cut,'公共措施原文')]
            tail=copy.deepcopy(event);tail.update(event_id=eid(event,'PREDICTION'),start=a+cut,text=t[cut:],
                route='commentary',countries=[],policy_state='',policy_level='unknown',connection_path=[],
                roles={'actors':[],'actions':[],'targets':[],'measures':[]},
                evidence=[evidence(full,a+cut,b,'效果预测原文')],reason='当前公共事实与后置效果预测分开；未改写原文')
            result=self.apply(fact,full,doc)+[tail]
            assert ''.join(e['text'] for e in result)==t
            return result
        switch=re.search(r'(?:[，,]|导致|使得)(?=[^，,。；]{0,12}(?:公司|企业|集团)[^，,。；]{0,12}(?:取消|暂停|撤销|停止|退出|反对|欢迎|称赞))',t)
        tail_has_condition=bool(switch and re.search(r'只有|除非|只要|才能|补贴|抵免|税收|税率|必须|不得|政府要求',t[switch.end():]))
        if switch and switch.start()>0 and not event.get('text_parts') and not re.search(r'如果|除非|只有|倘若',t[:switch.start()]) and not tail_has_condition:
            prefix=t[:switch.start()];pc=self.content_contract(prefix,before)
            if pc.public_fact:
                cut=a+switch.start();child=copy.deepcopy(event)
                child.update(event_id=eid(event,'FACT'),start=a,end=cut,text=prefix,policy_state=pc.state,newly_recovered=True,
                    reason=event.get('reason','')+'；BOUNDARY公共动作与企业反应按主体拆分')
                child.setdefault('roles',{})['measures']=[evidence(full,a,cut,'当前公共措施事实，不含企业反应')]
                child['boundary_parent_span']={'start':a,'end':b}
                remainder=copy.deepcopy(event)
                remainder.update(event_id=eid(event,'REACTION'),start=cut,end=b,text=full[cut:b],route='private_reaction',countries=[],policy_state='',policy_level='unknown',
                    reason='BOUNDARY企业反应另存；取消或暂停不改变前面的公共措施状态',connection_path=[],
                    roles={'actors':[],'actions':[],'targets':[],'measures':[]},evidence=[evidence(full,cut,b,'企业反应原文')])
                remainder['boundary_parent_span']={'start':a,'end':b}
                result=self.apply(child,full,doc)+[remainder]
                assert ''.join(e['text'] for e in result)==t
                return result
        c=self.content_contract(t,before);e=copy.deepcopy(event)
        e['policy_content_contract']=asdict(c)
        trace=dict(version=VERSION,input_route=e['route'],input_countries=list(e.get('countries',[])),content_decision=c.decision,
            content_basis=c.reason,country_evidence_can_change_publicness=False,changes=[])
        e['interface_trace']=trace
        if c.state=='reported_support_and_goal' and e.get('policy_state')!=c.state:
            e.update(policy_state=c.state,newly_recovered=True)
            trace['changes'].append('原文同时报告公共支持与未来目标，不标成仅目标或已实施')
        platform=platform_context(t,full,a)
        if platform and (c.public_fact or c.decision=='unchanged'):
            e.update(route='campaign',policy_state='campaign',reason='ASSERTION状态分流：'+platform['reason'])
            e.setdefault('evidence',[]).append(evidence(full,platform['start'],platform['end'],'竞选/候任平台上下文'))
            trace['changes'].append('同一人物的平台状态连接，不当作正式采纳')
            return [e]
        if c.decision in {'noise','commentary','private_project','private_reaction','background','local_policy','local_execution','out_of_scope','discussion','subject_unknown','quality_unknown','content_uncertain','international_framework','introduction'}:
            if baseline_keep:
                e.update(route=c.decision,countries=[],policy_state=c.state,reason='BOUNDARY内容核验：'+c.reason)
                trace['changes'].append('隔离明确非政策；没有使用S或国别得分')
            if c.decision in {'local_policy','local_execution'} and c.kind=='local_actor':
                e.update(route=c.decision,policy_level='local' if c.decision=='local_policy' else 'local_execution',reason=c.reason)
            return [e]
        if c.public_fact and c.decision in {'campaign','draft','discussion'}:
            e.update(route=c.decision,policy_state=c.state,reason='BOUNDARY状态分流：'+c.state+'；保留原文而不视为已采纳')
            trace['changes'].append('同一方案状态单列');return [e]
        # 内容不成立且此前不保留：在调用归属模块之前返回，接口上切断证据泄漏。
        if not baseline_keep and not c.public_fact:return [e]
        d=self.role_scope.country_decision(t,a,b,dict(file_id=e['file_id'],source_country=doc.get('source_country','')),full,doc.get('metadata_status',''))
        # 当前已通过内容层的字面施策角色，比后来找到的弱/跨句连接更强。
        # 只保留同国、同片段、原文字面及动作位置均可验证的证据；新的明确外国角色仍可纠错。
        if baseline_keep and c.public_fact and c.national_evidence and c.state not in BAD and d['method'] in {'verified_reference','scored_context'} and len(e.get('countries',[]))==1 and set(d['countries'])==set(e['countries']):
            current=[m for m in e.get('roles',{}).get('actors',[]) if m.get('public') and eligible(m) and m['country'] in e['countries'] and a<=m.get('start',-1)<m.get('end',-1)<=b and full[m['start']:m['end']]==m.get('text')]
            actions=[v for v in e.get('roles',{}).get('actions',[]) if a<=v.get('start',-1)<v.get('end',-1)<=b and full[v['start']:v['end']]==v.get('text') and any(m['end']<=v['start'] for m in current)]
            # 不能只验证机构/动作均在句内，还须验证它们之间是直接断言，而非“的计划、能否、专家称”。
            actions=[v for v in actions if any(m['end']<=v['start'] and re.fullmatch(ADVERBS+r'(?:在[^，。；;]{0,20}(?:会议|会上|会议上))?(?:审议)?',full[m['end']:v['start']]) for m in current)]
            actions=[v for v in actions if v['text']!='通过' or (not re.match(r'提高|降低|建设|发展|实施|加强|开展|增加|减少|提供|为',full[v['end']:b]) and re.search(r'议案|法案|法律|条例|方案|规划|战略|草案|协议|目标',full[v['end']:min(b,v['end']+90)]))]
            if current and actions:
                d['supplemental_method']=d['method'];d['supplemental_connection']=d['connection']
                d.update(method='explicit_roles',actors=current,connection=[],events=[dict(actors=current,action=v,method='上游已验证当前公共主体及字面动作') for v in actions],preserved_current_roles=True)
                d['scores']=score_candidates(t,a,self.role_scope.mentions(t,a),current,[],{},doc.get('source_country',''),self.role_scope.params,[v['start']-a for v in actions],doc.get('metadata_status',''),d.get('density_context'))
                e['country_basis']='当前句已验证公共机构及动作；弱连接仅作补充'
                trace['changes'].append('保留更强当前角色，未用跨句主体替换或降低证据等级')
        e['optimized_attribution']={k:v for k,v in d.items() if k!='anchor'}
        e['optimized_attribution'].update(decision_used=False,actual_method='',decision_history=[])
        if baseline_keep and not d['countries'] and not d['multiple_policy_events']:
            current={m['country'] for m in self.role_scope.mentions(t,a) if m.get('role') in {'country_candidate','public_actor'} and m.get('level')!='local'}
            if (current and not set(e.get('countries',[])).intersection(current)) or (d['reported_events'] and not d['events']):
                e.update(route='subject_unknown',countries=[],reason=e.get('reason','')+'；BOUNDARY当前主体与旧归属冲突，隔离而不继承外国锚点')
                trace['changes'].append('当前具名主体冲突，不能沿用旧错误归属')
                return [e]
        if not baseline_keep:
            if not c.public_fact or not c.national_evidence or not d['countries'] or d['multiple_policy_events'] or event.get('previous_quality_risks') or event.get('quality_risks'):return [e]
            e.update(route='main_explicit',countries=d['countries'],policy_level='national',policy_state=d['action_state'] or c.state,
                delivery_layer='扩展候选',newly_recovered=True,reason='BOUNDARY新增：'+c.reason+'；'+d['method'],country_basis='BOUNDARY '+d['method'])
            trace['changes'].append('独立内容合约通过后，才补国家；新增扩展候选')
        else:
            if d['countries'] and not d['multiple_policy_events']:
                old=set(e.get('countries',[]));new=set(d['countries'])
                if old!=new:
                    e.update(countries=d['countries'],newly_recovered=True,delivery_layer='扩展候选',country_basis='BOUNDARY '+d['method'],
                        reason=e.get('reason','')+'；BOUNDARY按当前动作范围更正主体')
                    trace['changes'].append('仅更正国家，不以关系提高公共性')
            # 明确共同签署动作优先于文件题名中的碳中和词，不能标成纯目标。
            generic_states={'announced_goal','announced_plan','announced_strategy','announced_funding_plan','announced_or_adopted','unknown'}
            if d['action_state'] and e.get('policy_state') in generic_states and e.get('policy_state')!=d['action_state']:
                e.update(policy_state=d['action_state'],newly_recovered=True);trace['changes'].append('状态绑定共同发布/签署动作')
            verbs={x['action']['text'] for x in d['events']}
            if '重申' in verbs and d['reported_events'] and e.get('policy_state') in {'announced_withdrawal','cancelled_or_withdrawn'}:
                e.update(policy_state='announced_commitment',newly_recovered=True);trace['changes'].append('被关注的外国退出不污染当前主体重申状态')
            if '限制' in verbs and e.get('policy_state')=='announced_funding_plan' and not re.search(r'拨款|贷款|预算|补贴|政府投资',t):
                e.update(policy_state='announced_plan',newly_recovered=True);trace['changes'].append('限制投资不是财政拨款计划')
        if e['route'].startswith('main_'):
            e.setdefault('roles',{}).update(actors=d['actors'] or e.get('roles',{}).get('actors',[]),
                actions=[x['action'] for x in d['events']] or e.get('roles',{}).get('actions',[]),targets=d['targets'],
                cooperation_countries=d['cooperation_countries'])
            local_events=[ev for ev in d['events'] if ev.get('national_local_coordination')]
            if local_events:
                parts={ (v['start'],v['end']):v for ev in local_events for v in ev.get('local_participants',[]) }
                e['roles']['local_participants']=list(parts.values())
                e['coordination_scope']='国家牵头/地方参与；地方自主新增要求不据此提升'
                for v in parts.values():e.setdefault('evidence',[]).append(evidence(full,v['start'],v['end'],'地方参与者，不是独立国家政策主体'))
            if d['joint']:
                e['event_type']='joint_policy';e['joint_participants']=d['countries']
                for p in d.get('joint_evidence',[]):e.setdefault('evidence',[]).append(evidence(full,p['start'],p['end'],p['role']))
            if d['cooperation_countries'] and not d['joint']:e['event_type']='single_policy'
            if d['method']=='explicit_roles' and len(d['countries'])==1 and not d['joint']:
                if e.get('event_type')=='joint_policy':
                    e['previous_joint_participants']=e.pop('joint_participants',[])
                    e['newly_recovered']=True;trace['changes'].append('当前动作只有一个主体，清除继承的共同政策标记')
                e['event_type']='single_policy'
            e.setdefault('connection_path',[]).extend(d['connection']);e.setdefault('evidence',[])
            for p in d['connection']:e['evidence'].append(evidence(full,p['start'],p['end'],'BOUNDARY国家路径，不作为内容依据'))
            if not e['evidence']:e['evidence']=[evidence(full,a,b,'当前措施原文')]
            used=bool(trace['changes'])
            e['optimized_attribution'].update(decision_used=used,actual_method=d['method'] if used else '',decision_history=[dict(changes=trace['changes'],input_route=trace['input_route'],countries=e['countries'])] if used else [])
        return [e]

def eid(event,suffix):return event.get('event_id','EVENT')+'-BOUNDARY-'+suffix
