#!/usr/bin/env python3
"""Synthetic order lifecycle and ledger boundaries only. No market input."""
import copy,json,resource
from pathlib import Path
import numpy as np
import pandas as pd
from replay_engine import replay,ms,BAR_MS,write
R=Path(__file__).resolve().parent
BASE=json.loads((R/'planned-protocol.json').read_text())

def fixture(n=8):
    t=ms('2024-01-01T00:00:00Z')+np.arange(n)*BAR_MS
    return pd.DataFrame({'open_time':t,'open':100.,'high':100.1,'low':99.9,'close':100.,'enter_long':False,'exit_long':False})
def spec_for(d):
    p=copy.deepcopy(BASE);p['input_expected_only']['evaluation_start']=pd.Timestamp(int(d.open_time.iloc[0]),unit='ms',tz='UTC').isoformat();p['input_expected_only']['evaluation_end_exclusive']=pd.Timestamp(int(d.open_time.iloc[-1])+BAR_MS,unit='ms',tz='UTC').isoformat();return p
def go(d,case=None):
    for k in ['open','close']:assert (d[k]>=d.low).all() and (d[k]<=d.high).all()
    return replay(d,spec_for(d),case or {'name':'base','fee_bps_per_side':8,'delay_bars':1})
def run():
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3)); checks=[]; fixtures={}
    def save(name,d,case=None):
        r=go(d,case);fixtures[name]={'input':d.to_dict('records'),'case':case or {'name':'base','fee_bps_per_side':8,'delay_bars':1},'spec':spec_for(d),'trades':json.loads(r[2].to_json(orient='records',double_precision=15)),'marks':json.loads(r[0].to_json(orient='records',double_precision=15)),'events':r[4],'metrics':r[3]};checks.append(name);return r
    d=fixture();d.loc[0,'enter_long']=True;d.loc[1,['open','high','low','close']]=[101,102,99,101]
    n,_,t,m,e=save('intrabar_entry_remainder_path_age_origin',d);assert len(t)==1 and t.iloc[0].fill_price==100 and t.iloc[0].phase=='open_to_low' and t.iloc[0].entry_age_origin_utc.endswith('00:10:00Z')
    d=fixture();d.loc[0,'enter_long']=True;d.loc[1,['open','high','low','close']]=[99,100,98,99]
    _,_,t,_,_=save('favorable_open_limit_slip_capped',d);assert abs(t.iloc[0].fill_price-99.0198)<1e-12
    d=fixture(3);d.loc[0,'enter_long']=True;d.loc[1,['open','high','low','close']]=[101,102,100.1,101]
    _,_,t,_,e=save('entry_timeout_no_implicit_rehang',d);assert len(t)==0 and len(e['orders'])==1 and e['orders'][0]['status']=='timeout_unfilled'
    d=fixture(2);d.loc[0,'enter_long']=True;d.loc[1,['open','high','low','close']]=[101,102,100.1,101]
    _,_,t,_,e=save('terminal_pending_cancel',d);assert len(t)==0 and e['orders'][0]['status']=='terminal_cancelled'
    d=fixture();d.loc[0,['enter_long','exit_long']]=True
    _,_,t,_,_=save('source_collision_suppression',d);assert len(t)==0
    d=fixture();d.loc[0,'enter_long']=True;d.loc[1,'exit_long']=True;d.loc[2,['open','high','low','close']]=[100.1,100.1,99.9,100]
    _,_,t,_,e=save('fee_profit_gate_denied',d);assert len(t)==1 and len(e['profit_gates'])==1 and not e['profit_gates'][0]['allowed']
    d=fixture();d.loc[0,'enter_long']=True;d.loc[1,'exit_long']=True;d.loc[2,['open','high','low','close']]=[100.17,100.2,99.9,100.15]
    _,_,t,_,e=save('fee_profit_gate_pass_can_fill_net_loss',d);assert len(t)==2 and e['profit_gates'][0]['allowed'] and t.iloc[-1].roundtrip_return<0 and t.iloc[-1].reason=='exit_signal'
    d=fixture();d.loc[0,'enter_long']=True;d.loc[1,['high','low']]=[110,89]
    _,_,t,_,e=save('samebar_entry_stop_before_roi',d);assert len(t)==2 and t.iloc[1].reason=='stoploss' and t.iloc[1].phase=='open_to_low' and abs(t.iloc[1].fill_price-89.982)<1e-12
    d=fixture();d.loc[0,'enter_long']=True;d.loc[2,['open','high','low','close']]=[80,81,79,80]
    _,_,t,_,_=save('gap_stop_price_and_adverse_slip',d);assert len(t)==2 and abs(t.iloc[-1].fill_price-79.984)<1e-12
    d=fixture();d.loc[0,'enter_long']=True;d.loc[2,'high']=104;d.loc[3,'low']=96
    _,_,t,m,_=save('trailing_disabled_despite_positive_offset',d);assert len(t)==1 and m['trailing_activations']==0
    for minutes,price,k in [(20,104,5),(30,103,7),(60,101,13)]:
        d=fixture(16);d.loc[0,'enter_long']=True;d.loc[k-1,'high']=price;d.loc[k,'high']=price
        _,_,t,_,_=save(f'roi_boundary_{minutes}',d,{'name':'fee0','fee_bps_per_side':0,'delay_bars':1});assert len(t)==2 and t.iloc[-1].bar_index==k and t.iloc[-1].roi_step_minutes==minutes and t.iloc[-1].fill_price==price
    d=fixture(9);d.loc[0,'enter_long']=True;d.loc[1,['open','high','low','close']]=[101,101,99,100];d.loc[[5,6],'high']=104
    _,_,t,_,_=save('intrabar_roi_clock_not_aged_from_open',d,{'name':'fee0','fee_bps_per_side':0,'delay_bars':1});assert t.iloc[-1].bar_index==6 and t.iloc[-1].roi_step_minutes==20
    d=fixture();d.loc[[0,1],'enter_long']=True;d.loc[2,'high']=106
    _,_,t,_,_=save('entry_signal_does_not_suppress_roi',d);assert t.iloc[-1].reason=='roi'
    for limit,reason in [(104.5,'roi'),(104,'exit_signal')]:
        d=fixture(8);d.loc[0,'enter_long']=True;d.loc[4,['close','high','exit_long']]=[limit,limit,True];d.loc[5,['open','high','low','close']]=[101,105,100,101]
        _,_,t,_,_=save(f'ascending_roi_signal_{reason}',d,{'name':'fee0','fee_bps_per_side':0,'delay_bars':1});assert len(t)==2 and t.iloc[-1].reason==reason and t.iloc[-1].fill_price==104
    d=fixture(8);d.loc[0,'enter_long']=True;d.loc[4,['close','high','exit_long']]=[104,104,True];d.loc[5,['open','high','low','close']]=[105,106,104,105]
    _,_,t,_,_=save('open_signal_priority_over_roi',d,{'name':'fee0','fee_bps_per_side':0,'delay_bars':1});assert t.iloc[-1].reason=='exit_signal'
    d=fixture(8);d.loc[0,'enter_long']=True;d.loc[4,['close','high','exit_long']]=[104.5,104.5,True];d.loc[5,['open','high','low','close']]=[101,105,89,100]
    _,_,t,_,e=save('pending_exit_cancelled_by_stop',d,{'name':'fee0','fee_bps_per_side':0,'delay_bars':1});assert t.iloc[-1].reason=='stoploss' and e['orders'][-1]['status']=='cancelled_by_risk'
    d=fixture();d.loc[0,'enter_long']=True
    _,_,t,_,_=save('delay_two_bars_not_one',d,{'name':'delay2','fee_bps_per_side':8,'delay_bars':2});assert len(t)==1 and t.iloc[0].bar_index==2
    d=fixture(3);d.loc[1,['open','high','low','close']]=[100,110,99.9,110]
    n,daily,t,m,_=save('buyhold_market_fullbar_mdd_terminal_mark',d,{'name':'buyhold','fee_bps_per_side':8,'delay_bars':1,'buy_hold':True});assert len(t)==1 and t.iloc[0].fill_price==100.02 and m['final_quantity']>0 and m['max_drawdown']>.08 and len(daily)==1
    # Complete accounting and causal identities on every event in every fixture.
    for x in fixtures.values():
        cash=100000.;qty=0.;fees=0.
        for e in x['trades']:
            n=e['quantity']*e['fill_price'];f=n*x['case']['fee_bps_per_side']/10000.;fees+=f
            if e['side']=='BUY':cash-=n+f;qty+=e['quantity']
            else:cash+=n-f;qty-=e['quantity']
            assert abs(cash-e['cash_after'])<1e-7 and abs(qty-e['quantity_after'])<1e-9
            if e['signal_available_utc']:assert e['signal_available_utc']<=e['execution_earliest_utc']
        assert abs(fees-x['metrics']['fees_paid'])<1e-7
        for mark in x['marks']:assert abs(mark['cash']+mark['quantity']*mark['close']-mark['equity'])<1e-7
    receipt={'status':'PASS_SYNTHETIC_EXECUTION_BOUNDARIES_ONLY','fixture_count':len(checks),'checks':checks,'all_event_float_accounting_recomputed':True,'historical_market_input_read':False,'historical_runs':0,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    return receipt,fixtures
if __name__=='__main__':
    r,f=run();write(R/'synthetic-execution-tests.json',r);write(R/'synthetic-fixtures.json',f);print(json.dumps(r,indent=2))
