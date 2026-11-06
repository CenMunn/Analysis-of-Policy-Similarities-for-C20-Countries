"""国家层级政策口径。规则性等级不是校准概率；原文区间均为analysis_text字符索引。"""

import copy,hashlib,json,re

from collections import defaultdict

from ..主体与国家归属.role_resolution import PendingResolver,G20,names

from ..政策归并与导出.registry_primitives import norm

VERSION='national-scope-20261022.6'

WEIGHTS={'E':.60,'P':.15,'D':.20,'M':.05}

PARAMETERS=dict(version=VERSION,country_weights=WEIGHTS,same_paragraph_max_gap=1200,named_roadmap_list_max_gap=4000,
    source_inference_requires=['公共措施成立','国家层级成立','无明确相反施策国家','来源为G20'],
    source_confidence='来源推定，较低；规则性证据等级，非校准概率',
    main_states=['announced_or_adopted','announced_goal','implementation','cancelled_or_withdrawn','suspended','conditional_arrangement','announced_phaseout'],
    holdout='开发与抽查排除留出文章；冻结规则后只生成全量盲预测，不读取或修改答案',
    duplicate_method='先按国家参与集合、层级、状态、完整规范原文精确去重；同政策名称归组仅作待核关联，不吞并新增细则和版本',
    local_policy_rule='地方独立政策统一排除；明确落实国家政策只作执行关联，地方新增要求仍地方归档',
    unassigned_rule='公共政策成立但国家仍不明：主体国家不明；不进入国家比较',
    analysis_time_scope='历史材料全部可用政策动作时间；不解释为现行政策。两配置使用相同范围，另导出日期缺失标记')

TOPIC=re.compile(r'双碳|碳中和|碳达峰|碳排放|碳税|碳交易|碳市场|净零|低碳|减排|脱碳|温室气体|气候|全球变暖|巴黎协定|京都议定书|二氧化碳|清洁能源|新能源|可再生|绿色能源|能源转型|能源效率|能效|节能|光伏|太阳能|风电|风能|风力发电|核电|民用核|核能|反应堆|氢能|氢气|氢能源|燃料电池|电动车|电动汽车|新能源汽车|零排放|零碳|充电|燃油车|燃油汽车|燃煤|煤炭|煤电|清洁电力|碳捕|碳封|CCS|CCUS')

TOPIC=re.compile(TOPIC.pattern+r'|绿氢|绿色氢|氢经济|加氢站|制氢|储能|需求响应|上网电价|燃油经济性|国家自主贡献|NDC')

INSTRUMENT=re.compile(r'政策|法案|条例|法规|法律|法令|修正案|议定书|公约|规划|战略|计划|路线图|方案|目标|承诺|补贴|补助|拨款|预算|投入|投资|税|基金|财政|标准|配额|排放权|禁售|禁止|淘汰|采购|电价|拍卖|招标|协议|协定|备忘录|实施|减排|碳中和|净零|碳达峰|(?:减少|替代).{0,12}传统能源')

ACTION=re.compile(r'禁止销售|征求意见|达成一致|宣布|公布|发布|颁布|制定|制订|修订|批准|通过|签署|签订|提交|承诺|重申|决定|设定|确定|实行|实施|征收|加征|取消|废除|暂停|冻结|退出|重返|恢复|禁止|启动|设立|拨款|采购|购买|提供|给予|规定|要求|投入|投资|部署|力争|计划|提高|增加|减少|降低|削减|建立|支持|落实|执行|包括')

ACTION=re.compile(ACTION.pattern+r'|打造|接受|设定|提出|实现|达到')

FORMAL=re.compile(r'宣布|公布|发布|颁布|批准|通过|签署|决定|制定|规定|要求|承诺|设定|确定|提出|重申|实施|执行|拨款|征收|取消|废除|退出')

PUBLIC=re.compile(r'政府|国会|议会|内阁|财政部|能源部|环境部|环境省|经济产业省|委员会|国务院|发改委|国家能源局|生态环境部|总统|总理|首相|主席|参议院|众议院|环保署|众议员|参议员|州长|市长')

DETAIL=re.compile(r'规定|要求|必须|不得|应当|符合|条件|申请|每户|每辆|每台|补贴|补助|税率|抵扣|抵免|上限|减免|有义务|用于|包括|落实|执行|建设费|运维费')

PRIVATE=re.compile(r'公司|企业|集团|厂商|大学|学院|研究院|协会|专家|学者|分析师|投资者|记者|开发商')

POLICY_REF=re.compile(r'该(?:计划|法律|法案|政策|战略|规划|措施|目标|方案|协议|规定)|这项(?:法律|政策|计划|措施)|上述(?:措施|政策|计划)|根据(?:该|现行)|按照(?:该|上述)|依据(?:该|上述)|《[^》]+》')

ACTOR_REF=re.compile(r'^(?:[“”\s]*(?:同时|此外|另外|为此|其中|同年|因此|并且)[，,]?\s*)?(?:政府|联邦政府|中央政府|总统|首相|总理|有关部门|该国|该部|国会|参议院|众议院|内阁|我们|他|她|其政府)')

CONTEXT_SWITCH=re.compile(r'另一方面|相比之下|反观|另据|其他新闻|相关阅读|专家认为|分析师认为|笔者认为|我们建议')

NATIONAL_SCOPE=re.compile(r'全国|国家(?:层面|目标|战略|计划|规划|能源|政策|法律)|联邦(?:政府|经济事务和能源部长|环境局|内阁)|中央政府|中央人民政府|中央财政|中央部门|国会|议会|内阁|参议院|众议院|总统|总理|首相|国务院|发改委|生态环境部|国家能源局|财政部|经济产业省|环境省|国家碳|关税')

