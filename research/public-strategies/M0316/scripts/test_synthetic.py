#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
import copy,json,pathlib
import pandas as pd
from run_replay import replay,ms,write,ROOT,BAR_MS
S=json.loads((ROOT/'specs/protocol.json').read_text());CASE={'name':'synthetic','fee_bps':8,'delay_bars':1};results=[]
def run(rows,fee=8,start='2023-01-01T00:00:00Z'):
    d=pd.DataFrame(rows,columns=['open','high','low','close','entry_signal','exit_signal']);d['open_time']=[ms(start)+i*BAR_MS for i in range(len(d))];d['close_time']=d.open_time+BAR_MS-1
    s=copy.deepcopy(S);s['evaluation']['start']=start;s['evaluation']['end_exclusive']=pd.Timestamp(d.open_time.iloc[-1]+BAR_MS,unit='ms',tz='UTC').isoformat();return replay(d,s,{**CASE,'fee_bps':fee})
def ok(name):results.append(name)
# Existing signal close100, next bar never reaches100: limit genuinely unfilled.
x=run([[100,100,100,100,1,0],[110,112,105,110,0,0]]);assert len(x[2])==0 and x[4]['orders'][0]['status']=='terminal_cancelled';ok('unmarketable_limit_unfilled_terminal')
x=run([[100,100,100,100,1,0],[90,91,89,90,0,0]]);assert abs(x[2].iloc[0].fill_price-90.018)<1e-12;assert x[2].iloc[0].fill_price<=100;ok('favorable_buy_gap_slip_capped')
x=run([[100,100,100,100,1,0],[100,101,99,100,0,0]]);assert x[2].iloc[0].fill_price==100;ok('buy_slip_not_above_limit')
x=run([[100,100,100,100,1,0],[105,106,99,100,0,0]]);assert x[2].iloc[0].fill_price==100 and pd.isna(x[2].iloc[0].execution_time_utc);ok('intrabar_limit_exact_bounded_time')
x=run([[100,100,100,100,1,0],[105,106,60,80,0,0]]);assert list(x[2].reason)==['entry_signal','stoploss'];assert x[2].iloc[1].phase=='open_to_low';ok('same_entry_bar_limit_then_market_stop')
x=run([[100,100,100,100,1,0],[100,120,60,80,0,0]]);assert x[2].iloc[1].reason=='stoploss';ok('low_before_high_path_is_explicit')
x=run([[100,100,100,100,1,0],[100,104,99,102,0,0]]);assert x[2].iloc[1].reason=='trailing_stop';assert x[2].iloc[1].phase=='high_to_close';ok('fee_aware_trailing_same_entry_bar')
x=run([[100,100,100,100,1,0],[100,101.86,100,101.86,0,0]],fee=0);assert not any(e['event']=='trailing_activation' for e in x[4]['risk']);ok('exact_offset_no_positive_trailing')
x=run([[100,100,100,100,1,0],[100,101.861,100,101.861,0,0]],fee=0);assert any(e['event']=='trailing_activation' for e in x[4]['risk']);ok('strict_greater_offset_positive')
x=run([[100,100,100,100,1,0],[100,101.9,100,101.9,0,0]],fee=8);assert not any(e['event']=='trailing_activation' for e in x[4]['risk']);ok('fees_delay_trailing_activation')
rows=[[100,100,100,100,1,0],[100,100,100,100,1,0],[170,170,170,170,0,0]];x=run(rows);assert [e for e in x[4]['risk'] if e['event']=='open_state'][-1]['roi_suppressed'];assert len(x[2])==1;ok('entry_signal_suppresses_roi')
rows=[[100,100,100,100,1,0],[100,100,100,100,0,0],[170,170,170,170,0,0]];x=run(rows);assert list(x[2].reason)==['entry_signal','roi'];ok('roi_unsuppressed_opens_at_fee_aware_target')
x=run([[100,100,100,100,1,0],[100,101,99,100,0,1],[100,100,100,100,0,0]]);assert x[2].iloc[1].fill_price>=100 and x[2].iloc[1].reason=='exit_signal';ok('signal_limit_sell_cannot_cross_below_limit')
x=run([[100,100,100,100,1,0],[100,101,99,100,0,1],[90,95,60,80,0,0]]);assert x[2].iloc[1].reason=='stoploss' and x[4]['orders'][-1]['status']=='cancelled_by_risk';ok('unfilled_exit_competes_with_market_stop')
x=run([[100,100,100,100,1,0],[105,106,104,105,0,0],[95,96,94,95,0,0]]);assert len(x[2])==0 and x[4]['orders'][0]['status']=='timeout_unfilled';ok('timeout_does_not_auto_rehang')
x=run([[100,100,100,100,1,0],[100,100,100,100,0,0]],start='2023-03-24T08:00:00Z');assert x[2].iloc[0].execution_time_utc=='2023-03-24T14:00:00Z';ok('halt_open_resume14_not12')
x=run([[100,100,100,100,1,0],[105,106,99,100,0,0]],start='2023-03-24T04:00:00Z');assert x[2].iloc[0].execution_latest_utc=='2023-03-24T11:26:59.999000Z';ok('prehalt_intrabar_bound')
write(ROOT/'artifacts/C0-synthetic-validation.json',{'status':'PASS','cases':results,'count':len(results),'real_strategy_returns_computed':False,'method':'worker synthetic tests; independent reviewer separate'})
print(json.dumps(results))
