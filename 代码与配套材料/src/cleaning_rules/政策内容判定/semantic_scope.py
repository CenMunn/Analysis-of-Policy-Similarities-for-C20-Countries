"""V7.1：依据新增16条开发审查，修正层级、审查状态和公共贷款。"""

import re

from ..政策内容判定.assertion_scope import ReleaseScope,discourse_veto

from ..主体与国家归属.national_scope import evidence

VERSION='policy-semantic-release-20261022.7.1'

PROVINCES='山西|陕西|山东|广东|广西|四川|云南|贵州|河北|河南|湖北|湖南|浙江|江苏|安徽|福建|江西|甘肃|青海|辽宁|吉林|黑龙江|海南|北京|上海|天津|重庆|内蒙古|新疆|宁夏|西藏'

LOCAL=re.compile(r'(?:'+PROVINCES+r')(?:省|市|自治区)?(?:发展和改革委员会|发改委|能源局|财政厅|生态环境厅|政府)[^。；]{0,20}(?:发布|印发|公布|出台|制定)')

class ReleaseScope71(ReleaseScope):
    def assess_unit(self,record,full,doc,a,b):
        e=super().assess_unit(record,full,doc,a,b);t=full[a:b];e['algorithm_version']=VERSION
        if re.search(r'本文引用地址|https?://',t) and re.search(r'[A-Za-z]{2,}\?',t):
            e.update(route='quality_unknown',reason='V7.1网页URL与截断缩写混入政策句；隔离原文，不能当纯政策正文');return e
        if LOCAL.search(t):
            if re.search(r'落实|执行|贯彻',t) and re.search(r'国家|国务院|中央',t):
                e.update(route='local_execution',policy_level='local_execution',reason='地方落实信息另存，需要关联国家文件，未将新增地方要求提升为国家政策')
            else:e.update(route='local_policy',policy_level='local',reason='V7.1具名省市公共机构独立发布政策；不进入国家比较')
            return e
        if re.search(r'(?:承诺|策略|计划|政策)[^。；]{0,25}(?:进一步)?证明[，,]?',t) and not re.search(r'规定|补贴|税率|达到\d|减排\d|20\d\d年.{0,10}(?:实现|达到)',t):
            e.update(route='commentary',reason='V7.1主断言是证明某趋势的评价，无新增政策要求');return e
        if e['route'].startswith('main_') and re.search(r'要求.{0,12}(?:修改或废除|修改或取消|重新审查|评估修改)',t):
            e.update(policy_state='announced_review',implementation_claim='已经要求审查/修改选项，不声称被审查政策已经废除')
        # 国家机构实际提供贷款与企业自主投资分开；拒绝、拟议、建议不自动提升。
        if e['route']=='content_uncertain' and re.search(r'电动汽车|可再生能源|清洁能源|节能|光伏|风电',t) and not re.search(r'拟|建议|若|如果|尚未|未提供|没有提供',t):
            actors=[m for m in self.mentions(t,a) if m.get('public') and m.get('level')=='national' and re.match(r'.{0,10}提供了?[^。；]{0,35}(?:低成本贷款|低息贷款|贷款担保|优惠贷款)',t[m['end']-a:])]
            if actors:
                e.update(route='main_explicit',countries=sorted({m['country'] for m in actors}),policy_level='national',policy_state='implementation',
                    reason='V7.1国家公共机构提供优惠贷款，企业是受款对象，不是施策主体',country_basis='句内公共机构→实际提供贷款')
                e['roles']['actors']=actors;e['evidence'].append(evidence(full,a,b,'公共机构优惠贷款事实，金额原样保留'))
        if e['route']=='content_uncertain' and re.search(r'比例不低于|不得超过|必须达到',t):
            prior=full[max(0,a-500):a]
            m=re.search(r'(?:国家|国务院|政府)[^。；]{0,30}(?:发布|印发)《[^》]+(?:规划|办法|方案)[^》]*》[^。；]*$',prior)
            if m and not re.search(r'拟|草案|征求意见|如果',m.group()):
                cs=sorted({x['country'] for x in self.mentions(m.group(),a-len(prior)+m.start()) if x.get('public')})
                if len(cs)==1:
                    e.update(countries=cs,policy_level='national',policy_state='execution_requirement',
                        route='quality_unknown',reason='V7.1已连接国家规划执行门槛；发布机构/实施状态仍需核实，单列质量核验而非当非政策')
                    e['connection_path']=[dict(from_text=t,to_text=m.group(),relation='紧邻同名国家规划→具体执行比例；未盲继承最近国家')]
                    e['evidence'].append(evidence(full,a-len(prior)+m.start(),a,'具体国家规划与后续门槛连接'))
        return e

    def assess(self,record,full,doc,doc_records):
        t=record['text'];m=re.match(r'^(?:氢政策|能源政策)(?=(?:韩国|日本|美国|德国|法国|中国)第一个)',t)
        if not m:return super().assess(record,full,doc,doc_records)
        result=[]
        for x,y,route in [(0,m.end(),'introduction'),(m.end(),len(t),None)]:
            child=dict(record,text=t[x:y],start=record['start']+x,end=record['start']+y)
            rows=super().assess(child,full,doc,doc_records)
            if route:
                for e in rows:e.update(route=route,reason='章节标题前缀单独归档，保留后面的完整发布事实')
            result+=rows
        return result
