"""补漏候选入口和主体连接。新子类，不修改冻结基线，不用国名密度覆盖角色。"""

import re

from ..上下文与证据连接.evidence_scope import EvidenceScope,TOPIC,CONCRETE,grade

from ..主体与国家归属.national_scope import ACTION,DETAIL,POLICY_REF,LOCAL_WORDS,FORMAL,INSTRUMENT,policy_state,evidence

from ..主体与国家归属.role_resolution import G20,names

VERSION='policy-recall-linking-20261022.5'

XTOPIC=re.compile(TOPIC.pattern+r'|碳定价|热泵|绿色供暖|绿色增长战略|绿色成长战略|氨燃料|氨.{0,10}混烧|脱柴油|锂(?:离子|电子)?电池|蓄电池')

MEASURE=re.compile(CONCRETE.pattern+r'|资助|援助|支援|资金支持|指南|补偿|热泵|配额制|义务|能源占比|电源构成|容量市场|碳定价|标准|方针|指示|策略|核电项目|用量|投入|生产.{0,8}目标')

PUBLIC_CUE=re.compile(r'政府|总统|首相|总理|内阁|国会|议会|国务院|能源部|环境省|国土交通省|农林水产省|教研部|财政部|经济产业|MOTIE|国家.{0,8}(?:计划|规划|目标)')

FUTURE_RELEASE=re.compile(r'(?:拟|计划|准备|即将|有望|预计)(?:(?:于|在)?(?:明年|下月|近日|近期|年内|本月|今年|未来几周|\d{4}年\d{0,2}月?)|正式|尽快|再次|进一步|\s){0,3}(?:宣布|公布|发布|出台)')

FUTURE_PUBLICATION=re.compile(FUTURE_RELEASE.pattern+r'|酝酿.{0,20}(?:法案|预算|提案)|尚待.{0,20}(?:通过|批准)|草案|征求意见稿|候选人|竞选|选举期间|威胁要')

DEICTIC=re.compile(r'^\s*(?:在此基础上|据此|为此|上述|该|这项|其|按照|根据|依照|今后|降低发电成本|提高能源效率|每户|每辆|对于|规模从|政府|首相|总统|有关部门|第?\d+[、.．]|(?:住宅|公共建筑|食品|农林|水产|交通|航空|港口|建筑|创新|碳捕集)[^。；]{0,20}[：:])')

GOAL_DETAIL=re.compile(r'(?:到|截至|力争|目标|将).{0,65}(?:\d|新增|提高|降低|实现|关闭|建设|普及|节能|减排)|每户|每辆|不得|必须|应当|配额|补贴|补助|资金支持|资助|容量市场|碳定价|促进.{0,18}(?:低碳|绿色投资|脱碳)|发展.{0,15}碳封存')

SECTORS={'solar':r'光伏|太阳能','wind':r'风电|风力|风能','hydrogen':r'氢|加氢站|氨燃料',
    'transport':r'汽车|车辆|充电|交通','building':r'建筑|供暖|热泵','nuclear':r'核电|核能|反应堆',
    'coal':r'煤炭|煤电|燃煤','climate':r'碳中和|碳排放|温室气体|减排|脱碳|碳定价|净零'}

def recall_candidate(text):
    """只决定是否送入重判；命中绝不等于通过主分析。"""
    if len(text.strip())<8:return False,'过短且没有完整安排'
    if re.match(r'\s*(?:\d+[、.．])?[^：:。]{2,18}[：:]',text) and re.search(r'节能|减排|碳封存|绿色清洁',text):
        return True,'能源战略分项标题及目标表述；仅补入口，仍须连接发布主体'
    if XTOPIC.search(text) and (MEASURE.search(text) or PUBLIC_CUE.search(text) and ACTION.search(text)):
        return True,'双碳主题与公共/措施线索；送入语义、层级和状态重判'
    if POLICY_REF.search(text) and DETAIL.search(text):return True,'政策指代与执行条件；需要另查同一政策锚点'
    return False,'未命中扩展补漏候选门；保留旧档，不宣称已语义审完'

