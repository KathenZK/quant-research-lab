"""Standalone descriptive plot of registered frozen-version replay outcomes."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

FAMILY=Path(__file__).resolve().parents[1]
A=FAMILY/'artifacts'

def main():
    fonts=[Path('/System/Library/Fonts/PingFang.ttc'),Path('/System/Library/Fonts/STHeiti Light.ttc')]
    for p in fonts:
        if p.exists():
            font_manager.fontManager.addfont(str(p));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(p)).get_name();break
    plt.rcParams['axes.unicode_minus']=False
    rows=[r for r in json.loads((A/'all_results.json').read_text()) if r['primary']]
    rows.sort(key=lambda r:r['return'])
    labels=[]
    for r in rows:
        n=r['name'].split(' / ')[0].replace('HYPE-30M-Keltner-Trend-Breakout','HYPE 30m Keltner').replace('HYPE-1H-Adaptive-Regime','HYPE 1h AR')
        labels.append(n)
    fig,ax=plt.subplots(figsize=(12,10),layout='constrained')
    fig.patch.set_facecolor('#faf9f6');ax.set_facecolor('#faf9f6')
    values=[r['return']*100 for r in rows]
    colors=['#267d72' if x>0 else '#bd5b4d' if x<0 else '#8f9698' for x in values]
    ax.barh(labels,values,color=colors,height=.66)
    for i,v in enumerate(values):
        ax.text(v+(.8 if v>=0 else -.8),i,f'{v:+.2f}%',va='center',ha='left' if v>=0 else 'right',fontsize=10)
    ax.axvline(0,color='#7d8588',linewidth=.8)
    ax.set_xlim(min(values)-11,max(values)+12)
    ax.set_xlabel('从各自落档之后到 2026-09-05 的收益（%）',labelpad=12)
    ax.set_title('早期策略落档后：多数版本没有继续赚钱',loc='left',fontsize=18,pad=28)
    ax.spines[['top','right','left']].set_visible(False)
    ax.spines['bottom'].set_color('#ccd0cd')
    ax.tick_params(axis='y',length=0,pad=10)
    ax.grid(axis='x',alpha=.12);ax.set_axisbelow(True)
    fig.text(.01,.002,'各策略起点不同；扣原手续费和滑点。资金费调整为现有事件估计；CC含时序争议，SOL零交易。',fontsize=9,color='#566260')
    fig.savefig(A/'registered_returns.png',dpi=160,bbox_inches='tight')
    fig.savefig(A/'registered_returns.svg',bbox_inches='tight')

if __name__=='__main__':main()
