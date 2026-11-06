"""可追溯日期和政策文件登记。只丰富属性，不更改内容纳入、国家或原文状态。"""
import datetime, re, unicodedata, itertools
from collections import defaultdict, Counter
from ..公共工具.identifiers import ident
from ..政策归并与导出.registry_primitives import norm
from ..公共工具.io_utils import write_csv, write_json

DATE=re.compile(r'(?<![0-9０-９])([12１２][0-9０-９]{3})(?:年|[-/])(?:([0-9０-９]{1,2})(?:月|[-/])(?:([0-9０-９]{1,2})日?)?)?')
REL=re.compile(r'(?:今年|明年|去年|次年|当年|当天|同年)(?:[0-9０-９]{1,2}月(?:[0-9０-９]{1,2}日)?)?|(?<![0-9年])(?:[0-9]{1,2}月[0-9]{1,2}日)')
PUB=r'发布|公布|通过|签署|批准|宣布|颁布|制定|出台|修订'
IMPLEMENT=r'实施|生效|施行|执行'
POLICY=r'(?:法律|法案|条例|办法|规划|战略|行动计划|政策|计划|行政命令|规则|规定|协定|议定书|联合声明|倡议|纲要|意见|方案|标准|指令|基本方针|公约|法)(?:[（(][^()（）]*[)）])?$'

