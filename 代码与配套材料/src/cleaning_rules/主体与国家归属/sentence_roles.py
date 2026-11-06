"""动作约束的句内角色抽取。规则实现；不是预训练语义角色模型。"""

import re

from ..主体与国家归属.role_patterns import BARE_BRIDGE

VERSION='policy-roles-2026-10-22.4'

ACTION=re.compile(r'征求意见|禁止销售|停止销售|宣布|公布|发布|颁布|出台|制定|制订|修订|批准|通过|签署|签订|提交|承诺|提出|重申|决定|设定|确定|实行|实施|征收|加征|取消|废除|暂停|冻结|退出|重返|恢复|禁止|启动|设立|拨款|采购|购买|提供|给予|规定|要求|投入|投资|部署|推动|力争|计划|建立|提高|增加|减少|降低|削减|达到|实现|建设')

PRIVATE=re.compile(r'公司|企业|集团|协会|专家|学者|分析师|研究院|媒体|记者|产业|市场|顾问|创始人|的兄弟|的儿子|的女儿')

UNCERTAIN=re.compile(r'若|如果当选|候选人|竞选|建议|呼吁|敦促|希望|应该|应当|否认|尚未|并未|没有|不会|未获|预计|预测|有望|可能|是否|能否|如果|倘若|据传|取决|被爆出|计划宣布|表明他将|得以争取')

POLICY_NOUN=r'计划|政策|规划|战略|法案|条例|办法|方案|路线图|目标|协定|备忘录|标准'

def literal(text,offset,a,b,**kw):
    return dict(start=offset+a,end=offset+b,text=text[a:b],**kw)

