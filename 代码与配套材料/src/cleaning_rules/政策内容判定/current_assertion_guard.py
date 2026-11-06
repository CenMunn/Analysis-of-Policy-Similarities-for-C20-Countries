"""当前主断言核验：不读取国别分数、记录编号或参考标签。"""
import re

ADOPTION=re.compile(r'(?:政府|内阁|国会|总统|首相|总理|部委)[^。；]{0,20}(?:批准|签署|颁布|决定|正式发布|正式公布|出台)|(?:法案|法律|条例)[^。；]{0,8}(?:生效|通过)')
CONCRETE=re.compile(r'补贴|税率|抵免|征收|配额|拨款|采购|招标|认证|许可|禁止|淘汰|标准|\d[\d.,]*\s*(?:%|％|美元|欧元|日元|韩元|英镑|万元|亿元)')

def assertion_exclusion(text):
    """返回处置/状态/理由。只识别清楚的反例，不把所有未命中句一律排除。"""
    t=text.strip(' \n“”"')
    if re.search(r'账号登录|新浪QQ微信|指导价机制.{0,70}(?:院士|认为)',t):
        return 'quality_unknown','unknown','登录组件或不同新闻黏连，完整政策事实范围尚不可靠'
    if re.search(r'(?:根据|在)[^。；]{0,45}(?:一份排名|吸引力排名|排行榜)',t) and not ADOPTION.search(t):
        return 'background','','投资吸引力/市场排名，不是公共措施'
    if re.search(r'必要的(?:政策措施|政策支持)(?:和目标)?',t) and not CONCRETE.search(t):
        return 'content_uncertain','','政策支持泛称没有交代具体工具、目标或执行内容'
    if re.search(r'积极开展与[^。；]{0,45}(?:相关合作|有关合作)',t) and not re.search(r'签署|签订|拨款|批准|《[^》]+》|升级.{0,15}对话',t):
        return 'background','','国际合作概述，具体共同决定和执行安排须另抽'
    if re.search(r'《巴黎协定》[^。；]{0,30}(?:确定|确立)[^。；]{0,35}基本框架',t) and not re.search(r'(?:中国|美国|日本|韩国|德国|法国|英国).{0,12}(?:加入|批准|退出|承诺)',t):
        return 'international_framework','','全球框架介绍，不是某国采取措施'
    if re.match(r'(?:该|此)项目.{0,22}(?:开工|动工)',t) and re.search(r'拖期|投资额飙升|推迟投运',t) and not ADOPTION.search(t):
        return 'private_project','','项目建设进度及投资变化，没有当前公共决定'
    current_support=bool(re.search(r'(?:政府|总统|首相|部)[^。；]{0,12}(?:声明|宣布|表示|承诺)',t) and re.search(r'提供.{0,12}(?:资金|技术援助)|拨款|拨付|采购|税率|配额|认证条件',t))
    if re.search(r'(?:项目|计划|政策|举措)(?:将|有望|预计将).{0,12}(?:解决|带动|促进|有助于)',t) and not ADOPTION.search(t) and not current_support:
        return 'commentary','','项目或政策的效果预测，不等于措施事实'
    if re.search(r'(?:机组|电站)[^。；]{0,40}(?:全球首座|世界首座|争取.{0,12}订单)',t) and not re.search(r'政府.{0,15}(?:拨款|批准|资助|采购|许可)',t):
        return 'background','','工程成果、商运预期或订单前景，不是公共政策决定'
    if re.search(r'下周前往.{0,35}(?:活动|参观|访问)|出席.{0,35}(?:签约仪式|开幕式)',t) and not re.search(r'拨款|批准|签署.{0,20}(?:法|条例|协议)',t):
        return 'introduction','','人物行程/出席活动，不是采取公共措施'
    if re.search(r'(?:最佳发展|基准|发展|最优)情景下',t) and not re.search(r'确定.{0,10}目标|(?:采纳|批准|采用).{0,10}(?:情景|方案)',t):
        return 'background','scenario','情景测算未证明已作为国家目标采纳'
    if re.search(r'(?:发布|公布)的最新研究|(?:研究报告|模型测算|研究测算).{0,20}(?:预计|显示|表明)',t) and not ADOPTION.search(t):
        return 'background','scenario','研究测算和备选路径，与正式采纳分开'
    if re.search(r'根据[“"《]?[^，。；]{2,35}(?:委员会|协会|智库)[^，。；]{0,20}(?:计划|提案)',t) and not ADOPTION.search(t):
        return 'discussion','draft_or_proposal','非政府组织方案，未陈述政府采纳'
    if re.search(r'(?:政府|白宫|总统)[^。；]{0,20}希望(?:结束|取消|削减|废除)',t) and not ADOPTION.search(t):
        return 'discussion','proposed_change','表达调整愿望，未证明措施已经取消或终止'
    if re.search(r'(?:将|拟)(?:在[^，。；]{0,12})?(?:正式)?(?:推出|发布|公布|制定)[^。；]{0,24}(?:国家战略|能源战略|氢能源战略)',t) and not re.search(r'已经发布|正式发布了|正式公布了|已通过',t):
        return 'discussion','announced_intention','预告日后发布战略，不作为已公布的战略内容'
    if re.search(r'需要加大[^。；]{0,20}进口力度|延续了[^。；]{0,25}领导作用|发挥领导作用的传统',t) and not CONCRETE.search(t) and not ADOPTION.search(t):
        return 'commentary','','必要性、领导作用或意义评价，未交代具体公共工具'
    # 当前主句是企业声明；前置的行政令只作背景，不能借其主体通过。
    if re.search(r'(?:公司|微软|亚马逊|苹果|谷歌)[^。；]{0,45}(?:发表联合声明|表示将继续|重申支持)',t) and not re.search(r'政府.{0,15}(?:拨款|资助|委托|采购|批准)',t):
        return 'private_reaction','','企业对政策的反应与自主目标，不是行政令措施内容'
    return None

