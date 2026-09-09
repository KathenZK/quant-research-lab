from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
F=Path(__file__).resolve().parents[1];O=F/'artifacts';plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axs=plt.subplots(2,1,figsize=(12,10),layout='constrained');fig.patch.set_facecolor('#faf9f6')
colors=['#22685e','#c3693e','#385d91','#8d527a','#777777','#b29933']
for c,sid in zip(colors,['D7','D8','D9','D10']):
 d=pd.read_csv(O/f'freqtrade/{sid}-0.001-wallet.csv',parse_dates=['date']);eq=d.groupby('date').total_quote.sum()/25;eq.resample('D').last().plot(ax=axs[0],label=sid,color=c,linewidth=1.5)
b=pd.read_csv(O/'freqtrade/benchmark-0.48-0.001.csv',index_col=0,parse_dates=True).iloc[:,0];b.resample('D').last().plot(ax=axs[0],label='7-pair buy/hold, 48% invested',color='#777777',alpha=.8,linestyle='--')
axs[0].set_title('Native crypto strategies | source 25 USDT wallet / 12 USDT stake | 0.10% per side',loc='left',fontweight='bold');axs[0].set_ylabel('Equity / initial capital');axs[0].legend(ncol=3,loc='upper left',frameon=False);axs[0].grid(alpha=.15)
# Fixed representative mechanisms; the complete table contains every variant.
for c,var in zip(colors,['SPY_BUY_HOLD','A6_TEXT_MONTHLY10','A9_TEXT_ROC252','A36_JANUARY_BAROMETER','C1_GEM','C4_KDA100']):
 d=pd.read_csv(O/f'equity-diagnostic/{var}-10bps-equity.csv',index_col=0,parse_dates=True).iloc[:,0];d.plot(ax=axs[1],label=var,color=c,linewidth=1.5)
axs[1].set_title('Selected ETF mechanisms | daily execution diagnostics | 10 bps per side',loc='left',fontweight='bold');axs[1].set_ylabel('Total-return equity units (log scale)');axs[1].set_yscale('log');axs[1].legend(ncol=2,loc='upper left',frameon=False,fontsize=9);axs[1].grid(alpha=.15)
for ax in axs:ax.set_xlabel('');ax.set_facecolor('#faf9f6')
fig.suptitle('PUBLIC100  /  EXPLORE_UNTRUSTED\nIllustrative diagnostics only - 0 formally verified strategies',fontsize=16,fontweight='bold',x=.065,ha='left')
fig.savefig(O/'diagnostic-equity-curves.png',dpi=170,facecolor=fig.get_facecolor());fig.savefig(O/'diagnostic-equity-curves.pdf',facecolor=fig.get_facecolor())
