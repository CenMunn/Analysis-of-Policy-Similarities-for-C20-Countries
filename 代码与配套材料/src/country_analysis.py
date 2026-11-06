"""Country aggregation, missing-aware similarities, and grouped resampling.

Metadata rows align with matrix rows, have unique ``analysis_doc_id`` values,
and contain parsed lists in ``countries`` and ``resampling_groups``. Each text
is normalized before aggregation. A joint text is one observation referenced by
all its countries. Intersecting resampling-group labels form connected
components; absent labels create a unique component for that text.

``aggregate_country_vectors`` returns a dict with:
  countries: sorted country names from ALL metadata (also absent in a sample);
  vectors: dense float64 C x D L2-normalized means, NaN for invalid countries;
  valid_mask: bool C; counts: country -> count/weight/operational-flag dict;
  invalids: selected invalid rows with ID, reason, multiplicity;
  group_membership: ID -> stable component key; mode; exclude_multi.
Counts describe selected valid occurrences, unique texts and unique components.
``n_invalid_rows`` counts invalid selected occurrences. ``weight_sum`` sums
actual positive aggregation coefficients. The 10-text/5-group minimum is an
operational eligibility flag, never a statistical accuracy guarantee.

``selected_ids`` is a sequence, NOT a set: repeated IDs retain multiplicity.
``group_weights`` maps component keys (from group_membership) to nonnegative
multipliers; omitted keys get zero when a mapping is supplied. In group_equal
mode each component's mean has its multiplier as weight, while repeated IDs
still affect that component's mean. These multipliers preserve component draw
multiplicity during the grouped bootstrap.
"""

from collections import Counter, defaultdict
import csv
from pathlib import Path

import numpy as np
from scipy import sparse

EPS = 1e-10


def _true(value):
    return value if isinstance(value, (bool, np.bool_)) else str(value).strip().lower() in {'1', 'true', 'yes'}


def _prepare(vectors, metadata):
    matrix = sparse.csr_matrix(vectors, dtype=np.float64) if sparse.issparse(vectors) else np.asarray(vectors, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] != len(metadata):
        raise ValueError('vectors must be a 2-D matrix aligned with metadata')
    ids = [str(row['analysis_doc_id']) for row in metadata]
    if len(set(ids)) != len(ids):
        raise ValueError('analysis_doc_id values must be unique')
    countries = []
    parents = list(range(len(ids)))

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    owners = {}
    for i, row in enumerate(metadata):
        country = row.get('countries', [])
        groups = row.get('resampling_groups', [])
        if not isinstance(country, (list, tuple)) or not isinstance(groups, (list, tuple)):
            raise ValueError('countries and resampling_groups must be parsed lists')
        countries.append(sorted({str(x) for x in country if str(x).strip()}))
        for group in set(map(str, groups)):
            if group in owners:
                a, b = find(i), find(owners[group])
                parents[max(a, b)] = min(a, b)
            else:
                owners[group] = i
    members = defaultdict(list)
    for i, identifier in enumerate(ids):
        members[find(i)].append(identifier)
    keys = {root: 'component:' + min(values) for root, values in members.items()}
    membership = {identifier: keys[find(i)] for i, identifier in enumerate(ids)}
    # Inspect CSR data per row without densifying a text-by-vocabulary matrix.
    if sparse.issparse(matrix):
        matrix.sum_duplicates()
        finite = np.array([np.isfinite(matrix.data[matrix.indptr[i]:matrix.indptr[i + 1]]).all()
                           for i in range(matrix.shape[0])])
        safe = matrix.copy()
        safe.data[~np.isfinite(safe.data)] = 0
        norms = np.sqrt(np.asarray(safe.multiply(safe).sum(axis=1)).ravel())
    else:
        finite = np.isfinite(matrix).all(axis=1)
        safe = np.where(np.isfinite(matrix), matrix, 0)
        norms = np.linalg.norm(safe, axis=1)
    reasons = []
    for i, row in enumerate(metadata):
        if not _true(row.get('has_content', True)):
            reason = 'empty_content'
        elif not finite[i] or not np.isfinite(norms[i]):
            reason = 'nonfinite_vector'
        elif norms[i] <= EPS:
            reason = 'zero_vector'
        elif not countries[i]:
            reason = 'no_country'
        else:
            reason = None
        reasons.append(reason)
    valid = np.array([reason is None for reason in reasons])
    inverse = np.zeros(len(ids))
    inverse[valid] = 1 / norms[valid]
    unit = sparse.diags(inverse) @ safe if sparse.issparse(safe) else safe * inverse[:, None]
    return dict(unit=unit, ids=ids, countries=countries, membership=membership, reasons=reasons)