def extract_dates(text,reports):
    mentions=[];warnings=[];periods=[]
    for m in re.finditer(r'([12][0-9]{3})[—–\-至]([12][0-9]{3})年',text):
        periods.append(dict(start=m.start(),end=m.end(),text=m.group(),start_year=int(m[1]),end_year=int(m[2]),status='原文年份范围，未强制认定实施期间'))
    for m in DATE.finditer(text):
        y,mo,day=[int(unicodedata.normalize('NFKC',s)) if s else None for s in m.groups()]
        if not 1900<=y<=2199:continue
        try:
            if mo is not None and not 1<=mo<=12:raise ValueError()
            if day is not None:datetime.date(y,mo,day)
        except ValueError:
            warnings.append(dict(text=m.group(),start=m.start(),reason='无效日历日期，不写结构化日期'));continue
        value=f'{y:04d}'+(f'-{mo:02d}' if mo else '')+(f'-{day:02d}' if day else '')
        left=re.split('[。；，,!?！？]',text[:m.start()])[-1][-35:]
        right=re.split('[。；，,!?！？]',text[m.end():])[0][:30]
        role='unresolved';reason='日期与政策动作关系不足'
        if any(p['start']<=m.start()<p['end'] for p in periods):role='policy_period';reason='原文年份范围'
        elif re.search(r'(?:相?较(?:于)?|比|以)\s*$',left) and re.search(r'减少|降低|增长|下降|增加|基准|为基',right):role='baseline';reason='比较基准年，不是目标年'
        elif re.search(r'(?:到|至|截至|力争|目标(?:是|为)?|定在|定于|计划到|最迟(?:于)?)\s*$',left) and not re.search(PUB+'|'+IMPLEMENT,right[:10]):role='target';reason='显式截止、目标或时间表'
        elif re.match(r'(?:前|之前|底|末|左右|目标|\s*(?:实现|达到|达成|建成|成为|禁止|禁售|淘汰|关闭|退出))',right):role='target';reason='目标完成或截止表达'
        elif re.search(r'目标|承诺',text[max(0,m.start()-70):m.start()]) and re.search(r'减少|下降|降低|增加|超过|占比|产销量',right) and not re.search(PUB,right[:12]):role='target';reason='同一目标条款的并列指标年份'
        elif re.match(r'[^0-9]{0,16}(?:暂缓|暂停|废止|废除|撤销|取消|叫停)',right):role='state_change';reason='暂停、撤销等动作日期，不当作实施日期'
        elif re.match(r'(?:起|开始|正式|首次|即|将|全面|\s|的){0,8}(?:'+IMPLEMENT+')',right) or re.match(r'起在[^0-9]{0,18}(?:'+IMPLEMENT+')',right):
            planned=bool(re.search(r'将于|将从|拟于|计划于|预计于|有望于|如(?:果)?[^。；]{0,12}$',left))
            role='scheduled_implementation' if planned else 'implementation';reason='将来/条件生效安排' if planned else '原文明确实施/生效动作'
        elif re.match(r'(?:首次|正式|新|修订|重新|\s|的){0,8}(?:'+PUB+')',right) or re.search(r'(?:'+PUB+r')\s*(?:于|时间为)?\s*$',left):
            tentative=bool(re.search(r'将于|拟于|计划于|预计于|如果[^。；]{0,12}$',left))
            role='scheduled_decision' if tentative else 'decision';reason='未来发布安排' if tentative else '原文日期紧邻公布/通过动作'
        elif text[m.end():].startswith(('，',',')):
            next_clause=re.split('[。；，,]',text[m.end()+1:])[0][:35]
            if re.match(r'[^0-9]{0,25}(?:'+PUB+')',next_clause) and not re.search('报道|电讯|消息|预计|有望|如果|将于',next_clause):role='decision';reason='日期状语跨一个逗号直接修饰发布/通过动作'
        if role=='decision' and re.search(r'(?:公布|发布|通过)的第[0-9一二三四五六七八九十]+版',right):role='referenced_decision';reason='被比较旧版的发布年份，不写本条当前决定日期'
        roles=[role]
        if role=='decision' and re.match(r'(?:通过|公布|颁布)并(?:已)?生效',right):roles.append('implementation')
        mentions.append(dict(start=m.start(),end=m.end(),text=m.group(),value=value,role=role,roles=roles,precision='day' if day else 'month' if mo else 'year',basis=reason,context=text[max(0,m.start()-45):min(len(text),m.end()+45)]))
    def single(role):
        vals=sorted({m['value'] for m in mentions if role in m['roles']})
        # 嵌套精度可一致化；两个不同日期不能取第一条。
        maximal=[x for x in vals if not any(y.startswith(x+'-') for y in vals)]
        if len(maximal)>1:warnings.append(dict(role=role,values=vals,reason='多个不同日期，留空待角色/版本核对'))
        return maximal[0] if len(maximal)==1 else ''
    reports_out=[]
    for raw in reports:
        m=re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:\D|$)',raw or '')
        if m:
            try:reports_out.append(datetime.date(*map(int,m.groups())).isoformat())
            except ValueError:warnings.append(dict(text=raw,reason='无效报道日期'))
    rel=[dict(start=m.start(),end=m.end(),text=m.group(),resolved_value='',reason='缺显式原文年份，未用报道年份推造') for m in REL.finditer(text) if not any(d['start']<=m.start()<d['end'] for d in mentions)]
    return dict(report_dates=sorted(set(reports_out)),decision_date=single('decision'),implementation_date=single('implementation'),scheduled_implementation_date=single('scheduled_implementation'),scheduled_decision_date=single('scheduled_decision'),state_change_date=single('state_change'),target_years=sorted({int(x['value'][:4]) for x in mentions if x['role']=='target'}),date_evidence=mentions,relative_dates=rel,policy_periods=periods,date_warnings=warnings,date_extraction_status='程序按原文角色提取，非独立人工日期核验')

