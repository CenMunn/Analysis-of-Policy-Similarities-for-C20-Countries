"""V6：先识别当前断言，再允许角色及指代补证；保留V5代码与原文。"""

import re

from ..上下文与证据连接.context_scope import RecallLinkScope

from ..主体与国家归属.national_scope import evidence

VERSION = 'policy-assertion-guard-20261022.6.1'

TREATY = re.compile(r'巴黎(?:气候)?(?:协定|协议)|联合国气候变化框架公约|京都议定书')

COMMENT = re.compile(
    r'(?:批评|谴责|欢迎|质疑|赞扬)了?[^。；]{0,55}(?:声明|计划|政策|决定|战略)|'
    r'(?:是|成为|构成).{0,14}(?:主要瓶颈|最大障碍)|'
    r'(?:无疑|势必|显然|必然)(?:将会|会|将)?(?:推动|带动|促进|加速)|'
    r'(?:作出|做出)更大贡献|注入强大动力|期望借.{0,28}(?:刺激|带动)|'
    r'(?:政策|计划|战略|目标|措施|宣布碳中和).{0,16}(?:将对|将会极大促进|是.{0,6}赢家)|'
    r'(?:该计划|该政策)(?:将|会|可以|能)?由资本主义|'
    r'(?:趋势|进程加速)是必然|各方存在严重分歧|'
    r'(?:计划|政策)(?:认为|预计|估算|预测)[，,:：].{0,100}(?:节约|节省|拉动|增长|成本)|'
    r'^(?:专家|分析师|研究人员|学者).{0,12}(?:警告|预测|认为|指出)|'
    r'(?:主要作者|研究作者|专家|分析师|学者).{0,65}(?:说|认为|指出)[：:]')

STATS = re.compile(r'(?:部|局|机构).{0,10}录得.{0,35}(?:投资总额|产量|装机|发电)|'
                   r'截至.{0,25}(?:排放量|发电量).{0,40}(?:已较|已比|同比)|'
                   r'提前完成.{0,55}(?:阶段性减排目标|减排目标)')

OPTION = re.compile(r'(?:正在研究|研究如何|推演|备选|可选|可能途径).{0,40}(?:退出|路径|途径|方式)|'
                    r'(?:退出|路径).{0,20}(?:可能途径|三种|3种)')

NONFINAL = {'campaign','draft_or_proposal','proposed_change','conditional_proposal','discussion','not_adopted','no_change_or_denial'}

def assertion_decision(text):
    """返回阻断/分流理由；None表示仍须经过原有公共措施、层级、角色检查。"""
    checks=[
        ('noise',r'^\s*[（(]?(?:原标题|资料来源)[：:]','网页标题/资料引用元信息，不是可直接用于比较的政策事实'),
        ('industry_standard',r'团体标准.{0,90}(?:协会|学会).{0,16}(?:批准|发布)','协会团体标准不等于国家强制公共政策；未发现政府采纳该标准的证据'),
        ('background',STATS.pattern,'政府或机构报告统计结果，不等于政府采取措施'),
        ('commentary',COMMENT.pattern,'本句主断言是反应、评价、效果推测或学者观点；政策名称只是被谈论对象'),
        ('commentary',r'^(?:英国|美国|中国|日本|德国|法国)[^。；]{0,70}政府一直在积极推动[^。；]{0,45}政策却朝着','多国政策方向的笼统比较，没有可定位的公共工具'),
    ]
    for route,pattern,reason in checks:
        m=re.search(pattern,text)
        if not m:continue
        if route=='industry_standard' and re.search(r'(?:政府|国务院|国家能源局).{0,15}(?:要求|规定|决定采用|强制)',text):continue
        return dict(route=route,reason=reason,cue=m.group(),cue_start=m.start(),cue_end=m.end())
    if TREATY.search(text):
        global_actor=re.search(r'(?:近|超过|约)?\d{2,3}(?:多)?个(?:国家(?:领导人)?|缔约方)',text)
        generic_rule=re.search(r'缔约方.{0,20}(?:才可以|可以|必须|应当)|保存人收到退出通知',text)
        if global_actor or generic_rule:
            m=global_actor or generic_rule
            return dict(route='international_framework',reason='国际条约共同缔约或一般程序条款，不能继承相邻单一国家作为发布主体',cue=m.group(),cue_start=m.start(),cue_end=m.end())
    return None

