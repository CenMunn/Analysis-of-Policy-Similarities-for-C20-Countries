"""V7：以主断言和角色范围修补，保留V6.1及旧参考。"""

import re

from ..政策内容判定.assertion_guard import AssertionScope

from ..主体与国家归属.national_scope import evidence

VERSION='policy-semantic-release-20261022.7'

APPRAISAL=re.compile(r'(?:痛批|怒批)[^。；]{0,45}(?:决定|声明|政策)|'
                    r'是[一件个项“”\s]*(?:令人|让人).{0,12}(?:失望|遗憾|悲哀)|'
                    r'(?:承诺|目标|政策|策略).{0,50}(?:意义重大|意义深远)|'
                    r'这是[^。；]{0,55}之后的[^。；]{0,15}[“"](?:动作片|大动作)|'
                    r'(?:此次投资|这项投资|此次项目|该项目)体现了|'
                    r'一系列原因推动[^。；]{0,35}出台上述|政策背后的政治博弈')

RECOMMEND=re.compile(r'(?:咨询团体|专家|研究机构|学者|协会).{0,20}(?:表示|认为|建议)[，,:：]?[^。；]{0,30}政府应(?:当|该)?(?:计划|考虑|采取|提高|制定)')

JOINT_NAMES={'法德':['法国','德国'],'德法':['德国','法国'],'中美':['中国','美国'],'中法':['中国','法国'],
             '中德':['中国','德国'],'中俄':['中国','俄罗斯'],'英法':['英国','法国'],'日澳印':['日本','澳大利亚','印度']}

def discourse_veto(t):
    if APPRAISAL.search(t):return 'commentary','主谓关系是批评、比喻、意义/投资效果评价；内嵌政策提及不等于措施断言'
    if RECOMMEND.search(t) and not re.search(r'政府.{0,15}(?:宣布采纳|已采纳|决定采纳)',t):return 'discussion','第三方建议政府应采取措施，未声称政府已采纳'
    if re.search(r'(?:陆续|相继)发布了?[^。；]{0,25}(?:最新规划|最新计划)[。；]?',t) and not re.search(r'补贴|税率|到.{0,8}年.{0,8}(?:达到|实现)|规定|要求',t):
        return 'introduction','多国规划发布的引导概述，具体规划在后文分别识别'
    return None,None

class ReleaseScope(AssertionScope):
    def connect(self,text,a,b,record,full):
        if discourse_veto(text)[0]:return None,'主断言不接受国家继承'
        return super().connect(text,a,b,record,full)

    def anchor_pool(self,record,full):
        return [p for p in super().anchor_pool(record,full) if not discourse_veto(p['text'])[0]]

    def assess_unit(self,record,full,doc,a,b):
        e=super().assess_unit(record,full,doc,a,b);t=full[a:b];e['algorithm_version']=VERSION
        route,why=discourse_veto(t)
        if route:
            e.update(route=route,reason='V7主断言核验：'+why)
            if route=='discussion':e['policy_state']='discussion'
            e['discourse_evidence']=evidence(full,a,b,why)
            return e
        if e['route'].startswith('main_'):
            if e['policy_state']=='announced_or_adopted' and re.search(r'计划(?:到)?20\d\d年[^。；]{0,35}(?:达到峰值|实现碳中和|实现净零|比重提高到)',t) and not re.search(r'法案|法律|条例|拨款|税率',t):
                e['policy_state']='announced_goal'
                e['implementation_claim']='文件发布中的未来目标，未声称已经达成目标'
            if re.search(r'(?:国民议会|众议院|参议院|议会|国会)[^。；]{0,20}通过[^。；]{0,40}(?:法案|法律)',t) and not re.search(r'尚未|未能|拟议|如果|有望',t):
                e['policy_state']='legislative_passage'
                e['implementation_claim']='原文所述机构通过的立法阶段，不推定已完成全部立法程序或生效'
            for name,participants in JOINT_NAMES.items():
                if re.search(re.escape(name)+r'[^。；]{0,30}(?:合作计划|合作协议|联合声明)',t) and re.search(r'公布|签署|发布|达成',t):
                    actors=[m for m in e['roles']['actors'] if m.get('public') and m.get('level')!='local']
                    if not actors:continue
                    e.update(event_type='joint_policy',countries=sorted(participants),
                         country_basis='具名国家间合作安排；发布主体与合作参与方分列',reason='V7共同事件：一个合作安排，多参与方，不拆成无关联重复政策')
                    e['roles'].update(actors=actors,cooperation_countries=sorted(participants),
                         implementation_countries=sorted({m['country'] for m in self.mentions(t,a) if re.search(r'在|和|及',t[max(0,m['start']-a-2):m['start']-a])}))
                    e['joint_evidence']=evidence(full,a,b,'具名共同安排及发布者；不推定所有参与方均已完成国内程序')
                    break
        return e

    def assess(self,record,full,doc,doc_records):
        t=record['text'];segments=[]
        # 标题紧接明确日期；只切可定位前缀，不删任意短句。
        heading=re.match(r'^\s*[一二三四五六七八九十]+做好[^。；]{0,25}工作(?=(?:19|20)\d\d年)',t)
        if heading:segments=[(0,heading.end(),'introduction'),(heading.end(),len(t),None)]
        # 评价前项与有独立年份、政府、动作的事实后项。
        praise=re.search(r'[，,](?=(?:19|20)\d\d年[^，。；]{0,10}政府)',t)
        if not segments and praise and re.search(r'大获成功|取得成功|显著成效',t[:praise.start()]):
            segments=[(0,praise.end(),'commentary'),(praise.end(),len(t),None)]
        # 公共主体的可执行生态策略与宣传尾句分离；主体证据保存原句位置。
        core=re.search(r'增加森林面积',t);tail=re.search(r'[，,]为实现[^。；]{0,80}作出更大贡献',t)
        actors=[m for m in self.mentions(t,record['start']) if m.get('public') and m.get('level')!='local']
        if not segments and core and tail and core.start()<tail.start() and actors and re.search(r'强调|要求|提出|宣布',t[:core.start()]):
            segments=[(0,core.start(),'background'),(core.start(),tail.start(),'strategy_core'),(tail.start(),len(t),'commentary')]
        if not segments:return super().assess(record,full,doc,doc_records)
        result=[]
        for x,y,forced in segments:
            if y<=x:continue
            child=dict(record,text=t[x:y],start=record['start']+x,end=record['start']+y)
            rows=super().assess(child,full,doc,doc_records)
            for e in rows:
                e['semantic_split']=dict(parent_start=record['start'],parent_end=record['end'],method='独立标题/评价边界切分，不改写原文')
                if forced=='strategy_core':
                    e.update(route='main_explicit',countries=sorted({m['country'] for m in actors}),policy_level='national',policy_state='announced_strategy',
                         reason='V7拆分：国家公共主体提出的森林面积、质量及碳汇策略，宣传尾句另归档',country_basis='同一句国家公共主体与策略动作',
                         connection_path=[dict(from_text=e['text'],to_text=t[:core.start()],relation='同句策略内容→明确公共发言主体')])
                    e['roles']['actors']=actors;e['evidence'].append(evidence(full,record['start'],record['start']+core.start(),'同句国家公共主体与指示动作'))
                elif forced:e.update(route=forced,reason='V7原文拆分：标题、评价或宣传部分另存，不进入措施正文')
            result.extend(rows)
        return result
