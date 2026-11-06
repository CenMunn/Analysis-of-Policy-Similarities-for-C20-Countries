"""仅从本次结果绘图；图中不附重复制作说明。"""
from pathlib import Path
import json,math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,Polygon,Circle,FancyArrowPatch,Rectangle
from matplotlib.colors import LinearSegmentedColormap
from .common import read_csv,write_csv

BLUE='#3F51B5';PURPLE='#7E57C2';GREEN='#2E7D32';GOLD='#C49A00';INK='#263238';GREY='#9DA4B3'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Microsoft YaHei','Noto Sans CJK SC','DejaVu Sans'],
 'axes.unicode_minus':False,'svg.fonttype':'none','font.size':10,'axes.spines.top':False,'axes.spines.right':False,
 'axes.labelcolor':INK,'text.color':INK,'savefig.facecolor':'white','figure.facecolor':'white','pdf.fonttype':42})

def save(fig,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    for suffix in ['png','svg','pdf']:fig.savefig(path.with_suffix('.'+suffix),dpi=260,bbox_inches='tight',pad_inches=.12)
    plt.close(fig)

def arrow(ax,a,b,color=GREY,style='-|>'):
    ax.add_patch(FancyArrowPatch(a,b,arrowstyle=style,mutation_scale=14,linewidth=1.4,color=color))

def icon(ax,x,y,kind,color=BLUE):
    if kind=='file':
        ax.add_patch(Polygon([(x-.30,y-.36),(x+.13,y-.36),(x+.30,y-.18),(x+.30,y+.36),(x-.30,y+.36)],fill=False,ec=color,lw=1.6))
        for yy in [-.15,0,.15]:ax.plot([x-.18,x+.15],[y+yy,y+yy],color=color,lw=1)
    elif kind=='filter':
        ax.add_patch(Polygon([(x-.4,y+.30),(x+.4,y+.30),(x+.10,y-.02),(x+.10,y-.34),(x-.10,y-.23),(x-.10,y-.02)],fill=False,ec=color,lw=1.6))
    elif kind=='tokens':
        for i in range(3):
            ax.add_patch(Rectangle((x-.40,y+.20-i*.22),.25+.13*i,.13,fill=False,ec=color,lw=1.3))
    elif kind=='vector':
        for i,h in enumerate([.30,.58,.23,.70,.42]):ax.add_patch(Rectangle((x-.38+i*.16,y-.34),.10,h,fc=color,alpha=.65,ec='none'))
    elif kind=='nodes':
        for dx,dy in [(-.32,.27),(.32,.27),(0,-.3)]:
            ax.plot([x,x+dx],[y,y+dy],c=color,lw=1.2);ax.add_patch(Circle((x+dx,y+dy),.09,fc='white',ec=color,lw=1.4))
        ax.add_patch(Circle((x,y),.10,fc=color))
    elif kind=='matrix':
        for i in range(4):
            for j in range(4):ax.add_patch(Rectangle((x-.32+i*.17,y-.32+j*.17),.14,.14,fc=color,alpha=min(.95,.15+.65*(i==j)+.10*((i+j)%3)),ec='none'))

def pipeline(target):
    fig,ax=plt.subplots(figsize=(15,6.5));ax.set(xlim=(0,15),ylim=(0,6.5));ax.axis('off')
    stages=[('01 数据清洗','file','2,989 篇原始 TXT','网页清理 · 事实切分\n主体、层级、状态识别'),
            ('02 统一表征','tokens','11,258 个冻结词项','jieba + 领域词典\n对数 TF · IDF · Top-K'),
            ('03 稠密向量','vector','fastText 300 维','TF-IDF 加权平均\n去均值作为独立对照'),
            ('04 国家关系','nodes','13 / 18 个有材料国家','来源关联组等权\n具体国家 + 教师六组'),
            ('05 结果评价','matrix','固定配对 + K 实验','主题、措施分别评价\n来源组重抽样 10,000 次')]
    for i,(title,kind,num,desc) in enumerate(stages):
        x=.2+i*3
        ax.text(x,6.15,title,fontsize=13,color=BLUE,weight='bold');ax.plot([x,x+2.6],[5.9,5.9],color='#D7DAE3')
        ax.add_patch(FancyBboxPatch((x,2.10),2.55,2.83,boxstyle='round,pad=.08,rounding_size=.08',facecolor='white',edgecolor=BLUE if i in [0,3] else GREY,lw=1.2))
        icon(ax,x+1.27,4.28,kind,BLUE if i!=2 else PURPLE)
        ax.text(x+1.27,3.48,num,ha='center',fontsize=11,weight='bold');ax.text(x+1.27,2.75,desc,ha='center',va='center',linespacing=1.7,fontsize=10)
        if i<4:arrow(ax,(x+2.66,3.56),(x+2.91,3.56))
    ax.text(1.47,1.52,'782 主集 + 5,183 扩展\n5,965 条事件记录',ha='center',color=GREEN,fontsize=10,linespacing=1.5)
    ax.plot([4.47,4.47,10.47],[5.02,5.5,5.5],color=GREY,lw=1.2);arrow(ax,(10.47,5.5),(10.47,5.02))
    ax.text(7.47,5.58,'TF-IDF 稀疏向量直接参与国家对照',ha='center',fontsize=9,color=BLUE)
    ax.add_patch(FancyBboxPatch((6.12,.55),2.7,1.05,boxstyle='round,pad=.1',fc='white',ec=PURPLE,lw=1.2))
    ax.text(7.47,1.08,'BGE 完整文本编码 · 512 维\n冻结模型，重叠分块',ha='center',va='center',fontsize=10,linespacing=1.6)
    ax.plot([2.75,2.75,6.02],[2.1,1.06,1.06],c=GREY,lw=1.2);arrow(ax,(5.6,1.06),(6.02,1.06))
    ax.text(4.45,.65,'政策事实全文',ha='center',fontsize=9,color=PURPLE)
    arrow(ax,(8.92,1.07),(10.48,2.02),PURPLE)
    save(fig,target/'图1_全流程图标示意')

def scoring(target):
    fig,ax=plt.subplots(figsize=(14,7));ax.set(xlim=(0,14),ylim=(0,7));ax.axis('off')
    ax.text(7,6.75,'CM-PACE 国家主体评分',ha='center',fontsize=18,weight='bold',color=BLUE)
    ax.text(7,3.55,r'$S(c)=0.60E(c)+0.15P(c)+0.20D(c)+0.05M(c)$',ha='center',fontsize=20,color=BLUE)
    cards=[(.25,4.45,6.05,1.65,'E 关系证据','当前合格施策主体 1；已验证指代连接 0.85；\n弱上下文关系 0.65；无关系 0。','先解释谁采取措施，避免把对象当主体。'),
           (7.7,4.45,6.05,1.65,'P 动作位置',r'$P=\max_{d\in\mathcal{D}_c}\ 1/(1+d/40)$'+'\n观测距离集合为空时为 0。','仅统计同分句前向距离，0≤d≤160 字符。'),
           (.25,.45,6.05,2.05,'D 分布支持',r'$D=\frac{n}{n+2}\frac{h}{q}\sqrt{\frac{p_{last}-p_{first}}{L}}$'+'\n仅 n≥3 且 h≥2 时启用，否则为 0。','结合频次、跨句覆盖和跨度，抑制两次局部密集。'),
           (7.7,.45,6.05,2.05,'M 来源核对','来源一致且可靠：1；来源一致但弱：0.5；\n不一致、明确冲突或无关系的多国竞争：0。','来源只辅助判断，不覆盖明确的正文角色。')]
    for x,y,w,h,title,formula,why in cards:
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.10',fc='white',ec=GREY,lw=1))
        ax.text(x+.17,y+h-.30,title,color=PURPLE,weight='bold',fontsize=12)
        ax.text(x+w/2,y+h-.90,formula,ha='center',va='center',fontsize=12,linespacing=1.7)
        ax.text(x+w/2,y+.22,why,ha='center',fontsize=10)
    for a,b in [((5.5,3.92),(4.9,4.38)),((8.5,3.92),(9.1,4.38)),((5.5,3.18),(4.9,2.60)),((8.5,3.18),(9.1,2.60))]:arrow(ax,a,b,BLUE)
    ax.text(7,6.36,'关系优先，评分处理证据不足或候选竞争；权重为经验设定',ha='center',fontsize=10)
    save(fig,target/'图2_CM-PACE评分展开')

def report_flow(target):
    fig,ax=plt.subplots(figsize=(8,5.5));ax.set(xlim=(0,8),ylim=(0,5.5));ax.axis('off')
    cards=[(.1,3.8,'file','原始文档','2,989 篇 TXT'),(4.2,3.8,'filter','政策清洗','782 主集 + 5,183 扩展事件'),
           (4.2,2.0,'tokens','分词与TF-IDF','11,258 词项 · 四种K'),(.1,2.0,'vector','词向量','fastText 加权 / BGE 全文'),
           (.1,.2,'nodes','国家聚合','13 / 18 国 · 教师六组'),(4.2,.2,'matrix','评价与选词','主题 / 措施 · 最小K与区间')]
    for x,y,kind,title,detail in cards:
        ax.add_patch(FancyBboxPatch((x,y),3.5,1.35,boxstyle='round,pad=.06',fc='white',ec=BLUE,lw=1.1))
        icon(ax,x+.55,y+.83,kind);ax.text(x+1.05,y+.88,title,fontsize=13,weight='bold',color=BLUE)
        ax.text(x+1.75,y+.26,detail,fontsize=10,ha='center')
    for a,b in [((3.7,4.48),(4.1,4.48)),((5.95,3.72),(5.95,3.43)),((4.1,2.68),(3.7,2.68)),((1.85,1.92),(1.85,1.63)),((3.7,.88),(4.1,.88))]:arrow(ax,a,b)
    save(fig,target/'报告版_流程')

def make_figures(output,target=None):
    out=Path(output);target=Path(target) if target else out/'图';target.mkdir(parents=True,exist_ok=True)
    pipeline(target);scoring(target);report_flow(target)
    allcov=read_csv(out/'04_国家关系/国家覆盖.csv');cov=allcov;mat=read_csv(out/'04_国家关系/相似度矩阵.csv')
    filt=lambda r:r['unit']=='article_policy' and r['scheme']=='国家' and r['method']=='TFIDF'
    cov=[r for r in cov if filt(r)];countries=[r['country'] for r in cov if r['view']=='main']
    vals={(r['view'],r['country']):int(r['n_unique_texts']) for r in cov}
    countries.sort(key=lambda c:vals['main_extended',c],reverse=True)
    fig,ax=plt.subplots(figsize=(11,6));yy=np.arange(len(countries))
    ax.barh(yy+.17,[vals['main_extended',c] for c in countries],height=.32,color=PURPLE,label='主集 + 扩展')
    ax.barh(yy-.17,[vals['main',c] for c in countries],height=.32,color=BLUE,label='仅主集')
    ax.set(yticks=yy,yticklabels=countries,xlabel='有效分析文本数',title='国家材料覆盖');ax.invert_yaxis();ax.legend(frameon=False);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    save(fig,target/'图3_国家材料覆盖')
    cmap=LinearSegmentedColormap.from_list('slateviolet',['#2E7D32','#FFFFFF',BLUE])
    for scheme,title in [('国家','具体国家'),('老师六组','教师六组')]:
      for view,label in [('main','仅主集'),('main_extended','主集与扩展')]:
        available=[r for r in mat if r['unit']=='article_policy' and r['view']==view and r['K']=='all' and r['scheme']==scheme]
        names=list(dict.fromkeys(r['country'] for r in available if r['country']==r['neighbor'] and r['cosine']))
        main_names={r['country'] for r in mat if r['unit']=='article_policy' and r['view']=='main' and r['K']=='all' and r['scheme']==scheme and r['country']==r['neighbor'] and r['cosine']}
        names=[c for c in names if c in main_names]
        low={r['country'] for r in allcov if r['unit']=='article_policy' and r['view']==view and r['scheme']==scheme and r['method']=='TFIDF' and r['meets_operational_minimum'].lower()=='false'}
        labels=[c+('†' if c in low else '') for c in names]
        fig,axes=plt.subplots(1,2,figsize=(14,6.7 if scheme=='国家' else 5.2),layout='constrained')
        for ax,m in zip(axes,['TFIDF','BGE_complete']):
            lookup={(r['country'],r['neighbor']):float(r['cosine']) for r in available if r['method']==m and r['cosine']}
            a=np.array([[lookup.get((c,d),np.nan) for d in names] for c in names]);im=ax.imshow(a,cmap=cmap,vmin=-1,vmax=1)
            ax.set(xticks=range(len(names)),yticks=range(len(names)),xticklabels=labels,yticklabels=labels,title='TF-IDF' if m=='TFIDF' else 'BGE')
            ax.tick_params(axis='x',labelrotation=55,labelsize=8);ax.tick_params(axis='y',labelsize=8)
            if scheme=='老师六组':
                for i in range(len(names)):
                    for j in range(len(names)):ax.text(j,i,f'{a[i,j]:.2f}',ha='center',va='center',fontsize=9,color='white' if a[i,j]>.65 else INK)
        fig.colorbar(im,ax=axes,shrink=.7,label='余弦相似度');fig.suptitle(f'{title} · {label} · 来源组等权'+(' · †覆盖不足' if low.intersection(names) else ''),fontsize=14)
        save(fig,target/f'图4_{title}_{label}_热力图')
    scores=read_csv(out/'05_评价/方法对照.csv');print('评价分层',sorted({(r['sample'],r['scope']) for r in scores}),flush=True)
    # Same-answer comparison uses only fixed common pairs, not rejudged pairs.
    chosen=[r for r in scores if r['sample']=='语义标签保持的活跃对']
    samples=['框内随机','专项难例'];methods=['TFIDF','FastText','BGE_complete','FastText_center']
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),sharey=True,layout='constrained')
    for ax,s in zip(axes,samples[:2]):
        data=[r for r in chosen if r['scope']==s];n=int(data[0]['n']);x=np.arange(4)
        for j,(axis,c) in enumerate([('topic',BLUE),('measure',PURPLE)]):
            v=[next(float(r['spearman']) for r in data if r['method']==m and r['axis']==axis) for m in methods]
            bars=ax.bar(x+(j-.5)*.34,v,width=.32,color=c,label='主题' if axis=='topic' else '措施')
            ax.bar_label(bars,fmt='%.3f',fontsize=8,padding=3)
        ax.set(xticks=x,xticklabels=['TF-IDF','fastText','BGE','fastText\n去均值'],ylim=(-1,1),title=f'{s} · n={n}');ax.axhline(0,c=GREY,lw=.8);ax.legend(frameon=False);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    axes[0].set_ylabel('Spearman ρ');save(fig,target/'图5_同口径方法对照')
    curves=read_csv(out/'05_评价/逐整数K曲线.csv');est=read_csv(out/'05_评价/词数精细估计.csv')
    fig,axes=plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
    for ax,r in zip(axes,est):
        rows=[z for z in curves if z['view']==r['view']];k=int(r['K95']);lo=int(r['ci_low']);hi=int(r['ci_high'])
        ax.plot([int(z['K']) for z in rows],[100*float(z['fraction_99_mass']) for z in rows],color=BLUE,lw=2)
        ax.axhline(95,color=GREY,ls='--');ax.axvspan(lo,hi,color=PURPLE,alpha=.13);ax.axvline(k,color=PURPLE,ls='--')
        ax.scatter(k,100*float(r['success']),c=PURPLE,zorder=3);ax.text(k+3,73,f'最小 K={k}\n条件性95%区间\n[{lo}, {hi}]',color=PURPLE,fontsize=11,linespacing=1.6)
        ax.set(xlim=(0,120 if r['view']=='main' else 250),ylim=(0,102),xlabel='按权重保留的不同有效词项数 K',title=('仅主集' if r['view']=='main' else '主集 + 扩展')+f" · n={r['valid_texts']}");ax.grid(alpha=.15)
    axes[0].set_ylabel('达到99%权重保留率的文本占比（%）');save(fig,target/'图6_最小K与条件区间')
    kinput=read_csv(out/'02_分词与TFIDF/K输入诊断.csv');changes=read_csv(out/'04_国家关系/K相似度变化.csv');tab=[]
    for r in kinput:
        if r['unit']!='article_policy':continue
        d=dict(r)
        for m in ['TFIDF','FastText']:
            a=next(v for v in changes if v['unit']=='article_policy' and v['view']==r['view'] and v['scheme']=='国家' and v['method']==m and v['K']==r['K'])
            d[m+'_members_changed']=a['neighbor_memberships_changed'];d[m+'_order_changed']=a['neighbor_orders_changed']
        tab.append(d)
    write_csv(target/'图表数据_K原定四配置.csv',tab)
    fig,axes=plt.subplots(1,2,figsize=(12,4.2),layout='constrained')
    for ax,view in zip(axes,['main','main_extended']):
        rows=[r for r in tab if r['view']==view];x=np.arange(4)
        ax.bar(x,[100*float(r['mean_weight_mass']) for r in rows],color=BLUE,width=.5)
        ax.set(xticks=x,xticklabels=['50','100','200','全部'],ylim=(0,110),ylabel='平均TF-IDF权重保留率（%）',xlabel='K',title='仅主集' if view=='main' else '主集 + 扩展')
        for i,r in enumerate(rows):ax.text(i,float(r['mean_weight_mass'])*100+2,f"{float(r['mean_weight_mass'])*100:.2f}%\n截断 {r['truncated']} 条",ha='center',fontsize=9)
    save(fig,target/'图7_词数压缩与实际截断')