AUTHORITIES={
 '中国':['中华人民共和国国务院','中共中央国务院','中华人民共和国生态环境部','国家发展和改革委员会','国家发改委','国家能源局','生态环境部','国务院','中央人民政府','全国人大常委会','全国人民代表大会','中共中央','习近平','李克强'],
 '美国':['美国联邦政府','美国国家环境保护局','美国环境保护署','美国环保署','EPA','白宫','拜登','奥巴马','特朗普','美国能源部','美国国会','美国参议院','美国众议院'],
 '日本':['日本经济产业省','经济产业省','日本环境省','日本内阁','日本国会','日本国土交通省','菅义伟','安倍晋三','岸田文雄','野田佳彦'],
 '韩国':['韩国产业通商资源部','韩国环境部','韩国国会','韩国2050碳中和委员会','韩国国务会议','青瓦台','文在寅','李明博'],
 '德国':['德国联邦政府','德国联邦议院','德国联邦经济和能源部','德国联邦环境部','德国政府','默克尔','朔尔茨'],
 '法国':['法国政府','法国国民议会','法国参议院','马克龙','奥朗德','萨科齐'],
 '英国':['英国政府','英国议会','英国下议院','英国上议院','英国财政部','约翰逊','特雷莎·梅','卡梅伦'],
 '意大利':['意大利政府','意大利议会','意大利内阁'],
 '俄罗斯':['俄罗斯政府','俄罗斯国家杜马','普京','梅德韦杰夫'],
 '印度':['印度政府','印度内阁','印度新能源和可再生能源部','莫迪'],
 '印度尼西亚':['印尼政府','印尼国会','印尼能源和矿产资源部','印度尼西亚政府','佐科'],
 '沙特阿拉伯':['沙特政府','沙特能源部','沙特王国能源部','沙特阿拉伯政府','穆罕默德·本·萨勒曼'],
 '南非':['南非政府','南非议会','南非内阁','拉马福萨'],
 '加拿大':['加拿大联邦政府','加拿大政府','加拿大议会','特鲁多'],
 '澳大利亚':['澳大利亚联邦政府','澳大利亚政府','澳大利亚议会','莫里森'],
 '阿根廷':['阿根廷政府','阿根廷国会'], '巴西':['巴西政府','巴西国会','博索纳罗','卢拉'],
 '墨西哥':['墨西哥政府','墨西哥国会','墨西哥能源部'], '土耳其':['土耳其政府','土耳其议会','埃尔多安'],
 '欧盟':['欧盟委员会','欧盟理事会','欧洲理事会','欧洲议会','欧盟政府','欧委会'],
}

REGIONS={
 '中国':['北京','上海','天津','重庆','广东','浙江','江苏','山东','安徽','吉林','山西','辽宁','黑龙江','福建','江西','河北','河南','湖北','湖南','四川','陕西','海南','广西','贵州','云南','甘肃','青海','内蒙古','宁夏','西藏','新疆','深圳','广州','杭州'],
 '美国':['加利福尼亚州','加州','纽约州','新墨西哥州','得克萨斯州','德克萨斯州','华盛顿州','马萨诸塞州','科罗拉多州','新泽西州','俄勒冈州','夏威夷州','马里兰州','康涅狄格州','洛杉矶市','纽约市'],
 '德国':['巴伐利亚州','巴登-符腾堡州','北莱茵-威斯特法伦州','柏林市','汉堡市'],
 '英国':['苏格兰','威尔士','北爱尔兰','伦敦市'], '日本':['东京都','东京市','福岛县','大阪府','神奈川县'],
 '加拿大':['魁北克省','安大略省','不列颠哥伦比亚省','阿尔伯塔省'],
 '澳大利亚':['新南威尔士州','维多利亚州','昆士兰州','南澳大利亚州','西澳大利亚州','塔斯马尼亚州'],
 '印度':['古吉拉特邦','马哈拉施特拉邦','卡纳塔克邦','泰米尔纳德邦','拉贾斯坦邦'],
 '法国':['巴黎市','法兰西岛大区'], '意大利':['威尼斯市','米兰市','罗马市','伦巴第大区'],
 '巴西':['圣保罗州','里约热内卢州'], '墨西哥':['墨西哥城'], '韩国':['首尔市','济州市','京畿道'],
 '俄罗斯':['莫斯科市'], '印度尼西亚':['雅加达省'], '南非':['西开普省','开普敦市'],
 '阿根廷':['布宜诺斯艾利斯市'], '土耳其':['伊斯坦布尔市'], '沙特阿拉伯':['利雅得市']}

LOCAL_WORDS=re.compile(r'地方政府|地方当局|州政府|州长|市政府|市长|省政府|省长|省级|市级|州议会|市议会|地方议会|县政府|自治州政府|(?<!联)邦政府|(?<!联)邦议会|都政府|府政府|大区政府')

def evidence(full,a,b,role='原文'):
    return dict(start=a,end=b,text=full[a:b],role=role)

def competition_scores(text,offset,mentions,actors,source,inherited=False):
    """沿用E/P/D/M权重及频次收缩密度，仅诊断当前事件，不裁定公共性。"""
    sentences=list(re.finditer(r'[^。！？；;\n]+[。！？；;\n]*',text));count=max(1,len(sentences));L=max(1,len(text));tau=L/count
    owners={m['country'] for m in actors};result=[]
    for c in sorted({m['country'] for m in mentions}|owners):
        positions=sorted({m['start']-offset for m in mentions if m['country']==c and m['role'] in {'public_actor','country_candidate'}})
        covered=[i for i,s in enumerate(sentences) if any(s.start()<=p<s.end() for p in positions)];n=len(positions)
        gap=(positions[-1]-positions[0])/(n-1) if n>1 else None
        tight=1/(1+gap/tau) if gap is not None else 0
        values=dict(E=(.85 if inherited else 1.) if c in owners else 0.,P=1/(1+covered[0]) if covered else 0.,
            D=n/(n+2)*(.7*len(covered)/count+.3*tight),M=1. if c==source else (0. if source else .5))
        result.append(dict(country=c,**values,score=sum(WEIGHTS[k]*v for k,v in values.items()),n=n,mean_gap=gap,
            note='当前事件的辅助评分；不是概率，不覆盖明确角色或内容/层级/状态判断'))
    return sorted(result,key=lambda x:(-x['score'],x['country']))

