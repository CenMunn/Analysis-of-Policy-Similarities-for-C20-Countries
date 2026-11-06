"""CM-PACE候选/关系优化。得分仅为证据排序量，不是校准正确概率。

明确动作角色 > 有路径的政策/主体指代 > 弱上下文评分 > 独立确认公共性后的来源推定。
新增自动保留始终进入扩展候选；不以S覆盖内容、层级、状态和质量隔离。
"""
import copy,re,math,json
from ..政策内容判定.semantic_scope import ReleaseScope71
from ..主体与国家归属.national_scope import TOPIC,INSTRUMENT,PUBLIC,PRIVATE,NATIONAL_SCOPE,LOCAL_WORDS,CONTEXT_SWITCH,G20,evidence,policy_state,competition_scores
from ..主体与国家归属.role_resolution import names
from ..上下文与证据连接.evidence_scope import context_state

VERSION='CM-PACE-attribution-20261026.6.3-density'
DEFAULTS=dict(weights={'E':.60,'P':.15,'D':.20,'M':.05},weak_min=.42,weak_margin=.10,
    context_chars=800,position_scale_chars=40,density_min_mentions=3,density_min_sentences=2,
    feature_version='action_relative',constrain_source=True,source_reliability=.5,
    weak_context_E=.65,source_to_extension=True)

CORPORATE=re.compile(r'(?:的)?(?:科技巨头|能源巨头|汽车巨头|汽车制造商|电力公司|国家电力公司|国家石油公司|石油公司|汽车公司|国有企业|国有公司|公用事业公司|大型企业|供应商|开发商|制造商|公司|企业|集团|厂商|媒体|学者|专家|市场|协会)')
NEW_VERB=re.compile(r'允许|授权|设定|设立|改造|推出|扩大|将把|将扩大|将提供|包括|规定|要求')
MODAL=r'(?:实际上|实际|一直|已经|仍然|继续|目前|最近|近日|日前|还|也|已|曾|将|会|则|正式|于|在|通过|表示|宣布|计划|的|[\s，,：:“”"\d０-９年月日]){0,16}'
CIVIL_NUCLEAR=re.compile(r'民用[^。；;]{0,15}核技术')
def policy_topic(text):return bool(TOPIC.search(text) or CIVIL_NUCLEAR.search(text) or '巴黎协议' in text)
GENERIC_SUBJECT=re.compile(r'(?:该国(?:政府)?|该政府|该部门|该部|联邦政府|中央政府|政府|总统|首相|总理|有关部门|能源部|财政部|环境部|环境省|国会|议会|内阁)')
ANAPHOR=re.compile(r'该国(?:政府)?|该政府|该部门|该部|该计划|这项法律|上述措施|该战略|该方案|其目标|该政策|该法律')
CONCRETE=re.compile(r'补贴|减免|税收|税率|上限|配额|认证|许可|出口|招标|拍卖|拨款|预算|标准|法律|法案|条例|备忘录|协议|减排|碳中和|净零|目标|电站|电厂|可再生能源|光伏|太阳能|风电|清洁氢|燃料电池|电动汽车|新能源|改造|占比|比例|份额')
COMMENT=re.compile(r'^(?:[“”\s]*)(?:分析师|专家认为|研究人员认为|笔者|这意味着|由此可见|调查显示)|凸显|意义重大|有助于|有望|预计|预测|相信|认为|担忧|加剧.{0,8}竞争|必要性|迫切|最便宜|应该|呼吁|建议')
BLOCK_STATES={'campaign','not_adopted','draft_or_proposal','proposed_change','discussion','conditional_proposal'}
PUBLIC_ACTION_TAIL=re.compile(MODAL+r'(?:(?:为|向|对)[^，。；;]{1,24}?)?(允许|授权|设定|提供|扩大|推出|要求|规定|计划|改造|制定|确认|打算|进行)')
PUBLIC_TOOL=re.compile(r'补贴|补助|税收|税率|减免|抵免|配额|排放上限|排放标准|认证制度|财政|拨款|预算|采购|招标|拍卖|低息贷款|优惠贷款|贷款担保|'
    r'《[^》]{2,80}(?:法|条例|办法|规划|战略|计划|协定)[^》]{0,12}》|'
    r'(?:允许|授权|禁止|不得).{0,40}(?:出口|出售|建设|建造|生产|经营|交易|排放)|'
    r'(?:电站|电厂).{0,20}(?:改造|改成|转为|关闭|淘汰)|'
    r'(?:到|于|前)\s*[2２][0０][\d０-９]{2}年.{0,30}(?:达到|减少|降低|实现|占|提高)|'
    r'(?:实施|推行|建立).{0,15}(?:碳定价|碳交易|排放权交易|碳税)')