def platform_context(text,full,start):
    """同一人物的竞选/候任平台连接；不按人物名字或报道日期单独判竞选。"""
    for person in ['拜登','特朗普']:
        before=full[:start]
        parallel=bool(re.match(r'\s*另一方面',text) and re.search(person+r'(?:政府)?[^。！？\n]{0,80}一方面[^。！？\n]{0,180}[；;，,]\s*$',before[-250:]))
        if (person not in text and not parallel) or not re.search(r'将|提出|计划|新政|承诺|要求|确保',text):continue
        patterns=[r'(?:总统候选人|候任总统|当选总统)[^。；]{0,20}'+person,
            person+r'[^。；]{0,25}(?:总统候选人|将在上任|在上任后|当选就任)',
            r'如果'+person+r'(?:胜选|成功入主白宫|当选)']
        hits=[m for p in patterns for m in re.finditer(p,before)]
        if not hits:continue
        anchor=max(hits,key=lambda m:m.start());bridge=before[anchor.end():]
        # 已就职或明确当前已采纳动作优先，不把早年的竞选背景传到后来决定。
        if re.search(person+r'.{0,16}(?:已经|已|正式)?(?:宣誓就职|就任总统|正式上任)|(?:上任后|就职后).{0,8}(?:已|正式)',bridge):continue
        current_adoption=bool(ADOPTION.search(text) or re.search(person+r'(?:总统)?(?:已|已经|正式|刚刚)+(?:签署|批准|颁布|公布|宣布)',text))
        if current_adoption and re.search(r'已经|正式|已批准|已签署|已颁布',text) and not re.search(r'如果|若当选|尚未|并未|未能',text):continue
        return dict(start=anchor.start(),end=anchor.end(),text=anchor.group(),reason='同一人物竞选/候任平台；无已就职或当前采纳证据')
    return None

def prediction_tail(text):
    """只拆清楚的逗号后效果尾句；条件、义务、金额及时间要求不能被删成预测。"""
    m=re.search(r'[，,](?=(?:预计|有望|分析师认为|专家认为|这将有助于|这将带动))',text)
    if not m:return None
    before,tail=text[:m.start()],text[m.end():]
    if re.search(r'如果|除非|只有|倘若|尚未|未获',before):return None
    if re.search(r'必须|不得|才能|方可|条件|税率|补贴|抵免|截止|提交|目标|20\d\d|\d[\d.]*\s*(?:美元|欧元|元|%|％)',tail):return None
    if not re.search(r'就业|股价|增长|成本|市场|竞争力|经济|收益|投资',tail):return None
    return m.start()
