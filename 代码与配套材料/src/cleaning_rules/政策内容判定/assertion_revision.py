"""Current-assertion gate and bounded execution recovery, revision 6.12.

No evaluation IDs or labels enter this module. Recovery uses literal ranges;
the final gate also applies to facts protected by earlier extraction layers.
"""
import copy
import re
from ..公共工具.identifiers import ident
from ..主体与国家归属.national_scope import G20, evidence

VERSION = 'assertion-and-execution-6.16'
COUNTRY = r'沙特阿拉伯|印度尼西亚|加拿大|俄罗斯|澳大利亚|意大利|阿根廷|墨西哥|南非|土耳其|巴西|沙特|印尼|中国|美国|日本|韩国|法国|德国|英国|印度|欧盟'
CANON = {'沙特': '沙特阿拉伯', '印尼': '印度尼西亚'}
PUBLIC = re.compile(r'政府|总统|首相|总理|国会|内阁|国务院|白宫|国家发改委|国家能源局|农业部|交通部|能源部|产业通商资源部|经济产业省|环境省|REPDO|METI|海洋能源管理局|拜登|特朗普|奥巴马')
DOMAIN = re.compile(r'碳|气候|氢|零排放|可再生|清洁能源|新能源|电网|风电|风力|太阳能|光伏|核电|核能|燃煤|煤电|能源效率|能源规划|能源试点|能效|燃油效率|燃油乘用车|电力系统电力设备|电动车|电动汽车|环保汽车|家用电器回收|循环经济|绿色发展|绿色电网|节能|储能|峰谷电价|重污染(?:大型)?邮轮')
DECISION = re.compile(r'公布|发布|颁布|制定|印发|批准|签署|宣布|决定|下令|命令|下达|指定|承诺|规定|设定|大幅降低|修改|征收|禁止|关闭|停止|拨款|招标|签订')


def countries(text):
    return {CANON.get(m[0], m[0]) for m in re.finditer('(?:'+COUNTRY+r')(?!湾|海峡)', text)}


def keep(event):
    return event.get('route', '').startswith('main_')


def public_goal_statement(text):
    return bool(PUBLIC.search(text) and re.search(r'发布(?:联合)?声明|正式公布',text) and re.search(r'设定了[^。]{0,100}目标|公布[^。]{0,80}目标',text) and not re.search(r'将发布|拟发布|预计发布|若当选|候选人',text))


def adopted_roadmap_anchor(text, start, full):
    if not re.search(r'根据(?:这两份|这两种|该|上述|第[一二]个)路线图',text):return None
    lo=max(0,start-2400);before=full[lo:start]
    matches=list(re.finditer(r'[^。\n]{0,100}(?:委员会|政府|内阁)[^。\n]{0,30}(?:采纳|批准|通过)[^。\n]{0,30}最终路线图[^。\n]*',before))
    if not matches:return None
    m=matches[-1]
    if re.search(r'尚未|未能|未获|计划采纳',m[0]):return None
    return dict(start=lo+m.start(),end=lo+m.end(),text=m[0])


