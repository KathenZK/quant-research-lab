from dataclasses import replace
from pathlib import Path
import importlib.util
import math
import sys
import numpy as np
import pandas as pd
import pytest
from engine import Config, CANDIDATES, features, replay, signal

def fixture(n=40):
    f=pd.DataFrame({'ts':pd.date_range('2020-01-01',periods=n,tz='UTC'),
        'open':100.,'high':101.,'low':99.,'close':100.,'quote_volume':2e7,
        'eligible':True,'research_segment_id':0,'research_window_valid':True})
    f=features(f)
    f['ma7']=100.;f['atr14']=10.;f['ma7_delta2']=1.;f['ma30']=90.;f['slow_slope']=1.
    return f

def prices(f,i,opening,close,low=None,high=None):
    f.loc[i,['open','close','low','high']]=[opening,close,min(opening,close)-1 if low is None else low,max(opening,close)+1 if high is None else high]

def test_linear_short_hand_accounting():
    f=fixture(16);prices(f,14,100,90);prices(f,15,100,80)
    cfg=Config('C0',fee=.001,slip=.0004)
    r=replay(f,cfg,start_idx=15,warmup=15)
    entry=100*(1-.0004);u=1/(entry*1.001);exit=80*(1+.0004)
    expected=1-u*entry*.001+u*(entry-exit)-u*exit*.001
    assert r['metrics']['equity']==pytest.approx(expected,abs=1e-12)
    assert r['trades'][0]['side']==-1

def test_reversal_two_fill_fees():
    f=fixture(17);prices(f,14,100,110);prices(f,15,100,90);prices(f,16,90,81)
    cfg=Config('C0',fee=.001,slip=0)
    r=replay(f,cfg,start_idx=15,warmup=15)
    u=1/(100*1.001);e=1-u*.1+u*(90-100)-u*90*.001
    u2=e/(90*1.001);expected=e-u2*90*.001+u2*(90-81)-u2*81*.001
    assert r['metrics']['equity']==pytest.approx(expected)
    assert len(r['trades'])==2 and r['trades'][0]['reason']=='reverse_signal'
    assert r['trades'][1]['reversal_entry']
    assert all(t['entry_fee']>0 and t['exit_fee']>0 for t in r['trades'])

def test_half_risk_cash_retained():
    f=fixture(17);prices(f,14,100,110);prices(f,15,100,90);prices(f,16,90,81)
    r=replay(f,Config('C0',fee=0,slip=0,size=.5),start_idx=15,warmup=15)
    assert r['metrics']['equity']==pytest.approx(.95*1.05)

def test_short_bankruptcy_absorbing_and_gap_deficit():
    for opening,high,reason in [(100,250,'economic_bankruptcy'),(250,251,'gap_stop')]:
        f=fixture(19);prices(f,14,100,90);prices(f,15,100,90)
        prices(f,16,opening,100,high=high)
        r=replay(f,Config('C0',fee=0,slip=0),start_idx=15,warmup=15)
        assert r['metrics']['bankrupt'] and r['nav'][16:]==[0.,0.,0.]
        assert r['trades'][0]['reason']==reason
        if opening==250:assert r['trades'][0]['uncapped_equity_after']==pytest.approx(-.5)

def test_prior_known_initial_stop_and_close_trailing_lag():
    f=fixture(17);prices(f,13,110,110);prices(f,14,110,110)
    prices(f,15,110,150,low=100,high=180);prices(f,16,115,116)
    r=replay(f,Config('C4',fee=0,slip=0),start_idx=15,warmup=15)
    assert r['active_stops'][15]==90
    assert r['trades'][0]['exit_idx']==16 and r['trades'][0]['exit_price']==115
    assert r['trades'][0]['reason']=='gap_stop'

def test_entry_day_stop_charges_roundtrip():
    f=fixture(16);prices(f,13,110,110);prices(f,14,110,110);prices(f,15,100,80,low=70)
    r=replay(f,Config('C1',fee=.001,slip=0),start_idx=15,warmup=15)
    t=r['trades'][0]
    assert t['entry_idx']==t['exit_idx']==15 and t['exit_raw_price']==90
    assert t['entry_fee']>0 and t['exit_fee']>0