def _aggregate(prepared, selected_ids, group_weights, mode, exclude_multi):
    if mode not in {'text_equal', 'group_equal'}:
        raise ValueError('mode must be text_equal or group_equal')
    ids = prepared['ids']
    indices = {identifier: i for i, identifier in enumerate(ids)}
    occurrences = Counter(ids if selected_ids is None else map(str, selected_ids))
    unknown = set(occurrences) - set(indices)
    if unknown:
        raise KeyError('unknown selected IDs: ' + ', '.join(sorted(unknown)))
    membership = prepared['membership']
    if group_weights is not None:
        for value in group_weights.values():
            if not np.isfinite(value) or value < 0:
                raise ValueError('group weights must be finite and nonnegative')
    present = {country for row in prepared['countries'] for country in row}
    country_names = prepared.get('country_universe')
    if country_names is None:
        country_names = sorted(present)
    elif len(set(country_names)) != len(country_names) or present - set(country_names):
        raise ValueError('country_universe must be unique and include every observed country')
    country_index = {country: i for i, country in enumerate(country_names)}
    included = defaultdict(list)
    invalids = []
    invalid_counts = Counter()
    for identifier, multiplicity in occurrences.items():
        i = indices[identifier]
        countries = prepared['countries'][i]
        if exclude_multi and len(countries) > 1:
            continue
        group = membership[identifier]
        multiplier = 1. if group_weights is None else float(group_weights.get(group, 0))
        if multiplier == 0:
            continue
        reason = prepared['reasons'][i]
        if reason:
            invalids.append(dict(analysis_doc_id=identifier, reason=reason, multiplicity=multiplicity))
            invalid_counts.update({country: multiplicity for country in countries})
            continue
        for country in countries:
            included[country].append((i, identifier, group, multiplicity, multiplier))
    rr, cc, values = [], [], []
    counts = {}
    for country in country_names:
        rows = included[country]
        group_sizes = Counter()
        for _, _, group, multiplicity, _ in rows:
            group_sizes[group] += multiplicity
        weight_sum = 0.
        for i, _, group, multiplicity, multiplier in rows:
            weight = multiplicity * multiplier
            if mode == 'group_equal':
                weight /= group_sizes[group]
            rr.append(country_index[country])
            cc.append(i)
            values.append(weight)
            weight_sum += weight
        n_unique = len(rows)
        n_groups = len(group_sizes)
        counts[country] = dict(n_rows=sum(row[3] for row in rows), n_unique_texts=n_unique,
                               n_groups=n_groups, n_multi_rows=sum(row[3] for row in rows if len(prepared['countries'][row[0]]) > 1),
                               n_invalid_rows=invalid_counts[country], weight_sum=weight_sum,
                               meets_operational_minimum=n_unique >= 10 and n_groups >= 5)
    coefficients = sparse.csr_matrix((values, (rr, cc)), shape=(len(country_names), len(ids)))
    means = coefficients @ prepared['unit']
    means = means.toarray() if sparse.issparse(means) else np.asarray(means)
    norms = np.linalg.norm(means, axis=1)
    valid_mask = np.isfinite(norms) & (norms > EPS)
    means[valid_mask] /= norms[valid_mask, None]
    means[~valid_mask] = np.nan
    return dict(countries=country_names, vectors=means, valid_mask=valid_mask,
                counts=counts, invalids=invalids, group_membership=dict(membership),
                mode=mode, exclude_multi=bool(exclude_multi))


