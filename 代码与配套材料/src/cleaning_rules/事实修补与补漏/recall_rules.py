"""Conservative add-only recall layer. No labels, source-folder promotion or probability claims."""

import copy

import hashlib

import re

from ..事实修补与补漏.content_repair import TOPIC, quality_flags, state_signal, BAD_STATES

from ..主体与国家归属.national_scope import evidence, LOCAL_WORDS

VERSION='policy-recall-20261023.7.3.4'

PARAMETERS={'anchor_window_chars':650,'state_after_chars':160,'precision_reference_development':0.9219904258267266,
            'precision_is_hard_floor':False,'tradeoff':'按真实误收与补回价值权衡；非政策不得靠分数通过',
            'country_weights_unchanged':[0.60,0.15,0.20,0.05], 'additions_layer':'扩展候选',
            'source_folder_inference':False,'confidence_is_probability':False}

COUNTRIES='印度尼西亚|沙特阿拉伯|澳大利亚|阿根廷|墨西哥|俄罗斯|加拿大|意大利|土耳其|中国|美国|英国|法国|德国|日本|韩国|印度|巴西|南非|印尼|沙特|欧盟'

CP=re.compile(COUNTRIES)

CANON={'印尼':'印度尼西亚','沙特':'沙特阿拉伯'}

FORMAL=re.compile(r'宣布|公布|发布|批准|制定|制订|签署|设定|决定|承诺|选定支持|启动|发起|推行|提出|提供|投资|投入|支持|要求|规定|征收|加收|停止|已针对.{0,30}制定')

MEASURE=re.compile(r'目标|政策|法案|法律|法规|条例|规划|计划|方案|战略|愿景|补贴|补助|贷款担保|税|拨款|投资|装机容量|标准|资助|选定支持|资格审核|购买价格|宣传活动|排放.{0,35}(?:下降|减少|降低)|20\d\d年.{0,25}(?:安装|达到|减少)|退出|停止')

CONT=re.compile(r'^(?:[“\s，,]*)(?:该(?:项目|计划|方案|政策|部|法|措施)|这(?:项|一)|其中|根据|按照|目标是)|此举|FIT|上网电价')

DETAIL=re.compile(r'包括.{0,35}(?:贷款|补贴|拨款)|购买价格.{0,30}(?:提高|调整)|选定支持|20\d\d年.{0,35}(?:实现|达到|安装|降低|减少|投资)|要求.{0,30}(?:补贴|排放|能效)|规定.{0,45}(?:补贴|排放|能效|固定价格)|目标是建设.{0,12}(?:电厂|加氢站|充电站)')

GUARD=re.compile(r'建议|提议|应当|应该|需要|有必要|如果|假如|倘若|尚未|尚待|未能|没有达成|待批准|待确认|晚些时候予以确认|正在考虑|拟定|拟议|草案|征求意见|竞选|候选人|若当选|可能|有望|预计|认为|嘲讽|研究显示|研究表明|发布研究|发布报告|评论|加剧.{0,10}竞争|引发.{0,10}争议|质疑|挑战|估算|支持者|石化奖|各行业之首')

PRIVATE=re.compile(r'公司|企业|集团|银行|研究人员|分析师|智库|专家|学者|研究所|协会')

POLICY_NAMES=re.compile(r'《([^《》]{2,70})》')

PROTECTED={'quality_unknown','local_policy','noise','introduction','international_framework','campaign'}

def country(name):return CANON.get(name,name)

def sentence_spans(text):
    return [(m.start(),m.end(),m.group()) for m in re.finditer(r'[^。！？\n]+[。！？\n]?',text)]

def fact_span(text):
    start=0;end=len(text)
    m=re.match(r'\s*(?:\|{2,}|据了解[，,]|据悉[，,])\s*',text)
    if m:start=m.end()
    tail=re.search(r'[，,](?:这个[^。；]{0,12}目标有望|敦促家庭|分析师认为|分析人士认为|这将带动|有望带动|预计将创造)',text[start:])
    if tail:end=start+tail.start()
    return start,end

