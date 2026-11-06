import re
def _refinement_clean(result):
    text = result['clean_text']
    logs = list(result['removal_log'])
    def remove(begin, end, rule):
        nonlocal text
        logs.append({'rule': rule, 'stage_start': begin, 'stage_end': end,
                     'removed_chars': end-begin, 'removed_text': text[begin:end]})
        text = text[:begin] + text[end:]
    prefix = re.match(r'\s*登录人民网通行证\s*立即注册', text)
    if prefix:
        remove(prefix.start(), prefix.end(), 'people_login_controls')
    controls = r'用微信扫描二维码分享至好友和朋友圈|扫一扫\s*手机快速访问'
    for match in reversed(list(re.finditer(controls, text))):
        remove(match.start(),match.end(),'exact_share_or_scan_controls')
    # 仅依据已核验的模板组合定位边界，不把孤立关键词当作文章结束。
    patterns = [
        (r'分享让更多人看到\s*推荐阅读', 'people_recommendation_footer'),
        (r'[|｜]相关专题[|｜]', 'people_topic_navigation_footer'),
        (r'微信[“\"]扫一扫[”\"]添加[“\"](?:学习大国|党史学习教育|人民党建云)[”\"]', 'people_wechat_footer'),
        (r'(?:经济参考报社|光明网|光明日报社)版权所有', 'publisher_copyright_footer'),
        (r'(?:免责声明[：:丨|]|【免责声明】)', 'disclaimer_footer'),
        (r'版权声明[：:]', 'copyright_statement_footer'),
        (r'官方微博\s*微信公众号[：:]', 'publisher_weibo_wechat_footer'),
        (r'[©Ⓒ]\s*版权所有', 'copyright_symbol_footer'),
        (r'All Rights Reserved.{0,40}版权所有', 'all_rights_footer'),
        (r'END相关推荐[：:]', 'end_related_links_footer'),
        (r'关键词\s*>>.{0,180}相关推荐评论\(', 'related_comments_footer'),
    ]
    boundaries = []
    for pattern, rule in patterns:
        for match in re.finditer(pattern, text):
            if match.start() < 60:
                continue
            tail = text[match.start():]
            if rule == 'people_topic_navigation_footer' and sum(t in tail for t in
                    ['学习路上', '习近平系列重要讲话', '中央文件', '微信', '学习大国']) < 2:
                continue
            if rule in {'disclaimer_footer', 'copyright_statement_footer'}:
                if not re.search(r'转载|不代表|版权|互联网|侵权|本网|本平台|所载内容|仅代表作者|不构成.{0,15}建议', tail[:300]):
                    continue
                # 引用中的“免责声明”不能截断后续真实报道。
                if tail.startswith(('免责声明：例如', '免责声明：一词')):
                    continue
            boundaries.append((match.start(), rule))
    if boundaries:
        start, rule = min(boundaries)
        remove(start, len(text), rule)
    # 插在正文中的明确括号推广语只删除该括号，保留之后的政策原句。
    for match in reversed(list(re.finditer(r'[（(]请关注微信公众号[：:][^）)\n]{1,35}[）)]', text))):
        remove(match.start(), match.end(), 'bounded_wechat_promotion')
    text = text.strip()
    markers = []
    benign_mentions = []
    for term in result['residual_noise_markers']:
        if term not in text:
            continue
        if term == '发表评论':
            occurrences = list(re.finditer(term, text))
            ui = [m for m in occurrences if not re.search(r'(?:上|中|报|刊|网)\s*$', text[max(0,m.start()-8):m.start()])
                  and not text[m.end():m.end()+4].startswith(('指出','认为','文章','表示'))]
            if not ui:
                benign_mentions.append(term)
                continue
        if term in {'微信公众号', '推荐阅读', '相关阅读'}:
            positions = [m.start() for m in re.finditer(term, text)]
            if all(p < len(text)-120 and text[p+len(term):p+len(term)+1] not in {'-', '—', '：', ':'}
                   for p in positions):
                benign_mentions.append(term)
                continue
        markers.append(term)
    flags = [f for f in result['clean_flags'] if f != 'residual_web_template']
    if markers:
        flags.append('residual_web_template')
    result.update(clean_text=text, removal_log=logs, clean_flags=sorted(set(flags)),
                  residual_noise_markers=markers, benign_template_mentions=benign_mentions,
                  clean_char_count=len(text))
    return result
