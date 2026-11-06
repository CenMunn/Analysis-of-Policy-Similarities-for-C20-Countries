"""增量语义收尾。证据分数是可解释排序量，未经概率校准；不改写任何原文。"""

import copy, hashlib, json, re

from collections import defaultdict

from ..主体与国家归属.national_scope import (NationalScope, TOPIC, PUBLIC, PRIVATE, ACTION, INSTRUMENT,
    POLICY_REF, LOCAL_WORDS, NATIONAL_SCOPE, evidence)

from ..主体与国家归属.role_resolution import names, G20

from ..政策归并与导出.registry_primitives import norm, facts, goal_facts

VERSION='policy-evidence-closeout-20261022.4'

PARAMETERS=dict(version=VERSION,high_min=80,medium_min=65,source_cap=65,context_cap=79,
    manual_group_limit=50,score_meaning='规则性证据充分程度和排序分，不是正确概率',
    dimensions=['content','country','level','state','quality'],
    score_weights=dict(content=.35,country=.25,level=.15,state=.15,quality=.10),
    uncertainty_policy='不明内容不因国别得分高而保留；低证据复杂项排除主分析并保留证据',
    time_scope='历史政策陈述；不声称现行有效；报道日期和目标日期不填补动作日期')

CONCRETE=re.compile(INSTRUMENT.pattern+r'|许可|限排|排放限制|能源结构|能源多样化|火力发电|清洁氢|低成本融资|技术转让|植树|核电.{0,12}(?:依赖|比例)|能耗(?:信息|标识)|能源.{0,8}标[识示]|产能|充电站|关闭.{0,15}(?:电厂|煤电)|(?:能源|发电).{0,12}(?:比例|份额|占比)|(?:放弃|削减|降低).{0,15}(?:核能|核电|火力)')

REAL_ACTION=re.compile(ACTION.pattern+r'|出台|印发|授权|标示|拒绝加入|提高到|增至|改为|放弃|削减|关闭|淘汰|撤销|建设')

HARD_ACTION=re.compile(r'宣布|公布|颁布|出台|印发|批准|签署|通过|授权|规定|决定|征收|加征|拨款|取消|废除|撤销|拒绝加入|制定了|建立了')

VAGUE=re.compile(r'付诸行动|空话一场|重大转变|加班加点|雄心勃勃|尽最大努力|发展新篇章|需要承担.{0,10}责任')

FORECAST=re.compile(r'预计|预测|分析师|研究主管|研究总监|Wood\s*Mackenzie|伍德.{0,2}麦肯齐|普华永道|《报告》预测',re.I)

SIDE_COMMENT=re.compile(r'[，,](?=(?:此举(?:将|即|可|有望)|这将|从而(?:有望|带动|使)|分析师|分析人士|专家认为|但.{0,8}(?:有望|可能)|这本是|贸易战逐渐|碳减排进程同步))')

POLICY_FILE=re.compile(r'《([^》]{2,100}(?:法|法案|条例|办法|规则|计划|战略|规划|路线图|方案|协定|政策)[^》]{0,20})》')

def digest(prefix,value):
    return prefix+hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:20]