def exclusion(text, start, full):
    """Return an archive decision only for an observable non-adopted assertion."""
    before = full[max(0, start - 950):start]
    if re.search(r'计划宣布|准备宣布|拟宣布|即将宣布',text) and not public_goal_statement(text):
        return 'discussion','announcement_preview','计划宣布目标的预告，尚未交代目标已正式公布'
    local_action=re.search(r'(?:州|市|县|省)(?:政府)?[^，。；;]{0,12}(?:关闭|禁止|拒绝|不允许|规定)',text)
    national_order=re.search(r'(?:联邦政府|中央政府|国务院|总统|白宫|国土交通省|经济产业省|环境省|财务省|文部科学省|农林水产省|外务省)[^，。；;]{0,20}(?:下令|决定|宣布|批准|规定|要求)',text)
    if local_action and not national_order:
        return 'local_policy','','当前采取动作的是州、市或县；标题/评论中的总统姓名不构成国家施策关系'
    if re.search(r'报告显示',text) and re.search(r'政府政策修订草案显示|拟议的目标[^。]{0,35}咨询小组',full[start+len(text):start+len(text)+300]):
        return 'draft','draft_or_proposal','当前报告所述目标由后文同一修订草案说明，归草案而非现行政策或纯统计'
    if re.search(r'(?:19|20)\d\d年[^。]{0,12}(?:就实现了|实现了|实现)碳达峰',text) and re.search(r'降幅|强度从|从\d',text) and not re.search(r'将|计划|承诺',text):
        return 'background','','历史达峰与排放变化回顾，不是新目标'
    if re.search(r'例如[，,]工人可以|这一提议旨在',text) and re.search(r'建议投资|提议|草案',before):
        return 'discussion','proposed_change','拟议安排中的举例；没有已采纳的执行要求'
    if re.search(r'全民君认为|作者认为|评论员认为|见证[^。]{0,50}称[，,]这会',text):
        return 'commentary','','评论者的办法或效果预测，名词从句内政策动作不是当前施策'
    if re.search(r'^\s*推动更多[^。]{0,25}投资',text) and re.search(r'带来多方面的好处|提供公共健康福利|创造数以万计',before):
        return 'commentary','','同段列举政策预期收益，未另列公共执行措施'
    if re.search(r'通过改变[^。]{0,40}方式[，,]联邦政府将支持',text):
        return 'commentary','','对联邦采购政策的行业效果概述；具体采购条款另行保留'
    if re.match(r'\s*他指出',text) and re.search(r'商人|执行合伙人|公司(?:的)?负责人',before[-450:]) and re.search(r'将生产|将成为|出口国',text):
        return 'private_project','','说话人回指企业人士；国家产出预测不变成政府目标'
    assessment = re.search(r'非明智之举|无疑成为|背道而驰|有意义的|形容[^。]{0,35}计划|不是[^。]{0,20}价值指向|引领全球[^。]{0,15}行动|诟病|从理论上说|或将难以|发展潜力很高|交换意见|是[^。]{0,15}最佳解决方案|具有战略意义|促进[^。]{0,25}技术进步|刺激[^。]{0,30}技术进步|只能让全球升温|造成[^。]{0,15}破产|不得不申请破产|受政策影响|加速[^。]{0,15}恢复经济|释放了信号|重要一步',text)
    if assessment and not re.search(r'(?:宣布|决定|颁布|规定|签署|下令|制定了)[^。]{0,100}(?:补贴|关税|税收|禁止|减排目标|监管要求)',text):
        return 'commentary','','当前是效果、意义、类比或一般交流；未陈述可单独采纳的公共措施'
    if re.search(r'(?:目前|此前|今年|每年)[^。]{0,90}(?:公布的[^。]{0,20}数据|只有[^。]{0,25}充电桩|有\s*\d+\s*个[^。]{0,15}开发案|帮助抵消)|资料[，,]目前',text) and not re.search(r'规定|决定|目标是|计划到|补贴标准',text):
        return 'background','','现有装机、开发进度或抵消量是统计背景'
    if re.search(r'(?:碳定价|碳税|碳交易)(?:是|指的是|指)[^。]{0,60}(?:机制|制度|经费)',text) and not re.search(r'决定|宣布|实施|颁布|规定',text):
        return 'background','','政策工具的定义，不是某国采用该工具的事实'
    if re.search(r'主要措施包括',text) and not PUBLIC.search(text) and not re.search(r'根据[^。]{0,30}(?:规划|法律|法案)|该计划',text):
        return 'background','','通用技术路径说明，无可定位的公共采纳动作'
    if re.search(r'投资者提问|专栏文章|作者发问|扫码支付|VIP服务协议',text):
        return 'noise','','问答、付费或推荐文章残留不进入政策事实集'
    if re.search(r'将举行[^。]{0,15}(?:会议|峰会)|将.{0,15}举办[^。]{0,15}峰会|即将[^。]{0,50}举行战略对话|将于[^。]{0,30}大会将',text) and not re.search(r'签署了|正式决定|批准了|法案规定',text):
        return 'background','','会议预告，未说明已采取的具体公共措施'
    if re.search(r'作为[^。]{0,20}项目的一部分|该CCUS项目|最终决定投资后|沙特阿美',text) and not re.search(r'政府[^。]{0,30}(?:委托|拨款|批准|采购)|国家招标|根据[^。]{0,20}法律',text):
        return 'private_project','','当前是经营项目、企业目标或最终投资决定条件，不等于政府措施'
    if re.search(r'国际社会通过了.{0,10}巴黎协定|国际社会[^。]{0,50}制度安排',text) and not re.search(r'(?:政府|总统)[^。]{0,20}(?:批准|签署|决定|承诺)',text):
        return 'international_framework','','全球协定制度背景，没有具体国家本次采纳事件'
    # Publication of measurements is not publication of a rule.
    if re.search(r'(?:资料|数据|调查|统计|报告)(?:显示|表明|指出)|公布的?(?:资料|数据)|发布的?(?:资料|数据)', text) and not re.search(r'(?:决定|规定|批准|下令|将拨款|补贴标准|政策要求)', text):
        return 'background', '', '公开统计/资料的发布动作不等于公共措施的发布'
    if re.search(r'民意调查|受访|民调|调查发现|数据显示|历年统计', text) and not re.search(r'(?:政府|国会)[^。]{0,12}(?:决定|批准|规定)', text):
        return 'background', '', '民调、统计或调查结果单列'
    if re.search(r'(?:与|和)[^。]{0,65}(?:计划|努力|目标|战略)(?:相符|一致)|(?:计划|战略)[^。]{0,12}(?:相符|一致)|发出[^。]{0,18}信号|具有[^。]{0,12}重要意义|(?:是|也是)[^。]{0,16}(?:关键|重要动力|最佳方案|最有效途径)', text) and not re.search(r'(?:决定|批准|规定|下令|拨款|征收|签署)', text):
        return 'commentary', '', '当前谓词是重要性或相符性评价，不是措施动作'
    if re.search(r'不确定性|是否会[^。]{0,20}退出|值得注意|令人担忧|不难发现|由此可见|从[^。]{0,30}计划说起', text) and not re.search(r'(?:宣布|决定|批准|规定|签署|颁布)', text):
        return 'commentary', '', '引导、评价或不确定性讨论'
    if re.search(r'计划[^。]{0,20}加剧|政策[^。]{0,20}(?:带动|引发|影响)|可能[^。]{0,30}(?:就业|股价|收益)|有望[^。]{0,30}(?:就业|增长|潜力)|减排潜力', text) and not re.search(r'(?:公布|批准|规定|下令|征收|签署)', text):
        return 'commentary', '', '政策效果预测，不是新增政策事实'
    # Budget requests and alternatives must attach to their own proposal.
    if re.search(r'预算要求|预算申请|申请[^。]{0,15}预算|预算请求|要求国会[^。]{0,20}(?:拨款|提供)|向国会[^。]{0,12}(?:请求|申请)', text) and not re.search(r'已批准|通过了预算|国会批准', text):
        return 'draft', 'budget_request', '预算申请尚非获批拨款'
    if re.search(r'预算|经费', text) and re.search(r'提出|申请|希望|用于|计划', text) and re.search(r'预算要求|预算申请|申请[^。]{0,10}预算|提出在下一年度预算', before[-650:]) and not re.search(r'获批|已批准|国会通过|此前实施', text):
        return 'draft', 'budget_request', '与前文同一轮预算申请连接；不升级为已拨款'
    if re.search(r'预算|拨款',text) and (re.search(r'提出[^。]{0,20}下一年度预算',text) or re.search(r'敦促国会[^。]{0,35}(?:设立|拨款)',before)) and not re.search(r'国会已批准|正式通过|已拨款',text):
        return 'draft','budget_request','预算要求或总统敦促国会的拟议资金，不等于获批支出'
    if re.search(r'讨论预算',text):
        return 'draft','budget_discussion','文件讨论预算，未给出批准拨付动作'
    if re.search(r'根据(?:这|该|上述)|方案[一二三123]|第一种|第二种|第三种|路线图', text) and re.search(r'(?:草案|征求意见)[^。]{0,100}(?:三种|方案|路线)|(?:三种|备选)[^。]{0,50}(?:方案|路径|路线)', before) and not re.search(r'最终通过|已采纳|正式实施|此前已', text) and not adopted_roadmap_anchor(text,start,full):
        return 'draft', 'alternative_in_draft', '同一草案的备选路径，未将其中任一路径写为已采取'
    if re.search(r'(?:政府|总统|首相|总理)可以(?:重新|要求|采取|利用|审视|撤销|加快)',text) and not re.search(r'法律规定|法案规定|授权|允许|批准|规定可以|宣布|决定|已经',text):
        return 'discussion','proposed_change','政府可以采取的可选路径，未交代正式决定或法律授权'
    if re.search(r'当选后(?:将|推行|实施|制定)|若.{0,10}当选',text) and not re.search(r'当选后已|当选后正式|当选后宣布',text):
        return 'campaign','conditional_campaign','以未来当选为条件的承诺，不因历史报道或出现总统名称变为已采取措施'
    if re.search(r'预计[^。]{0,45}将[^。]{0,25}(?:宣布|签署)|可能还会要求|将发布(?:联合)?声明',text) and not re.search(r'已经宣布|已经签署',text):
        return 'discussion','announcement_preview','知情消息或预测中的未来宣布，不能升级为正式公布'
    if re.search(r'政府可以|联邦政府可|可采取的措施', text) and re.search(r'科学家|专家|学者|建议|可以采取', before[-300:]):
        return 'discussion', 'proposed_change', '建议者提出可选措施，政府不是已采纳主体'
    if re.search(r'若[^，。]{0,10}(?:当选|胜选)|将在上任后第一天|如果[^，。]{0,10}当选',text):
        return 'campaign','conditional_campaign','当前动作明确依赖胜选/未来就职条件'
    if re.search(r'竞选团队|竞选纲领|上任的?第一年|竞选承诺中|若当选|如果当选|在上任的头\d+天', text) and not re.search(r'已(?:经)?(?:兑现|履行)|宣布兑现|就职后[^。]{0,15}(?:宣布|签署)|上任的?第一年就宣布', text):
        return 'campaign', 'campaign', '竞选平台或条件主张单列'
    if re.search(r'总统任期的?\d+年|——大力|还承诺',text) and re.search(r'竞选|候选人|选举团队|刚结束的.{0,10}大选|上任的?第一年',before) and not re.search(r'就职后.{0,10}(?:宣布|签署)|政府已宣布',text):
        return 'campaign','campaign','同一竞选/选举团队平台的后续主张，未找到新的执政决定'
    if re.match(r'\s*——',text) and re.search(r'欢迎拜登当选|拜登团队',full[:1800]) and re.search(r'让这些计划能够在国会获得通过',full[:1800]):
        return 'campaign','campaign','未获国会通过的候任团队平台条目'
    if re.search(r'清洁能源革命和环境计划',text) and re.search(r'总统上任的第一年',full[start:start+1500]):
        return 'campaign','campaign','同一总统竞选计划，第一年立法仍为承诺'
    if re.search(r'主推的方向|准备放弃[^。]{0,20}福利计划|行动要点[^。]{0,80}需要投资',text):
        return 'discussion','proposed_change','党派议案推进或行动建议，未表明已获采纳'
    if re.search(r'将签署|拟签署',text) and not re.search(r'已签署|签署了|已经签署',text) and not public_goal_statement(text):
        return 'discussion','announcement_preview','签署预告，不能标记成已签署或已取消'
    if re.search(r'政府计划|政府将|计划到',text) and re.search(r'草案中确定|这份路线图草案|上述规划和目标仍然是暂定计划',before[-800:]) and not re.search(r'此前|原定|曾表示|已正式|已经通过',text):
        categories=[r'汽车|电池',r'氢',r'核能|核电',r'光伏|太阳能']
        if any(re.search(p,text) and re.search(p,before[-800:]) for p in categories):
            return 'draft','draft_strategy_task','同一草案的后续任务，尚无正式采纳证据'
    if re.search(r'(?:^|[，,])(?:该|这家|此)?(?:公司|集团)|阿美公司|SK[^。]{0,12}(?:集团|计划)|集团主席|企业(?:已|将|计划|承诺)', text) and re.search(r'计划|承诺|宣布|投资|建设|出口|生产|减排|研发', text):
        regulated = re.search(r'政府[^。]{0,45}(?:批准|委托|资助|要求)|法律|法规定|达不到.{0,15}标准|合格.{0,15}成本|国家[^。]{0,15}招标|监管要求', text)
        if not regulated and not re.search(r'(?:政府|总统|部)[^。]{0,25}(?:公布|决定|规定|拨款|下令)', text):
            return 'private_project', '', '企业为当前承诺/投资/生产主体，非国家公共措施'
    return None


