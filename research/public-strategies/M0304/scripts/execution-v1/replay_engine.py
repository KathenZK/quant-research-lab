#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""M0304 explicit diagnostic O-L-H-C limit replay; not the Freqtrade runtime.
Real runs require a separately approved gate receipt; synthetic tests call replay.
"""
import argparse, gc, hashlib, importlib.metadata as md, json, math, os, resource, platform
import talib
from pathlib import Path
import numpy as np
import pandas as pd
from formula_probe import features, fee_aware_profit, roi_at
BAR_MS = 300000
LIMIT = 1024**3
TRADE_COLS = ['event_id','trade_id','bar_index','bar_open_utc','side','reason','phase','signal_bar_index','signal_available_utc','execution_time_utc','execution_earliest_utc','execution_latest_utc','entry_age_origin_utc','reference_price','limit_price','fill_price','quantity','notional','fee','cash_after','quantity_after','roi_step_minutes','roi_target','stop_level','entry_total_cost','roundtrip_return']
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def iso(t): return pd.Timestamp(int(t),unit='ms',tz='UTC').isoformat().replace('+00:00','Z')
def ms(t): return int(pd.Timestamp(t).value//10**6)
def write(p,x):
    with Path(p).open('x') as f: json.dump(x,f,indent=2,ensure_ascii=False,allow_nan=False); f.write('\n')
def read(p): return json.loads(Path(p).read_text())
def replay(z, spec, case):
    ex = spec['execution_plan']; risk=spec['risk_plan']; inp=spec['input_expected_only']
    assert risk['trailing_stop'] is False and risk['exit_profit_only'] is True and risk['ignore_roi_if_entry_signal'] is False and risk['use_exit_signal'] is True
    assert risk['minimal_roi']=={'0':.05,'20':.04,'30':.03,'60':.01} and risk['exit_profit_offset']==0
    start,end=ms(inp['evaluation_start']),ms(inp['evaluation_end_exclusive'])
    tm=z.open_time.to_numpy(dtype=np.int64); ix=np.flatnonzero((tm>=start)&(tm<end)); assert len(ix)>0
    first=int(ix[0]); n=len(ix); o,h,l,c=[z[x].to_numpy(dtype=float) for x in ['open','high','low','close']]
    entv,extv=[z[x].to_numpy(dtype=bool) for x in ['enter_long','exit_long']]
    fee=case['fee_bps_per_side']/10000.;slip=ex['slippage_bps']/10000.;delay=case.get('delay_bars',1);hold=case.get('buy_hold',False)
    initial=float(ex['initial_cash']);cash=initial;qty=entry=buy_cost=stop=0.;age_origin=0;trade_id=0;totalfees=0.
    trades=[];orders=[];gates=[];closed=[];marks=np.empty((n,4),dtype=float);ambiguous=[]
    for j,k0 in enumerate(ix):
        k=int(k0);opened=int(tm[k]);latest=opened+BAR_MS-1;prior=k-delay
        valid=prior>=first;ent=bool(valid and entv[prior]);ext=bool(valid and extv[prior])
        if hold:ent=(j==0);ext=False
        pending=None;exited=False;key,target_roi=roi_at(max(0,(opened-age_origin)//60000)) if qty>0 else (0,.05)
        if qty==0 and ent and not ext:
            pending={'side':'BUY','limit':None if hold else float(c[prior]),'signal':None if hold else prior,'status':'open','profit_gate':None}
        elif qty>0 and ext and not ent:
            gate=fee_aware_profit(float(o[k]),entry,fee,fee);allow=bool(gate>risk['exit_profit_offset'])
            gates.append({'bar_index':k,'signal_bar_index':prior,'decision_time_utc':iso(opened),'decision_quote':float(o[k]),'entry_fill':entry,'fee_bps_per_side':case['fee_bps_per_side'],'fee_aware_profit':gate,'strict_offset':risk['exit_profit_offset'],'allowed':allow})
            if allow:pending={'side':'SELL','limit':float(c[prior]),'signal':prior,'status':'open','profit_gate':gate}
        if pending:
            pending.update({'order_id':len(orders)+1,'bar_index':k,'placed_utc':iso(opened),'order_type':'market' if hold else 'limit','tif':None if hold else 'GTC','timeout_utc':None if hold else iso(opened+BAR_MS),'signal_available_utc':iso(tm[prior]+BAR_MS) if not hold else None});orders.append(pending)
        def target():return entry*(1+fee)*(1+target_roi)/(1-fee)
        def fill(side,ref,reason,phase,limit=None):
            nonlocal cash,qty,entry,buy_cost,stop,age_origin,trade_id,totalfees,exited,pending,key,target_roi
            reference=float(ref);price=reference*(1+slip if side=='BUY' else 1-slip)
            if limit is not None:price=min(price,limit) if side=='BUY' else max(price,limit)
            signal=pending['signal'] if pending and pending['side']==side and reason in ('entry_signal','exit_signal','buyhold') else None
            rt=None
            if side=='BUY':
                budget=cash*ex['cash_budget_fraction'];amount=budget/(price*(1+fee));notional=amount*price;commission=notional*fee
                cash-=notional+commission;qty=amount;entry=price;buy_cost=notional+commission;stop=entry*(1+risk['stoploss'])
                age_origin=opened if phase=='open' else opened+BAR_MS;trade_id+=1;key,target_roi=0,.05
                if phase!='open' and l[k]<=stop and h[k]>=target():ambiguous.append({'bar_index':k,'entry':entry,'stop':stop,'roi_level':target(),'resolution':'frozen O-L-H-C remaining entry path; not a bound'})
            else:
                assert qty>0;amount=qty;notional=amount*price;commission=notional*fee;cash+=notional-commission;qty=0.;exited=True
                rt=(notional-commission)/buy_cost-1;closed.append(rt)
            totalfees+=commission
            trades.append(dict(event_id=len(trades)+1,trade_id=trade_id,bar_index=k,bar_open_utc=iso(opened),side=side,reason=reason,phase=phase,signal_bar_index=signal,signal_available_utc=iso(tm[signal]+BAR_MS) if signal is not None else None,execution_time_utc=iso(opened) if phase=='open' else None,execution_earliest_utc=iso(opened),execution_latest_utc=iso(opened if phase=='open' else latest),entry_age_origin_utc=iso(age_origin),reference_price=reference,limit_price=limit,fill_price=price,quantity=amount,notional=notional,fee=commission,cash_after=cash,quantity_after=qty,roi_step_minutes=key,roi_target=target_roi,stop_level=stop,entry_total_cost=buy_cost,roundtrip_return=rt))
            if pending:
                pending['status']='filled' if pending['side']==side and reason in ('entry_signal','exit_signal','buyhold') else 'cancelled_by_risk'
                pending['resolved_phase']=phase;pending['fill_event_id']=len(trades) if pending['status']=='filled' else None;pending=None
            assert cash>=-1e-7 and qty>=0
        if pending and pending['side']=='BUY' and (hold or o[k]<=pending['limit']):
            fill('BUY',o[k],'buyhold' if hold else 'entry_signal','open',None if hold else pending['limit'])
        if qty>0 and not hold:
            key,target_roi=roi_at(max(0,(opened-age_origin)//60000))
            if l[k]<=stop and h[k]>=target():ambiguous.append({'bar_index':k,'entry':entry,'stop':stop,'roi_level':target(),'resolution':'frozen O-L-H-C path; not a bound'})
            if o[k]<=stop:fill('SELL',o[k],'stoploss','open')
            elif pending and pending['side']=='SELL' and o[k]>=pending['limit']:fill('SELL',o[k],'exit_signal','open',pending['limit'])
            elif o[k]>=target():fill('SELL',o[k],'roi','open',target())
        if not hold:
            for a,b,phase in [(float(o[k]),float(l[k]),'open_to_low'),(float(l[k]),float(h[k]),'low_to_high'),(float(h[k]),float(c[k]),'high_to_close')]:
                if qty==0 and pending and pending['side']=='BUY' and not exited and b<=pending['limit']<=a:
                    level=pending['limit'];fill('BUY',level,'entry_signal',phase,level);a=level
                if qty<=0:continue
                if b<a:
                    if b<=stop<=a:fill('SELL',stop,'stoploss',phase)
                else:
                    candidates=[]
                    if pending and pending['side']=='SELL' and a<=pending['limit']<=b:candidates.append((pending['limit'],0,'exit_signal'))
                    if a<=target()<=b:candidates.append((target(),1,'roi'))
                    if candidates:
                        level,_,reason=min(candidates);fill('SELL',level,reason,phase,level)
        if pending:
            pending['status']='terminal_cancelled' if opened+BAR_MS>=end else 'timeout_unfilled';pending['resolved_phase']='terminal' if opened+BAR_MS>=end else 'next_open';pending=None
        equity=cash+qty*c[k];marks[j]=(cash,qty,equity,equity/initial)
    nav=pd.DataFrame(marks,columns=['cash','quantity','equity','nav']);nav.insert(0,'bar_index',ix)
    nav.insert(1,'bar_open_utc',pd.to_datetime(tm[ix],unit='ms',utc=True).strftime('%Y-%m-%dT%H:%M:%SZ'))
    nav.insert(2,'timestamp_utc',pd.to_datetime(tm[ix]+BAR_MS,unit='ms',utc=True).strftime('%Y-%m-%dT%H:%M:%SZ'));nav['close']=c[ix]
    daily=nav.assign(date=nav.bar_open_utc.str[:10]).groupby('date',sort=True).tail(1)
    eq=np.r_[initial,marks[:,2]];ret=eq[1:]/eq[:-1]-1;deq=np.r_[initial,daily.equity.to_numpy()];dr=deq[1:]/deq[:-1]-1
    def sharpe(a,scale):return float(a.mean()/a.std(ddof=1)*math.sqrt(scale)) if len(a)>1 and a.std(ddof=1)>0 else None
    metrics={'total_return':float(eq[-1]/initial-1),'annualized_return':float((eq[-1]/initial)**(365/((end-start)/86400000))-1),'max_drawdown':float(np.max(1-eq/np.maximum.accumulate(eq))),'sharpe_daily':sharpe(dr,365),'sharpe_5m':sharpe(ret,365*288),'final_equity':float(eq[-1]),'final_cash':cash,'final_quantity':qty,'fees_paid':totalfees,'fill_events':len(trades),'completed_roundtrips':len(closed),'winning_roundtrip_fraction':float(np.mean(np.array(closed)>0)) if closed else None,'orders':len(orders),'timeout_orders':sum(q['status']=='timeout_unfilled' for q in orders),'terminal_cancelled_orders':sum(q['status']=='terminal_cancelled' for q in orders),'position_bar_fraction':float(np.mean(marks[:,1]>0)),'observations':len(nav),'daily_observations':len(daily),'signal_exit_gate_checks':len(gates),'signal_exit_gate_denials':sum(not q['allowed'] for q in gates),'range_stop_roi_ambiguous_bars':len(ambiguous),'trailing_activations':0}
    return nav,daily,pd.DataFrame(trades,columns=TRADE_COLS),metrics,{'orders':orders,'profit_gates':gates,'bar_ambiguities':ambiguous}

def load_input(path,spec):
    contract=spec['input_expected_only'];assert sha(path)==contract['sha256'];assert Path(path).stat().st_size==contract['bytes']
    d=pd.read_csv(path);assert len(d)==contract['rows'];grid=np.arange(ms(contract['start']),ms(contract['end_exclusive']),BAR_MS)
    assert np.array_equal(d.open_time.to_numpy(),grid);assert np.array_equal(d.close_time.to_numpy(),grid+BAR_MS-1)
    for col,value in [('exchange','binance'),('market_type','spot'),('timeframe','5m'),('native_symbol','BTCUSDT'),('source','binance_vision'),('symbol','BTC/USDT')]:assert (d[col]==value).all(),col
    vals=d[['open','high','low','close','volume','quote_volume','taker_buy_base_volume','taker_buy_quote_volume','trade_count']].to_numpy();assert np.isfinite(vals).all()
    assert (d.low>0).all() and (d.high>=d[['open','close']].max(axis=1)).all() and (d.low<=d[['open','close']].min(axis=1)).all()
    assert (d.volume>0).all() and (d.quote_volume>0).all() and (d.trade_count>0).all()
    assert ((d.taker_buy_base_volume>=0)&(d.taker_buy_base_volume<=d.volume)).all()
    assert ((d.taker_buy_quote_volume>=0)&(d.taker_buy_quote_volume<=d.quote_volume)).all()
    return d

def run(input_path,output,spec_path,gate_path):
    resource.setrlimit(resource.RLIMIT_AS,(LIMIT,LIMIT));spec=read(spec_path);gate=read(gate_path)
    assert gate['status']=='APPROVED_FOR_HISTORICAL_RUN' and gate['protocol_sha256']==sha(spec_path) and gate['input_sha256']==spec['input_expected_only']['sha256']
    assert gate['source_recovery_qa_passed'] and gate['independent_C0_passed']
    for name,digest in spec['implementation_files'].items():assert sha(Path(__file__).resolve().parent/name)==digest,name
    for name,version in spec['environment']['packages'].items():assert md.version(name)==version,name
    assert platform.python_version()==spec['environment']['python']
    assert sha(talib._ta_lib.__file__)==spec['environment']['talib_binary_sha256']
    assert talib.get_compatibility()==0 and talib.get_unstable_period('RSI')==0
    out=Path(output);out.mkdir(parents=True,exist_ok=False);d=load_input(input_path,spec);z=features(d)
    signal=z[['open_time','slowk','rsi','fisher_rsi','bb_lowerband','sar','CDLHAMMER','enter_long','exit_long']]
    signal.to_csv(out/'signals.csv',index=False,float_format='%.17g');del signal;results={}
    cases=spec['preregistered_cases']+[{'name':'buyhold','fee_bps_per_side':8,'delay_bars':1,'buy_hold':True}]
    for case in cases:
        nav,daily,t,m,event=replay(z,spec,case);name=case['name']
        for suffix,frame in [('nav',nav),('daily-nav',daily),('trades',t)]:frame.to_csv(out/f'{name}-{suffix}.csv',index=False,float_format='%.17g')
        write(out/f'{name}-events.json',event);results[name]={'case':case,'metrics':m};del nav,daily,t,event;gc.collect()
    summary={'record_id':'M0304','status':'RUN_COMPLETE_PENDING_INDEPENDENT_REVIEW','fidelity_class':'HYPOTHESIS','data_quality_status':'DIAGNOSTIC_ONLY','strict_reproductions':0,'trusted':False,'oos_claim':False,'promotion':False,'protocol_sha256':sha(spec_path),'input_sha256':sha(input_path),'engine_sha256':sha(__file__),'actual_strategy_ids':1,'strategy_configurations':4,'controls':1,'parameter_searches':0,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'results':results}
    write(out/'summary.json',summary);return summary
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--spec',required=True);p.add_argument('--gate',required=True);a=p.parse_args();print(json.dumps(run(a.input,a.output,a.spec,a.gate),indent=2))
