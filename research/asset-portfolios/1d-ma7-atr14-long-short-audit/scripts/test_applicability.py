import numpy as np
import pandas as pd
from applicability_features import features
from analyze_applicability import masks,describe,bootstrap,prior_quartile


def bars(n=180):
    c=100*np.exp(.005*np.arange(n))
    return [dict(ts=i*86400000,open=float(x*.999),high=float(x*1.02),low=float(x*.98),close=float(x)) for i,x in enumerate(c)]


def test_features_known_values_and_future_price_volume_invariance():
    b=bars();q=np.linspace(1e6,2e6,len(b));a=features(b,q)
    assert abs(a.efficiency30.iloc[-1]-1)<1e-12
    assert a.trend_state.iloc[-1]==1 and a.chop30.iloc[-1]==0
    assert abs(a.liquidity30.iloc[-1]-np.median(q[-30:]))<1e-9
    prefix=features(b[:110],q[:110]);pd.testing.assert_frame_equal(a.iloc[:110],prefix)
    for x in b[110:]:
        for k in ['open','high','low','close']:x[k]*=20
    q[110:]*=1000
    pd.testing.assert_frame_equal(features(b,q).iloc[:110],prefix)


def test_direction_alignment_is_side_aware():
    t=pd.DataFrame(dict(trend_state=[1,-1,0,1,-1],momentum30=[.2,-.2,0,.2,-.2],side=[1,-1,1,-1,1]))
    for f in ['trend_aligned','momentum_aligned']:
        a,b=masks(t,f);assert a.tolist()==[True,True,False,False,False];assert (a^b).all()


def test_bankrupt_trade_stays_in_mean_and_blocks_finite_log_claim():
    t=pd.DataFrame(dict(symbol=['A','B'],month=['2024-01','2024-02'],ret_pct=[50.,-100.],equity_before=[1.,1.],equity_after=[1.5,0.]))
    s=describe(t)
    assert s['trades']==2 and s['bankruptcies']==1
    assert s['mean_return_pct']==-25 and s['mean_log_return_pct'] is None


def test_crossed_bootstrap_identical_paired_groups_have_zero_effect():
    t=pd.DataFrame([dict(symbol=f'S{i}',month=f'2024-{m:02d}',ret_pct=i-m,group=g) for i in range(15) for m in range(1,10) for g in [0,1]])
    r=bootstrap(t,t.group.eq(0),t.group.eq(1),seed=7)
    assert r['effect_pp']==0 and r['ci_low']==0 and r['ci_high']==0 and r['month_adjusted_pp']==0


def test_prior_selection_does_not_use_future_coverage_or_results():
    previous=pd.DataFrame(dict(symbol=['A','B','C','D'],return_pct=[1.,2.,3.,4.]))
    future=pd.DataFrame(dict(symbol=['A','B'],return_pct=[100.,200.]))
    cutoff,selected,pair=prior_quartile(previous,future)
    assert cutoff==3.25 and selected=={'D'} and not pair.selected.any()
    future=pd.DataFrame(dict(symbol=['C','D'],return_pct=[-100.,-99.]))
    cutoff2,selected2,pair2=prior_quartile(previous,future)
    assert cutoff2==cutoff and selected2==selected and pair2.loc[pair2.selected,'symbol'].tolist()==['D']
