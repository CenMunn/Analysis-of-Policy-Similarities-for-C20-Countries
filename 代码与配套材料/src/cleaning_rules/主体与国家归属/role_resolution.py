"""补全待核的公共主体，不用文件夹、国名频次或分类器分数代替角色证据。"""

import re

from collections import defaultdict

from ..主体与国家归属.sentence_roles import SentenceRoles

from ..政策内容判定.topic_rules import TOPIC

VERSION='pending-resolution-20261022.4'

G20={'中国','美国','日本','韩国','德国','法国','英国','意大利','俄罗斯','印度','印度尼西亚','沙特阿拉伯','南非','加拿大','澳大利亚','阿根廷','巴西','墨西哥','土耳其','欧盟'}

FORMAL=re.compile(r'宣布|公布|发布|颁布|通过|批准|制定|签署|签订|提出|承诺|设定')

TASK=re.compile(r'规定|要求|必须|有义务|设立|建立|制定|实施|提供|给予|投入|投资|预算|购买|补贴|补助|税率|退税|关税|减少|增加|降低|提高|建设|淘汰|要|着力|坚持|推进|支持|编制|设置|设定|认定|开展|放宽|组织|承诺|签署')

PRIVATE=re.compile(r'公司|企业|集团|协会|专家|学者|分析师|记者|研究人员|投资者|抗议者|环保团体')

TOPICS={'汽车':r'汽车|车辆|电动车|充电','氢能':r'氢能|氢气|氢经济|燃料电池','光伏':r'光伏|太阳能','风能':r'风电|风能','核能':r'核电|核能|反应堆','煤炭':r'燃煤|煤电|煤炭','气候':r'碳中和|碳排放|气候|净零|温室气体'}

def topics(text):return {k for k,p in TOPICS.items() if re.search(p,text)}

def names(text):
    return {m[1].replace(' ','') for m in re.finditer(r'[《“]([^》”]{2,65}(?:法案|条例|法律|规划|计划|战略|路线图|方案|法))[》”]',text) if not re.search('巴黎|京都|报告|议定书',m[1])}

def span(full,a,b,**kw):return dict(start=a,end=b,text=full[a:b],**kw)

