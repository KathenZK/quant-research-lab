#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Frozen M0275 single-symbol diagnostic. Native-minute ROI, open-observed proxy.
No parameter search. Raw data and full source are never bundled by this script.
"""
import argparse, hashlib, importlib.metadata as md, json, math, os, pathlib, resource, sys
import numpy as np
import pandas as pd
import ta
from ta.utils import dropna
ROOT = pathlib.Path(__file__).resolve().parents[1]
BAR_MS = 14400000
HALT_BAR = 1679659200000
HALT_RESUME = 1679666400000
HALT_PREVIOUS = 1679644800000
HALT_START = 1679657220000

def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def write(p, x):
    with pathlib.Path(p).open('x') as f: json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False); f.write('\n')
def iso(t): return pd.Timestamp(int(t),unit='ms',tz='UTC').isoformat().replace('+00:00','Z')
def ms(t): return int(pd.Timestamp(t).value//10**6)
def load_input(path,spec):
    assert sha(path)==spec['input']['sha256']
    d=pd.read_csv(path); assert len(d)==4572
    opened=d.open_time.to_numpy(dtype=np.int64)
    assert np.array_equal(opened, np.arange(ms('2022-12-01T00:00:00Z'),ms('2025-01-01T00:00:00Z'),BAR_MS))
    assert (d.close_time==d.open_time+BAR_MS-1).all()
    for col,value in [('exchange','binance'),('market_type','spot'),('timeframe','4h'),('native_symbol','BTCUSDT'),('source','binance_vision')]: assert (d[col]==value).all()
    assert np.isfinite(d[['open','high','low','close','volume','quote_volume','trade_count','taker_buy_base_volume','taker_buy_quote_volume']]).all().all()
    assert (d.low>0).all() and (d.high>=d[['open','close']].max(axis=1)).all() and (d.low<=d[['open','close']].min(axis=1)).all()
    assert (d.volume>0).all() and (d.trade_count>0).all()
    return d

def input_frame(d):
    # Freqtrade only passes date/open/high/low/close/volume to this strategy.
    # Including raw Binance ignore=0 would cause ta.dropna to remove every row.
    f=d[['open','high','low','close','volume']].copy();f.insert(0,'date',pd.to_datetime(d.open_time,unit='ms',utc=True));return f

def features(d):
    f=input_frame(d); z=dropna(f)
    if not z.index.equals(f.index): raise ValueError('ta.dropna removed rows; never silently compress market calendar')
    z['kcw']=ta.volatility.keltner_channel_wband(z.high,z.low,z.close,window=20,window_atr=10,fillna=False,original_version=True)
    z['dcp']=ta.volatility.donchian_channel_pband(z.high,z.low,z.close,window=10,offset=0,fillna=False)
    z['ratio']=z.dcp.shift(15)/z.kcw.shift(9)
    z['entry_signal']=z.ratio.between(.16,.75,inclusive='both')
    z['exit_signal']=False
    return pd.concat([d[['open_time','close_time']],z.drop(columns=['date'])],axis=1)

def roi_at(elapsed_minutes,table):
    eligible=[(int(k),float(v)) for k,v in table.items() if int(k)<=elapsed_minutes]
    return max(eligible,key=lambda x:x[0])

def replay(z,spec,case):
    start=ms(spec['evaluation']['start']); end=ms(spec['evaluation']['end_exclusive'])
    indices=np.flatnonzero((z.open_time>=start)&(z.open_time<end)); first=int(indices[0])
    cash=float(spec['execution']['initial_cash']); qty=0.; entry=0.; entry_ms=None; buy_cost=0.
    fee=case['fee_bps']/10000; slip=spec['execution']['slippage_bps']/10000; delay=case['delay_bars']; fraction=spec['execution']['cash_budget_fraction']
    trades=[]; nav=[]; roundtrips=[]; totalfees=0.; hits=0; ambiguous=0; step_events=[]
    for k in indices:
        r=z.iloc[k]; opened=int(r.open_time); effective=HALT_RESUME if opened==HALT_BAR else opened
        latest=HALT_START-1 if opened==HALT_PREVIOUS else int(r.close_time)
        prior=int(k-delay); valid=prior>=first; signal=bool(valid and z.iloc[prior].entry_signal)
        hold=case.get('buy_hold',False)
        if hold: signal=k==first
        def fill(side,ref,reason,phase,roi_key=None,roi_value=None):
            nonlocal cash,qty,entry,entry_ms,buy_cost,totalfees
            price=float(ref)*(1+slip if side=='BUY' else 1-slip)
            before_qty=qty
            if side=='BUY':
                budget=cash*fraction; amount=budget/(price*(1+fee)); notional=amount*price; commission=notional*fee
                cash-=notional+commission; qty=amount;entry=price;entry_ms=effective;buy_cost=notional+commission
            else:
                amount=qty;notional=amount*price;commission=notional*fee;cash+=notional-commission;qty=0
                roundtrips.append((notional-commission)/buy_cost-1)
            totalfees+=commission
            trades.append({'event_id':len(trades)+1,'bar_index':int(k),'bar_open_utc':iso(opened),'side':side,'reason':reason,'phase':phase,
                           'signal_bar_index':prior if side=='BUY' and not hold else None,
                           'signal_close_utc':iso(z.iloc[prior].close_time) if side=='BUY' and not hold else None,
                           'execution_time_utc':iso(effective) if phase in ['open','open_gap'] else None,
                           'execution_earliest_utc':iso(effective),'execution_latest_utc':iso(effective if phase in ['open','open_gap'] else latest),
                           'time_basis':'resume_1h_open_proxy' if opened==HALT_BAR else 'native_4h_open_or_intrabar_interval',
                           'roi_step_minutes':roi_key,'roi_target':roi_value,'entry_time_utc':iso(entry_ms),
                           'reference_price':float(ref),'fill_price':price,'quantity':amount,'notional':notional,'fee':commission,'cash_after':cash,'quantity_after':qty})
        # No indicator exits. Risk checks only after a possible due entry.
        if qty==0 and signal: fill('BUY',r.open,'buy_hold' if hold else 'entry_signal','open')
        if qty>0 and not hold:
            elapsed=(effective-entry_ms)//60000; key,roi=roi_at(elapsed,spec['risk']['minimal_roi'])
            for minute in [int(x) for x in spec['risk']['minimal_roi'] if int(x)>0]:
                boundary=entry_ms+minute*60000
                next_effective=HALT_RESUME if opened+BAR_MS==HALT_BAR else opened+BAR_MS
                if effective<boundary<next_effective:
                    step_events.append({'bar_index':int(k),'boundary_utc':iso(boundary),'minutes':minute,'observed_from_utc':iso(next_effective),'position_at_open':True,'effect':'new tier not used until next effective open if still held; no assertion position survives to boundary'})
            stop=entry*(1+spec['risk']['stoploss']);target=entry*(1+fee)*(1+roi)/(1-fee)
            stop_hit=float(r.low)<=stop;roi_hit=float(r.high)>=target
            if stop_hit and roi_hit: hits+=1
            if stop_hit and roi_hit and stop<float(r.open)<target: ambiguous+=1
            if r.open<=stop: fill('SELL',r.open,'stoploss','open_gap',key,roi)
            elif r.open>=target: fill('SELL',r.open,'roi','open_gap',key,roi)
            elif stop_hit: fill('SELL',stop,'stoploss','intrabar_unknown',key,roi)
            elif roi_hit: fill('SELL',target,'roi','intrabar_unknown',key,roi)
        eq=cash+qty*float(r.close)
        nav.append({'bar_index':int(k),'bar_open_utc':iso(opened),'timestamp_utc':iso(r.close_time+1),'cash':cash,'quantity':qty,'close':float(r.close),'equity':eq,'nav':eq/spec['execution']['initial_cash']})
    n=pd.DataFrame(nav);t=pd.DataFrame(trades); eq=np.r_[spec['execution']['initial_cash'],n.equity.to_numpy()];rets=eq[1:]/eq[:-1]-1
    daily=n.assign(date=pd.to_datetime(n.bar_open_utc,utc=True).dt.strftime('%Y-%m-%d')).groupby('date',sort=True).tail(1)
    deq=np.r_[spec['execution']['initial_cash'],daily.equity.to_numpy()];dr=deq[1:]/deq[:-1]-1
    def sharpe(x,scale): return float(x.mean()/x.std(ddof=1)*np.sqrt(scale)) if x.std(ddof=1)>0 else None
    m={'total_return':float(eq[-1]/eq[0]-1),'annualized_return':float((eq[-1]/eq[0])**(365/((end-start)/86400000))-1),
       'max_drawdown':float(np.max(1-eq/np.maximum.accumulate(eq))),'sharpe_daily':sharpe(dr,365),'sharpe_4h':sharpe(rets,365*6),
       'final_equity':float(eq[-1]),'final_cash':cash,'final_quantity':qty,'fill_events':len(t),'completed_roundtrips':len(roundtrips),
       'winning_roundtrip_fraction':float(np.mean(np.array(roundtrips)>0)) if roundtrips else None,'fees_paid':totalfees,
       'position_bar_fraction':float((n.quantity>0).mean()),'both_stop_roi_touched':hits,'unresolved_stop_roi_samebar':ambiguous,
       'roi_boundary_candidate_bars':len(step_events),'observations':len(n),'daily_observations':len(daily)}
    return n,daily,t,m,step_events

def run(input_path,outdir,spec_path):
    out=pathlib.Path(outdir);out.mkdir(parents=True,exist_ok=False)
    spec=json.loads(pathlib.Path(spec_path).read_text())
    for p,h in spec['frozen_file_hashes'].items(): assert sha(ROOT/p)==h,p
    for name,v in spec['dependencies']['packages'].items(): assert md.version(name)==v,name
    for name,h in spec['dependencies']['ta_file_hashes'].items(): assert sha(pathlib.Path(ta.__file__).parent/name)==h,name
    resource.setrlimit(resource.RLIMIT_AS,(1536*1024**2,1536*1024**2))
    d=load_input(input_path,spec);z=features(d)
    z[['open_time','dcp','kcw','ratio','entry_signal']].to_csv(out/'signals.csv',index=False,float_format='%.17g')
    results={}
    for case in spec['cases']:
        n,daily,t,m,events=replay(z,spec,case);name=case['name']
        for suffix,frame in [('nav',n),('daily-nav',daily),('trades',t)]:frame.to_csv(out/f'{name}-{suffix}.csv',index=False,float_format='%.17g')
        write(out/f'{name}-roi-boundaries.json',events)
        results[name]={'case':case,'metrics':m}
    summary={'id':'M0275','origin_run_id':spec['run_id'],'variant_id':spec['variant_id'],'fidelity_class':'HYPOTHESIS','data_quality_status':'DIAGNOSTIC_ONLY','strict_reproductions':0,
             'trusted':False,'oos_claim':False,'promotion':False,'protocol_sha256':sha(spec_path),'input_sha256':sha(input_path),'engine_sha256':sha(__file__),
             'actual_strategy_ids':1,'strategy_configurations':4,'controls':1,'parameter_searches':0,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'results':results}
    write(out/'summary.json',summary);return summary
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--spec',default=str(ROOT/'specs/protocol.json'));a=p.parse_args();print(json.dumps(run(a.input,a.output,a.spec),ensure_ascii=False,indent=2))
