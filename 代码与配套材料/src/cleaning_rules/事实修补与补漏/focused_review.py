"""7.5.7：断言类型质检及国家覆盖补漏；不使用样本编号、评价标签或来源国兜底。"""
import copy,re
from ..事实修补与补漏.coverage_repair import CoverageRepair,C,piece
from ..事实修补与补漏.recall_rules import country

VERSION='focused-quality-recall-20261024.7.5.7'
PARAMETERS=dict(context_chars=900,new_layer='扩展候选',source_inference=False,
    confidence_is_probability=False,weights_changed=False,
    retained_gate='本句必须陈述措施；前文锚点不能将统计、评价变成政策')
UNSAFE=re.compile(r'如果|假如|倘若|尚未|尚待|未曾|否认|没有|不曾|建议|草案|拟议|拟定|征求意见|竞选|候选人|可能批准|希望.*批准')
CONCRETE=re.compile(r'(?:政府|国会|议会|部|局|总统|首相|总理).{0,28}(?:宣布|决定|批准|下令|公布|制定|规定|(?<!的)要求(?!下)|拨款|征收)|每(?:户|辆|吨).{0,20}(?:补贴|税|元|美元|英镑)|法(?:律|案).{0,12}(?:规定|授权)')
LOCAL=re.compile(r'(?:加州|加利福尼亚州|纽约州|新南威尔士州|魁北克省|安大略省|东京都|威尼斯)(?:政府)?(?:发布|公布|制定|宣布|规划|决定|出台)')
COUNTRY=C[:-1]+'|大韩民国)'
STRATEGY=re.compile(r'(?P<c>'+C+r')(?P<agency>经济发展部|矿业和能源部|能源部|环境部|政府)?(?:日前|近日|最近|上周|已经|正式|已)?(?:公布|发布|批准)(?:了)?(?P<name>(?:国家)?(?:氢能|氢气|清洁能源|可再生能源)(?:发展)?(?:战略|构想|行动计划))[^。；;]*[。；;]?')
AUCTION=re.compile(r'(?P<c>'+C+r')(?P<agency>矿业和能源部|能源部|政府)(?:日前|近日|最近|上周)?宣布了?[^。；]{0,90}(?:新能源|可再生能源)拍卖的指导方针[。]?')
GOAL=re.compile(r'(?P<c>'+C+r')(?P<agency>总理|首相|总统)(?P<leader>[^，,。；]{1,12}?)(?:正式|已经|已)?(?:提出|宣布|承诺)(?:了)?(?:'+C+r')?(?:将在|将|到|于)?\s*20\d\d\s*年(?:前)?实现(?:净零碳排放|碳中和|净零排放)的目标')
PHASEOUT=re.compile(r'(?P<c>'+C+r')宣布将(?:从|于)\s*20\d\d\s*年开始(?:淘汰|禁售)(?:内燃机汽车|燃油车|汽油和柴油汽车)[。]?')
JOINT=re.compile(r'(?P<a>'+COUNTRY+r')[和与](?P<b>'+COUNTRY+r')就(?:清洁能源|低碳|可再生能源)[^，,。；]{1,75}(?:工作计划|行动计划)达成一致')
BILATERAL=re.compile(r'(?P<a>'+C+r')还?与(?P<partners>(?:新西兰|阿根廷|荷兰|'+C+r')(?:[,，、和及](?:新西兰|阿根廷|荷兰|'+C+r'))+)等?(?P<claim>签署了关于为实现氢社会而开展合作的协议备忘录[。]?)')
ANCHOR=re.compile(r'(?P<c>'+C+r')(?:矿业和能源部|经济发展部|能源部|政府)[^。！？]{0,140}(?:新能源拍卖的指导方针|《国家氢能战略》|国家氢能发展战略)[^。！？]*[。！？；;]')

def canonical(c):return '韩国' if c=='大韩民国' else country(c)

