import os
from pathlib import Path
import pandas as pd,numpy as np,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
A=Path(os.environ.get('TPSA_R0_OUTPUT',str(Path(__file__).resolve().parents[1]/'artifacts')))
fig,ax=plt.subplots(2,1,figsize=(11,7),sharex=True,gridspec_kw={'height_ratios':[2,1]})
for name in ['ML_p040','ALL_EVENTS','HASH20_EVENTS']:
    q=pd.read_csv(A/name/'account_equity.csv');x=pd.DatetimeIndex([pd.Timestamp('2025-01-01',tz='UTC'),*pd.to_datetime(q.time,utc=True)]);y=np.r_[10000.,q.equity_ex_actual_funding];ax[0].plot(x,y,label=name,lw=1.5);ax[1].plot(x,100*(y/np.maximum.accumulate(y)-1),lw=1.5)
ax[0].set_ylabel('USD; actual funding excluded');ax[1].set_ylabel('Drawdown (%)');ax[0].legend();ax[0].axhline(10000,color='grey',lw=.7);ax[0].set_title('TPSA-LA R0: reused conditional account / daily-open price proxy')
for a in ax:a.grid(alpha=.18)
fig.tight_layout();fig.savefig(A/'equity_drawdown.png',dpi=150);plt.close(fig)
