#!/usr/bin/env python3
"""Optional presentation PNG. The canonical SVG charts need no third-party library."""
from pathlib import Path
import csv,datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=Path(__file__).resolve().parents[1]/'artifacts/results'
fig,axs=plt.subplots(2,1,figsize=(11,7),sharex=True,gridspec_kw={'height_ratios':[3,1]})
for asset,color in [('BTC','#266B83'),('ETH','#AE5E37')]:
    r=list(csv.DictReader((p/(asset.lower()+'_account_hourly.csv')).open()));x=[datetime.datetime.fromisoformat(q['utc']) for q in r]
    axs[0].plot(x,[float(q['equity_usd']) for q in r],color=color,label=asset+' spot + USDT perpetual')
    axs[1].plot(x,[float(q['drawdown'])*100 for q in r],color=color)
axs[0].plot(x,[float(q['cash_benchmark_usd']) for q in r],color='#777',ls='--',label='Assumed 4% cash opportunity')
axs[0].axhline(10000,color='#ddd');axs[0].set_ylabel('Account equity (USD)');axs[1].set_ylabel('Drawdown (%)');axs[0].legend(loc='upper left')
fig.suptitle('Separate $10,000 accounts — reused historical carry diagnostic\nOHLC executions and funding notional proxies; no live fill claim')
for ax in axs:ax.grid(alpha=.15);ax.spines[['top','right']].set_visible(False)
fig.tight_layout();fig.savefig(p/'perpetual_equity_drawdown.png',dpi=170)
