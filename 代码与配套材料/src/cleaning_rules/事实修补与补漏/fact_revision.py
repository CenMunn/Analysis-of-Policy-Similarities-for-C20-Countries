"""V7.5通用增量修补。不读取标注、样本编号或国家文件夹做决定。"""

import copy

import re

from ..主体与国家归属.national_scope import AUTHORITIES

from ..事实修补与补漏.recall_rules import CP, country

from ..公共工具.identifiers import ident

VERSION='policy-revision-20261023.7.5.5'

PARAMETERS={'context_chars':900,'published_task_chars':4000,'new_layer':'扩展候选',
    'country_folder_override':False,'probability_calibrated':False,
    'rule_order':['literal_fact_boundary','public_action_state','content_veto','actor_or_named_anchor','candidate_admission'],
    'inputs_exclude_labels':True,'source_inference_added':False}

TOPIC=re.compile(r'碳|CO2|气候|巴黎协定|温室气体|可再生|新能源|节能|能源转型|能源转换|清洁能源|绿色增长|光伏|太阳能|风能|风电|核能|核电|氢(?:气|能|战略|燃料)?|绿氢|蓝氢|FIT|动力蓄电池|电动汽车|电动车|燃油车')

MEASURE=re.compile(r'战略|规划|计划|目标|法案|法律|协定|规定|政策|标准|补贴|配额|关税|税率|抵扣|投资|拨款|预算|融资|资金|示范|认证|排放|减排|建设|发电|碳中和|脱碳|目录|碳足迹|采购|贷款')

TOPIC=re.compile(TOPIC.pattern+r'|清洁电力|植树造林|风力发电')

MEASURE=re.compile(MEASURE.pattern+r'|建造|价格|FIT')

ACT=re.compile(r'宣布|公布|发布|批准|通过|制定|制订|更新|签署|签订|设定|承诺|决定|出台|征收|加征|实施|建设|种植|允许|降低|提高|出资|投资|投入|划拨|放弃|取消|退出|扩大|要求|规定|推进|支持|计划|目标|规划|斥资|招标')

FORMAL=re.compile(r'公布|发布|制定|制订|更新|批准|通过|签署|签订|正式启动|正式实施|正式实现')

ACT=re.compile(ACT.pattern.replace('发布','发布(?!会)'))

FORMAL=re.compile(FORMAL.pattern.replace('发布','发布(?!会)')+r'|出台|实施|推行')

LOCAL=re.compile(r'州政府|市政府|省政府|市长|州长|东京都政府|浙江省|加利福尼亚州政府')

PRIVATE=re.compile(r'公司|企业|集团|开发商|投资者|分析师|专家|研究院|学者|协会')

DETAIL=re.compile(r'要求|规定|必须|不得|可以使用|抵扣|纳入.{0,15}评估|购买价格|每户|每辆|符合条件|具备条件|用于投资|计划包括|开展.{0,30}示范|推进|发展|研发|供应量|其中.{0,12}(?:GW|吉瓦)|目标|招标')

DETAIL=re.compile(DETAIL.pattern+r'|碳足迹|开始实施FIT')

TASK=re.compile(r'^(?:[“\s]*)(?:重点任务[：:]|开展|推进|研发|发展|开发|促进|强化|建造|提供|扩大|到20\d\d|力争)')

REF=re.compile(r'该(?:政策|计划|战略|法|目标|国|项目)|这些项目|这项|宣言|根据|其中|具体而言|FIT|政府|他表示|^它表示')

NAME=re.compile(r'《([^》]{2,80})》|[“「]([^”」]{2,40}(?:计划|战略|政策|协定|目标|2030|规划))[”」]')

ACTOR_ROLES=re.compile(r'(?:联邦)?(?:政府|总统|首相|总理|环境省|环境部|能源部|工业部|国会|内阁|能源大臣|贸易、工业和能源部|商业与工业部长)')

def names(t):return {a or b for a,b in NAME.findall(t)}

def spans(t):return [(m.start(),m.end(),m.group()) for m in re.finditer(r'[^。！？\n]+[。！？\n]?',t)]

def keep(e):return e.get('route','').startswith('main_')

