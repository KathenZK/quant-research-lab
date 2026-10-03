#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic-only executor assertions, separate from actual market results."""
import json,pathlib
import numpy as np,pandas as pd
from run_replay import replay,write,ms,HALT_BAR,HALT_RESUME,HALT_PREVIOUS
ROOT=pathlib.Path(__file__).resolve().parents[1]
def spec(n,start='2023-01-01T00:00:00Z'):
    return {'evaluation':{'start':start,'end_exclusive':pd.Timestamp(ms(start)+n*14400000,unit='ms',tz='UTC').isoformat()},'execution':{'initial_cash':100000,'slippage_bps':0,'cash_budget_fraction':.95},'risk':{'minimal_roi':{'0':.598,'644':.166,'3269':.115,'7289':0},'stoploss':-.128}}
def data(n,start='2023-01-01T00:00:00Z'):
    t=np.arange(ms(start),ms(start)+n*14400000,14400000)
    return pd.DataFrame({'open_time':t,'close_time':t+14399999,'open':100.,'high':100.,'low':100.,'close':100.,'entry_signal':[True]+[False]*(n-1),'exit_signal':False})
def main():
    case={'name':'synthetic','fee_bps':0,'delay_bars':1};checks=[]
    d=data(5);d.loc[1,['high','low']]=[170,70];n,dy,t,m,e=replay(d,spec(5),case)
    assert t.side.tolist()==['BUY','SELL'] and t.reason.iloc[1]=='stoploss' and abs(t.reference_price.iloc[1]-87.2)<1e-10;checks.append('same-bar stop-first when both high and low touch; no same-bar reentry')
    d=data(5);d.loc[2,['open','high','low','close']]=[60,80,60,70];_,_,t,_,_=replay(d,spec(5),case)
    assert t.reason.iloc[1]=='stoploss' and t.phase.iloc[1]=='open_gap' and t.reference_price.iloc[1]==60;checks.append('gap-through stop sells at observed worse open')
    d=data(5);d.loc[2,['open','high','low','close']]=[170,180,70,100];_,_,t,_,_=replay(d,spec(5),case)
    assert t.reason.iloc[1]=='roi' and t.phase.iloc[1]=='open_gap';checks.append('chronological open ROI gap precedes subsequent low stop')
    d=data(8);d.loc[3,'high']=120;d.loc[4,'high']=120;_,_,t,_,e=replay(d,spec(8),case)
    assert int(t.bar_index.iloc[1])==4 and int(t.roi_step_minutes.iloc[1])==644;checks.append('644 minute tier not used for preceding whole-bar high; first usable open at720 minutes')
    assert e[0]['minutes']==644 and e[0]['observed_from_utc']=='2023-01-01T16:00:00Z';checks.append('native minute boundary retained in candidate log')
    start='2023-03-24T08:00:00Z';d=data(3,start);_,_,t,_,_=replay(d,spec(3,start),case)
    assert t.execution_time_utc.iloc[0]=='2023-03-24T14:00:00Z';checks.append('halt bucket nominal12 open modeled at14 resume, never12')
    d=data(8);d.entry_signal=True;_,_,t,_,_=replay(d,spec(8),{**case,'delay_bars':2})
    assert int(t.bar_index.iloc[0])==2;checks.append('extra one-bar entry delay')
    start='2023-03-24T04:00:00Z';d=data(4,start);d.loc[1,['high','low']]=[170,70];_,_,t,_,_=replay(d,spec(4,start),case)
    assert t.execution_latest_utc.iloc[1]=='2023-03-24T11:26:59.999000Z';checks.append('08h risk interval capped before actual halt, no fabricated halt fill')
    d=data(34);d.loc[14,'high']=112;d.loc[15,'high']=112;_,_,t,_,_=replay(d,spec(34),case)
    assert int(t.bar_index.iloc[1])==15 and int(t.roi_step_minutes.iloc[1])==3269;checks.append('3269 minute tier deferred to first later open')
    d=data(34);_,_,t,_,_=replay(d,spec(34),case)
    assert int(t.bar_index.iloc[1])==32 and int(t.roi_step_minutes.iloc[1])==7289;checks.append('7289 minute ROI0 deferred, open equal target exits')
    d=data(34);sp=spec(34);sp['execution']['slippage_bps']=2;_,_,t,_,_=replay(d,sp,{**case,'fee_bps':8})
    assert len(t)==1;checks.append('ROI0 fee-adjusted target not equated to raw entry reference')
    d=data(34);d.loc[32,['open','high','low','close']]=[101,101,100,100];sp=spec(34);sp['execution']['slippage_bps']=2;_,_,t,_,_=replay(d,sp,{**case,'fee_bps':8})
    assert t.reason.iloc[1]=='roi' and t.fill_price.iloc[1]<t.reference_price.iloc[1];checks.append('adverse exit slippage applied after fee-aware ROI target')
    receipt={'status' :'PASS','synthetic_only':True,'uses_actual_market_returns':False,'checks':checks,'production_engine_modified':False}
    print(json.dumps(receipt,indent=2));return receipt
if __name__=='__main__':main()