def context_owner(ref, text, start, full, direct=False):
    """Prefer explicit actors; connect execution only to a bounded public anchor."""
    ms = [x for x in ref.mentions(text, start) if x.get('public') and x.get('level') != 'local' and x.get('role') not in {'target', 'private_or_context', 'location'}]
    specific=[x for x in ms if x.get('text')=='REPDO' and x['country']=='沙特阿拉伯']
    if specific and re.search(r'REPDO[）)](?:具体)?负责',text):
        return dict(countries=['沙特阿拉伯'],actors=specific,connection=[],basis='具体机构REPDO及负责动作；专名优先于能源部等跨国通用机构词',kind='explicit')
    cs = {x['country'] for x in ms} & G20
    if len(cs) == 1 and (DOMAIN.search(text) or direct):
        return dict(countries=sorted(cs), actors=ms, connection=[], basis='当前公共主体与本句措施动作', kind='explicit')
    if len(cs) > 1 and DOMAIN.search(text) and re.search(r'共同|双方|联合|两国', text) and re.search(r'发起|签署|成立|建立|同意', text):
        return dict(countries=sorted(cs), actors=ms, connection=[], basis='共同公共动作的多个参与方', kind='joint')
    if direct:
        # Country belongs to a policy subject, not any country name in an object.
        m = re.search('('+COUNTRY+r')(?:政府)?(?:曾|已|将|还|计划|承诺|宣布|政府规划|[^，。]{0,8}愿景)', text)
        if m:
            return dict(countries=[CANON.get(m[1], m[1])], actors=ms, connection=[], basis='国名与规划/目标/措施谓词的直接连接', kind='explicit')
    lo = max(0, start - 1800)
    spans = list(re.finditer(r'[^。！？\n]+[。！？\n]*', full[lo:start]))
    # A public meeting followed by its agenda is one bounded linking path.
    if re.search(r'双方同意.{0,15}(?:成立|建立)',text):
        nearby=full[max(0,start-600):start]
        actors=[x for x in ref.mentions(nearby,max(0,start-600)) if x.get('public') and x.get('level')!='local' and x.get('role') not in {'target','private_or_context','location'}]
        cc={x['country'] for x in actors}&G20
        if len(cc)==2 and re.search(r'会见|两国',nearby) and DOMAIN.search(nearby) and re.search(r'合作',nearby):
            return dict(countries=sorted(cc),actors=actors,connection=[dict(start=max(0,start-600),end=start,text=nearby)],basis='公共会见双方→同一议程→建立合作机制',kind='joint')
    for m in reversed(spans):
        q = m[0]; a = lo+m.start(); b=lo+m.end(); bridge=full[b:start]
        if re.search(r'以下.{0,12}建议|专家建议如下|观点如下|公司介绍自己的计划', bridge):
            break
        if exclusion(q,a,full):
            prior=re.search(r'前任总统[^，。]{0,10}的[“《][^”》]{2,40}(?:计划|法案|法规)[”》]',q)
            if prior and re.search(r'该计划|这项计划',text) and len(countries(q))==1:
                return dict(countries=sorted(countries(q)),actors=[],connection=[dict(start=a+prior.start(),end=a+prior.end(),text=prior[0])],basis='未来撤销动作的对象是前任已存在政策；当前条款连接历史对象而非拟议撤销动作',kind='linked')
            continue
        if not DOMAIN.search(q):
            continue
        country_action=bool(re.search('('+COUNTRY+r')(?:首先|将|已|曾|政府)?(?:颁布|实施|立法|推行|加强|计划|承诺|经济产业|经产省)|('+COUNTRY+r')已经与[^。]{0,45}签署',q))
        public_fact = bool((PUBLIC.search(q) or country_action or (len(countries(q))>1 and re.search(r'联合发起',q))) and (DECISION.search(q) or re.search(r'同意|会见|讨论.{0,35}合作|规划|推行|联合发起|公布|实施|加强|计划|政府提出到20\d{2}年|邀请.{0,35}投标', q)))
        # A previously enacted law remains a valid anchor even when an article
        # discusses future repeal of that law.
        historical = bool(re.search(r'奥巴马于2015年推行|(?:政府|国会)[^。]{0,25}(?:颁布|实施|通过)', q))
        if not public_fact and not historical:
            continue
        if re.search(r'草案|尚未|未获|竞选|将公布|拟发布', q) and not historical:
            continue
        actors=[x for x in ref.mentions(q,a) if x.get('public') and x.get('level')!='local' and x.get('role') not in {'target','private_or_context','location'}]
        cc={x['country'] for x in actors}&G20
        if not cc and (len(countries(q))==1 or re.search(r'联合发起',q)):
            cc=countries(q)
        if not cc:
            continue
        current = countries(text)
        if current and not current.issubset(cc):
            continue
        if len(cc)>1 and not (re.search(r'双方|共同|两国|上述合作|该倡议',text) and re.search(r'合作|会见|共同|联合',q)):
            continue
        if re.search(r'(?:公司|企业|集团)[^。]{0,25}(?:自主|自己的|宣布|投资|开发)',bridge) and not re.search(r'政府[^。]{0,25}(?:委托|资助|要求)',bridge) and not (re.search(r'电力采购公司.{0,25}协议购买电力',text) and re.search(r'签署.{0,12}电力购买协议',q)):
            continue
        return dict(countries=sorted(cc),actors=actors,connection=[dict(start=a,end=b,text=q)],basis='具体执行表达→同政策公共锚点→主体国家',kind='joint' if len(cc)>1 else 'linked')
    # Whole-document lookup is limited to an explicit national strategy section
    # for a technical target which itself names that country (not a bare pronoun).
    if re.search(r'相关技术.{0,15}要达到|技术水平.{0,15}达到',text) and len(countries(text))==1:
        c=next(iter(countries(text)));prefix=full[:start]
        patterns=list(re.finditer(re.escape(c)+r'[^。\n]{0,80}(?:发布|公布|制定|出台|修订)[^。\n]{0,80}(?:氢能|氢能源)[^。\n]{0,30}(?:战略|路线图)[^。\n]*',prefix))
        if patterns:
            m=patterns[-1]
            if not re.search(r'草案|尚未',m[0]):return dict(countries=[c],actors=[],connection=[dict(start=m.start(),end=m.end(),text=m[0])],basis='当前国名技术任务→全文同国已发布氢能战略',kind='linked')
    return None