def aggregate_country_vectors(vectors, metadata, selected_ids=None, group_weights=None,
                              mode='text_equal', exclude_multi=False, country_universe=None):
    """Aggregate normalized text vectors with explicit sample multiplicities."""
    prepared = _prepare(vectors, metadata)
    if country_universe is not None:
        prepared['country_universe'] = list(country_universe)
    return _aggregate(prepared, selected_ids, group_weights, mode, exclude_multi)


def cosine_country_matrix(result):
    """Return C x C cosines; unavailable countries retain NaN, including diagonal."""
    matrix = result['vectors'] @ result['vectors'].T
    return np.clip(matrix, -1., 1.)


def rank_country_similarities(result):
    """Finite neighbors, descending cosine; ties use country-name lexical order."""
    matrix = cosine_country_matrix(result)
    countries = result['countries']
    records = []
    for i, country in enumerate(countries):
        neighbors = [(countries[j], float(matrix[i, j])) for j in range(len(countries))
                     if i != j and np.isfinite(matrix[i, j])]
        neighbors.sort(key=lambda x: (-x[1], x[0]))
        records.extend(dict(country=country, neighbor=neighbor, rank=rank, cosine=value)
                       for rank, (neighbor, value) in enumerate(neighbors, 1))
    return records


def export_country_outputs(result, out_dir):
    """Write UTF-8 BOM CSV files. Missing similarities are blank, never zero."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {key: directory / name for key, name in dict(similarities='country_cosine.csv',
             ranks='country_ranks.csv', stats='country_stats.csv').items()}
    with paths['similarities'].open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['country', *result['countries']])
        for country, row in zip(result['countries'], cosine_country_matrix(result)):
            writer.writerow([country, *[float(value) if np.isfinite(value) else '' for value in row]])
    with paths['ranks'].open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['country', 'neighbor', 'rank', 'cosine'])
        writer.writeheader()
        writer.writerows(rank_country_similarities(result))
    fields = ['country', 'valid', 'n_rows', 'n_unique_texts', 'n_groups', 'n_multi_rows',
              'n_invalid_rows', 'weight_sum', 'meets_operational_minimum']
    with paths['stats'].open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for country, valid in zip(result['countries'], result['valid_mask']):
            writer.writerow(dict(country=country, valid=bool(valid), **result['counts'][country]))
    return {key: str(path) for key, path in paths.items()}


def grouped_bootstrap(vectors, metadata, n_repeats=200, seed=42, mode='text_equal',
                      exclude_multi=False, selected_ids=None, country_universe=None):
    """Resample global connected components with replacement, retaining all texts.

    All members of a component move together, including shared joint texts.
    Each replicate draws G components from the G eligible components. Invalid
    country pairs are NaN; percentile summaries use only finite replicates and
    report their count. These are descriptive resampling intervals, with no
    claim of calibrated coverage or reliability for small country samples.
    """
    if not isinstance(n_repeats, (int, np.integer)) or n_repeats < 1:
        raise ValueError('n_repeats must be a positive integer')
    prepared = _prepare(vectors, metadata)
    if country_universe is not None:
        prepared['country_universe'] = list(country_universe)
    selected_ids = None if selected_ids is None else list(selected_ids)
    base = _aggregate(prepared, selected_ids, None, mode, exclude_multi)
    allowed = set(prepared['ids'] if selected_ids is None else map(str, selected_ids))
    groups = sorted({prepared['membership'][identifier] for i, identifier in enumerate(prepared['ids'])
                     if identifier in allowed and prepared['reasons'][i] is None
                     and not (exclude_multi and len(prepared['countries'][i]) > 1)})
    size = len(base['countries'])
    samples = np.full((n_repeats, size, size), np.nan)
    rng = np.random.default_rng(seed)
    if groups:
        for repeat in range(n_repeats):
            draws = Counter(rng.choice(groups, size=len(groups), replace=True))
            result = _aggregate(prepared, selected_ids, draws, mode, exclude_multi)
            samples[repeat] = cosine_country_matrix(result)
    lower, median, upper = (np.full((size, size), np.nan) for _ in range(3))
    n_valid = np.isfinite(samples).sum(axis=0)
    for i in range(size):
        for j in range(size):
            finite = samples[:, i, j][np.isfinite(samples[:, i, j])]
            if len(finite):
                lower[i, j], median[i, j], upper[i, j] = np.percentile(finite, [2.5, 50, 97.5])
    return dict(countries=base['countries'], samples=samples, lower=lower, median=median,
                upper=upper, n_valid=n_valid, n_repeats=n_repeats, seed=seed)


"""Teacher's six buckets, based on corrected policy countries rather than folder attribution."""
import numpy as np
GROUPS={'德意':['德国','意大利'],'法国':['法国'],'美国':['美国'],
        '日韩沙特印尼':['日本','韩国','沙特阿拉伯','印度尼西亚'],'英国':['英国'],'中国汇总':['中国']}