def test_gap_past_entry_stop_not_cancelled():
    f=fixture(16);prices(f,13,110,110);prices(f,14,110,110);prices(f,15,80,80)
    r=replay(f,Config('C1',fee=.001,slip=0),start_idx=15,warmup=15)
    t=r['trades'][0];assert t['entry_price']==t['exit_price']==80 and t['equity_after']<1

def test_confirmed_reversal_and_c5_flat_wait():
    f=fixture(20);prices(f,13,110,110);prices(f,14,110,110);prices(f,15,110,90);prices(f,16,90,90)
    f.loc[15:,'ma7_delta2']=-1;f.loc[15:,'ma30']=100;f.loc[15:,'slow_slope']=-1
    for i in range(17,20):prices(f,i,90,90)
    direct=replay(f,Config('C4',fee=0,slip=0,initial_atr=10,trail_atr=10),start_idx=15,warmup=15)
    wait=replay(f,Config('C5',fee=0,slip=0,initial_atr=10,trail_atr=10),start_idx=15,warmup=15)
    assert direct['trades'][1]['entry_idx']==17
    assert wait['trades'][0]['exit_idx']==17 and wait['trades'][1]['entry_idx']==19

def test_delay_keeps_old_stop_active():
    f=fixture(18);prices(f,13,110,110);prices(f,14,110,110);prices(f,15,110,110);prices(f,16,110,80,low=70)
    r=replay(f,Config('C1',delay=2,fee=0,slip=0),start_idx=15,warmup=15)
    assert r['trades'][0]['entry_idx']==16 and r['trades'][0]['exit_idx']==16
    assert r['trades'][0]['signal_idx']==14

@pytest.mark.parametrize('candidate',CANDIDATES)
def test_prefix_invariance_and_trade_product(candidate):
    rng=np.random.default_rng(20260908);c=100*np.exp(np.cumsum(rng.normal(0,.06,250)))
    f=fixture(250);f['open']=np.r_[100.,c[:-1]];f['close']=c
    f['high']=np.maximum(f.open,c)*1.03;f['low']=np.minimum(f.open,c)*.97;f=features(f)
    cfg=Config(candidate)
    r=replay(f,cfg,start_idx=121,force_end=False)
    for n in [150,190,230]:
        p=replay(f.iloc[:n],cfg,start_idx=121,force_end=False)
        assert p['nav']==r['nav'][:n]
        assert p['events']==[e for e in r['events'] if e['i']<n]
    closed=replay(f,cfg,start_idx=121)
    assert math.prod(t['equity_after']/t['equity_before'] for t in closed['trades'])==pytest.approx(closed['nav'][-1])
    assert all(t['entry_idx']==t['signal_idx']+1 for t in closed['trades'])

def test_masks_gaps_and_unsorted_rejected():
    f=fixture(150)
    for bad in [f.iloc[::-1],f.drop(70),f.assign(eligible=False),f.assign(research_segment_id=np.arange(150))]:
        with pytest.raises(AssertionError):features(bad)
    f['research_window_valid']=False
    r=replay(f,Config('C0'))
    assert r['trades']==[]

def test_compensated_sum_exact_boundary_regression():
    # A real 1INCH strict-equality boundary must not become a spurious cross.
    from run_research import INPUT, read_frame
    import json
    f=read_frame('1INCH/USDT:USDT',json.loads((INPUT/'frame-manifest.json').read_text()))
    f=features(f[f.ts>=pd.Timestamp('2024-12-05',tz='UTC')])
    close=f.close.tolist()
    for i in range(6,len(f)):
        assert f.ma7.iloc[i]==sum(close[i-6:i+1])/7
    r=replay(f,Config('B0'),start_idx=0,warmup=15)
    assert r['metrics']['return_pct']==pytest.approx(-56.439987817896885,abs=1e-10)