def recovery(ref, events, record, full, doc):
    """Recover strongly typed assertions before inherited fragment losses."""
    if any(e.get('decision_origin')=='fixed_review_input' for e in events):
        return None
    a,b=record['start'],record['end'];t=full[a:b];before=full[max(0,a-1800):a]
    if len(t)>1600 or not t.strip():
        return None
    media=re.match(r'(?:中国|北极星)[^，。]{0,15}网讯[:：]',t)
    if media:a+=media.end();t=full[a:b]
    intro=re.search(r'值得注意的是[，,]?',t)
    if intro and re.search(r'首次被纳入修订后的.{0,15}能源计划',t[intro.end():]):
        a+=intro.end();t=full[a:b]
    if public_goal_statement(t) and DOMAIN.search(t):
        owner=context_owner(ref,t,a,full,direct=True)
        if owner:
            return ref.emit(record,events,full,[dict(parts=[(a,b)],owner=owner,state='announced_goal',rule='announced_goal_pending_instrument_signature',reason='公共主体已发布声明公布目标；保留将签署原文限定，不将尚待签署的行政令标记为已经签署或实施')])
    withdrawn=re.search(r'(特朗普|拜登|奥巴马)(?:政府)?(?:当选并)?((?:宣布)?(?:退出了?|撤销)[《“][^》”]{2,35}[》”])',t)
    if withdrawn and re.search(r'意味着|情况之下|言论|其实不然',t) and not re.search(r'若当选|如果当选|计划撤销|将撤销|将退出',t[:withdrawn.end()]):
        owner=context_owner(ref,withdrawn[0],a+withdrawn.start(),full,direct=True)
        if owner:
            state='announced_withdrawal' if '宣布' in withdrawn[2] else 'cancelled_or_withdrawn'
            return ref.emit(record,events,full,[dict(parts=[(a+withdrawn.start(1),a+withdrawn.end(1)),(a+withdrawn.start(2),a+withdrawn.end(2))],owner=owner,state=state,rule='literal_withdrawal_inside_commentary',reason='只保存评论中明确声称的既有撤销/退出动作；评论推论与未来预测分开')])
    # A quoted national pledge may appear in a commentary article. Keep its
    # literal content only when the nearby speaker is an identifiable public actor.
    pledge=re.search(r'所作出的[^。]{0,12}政治承诺是[:：]((?:'+COUNTRY+r')[^。]{0,90}(?:净零排放|碳中和)[^。]*)',t)
    if pledge:
        q=pledge[1];actors=[x for x in ref.mentions(full[max(0,a-1000):a],max(0,a-1000)) if x.get('public') and x.get('level')!='local' and x.get('role') not in {'target','location','private_or_context'}]
        cs=countries(q);speaker=[x for x in actors if x['country'] in cs]
        if len(cs)==1 and speaker:
            x=speaker[-1];owner=dict(countries=sorted(cs),actors=[x],connection=[dict(start=x['start'],end=x['end'],text=full[x['start']:x['end']])],basis='当前引述承诺→前文公共领导人→同国，未把评论者作为施策主体',kind='linked')
            return ref.emit(record,events,full,[dict(parts=[(a+pledge.start(1),a+pledge.end(1))],owner=owner,state='announced_goal',rule='public_pledge_inside_commentary',reason='保留公开讲话中原样引述的国家承诺；导语评价另存，不推断已经立法或实现')])
    task=re.search(r'(?:菅义伟|首相|总统|总理)表示[，,](.+?)(?:将是关键)[，,]((?:'+COUNTRY+r')将加强对这些领域的研究与开发)',t)
    if task and DOMAIN.search(task[1]) and not re.search(r'候选人|若当选|竞选',t):
        owner=context_owner(ref,t,a,full,direct=True)
        if owner:
            parts=[(a+task.start(1),a+task.end(1)),(a+task.start(2),a+task.end(2))]
            cleaned=[]
            for x,y in parts:
                pos=x
                for stock in re.finditer(r'[（(]\d{6}[,，]股吧[)）]',full[x:y]):
                    if pos<x+stock.start():cleaned.append((pos,x+stock.start()))
                    pos=x+stock.end()
                if pos<y:cleaned.append((pos,y))
            return ref.emit(record,events,full,[dict(parts=cleaned,owner=owner,state='announced_plan',rule='public_research_task_with_topic_reference',reason='保留国家研发任务与这些领域的技术先行词；重要性评价、股吧代码及非双碳数字化尾句分开')])
    # An explicitly quoted adopted goal survives inside a corporate reaction.
    goal=re.search('(?:'+COUNTRY+r')(?:首相|总统|总理|政府)[^，。]{0,75}(?:做出的|作出的|宣布的|提出的)[^，。]{0,60}(?:承诺|目标)',t)
    if goal and DOMAIN.search(goal[0]) and not re.search(r'候选人|如果|若当选|竞选|拟提出',goal[0]):
        owner=context_owner(ref,goal[0],a+goal.start(),full,direct=True)
        if owner:return ref.emit(record,events,full,[dict(parts=[(a+goal.start(),a+goal.end())],owner=owner,state='announced_goal',rule='public_goal_inside_private_reaction',reason='企业反应中的明确已作出国家目标单独保留；企业项目与推动力评价隔离')],archive_route='private_reaction')
    # Measurements and strategy instructions in the same sentence are separate propositions.
    task=re.search(r'[“《]([^”》]{2,40}(?:战略|规划|计划))[”》](?:设定的目标是|规定|要求|提出)[^。]*',t)
    if task and re.search(r'数据|统计|排放量',t[:task.start()]) and DOMAIN.search(task[0]) and not exclusion(task[0],a+task.start(),full):
        owner=None
        for anchor in reversed(list(re.finditer(r'[^。\n]*'+re.escape(task[1])+r'[^。\n]*',full[:a]))):
            if not PUBLIC.search(anchor[0]) or not re.search(r'发布|公布|制定|批准|通过',anchor[0]) or exclusion(anchor[0],anchor.start(),full):continue
            owner=context_owner(ref,anchor[0],anchor.start(),full,direct=True)
            if owner:
                owner['connection']=[dict(start=anchor.start(),end=anchor.end(),text=anchor[0])]
                owner['kind']='linked';owner['basis']='当前战略任务→全文同名战略的公共发布主体→国家'
                break
        if owner and not ref.publication_status(task[0],a+task.start(),full):
            return ref.emit(record,events,full,[dict(parts=[(a+task.start(),a+task.end())],owner=owner,state='announced_goal',rule='strategy_task_after_statistics',reason='统计前句归背景；同句已发布战略的目标及排除条件、技术任务完整保留')],archive_route='background')
    # Preserve a past withdrawal fact when the rest is an assessment of its meaning.
    nominal=re.search(r'(?:特朗普|[^，。]{1,8})政府(?:正式)?退出《巴黎协定》(?=是在)',t)
    if nominal:
        owner=context_owner(ref,nominal[0],a+nominal.start(),full,direct=True)
        if owner:return ref.emit(record,events,full,[dict(parts=[(a+nominal.start(),a+nominal.end())],owner=owner,state='cancelled_or_withdrawn',rule='past_fact_before_assessment',reason='历史退出事实与治理效果评价分开')])
    embedded=re.search(r'(特朗普|奥巴马|拜登)(?:政府)?[^，。]{0,35}最明显的标志[，,]是(宣布退出巴黎气候协定)',t)
    if embedded:
        owner=context_owner(ref,embedded[1]+embedded[2],a+embedded.start(),full,direct=True)
        if owner:return ref.emit(record,events,full,[dict(parts=[(a+embedded.start(1),a+embedded.end(1)),(a+embedded.start(2),a+embedded.end(2))],owner=owner,state='announced_withdrawal',rule='withdrawal_within_assessment',reason='只保留同一主体与宣布退出动作，最明显标志及唯一国家等评价归档')])
    # Split only observable changes of proposition/subject; conditions stay intact.
    cuts=list(re.finditer(r'[，,；;](?=(?:如今[^，。]{0,12}声音|沙特阿美公司|[^，。]{0,12}公司去年|威尼斯政府|这意味着|这能够|这可能(?:令|让|使)|因目标.{0,10}诟病|这\d+座(?:核电站)?已经|将在下一财年申请|这将为超过|也引起了[^。]{0,30}担忧|同时[，,]?[^，。]{0,12}政府也配备))',t))
    end=cuts[0].start() if cuts else len(t)
    core=t[:end]
    if exclusion(core,a,full):
        return None
    if re.search(r'(?:省|市|区|县|州)(?:人民)?政府|省发改委|市发改委',core) and not re.search(r'国家发改委|国家发展改革委|国务院|中央政府|联邦政府|国家能源局|联邦[^。]{0,8}法院|最高法院',core):
        return None
    # Existing adoption may be quoted in an advocacy paragraph, but the outer
    # advocacy is never inherited by the extracted fact.
    strong = bool(
        re.search(r'根据[^，。]{0,20}政府规划[^。]{0,140}(?:预计|将|目标)',core)
        or re.search(r'(?:政府|总统|拜登|特朗普)[^。]{0,30}(?:宣布|公布|命令|下令|下达|曾表示|计划到|指定|大幅降低|关闭了)',core)
        or re.search(r'(?:交通部|能源部|国家发改委)[^。]{0,20}(?:下令|印发|批准)',core)
        or re.search(r'根据[^。]{0,22}愿景[^。]{0,40}(?:将|推动|发展)',core)
        or re.search(r'大臣[^。]{0,18}透露[^。]{0,25}计划在[^。]{0,30}氢能源供应链',core)
        or re.search('('+COUNTRY+r')已经与[^。]{0,40}签署.{0,10}电力购买协议',core)
        or re.search('(?:'+COUNTRY+r')已经决定[^。]{0,100}[；;]同时支持可再生能源',core)
    )
    adopted=adopted_roadmap_anchor(core,a,full)
    typed = bool(adopted and re.search(r'目标|比例.{0,15}将|二氧化碳当量.{0,15}将',core) or
        re.search(r'REPDO[）)](?:具体)?负责',core)
        or re.search(r'(?:'+COUNTRY+r')已经决定[^。]{0,100}[；;]同时支持可再生能源',core)
        or
        re.search(r'政府[^。]{0,45}关闭了[^。]{0,30}[；;][^。]{0,35}政府[^。]{0,12}关闭了',core)
        or
        re.search(r'(?:生产企业|企业).{0,10}若达不到.{0,20}标准.{0,15}处罚',core)
        or re.search(r'(?:并网|电网).{0,60}(?:成本分摊|分摊机制)',core)
        or re.search(r'(?:上网电价|FIT价格).{0,40}(?:降到|降至|为|提高到).{0,15}(?:円|元|kWh)',core,re.I)
        or re.search(r'(?:赠款|补助).{0,40}(?:合格|符合条件).{0,20}(?:成本|支出).{0,15}[%％]',core)
        or re.search(r'(?:相关技术|技术水平).{0,12}(?:要达到|达到世界最高)',core)
        or re.search(r'(?:共同发起|双方同意成立|双方同意建立).{0,35}(?:倡议|机制|对话)',core)
        or re.search(r'该计划.{0,18}(?:燃煤|电厂).{0,20}(?:制定|规定).{0,15}(?:减排|标准)',core)
        or re.search(r'政府已指定.{0,35}港口',core)
        or re.search(r'农业部[^。]{0,35}发布[^。]{0,25}试点项目的信息要求',core)
        or re.search(r'保证金[^。]{0,20}(?:円|元)/kW|中标者需要在.{0,12}保证金',core)
        or re.search(r'这些项目的综合发电容量|对\d+个新能源项目[^。]{0,50}招标',core)
        or re.search(r'电力采购公司将根据[0-9—-]+年协议购买电力',core)
        or re.search(r'海洋能源管理局正在探索[^。]{0,110}可租赁的水域',core)
        or re.search(r'政府开始重新审查该项目',core)
        or re.search(r'联邦上诉法院[^。]{0,30}暂停执行',core)
        or re.search(r'国家电力公司.{0,15}正在扩大.{0,25}生物质耦合',core)
        or re.search(r'核电站[^。]{0,80}运行的最后一天[^。]{0,30}退役',core)
        or re.search(r'首次被纳入修订后的.{0,15}能源计划',core)
    )
    if not strong and not typed:
        return None
    target_expression=bool(re.search(r'根据[^，。]{0,20}政府规划|政府还计划到',core))
    if any(keep(e) for e in events) and not typed and not cuts and not target_expression:
        return None
    old_block=ref.nonpolicy(core,a,full)
    incumbent=bool(re.search(r'美国总统拜登(?:近期|近日)?宣布',core) and not re.search(r'当选总统|候任|竞选|将宣布|若当选',core))
    if old_block and not (typed or target_expression or (incumbent and old_block[0]=='campaign')):
        return None
    owner=context_owner(ref,core,a,full,direct=strong)
    if adopted and not owner and len(countries(adopted['text']))==1:
        owner=dict(countries=sorted(countries(adopted['text'])),actors=[],connection=[adopted],basis='同名路线图的最终采纳事实→当前目标；保留并列情景而不写成已经实现',kind='linked')
    if not owner:
        m=re.search('首次被纳入修订后的('+COUNTRY+r')能源计划',core)
        if m:owner=dict(countries=[CANON.get(m[1],m[1])],actors=[],connection=[],basis='原文明示该国家能源计划已纳入的能源类型',kind='explicit')
    if not owner and re.search(r'运行的最后一天[^。]{0,30}退役',core):
        tail=full[b:b+800];m=re.search(r'默克尔政府决定逐步退出核电计划',tail)
        if m and countries(core)=={'德国'}:
            owner=dict(countries=['德国'],actors=[],connection=[dict(start=b+m.start(),end=b+m.end(),text=m[0])],basis='本句法定退役执行→后文同国政府退出核电决定',kind='linked')
    if re.search(r'电力采购公司将根据',core) and not re.search(r'(?:签署|签订).{0,20}电力购买协议|政府.{0,30}招标',before):return None
    if re.search(r'国家电力公司',core) and not re.search(r'政府计划[^。]{0,140}生物质',before):return None
    if not owner or not (DOMAIN.search(core) or (typed and owner['connection'])):
        return None
    # Strong action is not enough if it is still a draft/campaign/suggestion.
    st=ref.publication_status(core,a,full)
    if st and st[0]=='campaign' and re.search(r'美国总统拜登(?:近期|近日)?宣布',core) and not re.search(r'当选总统|候任|竞选|将宣布|若当选',core):st=None
    oldlaw=bool(re.search(r'该计划.{0,18}(?:燃煤|电厂).{0,20}(?:制定|规定)',core) and re.search(r'2015年推行',before))
    if st and not oldlaw and not adopted:
        return None
    if re.search(r'政府已指定.{0,35}港口',core) and not re.search(r'海上风电|近海风电',before):
        return None
    state='execution_requirement' if typed and not re.search(r'共同发起|双方同意',core) else ref.state(core,'announced_plan')
    if re.search(r'命令.{0,20}审查|下令.{0,20}审查',core):state='announced_review'
    elif re.search(r'关闭了',core):state='implementation'
    elif re.search(r'共同发起|双方同意',core):state='announced_cooperation'
    elif re.search(r'政府曾表示|根据.{0,15}政府规划|政府还计划到',core):state='announced_goal'
    elif re.search(r'大幅降低|改为',core):state='revised_standard'
    elif re.search(r'正在探索|重新审查|信息要求',core):state='announced_review'
    elif re.search(r'暂停执行',core):state='suspended_by_court'
    elif re.search(r'运行的最后一天[^。]{0,30}退役',core):state='scheduled_retirement'
    elif re.search(r'宣布[，,]将制定',core):state='announced_preparation'
    if adopted:state='announced_goal'
    if re.search(r'正式宣布终结[^。]{0,45}标准[^。]{0,100}而不是之前',core):state='revised_standard'
    if re.search(r'政府[^。]{0,45}关闭了[^。]{0,30}[；;][^。]{0,35}政府[^。]{0,12}关闭了',core):state='implementation'
    if re.search(r'政府不再(?:命令|要求)',core):state='cancelled_or_withdrawn'
    p=dict(parts=[(a,a+end)],owner=owner,state=state,rule='typed_assertion_or_execution',reason='明确公共动作或同政策执行条款；条件/状态完整保留，评价或不同主体尾句隔离')
    result=ref.emit(record,events,full,[p],archive_route='commentary')
    if result:
        for e in result:e['assertion_revision']=VERSION
    return result


