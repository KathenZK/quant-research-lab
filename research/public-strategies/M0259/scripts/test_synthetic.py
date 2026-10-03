#!/usr/bin/env python3
"""Synthetic unit tests only. Not market evidence or an added strategy trial."""
from pathlib import Path
import csv
import io
import numpy as np
import pandas as pd
from replay import simulate,indicators,load_qtp
from validate_independent import reference_indicators, oracle, compare_rows


def test(qtp):
    n=100
    for close in [np.full(n,100.),np.arange(n,dtype=float)+50,150-np.arange(n,dtype=float),100+np.sin(np.arange(n))]:
        d=pd.DataFrame({'close':close,'high':close+2,'low':close-1})
        s=indicators(d,qtp);ref=reference_indicators(d.astype(str).to_dict('records'))
        for k in ['rsi','bb_lower','bb_mid','bb_upper']:
            np.testing.assert_allclose(s[k],np.array([np.nan if r[k] is None else r[k] for r in ref]),atol=1e-8,rtol=1e-10)
        assert s.entry.tolist()==[r['entry'] for r in ref]
        assert s.exit.tolist()==[r['exit'] for r in ref]
    def ledger(bars,exit_signal=False,lag=1):
        rows=[]
        for i,(o,h,l,c) in enumerate(bars):
            rows.append({'ts':(pd.Timestamp('2022-12-31T23:00:00Z')+pd.Timedelta(hours=i)).strftime('%Y-%m-%dT%H:%M:%SZ'),'open':o,'high':h,'low':l,'close':c})
        d=pd.DataFrame(rows);s=pd.DataFrame({'entry':[True]+[False]*(len(rows)-1),'exit':[False]*len(rows)})
        if exit_signal:s.loc[1,'exit']=True
        return simulate(d,s,8,lag)
    # Warm-up last known signal fills first evaluation open. Budget includes fees.
    nav,trades,fills,amb,pos=ledger([(100,100,100,100),(100,105,99,103),(101,102,100,101)])
    assert fills.iloc[0].ts=='2023-01-01T00:00:00Z'
    assert abs(fills.iloc[0].cash_after-5000)<1e-8
    assert abs(pos['entry_budget']-95000)<1e-8
    assert pos and len(trades)==0
    # Entry and both risk thresholds on the same bar: stop wins.
    nav,trades,fills,amb,pos=ledger([(100,100,100,100),(100,120,70,110)])
    assert trades.iloc[0].exit_reason=='stoploss' and amb[0]['path_ambiguous']
    # Gap has known ordering. Stop/ROI range overlap does not imply path uncertainty.
    nav,trades,fills,amb,pos=ledger([(100,100,100,100),(100,105,99,103),(70,120,60,100)])
    assert trades.iloc[0].exit_reason=='stop_gap' and trades.iloc[0].exit_raw==70
    assert not amb[0]['path_ambiguous']
    nav,trades,fills,amb,pos=ledger([(100,100,100,100),(100,105,99,103),(115,120,70,100)])
    assert trades.iloc[0].exit_reason=='roi_gap' and trades.iloc[0].exit_raw==115
    assert not amb[0]['path_ambiguous']
    # Already-known signal exits at open, before the later risk path.
    nav,trades,fills,amb,pos=ledger([(100,100,100,100),(100,105,99,103),(101,120,70,100)],True)
    assert trades.iloc[0].exit_reason=='exit_signal' and trades.iloc[0].exit_raw==101
    # ROI is net of fees before exit slippage; 10% trigger realizes 9.978%.
    nav,trades,fills,amb,pos=ledger([(100,100,100,100),(100,112,99,111)])
    assert trades.iloc[0].exit_reason=='roi'
    assert abs(trades.iloc[0]['return']-0.09978)<1e-12
    # Extra one-bar delay uses the actual later open, not the signal price.
    nav,trades,fills,amb,pos=ledger([(100,100,100,100),(100,105,99,103),(102,105,100,103)],lag=2)
    assert fills.iloc[0].ts=='2023-01-01T01:00:00Z' and fills.iloc[0].raw_price==102
    assert min(nav.cash)>=0
    # Cross-check every hourly and exported daily account row on synthetic oscillating data.
    times=pd.date_range('2022-12-31T00:00:00Z',periods=1000,freq='h')
    close=100+15*np.sin(np.arange(1000)/13)+np.cos(np.arange(1000))
    opens=np.r_[close[0],close[:-1]]
    d=pd.DataFrame({'ts':times.strftime('%Y-%m-%dT%H:%M:%SZ'),'open':opens,
                    'high':np.maximum(opens,close)+.5,'low':np.minimum(opens,close)-.5,'close':close})
    src=d.astype(str).to_dict('records');ind=reference_indicators(src);sig=indicators(d,qtp)
    for fee,lag,bh in [(8,1,False),(0,1,False),(20,1,False),(8,2,False),(8,1,True)]:
        primary=simulate(d,sig,fee,lag,bh)
        independent=oracle(src,ind,fee/10000,lag,bh)
        for actual,expected in [(primary[0],independent[0]),(primary[2],independent[1]),(primary[1],independent[2])]:
            if not expected:assert actual.empty;continue
            rows=list(csv.DictReader(io.StringIO(actual.to_csv(index=False,float_format='%.12g'))))
            compare_rows(rows,expected)
        daily_primary=primary[0].groupby(primary[0].ts.str[:10]).tail(1)
        daily_ref=list({r['ts'][:10]:r for r in independent[0]}.values())
        compare_rows(list(csv.DictReader(io.StringIO(daily_primary.to_csv(index=False,float_format='%.12g')))),daily_ref)
    return {'status':'PASS','independent_synthetic_ledger_cases':5,'independent_daily_export_check':'PASS','test_type':'synthetic_unit_tests_only','indicator_paths':4,
            'execution_checks':['warmup-first-open','fee-inclusive-budget','no-terminal-liquidation','same-bar-stop-before-roi','gap-stop','gap-roi','signal-before-intrabar-risk','fee-aware-roi-with-slippage','extra-bar-delay','nonnegative-cash']}
if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--qtpylib',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    result=test(load_qtp(a.qtpylib));Path(a.out).write_text(json.dumps(result,indent=2)+'\n');print(result)
