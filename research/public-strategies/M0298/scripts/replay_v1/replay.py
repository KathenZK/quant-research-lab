#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""M0298 native-5m diagnostic hypothesis. No download, external source execution,
network, order API, search, or original-Freqtrade-engine claim. Historical CLI
requires separately approved C0 plus complete input QA and execution audit gates.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,platform,resource
from pathlib import Path
# Hard virtual-address ceiling before numerical-library imports; RSS also recorded.
_AS_CAP=1024**3
_soft,_hard=resource.getrlimit(resource.RLIMIT_AS)
resource.setrlimit(resource.RLIMIT_AS,(_AS_CAP if _hard==resource.RLIM_INFINITY else min(_AS_CAP,_hard),_hard))
import numpy as np
import pandas as pd
import talib
from signal_logic import indicators

INITIAL=100000.; FRACTION=.95; FRICTION=.0002; ROI=.01; STOP=.25
INPUT_SHA='91e5bb0ba80ba2b70c5d6a5924c590459b0ffbe3e5955ba177abc981fb2a0af2'
START=1704067200000; END=1735689600000; WARMUP_START=1701388800000; STEP=300000
CASES=[('base',8,1,False),('fee0',0,1,False),('fee20',20,1,False),('delay2',8,2,False),('buyhold',8,1,True)]
NUMERIC=['cash','quantity','close','equity','drawdown','net_liquidation_equity']

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,obj):
    with Path(p).open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def utc(ms):return pd.Timestamp(int(ms),unit='ms',tz='UTC').strftime('%Y-%m-%dT%H:%M:%SZ')
def write_csv(df,p):
    with Path(p).open('x') as f:df.to_csv(f,index=False,float_format='%.17g',lineterminator='\n')

def verify_environment():
    assert platform.python_version()=='3.12.14'
    assert [np.__version__,pd.__version__,talib.__version__]==['2.3.5','2.2.3','0.6.8']
    assert talib.__ta_version__.decode().split()[0]=='0.6.4'
    for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):assert os.environ.get(k)=='1',k
    assert talib.get_compatibility()==0 and talib.get_unstable_period('EMA')==0 and talib.get_unstable_period('RSI')==0