def identity_candidates(text,countries,names):
    found=[]
    for m in re.finditer(r'《([^》]{2,90})》|[“「]([^”」]{2,90})[”」]',text):
        name=m[1] or m[2];a,b=m.span(1 if m[1] else 2)
        if re.search(POLICY,name) and not re.search(r'时报|日报|杂志|新闻|[《》。，；：！？]',name):found.append((a,b,name))
    # 外层引语不能遮住内嵌《文件名》。
    for m in re.finditer(r'《([^》]{2,90})》',text):
        if re.search(POLICY,m[1]) and not any(a==m.start(1) and b==m.end(1) for a,b,_ in found):found.append((m.start(1),m.end(1),m[1]))
    for name in names:
        if not re.search(POLICY,name):continue
        for m in re.finditer(re.escape(name),text):
            if not any(a<=m.start() and m.end()<=b for a,b,_ in found):found.append((m.start(),m.end(),name))
    result=[]
    for a,b,name in sorted(set(found)):
        before=text[max(0,a-45):a];after=text[b:b+24]
        left=re.split('[。；，,]',before)[-1];right=re.split('[。；，,]',after)[0]
        role='mentioned_policy';why='仅具名提及，未据此认定本次发布'
        if re.search(r'(?:依据|根据|依照|按照|现有的?|实施现有的?)《?$',left):role='legal_basis';why='上位法或现有依据'
        elif re.search(r'(?:撤销|废除|废止|取代|替代|修改|重新审核|推翻|暂停|叫停)[^。；，]{0,18}$',left):role='affected_policy';why='被修改、替代或撤销对象'
        elif re.search(PUB,left) or re.match(r'[》”」）)]{0,3}(?:于.{0,15})?(?:发布|公布|通过|生效|要求|提出|规定|设定)',right):role='current_instrument';why='与发布/文件规定动作相接，仍须核对主体范围'
        versions=list(re.finditer(r'第[0-9一二三四五六七八九十]+版',before))
        version=versions[-1].group() if versions and len(before)-versions[-1].end()<=5 else ''
        # 括号/空格差异规范化；不自动把译名或语义相近文件合并。
        canonical=unicodedata.normalize('NFKC',name).strip()
        global_treaty=canonical in ['巴黎协定','京都议定书','联合国气候变化框架公约']
        if global_treaty:role='international_framework';why='国际框架本身不同于各国批准、履约或退出事件'
        family_scope=('international',) if global_treaty else tuple(sorted(countries))
        family_id=ident('FAMILY-',(family_scope,norm(canonical)))
        alias_of=''
        if len(name)<=3 and re.search(r'(?:简称|下称)《?$',before):
            prior=[x for x in result if x['end']<a and len(x['name'])>3]
            if prior and not re.search('[。；]',text[prior[-1]['end']:a]):
                alias_of=prior[-1]['name'];canonical=prior[-1]['canonical_name'];family_id=prior[-1]['family_id']
        result.append(dict(name=name,canonical_name=canonical,start=a,end=b,role=role,role_reason=why,version=version,countries=countries,family_id=family_id,alias_of=alias_of,identity_verified=False,basis='原文明示局部简称→'+alias_of if alias_of else '具名国际框架关联' if global_treaty else '同国家与完整具名字符串的家族候选；非独立政策认定'))
    return result

def version_links(a,b,name):
    if sorted(a['countries'])!=sorted(b['countries']):return None
    digits=lambda r:set(re.findall(r'\d+(?:\.\d+)?(?:[%％]|万|亿|年)',unicodedata.normalize('NFKC',r['policy_fact'])))
    if a['policy_state']!=b['policy_state']:rel='different_state_keep_both'
    elif digits(a)!=digits(b):rel='possible_substantive_revision'
    elif norm(a['policy_fact'])==norm(b['policy_fact']):rel='same_text_different_context_candidate'
    else:rel='complementary_or_duplicate_candidate'
    return dict(from_record=a['event_record_id'],to_record=b['event_record_id'],policy_name=name,relation=rel,chronological_order_confirmed=False,independently_verified=False,merge_performed=False,reason='只建立可复核关联，不按相似度或时间邻近强行归并')