def remap_metadata(docs):
    mapping={c:g for g,cs in GROUPS.items() for c in cs}
    return [dict(d,member_countries=list(d['countries']),countries=sorted({mapping[c] for c in d['countries'] if c in mapping})) for d in docs]

def member_equal(vectors,countries):
    v=np.asarray(vectors,dtype=float);names=list(countries);groups=list(GROUPS)
    pooled=np.full((len(groups),v.shape[1]),np.nan);members=[]
    for i,g in enumerate(groups):
        selected=[names.index(c) for c in GROUPS[g] if c in names and np.isfinite(v[names.index(c)]).all() and np.linalg.norm(v[names.index(c)])>1e-10]
        members.append([names[j] for j in selected])
        if selected:
            unit=v[selected]/np.linalg.norm(v[selected],axis=1)[:,None];mean=unit.mean(0);norm=np.linalg.norm(mean)
            if norm>1e-10:pooled[i]=mean/norm
    return dict(groups=groups,vectors=pooled,similarity=pooled@pooled.T,members=members)


def read_vectors(output,unit,view,method,k='all'):
    root=Path(output)
    return sparse.load_npz(root/f'02_分词与TFIDF/{unit}/{view}/TFIDF_{k}.npz') if method=='TFIDF' else np.load(root/f'03_词向量/{unit}/{view}/{method}_{k}.npy')


def top3(mat,names,pool):
    return {names[i]:[names[j] for j in sorted([j for j in pool if j!=i and np.isfinite(mat[i,j])],
                  key=lambda j:(-mat[i,j],names[j]))[:3]] for i in pool}


