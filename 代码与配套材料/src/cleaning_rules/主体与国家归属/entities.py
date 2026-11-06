import re
PUBLIC_SUFFIX = re.compile(r'(?:联邦|中央|地方)?(?:政府|总统|总理|首相|议会|国会|内阁|能源部|环境部|环保部|外交部|财政部|经济产业省|产业通商资源部|能源署|环境署|参议院|众议院|交通部|商务部|部长|央行|委员会)')
PRIVATE_NAMES=re.compile(r'沙特阿美|沃尔玛|亚马逊|远景动力|Uniper|微软|特斯拉|通用汽车',re.I)
class BaseMentions:
    def __init__(self,names):
        self.names=names
        self.role_refinements=True
        self.name_pattern=re.compile("|".join(re.escape(n) for n in sorted(names,key=len,reverse=True)))
    def mentions(self, text, offset=0):
            out = []
            for m in self.name_pattern.finditer(text):
                if text.rfind('《', 0, m.start()) > text.rfind('》', 0, m.start()):
                    continue
                c, public = self.names[m.group()]
                a, b = m.span()
                suffix = PUBLIC_SUFFIX.match(text, b)
                if suffix:
                    b = suffix.end()
                    public = True
                after = text[b:b+15]
                prefix = text[max(0, a-8):a]
                role = 'mention'
                if re.search(r'(?:对|针对|向|来自|效仿|相比|借鉴)\s*$', prefix):
                    role = 'target'
                elif re.match(r'(?:的)?(?:公司|企业|集团|媒体|记者|学者|专家|市场|产业|经济|研究院|协会|联合会)', after):
                    role = 'private_or_context'
                elif public:
                    role = 'public_actor'
                else:
                    role = 'country_candidate'
                if out and out[-1]['country']==c and out[-1]['end']==offset+a and public and role=='public_actor':
                    prev=out.pop();a=prev['start']-offset
                out.append(dict(country=c, text=text[a:b], start=offset+a, end=offset+b, public=public, role=role))
            return out
class PrivateMentions(BaseMentions):
    def mentions(self,text,offset=0):
            mentions=super().mentions(text,offset)
            private=[m.span() for m in PRIVATE_NAMES.finditer(text)]
            for m in mentions:
                if any(a<=m['start']-offset<b for a,b in private):m.update(role='private_or_context',public=False)
            return mentions
class EntityMentions(PrivateMentions):
    def mentions(self, text, offset=0):
            values = super().mentions(text, offset)
            for m in values:
                a, b = m['start']-offset, m['end']-offset
                if self.role_refinements and m['country']=='中国' and text[max(0,a-2):b+1]=='发展中国家':
                    m['role']='not_country'
                if self.role_refinements and re.match(r'(?:通讯社|记者|媒体|有线电视新闻网|有线电视|广播公司|广播电台|电视台|《[^》]*(?:时报|日报|邮报|新闻|周刊)[^》]*》)',text[b:]):
                    m.update(role='private_or_context',public=False)
                if re.search(r'(?:帮助|助力|呼吁|提议|促请|敦促|建议|希望)\s*$', text[max(0,a-10):a]):
                    m.update(role='target', public=False)
                if re.match(r'(?:工业家联合会|机械产业振兴会|铁路网公司|产业协会)', text[b:]):
                    m.update(role='private_or_context', public=False)
            return [m for m in values if m['role']!='not_country']