def fact_bounds(t):
    """只截取字面事实，不补写主谓；返回边角原文的分类。"""
    a,b=0,len(t);pre='introduction';post='commentary'
    abstract=re.search(r'摘要[：:]',t)
    if abstract and re.search(r'DOI[：:]|参考文献|引证文献',t):
        a=abstract.end();footer=re.search(r'(?:另外[,，][^。]*?DOI[：:]|DOI[：:]|参考文献|引证文献)',t[a:])
        if footer:return a,a+footer.start(),'introduction','noise'
    exam=re.search(r'答案[A-D](?=(?:中国|美国|日本|德国|法国)(?:总统|政府|首相))',t)
    if exam:a=exam.end();pre='noise'
    m=re.search(r'并退出《[^》]+》[。]?',t)
    if m and re.search(r'力主|全盘否定',t[:m.start()]) and not re.search(r'如果|若|拟|可能|将|未|不|没有|否认',t[:m.start()]):
        return m.start(),m.end(),'commentary','commentary'
    # 引用中已发生的另一主体措施独立提取，不继承竞选语气。
    m=re.search(r'(?:特朗普|奥巴马|拜登|美国|中国|日本|德国|法国)(?:政府)?(?:已经|正式|已)(?:退出|取消|废除)[^，。；”]+',t)
    if m and re.search(r'竞选|若当选|候选人',t):return m.start(),m.end(),'campaign','campaign'
    m=re.search(r'此前政府宣布的[^。；]+(?:目标)',t)
    if m and re.search(r'有可能脱离|预示着',t):return m.start(),m.end(),'commentary','commentary'
    # 明确网页/媒体开头；绝不从条件句内部的政府二字开始截断。
    m=re.match(r'「本文来源：[^」]+」',t)
    if m:a=m.end();pre='noise'
    if t.startswith('原标题：'):
        m=re.search(r'(?:中国|美国|日本|韩国|法国|德国)(?:总统|政府|首相|总理)[^。]{0,60}(?:公布|发布|宣布)',t)
        if m:a=m.start();pre='introduction'
    if '|' in t[:100] and '新闻首页' in t[:100]:
        m=re.search(r'(?:日本|美国|中国|德国|法国)政府(?:放弃|宣布|决定)',t)
        if m:a=m.start();pre='noise'
    m=re.match(r'(?:据[^，。]{2,55}报道[，,]|[^，。]{0,25}报道[，,])',t[a:])
    if m:a+=m.end()
    s=t[a:]
    # 状态属于前面的征税决定；后面的取消/冻结属于企业反应。
    m=re.search(r'(?:的决定|的政策)(?=(?:已经|已)?导致.{0,50}(?:企业|行业|公司|投资))',s)
    if m:return a,a+m.end(),pre,'private_reaction'
    m=re.search(r'[，,；;](?=(?:但|然而|而|随后)?(?:企业|公司|行业).{0,25}(?:取消|冻结|停止).{0,12}(?:投资|项目|建设))',s)
    if m:return a,a+m.start(),pre,'private_reaction'
    # 时间/金额/条件在前半句全部保留。不能见“预计”即切：规划目标也可能用预计。
    tail=re.search(r'[，,](?=(?:分析师|分析人士|专家认为|预计(?:将)?(?:带动|创造|增加就业)|有望(?:带动|推动|刺激)|这将(?:带动|导致)|这无疑|从而导致|并影响到|但技术及成本|尚没有.{0,12}企业|印尼有\d))',s)
    if tail:b=a+tail.start()
    growth=re.search(r'[，,]同比增长[^。]*[。]?$ ',t[a:b],re.X)
    if growth and re.search(r'斥资|拨款|补贴|政府.{0,12}投资',t[a:a+growth.start()]):b=a+growth.start();post='background'
    m=re.search(r'[，,](?=旨在到20\d\d年底提供.{0,15}就业机会|届时.{0,20}使用率最高)',t[a:b])
    if m:b=a+m.start()
    # 实施制度这一历史事实嵌在行业效果句中。
    m=re.search(r'\d{4}年\d{1,2}月开始实施FIT',t)
    if m and re.search(r'起航|快速增长',t):return m.start(),m.end(),'background','commentary'
    return a,b,pre,post