def quality_reason(t):
    """当前主断言；明确措施及其执行条件优先于泛效果词。"""
    if re.fullmatch(r'(?:此外[，,]|另外[，,]|同时[，,])?(?:为|为了)[^。！？]{1,60}[，,]\s*',t):
        return 'introduction','目的从句不完整；其中退出等动作属于原因/对象，不能单独生成政策事件','purpose_fragment'
    lm=LOCAL.search(t)
    if lm and re.fullmatch(r'(?:根据|据|近日|日前|此外[，,]|去年|今年|\d+[年月日]|\s)*',t[:lm.start()]):
        return 'local_policy','当前发布者是地方政府；地方自主目标不提升为全国措施','local_publisher'
    if CONCRETE.search(t):return None
    if re.search(r'若非|倘若没有|如果没有',t) and re.search(r'统计|测算|估计|使用量|排放量',t):
        return 'background','历史统计与反事实估计，未声称公共决定','counterfactual_statistic'
    if re.search(r'不仅高出.{0,15}(?:计划|目标)|高于年初目标|超过原定目标',t) and re.search(r'占[\d.]+[%％]|增长|翻了',t):
        return 'background','已实现的占比/增长与旧目标对照，非本句新增措施','realized_statistic'
    if re.search(r'(?:金融机构|银行|企业|公司).{0,15}高管(?:表示|认为|称)',t) and re.search(r'很难|难以预测|专业性强|投资标的|贷款标的',t):
        return 'commentary','金融机构评价技术或投资前景，非公共机构决定','private_comment'
    if re.search(r'(?:补贴|政策|计划|战略).{0,25}(?:是|也是).{0,25}(?:推动力|驱动力|增长动力)',t):
        return 'commentary','对政策作用的概括评价，未交代具体措施','generic_effect'
    if re.search(r'高景气(?:发展)?期|长期处于.{0,10}景气|发展空间巨大|前景广阔',t):
        return 'commentary','行业景气和效果预测，非公共措施本身','market_outlook'
    if re.search(r'从长远来看|对于这些计划|对于该计划',t) and re.search(r'十分有利|非常有利|大有裨益|十分有益',t):
        return 'commentary','领导人对计划的价值评价不能替代措施内容','official_evaluation'
    return None