def policy_state(text):
    if re.search(r'若当选|如果当选|竞选|候选人|候任|上任后将',text):return 'campaign'
    if re.search(r'将愿意|只有在.{0,120}才会承诺|(?:将|拟|即将)[^。；]{0,25}(?:签署|宣布|公布|发布)|对是否.{0,20}持|需要尽快|经济学家.{0,45}施压',text):return 'discussion'
    if re.search(r'(?:如果|倘若|除非).{0,80}(?:暂缓|暂停|取消|终止|才.{0,10}实施)',text):return 'conditional_arrangement'
    if re.search(r'尚未|并未|没有准备好|没有(?:通过|宣布|出台)|未获通过|被否决|遭否决',text):return 'not_adopted'
    if re.search(r'拟取消|拟废除|计划取消|计划退出|准备退出',text):return 'proposed_change'
    if re.search(r'草案|征求意见|咨询文件|修订稿|提议|此前提议|提交.{0,18}法案|提出.{0,18}法案|计划宣布|拟宣布|准备宣布|即将宣布',text) or ('提案' in text and not re.search(r'通过|批准|正式生效',text)):return 'draft_or_proposal'
    if re.search(r'建议|呼吁|敦促|应该|希望|需要.{0,15}制定|期待|讨论|考虑|有望|预计|可能',text):
        if not re.search(r'(?:已|正式|政府)?(?:采纳|决定执行|决定接受).{0,25}建议|规定|法案.{0,8}要求',text):return 'discussion'
    if re.search(r'(?:决定|宣布|计划|承诺).{0,35}(?:淘汰|关闭|废除).{0,18}(?:核电|煤炭|燃煤|煤电)|(?:禁售|停止销售).{0,20}燃油',text):return 'announced_phaseout'
    if re.search(r'取消|废除|废止|撤销|退出|终止|不再提供|停止补贴',text):return 'cancelled_or_withdrawn'
    if re.search(r'暂停|冻结|暂缓',text):return 'suspended'
    if re.search(r'已实施|已生效|正式生效|开始实施|正式施行',text):return 'implementation'
    if re.search(r'目标|承诺|力争|碳达峰|实现碳中和|实现净零',text):return 'announced_goal'
    return 'announced_or_adopted'

def split_units(text,mentions):
    """只切已见证据的效果尾句、句号/分号、显式另一个公共主体；保留前置条件。"""
    cuts={0,len(text)}
    photo=re.match(r'[（(]本图由[^）)]+[）)]',text)
    if photo:cuts.add(photo.end())
    if re.search(r'点击量|点击数|记者\s*[|｜：:]|^来源[：:]',text[:150]):
        actors=[m for m in mentions(text,0) if m.get('public') and m['start']>0]
        if actors:
            stop=actors[0]['start'];date=re.search(r'(?:19|20)\d\d年(?:\d{1,2}月)?(?:\d{1,2}日)?',text[:stop])
            if date:stop=date.start()
            if stop:cuts.add(stop)
    for m in re.finditer(r'[。！？；;\n][”’」』]*',text):
        if re.match(r'\s*(?:不符合|未满足|不得|否则|除非|只有符合)',text[m.end():]):continue
        cuts.add(m.end())
    for m in re.finditer(r'[，,](?=(?:分析师|分析人士|科学家|专家(?:认为|预计|指出)|研究人员认为|这些行为表明|这将(?:带动|导致|造成|进一步瓦解)|由此(?:可见|奠定)|可见|有望带动))',text):cuts.add(m.end())
    for m in re.finditer(r'上一篇[：:]|下一篇[：:]|相关阅读[：:]',text):cuts.add(m.start())
    ms=mentions(text,0)
    conditional=bool(re.search(r'如果|倘若|除非|只有',text))
    for m in re.finditer(r'[，,](?=[^，,。；]{0,12}(?:政府|总统|总理|首相|国会|议会))',text):
        left=text[:m.start()];right=text[m.end():]
        lm={x['country'] for x in ms if x['end']<=m.start()};rm=[x for x in ms if m.end()<=x['start']<m.end()+24]
        if not conditional and lm and rm and any(x['country'] not in lm for x in rm) and ACTION.search(left) and ACTION.search(right):cuts.add(m.end())
    for m in re.finditer(r'[，,](?=[\u4e00-\u9fff]{2,8}(?:则|将|承诺|计划))',text):
        rm=[x for x in ms if m.end()<=x['start']<m.end()+8 and x['role'] in {'public_actor','country_candidate'}]
        lm={x['country'] for x in ms if x['end']<=m.start()}
        if not conditional and rm and lm and any(x['country'] not in lm for x in rm) and re.search(r'目标|碳中和|净零|承诺',text[:m.start()]):cuts.add(m.end())
    for m in re.finditer(r'[，,、]',text):
        if conditional or not ACTION.search(text[:m.start()]):continue
        following=[x for x in ms if m.end()<=x['start']<=m.end()+18 and x['role'] in {'public_actor','country_candidate'}]
        if not following:continue
        first=following[0];prefix=text[m.end():first['start']]
        if not re.fullmatch(r'(?:随后|最近数月|同时|另外|而|此外|继而|相较之下|作为对比|[\s，,])*',prefix):continue
        prior={x['country'] for x in ms if x['end']<=m.start()}
        action=ACTION.search(text[first['end']:first['end']+80])
        if action and prior and first['country'] not in prior:cuts.add(m.end())
    p=sorted(cuts);return [(a,b) for a,b in zip(p,p[1:]) if b>a]