class AssertionScope(RecallLinkScope):
    def __init__(self,raw_mentions):
        super().__init__(raw_mentions)
        self.guard_anchor_cache={}

    def anchor_pool(self,record,full):
        fid=record['file_id']
        if fid not in self.guard_anchor_cache:
            pool=super().anchor_pool(record,full)
            self.guard_anchor_cache[fid]=[a for a in pool if not assertion_decision(a['text'])]
        return self.guard_anchor_cache[fid]

    def connect(self,text,a,b,record,full):
        blocked=assertion_decision(text)
        if blocked:return None,'断言门阻断主体继承：'+blocked['reason']
        return super().connect(text,a,b,record,full)

    def relation(self,text,offset):
        rel=super().relation(text,offset)
        # 主语+叫停是已经采取的行政动作；报告来源不是施策主体。
        for m in self.mentions(text,offset):
            tail=text[m['end']-offset:]
            hit=re.match(r'(?:政府)?(?:已经|已|正式)?(叫停|停建|缓建)',tail)
            if hit and m.get('role') in {'public_actor','country_candidate'}:
                actor=dict(m,public=True,level=m.get('level','national'))
                pos=m['end']+hit.start(1)
                rel['events'].append(dict(actors=[actor],action=dict(start=pos,end=pos+len(hit[1]),text=hit[1]),method='明确国家主语与行政停建动作'))
        rel['countries']=sorted({m['country'] for e in rel['events'] for m in e['actors']})
        return rel

    def assess_unit(self,record,full,doc,a,b):
        t=full[a:b]
        e=super().assess_unit(record,full,doc,a,b)
        e['algorithm_version']=VERSION
        e['assertion_gate']=dict(outcome='未命中阻断；仍沿用公共措施/角色/层级检查',calibrated_probability=False)
        def change(route,reason,state=None,decision=None):
            e.update(route=route,reason='断言与状态核验：'+reason)
            if state:e['policy_state']=state
            e['assertion_gate']=dict(outcome=route,reason=reason,evidence=dict(start=a,end=b,text=t),calibrated_probability=False)
            if decision:e['assertion_gate']['trigger']=dict(start=a+decision['cue_start'],end=a+decision['cue_end'],text=decision['cue'])
            return e
        blocked=assertion_decision(t)
        if blocked:return change(blocked['route'],blocked['reason'],decision=blocked)
        before=full[max(0,a-650):a];after=full[b:b+420]
        # 在同一候选人的竞选假设范围内，摘要不因写“制定”而变成在任政策。
        campaign=re.search(r'(?:如果|若)拜登.{0,8}(?:胜选|入主白宫|当选)',before+after)
        if '拜登' in t and campaign and not re.search(r'上任|上台|就职|已重返|已经签署|已正式',t):
            if '内容摘要' in t or re.search(r'政策与?计划|工厂零排放',t):
                pos=max(0,a-650)+campaign.start() if campaign.start()<len(before) else b+campaign.start()-len(before)
                e['evidence'].append(evidence(full,pos,pos+len(campaign.group()),'同一候选人竞选假设语境'))
                return change('campaign','摘要中的主张受同一候选人胜选条件约束，未当成在任公共措施','campaign')
        if re.match(r'\s*(?:第[一二三四五六七八九十123456789]+种|[一二三四五六七八九十]是)',t) and OPTION.search(before):
            return change('discussion','当前是前文列举的备选路径，未声称已采取','proposed_change')
        if re.search(r'(?:尚未|没有|并未)(?:正式)?(?:决定|宣布|批准).{0,15}(?:退出|取消|关闭|废除)',t):
            return change('discussion','否定决定或批准，不能转换为已采取动作','not_adopted')
        if re.search(r'宣布(?:将|计划)?退出',t) and not re.search(r'退出.{0,12}(?:已生效|已经生效)|已经正式退出|正式退出了',t):
            e['policy_state']='announced_withdrawal'
            e['implementation_claim']='仅声称宣布退出；生效日另核，不推定已经完成退出'
        if re.search(r'(?:政府)?计划将.{0,30}(?:转换|改造)|到20\d\d年.{0,40}(?:退役|关闭)',t) and not re.search(r'已(?:经)?(?:完成|退役|关闭)',t):
            e['policy_state']='announced_phaseout'
        if re.search(r'(?:目标是|同意在|承诺).{0,90}(?:到20\d\d年|本十年|减排|排放量|发电|供电)',t) and e['route'].startswith('main_'):
            e['policy_state']='announced_goal'
        if re.search(r'发电量',t) and re.search(r'\d+(?:\.\d+)?(?:亿|万亿)千瓦(?!时)',t):
            return change('quality_unknown','发电量与功率单位、数量级存在原文疑点；保留原值待核，未擅自修正')
        if e['route'].startswith('main_') and re.search(r'(?:19|20)\d\d年.{0,8}(?:中国|美国|日本|韩国|德国|法国|英国)叫停',t):
            e['policy_state']='implementation'
            e['reason']='断言与状态核验：明确国家主语与过去行政停建动作；报告来源不是施策主体'
            e['implementation_claim']='原文声称当年实际叫停，未推定其它待核准项目也已停建'
        if e['route'] in {'content_uncertain','subject_unknown'} and e['policy_state'] not in NONFINAL:
            rel=self.relation(t,a)
            direct=[m for x in rel['events'] for m in x['actors'] if m.get('public') and m.get('level')!='local']
            cs=sorted({m['country'] for m in direct})
            concrete=re.search(r'(?:要求|决定|宣布).{0,10}(?:停建|缓建)煤电|(?:承诺|宣布).{0,60}(?:风力发电|风电|风力发电场).{0,25}(?:每个家庭|每户家庭)',t)
            if len(cs)==1 and concrete:
                e.update(countries=cs,policy_level='national',country_basis='当前公共主体与明确行政要求或带期限能源目标')
                return change('main_explicit','事实拆净后仍有当前公共主体、具体工具/能源目标，补足措施词覆盖','announced_goal' if re.search(r'家庭',t) else 'execution_requirement')
        # 正式国家目标可被二手报告复述；具体行政停建事实不应被周边另一国家抢走。
        if re.search(r'叫停|停建|缓建',t) and e['route']=='subject_unknown':
            rel=self.relation(t,a)
            direct=[x for x in rel['events'] if x.get('method')=='明确国家主语与行政停建动作']
            cs=sorted({m['country'] for x in direct for m in x['actors']})
            if len(cs)==1 and re.search(r'煤电|燃煤|煤炭',t):
                anchors=[p for p in self.anchor_pool(record,full) if p['countries']==cs and 0<=a-p['end']<=650]
                if anchors:
                    p=max(anchors,key=lambda p:p['end'])
                    e.update(countries=cs,policy_level='national',country_basis='当前叫停主语及同国前文国家行政文件',connection_path=[dict(from_text=t,to_text=p['text'],relation='明确国家动作→国家行政文件')])
                    e['evidence'].append(evidence(full,p['start'],p['end'],'国家行政文件上下文'))
                    return change('main_explicit','报告复述国家明确叫停煤电措施，当前国家关系优先于外国背景','implementation')
        return e

    def assess(self,record,full,doc,doc_records):
        t=record['text'];cuts={0,len(t)}
        if re.match(r'^\s*原标题[：:]',t):
            report=re.search(r'据[^。！？；]{2,45}报道[，,：:]',t)
            if report and re.search(r'(?:政府|总统|首相|部门).{0,45}(?:停止|公布|宣布|实施|决定)',t[report.end():]):
                cuts.add(report.end())
        # 不改写文本；只切独立评价主体/预测从句，不按所有逗号切分。
        boundaries=[r'(?=(?:专家|分析师|研究人员)警告说)',
                    r'[，,](?=因为到20\d\d年.{0,40}(?:需求|增长))',
                    r'[，,](?=旨在重拾.{0,20}领导者地位)',
                    r'[，,](?=由于政策的变化.{0,60}(?:将会|可能))']
        for pattern in boundaries:
            for m in re.finditer(pattern,t):
                prefix=t[:m.start()]
                if re.search(r'宣布|承诺|政府计划|已重返|叫停',prefix) and not re.search(r'如果|倘若|除非|尚未',prefix):
                    cuts.add(m.start())
        if len(cuts)==2:return super().assess(record,full,doc,doc_records)
        out=[];cs=sorted(cuts)
        for x,y in zip(cs,cs[1:]):
            child=dict(record,text=t[x:y],start=record['start']+x,end=record['start']+y)
            rows=super().assess(child,full,doc,doc_records)
            if x==0 and re.match(r'^\s*原标题[：:]',t[x:y]):
                for e in rows:e.update(route='noise',reason='断言拆分：标题与报道引导前缀归档，实际政策正文另存')
            if x and re.match(r'[，,]?(?:专家警告说|分析师警告说|研究人员警告说|因为到|旨在重拾|由于政策的变化)',t[x:y]):
                for e in rows:e.update(route='commentary',reason='断言拆分：独立评价/预测/动机从句，原文单独归档')
            for e in rows:e['assertion_split']=dict(parent_start=record['start'],parent_end=record['end'],rule='清楚的评价主体或因果预测边界；逐字保留原文')
            out.extend(rows)
        return out
