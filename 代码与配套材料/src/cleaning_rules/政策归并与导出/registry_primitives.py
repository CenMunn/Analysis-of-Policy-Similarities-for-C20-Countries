import re,unicodedata
def norm(text):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',text)).casefold()

def goal_facts(text):
    facts={}
    for label,pattern in [('netzero','碳中和|净零排放|净零|零碳排放'),('peak','碳达峰|达到峰值|达峰')]:
        years=[]
        for m in re.finditer(pattern,text):
            before=re.findall(r'20\d\d|2100',text[max(0,m.start()-45):m.start()])
            after=re.findall(r'20\d\d|2100',text[m.end():m.end()+25])
            if before:years.append(before[-1])
            elif after:years.append(after[0])
        if years:facts[label+'_year']=sorted(set(years))
    return facts

def facts(row):
    text=unicodedata.normalize('NFKC',row['text'])
    result=goal_facts(text)
    sector='ev' if re.search(r'汽车|电动车|购车|每辆',text) else 'pv' if re.search(r'光伏|太阳能',text) else 'general'
    amounts=re.findall(r'(?:每辆|每台|每户|补贴|补助|补贴标准)[^。；;]{0,14}?(\d+(?:\.\d+)?)(亿元|万元|元|欧元|美元|英镑|韩元|日元)',text)
    if amounts:result['subsidy_'+sector]=sorted(set(a+b for a,b in amounts))
    budgets=re.findall(r'(?:拨款|投入|投资|预算)[^。；;]{0,12}?(\d+(?:\.\d+)?)(万亿|亿|万)?(美元|欧元|英镑|韩元|日元|元)',text)
    if budgets:result['budget_'+sector]=sorted(set(''.join(x) for x in budgets))
    ratios=re.findall(r'\d+(?:\.\d+)?\s*[%％]',text)
    if ratios:result['ratio_'+sector]=sorted(set(norm(x) for x in ratios))
    for m in re.finditer(r'发票|身份证|登记证|申请表|营业执照',text):
        result['requirement_'+m.group()]=['不要求' if re.search(r'不再要求|无需|免交',text[max(0,m.start()-12):m.start()]) else '要求']
    for name,obj in [('coal','燃煤电厂|煤电'),('nuclear','核电|核能'),('wind','海上风电|风电|风能'),('solar','光伏|太阳能'),('fossil_vehicle','燃油车|燃油汽车')]:
        directions=[]
        if re.search(r'(?:禁止|停止|不再|淘汰|退出|取消|关闭|退役).{0,14}(?:'+obj+')',text):directions.append('限制或退出')
        if re.search(r'(?:允许|鼓励|支持|发展|投资).{0,14}(?:'+obj+')',text):directions.append('允许或支持')
        if directions:result['direction_'+name]=sorted(set(directions))
    return result
