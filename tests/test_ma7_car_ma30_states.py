"""Deterministic boundaries and execution parity for the frozen MA30 overlay."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ma30_fixture', ROOT/'tests/test_ma7_car_admission_routing.py')
fixture = importlib.util.module_from_spec(spec); sys.modules[spec.name] = fixture; spec.loader.exec_module(fixture)
old, new = fixture.load('v4'), fixture.load('v5')

def cfg(mode='none'):
    return new.Config(reverse=False, progress_days=4, fee=.001, slip=.0004,
                      admission_routing=True, ma30_mode=mode)

def state(side=1):
    return {'side':side,'entry_reference':100.,'entry_price':100.,
            'extreme_price':100.,'no_new_extreme_days':0}

def row(side=1, movement=3., q=.1, distance7=.2, distance30=1., delta=3., day=1):
    c=100+side*movement;ma30=c-side*distance30*10
    return SimpleNamespace(timestamp=fixture.ZERO+pd.Timedelta(days=day), close=c,
        high=c+1,low=c-1,atr=10.,ma=c-side*distance7*10,ma30=ma30,
        prev_ma30=ma30-side*q*10,rsi=50.,sm_delta=side*delta,
        sm_previous_delta=0.,sm_previous_atr=10.,sm_previous_atr2=10.)

def observe(p,r,mode='both',profit=True):
    p['extreme_price']=(max if p['side']==1 else min)(p['extreme_price'],r.high if p['side']==1 else r.low)
    return new.ma30_exit_state_step(p,r,mode,profit)

@pytest.mark.parametrize('route',['v3','defense','extension'])
def test_off_preserves_v4_exact(route):
    raw,h=fixture.random_market();d=fixture.routes(old.features(raw),route)
    kw=dict(reverse=False,progress_days=4,fee=.001,slip=.0004,admission_routing=True)
    a=old.simulate(h,d,old.Config(**kw));b=new.simulate(h,d,new.Config(**kw))
    for k,v in a[0].items():assert b[0][k]==v
    for x,y in zip(a[1:],b[1:]):pd.testing.assert_frame_equal(x,y,check_exact=True)

@pytest.mark.parametrize('side',[-1,1])
@pytest.mark.parametrize('mode',['defense','extend','both'])
def test_directional_conflict_requires_pressure(side,mode):
    z=observe(state(side),row(side,q=-.1,distance7=-.1,movement=-1),mode,False)
    assert z['sm_defense']==(mode in {'defense','both'})
    assert not z['sm_healthy'] and not z['m30_suppress_short_tp']
    # A healthy price path inside an adverse intermediate slope isn't forcibly stopped.
    z=observe(state(side),row(side,q=-.1,distance7=.2),mode,True)
    assert not z['sm_defense']

@pytest.mark.parametrize('side',[-1,1])
@pytest.mark.parametrize('q,conflict',[(-.050001,True),(-.049999,False)])
def test_threshold_neighbors(side,q,conflict):
    z=observe(state(side),row(side,q=q,distance7=-.1),'defense',False)
    assert z['m30_conflict']==conflict and z['sm_defense']==conflict

@pytest.mark.parametrize('side',[-1,1])
@pytest.mark.parametrize('profit',[False,True])
def test_healthy_needs_three_held_days_and_profit(side,profit):
    p=state(side)
    for i in range(1,4):
        z=observe(p,row(side,movement=3*i,day=i),profit=profit)
        assert z['sm_healthy']==(i==3 and profit)
        assert z['m30_suppress_short_tp']==(i==3 and profit)
    assert p['sm_healthy_days']==int(profit)

@pytest.mark.parametrize('side',[-1,1])
def test_watch_protect_priority_and_fixed_atr(side):
    p=state(side);r=row(side,movement=25,delta=25,distance7=2.5)
    z=observe(p,r);assert z['sm_watch']=='WATCH' and not z['sm_protect']
    assert z['m30_suppress_short_tp'];a=z['sm_watch_atr']
    r=row(side,movement=15,delta=-10,q=-.1,distance7=.1,day=2);r.atr=20.
    z=observe(p,r);assert z['sm_watch']=='PROTECT' and z['sm_watch_atr']==a
    assert z['sm_transition']=='exhaustion_protect' and not z['m30_suppress_short_tp']
    z=observe(p,row(side,movement=30,day=3));assert z['sm_watch']=='PROTECT'

@pytest.mark.parametrize('side',[-1,1])
def test_loss_of_alignment_restores_short_tp(side):
    p=state(side);z=observe(p,row(side,movement=25,delta=25,distance7=2.5));assert z['m30_suppress_short_tp']
    z=observe(p,row(side,movement=26,delta=1,q=0,distance7=2.6,day=2))
    assert z['sm_watch']=='NORMAL' and not z['m30_suppress_short_tp']
    assert z['sm_transition']=='watch_alignment_lost'

@pytest.mark.parametrize('mode',['defense','extend','both'])
def test_full_account_ratchet_and_next_day(mode):
    raw,h=fixture.random_market();d=fixture.routes(old.features(raw),'v3')
    a=new.simulate(h,d,cfg(mode));s=a[3];later=s[s.full_holding_day]
    assert len(later)>0
    assert (later.timestamp==later.signal_day+pd.Timedelta(days=1)).all()
    assert (s.side*(s.new_stop-s.old_stop)>=-1e-12).all()
    assert (s.new_mult>=.5).all() and (s.new_mult<=s.old_mult).all()
    assert np.isclose(a[0]['ending_equity'],10000+a[1].net_pnl.sum())

def test_invalid_mode_and_mixed_routes_fail():
    with pytest.raises(ValueError):cfg('bad')
    with pytest.raises(ValueError):new.Config(ma30_mode='both')
    raw,h=fixture.random_market();d=fixture.routes(old.features(raw),'extension')
    with pytest.raises(ValueError):new.simulate(h,d,cfg('both'))

def test_future_prices_do_not_change_past_decisions():
    raw,h=fixture.random_market();d=fixture.routes(old.features(raw),'v3')
    a=new.simulate(h,d,cfg('both'));cut=d.timestamp.iloc[95]
    # Price changes occur strictly after cut, and all indicators are recomputed causally.
    raw2=raw.copy();raw2.loc[raw2.timestamp>cut,['open','high','low','close']]*=1.4
    h2=h.copy();h2.loc[h2.timestamp>cut+pd.Timedelta(days=1),['open','high','low','close']]*=1.4
    b=new.simulate(h2,fixture.routes(old.features(raw2),'v3'),cfg('both'))
    x=a[3][a[3].timestamp<=cut].reset_index(drop=True);y=b[3][b[3].timestamp<=cut].reset_index(drop=True)
    pd.testing.assert_frame_equal(x,y,check_exact=True)

@pytest.mark.parametrize('mode',['extend','both'])
def test_real_short_order_is_postponed_then_restored(mode):
    d,h=fixture.path(side=-1,closes=(20.,24.,26.,28.,25.),favorable=30.,ma=-20.,atr=10.)
    d['ma30']=d.close+10.;d['prev_ma30']=d.ma30+1.
    d['rsi']=10.;d['accel1']=True
    # Day 1 accelerates with alignment; day 2 loses MA30 alignment without retracing.
    d.loc[2:,'prev_ma30']=d.loc[2:,'ma30']
    prefix=pd.concat([d.iloc[[0]],d.iloc[[0]]],ignore_index=True)
    prefix['timestamp']=[fixture.ZERO-pd.Timedelta(days=2),fixture.ZERO-pd.Timedelta(days=1)]
    prefix['ready']=False;prefix['cross']=0;prefix['close']=100.
    d=pd.concat([prefix,d],ignore_index=True)
    d=fixture.routes(d,'v3')
    a=new.simulate(h,d,cfg('none'));b=new.simulate(h,d,cfg(mode))
    assert a[1].iloc[0].exit_time==fixture.ZERO+pd.Timedelta(days=2)
    assert b[1].iloc[0].exit_time==fixture.ZERO+pd.Timedelta(days=3)
    assert b[1].iloc[0].exit_reason=='accel1_rsi30'
    assert b[1].iloc[0].m30_short_tp_suppressed_count==1
    assert b[3].m30_short_tp_actually_suppressed.fillna(False).sum()==1