def nonpolicy_reason(text):
    """阻断概念解释、统计和评价继承政策主体；有新公共动作的混合句另隔离。"""
    checks=[
        ('international_framework',r'(?:全球.{0,10}\d{2,3}个国家|\d{2,3}个国家面前).{0,100}(?:协定|签署|通过)|(?:协定|协议).{0,80}\d{2,3}个国家面前',
         '国际协定的一般缔约/通过信息，未列明各国采纳事件；不继承为单一国家政策'),
        ('private_project',r'(?:投资者|私人投资者|投资机构)(?:共同|联合|已|将)?宣布[^。；]{0,50}(?:资金承诺|投资承诺|新资金)|(?:实施主体|项目实施方)[^。；]{0,80}企业[^。；]{0,60}将优先采用',
         '投资者承诺或项目企业自主采用技术；政府计划只是背景，不能当成公共拨款/强制措施'),
        ('background',r'一般有.{0,8}(?:种|个)(?:方法|途径)|(?:碳中和|净零排放)[，,]?就是|是指人类活动|(?:其|基本|主要)?原理是|跟踪表|统计了?各个国家|统计.{0,12}进展情况',
         '概念解释或各国进展统计，不能继承前文国家成为措施'),
        ('commentary',r'(?:策略|政策|计划|目标).{0,8}(?:加剧|影响国际竞争|贯穿了)|若想|极具雄心|若[^。；]{0,30}战略得以实现|应该不会|政策.{0,10}最违法|涉嫌违宪',
         '评价、假设效果或第三方反应，引用政策不等于声称新的公共措施'),
        ('background',r'任命多位.{0,25}官员|担任.{0,20}部长.{0,100}(?:代理协调|首席执行官)|认为该协定已经过时',
         '人事履历或对条约的判断，不是具体双碳工具'),
    ]
    for route,pattern,reason in checks:
        if re.search(pattern,text):return route,reason
    commentary=re.search(r'引发.{0,12}讨论|(?:媒体|分析师|业内人士).{0,12}(?:分析称|分析认为|称|认为)|(?:政策|法案|计划).{0,15}(?:造就.{0,12}产业|增加.{0,10}就业)|最大的受益者|受益者之一|至关重要|乐见其成|不负责任|疯狂指责|痛骂|(?:批评|谴责|指责)[^。；]{0,50}(?:退出|协定|政策)|(?:退出|协定).{0,25}道歉|一些国家决定离开',text)
    if commentary:
        # 若当前句同时具有真正的宣布/颁布动作，隔离混合句，不直接吞掉事实。
        formal=re.search(r'政府.{0,12}(?:宣布|颁布|公布|决定)|总统.{0,12}(?:宣布|签署)|(?:法律|法案)明确规定',text)
        return ('quality_unknown','当前句公共动作与效果/态度评价混杂，尚需安全拆分') if formal else ('commentary','句子主断言是反响、评价、批评、道歉或效果；内嵌政策不是新施策事件')
    return None,None