def context_state(text,before):
    if re.search(r'(?:尚未|还未|未能|未|没有|并未|未获|否认|拒绝).{0,3}(?:通过|批准|获批|颁布|出台)',text):return 'not_adopted','动作受否定或尚未获批准，保留未采纳状态'
    conditional=re.search(r'(?:如果|倘若|若|一旦)[^。；]{0,100}(?:批准|通过|签署|获批|当选|得以实施)',text)
    if conditional:
        prior=text[:conditional.start()]
        if not re.search(r'法律规定|法案规定|政府规定|已(?:经)?(?:通过|批准)|正式(?:生效|颁布|公布)',prior):
            return 'conditional_proposal','政策成立仍依赖批准、签署或实施假设，不能当已采纳'
    if re.search(r'推动.{0,12}(?:国会|议会|参议院|众议院).{0,10}通过|寻求.{0,10}(?:通过|批准)',text):return 'draft_or_proposal','仍在推动审议通过，未声称已获通过'
    if re.search(r'审批.{0,18}失败|未能.{0,12}(?:获批|通过)|未获批准|遭到否决|以失败告终',text):return 'not_adopted','未通过的审批结果'
    if re.search(r'(?:将|拟|准备|打算)(?:进一步|正式|首次|尽快)?(?:提出|推出|出台|制定|立法)|计划(?:于|在)?[^，,。；]{0,8}(?:提出|推出|出台|制定|立法)|正在(?:研究)?制定|下一步.{0,20}(?:要|将)制定|拟立法',text):
        if not re.search(r'已(?:经)?(?:批准|通过)|正式(?:批准|通过)',text):return 'draft_or_proposal','尚在制定、拟立法或未来提议阶段'
    if re.search(r'(?:将|拟|准备).{0,8}(?:推翻|撤销|取消|废除)',text) and not re.search(r'已经.{0,15}(?:推翻|撤销|取消|废除)|已于.{0,15}(?:取消|废除)',text):return 'proposed_change','未来拟调整，不能算已撤销'
    draft_points=list(re.finditer(r'草案|征求意见稿|讨论稿',before[-800:]))
    adopted_points=list(re.finditer(r'已经通过|已经批准|正式发布|正式公布|颁布|正式生效',before[-800:]))
    if draft_points and (not adopted_points or draft_points[-1].start()>adopted_points[-1].start()) and re.search(r'政府计划|计划.{0,15}(?:贷款|建造|投资)|草案',text) and not HARD_ACTION.search(text):
        return 'draft_or_proposal','同一段方案仍处于草案背景，当前未见正式通过'
    adopted=bool(re.search(r'(?:已经|已|正式|近日|日前|刚刚).{0,15}(?:签署|公布|通过|批准|宣布)|政府.{0,15}(?:宣布|批准|签署|通过)|(?:国会|议会).{0,15}(?:通过|批准)',text))
    if not adopted and re.search(r'拜登|特朗普|候选人|他的.{0,4}计划',text):
        prior=list(re.finditer(r'如果当选|若当选|竞选|参选|候任|尚未上任',before[-2200:]))
        if prior and re.search(r'计划|将|目标|提案|承诺',text):return 'campaign','同一人物计划处于竞选/候任语境，未见当前正式采纳'
    return None,''

