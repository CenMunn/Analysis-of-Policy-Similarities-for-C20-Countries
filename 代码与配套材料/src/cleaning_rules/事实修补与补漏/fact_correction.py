"""V7.4无标签双向语义修补；规则不读sample_id或参考答案。"""

import re

from ..事实修补与补漏.recall_rules import CP,country

VERSION='policy-closeout-20261023.7.4.4'

PARAMETERS={'context_before':850,'context_after':650,'source_country_inference':False,
    'confidence_is_probability':False,'new_recovery_layer':'扩展候选','P_R_goal':'保P提R，按真实错误和独立检验判断'}

TOPIC=re.compile(r'碳|CO2|气候|可再生能源|新能源|节能|清洁能源|绿色能源|燃油|电动汽车|电动车|氢能')

ACTUAL=re.compile(r'已(?:经)?(?:批准|通过|发布|公布|签署|实施|生效)|正式(?:发布|通过|公布|实施)|政府宣布')

class Corrector:
    def decide(self,old,full,doc):
        if old.get('text_parts'):return None
        a,b=old['start'],old['end'];t=full[a:b]
        if t!=old['text']:raise ValueError('原文跨度不一致')
        before=full[max(0,a-850):a];after=full[b:b+650];ctx=before+after
        kept=old['route'].startswith('main_')
        def reject(route,reason):return {'kind':'exclude','route':route,'reason':reason,
            'policy_state':'draft_or_proposal' if route=='draft' else route,
            'context_start':max(0,a-850),'context_end':min(len(full),b+650)}
        if kept:
            def edit(quote,state,reason,remainder='commentary'):
                x=a+t.index(quote);y=x+len(quote)
                return dict(kind='extract' if quote!=t else 'state',route='main_explicit',start=x,end=y,text=quote,
                    countries=old['countries'],policy_state=state,reason=reason,evidence_grade='原文断言及状态核查',remainder_route=remainder,
                    evidence=[dict(start=x,end=y,text=quote,role='保留事实'),dict(start=a,end=b,text=t,role='拆分前原文')])
            if re.search(r'媒体.{0,10}总结',t) and re.search(r'有[二三四五\d]+种(?:方式|路径)|备选路径',t):
                return reject('discussion','媒体分析的备选路径，不是政府已经选择或执行的措施')
            if re.search(r'不一定要.{0,15}保留',t) and re.search(r'很多方法|多种方法',t):
                return reject('commentary','对未来政策选择的评论，未宣布具体措施')
            if re.search(r'撰文指出|分析认为',t) and '仍未明确' in t and re.search(r'虽然|但|两倍',t):
                return reject('commentary','监管缺口与技术效果分析，不作为已采纳要求')
            m=re.search(r'(?:印尼|中国|美国|日本|韩国|德国|英国|法国)政府决定(?:不要|不再)提升减排目标',t)
            if m and re.search(r'评论|失望',t):return edit(m.group(),'no_change_or_denial','保留政府不提高目标的决定，拆除第三方失望评价')
            if re.search(r'取消.{0,50}计划.{0,8}将为.{0,30}(?:增加|创造).{0,15}(?:工作|就业)',t) and not ACTUAL.search(t):
                return reject('commentary','取消政策的预期就业效果，未断言取消已经完成')
            if re.search(r'计划.{0,12}对企业不公平|希望.{0,20}计划.{0,12}成为政治遗产|最引人注目的就是|打着.{0,15}旗号来否定',t):
                return reject('commentary','政策评价、政治动机或关注度描述，没有新的公共措施')
            if re.search(r'根据.{0,15}分析',t) and re.search(r'可能会导致|预估',t):
                return reject('commentary','影响预测，不是实际措施或执行条件')
            if re.search(r'指责|称其',t) and re.search(r'&ldq\s*$',t):
                return reject('quality_unknown','原文评论引语截断，未凭残句补写政策事实')
            if re.search(r'在任.{0,15}期间.{0,20}控告',t) and re.search(r'反对.{0,25}计划',t):
                return reject('background','官员上任前诉讼经历，不作为当前国家公共措施')
            if re.search(r'当.{0,20}计划.{0,8}生效后',t) and re.search(r'影响.{0,10}预估',t):
                return reject('commentary','假设生效后的健康影响估计，不作为已实施证据')
            if re.search(r'计划.{0,12}在法院受阻.{0,10}没能真正生效',t) and old.get('policy_state')!='suspended':
                return edit(t,'suspended','原文明确法院阻止生效，修正为受阻/暂缓状态')
            m=re.search(r'[，,](?:并且在[^，。]{0,25})?(?:每年|能创造每年).{0,15}(?:美元|欧元).{0,10}增长',t)
            if m and re.search(r'政府.{0,20}发布|日本发布',t[:m.start()]):
                return edit(t[:m.start()], 'announced_strategy','保留已发布战略事实，经济增长预测拆入评论')
            if re.search(r'全球.{0,25}\d+个国家.{0,18}(?:提出|制定).{0,8}目标',t):
                return reject('background','统计各国提出目标的数量，没有当前具体国家措施')
            if re.search(r'^【图\d|^\[图\d',t) and re.search(r'意义|旗帜|背景下',t):
                return reject('noise','图注与意义评价混杂，没有可提取的措施断言')
            if re.search(r'(?:相关|推荐|参考).{0,5}文献|搜索以下学术论文文献',before[-300:]) and re.search(r'[;；]\s*$',t):
                return reject('noise','推荐文献条目，不是当前报道正文')
            if re.search(r'在.{1,18}看来',t) and re.search(r'原因|因素|价格',t):
                return reject('commentary','归因分析，不等于政府采取关闭措施')
            if re.search(r'政府需要(?:实施|制定)|政府应(?:当|该)',t) and re.search(r'智库|研究所|专家|分析师|建议',before[-400:]+t) and not re.search(r'法院要求|法院裁定|总理|总统',t):
                return reject('discussion','第三方建议政府行动，缺少已采纳断言')
            if re.search(r'目标是将此立法|目标是将.{0,20}立法',t):
                return reject('draft','当前目标为促成立法，尚非已经生效的法律')
            if re.search(r'没有提到|没有提及',t) and re.search(r'报告|能源署|情景',t):
                return reject('commentary','报告未提及事项与情景评价，未声称新措施')
            if re.search(r'研究.{0,12}(?:显示|结果)|期刊.{0,20}研究',t) and not ACTUAL.search(t):
                m=re.search(r'其在20\d\d年[^。]{0,25}(?:净零|碳中和)[^。]{0,12}的目标',t)
                cs={country(x.group()) for x in CP.finditer(t)}
                if m and len(cs)==1:
                    x,y=a+m.start(),a+m.end()
                    return dict(kind='extract',route='main_explicit',start=x,end=y,text=full[x:y],countries=sorted(cs),
                        policy_state='reported_goal',reason='研究费用是估计，仅保留明确嵌入的国家净零目标',evidence_grade='上下文转述目标',
                        evidence=[dict(start=x,end=y,text=full[x:y],role='保留目标'),dict(start=a,end=b,text=t,role='国家与研究背景')],remainder_route='background')
                return reject('background','研究估计或效果预测，不能当成政府预算或承诺')
            if re.search(r'敞开大门|投资机会|广阔的投资空间',t) and not re.search(r'签署|批准|减免|补贴|税率|合同',t):
                return reject('commentary','欢迎投资的一般立场，没有具体公共工具')
            if re.search(r'^该项目旨在支持|^该项目.{0,12}支持.{0,10}转型',t) and re.search(r'公司|企业|开发商|财团|阿美',before[-450:]) and not re.search(r'政府(?:委托|批准|出资)|公共采购',t):
                return reject('private_project','承接企业项目；支持国家计划不等于公共措施')
            if re.search(r'声称',t) and re.search(r'法律禁止|联邦法律',t) and re.search(r'挑战|诉讼|争议',t):
                return reject('discussion','法律权限主张正被挑战，未证明限制已实际实施')
            if re.search(r'进入白宫以来|执政.{0,12}期间',t) and re.search(r'已经有.{0,20}(?:退役|关闭)',t) and not re.search(r'下令|批准|决定',t):
                return reject('background','任期内退役统计，未证明由该政府措施导致')
            if re.search(r'煤炭出口|煤炭.{0,8}出口',t) and re.search(r'禁止|暂停|禁令',t) and re.search(r'国内市场需求|保障.{0,12}供应|国内供应',ctx) and not re.search(r'减碳|减排|脱碳|转型|可再生能源',t+after[:300]):
                return reject('out_of_scope','国内能源保供措施，未建立减碳或转型联系')
            if re.search(r'核电站|核电',t) and re.search(r'安全标准|安全性',t) and not TOPIC.search(t) and '重要能源支柱' not in t:
                return reject('out_of_scope','核安全安排未明确连接双碳或能源转型')
            if re.search(r'不会为.{0,10}碳排放税统一定价|各国都是务实的',t):
                return reject('discussion','国际谈判立场，不是该国实际税制措施')
            if re.search(r'将设定.{0,15}标准.{0,15}影响很大',t):
                return reject('introduction','前瞻标题与影响评价，没有正式发布断言')
            if re.search(r'标准|指导方针',t) and re.search(r'通知草案|公开征求意见|起草的指导方针',after[:500]) and not re.search(r'已经实施|已实施|正式生效|已生效',t):
                return reject('draft','后文说明同一标准仍处于起草/征求意见环节')
            if re.search(r'要求公用事业|该清洁计划',t) and re.search(r'目标是将此立法|推动国会通过',before[-600:]):
                return reject('draft','同一公用事业立法方案尚待国会通过')
            if re.search(r'^该.{0,10}战略|^根据该战略',t) and re.search(r'政府将于.{0,12}公布.{0,20}战略',before[-500:]):
                return reject('draft','继承同一战略的发布前预告状态')
            if re.search(r'协议|计划|方案',t) and re.search(r'如果获(?:得)?批|尚待.{0,12}批准|尚需.{0,12}批准|仍需要通过.{0,12}批准',before[-400:]+after[:650]) and not ACTUAL.search(t):
                return reject('draft','同一安排尚待审批，金额不等于已拨款')
            if (re.search(r'^\s*[·•]|今年早些时候|上任第一天',t) and
                re.search(r'候任|过渡团队|竞选|百日承诺|计划在入驻白宫\d+天内',before[-800:]+after[:150]) and
                not re.search(r'已宣布|已签署|签署了|发布了|就任后|网站.{0,8}(?:更新|发布)',t)):
                return reject('campaign','竞选或候任承诺，未见当时已经采纳')
            return None
        # Recover only specific assertion structures. Protected quality/local units remain isolated.
        if old['route'] in {'quality_unknown','local_policy','noise','industry_standard','non_g20'}:return None
        if len(t)>1300:return None
        def recover(quote,c,state,reason,anchor=None,grade='原文明确'):
            if t.count(quote)!=1:return None
            start=a+t.index(quote);end=start+len(quote)
            ev=[{'start':start,'end':end,'text':quote,'role':'保留事实'},
                {'start':a,'end':b,'text':t,'role':'原片段上下文'}]
            if anchor:
                x,y=anchor;ev.append({'start':x,'end':y,'text':full[x:y],'role':'政策主体/主题连接'})
            return dict(kind='recover',route='main_explicit',start=start,end=end,text=quote,countries=[c],
                policy_state=state,reason=reason,evidence=ev,evidence_grade=grade)
        m=re.search(r'能源部已经批准[^。；]*?(?:并更新|并修改)[^。；，]*?(?:相关法规|法规|规定)',t)
        if m:
            cs={country(x.group()) for x in CP.finditer(t+before[-180:])}
            if len(cs)==1:return recover(m.group(),next(iter(cs)),'announced_or_adopted','国家能源部已批准参与政策并更新法规；私营参与不等于企业自主项目',(max(0,a-180),b))
        if '《中国制造2025》' in t and re.search(r'重点.{0,15}(?:节能|新能源)',t) and not re.search(r'建议|拟议|如果',t):
            return recover(t,'中国','announced_strategy','具名国家规划的具体节能新能源汽车条款，正文明确为中国规划')
        m=re.search(r'('+CP.pattern+r')对[^。；，,]{1,35}(?:电动车|电动汽车)[^。；，,]{0,12}(?:加收|征收)\s*\d+(?:\.\d+)?\s*[%％][^。；，,]{0,8}关税',t)
        if m and not re.search(r'建议|如果|拟|可能|应该',t):
            return recover(m.group(),country(m[1]),'reported_existing_measure','二手引述既有公共税制；施策国与征税对象分离，税率未外部核实',grade='二手事实转述')
        m=re.search(r'政府到20\d\d年禁止销售[^。；，,]{1,35}的目标',t)
        if m:
            cs={country(x.group()) for x in CP.finditer(t[:m.start()])}
            if len(cs)==1:return recover(m.group(),next(iter(cs)),'announced_goal','只抽已有禁售目标，不纳入同句尚待发布的新充电计划',(a,b))
        if re.search(r'白宫网站.{0,8}(?:更新|发布).{0,25}能源计划',t) and re.search(r'承诺撤销',t):
            return recover(t,'美国','announced_intent','正式网站已更新的能源策略意向，不称监管法规已全部撤销')
        if re.search(r'沙特新闻署(?:报导|报道)称',t) and re.search(r'将建设\d+个新核电站',t) and re.search(r'沙特.{0,80}(?:太阳能|可再生能源)',before[-500:]):
            return recover(t,'沙特阿拉伯','announced_plan','国家新闻署转述未来能源建设安排；预计花费不是已支付',(max(0,a-500),a),grade='国家新闻署转述')
        if re.search(r'^但考虑到.{0,80}将制定.{0,20}援助方案',t) and re.search(r'韩国总统文在寅.{0,100}宣布',before[-600:]) and re.search(r'火力发电站.{0,60}金融援助',before[-300:]):
            return recover(t,'韩国','announced_intent','停止海外煤电融资承诺中的过渡援助方向，具体方案尚未制定',(max(0,a-600),a))
        if re.search(r'^这是日本环境部.{0,20}推行的一项最新举措',t):
            hit=list(re.finditer(r'日本政府[^。]*?发起[^。]*?宣传活动[^。]*。',before))
            if hit:
                q=hit[-1];off=a-len(before)
                return recover(t,'日本','implementation','明确指代前文国家环境部门已开展的减碳宣传活动',(off+q.start(),off+q.end()))
        if re.search(r'^日本目前正面临.{0,25}二氧化碳排放量.{0,40}减少\d+[%％]的挑战',t) and '日本环境部' in before and '气候' in before:
            return recover(t,'日本','reported_goal','报道转述国家减排目标，保留相对时间与基期，不推算日期',(max(0,a-650),a),grade='上下文转述目标')
        if re.search(r'^碳中和\+?[:：].{0,40}CO2.{0,25}甲烷燃料',t):
            head=full[:min(a,2200)]
            m=re.search(r'韩国[^。]{0,180}(?:2021.{0,10}2025|第4次|第四次)[^。]{0,120}(?:新能源汽车|环保汽车)[^。]{0,50}(?:计划|规划)',head)
            if m:return recover(t,'韩国','announced_strategy','具名国家汽车计划的碳循环技术路线，不称已商业化',(m.start(),m.end()))
            m=re.search(r'根据韩国《新能源汽车法》规定[^。]*。',head)
            if m and '产业部每五年制订开发和普及基本计划' in head:
                return recover(t,'韩国','announced_strategy','国家汽车法与产业部周期基本计划下的碳循环路线；不称已商业化',(m.start(),head.index('环境部每年')+len('环境部每年制订普及实施计划。')))
        return None