def veto(t,context=''):
    legislative=bool(re.search(r'(?:议会|国会|参议院|众议院).{0,8}通过了?',t) and not re.search(r'尚未|没有|计划|力争|推动|如果',t))
    if re.search(r'参考资料|参考文献|——END——|欢迎关注',t):return 'noise','文献目录及网页尾部，不作为政策'
    if re.search(r'正在考虑|正考虑|力劝|政府相信|政策选项|将揭示|瞎指挥|应该否定|美国输不起|鼓舞士气',t):return 'discussion','尚在考虑、建议或评价，不是已声称措施'
    if re.search(r'没有.{0,18}(?:退出|取消|全盘否定)|未(?:退出|取消)|面临.{0,20}反对.{0,30}可能',t):return 'discussion','保留否定或推测作用域，不能拆成正向政策动作'
    if re.search(r'如果|假如|假使|倘若|若.*当选',t) and not re.search(r'(?:规定|要求|宣布)[^。]{0,100}(?:若|如果)|(?:若|如果)(?:家庭|居民|企业|符合|未满足|满足|申请)',t):return 'discussion','假设政策情景；未形成执行资格条件'
    if re.search(r'披露信息显示|同比增长|统计局数据|经济增幅|列出了\d个原因',t):return 'background','统计或论证背景'
    if re.search(r'如果.{0,20}(?:放弃|取消|退出|废除)|若.{0,12}当选|假如|情景推演',t):return 'discussion','假设主体改变政策，不是执行资格条件'
    if re.search(r'呼吁|建议政府|游说议员|请求国会|拟定.*战略|将在.{0,15}最终|将(?:于.{0,15})?(?:正式)?(?:公布|发布)计划',t):return 'discussion','呼吁、拟定、游说或未来公布安排'
    if re.search(r'向国会提交.{0,40}预算|预算咨文|推动国会通过|改革努力|组阁协议|联合组阁',t):return 'draft','预算提案、改革协商或组阁约定未等于正式措施'
    if re.search(r'宣布就任|大选结果|参会时说|辩论中|发言.*鼓舞|鼓舞士气',t):return 'background','政治活动或评价，未陈述公共措施'
    if re.search(r'科学家.{0,20}(?:研究|发表)|统计局数据显示|报告.{0,12}显示|战略.{0,4}显示|居各行业之首',t):return 'background','研究结论或统计；发布报告不是实施政策'
    if re.search(r'最闪亮|打着.{0,15}旗号|自我称赞|进行了辩护|目前看来|仍然有待观察|普遍的看法|受到.{0,8}欢迎|绝不是轻轻松松',t):return 'commentary','政策评价、推测或倡议解读'
    if re.search(r'尚未批准|尚未通过|没有通过|仍未决定|尚待.{0,8}批准|提交.{0,20}(?:国会|议会)审议|供国会审议',t):return 'draft','未获批准或仍在审议'
    if re.search(r'正在研究.{0,15}(?:路径|方案)|备选路径|假设|若当选|当选后推行|候选人|与现任总统|竞选',t):return 'campaign' if re.search('竞选|当选|候选|现任总统',t) else 'discussion','假设、备选或竞选安排'
    if re.search(r'拟议|多次提议|预算.{0,20}提出|委员会.{0,12}提出.{0,10}提议|将.{0,25}(?:最终确定|正式对外宣布)|将在未来几天内公布',t):return 'draft','提案/待公布，不提升为已正式措施'
    if re.search(r'不具名|知情人士',t):return 'discussion','匿名消息预告，未有正式发布证据'
    if LOCAL.search(t) and not re.search(r'中央政府|联邦政府|全国|落实国家',t):return 'local_policy','地方独立政策口径'
    if re.search(r'(?:专家|分析师|学者|研究院).{0,25}(?:建议|认为|估计|预计)|^专家建议',t):return 'commentary','专家意见未被公共机关采纳'
    if re.search(r'加剧.{0,10}竞争|深层次动机|政治牵制|战略牵制|具有重大意义|有益探索|重要成果|高度评价|积极贡献|感到非常高兴|至关重要|最早的|首个进一步|面临.{0,10}挑战|无需.{0,8}过虑|之所以|奇思妙想|是愚蠢的|很显然',t):return 'commentary','主断言为评价、动机或效果'
    if re.search(r'预计.{0,30}(?:产生|创造).{0,45}(?:就业|经济价值)|计划将帮助新增.{0,15}工作岗位|^预计.{0,40}就业|曾经估计|有望进一步提速',t):return 'commentary','预测政策影响，不是规定的目标或执行条件'
    if re.search(r'详细点评|演讲要点|来源：.*?【|原标题：',t) and len(t)<90:return 'introduction','标题或导语缺少措施内容'
    if re.search(r'设定目标[。\s]*$',t) and not re.search(r'\d|目标[为是]|减排.{0,8}%',t):return 'introduction','未给出目标内容'
    if re.search(r'这项计划是在\s*$',t):return 'quality_unknown','句子截断，未形成事实'
    if re.search(r'未来.{0,25}(?:将|上).{0,12}(?:发表讲话|会议)|主要内容为谈判|打算利用这次会议',t):return 'introduction','会议活动预告或动机'
    if re.search(r'技术全球领先|全球现投入运营|截至.{0,25}批准的.{0,15}安装量|截止到.{0,25}批准的.{0,15}安装量|名下的其他建筑.{0,60}未能达到',t):return 'background','统计或成果描述'
    if re.search(r'坚强后盾|需要筹措启动资金|全球气候变化新协议表示积极支持|(?:指|称为).{0,20}主张执行|并不是所有的人都认同|这一点尤为重要',t):return 'commentary','原则表态、概念或泛泛评价'
    if re.search(r'(?:公司|企业|集团|蒙牛|阿美).{0,50}(?:投资|宣布|建成|加入).{0,50}(?:工厂|牧场|财团|建设|项目)',t) and not re.search(r'政府.{0,30}(?:要求|规定|补贴|宣布|决定)|该政策.{0,30}(?:要求|需要)',t):return 'private_project','企业自主建设/财团安排，非公共决定'
    if re.search(r'草案|拟议|提案|征求意见|尚待批准',t) and not legislative and not re.search(r'正式通过|已通过|已经批准',t):return 'draft','草案及拟议单列'
    if re.search(r'(?:担任总统|政府).{0,8}可能(?:会)?|与.{0,15}补贴相比|考虑以后以某种形式|并没有明确',t):return 'discussion','假设情景或未具体化安排'
    if re.search(r'一书作者.{0,25}认为|方案受挫|未给出|不会.{0,3}限制经济增长',t):return 'commentary','当前主张为效果评价'
    if re.search(r'正在与.{0,15}讨论新规如何|协议应坚持|最大的?主张.*福利',t):return 'discussion','谈判原则、适用讨论或党派主张'
    if re.search(r'空污|空气污染|悬浮微粒',t) and not re.search(r'碳|能源转型|可再生|电动汽车|新能源汽车|禁止新的柴油车登记|禁售燃油',t):return 'out_of_scope','临时空气污染控制，未建立双碳或转型目的'
    if re.search(r'天然气自给率|稳定采购|核不扩散|防扩散',t) and not re.search(r'减排目标|碳中和目标|能源转型',t):return 'out_of_scope','能源安全或核安保；非明确双碳措施'
    # 前文只能用于同一人物的竞选计划；明确当前政府已公布的句子优先。
    if re.search(r'拜登',t) and re.search(r'竞选网站|竞选计划|竞选宣言|上任第一天|就职第一天|当选总统|尚未就任',context) and not re.search(r'政府.{0,15}(?:已|正式)?(?:公布|宣布|批准|签署)|就任后|上台后|履新签署',t):return 'campaign','同一人物计划在竞选/就任前语境，保留原状态'
    if re.search(r'以达到\s*$|讨论.{0,15}核电项目[。\s]*$',t):return 'quality_unknown' if t.rstrip().endswith('以达到') else 'discussion','截断或会谈讨论，缺少已声称措施'
    return None,''

