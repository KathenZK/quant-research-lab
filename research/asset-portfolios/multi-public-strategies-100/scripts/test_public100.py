"""Accounting and no-lookahead checks; artificial prices are test fixtures only."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
P=Path(__file__).parent
spec=importlib.util.spec_from_file_location('etf',P/'backtest_equity_diagnostic.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_cash_preserved_and_end_liquidation_charged():
 idx=pd.date_range('2020-01-01',periods=3);p=pd.DataFrame({'SPY':[100.,100.,100.]},index=idx)
 eq,orders,_=m.simulate(p,p,np.ones((3,1)),np.array([True,False,False]),.001)
 assert abs(eq.iloc[-1]-(1-.001)/(1+.001))<1e-12
 assert len(orders)==2

def test_weights_drift_without_daily_rebalancing():
 idx=pd.date_range('2020-01-01',periods=3);p=pd.DataFrame({'A':[100.,200.,400.],'B':[100.,100.,100.]},index=idx)
 eq,_,_=m.simulate(p,p,np.full((3,2),.5),np.array([True,False,False]),0)
 assert abs(eq.iloc[-1]-2.5)<1e-12

def test_constant_cash_has_no_market_exposure():
 idx=pd.date_range('2020-01-01',periods=3);p=pd.DataFrame({'SPY':[100.,300.,20.]},index=idx)
 eq,orders,_=m.simulate(p,p,np.zeros((3,1)),np.ones(3,bool),.001)
 assert np.allclose(eq,1) and not orders

def test_short_borrow_and_weekend_are_charged():
 idx=pd.to_datetime(['2020-01-03','2020-01-06']);p=pd.DataFrame({'SPY':[100.,100.]},index=idx)
 eq,_,_=m.simulate(p,p,-np.ones((2,1)),np.array([True,False]),0,borrow=.36525)
 assert abs(eq.iloc[-1]-.996)<1e-12

def test_decisions_do_not_change_when_future_prices_change():
 idx=pd.bdate_range('2008-01-01',periods=900);rng=np.random.default_rng(91)
 cols=m.C['equity_symbols'];p=pd.DataFrame(np.exp(np.cumsum(rng.normal(0,.01,(900,len(cols))),axis=0))*100,index=idx,columns=cols)
 q=p.copy();q.iloc[850:]*=10
 for variant in ['A6_CODE_DAILY210','A6_TEXT_MONTHLY10','A7_TEXT_ROC252','A9_CODE_MOM63','A29_CODE_REVERSED','A53_TEXT_DAILY200','C1_GEM','C4_KDA100']:
  a,ra=m.make_weights(p,variant);b,rb=m.make_weights(q,variant)
  assert np.allclose(a[:851],b[:851]),variant
  assert np.array_equal(ra[:851],rb[:851]),variant

def test_d4_full_sample_scaler_changes_past_allocation():
 # Source uses num_active_signals / signal_sum.max() over the full sample.
 earlier=np.array([1.,2.,1.]);extended=np.r_[earlier,5.]
 assert not np.allclose(earlier/earlier.max(),extended[:3]/extended.max())

def test_d5_source_uses_signal_bar_and_exit_bar_future_low():
 p=Path(__file__).resolve().parents[1]/'artifacts/sources/Adeline117__Strategy-project/src/backtest.py'
 s=importlib.util.spec_from_file_location('external_d5',p);d=importlib.util.module_from_spec(s);s.loader.exec_module(d)
 idx=pd.date_range('2024-01-01',periods=12,freq='h');ohlc=pd.DataFrame({'open':100.,'high':101.,'low':99.},index=idx)
 signal=pd.Series([-1],index=[idx[1]])
 r=d.run_backtest(signal,ohlc,hold_hours=8)
 assert r['trade_log'].index[0]==idx[1]  # same bar, contrary to next-bar prose
 ohlc.loc[idx[9],'high']=110.
 r2=d.run_backtest(signal,ohlc,hold_hours=8,stop_loss_pct=.05)
 assert r2['trade_log'].iloc[0].exit_price==105.  # uses the high after intended exit-open
