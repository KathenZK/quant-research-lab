"""Descriptive paired-version chart and CC common/long-window comparison."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

FAMILY=Path(__file__).resolve().parents[1]
A=FAMILY/'artifacts/iteration_comparison_20260911'

def main():
    for path in ['/System/Library/Fonts/PingFang.ttc','/System/Library/Fonts/STHeiti Light.ttc']:
        if Path(path).exists():
            font_manager.fontManager.addfont(path)
            plt.rcParams['font.family']=font_manager.FontProperties(fname=path).get_name()
            break
    plt.rcParams['axes.unicode_minus']=False
    ps=json.loads((A/'paired_results.json').read_text())
    ps.sort(key=lambda p:p['increment'])
    fig,ax=plt.subplots(figsize=(13,9))
    fig.patch.set_facecolor('#faf9f6');ax.set_facecolor('#faf9f6')
    for i,p in enumerate(ps):
        e,f=p['early_return']*100,p['final_return']*100
        color='#2d8275' if f>e+1e-7 else '#bd5c4c' if f<e-1e-7 else '#8a918e'
        ax.plot([e,f],[i,i],color=color,lw=3,zorder=2)
        ax.scatter(e,i,s=72,facecolor='#faf9f6',edgecolor='#727c7d',linewidth=1.5,zorder=3)
        ax.scatter(f,i,s=65,facecolor='#263e4e',edgecolor='#263e4e',zorder=4)
        ax.text(22,i,f"{e:+.2f}% → {f:+.2f}%",va='center',fontsize=10,color='#374a50')
    ax.set_yticks(range(len(ps)),[p['name'] for p in ps],fontsize=11)
    ax.set_xlim(-9,33);ax.set_xticks([-5,0,5,10,15,20])
    ax.axvline(0,color='#b2b8b5',lw=1);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    ax.set_xlabel('同一段后续行情的收益（%）',labelpad=12)
    ax.set_title('早期版与最终版：7组改善，6组变差，1组持平',loc='left',fontsize=19,pad=30)
    ax.scatter([],[],s=60,facecolor='#faf9f6',edgecolor='#727c7d',label='早期固定对照')
    ax.scatter([],[],s=60,facecolor='#263e4e',edgecolor='#263e4e',label='最终版')
    ax.legend(loc='upper right',frameon=False,bbox_to_anchor=(1.0,1.06),ncol=2)
    ax.spines[['top','right','left']].set_visible(False);ax.spines['bottom'].set_color('#b2b8b5')
    ax.tick_params(axis='y',length=0,pad=10)
    fig.subplots_adjust(left=.24,right=.98,bottom=.13,top=.89)
    fig.text(.02,.043,'2026-07-23 至 09-05 15:00 UTC｜每次入场1倍名义仓位｜手续费0.10% + 滑点0.04%/次',fontsize=10,color='#53635e')
    fig.text(.02,.017,'资金费为已有事件估算；EMA-X裸交叉按早期代码恢复，EMA-TB主对照从V35开始。不是新的盲测。',fontsize=9,color='#53635e')
    fig.savefig(A/'paired_returns.png',dpi=160);fig.savefig(A/'paired_returns.svg')
    plt.close(fig)

    rows=json.loads((A/'all_results.json').read_text());versions=['V10','V13','V18','V21','V35']
    common=[];long=[]
    for v in versions:
        common.append(next(r['return']*100 for r in rows if r['family']=='HYPE-CC' and r['version']==v and r['window']=='common' and r['scenario']=='equal_1x_base'))
        long.append(next(r['return']*100 for r in rows if r['family']=='HYPE-CC' and r['version']==v and r['window']=='long'))
    fig,axes=plt.subplots(1,2,figsize=(12,5),sharey=True)
    fig.patch.set_facecolor('#faf9f6')
    for ax,values,title in zip(axes,[common,long],['7月23日之后：中间版本更好','6月8日之后：五个版本都亏损']):
        ax.set_facecolor('#faf9f6')
        bars=ax.bar(versions,values,color=['#2d8275' if v>0 else '#bd5c4c' for v in values],width=.62)
        for bar,val in zip(bars,values):
            ax.text(bar.get_x()+bar.get_width()/2,val+(1.2 if val>=0 else -1.2),f'{val:+.2f}%',ha='center',va='bottom' if val>=0 else 'top',fontsize=10)
        ax.axhline(0,color='#87958e',lw=.8);ax.set_title(title,fontsize=14,pad=15)
        ax.spines[['top','right','left']].set_visible(False);ax.grid(axis='y',alpha=.12);ax.set_axisbelow(True)
        ax.set_ylim(-51,16);ax.tick_params(axis='both',length=0)
    axes[0].set_ylabel('收益（%）')
    fig.suptitle('HYPE 15分钟：10根中至少8根同色后反转',fontsize=18,y=.97)
    fig.subplots_adjust(left=.07,right=.98,bottom=.16,top=.80,wspace=.12)
    fig.text(.02,.045,'统一1倍名义仓位；截止2026-09-05 15:00 UTC。两段窗口均预先固定，费用相同，资金费为估算。',fontsize=10,color='#53635e')
    fig.savefig(A/'cc_versions_windows.png',dpi=160);fig.savefig(A/'cc_versions_windows.svg')
    plt.close(fig)

if __name__=='__main__':main()