def test_asset_time_split_purge_and_embargo():
    from statistical_review import split_trades
    rows=[{'symbol':'DEV','asset_fold':20,'signal_ts':'2023-09-01','exit_ts':'2023-10-01'},
          {'symbol':'CROSS','asset_fold':20,'signal_ts':'2023-09-01','exit_ts':'2024-01-02'},
          {'symbol':'EMBARGO','asset_fold':20,'signal_ts':'2023-11-20','exit_ts':'2023-12-02'},
          {'symbol':'MID','asset_fold':65,'signal_ts':'2024-03-01','exit_ts':'2024-03-07'},
          {'symbol':'HELD','asset_fold':92,'signal_ts':'2025-03-01','exit_ts':'2025-03-07'},
          {'symbol':'WRONG_ASSET','asset_fold':20,'signal_ts':'2025-03-01','exit_ts':'2025-03-07'}]
    splits=split_trades(pd.DataFrame(rows))
    assert list(splits['development'].symbol)==['DEV']
    assert list(splits['middle'].symbol)==['MID']
    assert list(splits['held'].symbol)==['HELD']

def test_two_way_cluster_reduces_to_single_cluster_when_groups_identical():
    from statistical_review import clustered_ols
    x=np.array([[1.,v] for v in range(1,9)])
    y=np.array([3.,4.,7.,6.,10.,13.,12.,17.]);groups=np.repeat(np.arange(4),2)
    beta,cov,_=clustered_ols(x,y,groups,groups)
    bread=np.linalg.inv(x.T@x);resid=y-x@beta
    sums=np.array([np.sum(x[groups==i]*resid[groups==i,None],axis=0) for i in range(4)])
    expected=bread@(sums.T@sums)@bread*(4/3)*(7/6)
    np.testing.assert_allclose(cov,expected,rtol=1e-10,atol=1e-12)

def test_bh_correction_unsorted_known_values():
    from statistical_review import bh_qvalues
    np.testing.assert_allclose(bh_qvalues([.5,.02,.01]),[.5,.03,.03])

def test_filter_exit_wait_and_reentry_are_replayed():
    f=fixture(24)
    for i in range(13,24):prices(f,i,110,110)
    f['liquidity90']=2e7;f.loc[16:19,'liquidity90']=1e6
    r=replay(f,Config('C3',filter_name='liquidity',fee=.001,slip=0),start_idx=15,warmup=15)
    assert r['trades'][0]['reason']=='filter_exit' and r['trades'][0]['exit_idx']==17
    assert r['trades'][1]['entry_idx']==21 and r['metrics']['rejected_signals']>0
    assert r['trades'][1]['equity_before']<1

def test_stock_pit_available_times_never_exceed_decision():
    root=Path(__file__).resolve().parents[1]
    f=pd.read_csv(root/'artifacts/stock-fundamentals-availability-20260908/daily-pit-availability.csv')
    decision=pd.to_datetime(f.signal_close_utc,utc=True)
    for col in ['profit','operating_cash','revenue']:
        known=pd.to_datetime(f[col+'_accepted_utc'],utc=True)
        assert (known.dropna()<=decision[known.notna()]).all()

@pytest.mark.parametrize('variant,candidate',[('long','B0'),('short','B1'),('both','B2'),('reverse','B3')])
def test_immutable_baseline_parity(variant,candidate):
    root=Path('/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/1d-ma7-atr14-long-short-audit/scripts')
    sys.path.append(str(root))
    spec=importlib.util.spec_from_file_location('frozen_audit_engine',root/'engine.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    rng=np.random.default_rng(43);c=100*np.exp(np.cumsum(rng.normal(.0001,.07,600)))
    f=fixture(600);f['open']=np.r_[100.,c[:-1]];f['close']=c
    f['high']=np.maximum(f.open,c)*1.02;f['low']=np.minimum(f.open,c)*.98;f=features(f)
    bars=[{'ts':int(r.ts.value//1000000),'open':r.open,'high':r.high,'low':r.low,'close':r.close} for r in f.itertuples()]
    for fee,slip in [(0,0),(.001,.0004),(.001,.0008)]:
        r=replay(f,Config(candidate,fee=fee,slip=slip),start_idx=0,warmup=15)
        o=old.execute(bars,variant,fee=fee,slip=slip)
        np.testing.assert_allclose(r['nav'],o['nav'],atol=1e-10,rtol=1e-12)
        assert [(t['entry_idx'],t['exit_idx'],t['side']) for t in r['trades']]==[(t['entry_idx'],t['exit_idx'],t['side']) for t in o['trades']]