def enrich_records(rows):
    for r in rows:
        r['legacy_policy_id']=r.get('policy_id','');r['legacy_version_id']=r.get('version_id','')
        r.update(extract_dates(r['policy_fact'],[s.get('reported_at','') for s in r['sources']]))
        candidates=identity_candidates(r['policy_fact'],r['countries'],[r['policy_name']] if r.get('policy_name') else [])
        r['policy_identity_candidates']=candidates
        active=[x for x in candidates if x['role']=='current_instrument' and not x['alias_of']]
        chosen=active[0] if len(active)==1 else candidates[0] if len(candidates)==1 and candidates[0]['role']=='mentioned_policy' and len(candidates[0]['name'])>3 else None
        if chosen:
            r['policy_id']=chosen['family_id'];r['policy_name']=chosen['canonical_name'];r['version_label']=chosen['version']
            r['identity_status']='同国家具名家族候选，未做独立政策身份确认'
        else:
            r['policy_id']=ident('UNRESOLVED-',r['event_record_id']);r['policy_name']='';r['version_label']=''
            r['identity_status']='多角色文件/仅法律依据/未具名，保留事件占位'
        r['version_id']=ident('VERSION-',(r['event_record_id'],r['version_label'],r['policy_state']))
        r['version_verification_status']='逐事件保留，家族不同状态/目标仅关联，未证明版本先后'
    return rows

def export_registry(out,rows):
    families=defaultdict(list);mentions=[];dates=[];relative=[];warnings=[];edges=[]
    for r in rows:
        for x in r['policy_identity_candidates']:
            mentions.append(dict(event_record_id=r['event_record_id'],**x))
            families[x['family_id']].append((r,x))
        for d in r['date_evidence']:dates.append(dict(event_record_id=r['event_record_id'],**d))
        for d in r['relative_dates']:relative.append(dict(event_record_id=r['event_record_id'],**d))
        for d in r['date_warnings']:warnings.append(dict(event_record_id=r['event_record_id'],**d))
    for family,rs in sorted(families.items()):
        unique={r['event_record_id']:r for r,x in rs};us=list(unique.values())
        # 相邻只是输出所有有根据家族成员的稀疏复核链，不声称时间顺序。
        for a,b in zip(us,us[1:]):
            edge=version_links(a,b,rs[0][1]['canonical_name'])
            if edge:
                roles_a=sorted({x['role'] for r,x in rs if r['event_record_id']==a['event_record_id']})
                roles_b=sorted({x['role'] for r,x in rs if r['event_record_id']==b['event_record_id']})
                if 'international_framework' in roles_a+roles_b:edge['relation']='common_framework_not_same_domestic_policy'
                elif 'legal_basis' in roles_a+roles_b:edge['relation']='shared_legal_basis_not_policy_identity'
                edges.append(dict(family_id=family,from_document_roles=roles_a,to_document_roles=roles_b,**edge))
    directory=out/'政策归并与版本'
    write_csv(directory/'文件角色与身份候选.csv',mentions)
    write_csv(directory/'具名家族候选.csv',[dict(family_id=f,name=rs[0][1]['canonical_name'],mentioned_countries=sorted({c for r,x in rs for c in r['countries']}),scope='international_framework' if any(x['role']=='international_framework' for r,x in rs) else 'country_scoped_document_candidate',event_record_ids=sorted({r['event_record_id'] for r,x in rs}),source_documents=len({s['file_id'] for r,x in rs for s in r['sources']}),identity_verified=False,independent_policy_count='') for f,rs in sorted(families.items())])
    write_csv(directory/'版本核验候选关系.csv',edges)
    write_csv(directory/'日期字面证据.csv',dates)
    write_csv(directory/'相对日期待核.csv',relative)
    write_csv(directory/'日期冲突与无效值.csv',warnings)
    return dict(algorithm='registry6.11',records=len(rows),date_fields={k:sum(bool(r[k]) for r in rows) for k in ['report_dates','decision_date','implementation_date','scheduled_implementation_date','target_years']},named_family_candidates=len(families),file_role_mentions=len(mentions),version_candidate_edges=len(edges),relative_dates=len(relative),date_warnings=len(warnings),identity_independently_verified=0,independent_policy_count=None,content_decisions_changed=False)