class SentenceRoles:
    def __init__(self,mentions):self.mentions=mentions

    def extract(self,text,offset=0):
        mentions=[dict(m) for m in self.mentions(text,offset)]
        for m in mentions:
            a,b=m['start']-offset,m['end']-offset
            if m['country']=='墨西哥' and a>0 and text[a-1:a]=='新' and text[b:b+1]=='州':
                m.update(country='美国',public=True,role='public_actor',start=m['start']-1,end=m['end']+1,text=text[a-1:b+1])
        events=[];targets=[]
        books=[m.span() for m in re.finditer(r'《[^》]+》',text)]
        report=re.search(r'据报道[，,]',text[:180])
        body_start=report.end() if report and re.search(r'点击量|来源[:：]|\|',text[:report.start()]) else 0
        for verb in ACTION.finditer(text):
            if verb.start()<body_start:continue
            if any(a<=verb.start()<b for a,b in books):continue
            tail=text[verb.end():]
            if re.match(r'的|在|中|后|前|时期|方面|以来|得以|是否|能否|问题',tail):continue
            if verb.group()=='通过' and not re.match(r'(?:了|一项|《|[^，。]{0,12}(?:法案|法律|条例|预算))',tail):continue
            if verb.group()=='发布' and re.match(r'会|推特|微博',tail):continue
            if verb.group() in {'发布','公布','提出'} and re.match(r'(?:了|的|一份)?(?:年度)?(?:数据|统计|研究|报告|预测)',tail):continue
            if verb.group()=='计划' and not re.match(r'(?:在|于|到|将|投资|投入|建设|建立|提高|增加|减少|实现|取消|逐步)',tail):continue
            # 动词在定语中只指称旧政策，不能单凭它创建新的施策关系。
            if re.match(r'[^，。；]{0,24}的(?:十点|\d+点|能源)?(?:'+POLICY_NOUN+r')',tail):continue
            left=max((m.end() for m in re.finditer(r'[。！？；;\n]',text[:verb.start()])),default=0)
            prior=[m for m in mentions if offset+left<=m['start'] and m['end']<=offset+verb.start() and offset+verb.start()-m['end']<=140]
            eligible=[m for m in prior if m['role'] in {'public_actor','country_candidate'}]
            # 被动句中“被/由”后是施策者；被动句头部的国家是受事。
            passive=list(re.finditer(r'被|由',text[left:verb.start()]))
            if passive:
                split=left+passive[-1].end()
                after=[m for m in eligible if m['start']>=offset+split]
                if after:
                    eligible=after
                    targets.extend(dict(m,role='target') for m in prior if m['end']<=offset+split-1)
            if not eligible:continue
            actor=eligible[-1];bridge=text[actor['end']-offset:verb.start()]
            if PRIVATE.search(bridge) and not re.search(r'(?:对|向|为)[^，。]{0,35}(?:公司|企业)[^，。]{0,8}$',bridge):continue
            if re.search(r'的(?:能源|新能源|气候|减排)?(?:政策|计划|目标|战略)|认为|反驳|质疑|指责|指控|效应|导致|造成|受到|根据|依据|按照',bridge):continue
            if re.search(r'机组|数据分析机构|统计|报告|研究|时期|问题|所需|^因|(?:以|为了|旨在|用来)$',bridge):continue
            speech=re.search(r'(?:表示|指出|强调|说)[，,：:]\s*[“"]?(.*)$',bridge)
            if speech and not re.match(r'将|要|须|应|必须|不得|我们|本国|政府|到20\d\d|在20\d\d',speech[1]):continue
            # 不从“在某国/来自某国”推定施策者，不跨越请求另一国实施的控制结构。
            prefix=text[max(left,actor['start']-offset-8):actor['start']-offset]
            if re.search(r'(?:在|位于|来自|针对|对|向|为|帮助|协助|会见|接见|呼吁|要求|取决|同|与)\s*$',prefix) and not passive:continue
            if not actor['public']:
                clean=bridge
                for m in prior:
                    if m['role']=='target':clean=clean.replace(m['text'],'')
                clean=re.sub(r'联合国大会|气候峰会|坚定不移地|则|已经|两国|双方|共同|联合|等国|纷纷|跟进|相继|承诺|决定|打算|效仿|借鉴|力争|还将|之后|之前|表示|都|前|后','',clean)
                if not BARE_BRIDGE.fullmatch(clean):continue
            if UNCERTAIN.search(text[left:verb.end()]):continue
            # 执行谓词沿用本句明确发出的安排；“要求中国减少”不能把中国当施策者。
            issuers=[actor]
            for m in reversed(eligible[:-1]):
                join=text[m['end']-offset:issuers[0]['start']-offset]
                joint=True
                if re.fullmatch(r'\s*(?:和|与|及|、|欧洲)+\s*',join) and joint:issuers.insert(0,m)
                else:break
            end=min((m.start() for m in re.finditer(r'[。！？；;\n]',text[verb.end():])),default=len(tail))+verb.end()
            status='目标或未来安排' if re.search(r'将|拟|计划|打算|目标|力争',text[left:end]) else '原文声称的措施'
            event=dict(action=literal(text,offset,verb.start(),verb.end()),
                       actors=[dict(m,role='施策主体') for m in issuers],
                       object=literal(text,offset,verb.end(),end),status=status,
                       method='句内动作约束角色')
            events.append(event)
        # 受事包括对/向等引导的对象，以及被动句头受事；不从国家频次创建角色。
        targets.extend(dict(m,role='target') for m in mentions if m['role']=='target')
        owners=sorted({m['country'] for e in events for m in e['actors']})
        # 明确双边联合声明即使只写一位领导人，也不能当成其本国独有政策。
        for name,pair in [('中美',['中国','美国']),('中欧',['中国','欧盟']),('美欧',['美国','欧盟'])]:
            declaration=re.search(r'《'+name+r'[^》]{0,35}联合声明》',text)
            if not events or not declaration:continue
            own_after=any(e['action']['start']>=offset+declaration.end() and any(m['start']>=offset+declaration.end() for m in e['actors']) for e in events)
            if not own_after:owners=sorted(set(owners)|set(pair))
        return dict(version=VERSION,events=events,countries=owners,
                    targets=list({(m['start'],m['end'],m['country']):m for m in targets}.values()),
                    resolved=len(owners)==1,method='句内动作约束角色' if owners else '',anchor=None)