class EvidenceScope(NationalScope):
    def mentions(self,text,offset=0):
        found=super().mentions(text,offset)
        country_map={'中国':'中国','美国':'美国','日本':'日本','韩国':'韩国','德国':'德国','法国':'法国','英国':'英国','印度尼西亚':'印度尼西亚','印尼':'印度尼西亚','沙特':'沙特阿拉伯','加拿大':'加拿大','澳大利亚':'澳大利亚'}
        for m in re.finditer(r'(中国|美国|日本|韩国|德国|法国|英国|印度尼西亚|印尼|沙特|加拿大|澳大利亚)(?:贸易、工业和能源部|贸易、工业与能源部|产业通商资源部|经济产业省|环境省|能源部|财政部|环境部|自然资源部|国家环境保护局)',text):
            a,b=offset+m.start(),offset+m.end();role='target' if re.search(r'(?:对|向|针对|呼吁|要求)\s*$',text[max(0,m.start()-5):m.start()]) else 'public_actor'
            found=[x for x in found if not(a<=x['start'] and x['end']<=b)]
            found.append(dict(country=country_map[m[1]],text=m.group(),start=a,end=b,public=True,level='national',role=role))
        return sorted(found,key=lambda x:(x['start'],-x['end']))

    def relation(self,text,offset):
        result=super().relation(text,offset)
        # 以国家法律为主语的授权和拒绝加入国际条约，不把媒体/企业作为施策者。
        for m in self.mentions(text,offset):
            local=m['end']-offset;tail=text[local:]
            match=re.match(r'(?:《[^》]{2,100}》)(?:明确|规定|授权|要求|禁止|允许)',tail)
            if match and m['role'] in {'country_candidate','public_actor'}:
                verb=re.search(r'明确|规定|授权|要求|禁止|允许',match.group())
                result['events'].append(dict(actors=[m],action=dict(start=offset+local+verb.start(),end=offset+local+verb.end(),text=verb.group()),method='国家法律主体与授权措施'))
            match=re.match(r'(?:政府)?(?:于|在|曾|已|将|近日|日前|[\d年月日，,\s]){0,20}(拒绝加入|出台|印发|放弃|撤销)',tail)
            if match and m['role'] in {'country_candidate','public_actor'}:
                result['events'].append(dict(actors=[m],action=dict(start=offset+local+match.start(1),end=offset+local+match.end(1),text=match[1]),method='补充具体政策工具动作'))
            match=re.match(r'(?:政府)?(?:于|在|就|曾|已|将|还|直接|近日|日前|[\d年月日，,\s]){0,25}(宣布|公布|通过|批准|决定|取消|放弃|启动)',tail)
            prefix=text[max(0,m['start']-offset-6):m['start']-offset]
            if match and m['role'] in {'country_candidate','public_actor'} and not re.search(r'对|向|针对|要求|建议',prefix):
                actor=dict(m)
                if m.get('public') or tail.startswith('政府'):actor.update(public=True,level='national')
                result['events'].append(dict(actors=[actor],action=dict(start=offset+local+match.start(1),end=offset+local+match.end(1),text=match[1]),method='主体与时间副词后的具体公共动作'))
            tax=re.match(r'(?:政府)?(?:已|曾|于|在|[\d年月日\s]){0,16}(上调|下调|调整|提高|降低).{0,18}(?:税|补贴标准)',tail)
            if tax and m['role'] in {'country_candidate','public_actor'}:
                result['events'].append(dict(actors=[m],action=dict(start=offset+local+tax.start(1),end=offset+local+tax.end(1),text=tax[1]),method='国家明确税收或法定补贴调整'))
        result['countries']=sorted({m['country'] for e in result['events'] for m in e['actors']})
        return result

    def connect(self,text,a,b,record,full):
        anchor,reason=super().connect(text,a,b,record,full)
        if anchor or reason in {'同名政策具有多个发布国家','当前国别与同名政策发布者相冲突'}:return anchor,reason
        # 法律/计划下的连续执行条款；必须出现条件或标准，不能把普通预测继承为政策。
        if re.match(r'\s*(?:(?:19|20)\d\d年|第[一二三四五六七八九十\d]+|规模从|对于|按照|该计划|其目标|该政策)',text) and re.search(r'必须|不得|要求|条件|标示|能耗信息|上限|补贴|税率|目标|将.{0,15}(?:份额|占比)|提高到',text):
            candidates=[p for p in self.anchor_pool(record,full) if 0<=a-p['end']<=900 and POLICY_FILE.search(p['text'])]
            if candidates:
                p=candidates[-1];bridge=full[p['end']:a]
                if not re.search(r'专家认为|分析师|另一方面|相比之下|公司计划|企业计划',bridge):
                    competing={m['country'] for m in self.mentions(bridge,p['end']) if m['role'] in {'public_actor','country_candidate'}}
                    if not competing-set(p['countries']):return p,'同一法律/计划的连续执行标准→发布机构'
        return None,reason

    def assess(self,record,full,doc,doc_records):
        # 使用基类既有句间和多国切分，然后只对已验证的效果尾句再切分。
        base=super().assess(record,full,doc,doc_records);out=[]
        for e in base:
            t=e['text'];cuts=[0,len(t)]
            if len(e['countries'])>1 and re.search(r'共同承诺.{0,30}(?:碳中和|净零)|自己的碳中和目标',t) and not re.search(r'共同签署|联合声明|协定规定',t):
                for c in e['countries']:
                    child=copy.deepcopy(e);child.update(event_id=e['event_id']+'-'+hashlib.sha256(c.encode()).hexdigest()[:6],countries=[c],
                        event_type='parallel_policy',shared_evidence_span=True,reason=e['reason']+'；各国相同目标分别记录，未认定单一共同法律')
                    child['roles']['actors']=[m for m in child['roles']['actors'] if m['country']==c]
                    child['roles']['cooperation_countries']=[];out.append(child)
                continue
            if not re.search(r'如果|倘若|除非|不符合|不得|仅限|只有',t):
                for m in SIDE_COMMENT.finditer(t):
                    if REAL_ACTION.search(t[:m.start()]) and not re.search(r'(?:后|之前|期间)[，,]?$',t[:m.end()]):cuts.append(m.end())
            cuts=sorted(set(cuts))
            if len(cuts)==2:out.append(e);continue
            for x,y in zip(cuts,cuts[1:]):
                child=self.assess_unit(record,full,doc,e['start']+x,e['start']+y)
                child['split_from_event_id']=e['event_id'];out.append(child)
        return out

    def assess_unit(self,record,full,doc,a,b):
        t=full[a:b];before=full[max(0,a-2200):a];e=super().assess_unit(record,full,doc,a,b)
        e['algorithm_version']=VERSION;e['refinement_evidence']=[]
        def change(route,reason,state=None):
            e['route']=route;e['reason']='本轮补正：'+reason
            if state:e['policy_state']=state
            e['refinement_evidence'].append(dict(start=a,end=b,text=t,reason=reason))
            return e
        if re.search(r'\d+(?:\.\d+)?万亿(?:千瓦|吉瓦|兆瓦)(?!时)',t):return change('quality_unknown','原文装机容量数量级或单位明显可疑，未自动改写')
        if re.search(r'^\s*球汽车制造商协会|签署了?一系列.{0,20}合作协议',t):return change('quality_unknown','原句开头截断或多份未命名协议尚未拆清，保留证据隔离')
        if re.search(r'(?:没有|并未|未曾|未|否认).{0,2}(?:取消|废除|撤销|退出)',t):return change('background','否定取消或退出，并非已经取消的新措施','no_change_or_denial')
        if e['route'].startswith('main_') and re.search(r'(?:纽约市长|[\u4e00-\u9fff]{2,6}(?:市长|省长|州长)|地方政府|州政府|市政府).{0,45}(?:宣布|表示|说|要求|承诺|必须|计划|提出)',t):
            return change('quality_unknown','国家事实与地方主体新增目标同句混杂，未提升地方目标到国家')
        if e['route'].startswith('main_') and re.search(r'(?:将|计划|最迟|到20\d\d年)[^。；]{0,35}(?:退出|关停|关闭|淘汰).{0,15}(?:煤|电厂|核能|核电)',t) and not re.search(r'已经|已于|已关闭|已经退出',t):
            e['policy_state']='announced_phaseout';e['refinement_evidence'].append(dict(start=a,end=b,text=t,reason='计划未来退出，不标成已经退出'))
        if e['route']=='draft' and e['policy_state']=='draft_or_proposal' and e['countries'] and e['policy_level']=='national' and TOPIC.search(t) and re.search(r'(?:国会|议会|政府|内阁).{0,12}(?:已经|已|正式)?(?:通过|批准).{0,50}草案',t) and not re.search(r'尚未|未能|否决|未获',t):
            return change('main_explicit','草案已经获得通过，保留通过状态，不声称已经生效','announced_or_adopted')
        if re.match(r'\s*(?:此举|这将|从而|这本是|碳减排进程同步)',t):return change('commentary','政策效果、动机或评价尾句')
        if re.search(r'^\s*(?:从.{0,15}态度来看|据分析|讲真|当然|笔者)|是否会|很感兴趣|投资回报|行业发展空间|公布了.{0,12}名单',t):return change('commentary','分析、疑问、排名或态度评论，不是政策措施')
        if re.search(r'为.{0,10}将做更多|政府必须开发|需要承担.{0,10}责任',t) and not HARD_ACTION.search(t):return change('discussion','建议性必要性表达，未声称已经作出公共决定')
        if re.search(r'似乎认识到|似乎宣布|有助于|受到.{0,12}欢迎',t) and not re.search(r'正式(?:发布|公布|通过)|已(?:经)?(?:批准|通过)',t):return change('commentary','不确定叙述、效果或反响，未当成政策事实')
        if re.search(r'一切.{0,8}都得让位|一心赶在|政治正确|作出的庄严承诺|非常讲究|需要承担|付诸行动',t) and not re.search(r'宣布|公布|颁布|批准|通过|签署|规定|20\d\d年.{0,15}(?:实现|达到)',t):return change('commentary','政治评价或重复目标态度，没有独立具体措施')
        if re.search(r'在新政策下|新政策将使|该计划将使|计划将使|计划.{0,8}将为.{0,20}增加.{0,12}工作机会',t) and re.search(r'碳排放.{0,30}(?:减少|降低)|工作机会|就业',t) and not HARD_ACTION.search(t):return change('commentary','政策效果预测，不是设定目标或措施')
        if re.search(r'长期关注|重要人物|曾先后提出或主导|成为.{0,10}领导者',t):return change('background','人物履历和历史概述，未具体交代某项措施')
        if VAGUE.search(t) and not (HARD_ACTION.search(t) and CONCRETE.search(t)):return change('commentary','一般态度或口号，不能替代具体公共措施')
        if FORECAST.search(before[-600:]) and not PUBLIC.search(t) and not HARD_ACTION.search(t) and re.search(r'市场渗透率|需求|产业将超过|投资其.{0,10}产业',t):return change('commentary','研究/市场预测语境，没有独立公共决定')
        state,why=context_state(t,before)
        if state and e['route'] not in {'local_policy','local_execution','quality_unknown','noise','out_of_scope','private_project'}:
            return change('campaign' if state=='campaign' else 'draft',why,state)
        if re.search(r'^\s*\d+[、.．].{0,15}(?:北京|上海|天津|重庆|东京|加州|纽约州)(?:市|都)?\d*月?\d*日?(?:印发|公布|发布|出台)',t):
            e['policy_level']='local';return change('local_policy','编号标题下地方政府独立措施')
        if not e['roles']['actors'] and re.search(r'(?:加州|东京都|北京市|纽约州|苏格兰)(?:还|已|\d+日|\d+月|[、，,]|根据|最新|的|计划){0,10}(?:发布|建立|印发|制定|宣布)',t):
            e['policy_level']='local';return change('local_policy','明确地方施策关系，不提升为国家政策')
        # 基线已经识别公共动作，但工具词表漏掉“许可、核能比例”等。
        if e['route']=='content_uncertain' and TOPIC.search(t) and CONCRETE.search(t):
            rel=self.relation(t,a);actors=[m for x in rel['events'] for m in x['actors']]
            public=[m for m in actors if m.get('public') or POLICY_FILE.search(t) or (m['role']=='country_candidate' and ((HARD_ACTION.search(t) and re.search(r'战略|规划|法律|条例|法案|国家|全国|碳中和|净零',t)) or re.search(r'(?:上调|下调|调整|提高|降低).{0,18}(?:税|补贴标准)',t)))]
            level=self.level(t,rel);cs=sorted({m['country'] for m in actors})
            anchor,ar=self.connect(t,a,b,record,full)
            if not public and anchor and re.search(r'目标|份额|比例|必须|条件|要求|补贴|税率',t):
                cs=anchor['countries'];level='national';public=[m for x in anchor['relation']['events'] for m in x['actors']]
                e['connection_path']=[dict(from_text=t,to_text=anchor['text'],relation=ar),dict(from_text=anchor['text'],to_text='、'.join(cs),relation='发布主体→国家')]
                e['evidence'].append(evidence(full,anchor['start'],anchor['end'],'同一政策执行条件锚点'))
            if public and cs and level=='national' and (REAL_ACTION.search(t) or e['connection_path']):
                e.update(countries=cs,policy_level='national',country_basis='明确施策动作或已保存的政策连接',
                    confidence_level='规则性关系证据',roles=dict(e['roles'],actors=public,actions=[x['action'] for x in rel['events']]))
                return change('main_explicit' if any(c in G20 for c in cs) else 'non_g20','公共主体关系成立，补充具体措施/法定授权工具词')
        if PRIVATE.search(t[:50]) and not PUBLIC.search(t[:70]) and not e['connection_path'] and not any(m.get('public') for m in e['roles']['actors']):
            if re.search(r'公司|企业|集团|开发商',t[:50]):return change('private_project','企业自主计划，无政府工具或政策执行连接')
        if e['route'].startswith('main_'):
            if not CONCRETE.search(t) or (not HARD_ACTION.search(t) and re.search(r'似乎|很感兴趣|乐观|很高兴|需要承担',t)):
                return change('content_uncertain','有国家或人物但具体公共安排仍不成立')
            if re.search(r'后[，,].{0,20}(?:贸易战|影响|市场)',t):return change('quality_unknown','政策事实作为从句与评论混杂，保留原文隔离')
        return e

