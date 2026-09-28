"""Mechanism tests for a fixed per-trade volatility scale; frozen engine reused."""
from pathlib import Path
import importlib.util,sys
from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
ROOT=Path(__file__).resolve().parents[1]
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
e=load('fixed_atr_test_engine',ROOT/'research/_shared-kernels/ma7-cross-atr-ratchet/v8/engine.py')
f=load('fixed_atr_test_fixture',ROOT/'tests/test_ma7_car_admission_routing.py')
def cfg(**kw):return e.Config(**{'reverse':False,'progress_days':4,'fee':.001,'slip':.0004,'trail_atr':False,**kw})

@pytest.mark.parametrize('side',[-1,1])
def test_future_atr_changes_do_not_move_fixed_stop(side):
 d,h=f.path(side=side,closes=(1.,)*9,favorable=10.,ma=0.,atr=10.)
 base=e.simulate(h,d,cfg());changed=d.copy();changed.loc[changed.index>0,'atr']=np.resize([2.,20.],len(changed)-1)
 fixed=e.simulate(h,changed,cfg())
 for a,b in zip(base[1:4],fixed[1:4]):
  keep=[c for c in a.columns if c not in ['adverse_ma_distance_atr']]
  pd.testing.assert_frame_equal(a[keep],b[keep],check_exact=True)
 # Dynamic comparator responds to exactly the same ATR sequence.
 dynamic=e.simulate(h,changed,cfg(trail_atr=True))
 assert not dynamic[3].new_stop.equals(fixed[3].new_stop)
 assert fixed[3].new_mult.min()<1.5,'fixed ATR must not disable multiplier tightening'

@pytest.mark.parametrize('scale',[.01,100.])
def test_price_unit_invariance(scale):
 raw,h=f.random_market();d=e.features(raw);original=e.simulate(h,d,cfg())
 rr=raw.copy();hh=h.copy()
 for col in ['open','high','low','close']:rr[col]*=scale;hh[col]*=scale
 scaled=e.simulate(hh,e.features(rr),cfg())
 assert original[1].entry_time.tolist()==scaled[1].entry_time.tolist()
 assert original[1].exit_time.tolist()==scaled[1].exit_time.tolist()
 np.testing.assert_allclose(original[1].return_on_entry_equity,scaled[1].return_on_entry_equity,atol=1e-12,rtol=1e-10)

def test_prefix_and_per_trade_reset():
 raw,h=f.random_market();d=e.features(raw);whole=e.simulate(h,d,cfg());cut=f.ZERO+pd.Timedelta(days=90)
 short=e.simulate(h[h.timestamp<cut],e.features(raw[raw.timestamp<cut]),cfg(),end=cut)
 for i,col in [(1,'exit_time'),(3,'timestamp')]:
  a=whole[i][whole[i][col]<cut];b=short[i][short[i][col]<cut]
  pd.testing.assert_frame_equal(a.reset_index(drop=True),b.reset_index(drop=True),check_exact=True)
 index=d.set_index('timestamp')
 assert whole[1].entry_atr.nunique()>1
 for trade in whole[1].itertuples():assert trade.entry_atr==index.loc[trade.signal_day,'atr']

def test_independent_checker_preserves_exact_rolling_equality():
 from dataclasses import asdict
 scripts=ROOT/'research/hype/1d-ma7-cross-atr-ratchet/scripts'
 sys.path.insert(0,str(scripts))
 import audit_fixed_atr_validation_20260924 as auditor
 raw,_=f.random_market();raw=raw.iloc[:30].copy()
 raw['close']=.00645;raw.loc[raw.index[-1],'close']=.0068
 raw['high']=raw.close+.001;raw['low']=raw.close-.001
 for key in ['eligible','observed_valid','is_closed','joint_eligible']:raw[key]=True
 d=auditor.indicators(raw,asdict(cfg()))
 assert d.iloc[-2].ma==d.iloc[-2].close
 assert d.iloc[-1].cross==1

def test_independent_checker_stops_requiring_entries_after_insolvency():
 from dataclasses import asdict
 sys.path.insert(0,str(ROOT/'research/hype/1d-ma7-cross-atr-ratchet/scripts'))
 import audit_fixed_atr_validation_20260924 as auditor
 at=pd.Timestamp('2025-01-02',tz='UTC');before=at-pd.Timedelta(days=1)
 times=pd.date_range(before,periods=4,freq='D')
 daily=pd.DataFrame({'timestamp':times,'ready':True,'slope':1.,'cross':1,'close':10.,'ma':9.,'atr':1.}).set_index('timestamp',drop=False)
 hourly=pd.DataFrame({'timestamp':times,'open':10.}).set_index('timestamp',drop=False)
 tr=pd.DataFrame([{'entry_time':at,'signal_day':before,'side':1,'entry_reason':'daily_cross','exit_time':at+pd.Timedelta(hours=1),'exit_reason':'stop_intrahour','net_pnl':-11000.}])
 events=pd.DataFrame([{'timestamp':at,'status':'filled'}])
 s={**asdict(cfg()),'start':str(at),'end_exclusive':str(at+pd.Timedelta(days=3))}
 assert auditor.audit_entry_lifecycle(tr,daily,hourly,s,events)['entries_verified']==1