def action_state(t,anchor=None):
    if re.search(r'(?:议会|国会).{0,8}通过了?',t):return 'legislative_passage'
    if re.search(r'(?:将.{0,10}|拟)(?:正式)?(?:取消|撤销|废除|退出)|将于.{0,12}签署退出',t):return 'announced_withdrawal'
    if re.search(r'(?:正式|已经|已)(?:退出|取消|废除|撤销)|政府放弃|废除了|取消了|退出了|^并退出《',t):return 'cancelled_or_withdrawn'
    if re.search(r'(?:宣布|决定).{0,10}退出',t):return 'announced_withdrawal'
    if re.search(r'若|如果|具备条件|符合条件',t):return 'conditional_arrangement'
    if re.search(r'碳配额|抵扣|购买价格|纳入.{0,15}评估|碳足迹|每户|每辆',t):return 'execution_requirement'
    if anchor and TASK.search(t):return 'published_plan_task'
    if re.search(r'正在建设|开始实施|已经实施|正式实施|正在招标|价格降低',t):return 'implementation'
    if re.search(r'斥资|亿.{0,6}(?:用于|基金)|(?:投资|资金|基金|拨款).{0,15}\d|\d.{0,15}(?:投资|基金|资金|拨款)',t):return 'announced_funding_plan'
    if re.search(r'目标|20\d\d.{0,55}(?:实现|达到|将|增加|减排|来自|占)|碳中和',t):return 'announced_goal'
    if re.search(r'战略',t):return 'announced_strategy'
    if re.search(r'计划|规划|方案',t):return 'announced_plan'
    return 'announced_or_adopted'

