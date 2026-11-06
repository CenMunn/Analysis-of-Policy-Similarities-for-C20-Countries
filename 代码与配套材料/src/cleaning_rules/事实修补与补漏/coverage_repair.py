"""国家覆盖漏入口修补；只读取原文，新增事实进入扩展候选。

角色模板在相邻子句上绑定施策主体、工具及状态，不用来源文件夹或样本ID。
原文仍由连续归档及可追溯多部分事实完整覆盖。
"""
import copy
import re
from ..事实修补与补漏.recall_rules import COUNTRIES, country
from ..公共工具.identifiers import ident

VERSION = 'policy-coverage-repair-20261024.7.5.6'
PARAMETERS = dict(strategy_anchor_chars=300, source_inference=False,
                  new_layer='扩展候选', weights_changed=False,
                  multi_country_semantics='各国并列承诺分别成事件，不当作共同政策',
                  confidence_is_probability=False)
C = '(?:' + COUNTRIES + ')'
TIME = r'(?:(?:从|自|于)?\s*(?:19|20)\d\d\s*年(?:\s*\d{1,2}\s*月)?(?:\s*\d{1,2}\s*日)?\s*)'
PREFIX = r'(?:\s|\d+[）).、]|另外[，,]|此外[，,]|同时[，,]|而)*'
TAX = re.compile(PREFIX + r'(?P<c>' + C + r')(?:政府)?(?:' + TIME + r')?(?:开始|已经开始|已开始|已|正式)?向(?P<target>[^，,。；;]{1,35}?)征收(?P<measure>[^，,。；;]{0,65}碳税)')
TARIFF = re.compile(PREFIX + r'(?P<c>' + C + r')(?:的)?(?:新能源|可再生能源|光伏|太阳能|风电)?上网电价(?:补贴)?(?:计划|政策|制度|方案)(?:已经|已)?延长至[^，,。；;]{1,30}')
PILOT = re.compile(PREFIX + r'(?P<c>' + C + r')(?:今年|去年|' + TIME + r')?(?:正式|已经|已)?(?:进入|启动|开始)(?:了)?全国(?:碳市场|碳排放交易体系|碳排放交易市场)(?:的)?试点(?:运行)?(?:阶段)?')
CONTRAST = re.compile(PREFIX + r'(?P<c>' + C + r')尚未公布碳达峰计划[，,](?P<goal>但(?:已)?规划\s*20\d\d\s*年实现碳中和[。]?)')
PARALLEL = re.compile(r'(?P<list>' + C + r'(?:[、及和]' + C + r')+)(?:等经济体|等国|等国家)?(?P<claim>做出20\d\d\s*年实现碳中和的承诺)')
UNSAFE = re.compile(r'如果|假如|倘若|建议|拟议|草案|尚未|尚待|否认|没有|未能|可能|预计|考虑|竞选|候选人|(?:拟|将)向')
PROTECTED = {'quality_unknown','local_policy','local_execution','noise','campaign','science','international_framework'}


def piece(full, a, b):
    return dict(start=a, end=b, text=full[a:b])


