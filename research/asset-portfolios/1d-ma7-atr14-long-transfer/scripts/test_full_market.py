"""Targeted checks for causal features, segment isolation and dependence bootstrap."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_full_market import price_features,economic_flags,run_segment
from analyze_full_market import bootstrap_contrast
from strategy_lab.data.research_inputs import segment_research_bars,complete_window_mask

def fixture_bars(n=160):
 rows=[]
 for i in range(n):
  c=100*np.exp(.001*i+.06*np.sin(i/5));o=c*(1+.004*np.cos(i/3))
  rows.append({'ts':int(pd.Timestamp('2025-01-01',tz='UTC').value//1000000)+i*86400000,'end_ts':int(pd.Timestamp('2025-01-01',tz='UTC').value//1000000)+(i+1)*86400000-1,'open':o,'high':max(o,c)*1.01,'low':min(o,c)*.99,'close':c})
 return rows

def test_future_price_and_volume_changes_cannot_change_signal_features():
 bars=fixture_bars();q=np.arange(len(bars),dtype=float)*100+1e7
 a=price_features(bars,q)
 altered=[dict(x) for x in bars]
 for i in range(111,len(bars)):
  for k in ['open','high','low','close']:altered[i][k]*=10 if i%2 else .05
 q2=q.copy();q2[111:]*=100
 b=price_features(altered,q2)
 for k in ['trend60','momentum30','efficiency30','chop30','atr_pct','liquidity30']:
  np.testing.assert_array_equal(a[k][:111],b[k][:111])
  prefix=price_features(bars[:111],q[:111]);np.testing.assert_array_equal(a[k][:111],prefix[k])

def test_invalid_day_resets_warmup_and_never_connects_positions():
 bars=fixture_bars(130)
 for index,close in [(19,80.),(20,140.),(89,80.),(90,140.)]:
  bars[index].update(open=close,close=close,high=close*1.01,low=close*.99)
 f=pd.DataFrame(bars);f['ts']=pd.to_datetime(f.ts,unit='ms',utc=True)
 f=f.assign(symbol='TEST/USDT:USDT',timeframe='1d',volume=1000.,quote_volume=1e7,trade_count=100,is_closed=True)
 f.loc[64,['volume','quote_volume','trade_count']]=0
 segmented=segment_research_bars(f,'1d',identity_policy='observed_diagnostic')
 segmented['research_window_valid']=complete_window_mask(segmented,backward=1)
 mask=complete_window_mask(segmented,backward=15)
 assert not mask.iloc[64:79].any() and mask.iloc[79]
 assert segmented.research_segment_id.nunique()==2
 trades=[]
 for _,part in segmented.groupby('research_segment_id',sort=False):
  _,t,_=run_segment('TEST/USDT:USDT','COIN','test',part,part.ts.iloc[0],part.ts.iloc[-1]+pd.Timedelta(days=1),deep=True)
  trades.extend(t)
  assert all(pd.Timestamp(x['entry_date'],tz='UTC')>=part.ts.iloc[0] and pd.Timestamp(x['exit_date'],tz='UTC')<=part.ts.iloc[-1] for x in t)
 assert len(trades)>0
 with pytest.raises(AssertionError):
  run_segment('TEST/USDT:USDT','COIN','test',segmented.loc[segmented.eligible],f.ts.iloc[0],f.ts.iloc[-1]+pd.Timedelta(days=1))

def test_discontinuity_flags_are_symmetric_and_scale_invariant():
 bars=fixture_bars();f=price_features(bars,[1e7]*len(bars));assert not any(economic_flags(bars,f).values())
 scaled=[dict(x,**{k:x[k]*.0001 for k in ['open','high','low','close']}) for x in bars]
 assert economic_flags(bars,f)==economic_flags(scaled,price_features(scaled,[1e7]*len(bars)))
 for multiple in [8,.125]:
  bad=[dict(x) for x in bars]
  for k in ['open','high','low','close']:bad[100][k]*=multiple
  assert economic_flags(bad,price_features(bad,[1e7]*len(bad)))['close_ratio_gt4_or_lt_quarter']

def test_two_way_bootstrap_keeps_matched_identical_groups_equal():
 rows=[]
 for coin in range(15):
  for month in range(8):
   for side in [0,1]:rows.append({'symbol':str(coin),'entry_month':str(month),'log_return_pct':coin+month,'side':side})
 t=pd.DataFrame(rows);r=bootstrap_contrast(t,t.side.eq(1),t.side.eq(0),7)
 assert abs(r['estimate_log_pp'])<1e-12 and abs(r['month_adjusted_log_pp'])<1e-12
 assert max(abs(x) for x in r['ci95'])<1e-12