def grade(e):
    t=e['text'];route=e['route'];main=route.startswith('main_');actors=e.get('roles',{}).get('actors',[])
    public=any(m.get('public') for m in actors);linked=bool(e.get('connection_path'))
    current_public=any(m.get('public') and e['start']<=m.get('start',-1)<e['end'] for m in actors)
    law=bool(POLICY_FILE.search(t) and re.search(r'规定|授权|必须|不得|义务|允许|明确',t))
    dims=dict(content=90 if main and (HARD_ACTION.search(t) or law) and CONCRETE.search(t) else 77 if main else 35,
        country=95 if current_public else 85 if linked and route=='main_explicit' else 72 if main and e.get('countries') else 30,
        level=95 if main and (current_public or NATIONAL_SCOPE.search(t) or law) else 80 if e.get('policy_level')=='national' else 25,
        state=90 if e.get('policy_state') in {'implementation','announced_phaseout','suspended','cancelled_or_withdrawn','conditional_arrangement'} else 85 if main else 45,
        quality=95 if not e.get('previous_quality_risks') else 75)
    reasons=[];caps=[]
    if route=='main_source_inferred':dims['country']=55;caps.append(65);reasons.append('只有国家依来源推定')
    if linked and not current_public:caps.append(79);reasons.append('主体通过上下文连接')
    if main and not current_public and not law:caps.append(74);reasons.append('只有国家称谓/目标，没有当前明确公共机构主体')
    if re.search(r'据悉|消息人士|似乎|据了解|尚未|拟立法|未来可能',t):caps.append(70);reasons.append('报道来源或状态含不确定表达')
    if re.search(r'分析师|专家认为|研究员|学者|撰文|研究主管',t[:80]):caps.append(65);reasons.append('第三方判断而非直接公共主体陈述')
    if len(e.get('countries',[]))>1:caps.append(79);reasons.append('多国关系保留扩展使用，需核验角色')
    if e.get('excluded_local_participants'):caps.append(79);reasons.append('国家与地方共同参与')
    if re.search(r'前总统|前首相|前任政府|其中还包括',t):caps.append(79);reasons.append('历史主体或承接列表，需结合当前施策上下文')
    if re.search(r'(?:做出|作出).{0,3}新.{0,3}承诺|政策美国总统',t):caps.append(74);reasons.append('承诺细节不足或标题正文黏连，仅扩展使用')
    if len(names(t))>1:caps.append(74);reasons.append('多个政策名称并列，尚未逐项拆清')
    if re.search(r'此举|从而|政治遗产|利好|受到了|大大提前|重要意义',t):caps.append(74);reasons.append('事实仍夹有评价性表达')
    score=round(sum(dims[k]*v for k,v in PARAMETERS['score_weights'].items()))
    if caps:score=min(score,*caps)
    if main and min(dims['content'],dims['country'],dims['level'],dims['quality'])<80:score=min(score,79)
    if not main:score=min(score,49)
    tier='A' if main and score>=80 and min(dims['content'],dims['country'],dims['level'],dims['quality'])>=80 else 'B' if main and score>=65 else 'C'
    return dict(evidence_score=score,tier=tier,dimensions=dims,caps=caps,limitations=reasons,
        meaning='证据充分程度的人工设计排序分，非校准正确概率',independent_validation=False)

DATE=re.compile(r'(?:19|20)\d\d年(?:\d{1,2}月)?(?:\d{1,2}日)?|(?:19|20)\d\d[-/]\d{1,2}[-/]\d{1,2}')