class CoverageRepair:
    def record(self, old, full, parts, countries, state, reason, anchors=(), rule=''):
        r = copy.deepcopy(old)
        ps = [piece(full, a, b) for a, b in parts]
        r.update(start=ps[0]['start'], end=ps[-1]['end'], text=''.join(p['text'] for p in ps),
                 event_id=ident('CR-', (old['event_id'], parts, countries, state)),
                 countries=countries, route='main_explicit', policy_level='national', policy_state=state,
                 delivery_layer='扩展候选', newly_recovered=True, country_basis='当前政策工具和正文国家关系',
                 algorithm_version=VERSION, reason=reason, coverage_repair_rule=rule,
                 coverage_previous_route=old['route'], coverage_parent_span=[old['start'],old['end']],
                 coverage_previous_countries=old.get('countries',[]),
                 independent_human=False, joint_participants=[], event_type='national_policy',
                 implementation_claim='只表示该动作的原文状态，不推定未来目标已经实现',
                 roles={'actors': [], 'actions': [], 'targets': [], 'measures': []},
                 policy_names=[], connection_path=[])
        r.pop('text_parts', None)
        if len(ps)>1:r['text_parts']=ps
        r['evidence']=[dict(p, file_id=r['file_id'], role='本条政策事实原文部分') for p in ps]
        if rule in {'negative_scope','parallel_goals'}:
            # 此两类是纯国家碳中和目标，不含新金额、实施条件或独立文件名。
            r['structured_goal']=dict(kind='national_netzero_target',countries=countries,
                                      target_year=re.search(r'20\d\d',r['text']).group(),state=state)
        for a,b,role in anchors:
            p=piece(full,a,b)
            r['evidence'].append(dict(p,file_id=r['file_id'],role=role))
            r['connection_path'].append(dict(from_text=r['text'],to_text=p['text'],to_start=a,to_end=b,
                                             countries=countries,relation=role))
        # 不虚构原文不存在的机构；国家名称是明确施策国，机构字段仍可为空。
        for c in countries:
            for p in ps:
                at=p['text'].find(c)
                if at>=0:
                    r['roles']['actors'].append(dict(country=c,text=c,start=p['start']+at,
                        end=p['start']+at+len(c),public=False,level='national',role='country_candidate'))
                    break
        return r

    def remainder(self, old, full, a, b, route):
        r=copy.deepcopy(old)
        r.update(**piece(full,a,b),event_id=ident('CR-R-',(old['event_id'],a,b,route)),route=route,
                 countries=[],delivery_layer='隔离归档',policy_state='',joint_participants=[],
                 reason='覆盖修补：政策事实之外的引导语/统计/说明另存，原文不销毁',
                 coverage_repair_rule='remainder',coverage_parent_span=[old['start'],old['end']],
                 coverage_previous_route=old['route'],newly_recovered=False,connection_path=[])
        r.pop('text_parts',None)
        r['evidence']=[dict(piece(full,a,b),file_id=r['file_id'],role='拆分余文原文')]
        return r

    def partitions(self, old, full, facts, covered, suffix_route='background'):
        # 联合覆盖用于留存标点等间隙；并列各国共享谓词允许证据区间重叠。
        out=list(facts);end=old['start']
        for a,b in sorted(covered):
            if a>end:out.append(self.remainder(old,full,end,a,'introduction' if end==old['start'] else suffix_route))
            end=max(end,b)
        if end<old['end']:out.append(self.remainder(old,full,end,old['end'],suffix_route))
        return sorted(out,key=lambda r:(r['start'],r['end'],str(r['countries'])))

    def revise(self, old, full, doc):
        if old.get('text_parts') or old['route'] in PROTECTED:return [old]
        a,b,t=old['start'],old['end'],old['text']
        assert full[a:b]==t
        # 未公布的是碳达峰，不传播到另一个有已公布战略佐证的碳中和目标。
        m=CONTRAST.fullmatch(t)
        if m:
            c=country(m['c']);following=full[b:b+PARAMETERS['strategy_anchor_chars']]
            sent=re.match(r'[^。！？]+[。！？]?',following)
            if sent and re.match(re.escape(m['c']),sent.group()) and re.search(r'公布了?低排放\s*发展战略',sent.group()):
                target_year=re.search(r'20\d\d',m['goal']).group()
                if target_year in sent.group() and not UNSAFE.search(sent.group()):
                    x,y=a+m.start('goal')+1,a+m.end('goal')
                    r=self.record(old,full,[(a+m.start('c'),a+m.end('c')),(x,y)],[c],'announced_goal',
                                  '否定仅绑定碳达峰；碳中和目标与紧随同国已公布战略相连',
                                  [(b,b+sent.end(),'同国已公布战略→目标状态')], 'negative_scope')
                    return self.partitions(old,full,[r],[(p['start'],p['end']) for p in r['text_parts']])
            return [old]
        # 规则只能证明下列肯定陈述，不越过条件、否定、专家建议与地方层级。
        for pattern,state,rule in [(TAX,'implementation','tax_actor_target'),(TARIFF,'program_extended','tariff_extension'),(PILOT,'pilot_operation','ets_pilot')]:
            m=pattern.match(t)
            if not m:continue
            candidate=t[m.start('c'):m.end()]
            if UNSAFE.search(t[:m.end()]):continue
            x,y=a+m.start('c'),a+m.end();c=country(m['c'])
            # 税率分项是执行条件。只切掉明确的预测/评论尾句，不丢金额与适用对象。
            if rule=='tax_actor_target':
                detail=re.match(r'[，,]其中[^。！？]*[。！？]?',t[m.end():])
                if detail:
                    d=detail.group()
                    tail=re.search(r'[，,](?=(?:预计|有望|分析师|专家认为|这将))',d)
                    if tail:d=d[:tail.start()]
                    if re.search(r'每吨征税|税率为|适用税率',d) and not UNSAFE.search(d) and not re.search(C,d):y+=len(d)
            reason={'tax_actor_target':'征税国是施策主体，企业是纳税对象；不判为企业自主项目',
                    'tariff_extension':'国家上网电价制度已延期；统计及抢装评论另存',
                    'ets_pilot':'全国碳市场进入试点运行；不等同全面正式运行'}[rule]
            r=self.record(old,full,[(x,y)],[c],state,reason,rule=rule)
            facts=[r];covered=[(x,y)]
            if rule=='tax_actor_target':
                rest=t[m.end():]
                publication=re.match(r'[，,]\s*'+TIME+r'公布了?低排放\s*发展战略[^。！？]*[。！？]?',rest)
                if publication and not UNSAFE.search(publication.group()) and not re.search(C,publication.group()):
                    u=y+1;v=y+publication.end()
                    sr=self.record(old,full,[(u,v)],[c],'announced_strategy',
                        '同句征税国→随后已公布低排放发展战略；保留计划和未来目标状态',
                        [(x,y,'同句相邻公共动作的省略主体')], 'published_strategy')
                    sr['policy_names']=['低排放发展战略']
                    facts.append(sr);covered.append((u,v))
            suffix='commentary' if rule=='ets_pilot' or re.match(r'[，,](?:预计|有望|分析师|专家认为)',full[max(u for _,u in covered):b]) else 'background'
            return self.partitions(old,full,facts,covered,suffix)
        # 相同谓词对应各自国家承诺；不把整个列举变成一个共同政策。
        m=PARALLEL.search(t)
        if m and not UNSAFE.search(t[:m.end()]):
            prefix=t[:m.start()]
            if not re.fullmatch(r'(?:我们不仅见证了|我们见证了|包括|此外[，,]?|\s)*',prefix):return [old]
            tail=t[m.end():]
            china=re.match(r'[，,]国家主席习近平',tail)
            if tail.strip('，,。；; ') and not (china and old['route'].startswith('main_') and old.get('countries')==['中国']):return [old]
            facts=[];covered=[]
            for cm in re.finditer(C,m['list']):
                ca=a+m.start('list')+cm.start();cb=a+m.start('list')+cm.end()
                pa,pb=a+m.start('claim'),a+m.end('claim')
                r=self.record(old,full,[(ca,cb),(pa,pb)],[country(cm.group())],'announced_goal',
                              '各国分别作出同一年份的碳中和承诺；拆出国家及共享原文谓词',
                              [(a+m.start(),a+m.end(),'并列主体共享谓词，非共同政策')], 'parallel_goals')
                r['event_type']='parallel_national_goal';facts.append(r);covered.extend([(ca,cb),(pa,pb)])
            if china:
                ca=a+m.end()+1
                r=self.record(old,full,[(ca,b)],['中国'],old.get('policy_state') or 'announced_goal',
                              '列举的外国目标与随后中国目标分开归属',rule='parallel_tail')
                if r['policy_state']=='unknown':r['policy_state']='announced_goal'
                facts.append(r);covered.append((ca,b))
            return self.partitions(old,full,facts,covered)
        return [old]