class RecallLinkScope(EvidenceScope):
    def __init__(self,raw_mentions):
        super().__init__(raw_mentions)
        # base_mentions保留原enriched_mentions；其内部只调用raw_mentions，不会回到此接口。
        # 原实现的新增国家机构只停在上层，句内抽取器/owners仍使用旧实体表。
        self.pending.mentions=self.mentions
        self.pending.roles.mentions=self.mentions
        self.extra_authorities={
            '日本':['日本农林水产省','农林水产省','日本国土交通省','国土交通省','日本经济产业部长',
                '日本经济产业大臣','萩生田光一','梶山弘志'],
            '德国':['德国联邦教研部','德国联邦教育和研究部','德国联邦经济和能源部','德国联邦经济部'],
            '韩国':['MOTIE','韩国产业通商资源部','韩国产业通商资源部长','韩国贸易工业和能源部'],
            '印度尼西亚':['印尼能源与矿产资源部','能源与矿产资源部','能源和矿产资源部',
                '能源与矿产资源部长Arifin Tasrif','能源和矿产资源部长Arifin Tasrif','Arifin Tasrif','阿里芬'],
            '沙特阿拉伯':['沙特阿拉伯能源部','沙特能源部长'],
            '英国':['英国商业能源和产业战略部','英国商业、能源和产业战略部'],
            '美国':['美国内政部','美国内政部长','Deb Haaland'],
        }
        self.extra_local={'首尔市政府':'韩国','首尔市相关部门':'韩国','SMG':'韩国',
            '中爪哇政府':'印度尼西亚','中爪哇省政府':'印度尼西亚','福岛县政府':'日本'}

    def mentions(self,text,offset=0):
        found=super().mentions(text,offset)
        def add(match,country,level):
            a,b=offset+match.start(),offset+match.end()
            if text.rfind('《',0,match.start())>text.rfind('》',0,match.start()):return
            if any(m['start']<=a and b<=m['end'] and m.get('public') and m.get('level')==level for m in found):return
            found[:]=[m for m in found if not(a<=m['start'] and m['end']<=b)]
            prefix=text[max(0,match.start()-5):match.start()]
            role='target' if re.search(r'(?:对|向|针对|要求|呼吁)\s*$',prefix) else 'public_actor'
            found.append(dict(country=country,text=match.group(),start=a,end=b,public=True,role=role,level=level))
        for c,aliases in getattr(self,'extra_authorities',{}).items():
            for alias in sorted(aliases,key=len,reverse=True):
                for m in re.finditer(re.escape(alias),text):add(m,c,'national')
        for alias,c in getattr(self,'extra_local',{}).items():
            for m in re.finditer(re.escape(alias),text):add(m,c,'local')
        for m in re.finditer(r'(中国|美国|日本|韩国|德国|法国|英国|印尼|沙特)官方(?=公布|发布|制定|宣布)',text):
            add(m,{'印尼':'印度尼西亚','沙特':'沙特阿拉伯'}.get(m[1],m[1]),'national')
        # 中文新闻常在已给出国家后用“韩自2012年…”；不把任意单字当国名。
        for m in re.finditer(r'^韩(?=自\d{4}年.{0,25}可再生能源配额制)',text):
            found.append(dict(country='韩国',text=m.group(),start=offset+m.start(),end=offset+m.end(),
                              public=False,role='country_candidate',level='national'))
        return sorted(found,key=lambda m:(m['start'],-m['end']))

    def relation(self,text,offset):
        result=super().relation(text,offset)
        mentions=self.mentions(text,offset)
        for m in mentions:
            if m['role'] not in {'public_actor','country_candidate'} or m.get('level')=='local':continue
            tail=text[m['end']-offset:]
            hit=re.search(r'停止|重启|敲定|创设|准备|公布',tail[:90])
            if not hit:continue
            bridge=tail[:hit.start()]
            if not re.fullmatch(r'(?:将|于|在|已|还|也|会|正式|近日|日前|最新|当地时间|周[一二三四五六日天]|宣布|表示|该国|自|[\d年月日内，,\s])*',bridge):continue
            if hit.group()=='准备' and not re.match(r'了?[^。；]{0,12}(?:策略|战略|措施|方案)',tail[hit.end():]):continue
            if hit.group()=='公布' and not re.match(r'的(?:最新)?方案',tail[hit.end():]):continue
            actor=dict(m)
            if not actor.get('public'):
                if hit.group()!='敲定' or not re.search(r'能源.{0,8}计划|新能源计划|国家.{0,8}规划',tail[hit.end():]):continue
                actor.update(public=True,level='national')
            pos=m['end']+hit.start()
            result['events'].append(dict(actors=[actor],action=dict(start=pos,end=pos+len(hit.group()),text=hit.group()),method='补充机构完成策略/已公布方案或未来执行谓词'))
        # 公共配额是施加于公司的义务，不因句中出现公司列表就判作企业自主计划。
        quota=re.search(r'(?:可再生能源)?配额制',text)
        if quota and re.search(r'必须|每年.{0,15}(?:要|须|保障)|义务|适用不同配额',text):
            lead=[m for m in mentions if m['start']<offset+quota.start() and m['role'] in {'country_candidate','public_actor'}]
            if lead:
                actor=lead[0]
                if actor.get('level')!='local':
                    result['events'].append(dict(actors=[actor],action=dict(start=offset+quota.start(),end=offset+quota.end(),text=quota.group()),method='国家配额工具及企业法定义务'))
        # “企业获得政府资金支持”：政府是资金提供方，企业及项目所在地不是施策国。
        receipt=re.search(r'(?:已|已经)?(?:获得|得到|获)了?[^。；]{0,65}(?:政府|财政部|能源部)[^。；]{0,35}(?:拨款|资金支持|补贴|资助)',text)
        if receipt:
            providers=[m for m in mentions if m.get('public') and m.get('level')!='local' and offset+receipt.start()<=m['start']<offset+receipt.end()]
            if providers:
                pos=re.search(r'拨款|资金支持|补贴|资助',receipt.group())
                result['events'].append(dict(actors=providers,action=dict(start=offset+receipt.start()+pos.start(),end=offset+receipt.start()+pos.end(),text=pos.group()),method='受款方获得明确政府资金支持'))
        unique={}
        # “在甲国宣布…之后，乙国总统表示…”：甲国是时间背景，乙国是当前发言主体。
        # 仅处理带明确时间从句和新公共发言人的结构，不能丢弃普通并列多国措施。
        focused=[]
        for m in mentions:
            local=m['end']-offset;prefix=text[:m['start']-offset]
            if m.get('public') and m['role']=='public_actor' and re.match(r'(?:公开|正式|随后|则|还|也|已|近日|\s){0,4}(?:表示|宣布|承诺)',text[local:]):
                if re.search(r'(?:在|继)[^。；]{0,100}(?:之后|后)[^。；]{0,20}[，,]',prefix):focused.append(m)
        if focused:
            speaker=max(focused,key=lambda m:m['start']);boundary=speaker['start']
            narrowed=[]
            for event in result['events']:
                actors=[m for m in event['actors'] if m['start']>=boundary or (m['country']==speaker['country'] and m.get('public'))]
                if actors and event['action']['start']>=boundary:narrowed.append(dict(event,actors=actors))
            if narrowed:result['events']=narrowed
        for e in result['events']:
            key=(e['action']['start'],tuple(sorted((m['country'],m['start']) for m in e['actors'])))
            unique[key]=e
        result['events']=list(unique.values())
        result['countries']=sorted({m['country'] for e in result['events'] for m in e['actors']})
        return result

    def anchor_pool(self,record,full):
        fid=record['file_id']
        if fid in self.cache:return self.cache[fid]
        pool=[]
        for m in re.finditer(r'[^。！？；;\n]+[。！？；;\n]*',full):
            text=m.group()
            effect=re.search(r'[，,](?=(?:预计|有望|这将|从而有望))',text)
            if effect and re.search(r'发布|公布|通过|签署',text[:effect.start()]):text=text[:effect.start()]
            if len(text)>1000 or not XTOPIC.search(text):continue
            if nonpolicy_reason(text)[0]:continue
            relation=self.relation(text,m.start())
            if not relation['countries'] or self.level(text,relation)!='national':continue
            if policy_state(text) in {'campaign','not_adopted','draft_or_proposal','proposed_change','discussion'} or FUTURE_PUBLICATION.search(text):continue
            if not FORMAL.search(text) or not (INSTRUMENT.search(text) or MEASURE.search(text)):continue
            pool.append(dict(start=m.start(),end=m.start()+len(text),text=text,countries=relation['countries'],names=names(text),relation=relation))
        self.cache[fid]=pool
        return pool

    def connect(self,text,a,b,record,full):
        anchor,reason=self._connect_impl(text,a,b,record,full)
        if anchor:
            current={m['country'] for m in self.mentions(text,a) if m['role'] in {'public_actor','country_candidate'}}
            if current-set(anchor['countries']):
                return None,'当前国别与同名政策发布者相冲突'
        return anchor,reason

    def _connect_impl(self,text,a,b,record,full):
        if nonpolicy_reason(text)[0]:return None,'非措施内容不接受政策主体继承'
        original,reason=super().connect(text,a,b,record,full)
        if reason in {'同名政策具有多个发布国家','当前国别与同名政策发布者相冲突'}:return None,reason
        anchors=self.anchor_pool(record,full)
        relevant=[p for p in anchors if p['end']<=a and a-p['end']<=1600]
        current_names=names(text)
        if current_names:
            return original,reason
        # 指代词的政策类型是约束：前文外国减排目标不与“该战略”竞争。
        ref_type=re.match(r'\s*(?:该|上述|这项)(战略|法律|条例)',text)
        if ref_type:
            typed=[p for p in relevant if ref_type[1] in p['text'] and re.search(r'发布|公布|通过|颁布|制定|首次提出',p['text'])]
            if typed and len({c for p in typed for c in p['countries']})==1:
                p=max(typed,key=lambda q:q['end'])
                bridge=full[p['end']:a]
                if len(bridge)<350 and not re.search(r'另一方面|相比之下|专家认为|分析师认为',bridge):
                    return p,'政策指代类型一致→前文已发布同类战略/法律→发布国家'
        if not DEICTIC.search(text) or not (GOAL_DETAIL.search(text) or DETAIL.search(text) or re.search(r'节能|减排|绿色清洁',text)):
            return original,reason
        new_sectors={k for k,pattern in SECTORS.items() if re.search(pattern,text)}
        candidates=[]
        for p in relevant:
            bridge=full[p['end']:a]
            if re.search(r'相关阅读|推荐阅读|上一篇|下一篇|另一方面|相比之下|专家认为|分析师认为',bridge):continue
            if LOCAL_WORDS.search(bridge):continue
            old_sectors={k for k,pattern in SECTORS.items() if re.search(pattern,p['text'])}
            shared_fields=set(re.findall(r'机场|建筑|住宅|港口|公共交通|农业|农林|食品',text))&set(re.findall(r'机场|建筑|住宅|港口|公共交通|农业|农林|食品',p['text']))
            if old_sectors and new_sectors and not old_sectors&new_sectors and not shared_fields and not re.search(r'战略|十点计划|绿色增长|能源基本计划',p['text']):continue
            candidates.append(p)
        countries={c for p in candidates for c in p['countries']}
        if len(countries)>1:return None,'存在多个合理国家政策锚点，未盲目继承最近国名'
        if original:return original,reason
        if not candidates:
            # 正式国家战略分项可跨较长列表；必须有具名已发布战略，不跨竞争公共主体。
            if re.match(r'\s*\d+[、.．]',text):
                candidates=[p for p in anchors if p['end']<=a and a-p['end']<=5000 and p['names'] and re.search(r'发布|公布',p['text'])]
                if len({c for p in candidates for c in p['countries']})!=1:return None,reason
            else:return None,reason
        p=max(candidates,key=lambda p:p['end'])
        others=[q for q in anchors if p['end']<=q['start']<a and set(q['countries'])!=set(p['countries'])]
        if others:return None,'同一连接路径内有竞争政策发布者'
        return p,'有约束的承接句/策略分项→已发布政策→公共机构→国家'

    def assess_unit(self,record,full,doc,a,b):
        t=full[a:b];e=super().assess_unit(record,full,doc,a,b)
        e['algorithm_version']=VERSION
        def change(route,reason):
            e.update(route=route,reason='补漏与连接修订：'+reason)
            return e
        route,why=nonpolicy_reason(t)
        if route:return change(route,why)
        if e['policy_state']=='announced_or_adopted' and re.search(r'(?:到|在)20\d\d年.{0,18}(?:达到|实现)(?:碳中和|净零排放)',t):
            e['policy_state']='announced_goal'
        if e['policy_state'] in {'announced_or_adopted','announced_goal'} and re.search(r'(?:将|计划|未来几年)[^。；]{0,35}投资\d+(?:\.\d+)?(?:万亿|亿|万)?(?:美元|英镑|欧元|日元)',t) and not re.search(r'已(?:经)?(?:拨付|支付|投资)|实际支出',t):
            e['policy_state']='announced_funding_plan'
            e['implementation_claim']='原文为已公布计划中的未来投资安排；不推定资金已经批准、拨付或支出'
        if re.search(r'选举期间|竞选期间|威胁要.{0,15}(?:退出|撤销|废除)',t):
            e['policy_state']='campaign';return change('campaign','竞选/威胁主张，未当成已经退出或实施')
        if len(t)<110 and re.match(r'\s*【免责声明】',full[b:b+70]):
            return change('content_uncertain','只剩短标题及免责声明，没有正文措施证据；不按完整政策自动通过')
        if re.search(r'将(?:于[^。；]{0,15})?退出|退出将于',t) and not re.search(r'已(?:经)?退出|正式退出了|已经生效',t):
            e['policy_state']='announced_withdrawal'
            e['implementation_claim']='保留未来退出/生效期限；不标为已经退出'
        before=full[max(0,a-1200):a]
        if re.match(r'\s*[一二三四五六七八九十]是',t) and re.search(r'(?:正在研究如何|备选|可选).{0,100}(?:种|个|形式|方式)|有\d种.{0,10}形式',before):
            e['policy_state']='proposed_change';return change('discussion','前文列举可选行动路径；当前编号项并非已经采取的措施')
        if re.search(r'酝酿.{0,20}(?:法案|预算|提案)|尚待.{0,20}(?:国会|议会).{0,8}(?:通过|批准)',t):
            e['policy_state']='draft_or_proposal';return change('draft','原文仍在酝酿或待审议，国家明确也不能通过')
        if FUTURE_RELEASE.search(t):
            e['policy_state']='draft_or_proposal';return change('draft','未来发布不等于已经公布')
        # 仅将同方案的预算条款置于待批准状态，不把已发布的方向目标一并否定。
        plan_before=full[max(0,a-4500):a]
        pending_after=full[b:min(len(full),b+6500)]
        fiscal=bool(re.search(r'\d+(?:\.\d+)?(?:万亿|亿|万)(?:美元|英镑|欧元|日元)',t) and re.search(r'投资|建立|拨款|设立|支出|预算',t))
        pending=re.search(r'(?:该方案|该计划|基建计划|基础设施计划|法案).{0,18}(?:仍需|能否|还须|需要|想顺利通过|通过国会|国会批准)|国会会批准吗',pending_after)
        if fiscal and pending and re.search(r'公布|宣布|发布',plan_before) and re.search(r'《[^》]{2,50}(?:计划|方案|法案)》',plan_before) and not re.search(r'已(?:经)?(?:批准|通过|拨付)|正式生效',t):
            e['policy_state']='draft_or_proposal'
            e['evidence'].append(evidence(full,b+pending.start(),b+pending.end(),'同方案后文仍需批准线索；不推定预算已经生效'))
            return change('draft','当前是资金/预算分项，关联后文同方案待国会批准；不把公布意向等同获批拨款')
        if re.search(r'设定了?(?:20\d\d年[、，,及以后的]*)+具体发展目标',t) and not re.search(r'\d+[%％]|万吨|亿元|吉瓦|兆瓦|万辆|减排\d',t):
            return change('background','只说明目标存在与年份，没有具体目标内容；可作关联背景')
        if e['route'] in {'draft','campaign','local_policy','local_execution','quality_unknown','noise','background','science','introduction','non_g20'}:
            return e
        if FUTURE_PUBLICATION.search(t) and e['route']!='main_explicit':return e
        # 评论、预测、企业自主安排不因补了机构别名而直接放行。
        if re.search(r'统计显示|数据显示|预计|有望|可能|专家认为|分析师|学者认为|首相认为|部长认为',t):return e
        relation=self.relation(t,a);actors=[m for x in relation['events'] for m in x['actors']]
        public=[m for m in actors if m.get('public') and m.get('level')!='local']
        quota=bool(re.search(r'配额制',t) and re.search(r'每年.{0,20}(?:要|必须|保障)|不得|义务|适用不同配额',t))
        if any(m.get('level')=='local' for m in actors):return e
        anchor,why=self.connect(t,a,b,record,full)
        if why=='存在多个合理国家政策锚点，未盲目继承最近国名' and not public:
            return change('subject_unknown',why)
        substantive=bool(MEASURE.search(t) and (ACTION.search(t) or GOAL_DETAIL.search(t) or quota or relation['events']))
        if re.match(r'\s*[^：:。]{2,18}[：:]',t) and re.search(r'节能|减排|碳封存|绿色清洁',t):substantive=True
        topical=bool(XTOPIC.search(t) or anchor and XTOPIC.search(anchor['text']))
        if not substantive or not topical:return e
        countries=relation['countries'] if public or quota else anchor['countries'] if anchor else []
        if not countries:return e
        if e['route']=='private_project' and not (quota or re.search(r'拨款|资金支持|补贴|资助',t) and public):return e
        if e['route']=='commentary':return e
        obligation=bool(anchor and re.search(r'根据.{0,45}计划.{0,25}需要制定|(?:法律|法案|条例).{0,20}(?:要求|规定)',t))
        if obligation and e['policy_state']=='discussion':e['policy_state']='execution_requirement'
        if e['policy_state']=='discussion' and public and re.search(r'(?:要求|指示).{0,45}(?:研究|探讨|讨论)',t):
            e['policy_state']='announced_or_adopted';e['implementation_claim']='仅指正式研究指示，不推定所研究工具已实施'
        if e['policy_state'] in {'campaign','not_adopted','draft_or_proposal','proposed_change','conditional_proposal','discussion'}:
            return change('campaign' if e['policy_state']=='campaign' else 'discussion' if e['policy_state']=='discussion' else 'draft',
                '内容识别和状态分流须一致；讨论、竞选或待采纳状态不能因角色补全而进入主集')
        if e['route'].startswith('main_'):return e
        if not public and not quota and not anchor:return e
        if not set(countries)<=G20:return e
        e.update(countries=sorted(countries),policy_level='national',country_basis='公共主体动作或可追溯同政策连接',
            confidence_level='规则性关系证据，非校准概率',roles=dict(e['roles'],actors=public or actors or [m for x in anchor['relation']['events'] for m in x['actors']],
                actions=[x['action'] for x in relation['events']]))
        if re.search(r'(?:将|计划|年内|到20\d\d年)[^。；]{0,25}停止.{0,25}(?:煤|核电|支援|支持)',t):e['policy_state']='announced_phaseout'
        if anchor and not public:
            e['connection_path']=[dict(from_text=t,to_text=anchor['text'],relation=why),
                                  dict(from_text=anchor['text'],to_text='、'.join(countries),relation='发布主体→国家')]
            e['evidence'].append(evidence(full,anchor['start'],anchor['end'],'已发布政策与机构连接证据'))
        # 正式指示开展研究是已经发出的行政安排，不当作碳价已经征收。
        if re.search(r'(?:要求|指示).{0,45}(?:研究|探讨|讨论)',t) and re.search(r'碳定价',t):
            e['policy_state']='announced_or_adopted';e['implementation_claim']='仅指研究/协同指示，不推定碳定价已采纳或实施'
        return change('main_explicit','公共措施成立；补回机构、配额义务、公共资助或同政策承接关系')

    def assess(self,record,full,doc,doc_records):
        text=record['text'];cut=None
        # 明确并列连接的政治评价与独立退出事实，按字面区间切分，不补写主语。
        mixed=re.search(r'[，,](?:并且|并)?让(?=(?:美国|中国|日本|韩国|英国|法国|德国)正式退出)',text)
        if mixed and re.search(r'不认为.{0,20}(?:气候|问题)',text[:mixed.start()]):
            cut_at=mixed.end();parts=[]
            for x,y in [(0,cut_at),(cut_at,len(text))]:
                child=dict(record,text=text[x:y],start=record['start']+x,end=record['start']+y)
                rows=super().assess(child,full,doc,doc_records)
                if x==0:
                    for row in rows:row.update(route='commentary',reason='政治态度前项；后项公共措施另按原文拆出')
                for row in rows:row['split_basis']='明确并列评价/事实边界，原文位置不变'
                parts+=rows
            return parts
        # 仅切可直接定位的重复报道和导航尾部；不改写正文。
        nav=re.search(r'继续阅读|全站导航|分享到|看不清换一张|领\d+期货',text)
        if nav and PUBLIC_CUE.search(text[:nav.start()]) and XTOPIC.search(text[:nav.start()]):
            cut=nav.start();prefix=text[:min(24,len(text))]
            repeat=text.find(prefix,len(prefix))
            if repeat>=len(prefix):
                cut=min(cut,repeat)
                if text[:cut].endswith('汇通网'):cut-=3
        if cut and cut>20:
            first=dict(record,text=text[:cut],end=record['start']+cut)
            rest=dict(record,text=text[cut:],start=record['start']+cut)
            result=super().assess(first,full,doc,doc_records)
            remainder=self.assess_unit(rest,full,doc,rest['start'],rest['end'])
            remainder.update(route='noise',reason='补漏与连接修订：重复报道或可定位的网站导航尾部')
            return result+[remainder]
        return super().assess(record,full,doc,doc_records)
