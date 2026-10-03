#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic fixtures only. No real-market research results."""
import copy,json,pathlib
import numpy as np
import pandas as pd
import run_replay as e
import validate_independent as v
from check_causality import original_functions

def check():
    x=pd.Series([np.nan,1.,1.,2.,2.,1.]);y=pd.Series([np.nan,1.,1.,1.,2.,2.])
    assert list(e.Q.crossed_above(x,y))==[False,False,False,True,False,False]
    z=pd.DataFrame({'open_time':np.arange(1672531200000,1672531200000+8*14400000,14400000),'open':100.,'high':101.,'low':99.,'close':100.,'volume':1.,'entry_signal':0,'exit_signal':0});z['close_time']=z.open_time+14400000-1;z.loc[0,'entry_signal']=1
    spec={'evaluation':{'start':'2023-01-01T00:00:00Z','end_exclusive':'2023-01-02T08:00:00Z'},'execution':{'initial_cash':100000,'slippage_bps':0,'cash_budget_fraction':.95},'risk':{'stoploss':-.2,'minimal_roi':{'0':.5}}};case={'fee_bps':8,'delay_bars':1}
    names=[]
    for name,ohlc,exit_signal,want,px in [('stop',(100,110,75,90),False,'stoploss',80),('roi',(100,160,90,150),False,'roi',100*1.0008*1.5/.9992),('dual',(100,160,75,110),False,'stoploss',80),('gap_stop',(70,100,60,90),False,'stoploss',70),('gap_roi',(160,170,70,100),False,'roi',160),('signal_priority',(100,170,60,90),True,'exit_signal',100)]:
        a=z.copy();a.loc[2,['open','high','low','close']]=ohlc;a.loc[1,'exit_signal']=int(exit_signal)
        nav,day,t,m=e.replay(a,spec,case);s=t[t.side=='SELL'].iloc[0];assert s.reason==want;assert abs(s.reference_price-px)<1e-10
        assert abs(t.iloc[0].notional+t.iloc[0].fee-95000)<1e-8;assert nav.cash.min()>=0
        assert t.iloc[0].bar_index==1 and t.iloc[0].signal_bar_index==0
        # Independent implementation verifies toy ledger too.
        rows=a.astype(str).to_dict('records');sig=(None,None,list(a.entry_signal),list(a.exit_signal));curve,daily,events,metrics=v.ledger(rows,sig,spec,case)
        for r,s in zip(events,t.to_dict('records')):
            for key in ('fill_price','quantity','fee','cash_after'):v.close(r[key],s[key])
        names.append(name)
    slippery=copy.deepcopy(spec);slippery['execution']['slippage_bps']=2
    a=z.copy();a.loc[2,['open','high','low','close']]=[100,170,90,150]
    _,_,t,_=e.replay(a,slippery,case)
    assert abs(t.iloc[0].fill_price-100.02)<1e-10
    target=t.iloc[0].fill_price*1.0008*1.5/.9992
    assert abs(t.iloc[1].fill_price-target*.9998)<1e-10
    net=(t.iloc[1].notional-t.iloc[1].fee)/(t.iloc[0].notional+t.iloc[0].fee)-1
    assert abs(net-.4997)<1e-10
    delayed=dict(case,delay_bars=2);_,_,late,_=e.replay(z,slippery,delayed)
    assert late.iloc[0].bar_index==2 and late.iloc[0].signal_bar_index==0
    assert abs(late.iloc[0].fill_price-100.02)<1e-10
    names.extend(['baseline_2bps_both_sides','roi_net_after_slip_49.97pct','extra_one_bar_delay'])
    # Synthetic halted-open fixture: signal from 08:00 bar is due at nominal
    # 12:00, but modeled resumption open is 14:00. Never backdate the fill.
    h=z.copy();h['entry_signal']=0;h.loc[2,'entry_signal']=1
    halted=copy.deepcopy(slippery);nominal=int(h.iloc[3].open_time);resume=nominal+2*3600000
    halted['execution']['open_execution_overrides']={str(nominal):{'effective_open_ms':resume,'basis':'resume_1h_open_proxy'}}
    _,_,fills,_=e.replay(h,halted,case)
    assert int(fills.iloc[0].bar_index)==3 and fills.iloc[0].bar_open_utc==e.iso(nominal)
    assert fills.iloc[0].execution_time_utc==e.iso(resume)
    assert fills.iloc[0].execution_earliest_utc==e.iso(resume)
    at13=e.replay(h,halted,case,closed_bar_cutoff_ms=nominal+3600000)[2]
    assert len(at13)==0
    names.append('halted_12h_open_deferred_to14h_no_fill_at13h_closed_bar_cutoff')
    prices=100+np.sin(np.arange(100)*.31)*10+np.arange(100)*.01
    q=pd.DataFrame({'open':prices,'high':prices+1,'low':prices-1,'close':prices,'volume':1.});q.loc[30:33,'volume']=0
    feat=e.features(q);orig=original_functions(q);ind=v.indicators(q.astype(str).to_dict('records'))
    for col in ('ema8','ema21'):np.testing.assert_array_equal(feat[col],orig[col])
    for j,col in enumerate(('ema8','ema21')):
        for n,b in enumerate(ind[j]):
            if b is None:assert np.isnan(feat[col].iloc[n])
            else:v.close(feat[col].iloc[n],b,1e-10)
    assert list(feat.entry_signal)==list(orig.enter_long.fillna(0))==[int(x) for x in ind[2]]
    assert list(feat.exit_signal)==list(orig.exit_long.fillna(0))==[int(x) for x in ind[3]]
    return {'status':'PASS','test_type':'SYNTHETIC_UNIT_TEST_NOT_BACKTEST','risk_scenarios':names,'indicator_checks':['TA-Lib SMA seed / alpha2/(N+1) Decimal parity','cross equality and NaN','volume>0 filter','original pinned source method parity'],'fee_budget':'95% inclusive; no negative cash','timing':'first close signal fills actual next open'}
if __name__=='__main__':print(json.dumps(check(),indent=2))
