import math
import numpy as np
import baseline_engine as baseline
from engine import execute, gross_oracle, VARIANTS


def sample(n=180, seed=7):
    rng=np.random.default_rng(seed)
    c=100*np.exp(np.cumsum(rng.normal(0,.04,n)))
    o=np.r_[100,c[:-1]]*np.exp(rng.normal(0,.01,n))
    return [dict(ts=i*86400000,end_ts=(i+1)*86400000-1,open=float(o[i]),
                 close=float(c[i]),high=float(max(o[i],c[i])*1.02),
                 low=float(min(o[i],c[i])*.98)) for i in range(n)]


def controlled():
    b=[dict(ts=i*86400000,open=100.,high=101.,low=99.,close=100.) for i in range(19)]
    ma=[100.]*19;atr=[20.]*19;slope=[0.]*19
    b[13]['close']=101.;b[14]['close']=99.;slope[14]=-1.
    b[15].update(open=100.,high=101.,low=89.,close=90.)
    b[16].update(open=90.,high=95.,low=79.,close=80.)
    b[17].update(open=80.,high=90.,low=79.,close=85.)
    b[18].update(open=85.,high=90.,low=79.,close=80.)
    return b,(ma,atr,[None]*19,slope)


def test_baseline_and_independent_oracle():
    for seed in [4,7,18]:
        b=sample(seed=seed)
        for fee,slip in [(0,0),(.001,.0004),(.001,.0008)]:
            old=baseline.execute(b,mode='causal',fee=fee,slip=slip)
            new=execute(b,'long',fee=fee,slip=slip)
            assert np.allclose(old['nav'],new['nav'],atol=1e-12,rtol=1e-12)
            assert [(t['entry_idx'],t['exit_idx']) for t in old['trades']]==[(t['entry_idx'],t['exit_idx']) for t in new['trades']]
        for variant in VARIANTS:
            r=execute(b,variant,fee=0,slip=0);tape,nav=gross_oracle(b,variant)
            assert [(t['entry_idx'],t['exit_idx'],t['side'],t['entry_price'],t['exit_price']) for t in r['trades']]==tape
            assert np.allclose(r['nav'],nav,atol=1e-12,rtol=1e-12)


def test_short_linear_pnl_and_fees():
    b,ind=controlled();r=execute(b,'short',fee=.001,slip=.0004,indicator_override=ind)
    assert len(r['trades'])==1
    entry=100*(1-.0004);exit_fill=80*(1+.0004);q=1/(entry*1.001)
    expected=1-q*entry*.001+q*(entry-exit_fill)-q*exit_fill*.001
    assert math.isclose(r['nav'][-1],expected,rel_tol=1e-13)
    gross=execute(b,'short',fee=0,slip=0,indicator_override=ind)
    assert math.isclose(gross['nav'][-1],1.2)  # Not 100/80=1.25.


def test_reverse_uses_post_exit_capital_and_two_fees():
    b,ind=controlled();b[16]['close']=101.;ind[3][16]=1.;b[17].update(open=102.,high=107.,low=100.,close=106.)
    b[18].update(open=106.,high=111.,low=104.,close=110.)
    r=execute(b,'reverse',fee=.001,slip=.0004,indicator_override=ind)
    assert len(r['trades'])==2
    t,u=r['trades'];assert t['reason']=='reverse_signal' and u['reversal_entry']
    assert t['exit_idx']==u['entry_idx']==17 and u['equity_before']==t['equity_after']
    assert t['exit_fee']>0 and u['entry_fee']>0
    assert math.isclose(u['units'],t['equity_after']/(u['entry_price']*1.001))
    assert len(execute(b,'both',indicator_override=ind)['trades'])==1


def test_gap_stop_and_entry_day_stop():
    b,ind=controlled();b[16].update(open=150.,high=155.,low=145.,close=150.)
    t=execute(b,'short',fee=0,slip=0,indicator_override=ind)['trades'][0]
    assert t['reason']=='gap_stop' and t['exit_price']==150. and t['ret_pct']==-50.
    b,ind=controlled();b[15].update(open=100.,high=135.,low=90.,close=120.)
    t=execute(b,'short',fee=0,slip=0,indicator_override=ind)['trades'][0]
    assert t['entry_idx']==t['exit_idx']==15 and t['exit_price']==130.


def test_bankruptcy_absorbing_and_gap_deficit_retained():
    b,ind=controlled();ind[1][:]=[100.]*19
    b[16].update(open=100.,high=220.,low=95.,close=210.)
    r=execute(b,'reverse',fee=0,slip=0,indicator_override=ind)
    assert r['metrics']['bankrupt'] and r['nav'][16:]==[0.,0.,0.]
    assert r['trades'][0]['reason']=='economic_bankruptcy'
    b[16]['open']=220.
    r=execute(b,'reverse',fee=0,slip=0,indicator_override=ind)
    assert r['trades'][0]['uncapped_equity_after']<0 and r['nav'][-1]==0


def test_no_stop_reverse_without_signal_and_invalid_mask():
    b,ind=controlled();b[16].update(open=150.,high=155.,low=145.,close=150.)
    assert len(execute(b,'reverse',indicator_override=ind)['trades'])==1
    mask=[True]*19;mask[14]=False
    assert not execute(b,'reverse',indicator_override=ind,valid_mask=mask)['trades']


def test_short_trailing_uses_prior_close_and_open_stop_priority():
    b,ind=controlled()
    # Day 15 high exceeds the newly computed 90 stop, but the active stop is 130.
    ind[0][15]=60.
    r=execute(b,'short',fee=0,slip=0,indicator_override=ind)
    assert r['trades'][0]['exit_idx']==16 and r['trades'][0]['reason']=='gap_stop'
    # A resting short gap stop executes before an already-scheduled reversal.
    b,ind=controlled();b[16]['close']=101.;ind[3][16]=1.
    b[17].update(open=150.,high=155.,low=145.,close=150.)
    r=execute(b,'reverse',fee=0,slip=0,indicator_override=ind)
    assert r['trades'][0]['reason']=='gap_stop'
    assert r['trades'][1]['reversal_entry'] and r['trades'][1]['entry_idx']==17
    assert r['trades'][1]['equity_before']==r['trades'][0]['equity_after']


def test_prefix_future_mutation_and_stop_monotonicity():
    b=sample()
    for v in VARIANTS:
        full=execute(b,v,force_end=False)
        for k in [40,90,150]:
            p=execute(b[:k],v,force_end=False)
            assert p['events']==[e for e in full['events'] if e['i']<k]
            assert p['nav']==full['nav'][:k]
        altered=[dict(x) for x in b]
        for x in altered[90:]:
            for key in ['open','close','high','low']:x[key]*=10
        assert execute(altered,v,force_end=False)['nav'][:90]==full['nav'][:90]
        for t in full['trades']:
            st=full['active_stops'][t['entry_idx']:t['exit_idx']]
            assert all(t['side']*(y-x)>=0 for x,y in zip(st,st[1:]))