def audit(events, full, ref=None, doc=None):
    """Recheck the current literal assertion, including old protected fragments."""
    out=[]
    for event in events:
        if not keep(event) or event.get('decision_origin')=='fixed_review_input':
            out.append(event);continue
        block=exclusion(event['text'],event['start'],full)
        status_evidence=None
        if not block and ref is not None and doc:
            from datetime import date
            m=re.fullmatch(r'(\d{4})-(\d{1,2})-(\d{1,2})',str(doc.get('published_at','')).strip())
            if m:
                try:reported=date(*map(int,m.groups()))
                except ValueError:reported=None
                for check in getattr(ref,'lifecycle_checks',[]):
                    if reported and date.fromisoformat(check['proposal_date'])<=reported<date.fromisoformat(check['final_announcement_date']) and any(alias.lower() in full.lower() for alias in check['aliases']) and re.search(check['current_reference_pattern'],event['text'],re.I):
                        block=('draft','draft_or_proposal','已核对官方政策沿革：该报告时间的新计划尚为提案；报告日期未当作政策决定日期')
                        status_evidence=check;break
        if not block:
            if re.search(r'政府不再(?:命令|要求)',event['text']):
                event=copy.deepcopy(event);event['policy_state']='cancelled_or_withdrawn';event['state_revision_reason']='停止原监管要求，保留不再限定，非新计划'
            if re.search(r'政府(?:直接)?取消了[^。]{0,30}(?:申请许可|项目许可)',event['text']):
                event=copy.deepcopy(event);event['policy_state']='cancelled_or_withdrawn';event['state_revision_reason']='取消绑定政府对该项目许可的动作，不继承前后其他政策状态'
            out.append(event);continue
        z=copy.deepcopy(event);route,state,why=block
        z.update(route=route,policy_state=state,countries=[],policy_level='unknown',delivery_layer='隔离归档',
                 event_id=ident('A612-',(event['event_id'],route)),previous_event_ids=[event['event_id']],
                 reason='ASSERTION_REVISION：'+why,assertion_revision=VERSION,assertion_revision_rule='current_assertion_rejection')
        if status_evidence:z['external_status_evidence']=status_evidence
        out.append(z)
    return out