def run_countries(output):
    """第四部分：来源组等权国家/六组聚合及固定范围敏感性。"""
    from .common import ROOT,read_json,parse_docs,write_json,write_csv
    out=Path(output);countries=read_json(ROOT/'config.json')['country_universe']
    matrices={};long=[];coverage=[];ranks=[];effects=[];rankchanges=[];kchanges=[];representatives=[]
    methods=['TFIDF','FastText','BGE_complete','FastText_center']
    for unit in ['article_policy','event']:
      for view in ['main','main_extended']:
        docs=parse_docs(out/f'02_分词与TFIDF/{unit}/{view}/元数据.csv')
        gc=defaultdict(set)
        for d in docs:
            for g in d['resampling_groups']:gc[g].update(d['countries'])
        nonshared=[d['analysis_doc_id'] for d in docs if all(len(gc[g])==1 for g in d['resampling_groups'])]
        for method in methods:
          for k in ([50,100,200,'all'] if method in ['TFIDF','FastText'] else ['all']):
            x=read_vectors(out,unit,view,method,k)
            cr=aggregate_country_vectors(x,docs,mode='group_equal',country_universe=countries)
            for scheme,names,md in [('国家',countries,docs),('老师六组',list(GROUPS),remap_metadata(docs))]:
                ar=cr if scheme=='国家' else aggregate_country_vectors(x,md,mode='group_equal',country_universe=names)
                mat=cosine_country_matrix(ar);matrices[unit,view,method,str(k),scheme]=mat
                pool=[i for i in range(len(names)) if np.isfinite(mat[i,i])]
                for i,c in enumerate(names):
                    if k=='all':coverage.append(dict(unit=unit,view=view,method=method,scheme=scheme,country=c,**ar['counts'][c]))
                    for j,n in enumerate(names):long.append(dict(unit=unit,view=view,method=method,K=k,scheme=scheme,country=c,neighbor=n,
                        cosine=float(mat[i,j]) if np.isfinite(mat[i,j]) else None))
                for c,ns in top3(mat,names,pool).items():
                    ranks.extend(dict(unit=unit,view=view,method=method,K=k,scheme=scheme,country=c,neighbor=n,rank=i+1,cosine=float(mat[names.index(c),names.index(n)])) for i,n in enumerate(ns))
                if k=='all':
                    alts={'text_equal':cosine_country_matrix(aggregate_country_vectors(x,md,mode='text_equal',country_universe=names)),
                          'no_shared_sources':cosine_country_matrix(aggregate_country_vectors(x,md,selected_ids=nonshared,mode='group_equal',country_universe=names))}
                    if scheme=='老师六组':alts['member_country_equal']=member_equal(cr['vectors'],countries)['similarity']
                    for variant,m in alts.items():
                        effects.extend(dict(unit=unit,view=view,method=method,scheme=scheme,variant=variant,country=c,neighbor=n,
                            baseline=float(mat[i,j]) if np.isfinite(mat[i,j]) else None,alternative=float(m[i,j]) if np.isfinite(m[i,j]) else None)
                            for i,c in enumerate(names) for j,n in enumerate(names))
            if unit=='article_policy' and k=='all' and method in ['TFIDF','BGE_complete']:
                for ci,c in enumerate(countries):
                    if not cr['valid_mask'][ci]:continue
                    scores=np.asarray(x@cr['vectors'][ci]).ravel();candidates=[i for i,d in enumerate(docs) if d['has_content'] and c in d['countries']]
                    selected=[];used=set()
                    for i in sorted(candidates,key=lambda i:(-scores[i],docs[i]['analysis_doc_id'])):
                        if used.intersection(docs[i]['resampling_groups']):continue
                        selected.append(i);used.update(docs[i]['resampling_groups'])
                        if len(selected)==2:break
                    for i in selected:representatives.append(dict(view=view,method=method,country=c,analysis_doc_id=docs[i]['analysis_doc_id'],
                        cosine_to_centroid=float(scores[i]),text=docs[i]['text'],event_ids=docs[i]['event_ids'],sources=docs[i]['source_ids']))
    for unit in ['article_policy','event']:
      for scheme,names in [('国家',countries),('老师六组',list(GROUPS))]:
       for method in methods:
        for view in ['main','main_extended']:
            full=matrices[unit,view,method,'all',scheme];pool=[i for i in range(len(names)) if np.isfinite(full[i,i])]
            b=top3(full,names,pool)
            for k in ([50,100,200,'all'] if method in ['TFIDF','FastText'] else ['all']):
                m=matrices[unit,view,method,str(k),scheme];t=top3(m,names,pool)
                delta=[abs(m[i,j]-full[i,j]) for i in pool for j in pool if i<j]
                kchanges.append(dict(unit=unit,view=view,scheme=scheme,method=method,K=k,common_countries=len(pool),
                    mean_abs_cosine_change=float(np.mean(delta)),max_abs_cosine_change=float(max(delta)),
                    neighbor_memberships_changed=sum(set(b[c])!=set(t[c]) for c in b),neighbor_orders_changed=sum(b[c]!=t[c] for c in b)))
        a=matrices[unit,'main',method,'all',scheme];b=matrices[unit,'main_extended',method,'all',scheme]
        pool=[i for i in range(len(names)) if np.isfinite(a[i,i]) and np.isfinite(b[i,i])]
        aa=top3(a,names,pool);bb=top3(b,names,pool)
        rankchanges.extend(dict(unit=unit,scheme=scheme,method=method,country=c,before=aa[c],after=bb[c],
                                common_candidates=[names[i] for i in pool],membership_changed=set(aa[c])!=set(bb[c]),order_changed=aa[c]!=bb[c]) for c in aa)
    for name,rows in [('相似度矩阵',long),('国家覆盖',coverage),('前三近邻',ranks),('聚合与共享来源对照',effects),
                      ('K相似度变化',kchanges),('主集扩展近邻变化',rankchanges),('代表原文',representatives)]:
        write_csv(out/f'04_国家关系/{name}.csv',rows)
    write_json(out/'04_国家关系/阶段摘要.json',dict(matrix_records=len(long),teacher_groups=GROUPS,
        aggregation='source_group_equal',missing='空值，不是零相似度',meaning='历史文本主题与措施表述接近，不是国家政策一致率'))
    run_periods(out)

