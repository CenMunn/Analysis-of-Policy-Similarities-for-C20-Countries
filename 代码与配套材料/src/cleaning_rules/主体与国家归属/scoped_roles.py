"""只输出事件角色、指代和得分；有意不实现assess/assess_unit内容筛选接口。"""
import copy,re
from ..主体与国家归属.optimized_attribution import OptimizedScope,score_candidates,DEFAULTS,eligible,policy_topic
from ..主体与国家归属.national_scope import G20,LOCAL_WORDS,CONTEXT_SWITCH,INSTRUMENT,policy_state
from ..主体与国家归属.role_resolution import names
from ..事实修补与补漏.recall_rules import COUNTRIES,country

VERSION='scoped-roles-20261026.6.8-joint-participants'
VERBS=r'允许|授权|限制|要求|禁止|宣布|公布|发布|出台|颁布|编制|承诺|重申|决定|制定|制订|推出|敲定|设定|设立|提供|给予|征收|采购|拨款|投入|推行|启动|实施|签署|签订|退出|支持|投资|扩大|提高|减少|降低|改造|计划|包括|规定'
ADVERBS=r'(?:政府|实际上|实际|一直|已经|仍然|继续|目前|此前|最近|近日|日前|尚未|并未|没有|从未|未|还|也|已|曾|将|会|则|正式|公开|明确|正在|的|于次年|次年|同年|于[\d年月日]+|在[\d年月日]+|[\s\d０-９年月日]){0,15}'
TARGET_BEFORE=re.compile(r'(?:向|对|针对|要求|请求|呼吁|敦促|建议|促请|限制|禁止|阻止|制止|迫使|希望)\s*$')
CORPORATE_AFTER=re.compile(r'(?:的)?(?:[\u4e00-\u9fff]{0,7})?(?:公司|企业|集团|厂商|巨头|制造商|行业协会|产业协会)')
LOCATION_NAME=r'(?:'+COUNTRIES+r'|欧洲|亚洲|非洲|北美|南美|东南亚|中东)'
LOCATION_PREFIX=re.compile(r'(?:在|(?<![由对关属基至源])于|面向)(?:'+LOCATION_NAME+r'(?:的)?(?:市场|境内|国内)?\s*(?:以及|和|与|及|、)\s*)*$')
REF=re.compile(r'该(?:国(?:政府)?|政府|部门|部|计划|政策|方案|战略|法律|目标)|这项(?:法律|政策|计划)|上述(?:措施|政策)|^我们|^他|^她')
BLOCKED_STATES={'campaign','not_adopted','draft_or_proposal','proposed_change','discussion'}

def public_actor_prefix(text):
    return not TARGET_BEFORE.search(text)