def generic_actor(text):
    for m in GENERIC_SUBJECT.finditer(text):
        prefix=text[max(0,m.start()-12):m.start()]
        if re.search(r'(?:向|对|请求|要求|呼吁|建议|敦促|希望|期待|促请)\s*$',prefix):continue
        return m
    return None

def eligible(m):return m.get('country') in G20 and m.get('role') in {'public_actor','country_candidate'} and m.get('level')!='local'

def score_candidates(text,offset,mentions,actors,links,strengths,source,params,action_positions=None,metadata_status='',density_context=None):
    """E查证据表；P为主体在措施动作之前的字符距离；D只用重复且跨句提及；M须来源有效且无角色冲突。"""
    p=dict(DEFAULTS,**params);weights=p['weights']
    own={m['country'] for m in actors if eligible(m)};linked={m['country'] for m in links if eligible(m)}
    candidates={m['country'] for m in mentions if eligible(m)}|own|linked|set(strengths)
    sentences=list(re.finditer(r'[^。！？；;\n]+[。！？；;\n]*',text));L=max(1,len(text));ns=max(1,len(sentences))
    action_positions=action_positions or [m.start() for m in NEW_VERB.finditer(text)]
    out=[]
    for c in sorted(candidates):
        ms=[m for m in mentions if eligible(m) and m['country']==c]
        positions=sorted({m['start']-offset for m in ms});covered=[i for i,s in enumerate(sentences) if any(s.start()<=x<s.end() for x in positions)]
        E=1. if c in own else .85 if c in linked else strengths.get(c,0.)
        n=len(positions);gap=(positions[-1]-positions[0])/(n-1) if n>1 else None
        dn=n;dh=len(covered);dk=ns;dL=L;dspan=positions[-1]-positions[0] if n>1 else 0;dscope='current_unit'
        if p.get('density_scope')=='linked_policy' and density_context and c in density_context['countries']:
            dt=density_context['text'];da=density_context['start']
            ds=list(re.finditer(r'[^。！？；;\n]+[。！？；;\n]*',dt))
            dp=sorted({m['start']-da for m in density_context['mentions'] if eligible(m) and m['country']==c})
            dn=len(dp);dk=max(1,len(ds));dL=max(1,len(dt));dh=sum(any(s.start()<=x<s.end() for x in dp) for s in ds)
            dspan=dp[-1]-dp[0] if dn>1 else 0;dscope='linked_policy'
        if p['feature_version']=='legacy':
            P=1/(1+covered[0]) if covered else 0.
            D=n/(n+2)*(.7*len(covered)/ns+.3*(1/(1+gap/(L/ns)) if gap is not None else 0))
            davail=bool(n)
        else:
            distances=[]
            for m in ms:
                end=m['end']-offset
                for action in action_positions:
                    if 0<=action-end<=160 and not re.search(r'[。！？；;\n]',text[end:action]):distances.append(action-end)
            # 已验证跨句主体无当前字面位置：P缺失，不虚构零距离。
            P=max((1/(1+d/p['position_scale_chars']) for d in distances),default=0.)
            davail=dn>=p['density_min_mentions'] and dh>=p['density_min_sentences']
            # 分布覆盖和跨度，惩罚两次局部紧邻提及；n=0/1/2不使用密度。
            span=dspan/dL
            D=dn/(dn+2)*dh/dk*math.sqrt(max(0,span)) if davail else 0.
        rel=1. if metadata_status in {'matched','exact','元数据匹配成功'} else p['source_reliability']
        M=rel if c==source and source in G20 else 0.
        if p['constrain_source']:
            if own and c not in own:M=0.
            if linked and c not in linked:M=0.
            # 多国弱竞争时来源不参与排序，防止5%的来源先验翻转微小差异。
            if len(candidates)>1 and not own and not linked:M=0.
        score=weights['E']*E+weights['P']*P+weights['D']*D+weights['M']*M
        out.append(dict(country=c,E=E,P=P,D=D,M=M,score=score,core_score=score-weights['M']*M,
            n=n,mean_gap=gap,D_available=davail,P_available=bool(ms and action_positions),
            density_mentions=dn,density_sentences=dh,density_total_sentences=dk,density_char_length=dL,density_span_chars=dspan,density_scope=dscope,
            evidence_type='direct' if c in own else 'verified_reference' if c in linked else 'weak_context' if E else 'mention_only',
            note='证据排序量，非概率；缺失项取0不重归一化'))
    return sorted(out,key=lambda r:(-r['score'],r['country']))