def load_history(path):
    # Must only be called after separate gates; no repair, sort or row dropping.
    assert sha(path)==INPUT_SHA
    d=pd.read_csv(path)
    needed=['open_time','open','high','low','close','volume','close_time','ts','exchange','market_type','timeframe','symbol','native_symbol','source','bar_close_ts','source_archive']
    assert set(needed).issubset(d)
    expected=np.arange(WARMUP_START,END,STEP,dtype=np.int64)
    assert len(d)==114336 and np.array_equal(d.open_time.to_numpy(),expected)
    assert np.array_equal(d.close_time.to_numpy(),expected+STEP-1)
    assert np.array_equal(pd.to_datetime(d.ts,utc=True).astype('int64').to_numpy()//1000000,expected)
    assert np.array_equal(pd.to_datetime(d.bar_close_ts,utc=True).astype('int64').to_numpy()//1000000,expected+STEP-1)
    for k,v in [('exchange','binance'),('market_type','spot'),('timeframe','5m'),('symbol','BTC/USDT'),('native_symbol','BTCUSDT'),('source','binance_vision')]:assert d[k].eq(v).all(),k
    n=d[['open','high','low','close','volume']].to_numpy(float)
    assert np.isfinite(n).all() and (n>0).all()
    assert (d.high>=d[['open','low','close']].max(axis=1)).all()
    assert (d.low<=d[['open','high','close']].min(axis=1)).all()
    assert int(((d.open_time>=START)&(d.open_time<END)).sum())==105408
    return d

def simulate(d,s,fee_bps=8,lag=1,buyhold=False,start=START,end=END):
    """One account, one long position. Per-bar numeric arrays; only sparse events
    and attempted signal orders retain dictionaries. Synthetic callers may use
    explicit smaller start/end. Signal bar i-lag must be closed before activation.
    """
    assert lag in (1,2) and fee_bps in (0,8,20)
    assert len(d)==len(s)
    fee=fee_bps/10000.; cost=fee+FRICTION
    ts=d.open_time.to_numpy(np.int64);o=d.open.to_numpy(float);h=d.high.to_numpy(float);l=d.low.to_numpy(float);c=d.close.to_numpy(float)
    ent=s.enter_long.to_numpy(bool);ext=s.exit_long.to_numpy(bool)
    es=np.flatnonzero((ts>=start)&(ts<end));assert len(es)>0
    cash=INITIAL;qty=0.;peak=INITIAL;pos=None
    values=np.empty((len(es),len(NUMERIC)),dtype=float)
    events=[];trades=[];orders=[];ambiguities=[]
    collision_bars=0;entry_count=0;exit_count=0
    def event(i,side,price,phase,reason,signal_i,notional,commission,friction,before,after,q,budget):
        events.append({'event_id':len(events)+1,'bar_index':int(i),'open_time':int(ts[i]),'bar_open':utc(ts[i]),'side':side,'fill_price':float(price),'phase':phase,'reason':reason,'signal_index':signal_i,'signal_open_time':None if signal_i is None else int(ts[signal_i]),'quantity':float(q),'notional':float(notional),'fee':float(commission),'friction':float(friction),'cash_before':float(before),'cash_after':float(after),'entry_budget':float(budget)})
    for k,ix in enumerate(es):
        i=int(ix);signal_i=i-lag;valid=signal_i>=0
        entry=bool(ent[signal_i]) if valid else False
        exit_=bool(ext[signal_i]) if valid else False
        if entry and exit_:collision_bars+=1
        signal_exit=exit_ and not entry
        limit=float(c[signal_i]) if valid else None
        held=qty>0
        reason=None;price=None;phase=None
        order=None
        if held and not buyhold:
            stop=pos['entry_fill']*(1-STOP)
            target=pos['entry_fill']*(1+cost)*(1+ROI)/(1-cost)
            if signal_exit:
                order={'order_id':len(orders)+1,'side':'sell','signal_index':signal_i,'activation_index':i,'limit_price':limit,'expires_exclusive':int(ts[i]+STEP),'time_in_force':'GTC','state':'UNRESOLVED'}
                orders.append(order)
            # Chronology: known open fills are resolved before OHLC path ambiguity.
            if o[i]<=stop: reason,price,phase='stop_gap',o[i],'open'
            elif signal_exit and o[i]>=limit: reason,price,phase='exit_signal',o[i],'open'
            elif o[i]>=target: reason,price,phase='roi_gap',o[i],'open'
            elif l[i]<=stop: reason,price,phase='stoploss',stop,'intrabar'
            elif signal_exit and h[i]>=limit: reason,price,phase='exit_signal',limit,'intrabar'
            elif h[i]>=target: reason,price,phase='roi',target,'intrabar'
            competitors=int(l[i]<=stop)+int(h[i]>=target)+int(signal_exit and h[i]>=limit)
            if competitors>=2:
                ambiguities.append({'bar_index':i,'open_time':int(ts[i]),'held_at_open':True,'range_stop':bool(l[i]<=stop),'range_roi':bool(h[i]>=target),'range_signal':bool(signal_exit and h[i]>=limit),'resolved_reason':reason,'resolved_phase':phase,'path_ambiguous':phase!='open','resolution':'known_open_before_intrabar; intrabar_stop_then_signal_then_roi'})
            if order is not None:
                order['state']='FILLED' if reason=='exit_signal' else ('CANCELLED_SUPERSEDED' if reason else 'CANCELLED_TIMEOUT')
                order['resolution_reason']=reason if reason else 'end_of_eligible_5m_bar'
                order['fill_price']=float(price) if reason=='exit_signal' else None
        if not held and ((buyhold and k==0) or (not buyhold and entry and not exit_)):
            if buyhold:
                price_entry=float(o[i]);entry_phase='open';entry_signal=None
            else:
                order={'order_id':len(orders)+1,'side':'buy','signal_index':signal_i,'activation_index':i,'limit_price':limit,'expires_exclusive':int(ts[i]+STEP),'time_in_force':'GTC','state':'UNRESOLVED'}
                orders.append(order)
                if o[i]<=limit:price_entry=float(o[i]);entry_phase='open'
                elif l[i]<=limit:price_entry=limit;entry_phase='intrabar'
                else:price_entry=None;entry_phase=None
                entry_signal=signal_i
                order['state']='FILLED' if price_entry is not None else 'CANCELLED_TIMEOUT'
                order['fill_price']=price_entry
            if price_entry is not None:
                budget=cash*FRACTION;notional=budget/(1+cost);qty=notional/price_entry
                entry_fee=notional*fee;entry_friction=notional*FRICTION;before=cash;cash-=budget;entry_count+=1
                pos={'trade_id':entry_count,'entry_index':i,'entry_open_time':int(ts[i]),'entry_phase':entry_phase,'entry_signal_index':entry_signal,'entry_fill':price_entry,'quantity':qty,'entry_budget':budget,'entry_fee':entry_fee,'entry_friction':entry_friction}
                event(i,'buy',price_entry,entry_phase,'buyhold' if buyhold else 'entry_signal',entry_signal,notional,entry_fee,entry_friction,before,cash,qty,budget)
                if not buyhold:
                    stop=price_entry*(1-STOP);target=price_entry*(1+cost)*(1+ROI)/(1-cost)
                    stop_hit=l[i]<=stop;roi_hit=h[i]>=target
                    if stop_hit or roi_hit:
                        ambiguities.append({'bar_index':i,'open_time':int(ts[i]),'held_at_open':False,'entry_phase':entry_phase,'range_stop':bool(stop_hit),'range_roi':bool(roi_hit),'path_ambiguous':bool(roi_hit and (stop_hit or entry_phase=='intrabar')),'resolution':'stop_first; suppress_entry_bar_roi_for_intrabar_entry'})
                    if stop_hit:reason,price,phase='stoploss',stop,'intrabar'
                    elif entry_phase=='open' and roi_hit:reason,price,phase='roi',target,'intrabar'
        if qty>0 and reason:
            notional=qty*float(price);exit_fee=notional*fee;exit_friction=notional*FRICTION;proceeds=notional-exit_fee-exit_friction;before=cash;cash+=proceeds
            event(i,'sell',price,phase,reason,signal_i if reason=='exit_signal' else None,notional,exit_fee,exit_friction,before,cash,qty,pos['entry_budget'])
            trade={**pos,'exit_index':i,'exit_open_time':int(ts[i]),'exit_phase':phase,'exit_reason':reason,'exit_signal_index':signal_i if reason=='exit_signal' else None,'exit_fill':float(price),'exit_fee':exit_fee,'exit_friction':exit_friction,'proceeds':proceeds,'pnl':proceeds-pos['entry_budget'],'return_on_budget':proceeds/pos['entry_budget']-1,'holding_bars':i-pos['entry_index']}
            trades.append(trade);exit_count+=1;qty=0.;pos=None
        nav=cash+qty*c[i];peak=max(peak,nav)
        assert cash>=-1e-8 and qty>=0 and np.isfinite(nav)
        values[k]=(cash,qty,c[i],nav,nav/peak-1,cash+qty*c[i]*(1-cost))
    curve=pd.DataFrame(values,columns=NUMERIC)
    curve.insert(0,'bar_index',es);curve.insert(1,'open_time',ts[es]);curve.insert(2,'valuation_time',ts[es]+STEP)
    return {'curve':curve,'trades':trades,'fills':events,'orders':orders,'ambiguities':ambiguities,'open_position':pos,'collision_signal_bars':collision_bars}

def metrics(result):
    curve=result['curve'];eq=curve.equity.to_numpy();daily=curve.groupby((curve.valuation_time-1)//86400000,sort=True).tail(1)
    daily_eq=daily.equity.to_numpy();dr=np.diff(np.r_[INITIAL,daily_eq])/np.r_[INITIAL,daily_eq[:-1]];std=dr.std(ddof=1) if len(dr)>1 else np.nan
    trades=result['trades'];fills=result['fills'];orders=result['orders']
    return {'initial_equity':INITIAL,'final_equity':float(eq[-1]),'total_return':float(eq[-1]/INITIAL-1),'annualized_return':float((eq[-1]/INITIAL)**(365/len(daily))-1),'max_drawdown':float(curve.drawdown.min()),'MDD_method':'all native5m bar-close NAV plus initial cash; negative fraction','sharpe_daily':float(dr.mean()/std*np.sqrt(365)) if np.isfinite(std) and std>0 else None,'sharpe_method':'UTC daily close returns including initial capital; sqrt365 ddof1 rf0','observations':len(curve),'daily_observations':len(daily),'closed_trades':len(trades),'fills':len(fills),'win_rate':sum(t['pnl']>0 for t in trades)/len(trades) if trades else None,'total_fees':sum(e['fee'] for e in fills),'total_cash_friction':sum(e['friction'] for e in fills),'open_position':result['open_position'],'ending_net_liquidation_equity':float(curve.net_liquidation_equity.iloc[-1]),'close_position_exposure_fraction':float((curve.quantity>0).mean()),'signal_orders':len(orders),'timeout_orders':sum(o['state']=='CANCELLED_TIMEOUT' for o in orders),'superseded_orders':sum(o['state']=='CANCELLED_SUPERSEDED' for o in orders),'collision_signal_bars':result['collision_signal_bars'],'recorded_ambiguity_rows':len(result['ambiguities']),'path_ambiguous_bars':sum(a['path_ambiguous'] for a in result['ambiguities'])}

def verify_gates(freeze_path,approval_path,input_path):
    freeze=json.loads(Path(freeze_path).read_text());approval=json.loads(Path(approval_path).read_text())
    assert freeze['status']=='FROZEN_BEFORE_RETURNS' and freeze['record_id']=='M0298'
    assert approval['status']=='APPROVED_DATA_AND_C0_FOR_HISTORICAL_RUN' and approval['record_id']=='M0298'
    assert approval['freeze_sha256']==sha(freeze_path)
    assert freeze['input']['sha256']==INPUT_SHA==approval['input_sha256']
    base=Path(freeze_path).parent
    for f in freeze['frozen_files']:
        p=(base/f['path']).resolve();assert sha(p)==f['sha256'],f['path']
    for key in ('complete_raw_qa','independent_raw_rebuild','independent_execution_review'):
        receipt=approval[key];p=(Path(approval_path).parent/receipt['path']).resolve();assert sha(p)==receipt['sha256']
    # No input bytes are consumed until these approval gates have been checked.
    assert sha(input_path)==INPUT_SHA
    return freeze

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--freeze',required=True);p.add_argument('--approval',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    verify_environment();freeze=verify_gates(a.freeze,a.approval,a.input)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    d=load_history(a.input);s=indicators(d.close.to_numpy())
    write_csv(pd.concat([d[['open_time']],s],axis=1),out/'signals.csv')
    summary={'record_id':'M0298','origin_run_id':'M0298-calendar2024-execution-v1-20261003','variant_id':'M0298-BTCUSDT-NATIVE5M-SIMPLE-20261003-v1','family':'PUBLIC-M0298-SIMPLE','evaluation':{'start_inclusive':'2024-01-01T00:00:00Z','end_exclusive':'2025-01-01T00:00:00Z','native_timeframe':'5m','expected_bars':105408,'warmup_tail_signals_allowed':True},'fidelity_class':'HYPOTHESIS','status':'DIAGNOSTIC_ONLY','strict_reproduction':False,'oos':False,'input_sha256':INPUT_SHA,'C0_sha256':sha(a.freeze),'approval_sha256':sha(a.approval),'strategy_configurations':4,'controls':1,'parameter_searches':0,'results':{}}
    for name,fee,lag,buyhold in CASES:
        result=simulate(d,s,fee,lag,buyhold)
        curve=result['curve'];write_csv(curve,out/f'{name}-nav.csv')
        daily=curve.groupby((curve.valuation_time-1)//86400000,sort=True).tail(1)
        write_csv(daily,out/f'{name}-daily-nav.csv')
        for key in ('trades','fills','orders','ambiguities'):dump(out/f'{name}-{key}.json',result[key])
        summary['results'][name]={'fee_bps':fee,'friction_bps':2,'lag_bars':lag,'metrics':metrics(result)}
        del result,curve,daily
    summary['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    assert summary['peak_rss_bytes']<1024**3
    dump(out/'summary.json',summary)
    dump(out/'result-manifest.json',{'files':[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.iterdir()) if p.is_file()],'self_excluded':True})
    print(json.dumps({'record_id':'M0298','configs':4,'controls':1,'peak_rss_bytes':summary['peak_rss_bytes']}))
if __name__=='__main__':main()