class NationalScope:
    def __init__(self,raw_mentions):
        self.pending=PendingResolver(raw_mentions);self.base_mentions=self.pending.mentions;self.cache={}
        self.authorities={n:c for c,ns in AUTHORITIES.items() for n in ns}
        self.regions={n:c for c,ns in REGIONS.items() for n in ns}
        self.ap=re.compile('|'.join(map(re.escape,sorted(self.authorities,key=len,reverse=True))))
        self.rp=re.compile('|'.join(map(re.escape,sorted(self.regions,key=len,reverse=True))))

    def mentions(self,text,offset=0):
        found=[dict(m) for m in self.base_mentions(text,offset)]
        for match in re.finditer(r'(中国|美国|日本|韩国|德国|法国|英国|意大利|俄罗斯|印度|沙特|印尼)(?:经济产业大臣|能源部长|环境部长|环境大臣|财政部长|国务卿|政府|国会|议会|内阁)',text):
            a,b=offset+match.start(),offset+match.end();country={'沙特':'沙特阿拉伯','印尼':'印度尼西亚'}.get(match[1],match[1])
            if any(x['start']<=a and b<=x['end'] and x.get('public') for x in found):continue
            found=[x for x in found if not (a<=x['start'] and x['end']<=b)]
            found.append(dict(country=country,text=match.group(),start=a,end=b,public=True,role='public_actor',level='national'))
        for match in self.ap.finditer(text):
            a,b=offset+match.start(),offset+match.end()
            if any(m['start']<=a and b<=m['end'] for m in found):continue
            if text.rfind('《',0,match.start())>text.rfind('》',0,match.start()):continue
            if re.match(r'(?:的)?(?:公司|企业|竞选团队|顾问|大学)',text[match.end():]):continue
            found.append(dict(country=self.authorities[match.group()],text=match.group(),start=a,end=b,public=True,role='public_actor',level='national'))
        for match in self.rp.finditer(text):
            tail=text[match.end():match.end()+20]
            addon=re.match(r'(?:省|市)?(?:政府|州长|市长|省长|议会|法律|法令|空气资源委员会)',tail)
            if not addon:
                head=text[:match.start()]
                geographic=re.match(r'(?:省|市)?(?=在|提出|制定|公布|宣布|发布|规定|计划|将|要|早在|碳市场)',tail)
                if not geographic or not re.fullmatch(r'[\s“（(\d一二三四五六七八九、.．）)]*',head):continue
                addon=geographic
            a,b=offset+match.start(),offset+match.end()+addon.end()
            found=[m for m in found if not (a<=m['start'] and m['end']<=b)]
            found.append(dict(country=self.regions[match.group()],text=text[match.start():match.end()+addon.end()],start=a,end=b,public=True,role='public_actor',level='local'))
        return sorted(found,key=lambda m:(m['start'],-m['end']))

    def relation(self,text,offset):
        relation=self.pending.owners(text,offset)
        events=list(relation['events']);mentions=self.mentions(text,offset)
        for m in mentions:
            tail=text[m['end']-offset:]
            if m['role']!='country_candidate' or not tail.startswith('将'):continue
            action=ACTION.search(tail)
            if not action or action.start()>65 or action.group() not in {'减少','降低','提高','增加','投资','建设','部署','打造','淘汰','关闭','实现','达到'}:continue
            if action.group() in {'实现','达到'} and not re.search(r'净零|碳中和|碳达峰|减排|排放.{0,12}目标',tail):continue
            before=tail[:action.start()]
            if re.search(r'企业|公司|市场|预计|预测|领先|地位|成本|报告|可能|有望|研究',before):continue
            if any(x['country']!=m['country'] for x in mentions if m['end']<=x['start']<m['end']+action.start()):continue
            if not TOPIC.search(tail):continue
            pos=m['end']+action.start()
            events.append(dict(actors=[m],action=dict(start=pos,end=pos+len(action.group()),text=action.group()),method='明确国家主体与具体能源转型行动'))
        for m in mentions:
            if m['role'] not in {'public_actor','country_candidate'}:continue
            local=m['end']-offset;tail=text[local:]
            # 补充“主体的计划包括…”和国家机构定语结构，也允许日期夹在主体动作之间。
            hit=re.match(r'(?:的(?:[^，。；]{0,18})?(?:计划|方案|战略|规划|政策|法案|目标)(?:包括|规定|要求|提出)?|(?:提出|公布|制定)的[^，。；]{0,20}(?:方案|计划|战略|政策)(?:要求|规定|包括)|(?:将|于|在|已|还|也|会|近期|正式|日前|近日|[，,：:“”"\s\d年月日零一二三四五六七八九十]|到|前|承诺|表示|的){0,35})(.*)',tail)
            if not hit:continue
            bridge=tail[:hit.start(1)];remaining=hit[1]
            action=ACTION.search(remaining)
            if not action and re.search(r'(?:计划|方案|战略|规划|政策|目标)(?:包括|规定|要求)',bridge):
                last=list(re.finditer(r'包括|规定|要求',bridge))[-1]
                apos=local+last.start();verb=last.group()
            elif action and action.start()<=35:
                between=bridge+remaining[:action.start()]
                if PRIVATE.search(between) and not re.search(r'(?:向|为|对).{0,15}(?:公司|企业)',between):continue
                if re.search(r'认为|批评|效果|导致|根据|依据|按照|^的(?:企业|公司)|受到|关于|出席|访问',between):continue
                if any(x['country']!=m['country'] for x in mentions if m['end']<=x['start']<offset+local+hit.start(1)+action.start()):continue
                apos=local+hit.start(1)+action.start();verb=action.group()
            else:continue
            prefix=text[max(0,m['start']-offset-8):m['start']-offset]
            if re.search(r'(?:针对|对|向|驻|赴|在|来自|要求|呼吁|建议)\s*$',prefix):continue
            if not m.get('public') and not re.fullmatch(r'(?:\s|将|于|在|已|还|也|到|前|[\d年月日]|政府|承诺|表示)*',text[m['end']-offset:apos]):continue
            if verb=='通过' and re.match(r'鼓励|提高|降低|加强|增加|提供',text[apos+len(verb):]):continue
            if verb in {'发布','公布'} and re.match(r'(?:了|一份|年度)?(?:报告|数据|统计|研究|预测)',text[apos+len(verb):]):continue
            event=dict(actors=[m],action=dict(start=offset+apos,end=offset+apos+len(verb),text=verb),method='国家机构或名词化公共安排')
            events.append(event)
        # 合作参与者须在同一签署谓词前组成并列主语，不能把针对对象混进来。
        for action in re.finditer(r'签署|签订|共同承诺',text):
            connectors=list(re.finditer(r'与|和|同',text[:action.start()]))
            for conn in reversed(connectors):
                left=[m for m in mentions if m['end']<=offset+conn.start() and m['role'] in {'public_actor','country_candidate'}]
                right=[m for m in mentions if offset+conn.end()<=m['start']<offset+action.start() and m['role'] in {'public_actor','country_candidate','target'}]
                if not left or not right:continue
                lead=left[-1];bridge=text[lead['end']-offset:conn.start()]
                if not re.fullmatch(r'(?:政府|还|已|又|曾|将|宣布|表示|同意|\s){0,10}',bridge):continue
                if PRIVATE.search(text[conn.end():action.start()]) or re.search(r'见证|针对',text[:action.start()]):continue
                actors=[lead]+right
                if len({m['country'] for m in actors})<2:continue
                events=[dict(actors=actors,action=dict(start=offset+action.start(),end=offset+action.end(),text=action.group()),method='合作谓词紧邻的并列签署主体')]
                break
        unique={}
        for e in events:
            for actor in e['actors']:
                matches=[m for m in mentions if m['start']==actor['start'] and m['country']==actor['country']]
                if matches:actor.update(max(matches,key=lambda m:m['end']))
            if re.match(r'者|人员|额|规模|效果|效应',text[e['action']['end']-offset:]):continue
            unique[(e['action']['start'],tuple(sorted((m['start'],m['country']) for m in e['actors'])))]=e
        events=list(unique.values())
        return dict(events=events,countries=sorted({m['country'] for e in events for m in e['actors']}),mentions=mentions,
            targets=relation.get('targets',[]))

    def level(self,text,relation):
        bound=[m for e in relation['events'] for m in e['actors']]
        local=[m for m in bound if m.get('level')=='local' or LOCAL_WORDS.search(m['text'])]
        national=[m for m in bound if m not in local and (m.get('public') or NATIONAL_SCOPE.search(m['text']))]
        if re.search(r'(?:时任|担任).{0,15}(?:省委书记|市委书记|省长|市长|州长)',text):return 'local'
        local_leads=[m for m in relation['mentions'] if m.get('level')=='local' and m['start']-min((x['start'] for x in relation['mentions']),default=m['start'])<4]
        if local_leads and re.search(r'依据|按照|落实|执行|根据|贯彻',text):
            if re.search(r'另行|额外|新增|加码|自主|自行|另定|自行提高|再增加|另外增加',text):return 'local'
            if re.search(r'国家|全国|国务院|中央|联邦|国会|《[^》]+》',text):return 'local_execution'
        if local_leads:return 'local'
        if re.search(r'(?:州|省|市|邦|大区)[、，,].{0,45}(?:州|省|市|邦|地区).{0,40}(?:典型|实施|地区)',text):return 'local'
        # 无动作角色时也标记明确地方主体，但不能从地名提及推断政策制定者。
        if not bound and (LOCAL_WORDS.search(text) or re.search(r'(?:加州|加利福尼亚州|纽约州|苏格兰|威尔士).{0,8}(?:规定|法律|要求|目标|制定)',text)):local=[dict(text='地方公共主体')]
        if local:
            if national:return 'mixed_level'
            implementing=re.search(r'依据|按照|落实|执行|根据|贯彻',text) and re.search(r'国家|全国|国务院|中央|联邦|国会|《[^》]+》',text)
            if implementing and not re.search(r'另行|额外|新增|加码|自主|自行|另定|自行提高|再增加|另外增加',text):return 'local_execution'
            return 'local'
        if national or NATIONAL_SCOPE.search(text):return 'national'
        if bound and relation['countries'] and all(m.get('role') in {'country_candidate','施策主体','public_actor'} for m in bound):return 'national'
        if relation['countries'] and not PRIVATE.search(text[:30]) and re.search(r'碳中和|碳达峰|净零',text):return 'national'
        return 'unknown'

    def anchor_pool(self,record,full):
        fid=record['file_id']
        if fid in self.cache:return self.cache[fid]
        pool=[]
        for m in re.finditer(r'[^。！？；;\n]+[。！？；;\n]*',full):
            t=m.group()
            if len(t)>800 or not TOPIC.search(t):continue
            relation=self.relation(t,m.start());level=self.level(t,relation)
            if not relation['countries'] or level!='national':continue
            if policy_state(t) in {'campaign','not_adopted','draft_or_proposal','proposed_change','discussion'}:continue
            if not FORMAL.search(t) or not INSTRUMENT.search(t):continue
            pool.append(dict(start=m.start(),end=m.end(),text=t,countries=relation['countries'],names=names(t),relation=relation))
        self.cache[fid]=pool;return pool

    def connect(self,text,a,b,record,full):
        anchors=self.anchor_pool(record,full);current_names=names(text)
        # 明确发布的同一专题路线图，允许其分项成本条件跨空行承接；存在竞争发布国家时禁用。
        if re.match(r'\s*为此[，,]',text) and re.search(r'加氢站.{0,25}(?:建设费|运维费)|建设费|运维费',text):
            candidates=[p for p in anchors if p['end']<=a and a-p['end']<=PARAMETERS['named_roadmap_list_max_gap']
                and re.search(r'发布|公布',p['text']) and any('路线图' in n and re.search(r'氢|燃料电池',n) for n in p['names'])]
            if candidates and len({c for p in candidates for c in p['countries']})==1:
                p=max(candidates,key=lambda p:p['end'])
                intervening=[q for q in anchors if p['end']<q['start']<a and set(q['countries'])!=set(p['countries'])]
                if not intervening:return p,'全文明确氢能路线图唯一发布主体→同专题成本条件'
        if current_names:
            matched=[p for p in anchors if p['names']&current_names and (p['start'],p['end'])!=(a,b)]
            countries={c for p in matched for c in p['countries']}
            if len(countries)>1:return None,'同名政策具有多个发布国家'
            if matched:
                explicit={m['country'] for m in self.mentions(text,a) if m['role'] in {'public_actor','country_candidate'}}
                if explicit-countries:return None,'当前国别与同名政策发布者相冲突'
                p=min(matched,key=lambda p:abs(a-p['end']));return p,'全文同名政策唯一发布主体'
            return None,'当前明确政策名称未找到同名发布者，不借其他计划继承'
        if not (POLICY_REF.search(text) or ACTOR_REF.search(text) or re.match(r'^(?:[“\s]*)(?:规定|每户|每辆|符合|要|着力|坚持|积极|加快|建立|推进)',text)):return None,'没有可验证的政策或主体指代'
        frames=[p for p in anchors if p['end']<=a and a-p['end']<=PARAMETERS['same_paragraph_max_gap'] and '\n\n' not in full[p['end']:a]]
        if not frames:return None,'没有同段有效国家公共措施锚点'
        p=frames[-1];bridge=full[p['end']:a]
        current_actors={m['country'] for m in self.mentions(text,a) if m.get('public') and m['role'] in {'public_actor','country_candidate'}}
        if current_actors and (current_actors!=set(p['countries'])):return None,'当前公共主体与前文发布者不一致'
        if CONTEXT_SWITCH.search(bridge):return None,'出现主题转换或第三方评论'
        others={m['country'] for m in self.mentions(bridge,p['end']) if m['role'] in {'public_actor','country_candidate'}}
        if others-set(p['countries']):return None,'锚点后出现竞争国家或公共主体'
        if LOCAL_WORDS.search(bridge):return None,'锚点后转为地方政府作用域'
        old_topics=set(re.findall(r'光伏|太阳能|风电|核电|氢能|汽车|煤炭',p['text']));new_topics=set(re.findall(r'光伏|太阳能|风电|核电|氢能|汽车|煤炭',text))
        if old_topics and new_topics and not old_topics&new_topics:return None,'当前措施主题与锚点不同'
        return p,'同段政策/主体指代连接'

    def assess(self,record,full,doc,doc_records):
        a,b=record['start'],record['end'];assert full[a:b]==record['text']
        result=[]
        for left,right in split_units(record['text'],self.mentions):
            e=self.assess_unit(record,full,doc,a+left,a+right)
            if e['route'].startswith('main_') and len(e['countries'])>1 and e.get('event_type')!='joint_policy':
                for c in e['countries']:
                    child=copy.deepcopy(e);child.update(event_id=e['event_id']+'-'+hashlib.sha256(c.encode()).hexdigest()[:6],countries=[c],event_type='parallel_policy',shared_evidence_span=True,
                        reason=e['reason']+'；各国分别采取同类措施，分为独立事件但共用原文证据')
                    child['roles']['actors']=[m for m in child['roles']['actors'] if m['country']==c]
                    result.append(child)
            else:result.append(e)
        return result

    def assess_unit(self,record,full,doc,a,b):
        t=full[a:b];relation=self.relation(t,a);level=self.level(t,relation);state=policy_state(t)
        bound=[m for e in relation['events'] for m in e['actors']]
        explicit=sorted({m['country'] for m in bound})
        local_participants=[m for m in bound if m.get('level')=='local' or LOCAL_WORDS.search(m['text'])]
        national_participants=[m for m in bound if m not in local_participants and m.get('public')]
        mixed_joint=bool(local_participants and national_participants and re.search(r'签署|签订',t) and re.search(r'合作|协议|备忘录',t))
        if mixed_joint:
            level='national';explicit=sorted({m['country'] for m in national_participants})
        path=[];links=[];conflicts=[]
        result=dict(event_id='NE-'+hashlib.sha256(f"{record['file_id']}:{a}:{b}".encode()).hexdigest()[:20],
            parent_unit_id=record['unit_id'],file_id=record['file_id'],start=a,end=b,text=t,
            route='',reason='',countries=[],country_basis='',confidence_level='未确定',confidence_basis='规则性证据等级，非校准概率',
            policy_level=level,policy_state=state,implementation_claim='未推定已经实施',
            excluded_local_participants=local_participants if mixed_joint else [],
            publication_evidence='当前句含公布、通过、批准或签署线索；尚未核验一手文本' if re.search(r'公布|颁布|通过|批准|签署',t) else '报道中的目标或公共安排；正式文件发布时间未核实',
            roles=dict(actors=bound,actions=[e['action'] for e in relation['events']],measures=[evidence(full,a,b,'措施与条件原文')],
                targets=relation['targets'],cooperation_countries=[],funding_countries=[],implementation_countries=[]),
            connection_path=path,national_policy_links=links,source_country=record.get('source_country',''),
            source_url=record.get('source_url',doc.get('url','')),title=record.get('title',doc.get('title','')),
            reported_at=record.get('published_at',doc.get('published_at','')),parent_policy_event_date=record.get('policy_event_date',''),
            evidence=[evidence(full,a,b)],heldout=record.get('heldout',False),
            previous_country=record.get('country',''),previous_quality_risks=record.get('quality_risks',[]),
            original_status=record.get('status',''),original_implementation_state=record.get('implementation_state',''),
            conditions=[m.group() for m in re.finditer(r'(?:如果|若|符合|仅限|只有|除非)[^。；]{0,90}',t)],
            time_mentions=[m.group() for m in re.finditer(r'(?:19|20)\d\d年(?:\d{1,2}月)?(?:\d{1,2}日)?',t)],
            policy_names=sorted(names(t)),human_confirmation='',reviewer='',algorithm_version=VERSION,
            s_score_diagnostic=record.get('country_score_details',[]),s_score_note='仅辅助查看竞争主体；不覆盖角色，不视为概率')
        def finish(route,reason,countries=None):
            result.update(route=route,reason=reason,countries=sorted(set(countries or [])))
            if route=='main_source_inferred':result.update(confidence_level='来源推定，较低',country_basis='来源文件夹；公共措施及国家层级另有正文证据')
            elif countries:result.update(confidence_level='明确关系/指代证据',country_basis='字面主体或有路径的政策主体连接')
            score_actors=[m for m in result['roles']['actors'] if not (mixed_joint and m in local_participants)]
            result['current_s_competition']=competition_scores(t,a,relation['mentions'],score_actors,result['source_country'],bool(result['connection_path']))
            return result
        if not t.strip():return finish('introduction','纯空白或排版')
        if re.search(r'window\.|function\s*\(|首页\s*>|上一篇[：:]|下一篇[：:]|0条评论|请遵守用户|扫码关注|相关阅读|点击量|点击数|本图由|^记者\s*[|｜：:]|^来源[：:]',t):
            return finish('noise' if not (relation['events'] and TOPIC.search(t)) else 'quality_unknown','网页模板残留；无法分开时隔离，不吞并政策')
        if re.search(r'从科学角国家|英国可再生能源项目开发办公室|首个国家“|到更[。\s]*$|到20\d(?!\d|年)|德国总统默克尔',t) or re.search(r'国家.*机构.*矛盾',str(record.get('quality_risks',[]))):
            return finish('quality_unknown','原文机构、国家或拼接疑点，需返回原始文档核对')
        if re.search(r'^(?:[“\s]*)(?:分析师|分析人士|专家认为|专家预计|研究人员认为|笔者|这将|这些行为表明|这意味着|由此可见|可见|该协议将有助于)',t) or re.search(r'股价|利好.{0,12}(?:板块|股票)|政府估计|政府预计|政府预测',t):
            return finish('commentary','效果评价或观点，不作为公共安排')
        if re.search(r'是大胆的|很高兴看到|权力的体现|潜在高价值渠道|其成本比|绝非易事|不是总统提出的所有|财政后果|政府.{0,5}需要尽快',t):return finish('commentary','评价、必要性或影响说明，引用政策不等于新增公共措施')
        if re.search(r'共统计.{0,8}\d+项|共统计了.{0,8}\d+项',t):return finish('background','多个政策的数量汇总及统计背景，不据此来源推定')
        if re.search(r'统计显示|据统计|共统计|数据显示|根据.{0,45}(?:调查|研究人员)|去年.{0,25}(?:占比|份额).{0,12}达到|超过\d+[%％].{0,15}已经达到',t) and not re.search(r'政府.{0,25}(?:决定|规定|宣布)|法律.{0,10}规定|通过立法',t):
            return finish('background','统计、调查或执行结果背景')
        if re.search(r'研究表明|科学家|全球升温|升温.{0,8}(?:度|℃)',t) and not (relation['events'] and re.search(r'政府|国会|议会|内阁',t)):
            return finish('science','科学结论或预测，不是国家措施')
        semantic=self.ap.sub('',t)
        topical=bool(TOPIC.search(semantic))
        if re.search(r'工业4.0|智能制造|反恐|国防|军事|核武器|核弹',semantic) and not topical:return finish('out_of_scope','其他公共事务，不是双碳与能源转型')
        if state=='campaign':return finish('campaign','竞选、候任主张单列，未当成政府已采纳',explicit)
        if state in {'not_adopted','draft_or_proposal','proposed_change'}:return finish('draft','草案、正式提议或未通过；原状态单列',explicit)
        if state=='discussion':
            # 法定申请条件中的“如果”不会进入讨论；建议被正式采纳也不能整句误删。
            return finish('discussion','建议、预测、预告或讨论；未证明已经采纳',explicit)
        if PRIVATE.search(t[:65]) and not (bound and any(m.get('public') for m in bound)) and not PUBLIC.search(t) and not (POLICY_REF.search(t) and DETAIL.search(t)):
            return finish('private_project','企业自主项目或第三方安排，无公共工具证据')
        if re.search(r'共同见证|见证下',t):return finish('quality_unknown','见证人不是签约人，公私措施尚未拆清')
        if re.search(r'共同承诺[：:]',t):return finish('quality_unknown','共同声明和具体国家分项目标混合，需分别绑定，未整句当共同措施')
        if len(explicit)>2 and re.search(r'与.{0,65}[、,，].{0,65}等国签订',t) and not re.search(r'共同签署|多边协定|联合声明',t):
            return finish('quality_unknown','多份双边合作还是单一多边政策尚未明确，不合成共同事件',explicit)
        if re.search(r'全球引入.{0,10}国家有\d+|新任总干事|中国作出巨额资金承诺',t):return finish('quality_unknown','政策报道与统计、标题或人事背景混杂，尚未完整拆清事实')
        if PRIVATE.search(t) and re.search(r'\d+(?:份|项).{0,15}(?:协议|备忘录)',t):return finish('quality_unknown','多份协议包含公私混合安排，实际公共签约条款不明')
        if re.search(r'(?:创始人|比尔.{0,3}盖茨|Catalyst).{0,120}(?:与|和).{0,12}政府合作',t):return finish('quality_unknown','私人提出合作，公共机构是合作宾语，未证明政府已采纳的工具')
        if re.search(r'政治遗产|光杆司令|弃暗投明',t) and relation['events']:return finish('quality_unknown','政策事实与政治评价混杂，尚未证明完整拆分边界')
        if level=='local':return finish('local_policy','地方独立制定或额外增加的目标/措施，排除国家主分析',explicit)
        if level=='local_execution':
            links.extend([dict(policy_name=n,evidence=evidence(full,a,b,'地方落实国家政策')) for n in names(t)] or [dict(policy_name='原文明确的国家政策',evidence=evidence(full,a,b))])
            return finish('local_execution','地方落实国家政策，只作执行信息关联，不生成独立国家政策',explicit)
        if level=='mixed_level':return finish('quality_unknown','国家与地方施策混在同一子句，尚不能证明各自边界')
        if record.get('quality_risks'):
            # 纯模板在拆开后的子句不传播；事实矛盾与截断风险不得因发现国家而通过。
            serious=[r for r in record['quality_risks'] if not re.search(r'网页|导航|评论模板|评论混杂|效果评价|政治评论|统计',r)]
            if serious:return finish('quality_unknown','原文损坏或语义质量风险仍需核对：'+'；'.join(serious))
        anchor=None;connection_reason=''
        if (not explicit or POLICY_REF.search(t)) and (DETAIL.search(t) or INSTRUMENT.search(t)):
            anchor,connection_reason=self.connect(t,a,b,record,full)
            if connection_reason in {'同名政策具有多个发布国家','当前国别与同名政策发布者相冲突'} and not explicit:
                return finish('subject_unknown',connection_reason)
        if anchor and not explicit:
            explicit=anchor['countries'];level='national';result['policy_level']=level
            result['evidence'].append(evidence(full,anchor['start'],anchor['end'],'政策发布主体锚点'))
            path.extend([dict(from_text=t,to_text=anchor['text'],relation=connection_reason),
                dict(from_text=anchor['text'],to_text='、'.join(explicit),relation='发布主体→国家')])
            topical=topical or bool(TOPIC.search(anchor['text']))
            result['roles']['actors']=[m for e in anchor['relation']['events'] for m in e['actors']]
        if not topical:return finish('out_of_scope','当前措施不涉及双碳与能源转型，机构名称不作主题命中')
        generic_public=bool(re.search(r'(?:联邦政府|中央政府|国会|参议院|众议院|内阁|财政部|能源部|总统|首相|联邦经济事务和能源部长)(?:[\s\d年月日，,]|近日|日前|曾|已|将|正式|于|在|还|也|会|此前|年内){0,25}(?:宣布|公布|发布|批准|通过|颁布|制定|决定|规定|承诺|提出|拨款|征收|取消|废除)(?!的|过的|所)',t))
        generic_public=generic_public or bool(re.search(r'(?:法案|法律|条例).{0,20}(?:在|由)(?:国会|议会|参议院|众议院).{0,5}通过',t))
        concrete=bool((anchor and DETAIL.search(t)) or (INSTRUMENT.search(t) and (relation['events'] or generic_public)))
        if not concrete:return finish('content_uncertain','未能确认具体公共目标、措施或执行条件，不能仅因有国家通过')
        if level!='national':return finish('level_unknown','公共安排可疑似成立，但未证明国家层级；不提升为国家政策')
        # 施策国家和合作、针对、实施、资金角色分开。
        current=self.mentions(t,a)
        local_countries={m['country'] for m in local_participants} if mixed_joint else set()
        unbound=[m for m in current if m['country'] not in set(explicit)|local_countries and m['role'] in {'public_actor','country_candidate'}]
        for m in unbound:
            pos=m['start']-a;prefix=t[max(0,pos-12):pos]
            if re.search(r'(?:向|对|针对|为|在|来自|与|和)\s*$',prefix):result['roles']['targets'].append(m)
            elif m.get('public'):conflicts.append(m)
        if conflicts:return finish('subject_unknown','存在未绑定动作的竞争公共主体，不能只选已识别一方')
        if len(explicit)>1 and not re.search(r'共同|联合|合作|协议|备忘录',t):
            years=set(re.findall(r'(?:19|20)\d\d',t));action_groups={tuple(sorted({m['country'] for m in e['actors']})) for e in relation['events']}
            if len(years)>1 or (len(action_groups)>1 and re.search(r'金额|亿|万|比例|份额|[％%]',t)):
                return finish('quality_unknown','多国期限或措施数值仍混在同一子句，不复制给各国')
        if re.search(r'拨款|财政援助|资助|贷款|出资|资金',t):result['roles']['funding_countries']=explicit
        if mixed_joint:
            result['roles']['cooperation_countries']=sorted({m['country'] for m in bound});result['event_type']='joint_policy'
        elif re.search(r'共同|联合|合作|协议|备忘录',t) and len(explicit)>1:
            groups={tuple(sorted({m['country'] for m in e['actors']})) for e in relation['events']}
            if len(groups)>1:return finish('subject_unknown','多国独立动作尚未拆清，不能视作共同政策')
            result['roles']['cooperation_countries']=explicit;result['event_type']='joint_policy'
        else:result['event_type']='single_policy'
        for m in current:
            if re.search(r'(?:在|由|实施方为)\s*$',t[max(0,m['start']-a-6):m['start']-a]) and m['country'] not in explicit:result['roles']['implementation_countries'].append(m['country'])
        if explicit:
            if not any(c in G20 for c in explicit):return finish('non_g20','明确施策国家不属于本次G20范围，单独归档',explicit)
            return finish('main_explicit',connection_reason or '当前句公共施策主体及国家层级明确',explicit)
        # 来源只补国家，不补“公共政策”和国家层级这两个前提。
        competing=[m for m in current if m['role'] in {'public_actor','country_candidate'}]
        if competing:return finish('subject_unknown','有未解析国别线索，来源不能覆盖正文')
        source=record.get('source_country') or doc.get('source_country','')
        before=full[max(0,a-1200):a].split('\n\n')[-1]
        prior_actors={m['country'] for m in self.mentions(before,a-len(before)) if m.get('public') and m['role'] in {'public_actor','country_candidate'}}
        if prior_actors-{source}:return finish('subject_unknown','同段有相反或竞争公共主体，来源推定不能覆盖')
        if not generic_public:return finish('subject_unknown','缺国别且没有当前句可验证的公共主体动作，不以来源补造关系')
        if source in G20:
            path.extend([dict(from_text=t,to_text='国家层级公共措施',relation='正文独立确认'),dict(from_text=source,to_text=source,relation='来源文件夹推定；无相反施策证据')])
            return finish('main_source_inferred','公共政策及国家层级已确认，缺国别且无相反证据，按来源推定',[source])
        return finish('subject_unknown','公共政策成立但仍无合理国家归属，从国家比较排除')