class PendingResolver:
    def __init__(self,mentions):
        self.raw_mentions=mentions;self.mentions=self.enriched_mentions;self.roles=SentenceRoles(self.enriched_mentions);self.cache={}

    def enriched_mentions(self,text,offset=0):
        found=[dict(m) for m in self.raw_mentions(text,offset)]
        extra=[(r'(?:加州|加利福尼亚州)(?:政府|州长(?:布朗)?|法律|法令|空气资源委员会)','美国'),
            (r'(?:吉林|山西|江苏|山东|浙江|安徽|广东|广西|河北|河南|湖北|湖南|四川|陕西|海南|辽宁|黑龙江|福建|贵州|云南|江西|甘肃|青海)(?:省|壮族自治区)?(?:人民政府|政府|人民代表大会|省长)','中国'),
            (r'国家发展和改革委员会|国家发改委|全国政协|中央人民政府|国务院|工信部','中国'),
            (r'(?<![\u4e00-\u9fff])德(?:联邦)?政府','德国'),(r'野田政府','日本'),
            (r'瑞士(?:政府|议会|联邦委员会)','瑞士'),(r'阿联酋(?:政府|能源部)','阿联酋'),
            (r'威尼斯(?:市)?政府','意大利')]
        for pattern,country in extra:
            for m in re.finditer(pattern,text):
                a,b=offset+m.start(),offset+m.end()
                if any(x['end']==a and x['country']!=country for x in found):continue
                if not any(x['start']<b and a<x['end'] for x in found):
                    found.append(dict(country=country,text=m.group(),start=a,end=b,public=True,role='public_actor'))
        return sorted(found,key=lambda m:(m['start'],-m['end']))

    def cooperation(self,text,offset,relation):
        mentions=self.mentions(text,offset)
        for action in re.finditer(r'签署|签订|达成',text):
            if not re.search(r'合作|协议|备忘录',text[action.end():action.end()+65]):continue
            for conn in reversed(list(re.finditer(r'与|和|同',text[:action.start()]))):
                left=[m for m in mentions if m['end']<=offset+conn.start() and m['role'] in {'public_actor','country_candidate'}]
                right=[m for m in mentions if offset+conn.end()<=m['start']<offset+action.start() and m['role'] not in {'private_or_context','book_title'}]
                if not left or not right:continue
                lead=left[-1];bridge=text[lead['end']-offset:conn.start()]
                if not re.fullmatch(r'(?:政府|还|已|又|曾|将|宣布|表示|同意|\s){0,8}',bridge):continue
                if PRIVATE.search(text[conn.end():action.start()]) or re.search(r'大学|学院|高校',text[conn.end():action.start()]):continue
                actors=[lead]+right;countries=sorted({m['country'] for m in actors})
                if len(countries)<2:continue
                event=dict(action=dict(start=offset+action.start(),end=offset+action.end(),text=action.group()),
                    actors=actors,method='合作谓词两侧参与者绑定')
                return dict(relation,events=[event],countries=countries,resolved=False)
        return relation

    def owners(self,text,offset):
        relation=self.cooperation(text,offset,self.roles.extract(text,offset))
        def means_not_adoption(e):
            return e['action']['text']=='通过' and bool(re.match(r'鼓励|加强|建设|提高|降低|提供|实施|增加|减少|支持|推动',text[e['action']['end']-offset:]))
        kept=[e for e in relation['events'] if not means_not_adoption(e)]
        if len(kept)!=len(relation['events']):
            cs=sorted({m['country'] for e in kept for m in e['actors']})
            relation=dict(relation,events=kept,countries=cs,resolved=len(cs)==1)
        if relation['countries']:return relation
        events=[]
        for m in self.mentions(text,offset):
            if m['role'] not in {'public_actor','country_candidate'}:continue
            local=m['end']-offset;tail=text[local:]
            hit=re.match(r'(?:政府|国会|议会|参议院|内阁|总统|总理|首相)?(?:将|于|在|已|还|也|会|计划|近期|正式|日前|近日|用科学方法|以透明程序|每|[，,]|\d|年|月|日|\s){0,25}(宣布|公布|发布|颁布|通过|批准|制定|签署|承诺|认定|开展|放宽|组织|设定)',tail)
            if not hit:continue
            if not m.get('public') and not re.match(r'政府|国会|议会|参议院|内阁|总统|总理|首相',tail):continue
            a=local+hit.start(1);b=local+hit.end(1)
            if hit.group(1)=='通过' and re.match(r'鼓励|加强|建设|提高|降低|提供|实施|增加|减少|支持|推动',text[b:]):continue
            if re.search(r'报告|数据|统计|预测|研究|分析',text[b:b+12]):continue
            events.append(dict(actors=[m],action=dict(start=offset+a,end=offset+b,text=text[a:b]),method='国家机构后接明确公共动作'))
        owners=sorted({m['country'] for e in events for m in e['actors']})
        return dict(relation,events=events,countries=owners,resolved=len(owners)==1)

    def nonpolicy(self,text,relation):
        semantic_text=re.sub(r'德国联邦经济和能源部|德国经济和能源部|能源部|能源部长','',text)
        if re.search(r'合作|备忘录|协议',text) and re.search(r'工业4.0|智能制造|教育合作',text) and not (TOPIC.search(semantic_text) or re.search(r'气候|变暖|脱碳|能效|低碳',semantic_text)):
            return ('其他公共政策','一般智能制造或教育合作，当前句未说明双碳或能源转型措施')
        if re.search(r'计划宣布|拟宣布|准备宣布|有望出台',text):return ('政策讨论','尚待宣布或出台的预告，不作为已正式声称的措施')
        if re.search(r'(?:预计|有望|即将).{0,70}(?:宣布|签署|签订|达成|出台|公布)|将承诺',text):
            return ('政策讨论','尚未宣布或签订的预告，不认定为已经形成的联合措施')
        if re.search(r'讨论.{0,35}期待.{0,35}(?:列入|制定|建立)|(?:^|[，,])(?:政府|各国政府)需要.{0,35}(?:制定|出台|建立)',text):
            return ('政策讨论','讨论、期待或政策必要性判断，不等于政府已采纳或承诺')
        if re.search(r'本次竞选|本次大选|竞选武器',text) and not re.search(r'参议员.{0,20}(?:提出|提交)《[^》]+法案》',text):
            return ('政策讨论','竞选计划单列，不认定在任政府已经采纳')
        if re.search(r'(?:通用汽车|公司|集团).{0,30}(?:致|给).{0,80}(?:信|函).{0,15}(?:重申|承诺|表示)',text):
            return ('企业项目','企业给公共机构的信件或自主承诺，收信机构不是施策者')
        if re.search(r'^(?:这些措施使得|该协议将有助于|这将(?:进一步)?(?:瓦解|导致|影响|阻碍|带动|促进))',text):return ('评论','评价措施作用或效果，不是独立政策安排')
        if re.search(r'(?:总统|总理|首相).{0,18}宣布.{0,40}(?:企业|公司).{0,20}(?:投资|建设).{0,8}计划',text) and not re.search(r'拨款|财政|担保|补贴|税收|贷款|公共采购',text):
            return ('企业项目','政府人士公布企业投资消息，本句没有公共资助或政府委托工具')
        if re.search(r'各州.{0,10}要求.{0,25}诉讼.{0,20}政府不得',text) and not re.search(r'法院.{0,12}裁定',text):
            return ('政策讨论','诉讼请求不等于法院已经作出禁令')
        if re.search(r'(?:取消|推迟)前往.{0,15}访问',text) and not re.search(r'法案|补贴|拨款|税率|减排目标|签署.{0,8}协议',text):
            return ('背景','官员行程、会面或讨论项目，不单独构成双碳公共措施')
        # 可独立定位的措施或法律条款优先；混合句不整句丢弃。
        if relation['events'] or re.search(r'通过立法|(?:法案|条例|法律|计划|政策|《[^》]+》).{0,10}(?:规定|明确|要求)',text):return None
        if re.search(r'(?:政府|他们|该国).{0,18}(?:将执行|执行|采纳|落实|决定接受).{0,45}(?:联合国|建议|减排)',text):return None
        if re.search(r'(?:国际能源署|国际氢能委员会|联合国|协会).{0,50}(?:呼吁|建议|敦促)',text):return ('政策讨论','国际组织或行业机构建议不等于国家公共措施')
        if re.search(r'研究表明|报告指出|报告显示',text) and self.mentions(text,0) and re.search(r'计划.{0,40}(?:投资|建设|拨款)|通过.{0,15}(?:法案|法规)',text):return None
        if re.search(r'上一篇[：:]|下一篇[：:]',text) and re.search(r'0条评论|发表请遵守|相关阅读|相关报道',text):
            return ('网页噪声','尾部导航、评论模板与推荐标题拼接，不属于该文政策正文')
        if re.search(r'呼吁(?:各国|政府)|建议政府|政府应该|(?:抗议者|专家|环保团体).{0,80}(?:要求|建议|呼吁).{0,8}(?:政府|各国)',text):
            return ('政策讨论','第三方向政府提出要求，不推定政府已采纳')
        if re.search(r'(?:预计|有望).{0,25}(?:将|会|于).{0,15}(?:宣布|签署|出台|公布)',text):
            return ('政策讨论','未来发布或签署的预告，不视为已采取措施')
        if re.search(r'根据.{0,55}(?:研究人员|调查|统计)|据统计|研究表明|(?:国际能源署|国际氢能委员会).{0,60}(?:报告|预测)',text):
            return ('背景','研究、调查、统计或行业预测，不是新增公共措施')
        if re.search(r'发布.{0,8}预测|(?:超过|约)?\d+[%％].{0,25}已经达到|只有\d+[%％].{0,8}达到了',text):
            return ('背景','政府发布的预测或政策执行比例统计，不能据发布谓词判成措施')
        if re.search(r'^(?:因为|因此|这意味着).{0,90}(?:没啦|不会受到影响|导致|利好|损害)',text):
            return ('评论','解释影响或因果后果，不单独声称采取公共措施')
        if re.search(r'(?:这一举措|该政策|这项政策).{0,20}(?:阻碍|导致|影响|利好)|(?:认为|表示).{0,40}(?:将会使|有望|股价|供应安全成为)',text):
            return ('评论','说明政策效果或价值判断，没有独立声称具体公共安排')
        if re.search(r'(?:公司|集团|三菱和三井|企业).{0,60}(?:重新调整其投资组合|审查脱碳策略|计划投资|宣布投资|收购)',text):
            if not re.search(r'政府.{0,25}(?:提供|拨款|采购|委托|补贴)|财政部|能源部',text):return ('企业项目','企业经营、投资或资产调整，未证明政府委托或公共工具')
        return None

    def anchors(self,record,full,records):
        key=(record['file_id'],len(full),len(records))
        if key in self.cache:return self.cache[key]
        anchors=[]
        # 旧内容层可能把“通过《全球变暖对策推进法》”归为背景；角色锚点必须能回看原文。
        pool=list(records)
        known={(r['start'],r['end']) for r in records}
        for m in re.finditer(r'[^。！？；;\n]+[。！？；;\n]*',full):
            if (m.start(),m.end()) not in known and len(m.group())<=650:
                pool.append(dict(start=m.start(),end=m.end(),text=m.group(),quality_risks=[]))
        for r in pool:
            if r.get('quality_risks'):continue
            t=r['text'];relation=self.owners(t,r['start'])
            if not relation['resolved'] or not relation['events']:continue
            if not any(FORMAL.fullmatch(e['action']['text']) for e in relation['events']):continue
            if re.search(r'退出|反对|拒绝|质疑|批评|呼吁|建议政府|预计|有望|假如|若当选|竞选|候选人|报告|统计|(?:将|即将|准备).{0,6}(?:宣布|公布|发布|签署)',t):continue
            if self.nonpolicy(t,relation):continue
            if not (TOPIC.search(t) or any(re.search(r'气候|变暖|清洁|能源|电|氢|节能|碳|可再生',n) for n in names(t))):continue
            country=relation['countries'][0]
            anchors.append(dict(start=r['start'],end=r['end'],text=t,country=country,policy_names=names(t),
                topics=topics(t),method='明确公共措施主体',events=relation['events']))
        # 公开领导人讲话中的连续任务清单。公共讲话只是作用域，当前句还必须有指令/任务。
        for m in self.mentions(full,0):
            if m['role']!='public_actor' or not m.get('public'):continue
            hit=re.match(r'(?:在[^。；]{0,35})?(?:强调|指出|指示|要求)[，,：:]',full[m['end']:])
            if hit:
                a=m['start'];b=m['end']+hit.end()
                anchors.append(dict(start=a,end=b,text=full[a:b],country=m['country'],policy_names=set(),topics=set(),method='公共领导人讲话作用域',events=[]))
        anchors.sort(key=lambda x:(x['start'],x['end']));self.cache[key]=anchors;return anchors

    def resolve(self,record,full,records):
        if record.get('heldout'):return dict(kind='protected_holdout',reason='独立留出不用于开发修订')
        t=record['text'];a,b=record['start'],record['end'];assert full[a:b]==t
        pending=lambda reason:dict(kind='pending',reason=reason,evidence=[])
        relation=self.owners(t,a)
        if re.search(r'(?:预计|有望|即将).{0,70}(?:签署|签订|达成|公布)|计划宣布|将承诺',t) and re.search(r'(?:已|正式)(?:经)?(?:签署|签订|通过|颁布)',t):
            return pending('既有措施与尚未形成的预告混合，需拆清状态，不能整句删除或按完成处理')
        preceding=full[max(0,a-500):a]
        if re.search(r'竞选|大选|候选人',preceding) and re.search(r'计划|规划|主张',t) and not re.search(r'正式通过|已经颁布|政府决定|正式签署',t):
            actors=[m for m in self.mentions(t,a) if m.get('public') and m['text'] in preceding and not re.search(r'政府|议会|国会|部|院',m['text'])
                and re.match(r'(?:则|还|也|将)?(?:计划|规划|主张)',t[m['end']-a:])]
            if actors:return dict(kind='nonpolicy',category='政策讨论',reason='同名候选人的竞选方案上下文，不认定在任政府已采纳',evidence=[span(full,a,b)])
        excluded=self.nonpolicy(t,relation)
        if excluded:return dict(kind='nonpolicy',category=excluded[0],reason=excluded[1],evidence=[span(full,a,b)])
        if record.get('quality_risks'):return pending('原文或语义质量风险仍未消除，不因找到国家自动通过')
        if PRIVATE.search(t) and re.search(r'(?:\d+|十[一二三四五六七八九]?|多)(?:份|项).{0,20}(?:协议|备忘录)',t):
            return pending('多份协议同时包含企业或其他领域合作，需确定具体公共政策条款与签约者')
        if re.search(r'从科学角国家|^\s*\d+年前[-—]|协议中[（(].{0,180}公司',t):return pending('截断拼接、推荐摘要或多个公私协议混杂，需先处理原文质量')
        if re.search(r'共同见证|见证下',t):return pending('官员见证不等于签约主体，需核对实际签约方及公共工具')
        if re.search(r'共同承诺[：:]',t):return pending('联合宣示和各国具体目标混合，需分别核对发布主体与分项措施')
        if re.search(r'探索制定|探索.{0,8}补贴|似乎|大概|我认为|人家',t):return pending('探索、推测或口语评价仍与政策内容混杂')
        owners=relation['countries']
        relevant_mentions=[m for m in self.mentions(t,a) if m['role'] in {'public_actor','country_candidate'}
            and not (t[max(0,m['start']-a-1):m['start']-a]=='除' and t[m['end']-a:m['end']-a+1]=='外')]
        unbound={m['country'] for m in relevant_mentions}-set(owners)
        if owners and unbound:return pending('还有未绑定角色的显式国家或公共主体，不能只保留已抽到的一方')
        if len(owners)==1:
            return dict(kind='single_country',country=owners[0],reason='句内施策角色明确',evidence=[span(full,a,b)],relation=relation)
        if len(owners)>1:
            # 联合行动须有合作语义，不能将相同目标自动当成联合政策。
            if re.search(r'共同|联合|合作|协议|备忘录',t) and not re.search(r'而|则在|分别|相比',t):
                groups={tuple(sorted({m['country'] for m in e['actors']})) for e in relation['events']}
                if len(groups)==1 and len(next(iter(groups)))>1:
                    return dict(kind='joint_policy',countries=owners,reason='同一合作/联合事件有多个明确参与主体',evidence=[span(full,a,b)],relation=relation)
            groups={}
            for e in relation['events']:
                cs=tuple(sorted({m['country'] for m in e['actors']}));start=min(m['start'] for m in e['actors'])
                groups[(start,cs)]=True
            ordered=sorted(groups)
            if len(ordered)>1 and all(not set(x[1])&set(y[1]) for i,x in enumerate(ordered) for y in ordered[:i]):
                clauses=[]
                for i,(start,countries) in enumerate(ordered):
                    left=start;right=ordered[i+1][0] if i+1<len(ordered) else b
                    # 浏览视图中截开效果评论；原始整句仍保存在账本及父记录。
                    tail=re.search(r'[，,](?:双方的联合行动为|这也|这将|这意味着|有望|从而)',full[left:right])
                    if tail:right=left+tail.start()
                    if right<=left:continue
                    excerpt=full[left:right]
                    clauses.append(span(full,left,right,countries=list(countries),
                        content_status='措施预告' if re.search(r'还将提出|计划宣布|有望出台',excerpt) else '政策事实候选'))
                if len(clauses)>1:return dict(kind='split_policies',countries=owners,clauses=clauses,reason='各国在不同施策子句中分别拥有措施或目标',evidence=[span(full,a,b)],relation=relation)
            return pending('多国角色已发现，但无法证明联合或独立事件边界')
        # 名词化提议中“来自奥巴马”是提议来源，不是拨款接受对象。
        for m in self.mentions(t,a):
            local_start=m['start']-a;local_end=m['end']-a
            if m.get('public') and t[max(0,local_start-2):local_start]=='来自' and re.match(r'的(?:提议|提案)',t[local_end:]):
                if re.search(r'拨款|补贴|税|法案',t) and not re.search(r'呼吁|敦促|要求.{0,12}政府',t):
                    return dict(kind='single_country',country=m['country'],status='正式拟议；未推定通过',reason='明确公共提议来源与接受资金对象分开',evidence=[span(full,a,b)])
        anchors=self.anchors(record,full,records);current_names=names(t)
        if current_names:
            matched=[x for x in anchors if x['policy_names']&current_names]
            if len({x['country'] for x in matched})>1:return pending('同名政策存在多个国家发布者，不能依最近国名猜测')
            if matched and TASK.search(t):
                chosen=min(matched,key=lambda x:abs(a-x['end']))
                if any(m['country']!=chosen['country'] for m in self.mentions(t,a)):
                    return pending('同名政策与当前显式国别冲突，不能用前文覆盖当前主体')
                if re.search(r'(?:专家|学者|分析师|研究人员).{0,30}(?:建议|呼吁|认为|预计)',t):
                    return pending('同名政策被第三方评论或建议引用，不继承为政府措施')
                return dict(kind='single_country',country=chosen['country'],reason='同一文档中同名政策唯一发布者',evidence=[span(full,a,b),span(full,chosen['start'],chosen['end'],role='政策发布锚点')])
        # 有明确外国词出现时，不能只继承前文或来源国家。
        current_mentions=self.mentions(t,a)
        if current_mentions:return pending('当前有国别或对象线索，尚未形成安全的施策关系')
        if not TASK.search(t):return pending('当前句没有足以承接公共安排的具体任务')
        frames=[x for x in anchors if x['end']<=a and a-x['end']<=900 and '\n\n' not in full[x['end']:a]]
        if not frames:return pending('没有距离和段落边界内的明确公共主体锚点')
        chosen=frames[-1];between=full[chosen['end']:a]
        if re.search(r'另据|另一方面|相比之下|其他国家|反观',between):return pending('锚点与当前句之间存在话题转换')
        if any(m['country']!=chosen['country'] for m in self.mentions(between,chosen['end'])):return pending('锚点后出现其他国家，阻断一般性主体继承')
        if re.search(r'(?:专家|学者|分析师|研究人员|作者|笔者).{0,20}(?:建议|认为|预计|指出|表示)',between):return pending('公共锚点后转为第三方观点，不能继承成政府措施')
        if re.search(r'什么是|所谓|通俗地说|我们认为|笔者|建议关注|重点关注',between):return pending('公共锚点后切入解释或投资评论，不能传递公共措施作用域')
        ts=topics(t);ats=chosen['topics']
        if ts and ats and not ts&ats and '气候' not in ts|ats:return pending('当前任务主题与政策锚点不一致')
        if chosen['method']=='公共领导人讲话作用域' and not re.match(r'\s*(?:要|着力|坚持|积极|加快|建立|推进|切实|坚决)',t):return pending('不是可明确接续的公开讲话任务清单')
        if re.search(r'有望|预计|认为|可能|将会使|研究|调查|阻碍|股价|政治遗产',t):return pending('效果评价或预测仍与事实混杂，不自动继承')
        if not re.match(r'\s*[“（(\d一二三四五六七八九、.．）)\s]*(?:政府|地方政府|联邦政府|现任政府|新政府|中央政府|参议院|众议院|国会|其|该|这|上述|本|根据|按照|依据|另外|此外|同时|同年|在此后|对于|对|每|价格|规定|要|着力|坚持|积极|加快|建立|推进|设立|以|最近的措施|为了解决)',t):
            return pending('句首缺少可验证的公共主体、政策指代或任务清单承接')
        return dict(kind='single_country',country=chosen['country'],reason='有界公共作用域内的任务/细则承接',evidence=[span(full,a,b),span(full,chosen['start'],chosen['end'],role='公共主体锚点')])