class OptimizedScope(ReleaseScope71):
    def __init__(self,raw_mentions,params=None):
        super().__init__(raw_mentions);self.params=dict(DEFAULTS,**(params or {}));self.link_cache={};self._decision_cache={}

    def mentions(self,text,offset=0):
        ms=super().mentions(text,offset)
        for m in ms:
            if CORPORATE.match(text[m['end']-offset:]):m.update(public=False,role='private_or_context')
        return ms

    def relation(self,text,offset):
        rel=super().relation(text,offset);ms=self.mentions(text,offset)
        # 上游pending也会产生事件：用同位置最终实体角色回填，阻止公司国籍成为公共主体。
        ev=[]
        for e in rel['events']:
            actors=[]
            for m in e['actors']:
                matches=[x for x in ms if x['country']==m['country'] and x['start']==m['start']]
                actual=max(matches,key=lambda x:x['end']) if matches else m
                if actual.get('role')=='private_or_context':continue
                actors.append(actual)
            if actors:ev.append(dict(e,actors=actors))
        for m in ms:
            if not eligible(m):continue
            local=m['end']-offset;tail=text[local:]
            hit=PUBLIC_ACTION_TAIL.match(tail)
            nominal=re.match(r'(?:的|提出的|公布的)(?:[^，。；;]{0,18})(?:计划|方案|战略|规划)(?:明确)?(包括|规定|要求)',tail)
            hit=nominal or hit
            if not m.get('public'):
                # 字面国家名只有紧邻正式公共动作时才补关系，不能从产业/企业国籍推导公共性。
                hit=re.match(MODAL+r'(签署|公布|发布|宣布|制定|批准)',tail)
            if not hit:continue
            a=local+hit.start(1);b=local+hit.end(1)
            if re.search(r'(?:对|向|针对|要求|建议|希望|呼吁)\s*$',text[max(0,m['start']-offset-6):m['start']-offset]):continue
            if not policy_topic(text):continue
            ev.append(dict(actors=[m],action=dict(start=offset+a,end=offset+b,text=text[a:b]),method='OPT公共主体→允许/授权/名词化方案动作',optimized_relation=True))
        # 公共主体的日期插入并列签署；公司合作不作为国家共同政策。
        for a in re.finditer(r'签署|签订|共同发表',text):
            prefix=text[:a.start()]
            for conn in reversed(list(re.finditer(r'与|同|和',prefix))):
                left=[m for m in ms if eligible(m) and m['end']<=offset+conn.start()]
                right=[m for m in ms if m.get('role') in {'public_actor','country_candidate','target'} and offset+conn.end()<=m['start']<offset+a.start() and m.get('level')!='local']
                if not left or not right:continue
                lead=left[-1]
                if not re.fullmatch(r'(?:政府|还|已|又|曾|将|宣布|表示|同意|于|在|[\d０-９年月日\s，,]){0,25}',text[lead['end']-offset:conn.start()]):continue
                if PRIVATE.search(text[conn.end():a.start()]) or re.search(r'见证',prefix):continue
                pair=[lead]+[dict(m,role='public_actor') for m in right]
                if len({m['country'] for m in pair})<2:continue
                ev=[dict(actors=pair,action=dict(start=offset+a.start(),end=offset+a.end(),text=a.group()),method='OPT具日期的并列公共签约主体',optimized_relation=True,joint=True)];break
        # “两国共同发表《中法…倡议》”：题名与公共发布动作共同证实参与方，不把任何中/法字当国名。
        joint=re.search(r'两国共同(发表|发布|签署)',text)
        if joint and not re.search(r'公司|企业|集团|见证',text[:joint.end()]):
            pairs={'中法':['中国','法国'],'中美':['中国','美国'],'中德':['中国','德国'],'中俄':['中国','俄罗斯'],
                   '法德':['法国','德国'],'德法':['德国','法国'],'日韩':['日本','韩国'],'韩澳':['韩国','澳大利亚']}
            matches=[(m,pairs[m[1]]) for m in re.finditer(r'《('+'|'.join(pairs)+r')[^》]{1,90}(?:倡议|计划|协定|协议|声明)[^》]{0,15}》',text)]
            groups={tuple(sorted(cs)) for _,cs in matches}
            public=[m for m in ms if eligible(m) and m.get('public')]
            if len(groups)==1 and public and all(m['country'] in next(iter(groups)) for m in public):
                title,cs=matches[0];participants=[]
                for i,c in enumerate(cs):
                    found=next((m for m in public if m['country']==c),None)
                    participants.append(found or dict(country=c,text=title.group(),start=offset+title.start(),end=offset+title.end(),
                        public=False,role='country_candidate',level='national',participant_evidence='具名双边题名＋两国共同发表'))
                ev=[dict(actors=participants,action=dict(start=offset+joint.start(1),end=offset+joint.end(1),text=joint[1]),
                    method='OPT共同发布谓词＋具名双边政策题名',optimized_relation=True,joint=True)]
        unique={(e['action']['start'],tuple(sorted((m['start'],m['country']) for m in e['actors']))):e for e in ev}
        ev=list(unique.values())
        return dict(rel,events=ev,mentions=ms,countries=sorted({m['country'] for e in ev for m in e['actors']}))

    def anchor_pool(self,record,full):
        return [p for p in super().anchor_pool(record,full)
                if not COMMENT.search(p['text']) and not re.search(r'未能.{0,8}(?:制定|出台|实施)|尚未|必须被允许',p['text'])
                and context_state(p['text'],'')[0] not in BLOCK_STATES]

    def connect(self,text,a,b,record,full):
        anchor,why=super().connect(text,a,b,record,full)
        if ANAPHOR.search(text) or GENERIC_SUBJECT.search(text):
            mentions=list(GENERIC_SUBJECT.finditer(text))
            if mentions and generic_actor(text) is None:return None,'通称公共机构是请求/要求/向等结构的宾语，不连接为施策者'
        if anchor:
            if re.search(r'该国|该政府|该部门|该部',text):
                bridge=full[anchor['end']:a]
                competition={m['country'] for m in self.mentions(bridge,anchor['end']) if eligible(m)}
                if competition-set(anchor['countries']):return None,'指代锚点后出现显式竞争国名，主体有歧义'
            return anchor,why
        if why in {'同名政策具有多个发布国家','当前国别与同名政策发布者相冲突'}:return None,why
        if not (ANAPHOR.search(text) or GENERIC_SUBJECT.match(text.lstrip('“” \n'))):return None,why
        if COMMENT.search(text):return None,'当前主断言为评论/建议，不补主体'
        current={m['country'] for m in self.mentions(text,a) if eligible(m) and m.get('public')}
        before=full[max(0,a-self.params['context_chars']):a];base=a-len(before)
        frames=[]
        for s in re.finditer(r'[^。！？；;\n]+[。！？；;\n]*',before):
            t=s.group()
            # 仅用于主体锚点的事实范围；把“但观察者认为…”留在原文，不拿评论作政策证据。
            tail=re.search(r'[，,](?:但|而)(?=[^。；]{0,60}(?:认为|批评|评价|观察))',t)
            if tail:t=t[:tail.start()]
            rel=self.relation(t,base+s.start())
            actors=[m for e in rel['events'] for m in e['actors'] if eligible(m)]
            cs=sorted({m['country'] for m in actors})
            if len(cs)!=1 or not policy_topic(t) or not INSTRUMENT.search(t) or COMMENT.search(t):continue
            if policy_state(t) in BLOCK_STATES or self.level(t,rel)!='national':continue
            frames.append(dict(start=base+s.start(),end=base+s.start()+len(t),text=t,countries=cs,names=names(t),relation=rel))
        if not frames:return None,why
        p=frames[-1];bridge=full[p['end']:a]
        if '\n\n' in bridge or CONTEXT_SWITCH.search(bridge) or LOCAL_WORDS.search(bridge):return None,'指代锚点之后有段落/主题/层级转换'
        competing={m['country'] for m in self.mentions(bridge,p['end']) if eligible(m)}
        if competing-set(p['countries']) or (current and current-set(p['countries'])):return None,'指代连接中存在竞争公共主体'
        old=set(re.findall(r'光伏|太阳能|风电|核电|氢能|汽车|煤炭',p['text']));new=set(re.findall(r'光伏|太阳能|风电|核电|氢能|汽车|煤炭',text))
        if old and new and not old&new:return None,'政策指代主题不一致'
        return p,'OPT该国/该政府/该部门→同段唯一国家公共政策锚点'

    def country_decision(self,text,a,b,record,full,metadata_status=''):
        key=(record['file_id'],a,b,record.get('source_country',''),metadata_status,json.dumps(self.params,sort_keys=True))
        if key not in self._decision_cache:self._decision_cache[key]=self._country_decision(text,a,b,record,full,metadata_status)
        return copy.deepcopy(self._decision_cache[key])

    def _country_decision(self,text,a,b,record,full,metadata_status=''):
        rel=self.relation(text,a);actors=[m for e in rel['events'] for m in e['actors'] if eligible(m)]
        direct=sorted({m['country'] for m in actors});anchor=None;why='';linked=[]
        if not direct:
            anchor,why=self.connect(text,a,b,record,full)
            if anchor:linked=[m for e in anchor['relation']['events'] for m in e['actors'] if eligible(m)]
        connection=[] if not anchor else [dict(from_text=text,to_text=anchor['text'],relation=why,start=anchor['start'],end=anchor['end'])]
        strengths={};weak_evidence=[]
        # 弱上下文必须是本句有公共动作但缺国别；不是把最近任何国名继承过来。
        generic=generic_actor(text)
        has_action=generic and PUBLIC_ACTION_TAIL.match(text[generic.end():])
        if not direct and not linked and has_action and CONCRETE.search(text) and not COMMENT.search(text):
            prior=full[max(0,a-self.params['context_chars']):a].split('\n\n')[-1];off=a-len(prior)
            if not CONTEXT_SWITCH.search(prior) and not LOCAL_WORDS.search(prior):
                # 文段内有公共机构及同主题；多个机构国别保留竞争，不只取最近。
                for m in self.mentions(prior,off):
                    if eligible(m) and m.get('public'):
                        strengths[m['country']]=self.params['weak_context_E'];weak_evidence.append(m)
                all_countries={m['country'] for m in self.mentions(prior,off) if eligible(m)}
                if all_countries-set(strengths):strengths={};weak_evidence=[]
        ms=self.mentions(text,a)
        if strengths and generic:
            # 候选仅绑定到本句真实的通称公共主体位置；E仍是弱上下文等级，不伪装明确角色。
            ms+= [dict(country=c,text=generic.group(),start=a+generic.start(),end=a+generic.end(),
                       public=True,role='country_candidate',level='unknown',candidate_origin='weak_context') for c in strengths]
        actions=[e['action']['start']-a for e in rel['events']]
        if has_action:
            actions.append(generic.end()+has_action.start(1))
        scores=score_candidates(text,a,ms,actors,linked,strengths,record.get('source_country',''),self.params,actions,metadata_status)
        if direct:cs=direct;method='explicit_roles'
        elif linked:cs=sorted({m['country'] for m in linked});method='verified_reference'
        else:
            cs=[];method='abstain'
            if scores and scores[0]['E']>0 and scores[0]['score']>=self.params['weak_min']:
                gap=scores[0]['score']-(scores[1]['score'] if len(scores)>1 else 0)
                core_gap=scores[0]['core_score']-max((s['core_score'] for s in scores[1:]),default=0)
                if gap>=self.params['weak_margin'] and core_gap>=self.params['weak_margin']:
                    cs=[scores[0]['country']];method='scored_context'
                    connection=[dict(from_text=text,to_text=m['text'],relation='OPT弱公共主体上下文→候选评分，非确定共指',start=m['start'],end=m['end']) for m in weak_evidence if m['country'] in cs]
        return dict(countries=cs,method=method,scores=scores,relation=rel,actors=actors or linked,connection=connection,
                    anchor=anchor,weak_evidence=weak_evidence,connection_reason=why)

    def assess_unit(self,record,full,doc,a,b):
        e=super().assess_unit(record,full,doc,a,b)
        return self.finalize(e,full,doc)

    def finalize(self,e,full,doc):
        """最后入口也调用：后续修补不得丢掉新增角色；固定复核输入不自动改写。"""
        t=e['text'];a=e['start'];b=e['end']
        civil_permission=bool(CIVIL_NUCLEAR.search(t) and re.search(r'允许|授权',t) and re.search(r'出售|出口',t))
        if e.get('route') not in {'subject_unknown','level_unknown','content_uncertain'} and not e.get('route','').startswith('main_') and not (e.get('route')=='out_of_scope' and civil_permission):return e
        previous=e.get('optimized_attribution',{})
        record=dict(file_id=e['file_id'],source_country=doc.get('source_country',e.get('source_country','')))
        d=self.country_decision(t,a,b,record,full,doc.get('metadata_status',''))
        e['optimized_attribution']={k:v for k,v in d.items() if k not in {'relation','anchor'}}
        e['optimized_attribution']['version']=VERSION
        e['optimized_attribution']['decision_used']=bool(previous.get('decision_used'))
        if previous.get('actual_method'):e['optimized_attribution']['actual_method']=previous['actual_method']
        e['optimized_attribution']['decision_history']=copy.deepcopy(previous.get('decision_history',[]))
        if e.get('decision_origin')=='fixed_review_input':return e
        rel=d['relation'];new_rel=any(x.get('optimized_relation') for x in rel['events'])
        private_only=bool(self.mentions(t,a)) and not any(eligible(m) for m in self.mentions(t,a)) and not PUBLIC.search(t)
        # 开发集发现的断言边界：这些句式即便有政策名，也不是已采纳公共措施。
        veto=None
        if re.search(r'(?:制定|实施).{0,25}(?:必要性|迫切)|(?:迈出|迈出的).{0,10}重要一步',t) and not re.search(r'政府.{0,10}(?:决定|宣布|批准)',t):
            veto=('commentary','OPT必要性/意义评价未断言已经采纳措施')
        elif re.search(r'必须被允许|应当被允许|应该被允许',t):veto=('discussion','OPT争取许可的诉求不等于已获得政府授权')
        elif re.search(r'(?:独立报|日报|媒体|报纸|报道称).{0,35}(?:标题|宣战|战火)',t) and re.search(r'认为|用|比喻',t):
            veto=('commentary','OPT媒体标题/修辞评价，不是措施事实')
        elif re.search(r'会见|访问',t) and re.search(r'达成.{0,8}(?:重要)?共识',t) and not re.search(r'签署|签订|批准|补贴|税率|承诺.{0,15}\d',t):
            veto=('discussion','OPT会谈和笼统共识单列线索，未写具体公共工具')
        if veto:
            e.update(route=veto[0],countries=[],reason=veto[1],policy_state=veto[0]);e['optimized_attribution']['decision_used']=True;return e
        if e.get('route','').startswith('main_') and private_only and not d['countries']:
            e.update(route='private_project',countries=[],reason='OPT公共主体复核：仅公司国籍/企业主体，原文没有公共安排',newly_recovered=False)
            e['optimized_attribution']['decision_used']=True;return e
        # 已有真实国别不以弱评分替换。只有新增明确关系，才校正旧角色。
        if e.get('route','').startswith('main_'):
            if d['countries'] and (new_rel or (not e.get('countries') and d['method']!='abstain')):
                changed=set(e.get('countries',[]))!=set(d['countries'])
                e.update(countries=d['countries'],country_basis='OPT '+d['method'])
                e['roles']['actors']=d['actors'];e['roles']['actions']=[x['action'] for x in rel['events']]
                if changed:e.update(newly_recovered=True,reason=e.get('reason','')+'；OPT新增角色关系校正国别')
                e['optimized_attribution']['decision_used']=changed or previous.get('decision_used',False)
            if any(x.get('joint') for x in rel['events']) and len(d['countries'])>1:
                e.update(event_type='joint_policy',countries=d['countries']);e['roles']['cooperation_countries']=d['countries']
            return e
        allowed={'subject_unknown','level_unknown','content_uncertain'}
        if civil_permission:allowed.add('out_of_scope')
        if e.get('route') not in allowed:return e
        if COMMENT.search(t) or re.search(r'见证|统计显示|数据显示|研究表明|同比|去年.{0,15}占比|如果|倘若|^若|尚未|并未|没有.{0,6}(?:允许|授权)|将.{0,6}(?:允许|授权)',t):return e
        if not policy_topic(t) or not CONCRETE.search(t) or not PUBLIC_TOOL.search(t):return e
        if e.get('quality_risks') or e.get('previous_quality_risks'):return e
        state,why=context_state(t,full[max(0,a-800):a]);state=state or policy_state(t)
        if state in BLOCK_STATES:return e
        lev=self.level(t,rel)
        anchor=d['anchor'];generic=generic_actor(t)
        generic_action=bool(generic and PUBLIC_ACTION_TAIL.match(t[generic.end():]))
        confirmed_public=bool(new_rel and any(m.get('public') for m in d['actors'])) or bool(anchor and generic_action) or bool(generic_action and PUBLIC_TOOL.search(t))
        if not confirmed_public:return e
        if lev not in {'national','unknown'}:return e
        # unknown不能仅因S高而升级：须当前国家公共机构或验证后的国家锚点。
        national=lev=='national' or bool(anchor) or bool(d['method']=='scored_context' and generic_action)
        if not national:return e
        cs=d['countries'];method=d['method']
        if not cs and self.params['source_to_extension'] and generic_action and NATIONAL_SCOPE.search(t):
            source=record['source_country'];curr=[m for m in self.mentions(t,a) if eligible(m)]
            prior=self.mentions(full[max(0,a-800):a],max(0,a-800))
            opposite={m['country'] for m in curr+prior if eligible(m) and m.get('public')}-{source}
            if source in G20 and not curr and not opposite:cs=[source];method='source_inferred'
        if not cs:return e
        previous_route=e['route']
        e.update(route='main_source_inferred' if method=='source_inferred' else 'main_explicit',countries=cs,policy_level='national',policy_state=state,
            newly_recovered=True,delivery_layer='扩展候选',country_basis='OPT '+method,
            reason='OPT当前公共措施与国家层级独立成立；'+method+'补主体，新增条目单列扩展候选',
            implementation_claim='保留原文动作状态，不推定未来目标已完成')
        e.setdefault('roles',{}).update(actors=d['actors'],actions=[x['action'] for x in rel['events']])
        e.setdefault('connection_path',[]).extend(d['connection']);e.setdefault('evidence',[])
        for p in d['connection']:e['evidence'].append(evidence(full,p['start'],p['end'],'OPT主体连接证据'))
        e['optimized_attribution'].update(decision_used=True,actual_method=method)
        e['optimized_attribution']['decision_history'].append(dict(previous_route=previous_route,
            method=method,countries=cs,reason=e['reason'],evidence=d['connection']))
        if any(x.get('joint') for x in rel['events']) and len(cs)>1:
            e.update(event_type='joint_policy');e['roles']['cooperation_countries']=cs
        return e