class RecallEngine:
    def __init__(self,scope):
        self.scope=scope
        self.authorities=dict(scope.authorities)
        self.authorities.update({'中国国家主席':'中国','胡锦涛':'中国','日本环境部':'日本',
                                '联邦经济部':'德国','沙特能源大臣':'沙特阿拉伯',
                                '沙特能源部':'沙特阿拉伯','REPDO':'沙特阿拉伯',
                                '可再生能源项目发展办公室':'沙特阿拉伯'})
        self.ap=re.compile('|'.join(map(re.escape,sorted(self.authorities,key=len,reverse=True))))

    def actors(self,text,offset=0):
        # Extract independently: a country mention must not mask a longer agency/leader mention.
        found=[]
        patterns=[(self.ap,lambda m:self.authorities[m.group()]),
                  (re.compile('('+COUNTRIES+r')(?:联邦)?(?:政府|总统|首相|总理|能源部|能源大臣|环境部|国家主席|国会|内阁)'),lambda m:country(m[1]))]
        for pat,owner in patterns:
            for m in pat.finditer(text):
                head=text[:m.start()];tail=text[m.end():]
                if re.search(r'对|针对|向|效仿|要求',head[-4:]):continue
                if head.rfind('《')>head.rfind('》'):continue
                if re.match(r'(?:的)?(?:公司|企业|顾问|研究|智库|专家|竞选团队)',tail):continue
                if LOCAL_WORDS.search(text[max(0,m.start()-5):m.end()+12]):continue
                action=FORMAL.search(tail[:110])
                if not action and not re.search(r'此举包括|目标是|具体负责|负责',tail[:80]):continue
                if action and re.search(r'公司|企业|专家|学者|银行|报告|希望|需要|呼吁|建议',tail[:action.start()]):continue
                found.append(dict(text=m.group(),country=owner(m),start=offset+m.start(),end=offset+m.end(),public=True,level='national',role='public_actor'))
        # Country as grammatical policy actor, not an arbitrary occurrence elsewhere in a paragraph.
        for m in CP.finditer(text):
            if any(x['start']<=offset+m.start()<x['end'] for x in found):continue
            head=text[:m.start()];tail=text[m.end():]
            if head.rfind('《')>head.rfind('》') or re.search(r'对|针对|向|来自|要求|希望',head[-4:]):continue
            match=re.match(r'(?:目前|已|已经|仍|仍然|正|正在|周[一二三四五六日天]|于20\d\d年|在20\d\d年|今年|去年|此前|则|还|也|当地时间[0-9]+日|[，,]){0,5}(宣布|公布|发布|承诺|制定|制订|设定|决定|已针对)',tail)
            if not match:
                match=re.match(r'开展[^。；]{0,45}[，,]已针对[^。；]{0,30}制定',tail)
            if not match:continue
            found.append(dict(text=m.group(),country=country(m.group()),start=offset+m.start(),end=offset+m.end(),public=True,level='national',role='country_policy_actor'))
        return sorted({(x['start'],x['end'],x['country']):x for x in found}.values(),key=lambda x:x['start'])

    def blocked(self,t):
        if GUARD.search(t) or LOCAL_WORDS.search(t) or quality_flags(t):return True
        if re.search(r'该州|该市|该省|本州|本市|本省',t):return True
        if re.search(r'市政府|省政府|州政府|市长|州长|首尔市|加利福尼亚州',t):return True
        if re.search(r'将(?:于[^，。；]{0,15})?(?:正式)?(?:公布|发布|签署|宣布)|拟(?:取消|废除|制定)',t):return True
        if re.search(r'计划前往|参观|访问|新闻发布会|演讲要点|参考文献|来源[：:]|相关阅读',t):return True
        if re.search(r'(?:公司|企业|集团|银行).{0,20}(?:计划|宣布|投资|决定|推出|建设|表示|认为)',t):return True
        if re.search(r'该公司|该企业|民间目标|类型政府目标|的支持者|的退出决定|发表.{0,8}评论|并没有|实际上确保|受到.{0,15}关注|未提可再生能源|未能成长',t):return True
        if re.search(r'(?:公布|发布|提出)的.{0,45}(?:显示|报道)|计划.{0,20}提交|将在.{0,15}公布|将制定路线图',t):return True
        if re.search(r'正在制定|正考虑|正准备|准备宣布|计划宣布|若通过|若想|似乎|必须|倡导|计划制定|将制定|的目标一再落空|并未|透露.{0,12}拟|今后.*制定',t):return True
        if re.search(r'新加坡|越南|泰国|马来西亚|新西兰|挪威|瑞典|瑞士|丹麦|全球领导人|全球升温|国际社会.*目标|巴黎峰会上达成|TMG|工党表示',t):return True
        if re.search(r'失望|意味着|动作片|辩护|至关重要|政治动机|面临.{0,8}压力|奠定.{0,20}基础|成本.{0,8}扼杀|得到.{0,10}支持|得到了.{0,10}支持|感谢|理由分析|软实力|鼓励多边主义|有助于|将会鼓励|希望|创造.{0,12}(?:岗位|就业)|引发.{0,12}讨论|媒体分析|称赞|首席|反驳|批评|无从知晓|压力将得到|是否能|影子|未提及|未提可再生|只字未提',t):return True
        if re.search(r'公司|企业|集团|阿美|投资者|民间|私人|党派|股价|药物|抗癌|生物医药|金融市场',t) and not re.search(r'规定.{0,15}(?:公司|企业)|根据协议.{0,15}企业投入',t):return True
        return False

    def anchors(self,t,a,full):
        prior=full[max(0,a-PARAMETERS['anchor_window_chars']):a];base=a-len(prior)
        candidates=[]
        for x,y,s in sentence_spans(prior):
            # Remove only a metadata-bearing lead up to a literal report boundary.
            # The retained context is still an exact source substring, including its modal verbs.
            if re.search(r'来源[：:]|联系电话|【[^】]*报道',s):
                boundaries=list(re.finditer(r'(?:报道|报道称)[，,]',s))
                if boundaries:
                    cut=boundaries[-1].end();x+=cut;s=s[cut:]
            if self.blocked(s):continue
            acts=self.actors(s,base+x);cs={v['country'] for v in acts}
            if len(cs)==1 and TOPIC.search(s) and MEASURE.search(s) and state_signal(s) not in BAD_STATES:
                candidates.append((base+x,base+y,s,acts))
            # Named acronym plus an explicit government-policy assertion; not folder inference.
            elif 'FIT' in t and 'FIT' in s and re.search(r'政府政策.{0,10}FIT',s):
                names={country(v.group()) for v in CP.finditer(s)}
                if len(names)==1:
                    hit=next(CP.finditer(s));acts=[dict(text=hit.group(),country=next(iter(names)),start=base+x+hit.start(),end=base+x+hit.end(),public=True,level='national',role='named_policy_country')]
                    candidates.append((base+x,base+y,s,acts))
        if not candidates:return None
        current_names=set(POLICY_NAMES.findall(t))
        if current_names:
            matched=[c for c in candidates if current_names & set(POLICY_NAMES.findall(c[2]))]
            if matched:candidates=matched
            elif any(POLICY_NAMES.findall(c[2]) for c in candidates):return None
        if len({v['country'] for c in candidates for v in c[3]})!=1:return None
        # Different named policies block an ambiguous pronoun; a repeated exact name can select its anchor.
        names={n for c in candidates for n in POLICY_NAMES.findall(c[2])}
        if len(names)>1 and not any(n in t for n in names):return None
        anchor=candidates[-1]
        intervening=full[anchor[1]:a]
        if re.search(r'另一方面|相比之下|转而|另一项|另一国|新计划|此外.{0,20}(?:公司|企业)',intervening):return None
        if GUARD.search(intervening) and re.search(r'草案|尚待|待确认|予以确认|竞选|尚未批准',intervening):return None
        if re.search(r'征求.{0,12}意见.{0,20}(?:敲定|确定)|方案.{0,20}(?:最终敲定|待选择)',intervening):return None
        otheractors=self.actors(intervening,anchor[1])
        if any(x['country']!=anchor[3][0]['country'] for x in otheractors):return None
        return anchor

    def purpose_anchor(self,t,end,full,cs):
        """Same restricted commodity + explicit official speech + energy purpose, in following text."""
        m=re.search(r'(?:停止|禁止)(?:了)?([^，。；]{1,10}?)出口',t)
        if not m or len(cs)!=1:return None
        def object_key(x):return re.sub(r'矿石|产品|矿','',x)
        key=object_key(m[1])
        if not key or key in {'原材料','商品','产品'}:return None
        spans=sentence_spans(full[end:end+650])
        for i,(a,b,s) in enumerate(spans):
            q=re.search(r'(?:禁止|停止)([^，。；]{1,10}?)出口.{0,8}(?:以|为了|来)吸引.{0,20}(?:电动汽车|新能源|可再生能源|电池制造)',s)
            if not q or object_key(q[1])!=key or self.blocked(s):continue
            speaker=self.actors(s,end+a);speaker_span=(end+a,end+b,s)
            if not speaker and re.match(r'他(?:举例)?(?:说|表示)',s) and i:
                aa,bb,ss=spans[i-1]
                if self.blocked(ss):continue
                speaker=self.actors(ss,end+aa);speaker_span=(end+aa,end+bb,ss)
            if {x['country'] for x in speaker}==cs:
                return (end+a,end+b,s,speaker,speaker_span)
        return None

    def recover(self,old,full,doc):
        if old.get('route','').startswith('main_') or old.get('route') in PROTECTED:return None
        if old.get('review_no') is not None or old.get('text_parts') or old.get('human_confirmation'):return None
        a,b=old['start'],old['end'];original=full[a:b]
        assert original==old['text']
        x,y=fact_span(original);t=original[x:y];start=a+x;end=a+y
        if len(t)<10 or len(t)>600 or self.blocked(t):return None
        if re.search(r'图[片表]|\.com|http|版权所有',t):return None
        current_state=state_signal(t)
        if current_state in BAD_STATES:return None
        if not MEASURE.search(t):return None
        acts=self.actors(t,start);cs={v['country'] for v in acts};anchor=None
        family='explicit_actor_measure';purpose=None
        topical=bool(TOPIC.search(t))
        if not topical and len(cs)==1:
            purpose=self.purpose_anchor(t,end,full,cs)
            if purpose:topical=True;family='same_measure_official_purpose'
        # A concrete future national target may omit its agency after a matched government plan.
        needs_link=bool(CONT.search(t) or re.search(r'('+COUNTRIES+r')目前计划到20\d\d',t))
        if needs_link and (not acts or not topical or re.search(r'此举|该项目|其中|FIT',t)):
            anchor=self.anchors(t,start,full)
            if anchor:
                ac={v['country'] for v in anchor[3]}
                # Explicit countries in the continuation cannot contradict the policy owner.
                mentioned={country(m.group()) for m in CP.finditer(t)}
                if (cs and cs!=ac) or (mentioned and not mentioned<=ac):return None
                acts=acts or anchor[3];cs=ac;topical=topical or bool(TOPIC.search(anchor[2]))
                family='same_policy_context'
        if len(cs)!=1 or not topical:return None
        if not FORMAL.search(t) and not (anchor and DETAIL.search(t)):return None
        if anchor and not DETAIL.search(t):return None
        if anchor and not TOPIC.search(t) and not re.search(r'FIT|贷款担保|拨款|^其中.{0,10}20\d\d',t):return None
        # Concrete content must remain after the actor/action; vague praise or an unspecified goal is insufficient.
        if not re.search(r'\d|[０-９]|禁止|规定|征收|加收|补贴|贷款|资助|发起.{0,20}宣传活动|停止.{0,25}(?:资金|支持|出口)|已针对.{0,30}制定.{0,12}规划|《[^》]+》|发布.{0,20}(?:愿景|战略)',t):return None
        if family=='explicit_actor_measure' and PRIVATE.search(t[:min(v['start'] for v in acts)-start]):return None
        if re.search(r'研究|报告|数据|统计|占全球|同比|去年.*增长',t) and not re.search(r'已(?:批准|制定)|贷款担保|制定.{0,15}规划',t):return None
        after=full[end:end+PARAMETERS['state_after_chars']]
        # Pending confirmation attached to this policy is a status veto, not evidence of adoption.
        if re.search(r'(?:该|这一|上述)(?:计划|方案|政策).{0,30}(?:尚待|仍需|待批准)|委员会将在晚些时候予以确认',after):return None
        before=full[max(0,start-300):start]
        if re.search(r'竞选|候选人|竞选宣言|一旦当选',before) and not re.search(r'(?:政府|内阁|国会).{0,15}(?:已经|已|正式)?(?:批准|通过|宣布|发布|制定)',t):return None
        if current_state in {'suspended','cancelled_or_withdrawn'}:pass
        elif 'FIT' in t and anchor:current_state='execution_requirement'
        elif re.search(r'排放.{0,40}(?:下降|减少)|目标是|计划到20\d\d',t):current_state='announced_goal'
        elif '贷款担保' in t:current_state='announced_funding_plan'
        elif re.search(r'(?:发布|制定|制订).{0,25}(?:愿景|战略)',t):current_state='announced_strategy'
        if purpose and re.search(r'停止了|已停止|已禁止',t):current_state='implementation'
        e=copy.deepcopy(old)
        e.update(event_id='R73-'+hashlib.sha256(f"{old['event_id']}:{start}:{end}".encode()).hexdigest()[:20],
                 start=start,end=end,text=t,route='main_explicit',countries=sorted(cs),policy_level='national',
                 policy_state=current_state,delivery_layer='扩展候选',newly_recovered=True,
                 algorithm_version=VERSION,recovery_family=family,previous_event_ids=[old['event_id']],
                 previous_routes=[old['route']],reason='V7.3明确措施补漏：'+('同政策锚点补主体/主题' if anchor else '当前原文公共施策关系'),
                 country_basis='同政策上下文关系' if anchor else '原文明确施策主体',
                 human_confirmation='',reviewer='',review_provenance='规则新增候选；未独立人工确认',
                 roles={'actors':acts,'actions':[],'measures':[],'targets':[]},
                 evidence=[evidence(full,start,end,'补回的逐字政策事实')],connection_path=[],
                 content_evidence_level='明确措施候选',country_evidence_level='上下文明确连接' if anchor else '当前句关系',
                 level_evidence_level='国家层级机构或国家施策',state_evidence_level='忠实原文状态，未核对外部有效性',
                 confidence_is_calibrated_probability=False)
        if anchor:
            aa,ab,s,am=anchor;e['evidence'].append(evidence(full,aa,ab,'同政策公共主体/主题锚点'))
            e['connection_path']=[{'from_text':t,'to_text':s,'relation':'当前措施/执行信息→同政策锚点'},
                                  {'from_text':s,'to_text':'；'.join(sorted(cs)),'relation':'原文公共主体→国家'}]
        if purpose:
            aa,ab,s,am,sp=purpose
            e['evidence'].append(evidence(full,aa,ab,'同一出口措施的能源转型目的'))
            if sp[0]!=aa:e['evidence'].append(evidence(full,sp[0],sp[1],'目的陈述的明确官方说话者'))
            e['connection_path']=[{'from_text':t,'to_text':s,'relation':'同一受限商品和出口措施→后文目的'},
                                  {'from_text':s,'to_text':sp[2],'relation':'目的陈述→官方说话者'},
                                  {'from_text':sp[2],'to_text':'；'.join(sorted(cs)),'relation':'说话者与施策主体同国'}]
            e['reason']='V7.3同一措施补主题：后文有明确官方说话者的能源转型目的；不采用作者推测'
        e['policy_names']=POLICY_NAMES.findall(t)+(POLICY_NAMES.findall(anchor[2]) if anchor else [])
        return e