class ScopedAttribution:
    def __init__(self,raw_mentions,params=None):
        self.entities=OptimizedScope(raw_mentions,params)
        self.params=dict(DEFAULTS,**(params or {}));self.authorities=self.entities.authorities
        self._decision_cache={};self._anchor_cache={}

    def clear_document_cache(self):self._decision_cache.clear();self._anchor_cache.clear()

    def named_policy_owner(self,text,offset=0):
        """当前政府推出的具名国家战略；不得把引用外国题名或地方政府当发布者。"""
        m=re.search(r'(?:联邦政府|中央政府|政府)(?:在|于)?(?:正式)?(?:推出|发布|公布|颁布)的[《“]('+COUNTRIES+r')[^》”]{1,45}(?:战略|规划|计划|法案|路线图)[》”]中',text)
        if not m:return None
        c=country(m[1]);start=m.start();prefix=text[max(0,start-10):start]
        if re.search(r'尚未|未曾|如果|若|拟|将|计划|地方|市|州|省',prefix):return None
        current=[x for x in self.mentions(text,offset) if eligible(x) and (x['end']<=offset+start or x['start']>=offset+m.end())]
        if any(x['country']!=c for x in current):return None
        if any(x.get('level')=='local' and x['start']<=offset+start<x['end'] for x in self.mentions(text,offset)):return None
        actor_text=re.match(r'联邦政府|中央政府|政府',m.group()).group()
        actor=dict(country=c,text=actor_text,start=offset+start,end=offset+start+len(actor_text),public=True,role='public_actor',level='national',basis='当前政府推出的具名国家政策题名')
        return dict(start=offset+m.start(),end=offset+m.end(),text=m.group(),countries=[c],actors=[actor],kind='current_named_policy_owner')

    def institution_continuation(self,text,a,full):
        """最近同段唯一国家机构的能源发言→当前通称政府的具体条款。"""
        if not re.search(r'(?:政府|该政府)(?:制定|根据.{1,20}|将|还|已|在)',text):return None
        if not policy_topic(text) or not re.search(r'20\d\d|补贴|投资|税率|配额|必须|不得',text):return None
        prior=full[max(0,a-350):a].split('\n\n')[-1];off=a-len(prior)
        if CONTEXT_SWITCH.search(prior) or LOCAL_WORDS.search(prior):return None
        ms=self.mentions(prior,off);cs={x['country'] for x in ms if eligible(x)}
        pub=[x for x in ms if eligible(x) and x.get('public') and x.get('level')!='local']
        if len(cs)!=1 or not pub:return None
        if {x['country'] for x in self.mentions(text,a) if eligible(x)}-cs:return None
        actor=pub[-1];tail=full[actor['end']:a]
        if not re.match(r'(?:[（(][^）)]{0,15}[）)]|[）)])?(?:\s|，|,|\d|日){0,8}(?:表示|宣布|公布|发布|制定)',tail):return None
        if not policy_topic(tail) or re.search(r'如果|若当选|草案|尚未|竞选|建议|否认|未能',tail):return None
        topics=lambda t:{k for k,p in {'氢':r'氢能|氢气|制氢','核':r'核电|核能','汽车':r'汽车|车辆','可再生':r'可再生|风能|风电|太阳能|光伏','节能':r'节能|能效','煤':r'煤炭|煤电'}.items() if re.search(p,t)}
        x,y=topics(text),topics(tail)
        if x and y and not x&y:return None
        return dict(start=actor['start'],end=a,text=full[actor['start']:a],countries=sorted(cs),actors=[actor],kind='adjacent_institution')

    def document_policy_speaker(self,text,a,full):
        """只有明确标为全文概述的单主体政策介绍，才跨小标题连接原发布者。"""
        intro=full[:min(a,450)]
        if not re.search(r'全文概述如下|全文介绍如下|计划全文如下',intro):return None
        if not re.search(r'(?:演讲|讲话)[^。]{0,18}(?:介绍|公布|发布)[^。]{0,30}(?:计划|战略|规划)',intro):return None
        if not re.search(r'政府[^。；]{0,25}(?:根据|依据|按照)[^。；]{0,18}(?:法案|法律|计划)',text):return None
        if not policy_topic(text) or re.search(r'建议|呼吁|如果|若|草案|拟议|希望',text):return None
        pub=[x for x in self.mentions(intro,0) if eligible(x) and x.get('public') and x.get('level')!='local']
        cs={x['country'] for x in pub}
        if len(cs)!=1:return None
        if {x['country'] for x in self.mentions(full[:a]+text,0) if eligible(x)}-cs:return None
        if re.search(r'以下为评论|记者评论|专家评论|观点如下|竞选|候任',full[:a]):return None
        end=intro.find('。')+1
        if end<=0:return None
        return dict(start=0,end=end,text=full[:end],countries=sorted(cs),actors=pub,kind='document_policy_speaker')

    def density_context(self,text,a,b,full,anchor,countries):
        """D的同政策窗口：验证锚点到当前事实，向前只扩展相同具名政策；不直接使用全文密度。"""
        if self.params.get('density_scope')!='linked_policy' or not anchor or not countries:return None
        limit=self.params.get('policy_density_chars',800)
        start=anchor['start'];policy_names=names(anchor['text'])|names(text)
        if b-start>limit:return None
        owners=set(countries)
        window=full[start:b]
        for sm in re.finditer(r'[^。！？；;\n]+[。！？；;\n]*',window):
            t=sm.group();pn=names(t)
            if pn and policy_names and not pn&policy_names:return None
            if re.search(r'相比之下|另一方面|地方政府|州政府|市政府|专家认为|分析师|预计|有望|竞选|草案',t):return None
            ms=self.mentions(t,start+sm.start())
            if any(m.get('level')=='local' for m in ms):return None
            if {m['country'] for m in ms if eligible(m)}-owners:return None
        # 原锚点之前的内容仅允许同名政策连续出现，不跨主题或段落拼接。
        if policy_names:
            earlier=full[max(0,b-limit):start];off=start-len(earlier)
            for sm in reversed(list(re.finditer(r'[^。！？；;\n]+[。！？；;\n]*',earlier))):
                t=sm.group()
                if not names(t)&policy_names or '\n\n' in t or re.search(r'预计|认为|草案|竞选|地方政府',t):break
                ms=self.mentions(t,off+sm.start())
                if any(m.get('level')=='local' for m in ms) or {m['country'] for m in ms if eligible(m)}-owners:break
                start=off+sm.start()
        return dict(start=start,end=b,text=full[start:b],countries=sorted(owners),mentions=self.mentions(full[start:b],start),
                    policy_names=sorted(policy_names),basis='已验证政策锚点→同一政策条款；同名政策可向前延展；冲突主体/地方/状态/主题阻断')

    def mentions(self,text,offset=0):
        values=self.entities.mentions(text,offset)
        pat=re.compile('('+COUNTRIES+r')(?:矿业和能源部|工业贸易能源部|产业部|贸易工业能源部|贸易、工业和能源部|能源和工业部)')
        for m in pat.finditer(text):
            values=[x for x in values if not(offset+m.start()<=x['start'] and x['end']<=offset+m.end())]
            values.append(dict(country=country(m[1]),text=m.group(),start=offset+m.start(),end=offset+m.end(),public=True,role='public_actor',level='national'))
        for m in values:
            a,b=m['start']-offset,m['end']-offset;prefix=text[max(0,a-14):a];tail=text[b:]
            sentence_start=max([0]+[x.end() for x in re.finditer(r'[。！？；;\n]',text[:a])])
            actor_prefix=text[sentence_start:a]
            company_subject=bool(re.search(r'公司|企业|集团|厂商|制造商|科技巨头|Pty\s+Ltd|\bInc\b|\bCorp\b',actor_prefix,re.I))
            public_subject=any(x.get('public') and x.get('role')!='target' and offset+sentence_start<=x['start']<x['end']<=offset+a
                and re.match(ADVERBS+'('+VERBS+')',text[x['end']-offset:a]) for x in values)
            # 仅在同句已有企业或明确公共主体动作时移除地点候选。不能靠移除国名，
            # 使“该计划＋项目地点/会议地点”绕过原有的跨句证据不足隔离。
            if not m.get('public') and (company_subject or public_subject) and LOCATION_PREFIX.search(text[max(sentence_start,a-100):a]):
                m.update(role='location',role_basis='在/于/面向引出的地点或市场列举，不是推出动作的施策者')
            elif TARGET_BEFORE.search(prefix):m['role']='target'
            elif not m.get('public') and CORPORATE_AFTER.match(tail):m.update(role='private_or_context',public=False)
        return sorted({(m['start'],m['end'],m['country']):m for m in values}.values(),key=lambda m:(m['start'],-m['end']))

    def relation(self,text,offset=0):
        ms=self.mentions(text,offset);events=[];reported=[];cooperation=[];joint=False
        for m in ms:
            if not eligible(m):continue
            local=m['end']-offset;tail=text[local:]
            nominal=re.match(r'(?:的|提出的|公布的)[^，。；;]{0,15}(?:计划|方案|战略|规划)(?:明确)?(包括|规定|要求)',tail)
            direct=re.match(ADVERBS+'('+VERBS+')',tail)
            if not direct and m.get('public'):
                direct=re.match(r'(?:周|星期)[一二三四五六日天](?:正式|公开)?('+VERBS+')',tail)
            continued=re.match(r'做出了?回应[，,](?:并)?(要求|规定|决定)',tail)
            if continued:direct=continued
            if not direct and m.get('public'):
                direct=re.match(r'(?:再度|再次)?联合(?:其它|其他|有关|相关)?部门(出台|发布|制定)',tail)
            if not direct and m.get('public') and re.match(r'(?:公开|正式)?(?:表示|宣布)[，,]?(?:到|将|计划|(?:中国|韩国|日本|美国|德国|法国|英国))',tail):
                quant=re.search(r'降低|提高|减少|增加|达到|实现',tail[:75])
                if quant and re.search(r'20\d\d|[%％]',tail[:90]):
                    intro=re.match(r'(?:公开|正式)?(?:表示|宣布)[，,]?',tail)
                    declared=[x for x in ms if eligible(x) and m['end']+intro.end()<=x['start']<m['end']+quant.start()]
                    foreign=[x for x in declared if x['country']!=m['country']]
                    ev=dict(actors=[m],action=dict(start=m['end']+quant.start(),end=m['end']+quant.end(),text=quant.group()),method='公共机构陈述自己的量化政策目标',scope_start=m['start'],scope_end=offset+len(text))
                    if foreign:reported.append(dict(ev,actors=foreign,method='转述外国量化目标，未证明发言者自身措施或外方已经承诺'))
                    else:events.append(ev)
            # 日期/短介词状语只在明确公共机构后接受，不跨逗号寻找任意后续谓词。
            if not direct and m.get('public'):
                direct=re.match(r'(?:\d{1,2}日)?(?:在[^，。；;]{0,24}(?:期间|时|后)?|于[^，。；;]{0,14}|[\s，,])(?:正式|公开|明确)?('+VERBS+')',tail)
            if not direct and m.get('public') and re.fullmatch(r'\s*(?:根据|依据|按照)[\d０-９年月日\s]*',text[:m['start']-offset]):
                law_ref=re.match(r'(通过|批准|颁布|制定)的[^，。；;]{1,70}(?:法案|法律|条例)',tail)
                if law_ref and re.search(r'必须|不得|税率|价格|定价|配额|补贴|截止|义务|\d.*(?:欧元|美元|[%％])',tail[law_ref.end():]):direct=law_ref
            hit=nominal or direct
            if not hit:continue
            if not m.get('public') and hit[1] not in {'宣布','公布','发布','承诺','重申','制定','制订','决定','设定','签署','签订','推出'}:continue
            if hit[1] in {'签署','签订'} and re.search(r'(?:与|同|和)\s*$',text[max(0,m['start']-offset-3):m['start']-offset]):continue
            pos=local+hit.start(1);verb=hit[1]
            if verb in {'公布','发布'} and re.match(r'(?:了|一份)?(?:数据|统计|调查|研究报告|预测)',text[local+hit.end(1):]):continue
            events.append(dict(actors=[m],action=dict(start=offset+pos,end=offset+local+hit.end(1),text=verb),method='本句公共主体的紧邻谓词',scope_start=m['start'],scope_end=offset+len(text)))

        # 同句“某部长表示，政府将给予...”连接的是本句真实代称，不借前文国名制造动作。
        generic=re.search(r'(?:该国政府|该政府|联邦政府|中央政府|政府)',text)
        if generic and public_actor_prefix(text[max(0,generic.start()-12):generic.start()]):
            pub=[m for m in ms if eligible(m) and m.get('public') and m['end']<=offset+generic.start()]
            if pub and len({m['country'] for m in pub})==1:
                speaker=pub[-1];bridge=text[speaker['end']-offset:generic.start()]
                hit=re.match(ADVERBS+r'(?:(?:为|对|向)[^，。；]{1,24}?)?(给予|提供|规定|要求|设定|允许|授权)',text[generic.end():])
                if not hit:
                    hit=re.match(r'(?:当天|当日|同日)?(?:在[^，。；;]{0,22}(?:会议上|会上|会议))?(?:审议)?(通过|批准|决定)',text[generic.end():])
                    if hit and hit[1]=='通过':
                        obj=text[generic.end()+hit.end():]
                        if re.match(r'(?:提高|降低|建设|发展|实施|加强|开展|增加|减少|提供)',obj) or not re.search(r'议案|法案|法律|条例|方案|规划|战略|草案|协议|目标',obj[:90]):hit=None
                if hit and re.search(r'表示|宣布|说明|强调',bridge) and len(bridge)<=45:
                    pos=generic.end()+hit.start(1);events.append(dict(actors=[speaker],action=dict(start=offset+pos,end=offset+generic.end()+hit.end(1),text=hit[1]),
                        method='同句公共机构发言者→代称政府→具体动作',scope_start=offset+generic.start(),scope_end=offset+len(text)))

        # 主断言“中方关注美国退出，并重申...”与被转述的外国动作分开。
        observer=re.search(r'密切关注|关注|回应|评论|谴责|批评|欢迎',text)
        reiteration=re.search(r'[，,]\s*(?:并|也|同时)(?:同时)?(?:重申|继续承诺)',text)
        if observer and reiteration and observer.start()<reiteration.start():
            speakers=[m for m in ms if eligible(m) and m.get('public') and m['end']<=offset+observer.start()]
            if speakers:
                speaker=speakers[0];reported+=events
                v=re.search(r'重申|承诺',reiteration.group());start=reiteration.start()+v.start()
                events=[dict(actors=[speaker],action=dict(start=offset+start,end=offset+start+len(v.group()),text=v.group()),
                    method='主发言者→重申；外国动作保留为转述对象',scope_start=offset+start,scope_end=offset+len(text))]

        # 合作签约只产生参与者证据；后续单方义务不得复制给其他签约国。
        for action in re.finditer(r'签署|签订',text):
            for con in reversed(list(re.finditer(r'与|同|和',text[:action.start()]))):
                if re.search(r'[，,。；！？\n]',text[con.end():action.start()]):continue
                left=[m for m in ms if eligible(m) and m['end']<=offset+con.start()]
                right=[m for m in ms if m.get('role') in {'public_actor','country_candidate','target'} and offset+con.end()<=m['start']<offset+action.start() and m.get('level')!='local']
                if not left or not right:continue
                if len({m['country'] for m in right})>1 and re.search(r'确认|证实|表示|认为',text[right[0]['end']-offset:right[-1]['start']-offset]):continue
                lead=left[-1];bridge=text[lead['end']-offset:con.start()]
                if not re.fullmatch(ADVERBS,bridge) and not re.fullmatch(r'(?:在|就|做出承诺|后|仅|一周|两周|政府|于|[\s，,\d年月日]){0,20}',bridge):continue
                if re.search(r'公司|企业|集团|见证',text[con.end():action.start()]):continue
                participants=[lead]+[dict(m,role='public_actor') for m in right]
                cs=sorted({m['country'] for m in participants})
                if len(cs)<2:continue
                cooperation=cs
                unilateral=[]
                for m in ms:
                    if not eligible(m) or m['start']<offset+action.end():continue
                    tail=text[m['end']-offset:]
                    goal=re.match(r'(?:将|到|于|在|力争|承诺)[^。；]{0,75}',tail)
                    if goal and re.search(r'20\d\d|[\d０-９]+[%％]',goal.group()) and re.search(r'可再生|减排|碳中和|净零|电能|电力|能源',goal.group()):
                        pred=re.search(r'来源于|实现|达到|占|减少|降低|提高',goal.group())
                        pos=m['end']-offset+(pred.start() if pred else 0);verb=pred.group() if pred else goal.group()[:1]
                        unilateral.append(dict(actors=[m],action=dict(start=offset+pos,end=offset+pos+len(verb),text=verb),method='共同声明中明确单方目标',scope_start=m['start'],scope_end=offset+len(text)))
                if unilateral:events=unilateral;joint=False
                else:
                    events=[dict(actors=participants,action=dict(start=offset+action.start(),end=offset+action.end(),text=action.group()),method='同一签署动作的公共参与方',scope_start=lead['start'],scope_end=offset+len(text))];joint=True
                break

        # “两国共同发表”要求具名双边题名及对应公共发言人，不凭单字国名推断。
        pairmap={'中法':['中国','法国'],'中美':['中国','美国'],'中德':['中国','德国'],'中俄':['中国','俄罗斯'],'法德':['法国','德国'],'德法':['德国','法国'],'韩澳':['韩国','澳大利亚']}
        j=re.search(r'两国共同(发表|发布|签署)',text)
        titles=list(re.finditer(r'《('+'|'.join(pairmap)+r')[^》]{1,80}(?:倡议|计划|协定|声明)[^》]{0,12}》',text))
        if j and titles and len({tuple(sorted(pairmap[m[1]])) for m in titles})==1:
            cs=pairmap[titles[0][1]];pub=[m for m in ms if eligible(m) and m.get('public')]
            if pub and all(m['country'] in cs for m in pub):
                people=[next((m for m in pub if m['country']==c),dict(country=c,text=titles[0].group(),start=offset+titles[0].start(),end=offset+titles[0].end(),public=False,role='country_candidate',level='national')) for c in cs]
                events=[dict(actors=people,action=dict(start=offset+j.start(1),end=offset+j.end(1),text=j[1]),method='具名双边政策＋两国共同发表',scope_start=offset+j.start(),scope_end=offset+len(text))]
                joint=True;cooperation=sorted(cs)

        # 双边合作计划的公布方与参与方分开：地点列举本身不产生共同政策。
        joint_title=re.search(r'('+'|'.join(pairmap)+r')[^，。；]{1,35}合作(?:计划|方案|协议)',text)
        joint_evidence=[]
        if joint_title and events and not re.search(r'尚未|并未|没有|建议|希望|拟|草案|如果|若当选',text[:joint_title.end()]):
            participants=sorted(pairmap[joint_title[1]])
            publishers=[ev for ev in events if ev['action']['text'] in {'公布','发布','宣布','签署'} and ev['action']['end']<=offset+joint_title.start()
                and all(m.get('public') and m.get('level')!='local' and m['country'] in participants for m in ev['actors'])]
            if publishers:
                events=publishers;joint=True;cooperation=participants
                joint_evidence=[dict(start=offset+joint_title.start(),end=offset+joint_title.end(),text=joint_title.group(),role='共同政策题名中的参与国；不是新增公布机构')]

        # 国家牵头与地方参与绑定到公共动作，不把句中出现“地方”当成地方自主制定。
        local_parts=[dict(start=offset+m.start(),end=offset+m.end(),text=m.group(),level='local',role='implementation_partner')
            for m in re.finditer(r'(?:各|有关|相关)?地方政府|\d+个地区政府|二十多个州和地方政府|各州(?:、市)?(?:、县)?',text)]
        if local_parts:
            public=[m for m in ms if eligible(m) and m.get('public')]
            all_public=[m for m in ms if m.get('public') and m.get('role') not in {'target','location','private_or_context'}]
            for m in public:
                if any(x.get('level')=='local' and x['start']<m['start'] for x in all_public):continue
                tail=text[m['end']-offset:]
                agreement=re.match(ADVERBS+r'就[^。；;]{1,55}?与(?:各|有关|相关)?地方政府[^。；;]{0,35}?(达成(?:了)?一致|达成(?:了)?协议)',tail)
                if agreement and policy_topic(agreement.group()) and re.search(r'碳(?:排放权)?定价|碳交易|减排标准|补贴|能源转型',agreement.group()) and not re.search(r'尚未|并未|没有|未能|拟|将|希望|期待|建议|呼吁',tail[:agreement.start(1)]):
                    act=dict(start=m['end']+agreement.start(1),end=m['end']+agreement.end(1),text=agreement[1])
                    events.append(dict(actors=[m],action=act,method='国家主体就具体政策与地方达成一致',scope_start=m['start'],scope_end=offset+len(text),national_local_coordination=True,coordination_kind='policy_agreement',local_participants=local_parts))
                meeting=re.match(ADVERBS+r'召开(?:了)?',tail)
                roadmap=re.search(r'在[“"《]([^”"》]{2,65}(?:路线图|行动计划|实施方案))[”"》]中(指明|明确|规定|确定)(?:了)?',tail)
                if meeting and roadmap and not re.search(r'将|拟|预计|计划',tail[:meeting.end()]) and not re.search(r'草案|建议|尚未|未获|未通过',tail[:roadmap.end()]) and policy_topic(text):
                    after=tail[roadmap.end():]
                    if re.search(r'20\d\d|必须|不得|补贴|标准|配额',after) and re.search(r'去碳|脱碳|减排|能源|电力|充电',after):
                        act=dict(start=m['end']+roadmap.start(2),end=m['end']+roadmap.end(2),text=roadmap[2])
                        events.append(dict(actors=[m],action=act,method='国家召开央地会议并明确具名政策内容',scope_start=m['start'],scope_end=offset+len(text),national_local_coordination=True,coordination_kind='published_roadmap',policy_name=roadmap[1],local_participants=local_parts,independent_current_policy=True))
                legal=re.search(r'(?:新法规|该法律|该法案|该条例|联邦法规)(规定|要求|允许|鼓励)',tail)
                if legal and re.match(ADVERBS+r'(?:强调|表示|说明)',tail) and policy_topic(text) and not re.search(r'草案|拟|尚未|建议|希望',tail[:legal.end()]):
                    act=dict(start=m['end']+legal.start(1),end=m['end']+legal.end(1),text=legal[1])
                    events.append(dict(actors=[m],action=act,method='国家主体说明现有规则→地方执行选择',scope_start=m['start'],scope_end=offset+len(text),national_local_coordination=True,coordination_kind='national_rule_local_execution',local_participants=local_parts))
            for ev in events:
                if ev.get('national_local_coordination'):continue
                if not all(m.get('public') and eligible(m) for m in ev['actors']):continue
                if any(x.get('level')=='local' and x['start']<min(m['start'] for m in ev['actors']) for x in all_public):continue
                if ev['action']['text'] in {'推出','公布','发布','提供','拨款','资助','颁布','制定','批准','承诺','授权','下放'} and re.search(r'资助|拨款|财政|补贴|合作建设|授权|下放.{0,15}(?:标准|制定权)',text) and not re.search(r'希望|期待|建议|呼吁|尚未|如果|若当选',text):
                    ev.update(national_local_coordination=True,coordination_kind='national_funding_or_task',local_participants=local_parts)
            if re.search(r'(?:地方政府|州政府|市政府|省政府)[^。；;]{0,18}(?:自行|另行|额外|自主|加码)',text):
                # 仍需拆分国家安排与地方新增措施，不能用合作标签整段放行。
                for ev in events:ev.pop('national_local_coordination',None)

        # 并列国家各自宣布目标，不是仅最后一国施策，也不是共同政策。
        if not joint:
            expanded=[]
            for ev in events:
                actor=ev['actors'][0]
                prior=[m for m in ms if eligible(m) and m['end']<=actor['start']]
                siblings=[];right=actor['start']-offset
                for m in reversed(prior):
                    bridge=text[m['end']-offset:right]
                    if not re.fullmatch(r'\s*(?:和|与|及|以及|、)\s*',bridge):break
                    siblings.append(m);right=m['start']-offset
                if siblings and ev['action']['text'] in {'宣布','公布','承诺','设定'}:
                    expanded.extend(dict(ev,actors=[m],method='并列主体各自采取措施') for m in list(reversed(siblings))+[actor])
                else:expanded.append(ev)
            events=expanded
        # 不把多条不同主语动作强制合为一个国家集合。
        groups={tuple(sorted({m['country'] for m in e['actors']})) for e in events}
        multiple=len(groups)>1 and not joint
        cs=[] if multiple else sorted({m['country'] for e in events for m in e['actors']})
        if joint_evidence:cs=cooperation
        signing=list(re.finditer(r'签署|签订',text));claim_state=None
        if signing:
            prefix=re.split(r'[，,。；]',text[:signing[-1].start()])[-1]
            if re.search(r'(?:尚未|并未|没有|从未|未)[^，,。；]{0,20}$',prefix):claim_state='not_adopted'
        return dict(events=events,countries=cs,mentions=ms,targets=[m for m in ms if m.get('role')=='target'],reported_events=reported,
                    cooperation_countries=cooperation,joint=joint,multiple_policy_events=multiple,claim_state=claim_state,joint_evidence=joint_evidence)

    def _context(self,text,a,record,full):
        owner=self.named_policy_owner(text,a)
        if owner:return owner,'当前政府推出的具名国家战略→发布主体→国家'
        prior=full[max(0,a-self.params['context_chars']):a].split('\n\n')[-1];off=a-len(prior)
        generic=re.search(r'联邦政府|中央政府|该政府|政府|能源部',text)
        if generic and any(m.get('level')=='local' and m['start']<=a+generic.start()<m['end'] for m in self.mentions(text,a)):
            return None,'当前政府属于具名地方机构，不继承国家层级锚点'
        if generic and TARGET_BEFORE.search(text[max(0,generic.start()-12):generic.start()]):return None,'请求/要求中的公共机构是宾语，不继承为施策者'
        if not REF.search(text) and not re.search(r'政府|总统|首相|总理|能源部|^为实现该',text):return None,'当前无主体/政策指代表达'
        if re.match(r'^[“”\s]*(?:我们|他|她)',text):
            speeches=[]
            for m in self.mentions(prior,off):
                if not eligible(m) or not m.get('public'):continue
                tail=prior[m['end']-off:]
                hit=re.match(r'(?:在[^。；]{0,35})?(?:表示|说|强调|指出|在国会.{0,15}演讲)',tail)
                if hit:speeches.append((m,m['end']+hit.end()))
            if speeches:
                m,end=speeches[-1];bridge=full[end:a]
                others={x['country'] for x in self.mentions(bridge,end) if eligible(x)}
                if not others-{m['country']} and not CONTEXT_SWITCH.search(bridge):
                    return dict(start=m['start'],end=end,text=full[m['start']:end],countries=[m['country']],actors=[m],kind='speaker'),'最近可验证公共发言人→人称指代'
        anchors=[]
        for sm in re.finditer(r'[^。！？；;\n]+[。！？；;\n]*',prior):
            t=sm.group()
            comment=re.search(r'[，,](?:但|而)(?=[^。；]{0,65}(?:认为|评价|批评))',t)
            if comment:t=t[:comment.start()]
            rel=self.relation(t,off+sm.start());cs=rel['countries']
            target=bool(re.search(r'到\s*20\d\d.{0,55}(?:[%％]|比重|份额|减少|提高|降低)',t))
            if len(cs)!=1 or not rel['events'] or not policy_topic(t) or not (INSTRUMENT.search(t) or target):continue
            if re.search(r'未能|尚未|认为|预计|有望|批评|建议|呼吁|草案|候选人|竞选',t):continue
            if policy_state(t) in BLOCKED_STATES:continue
            anchors.append(dict(start=off+sm.start(),end=off+sm.start()+len(t),text=t,countries=cs,actors=[m for e in rel['events'] for m in e['actors']],kind='policy'))
        if not anchors:
            institution=self.institution_continuation(text,a,full)
            if institution:return institution,'同段唯一国家机构能源发言→当前政府具体目标/条款；不靠来源文件夹'
            speaker=self.document_policy_speaker(text,a,full)
            if speaker:return speaker,'明确全文政策概述→原文发布主体→当前依法提供措施'
            return None,'没有具名公共措施锚点'
        p=anchors[-1];bridge=full[p['end']:a]
        other={m['country'] for m in self.mentions(bridge,p['end']) if eligible(m)}
        current_public={m['country'] for m in self.mentions(text,a) if eligible(m)}
        if current_public-set(p['countries']):return None,'当前明确公共主体与前文锚点冲突，不继承外国主体'
        if other-set(p['countries']) or CONTEXT_SWITCH.search(bridge) or LOCAL_WORDS.search(bridge):return None,'锚点后竞争主体/主题/地方作用域阻断'
        current_names=names(text)
        if current_names and names(p['text']) and not current_names&names(p['text']):return None,'政策名称不一致'
        return p,'同一政策/通称公共主体→发布机构→国家'

    def country_decision(self,text,a,b,record,full,metadata_status=''):
        rel=self.relation(text,a);actors=[m for e in rel['events'] for m in e['actors'] if eligible(m)]
        cs=rel['countries'];connection=[];anchor=None;linked=[];strengths={};method='abstain'
        if cs:method='explicit_roles'
        elif not rel['multiple_policy_events']:
            anchor,why=self._context(text,a,record,full)
            # 所有权句式直接给出国家政策身份；不得把“某国企业的计划”连成国家政策。
            if not anchor:
                holder=re.match(r'\s*根据([^，。；]{2,12}?)(?:这份|的|这项)?(?:最新)?(?:能源|气候|碳中和|绿色增长)(?:发展)?(?:计划|规划|战略)',text)
                if holder and re.fullmatch(COUNTRIES,holder.group(1)):
                    hm=[m for m in rel['mentions'] if eligible(m) and m['start']<a+holder.end()]
                    hc=sorted({m['country'] for m in hm})
                    if len(hc)==1:
                        anchor=dict(countries=hc,actors=hm,start=a,end=a+holder.end(),text=holder.group());why='当前明确国家所有权的政策题名→国家，公共性仍由内容层判断'
            if anchor:
                cs=anchor['countries'];linked=anchor['actors'];method='verified_reference'
                connection=[dict(from_text=text,to_text=anchor['text'],relation=why,start=anchor['start'],end=anchor['end'])]
        current_generic=re.search(r'(?:联邦政府|中央政府|该国政府|该政府|政府|能源部)',text)
        weak=[]
        local_generic=bool(current_generic and any(m.get('level')=='local' and m['start']<=a+current_generic.start()<m['end'] for m in rel['mentions']))
        if not cs and not rel['multiple_policy_events'] and not any(eligible(m) for m in rel['mentions']) and not local_generic and current_generic and public_actor_prefix(text[max(0,current_generic.start()-12):current_generic.start()]):
            prior=full[max(0,a-800):a].split('\n\n')[-1];off=a-len(prior)
            pm=self.mentions(prior,off);public=[m for m in pm if eligible(m) and m.get('public')]
            pcs={m['country'] for m in public};allcs={m['country'] for m in pm if eligible(m)}
            tail=text[current_generic.end():]
            if len(pcs)==1 and not allcs-pcs and not CONTEXT_SWITCH.search(prior) and not LOCAL_WORDS.search(prior) and re.match(ADVERBS+r'(?:(?:为|对|向)[^，。；]{1,24}?)?(?:提供|给予|规定|要求|计划|设定|允许|授权)',tail):
                strengths={c:self.params['weak_context_E'] for c in pcs};weak=public
        ms=rel['mentions'][:]
        if strengths and current_generic:
            ms+=[dict(country=c,text=current_generic.group(),start=a+current_generic.start(),end=a+current_generic.end(),public=True,role='country_candidate') for c in strengths]
        positions=[e['action']['start']-a for e in rel['events']]
        if current_generic and not positions:
            v=re.search(VERBS,text[current_generic.end():]);positions=[current_generic.end()+v.start()] if v else []
        density=self.density_context(text,a,b,full,anchor,cs)
        scores=score_candidates(text,a,ms,actors if cs and method=='explicit_roles' else [],linked,strengths,record.get('source_country',''),self.params,positions,metadata_status,density)
        if not cs and scores and scores[0]['E']>0:
            best=scores[0];second=scores[1] if len(scores)>1 else {'score':0,'core_score':0}
            if best['score']>=self.params['weak_min'] and best['score']-second['score']>=self.params['weak_margin'] and best['core_score']-second['core_score']>=self.params['weak_margin']:
                cs=[best['country']];method='scored_context';connection=[dict(from_text=text,to_text=m['text'],relation='弱机构上下文评分；不证明公共政策',start=m['start'],end=m['end']) for m in weak]
        verbs=[e['action']['text'] for e in rel['events']]
        action_state=rel['claim_state'] or ('announced_or_adopted' if rel['joint'] and any(v in {'签署','签订','发表','发布'} for v in verbs) else None)
        if not action_state:
            kinds={e.get('coordination_kind') for e in rel['events'] if e.get('national_local_coordination')}
            if kinds=={'policy_agreement'}:action_state='reported_policy_agreement'
            elif kinds=={'national_rule_local_execution'}:action_state='reported_execution_rule'
            elif kinds and '承诺' in verbs:action_state='announced_commitment'
        return dict(countries=cs,method=method,scores=scores,actors=actors or linked,events=rel['events'],targets=rel['targets'],connection=connection,
            reported_events=rel['reported_events'],cooperation_countries=rel['cooperation_countries'],joint=rel['joint'],multiple_policy_events=rel['multiple_policy_events'],
            action_state=action_state,anchor=anchor,density_context=density,version=VERSION,joint_evidence=rel['joint_evidence'])