def run_periods(output):
    """只对已有逐条回源日期参考仍适用的事件作时期对照。"""
    import json
    from .common import ROOT,read_csv,read_json,parse_docs,write_csv,write_json
    out=Path(output);dates=read_csv(ROOT/'resources/evaluation/日期证据.csv')
    source=out/'01_数据清洗/最终分析输入';index={r['file_id']:r for r in read_csv(source/'追溯/来源索引.csv')}
    texts={k:(source/r['normalized_text_file']).read_text(encoding='utf-8-sig') for k,r in index.items()}
    for r in dates:
        for p in json.loads(r['source_spans']):assert texts[p['file_id']][int(p['start']):int(p['end'])]==p['text']
    year={r['event_id']:int(r['year']) for r in dates};period=lambda y:'2015及以前' if y<=2015 else '2016-2020' if y<=2020 else '2021及以后'
    country_names=read_json(ROOT/'config.json')['country_universe'];counts=[];matrices=[]
    for view in ['main','main_extended']:
        ds=parse_docs(out/f'02_分词与TFIDF/event/{view}/元数据.csv')
        for method in ['TFIDF','FastText','BGE_complete']:
            x=read_vectors(out,'event',view,method)
            for bucket in ['2015及以前','2016-2020','2021及以后']:
                selected=[d['analysis_doc_id'] for d in ds if d['event_ids'] and d['event_ids'][0] in year and period(year[d['event_ids'][0]])==bucket]
                for scheme,names,docs in [('国家',country_names,ds),('老师六组',list(GROUPS),remap_metadata(ds))]:
                    a=aggregate_country_vectors(x,docs,selected_ids=selected,mode='group_equal',country_universe=names);m=cosine_country_matrix(a)
                    for i,c in enumerate(names):
                        counts.append(dict(view=view,method=method,period=bucket,scheme=scheme,country=c,**a['counts'][c]))
                        for j,n in enumerate(names):matrices.append(dict(view=view,method=method,period=bucket,scheme=scheme,country=c,neighbor=n,cosine=float(m[i,j]) if np.isfinite(m[i,j]) else None))
    write_csv(out/'04_国家关系/时期子集覆盖.csv',counts);write_csv(out/'04_国家关系/时期子集相似度.csv',matrices)
    write_json(out/'04_国家关系/日期范围说明.json',dict(reference_events=len(year),source_spans_checked=True,
        label_origin='历史回源辅助参考，非独立真人验收',periods=['≤2015','2016—2020','≥2021'],
        limitation='日期角色见原表，不能把目标年份当实施年；子集不代表整批，主体与文本变更后未重新核对者不继承。'))