class RevisionEngine:
    def __init__(self):
        self.authorities={a:c for c,aa in AUTHORITIES.items() for a in aa}
        self.authorities.update({'工信部':'中国','工业和信息化部':'中国','韩国工业部':'韩国','韩国贸易、工业和能源部':'韩国',
            '阿尔特迈尔':'德国','普鲁伊特':'美国','本萨勒曼':'沙特阿拉伯','沙特能源大臣':'沙特阿拉伯'})
        self.ap=re.compile('|'.join(map(re.escape,sorted(self.authorities,key=len,reverse=True))))
        self.cache={}

    def actors(self,t):
        found=[]
        for m in self.ap.finditer(t):
            if t[:m.start()].rfind('《')>t[:m.start()].rfind('》'):continue
            if re.search(r'对|针对|向|要求|希望|建议',t[max(0,m.start()-5):m.start()]):continue
            tail=t[m.end():]
            if re.match(r'(?:的)?(?:公司|企业|专家|竞选团队)',tail):continue
            backward=bool(re.search(r'[”」][^。]{0,5}$',t[:m.start()]) and re.search(r'表示|说|称',tail[:15]) and ACT.search(t[:m.start()]))
            if ACT.search(tail[:120]) or backward or (re.match(r'称[，,]',tail) and DETAIL.search(tail[:110])):
                found.append((m.start(),m.end(),self.authorities[m.group()],m.group()))
        for m in CP.finditer(t):
            if t[:m.start()].rfind('《')>t[:m.start()].rfind('》'):continue
            if any(a<=m.start()<b for a,b,_,_ in found):continue
            head=t[max(0,m.start()-6):m.start()];tail=t[m.end():]
            if re.search(r'对|针对|来自|向|超过|效仿|要求',head):continue
            public=ACTOR_ROLES.match(tail)
            direct=re.match(r'(?:目前|已经|已|将|还|未来|计划|于|在|今后几年|未来将|20\d\d年(?:之前|以前|前)?|[，,]){0,5}(?:制定|宣布|公布|上调|计划|斥资|种植|实现|设定|承诺|扩大|决定|增加|禁止)',tail)
            dated_implementation=re.match(r'自\d{4}年[^。；]{0,90}实施',tail)
            official_detail=bool(public and re.search(r'称[，,]',tail[:public.end()+5]) and DETAIL.search(tail[:120]))
            if (public and ACT.search(tail[:135])) or direct or dated_implementation or official_detail:
                found.append((m.start(),m.end()+(public.end() if public else 0),country(m.group()),t[m.start():m.end()+(public.end() if public else 0)]))
        return sorted(found)

    def doc_anchors(self,fid,full):
        if fid in self.cache:return self.cache[fid]
        aa=[]
        for a,b,t in spans(full):
            if len(t)>1800 or veto(t)[0] or LOCAL.search(t):continue
            acts=self.actors(t);cs=sorted({c for _,_,c,_ in acts})
            if len(cs)==1 and FORMAL.search(t) and (names(t) or re.search(r'战略|规划|计划|政策|目标|配额制|RPS|FIT',t)):
                aa.append(dict(start=a,end=b,text=t,countries=cs,names=sorted(names(t)),actors=acts))
        self.cache[fid]=aa
        return aa

    def link(self,t,a,full,fid):
        anchors=[x for x in self.doc_anchors(fid,full) if x['end']<=a and a-x['end']<=PARAMETERS['published_task_chars']]
        near=[x for x in anchors if a-x['end']<=900]
        if not names(t) and not TASK.search(t) and len({c for x in near for c in x['countries']})>1:return None
        selected=[]
        for an in anchors:
            gap=full[an['end']:a]
            same=bool(names(t)&set(an['names']))
            task=bool(TASK.search(t) and re.search(r'重点任务|具体修订内容|发展目标',gap[-1500:]) and re.search(r'战略|规划',an['text']))
            if same or task or (a-an['end']<=900 and REF.search(t)):
                competing={c for _,_,c,_ in self.actors(gap)}-set(an['countries'])
                competing|={self.authorities[m.group()] for m in self.ap.finditer(gap)}-set(an['countries'])
                current_people={self.authorities[m.group()] for m in self.ap.finditer(t)}-set(an['countries'])
                if not same and (competing or current_people):continue
                if re.search(r'另一方面|相比之下|另一个.{0,10}(?:计划|政策)|相关阅读|(?:专家|分析师)建议',gap[-250:]) and not same and not task:continue
                selected.append(an)
        if not selected:return None
        exact=[x for x in selected if names(t)&set(x['names'])]
        if exact:selected=exact
        # 不能因为比较句里的德国而覆盖日本战略；也不能跨两个施策主体继承。
        if len({c for x in selected for c in x['countries']})!=1:return None
        if not exact and len({n for x in selected for n in x['names']})>1:
            # 同一机关连续更新同一战略也可能多名；仅明确任务清单可用最近已公布战略。
            if not TASK.search(t):return None
        return selected[-1]

    def diagnose(self,e,full,doc):
        a,b=e['start'],e['end'];x,y,pre,post=fact_bounds(e['text']);t=e['text'][x:y]
        ctx=full[max(0,a-900):a]+full[b:b+450]
        if '拜登' in t and 'joebiden.com/climate-plan' in full:
            ctx+='竞选网站'+full[:250]
        route,why=veto(t,ctx)
        actors=self.actors(t);cs=sorted({q[2] for q in actors})
        anchor=None if len(cs)==1 else self.link(t,a+x,full,e['file_id'])
        if anchor and not cs:cs=anchor['countries']
        topical=bool(TOPIC.search(t))
        candidate=bool(topical and (ACT.search(t) or MEASURE.search(t) or DETAIL.search(t)))
        return dict(start=a+x,end=a+y,text=t,prefix_route=pre,suffix_route=post,route=route,reason=why,
                    actors=actors,countries=cs,anchor=anchor,candidate=candidate,context_start=max(0,a-900),context_end=min(len(full),b+450))

    def revise(self,event,full,doc):
        e=event
        if e.get('text_parts'):return [copy.deepcopy(e)]
        a,b=e['start'],e['end'];assert full[a:b]==e['text']
        d=self.diagnose(e,full,doc);t=d['text'];was=keep(e);anchor=d['anchor'];cs=d['countries'];joint=[]
        if d['route']:
            if not was:return [copy.deepcopy(e)]
            return self.partition(e,full,d,False,d['route'],d['reason'],d['route'])
        if not t.strip():return [copy.deepcopy(e)]
        # 双方排放交易系统正式连接后的互认条件，不要求本句重复政府。
        if re.search(r'碳配额',t) and re.search(r'抵扣|互认',t):
            prior=full[max(0,a-350):a]
            links=[(u,v,s) for u,v,s in spans(prior) if re.search(r'正式.{0,12}(?:连接|联通)|协议.{0,12}生效',s)]
            if links:
                u,v,s=links[-1]
                joint=sorted(set(re.findall(CP.pattern+r'|瑞士|挪威|新西兰',t+s)))
                cs=sorted({country(c) for c in joint if CP.fullmatch(c)})
                if cs:anchor=dict(start=a-len(prior)+u,end=a-len(prior)+v,text=s,countries=cs,names=[],actors=[])
        # 明确制度实施/电价条件的国家由正文题名和币种共同支持；非来源文件夹。
        if not cs and 'FIT' in t and ('日本' in full[:180]) and ('日元' in t or '日本' in full[max(0,a-250):b+100]):
            cs=['日本'];anchor=dict(start=0,end=min(180,len(full)),text=full[:180],countries=cs,names=['FIT'],actors=[])
        # 公共机关直接决定、目标、正在实施；实体角色不能仅是企业/专家。
        direct=bool(cs and d['actors'] and TOPIC.search(t) and (ACT.search(t) or DETAIL.search(t)) and (MEASURE.search(t) or DETAIL.search(t)))
        linked=bool(cs and anchor and TOPIC.search(t) and DETAIL.search(t))
        if not was and direct:
            # 候选入口宽，自动保留窄：需要发布/实施动作、具体国家目标或财政安排。
            assertion=bool(re.search(r'宣布|公布|制定|制订|出台|上调|规定|正式|实施|正在建设|出资|征收|签署|允许|斥资|价格降低|决定|废除了|支持资金|政府规划|政府.{0,20}(?:目标|计划|推进)|(?:中国|美国|日本|韩国|印尼|沙特|德国|法国).{0,6}计划(?:到|将)|种植超过',t))
            if not assertion:direct=False
        if not was and not (direct or linked or joint):return [copy.deepcopy(e)]
        if not was and e.get('route') in {'local_policy','non_g20','quality_unknown'}:return [copy.deepcopy(e)]
        actual=bool(re.search(r'正式(?:退出|取消|实施)|废除了|公布了|制定了|宣布了|政府宣布|政府制定|政府决定|政府公布|签署命令',t))
        new_intent=bool(d['actors'] and re.search(r'(?:表示|说).{0,70}将.{0,20}(?:签署|正式取消)',t))
        # 历史分流可以重判，但需要新的字面事实或特定执行关系，不能只重新命中国家和话题。
        if not was and e.get('route') in {'science','background','private_project'} and not (actual and d['start']>a):return [copy.deepcopy(e)]
        if not was and e.get('route')=='commentary' and not (linked and DETAIL.search(t) or d['start']>a or d['end']<b):return [copy.deepcopy(e)]
        if not was and e.get('route') in {'campaign','draft'} and not (actual or new_intent):return [copy.deepcopy(e)]
        # 具体词组必须承接当前政策，不能把纯政策评价交给邻近国家。
        if linked and not joint and not d['actors'] and not (REF.search(t[:35]) or TASK.search(t) or 'FIT' in t):return [copy.deepcopy(e)]
        # 软语气只能作为正式规划/公开宣布的计划，不把愿望与泛泛支持升格。
        if not was and re.search(r'希望|有望|可能|预计',t) and not re.search(r'根据.{0,20}政府规划|政府.{0,20}(?:规划|计划)|计划.{0,40}到20\d\d|到20\d\d.{0,20}供应量',t) and not anchor:
            return [copy.deepcopy(e)]
        if not was and PRIVATE.search(t[:45]) and not d['actors'] and not re.search(r'该政策|规定|要求|必须',t):return [copy.deepcopy(e)]
        if was and not d['actors'] and not joint:cs=e.get('countries',[])
        if not cs:cs=e.get('countries',[])
        if not cs:return [copy.deepcopy(e)]
        if len(cs)>1 and not joint:return [copy.deepcopy(e)]
        state=action_state(t,anchor)
        if was and d['end']==b:
            state=e.get('policy_state','unknown')
            if state=='unknown':state=action_state(t,anchor)
        state_reason='仅依据当前施策动作的时态；金额、条件和否定保留'
        if re.search(r'政府放弃|正式退出|已经取消|废除了|履新签署|^并退出《',t):state=action_state(t,anchor)
        following=full[b:b+220]
        if re.match(r'但该计划',following) and '从未生效' in following and re.search(r'法院.{0,12}(?:搁置|暂停)',following):
            state='historical_goal_suspended';state_reason='紧随同一该计划的法院搁置及从未生效证据'
            d['lifecycle_evidence']=(b,min(len(full),b+len(following)))
        if re.search(r'补贴',t) and re.match(r'起始于.{0,20}补贴政策在\d{4}年已经告一段落',following):
            state='historical_program_ended';state_reason='同一补贴紧随结束年份；不扩展到后续新计划'
            d['lifecycle_evidence']=(b,b+following.index('。')+1)
        changed=(not was or d['start']!=a or d['end']!=b or set(cs)!=set(e.get('countries',[])) or state!=e.get('policy_state'))
        if not changed:return [copy.deepcopy(e)]
        d.update(countries=cs,joint_participants=joint,state_reason=state_reason)
        why=('补入口：明确公共动作' if direct else '补入口：同名政策/执行任务连接' if anchor else '修正原保留事实') if not was else '原保留事实边界、施策主体或动作状态修正'
        return self.partition(e,full,d,True,'main_explicit',why,state)

    def partition(self,e,full,d,accepted,route,reason,state):
        a,b=e['start'],e['end'];x,y=d['start'],d['end']
        if not accepted:x,y=a,b
        out=[]
        for u,v,kind in [(a,x,d['prefix_route']),(x,y,route),(y,b,d['suffix_route'])]:
            if u==v:continue
            r=copy.deepcopy(e);r.update(event_id=ident('E75-',(e['event_id'],u,v,kind,state)),start=u,end=v,text=full[u:v],route=kind,
                algorithm_version=VERSION,previous_event_ids=[e['event_id']],previous_routes=[e['route']],
                reason=reason if u==x and v==y else '政策事实之外的原文单独归档，保留完整处理证据',
                independent_human=False,assistant_reviewed=False,accepted_for_formal_analysis=False,
                human_confirmation='',reviewer='',review_provenance='通用规则重判，不冒充人工确认')
            r['evidence']=[dict(file_id=e['file_id'],start=u,end=v,text=full[u:v],role='本条字面原文')]
            if accepted and kind=='main_explicit':
                r.update(countries=d['countries'],policy_level='national',policy_state=state,
                    delivery_layer=e.get('delivery_layer','扩展候选') if keep(e) else '扩展候选',
                    country_basis='正文公共主体' if d['actors'] else '正文同政策连接',newly_recovered=not keep(e),
                    joint_participants=d.get('joint_participants',[]),confidence_is_calibrated_probability=False,
                    policy_names=sorted(names(full[u:v])),connection_path=[])
                if d.get('anchor'):
                    an=d['anchor'];r['evidence'].append(dict(file_id=e['file_id'],start=an['start'],end=an['end'],text=full[an['start']:an['end']],role='政策发布或执行制度锚点'))
                    r['connection_path']=[dict(from_text=full[u:v],to_start=an['start'],to_end=an['end'],to_text=an['text'],countries=d['countries'],relation='当前执行条件/任务→同政策发布与主体')]
                if d.get('lifecycle_evidence'):
                    p,q=d['lifecycle_evidence'];r['evidence'].append(dict(file_id=e['file_id'],start=p,end=q,text=full[p:q],role='同政策后续状态证据'))
                r['evidence_dimensions_v75']={
                    'content':{'grade':'字面事实规则支持','reason':reason},
                    'country':{'grade':r['country_basis'],'reason':'；'.join(d['countries'])},
                    'level':{'grade':'国家机关或国家制度上下文','reason':'地方独立口径另行排除'},
                    'state':{'grade':'动作绑定的原文状态','reason':d.get('state_reason','')}}
                if u>a and not d.get('anchor'):
                    r['evidence'].append(dict(file_id=e['file_id'],start=a,end=b,text=full[a:b],role='拆分前同句主体、条件及时间证据'))
            else:
                r.update(countries=[],policy_state=state if not accepted else '',delivery_layer='隔离归档',newly_recovered=False)
                r['evidence'].append(dict(file_id=e['file_id'],start=d['context_start'],end=d['context_end'],text=full[d['context_start']:d['context_end']],role='分流上下文'))
            out.append(r)
        assert ''.join(r['text'] for r in out)==e['text']
        return out
