"""V3 sensitivity engine: frozen parity, independent features and causal prefix."""
from pathlib import Path
from dataclasses import replace
import importlib.util
import sys
import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
f=load('parameter_fixture',ROOT/'tests/test_ma7_car_admission_routing.py')
old=load('parameter_old',ROOT/'research/_shared-kernels/ma7-cross-atr-ratchet/v7/engine.py')
new=load('parameter_new',ROOT/'research/_shared-kernels/ma7-cross-atr-ratchet/v8/engine.py')
audit=load('parameter_audit',ROOT/'research/hype/1d-ma7-cross-atr-ratchet/scripts/audit_v3_parameters_20260924.py')
study=load('parameter_study',ROOT/'research/hype/1d-ma7-cross-atr-ratchet/scripts/v3_parameter_study_20260924.py')

def test_default_exact_parity():
 raw,h=f.random_market();d=old.features(raw);dn=new.features(raw)
 pd.testing.assert_frame_equal(d,dn[d.columns],check_exact=True)
 for reverse in [False,True]:
  a=old.simulate(h,d,old.Config(reverse=reverse,progress_days=4,fee=.001,slip=.0004))
  b=new.simulate(h,dn,new.Config(reverse=reverse,progress_days=4,fee=.001,slip=.0004))
  for k,v in a[0].items():assert b[0][k]==v,(k,v,b[0][k])
  for x,y in zip(a[1:],b[1:]):pd.testing.assert_frame_equal(x,y[x.columns],check_exact=True)

@pytest.mark.parametrize('key',list(study.GRID))
def test_independent_indicators_and_prefix(key):
 raw,h=f.random_market();raw['eligible']=raw['observed_valid']=raw['is_closed']=raw['joint_eligible']=True
 cfg=replace(study.base_config(new),**{key:study.GRID[key][1][1]})
 d=study.feature_frame(new,raw,cfg);ind=audit.indicators(raw,study.asdict(cfg)).reset_index(drop=True)
 for col in ['ma','atr','rsi','slope','cross','accel1','ready']:
  np.testing.assert_allclose(d[col],ind[col],rtol=1e-12,atol=1e-12,equal_nan=True)
 cut=f.ZERO+pd.Timedelta(days=90);a=new.simulate(h,d,cfg);prefix=study.feature_frame(new,raw[raw.timestamp<cut],cfg)
 pd.testing.assert_frame_equal(d[d.timestamp<cut].reset_index(drop=True),prefix,check_exact=True)
 b=new.simulate(h[h.timestamp<cut],prefix,cfg,end=cut)
 for i,col in [(1,'exit_time'),(3,'timestamp')]:
  x=a[i][a[i][col]<cut];y=b[i][b[i][col]<cut]
  pd.testing.assert_frame_equal(x.reset_index(drop=True),y.reset_index(drop=True),check_exact=True)

@pytest.mark.parametrize('side',[-1,1])
@pytest.mark.parametrize('floor,step',[(.3,.15),(.7,.3),(0.,1.)])
def test_stop_schedule_and_monotonicity(side,floor,step):
 d,h=f.path(side=side,closes=(1.,)*14,favorable=10.,ma=0.,atr=10.)
 cfg=replace(study.base_config(new),atr_floor=floor,tighten_step=step)
 result=new.simulate(h,d,cfg);s=result[3];expected=1.5
 for row in s.itertuples():
  if row.tightened:expected=max(floor,round(expected-step,10))
  assert row.new_mult==expected
  assert side*(row.new_stop-row.old_stop)>=0
 first=s[s.tightened].iloc[0]
 assert first.signal_day==f.ZERO+pd.Timedelta(days=5)
 assert first.timestamp==f.ZERO+pd.Timedelta(days=6)

def test_balanced_joint_design_and_one_factor_grid():
 cases,members=study.registry(new);lookup={c['case_id']:c for c in cases}
 joint=[lookup[m['case_id']]['config'] for m in members if m['group']=='joint']
 assert len(cases)==121
 assert len({tuple(x[k] for k in study.GRID) for x in joint})==32
 assert len({tuple(sorted(c['config'].items())) for c in cases})==len(cases)
 for k in study.GRID:assert sum(m['case_id']=='B' for m in members if m['group']=='neighbor' and m['parameter']==k)==1
 cols=list(study.GRID)
 for k in cols:
  assert sum(x[k]==study.GRID[k][1][1] for x in joint)==16
 for i,x in enumerate(cols):
  for y in cols[i+1:]:
   for vx in [study.GRID[x][1][1],study.GRID[x][1][3]]:
    for vy in [study.GRID[y][1][1],study.GRID[y][1][3]]:assert sum(r[x]==vx and r[y]==vy for r in joint)==8

@pytest.mark.parametrize('kw',[{'ma_period':1},{'atr_floor':2},{'tighten_step':0},{'rsi_threshold':101}])
def test_invalid_parameters(kw):
 with pytest.raises(ValueError):new.Config(**kw)
