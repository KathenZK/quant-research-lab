"""Adversarial timing/accounting tests. Artificial prices are fixtures only."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import numpy as np
import pandas as pd
import pytest
import backtest_public100_funding as f
import backtest_public100_b5 as b5
import diagnose_public100_boros as boros
import backtest_public100_source_corrections as corrections
from public100_r2_inputs import session,calendar

def sample(n=20):
    t=pd.date_range('2023-12-01',periods=n,freq='h',tz='UTC');bars=pd.DataFrame({'open':100.,'close':100.,'high':101.,'low':99.},index=t)
    events=pd.DataFrame({'funding_rate':.01,'markPrice':100.},index=t[::8]);return bars,events

@pytest.mark.parametrize('direction,expected',[(1,.98),(-1,1.02)])
def test_funding_sign_and_no_retroactive_first_payment(direction,expected):
    bars,events=sample();s=pd.Series(direction,index=events.index)
    eq,orders,payments,stats=f.simulate(bars,events,s,'D1_CODE_SPARSE',0)
    assert eq.iloc[-1]==pytest.approx(expected)
    assert pd.Timestamp(orders[0]['ts'])==bars.index[1]
    assert [pd.Timestamp(p['ts']) for p in payments]==list(events.index[1:])

def test_price_loss_is_counted_even_when_funding_is_received():
    bars,events=sample();bars.loc[bars.index[2]:,['open','close','high','low']]=[120.,120.,121.,119.]
    s=pd.Series(-1,index=events.index);eq,_,_,stats=f.simulate(bars,events,s,'D1_CODE_SPARSE',0)
    assert stats['funding_pnl_fraction_initial']>0 and stats['gross_price_pnl_fraction_initial']==pytest.approx(-.2)
    assert eq.iloc[-1]<1

def test_d5_fixed_hold_no_overlapping_full_account():
    bars,events=sample(32);s=pd.Series(-1,index=events.index)
    eq,orders,_,_=f.simulate(bars,events,s,'D5_BASE90_15_HOLD8',.0006)
    quantity=0.;entered=None
    for o in orders:
        time=pd.Timestamp(o['ts'])
        if o['reason']=='entry':
            assert abs(quantity)<1e-12;entered=time
        elif o['reason']=='close':assert time-entered==pd.Timedelta(hours=8)
        quantity+=o['quantity']
    assert abs(quantity)<1e-12

def test_zero_price_change_still_pays_two_sided_cost():
    bars,events=sample(4);events.funding_rate=0;s=pd.Series(1,index=events.index)
    eq,orders,_,_=f.simulate(bars,events,s,'D1_CODE_SPARSE',.001)
    assert len(orders)==2 and eq.iloc[-1]==pytest.approx((1-.001)/(1+.001))

def test_future_rates_do_not_change_past_signals():
    rng=np.random.default_rng(42);t=pd.date_range('2023-01-01',periods=240,freq='8h',tz='UTC');a=pd.DataFrame({'funding_rate':rng.normal(.0001,.0001,len(t))},index=t);b=a.copy();b.iloc[170:]=.1
    for variant in f.VARIANTS:
        sa,_=f.signals(a,variant);sb,_=f.signals(b,variant);pd.testing.assert_series_equal(sa.iloc[:170],sb.iloc[:170])

def test_d2_literal_threshold_does_not_create_trades_from_bps():
    _,events=sample(240);events.funding_rate=.0001
    for variant in ['D2_DEFAULT10_001','D2_EXAMPLE20_0015']:
        signal,meta=f.signals(events,variant);assert not signal.any() and meta['threshold_fraction']>=.01

def test_b5_original_counter_and_future_price_isolation():
    dates=pd.bdate_range('2009-01-01',periods=800);rng=np.random.default_rng(6);a=pd.DataFrame(100*np.exp(np.cumsum(rng.normal(.0002,.01,(800,len(b5.SYMS))),axis=0)),index=dates,columns=b5.SYMS);b=a.copy();b.iloc[700:]*=50
    wa,ra,records=b5.weights(a,22);wb,rb,_=b5.weights(b,22);start=np.flatnonzero(dates>=pd.Timestamp('2011-01-03'))[0]
    assert np.flatnonzero(ra)[0]==start+21 and np.all(np.diff(np.flatnonzero(ra))==22)
    assert np.allclose(wa[:701],wb[:701]) and np.array_equal(ra[:701],rb[:701])

def test_intraday_missing_bar_or_zero_volume_is_rejected():
    row=calendar('2026-08-05','2026-08-05').iloc[0];t=pd.date_range(row.open,row.close,freq='2min',inclusive='left');d=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,'volume':10.},index=t)
    assert len(session(d,row,2))==195
    with pytest.raises(AssertionError):session(d.drop(t[10]),row,2)
    d.loc[t[50],'volume']=0
    with pytest.raises(AssertionError):session(d,row,2)

def test_boros_exit_mark_can_erase_positive_funding_spread():
    estimate=boros.pnl(1,.20,.25,.10,168,.3)
    assert estimate==pytest.approx(.05*168/8760-.1*.3) and estimate<0

def test_boros_long_short_cashflows_are_opposite_before_fees():
    assert boros.pnl(1,.12,.08,.09,168,.2)==pytest.approx(-boros.pnl(-1,.12,.08,.09,168,.2))

def test_boros_maturity_has_no_remaining_rate_mtm():
    assert boros.pnl(1,.12,.08,2.,168,0)==pytest.approx((.08-.12)*168/8760)

def test_gem_us_absolute_hurdle_precedes_foreign_relative_winner():
    dates=pd.bdate_range('2018-01-01','2020-02-07')
    cl=pd.DataFrame(100.,index=dates,columns=['IVV','VEU','BND','BIL'])
    cl.loc['2020-01-31']=[90.,200.,100.,101.]
    _,_,decisions=corrections.weights(cl,cl,'C1_GEM_SOURCE_IVV_VEU_BND','2020-02-01')
    assert decisions[0]['target']=='BND'
    assert decisions[0]['last_input_date']=='2020-01-31'

def test_january_first_day_open_can_reverse_legacy_close_signal():
    dates=pd.bdate_range('2020-12-01','2021-02-05')
    cl=pd.DataFrame(100.,index=dates,columns=['SPY','BIL']);op=cl.copy()
    cl.loc['2021-01-01','SPY']=99.;cl.loc['2021-01-29','SPY']=99.5
    _,_,decisions=corrections.weights(cl,op,'A36_JAN_FIRST_OPEN','2021-01-01')
    assert cl.loc['2021-01-29','SPY']>cl.loc['2021-01-01','SPY']
    assert decisions[-1]['target']=='BIL' and decisions[-1]['january_return']==pytest.approx(-.005)

def test_source_corrections_never_use_future_close_for_decisions():
    dates=pd.bdate_range('2008-01-01','2012-08-31');rng=np.random.default_rng(16)
    a=pd.DataFrame(100*np.exp(np.cumsum(rng.normal(0,.01,(len(dates),6)),axis=0)),index=dates,columns=['SPY','BIL','IVV','VEU','BND','EFA']);b=a.copy();b.loc['2012-02-01':]*=10
    for variant in ['A36_JAN_FIRST_OPEN','A36_PREVIOUS_DEC_CLOSE','C1_GEM_SOURCE_IVV_VEU_BND']:
        wa,ra,_=corrections.weights(a,a,variant);wb,rb,_=corrections.weights(b,a,variant)
        past=dates<=pd.Timestamp('2012-02-01')
        assert np.array_equal(wa[past],wb[past]) and np.array_equal(ra[past],rb[past])