class FocusedReview(CoverageRepair):
    def archive(self,old,route,why,rule):
        r=copy.deepcopy(old)
        r.update(route=route,reason=why,delivery_layer='隔离归档',focused_rule=rule,
            focused_previous_route=old['route'],focused_parent_span=[old['start'],old['end']],
            focused_previous_countries=old.get('countries',[]),algorithm_version=VERSION)
        # 保留国家、状态和原证据用于档案追溯；不计入国家政策主/扩展集。
        if route=='local_policy':r['policy_level']='local'
        return r

    def record(self,old,full,parts,countries,state,reason,anchors=(),rule=''):
        r=super().record(old,full,parts,countries,state,reason,anchors,rule)
        r.update(algorithm_version=VERSION,focused_rule=rule,focused_previous_route=old['route'],
                 focused_parent_span=[old['start'],old['end']])
        r.pop('coverage_repair_rule',None)
        return r

    def remainder(self,old,full,a,b,route):
        r=super().remainder(old,full,a,b,route)
        r.update(focused_rule='fact_remainder',focused_previous_route=old['route'],focused_parent_span=[old['start'],old['end']],
                 reason='本轮事实边界修补：余文按原文保留，未进入分析事实')
        r.pop('coverage_repair_rule',None)
        return r

    def fact(self,old,full,m,state,rule,reason,tail='commentary',actor_group=None,cut_end=None):
        a=old['start'];x=a+m.start();y=a+(m.end() if cut_end is None else cut_end);c=canonical(m['c'])
        r=self.record(old,full,[(x,y)],[c],state,reason,rule=rule)
        if actor_group and m.groupdict().get(actor_group):
            z=m['c']+m[actor_group]
            r['roles']['actors']=[dict(country=c,text=z,start=a+m.start('c'),end=a+m.end(actor_group),public=True,level='national',role='policy_actor')]
        return self.partitions(old,full,[r],[(x,y)],tail)

    def revise(self,old,full,doc):
        a,b,t=old['start'],old['end'],old['text']
        # 即使整句已保留，也须去掉统计头和评价尾；政策目标中的年份、百分比原样保留。
        mixed=re.search(r'按照(?P<agency>工信部|工业和信息化部)的(?:规划|计划)[，,][^。！？]+',t)
        if mixed and not UNSAFE.search(t) and re.search(r'发展空间巨大|前景广阔',mixed.group()):
            end=re.search(r'[，,](?:发展空间巨大|前景广阔)',mixed.group())
            if end:
                x,y=a+mixed.start(),a+mixed.start()+end.start()
                r=self.record(old,full,[(x,y)],['中国'],'announced_goal','统计与评论之间的部委规划目标单独提取，保留全部时间和比例',rule='mixed_plan_fact')
                r['roles']['actors']=[dict(country='中国',text=mixed['agency'],start=a+mixed.start('agency'),end=a+mixed.end('agency'),public=True,level='national',role='policy_actor')]
                return self.partitions(old,full,[r],[(x,y)])
        q=quality_reason(t)
        if q and old['route'].startswith('main_'):return [self.archive(old,*q)]
        if old['route'].startswith('main_') or old.get('text_parts'):return [old]
        if old['route'] in {'noise','local_policy','local_execution','quality_unknown','campaign'}:return [old]
        if UNSAFE.search(t):return [old]
        # 已批准的国家构想与另一国尚在探索的方案各自绑定状态。
        m=STRATEGY.search(t)
        if m and not re.search(r'公司|企业|专家|建议|希望|如果|见证',t[:m.start()]):
            stop=m.end()
            for end in re.finditer(r'[，,](?P<next>'+C+r'|从而|这将|有望)',m.group()):
                if canonical(end['next'])!=canonical(m['c']):stop=m.start()+end.start();break
            return self.fact(old,full,m,'approved_strategy' if '批准' in m.group() else 'announced_strategy',
                'national_strategy','国家/公共部门明确公布或批准战略；不把未来目标当成完成',actor_group='agency',cut_end=stop)
        m=AUCTION.search(t)
        if m:return self.fact(old,full,m,'announced_auction','auction_guideline','国家能源机构公布新能源拍卖规则，拍卖未来日期原样保留',actor_group='agency')
        m=GOAL.search(t)
        if m and not re.search(r'建议|见证|公司|企业|如果',t[:m.end()]):
            return self.fact(old,full,m,'announced_goal','national_target','现任国家领导人正式提出国家目标；与后接评论分开',actor_group='agency')
        m=PHASEOUT.search(t)
        if m:return self.fact(old,full,m,'announced_phaseout','future_phaseout','宣布的是未来淘汰安排，未标成已完成')
        m=JOINT.search(t)
        if m:
            cs=[canonical(m['a']),canonical(m['b'])];x,y=a+m.start(),a+m.end()
            r=self.record(old,full,[(x,y)],sorted(cs),'agreement_reached','两国就同一清洁能源工作计划达成一致；一个共同事件、多个国家引用',rule='joint_workplan')
            r.update(joint_participants=sorted(cs),event_type='joint_policy')
            return self.partitions(old,full,[r],[(x,y)])
        m=BILATERAL.fullmatch(t)
        if m:
            facts=[];covered=[]
            for p in re.finditer(r'新西兰|阿根廷|荷兰|'+C,m['partners']):
                parts=[(a+m.start('a'),a+m.start('partners')),(a+m.start('partners')+p.start(),a+m.start('partners')+p.end()),(a+m.start('claim'),a+m.end('claim'))]
                cs=[canonical(m['a']),canonical(p.group())]
                r=self.record(old,full,parts,sorted(cs),'agreement_signed','一国分别与列举伙伴签署氢社会合作备忘录；逐伙伴成共同事件，协议名称和日期未明确',[(a,b,'分别签约列举原文，不解释为单一多边协议')],rule='bilateral_list')
                r.update(joint_participants=cs,event_type='joint_policy')
                facts.append(r);covered.extend(parts)
            return self.partitions(old,full,facts,covered)
        # 具体执行条款只接回有明确发布机构的同一政策，遇到竞争国/换题即停止。
        before=full[max(0,a-PARAMETERS['context_chars']):a];offset=max(0,a-PARAMETERS['context_chars'])
        anchors=list(ANCHOR.finditer(before))
        if anchors:
            m=anchors[-1];cs=canonical(m['c']);between=before[m.end():]
            others={canonical(x.group()) for x in re.finditer(C,between+t)}-{cs}
            changed=re.search(r'市场分析|相关新闻|下一篇|公司计划|虽然|反对|评论',between)
            isauction='拍卖' in m.group()
            detail=(re.match(r'通过在官方公报|本次招标将授予购电协议|电力供应计划于|投资者和相关方可以|根据该部法令',t) if isauction else
                    re.match(r'到20\d\d年|打造全球氢气供应基地|'+C+r'提出的低碳氢能',t))
            if detail and not others and not changed and not re.search(r'预计带动|有望|公司计划|评论|批评',t):
                r=self.record(old,full,[(a,b)],[cs],'execution_requirement' if isauction else 'published_strategy_detail',
                    '当前具体条款→近邻已发布的同一拍卖/氢能战略→发布机构→国家；保留时间及条件',
                    [(offset+m.start(),offset+m.end(),'同主题已公布政策及发布主体')],rule='linked_policy_detail')
                return [r]
        return [old]
