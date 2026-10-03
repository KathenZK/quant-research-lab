#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""M0316 diagnostic limit-order replay, explicit O-L-H-C path; not Freqtrade."""
import argparse,hashlib,importlib.metadata as md,json,os,pathlib,resource
import numpy as np
import pandas as pd
import talib
ROOT=pathlib.Path(__file__).resolve().parents[1]
BAR_MS=14400000; HALT_BAR=1679659200000; HALT_RESUME=1679666400000; HALT_PREVIOUS=1679644800000; HALT_START=1679657220000
TRADE_COLUMNS=['event_id','bar_index','bar_open_utc','side','reason','phase','signal_bar_index','signal_close_utc','execution_time_utc','execution_earliest_utc','execution_latest_utc','entry_age_origin_utc','reference_price','limit_price','fill_price','quantity','notional','fee','cash_after','quantity_after','roi_step_minutes','roi_target','stop_level']
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def write(p,x):
    with pathlib.Path(p).open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def iso(t):return pd.Timestamp(int(t),unit='ms',tz='UTC').isoformat().replace('+00:00','Z')
def ms(t):return int(pd.Timestamp(t).value//10**6)
def load_input(path,spec):
    assert sha(path)==spec['input']['sha256'];assert pathlib.Path(path).stat().st_size==spec['input']['bytes']
    d=pd.read_csv(path);assert len(d)==4572
    assert np.array_equal(d.open_time,np.arange(ms('2022-12-01T00:00:00Z'),ms('2025-01-01T00:00:00Z'),BAR_MS))
    assert (d.close_time==d.open_time+BAR_MS-1).all()
    for c,v in [('exchange','binance'),('market_type','spot'),('timeframe','4h'),('native_symbol','BTCUSDT'),('source','binance_vision')]:assert (d[c]==v).all()
    assert np.isfinite(d[['open','high','low','close','volume']]).all().all()
    assert (d.low>0).all() and (d.high>=d[['open','close']].max(axis=1)).all() and (d.low<=d[['open','close']].min(axis=1)).all()
    assert (d.volume>0).all() and (d.trade_count>0).all()
    return d

def features(d):
    z=d.copy();z['hl2']=(z.open+z.close)/2
    z['rsi']=talib.RSI(z.hl2.to_numpy(),timeperiod=10);z['ema5']=talib.EMA(z.close.to_numpy(),timeperiod=5);z['ema10']=talib.EMA(z.close.to_numpy(),timeperiod=10);z['adx']=talib.ADX(z.high.to_numpy(),z.low.to_numpy(),z.close.to_numpy(),timeperiod=14)
    z['entry_signal']=(z.rsi>50)&(z.rsi.shift(1)<=50)&(z.ema5>z.ema10)&(z.ema5.shift(1)<=z.ema10.shift(1))&(z.adx>25)&(z.volume>0)
    z['exit_signal']=(z.rsi<50)&(z.rsi.shift(1)>=50)&(z.ema5<z.ema10)&(z.ema5.shift(1)>=z.ema10.shift(1))&(z.adx>25)&(z.volume>0)
    z.loc[z.index<30,['entry_signal','exit_signal']]=False
    return z

def roi_at(elapsed,table):return max([(int(k),float(v)) for k,v in table.items() if int(k)<=elapsed],key=lambda x:x[0])
def replay(z,spec,case):
    start=ms(spec['evaluation']['start']);end=ms(spec['evaluation']['end_exclusive']);indices=np.flatnonzero((z.open_time>=start)&(z.open_time<end));first=int(indices[0])
    cash=float(spec['execution']['initial_cash']);qty=0.;entry=0.;age_origin=0;buy_cost=0.;stop=0.;peak=0.;active=False
    fee=case['fee_bps']/10000;slip=spec['execution']['slippage_bps']/10000;delay=case['delay_bars'];fraction=spec['execution']['cash_budget_fraction'];hold=case.get('buy_hold',False)
    trades=[];orders=[];nav=[];risk=[];roundtrips=[];totalfees=0.;activation_count=0;roi_suppressed=0;boundaries=[]
    for k in indices:
        r=z.iloc[k];opened=int(r.open_time);effective=HALT_RESUME if opened==HALT_BAR else opened;latest=HALT_START-1 if opened==HALT_PREVIOUS else int(r.close_time)
        prior=int(k-delay);valid=prior>=first;ent=bool(valid and z.iloc[prior].entry_signal);ext=bool(valid and z.iloc[prior].exit_signal)
        if hold:ent=k==first;ext=False
        pending=None;exited=False;key=0;roi=spec['risk']['minimal_roi']['0'];suppress=ent and not hold
        if qty==0 and ent and not ext:pending={'side':'BUY','limit':float(r.open) if hold else float(z.iloc[prior].close),'signal':None if hold else prior,'status':'open'}
        elif qty>0 and ext and not ent:pending={'side':'SELL','limit':float(z.iloc[prior].close),'signal':prior,'status':'open'}
        if pending:pending.update({'order_id':len(orders)+1,'bar_index':int(k),'placed_utc':iso(effective),'tif':'gtc','timeout_utc':iso(HALT_RESUME if opened+BAR_MS==HALT_BAR else opened+BAR_MS)});orders.append(pending)
        def fill(side,ref,reason,phase,limit=None):
            nonlocal cash,qty,entry,age_origin,buy_cost,totalfees,stop,peak,active,exited,pending,key,roi
            raw=float(ref);price=raw*(1+slip if side=='BUY' else 1-slip)
            if limit is not None:price=min(price,limit) if side=='BUY' else max(price,limit)
            isopen=phase=='open';sig=pending['signal'] if pending and pending['side']==side and reason in ['entry_signal','exit_signal'] else None
            if side=='BUY':
                budget=cash*fraction;amount=budget/(price*(1+fee));notional=amount*price;commission=notional*fee;cash-=notional+commission;qty=amount;entry=price;buy_cost=notional+commission
                age_origin=effective if isopen else latest+1;stop=entry*(1+spec['risk']['stoploss']);peak=entry;active=False;key=0;roi=float(spec['risk']['minimal_roi']['0'])
            else:
                amount=qty;notional=amount*price;commission=notional*fee;cash+=notional-commission;qty=0.;exited=True;roundtrips.append((notional-commission)/buy_cost-1)
            totalfees+=commission
            trades.append(dict(event_id=len(trades)+1,bar_index=int(k),bar_open_utc=iso(opened),side=side,reason=reason,phase=phase,signal_bar_index=sig,signal_close_utc=iso(z.iloc[sig].close_time) if sig is not None else None,
                execution_time_utc=iso(effective) if isopen else None,execution_earliest_utc=iso(effective),execution_latest_utc=iso(effective if isopen else latest),entry_age_origin_utc=iso(age_origin),reference_price=raw,limit_price=limit,fill_price=price,quantity=amount,notional=notional,fee=commission,cash_after=cash,quantity_after=qty,roi_step_minutes=key,roi_target=roi,stop_level=stop))
            if pending:
                pending['status']='filled' if pending['side']==side and reason in ['entry_signal','exit_signal','buy_hold'] else 'cancelled_by_risk'
                pending['resolved_phase']=phase;pending=None
        def trail(price,phase):
            nonlocal peak,active,stop,activation_count
            if qty<=0 or hold:return
            peak=max(peak,float(price));threshold=entry*(1+fee)*(1+spec['risk']['trailing_offset'])/(1-fee)
            if not active and peak>threshold:active=True;activation_count+=1;risk.append({'bar_index':int(k),'event':'trailing_activation','phase':phase,'activation_price_threshold':threshold,'observed_path_price':float(price),'fee_bps':case['fee_bps']})
            if active:stop=max(stop,peak*(1-spec['risk']['trailing_positive']))
            elif peak==threshold:stop=max(stop,peak*(1+spec['risk']['stoploss']))
        def target():return entry*(1+fee)*(1+roi)/(1-fee)
        # Pending limit entry first, followed immediately by same-entry-bar risk.
        if pending and pending['side']=='BUY' and float(r.open)<=pending['limit']:fill('BUY',r.open,'buy_hold' if hold else 'entry_signal','open',None if hold else pending['limit'])
        if qty>0 and not hold:
            key,roi=roi_at(max(0,(effective-age_origin)//60000),spec['risk']['minimal_roi'])
            if suppress:roi_suppressed+=1
            for minute in [int(x) for x in spec['risk']['minimal_roi'] if int(x)>0]:
                boundary=age_origin+minute*60000;following=HALT_RESUME if opened+BAR_MS==HALT_BAR else opened+BAR_MS
                if effective<boundary<following:boundaries.append({'bar_index':int(k),'boundary_utc':iso(boundary),'minute':minute,'deferred_to_utc':iso(following),'position_at_open_only':True})
            risk.append({'bar_index':int(k),'event':'open_state','entry':entry,'stop':stop,'trailing_active':active,'peak':peak,'roi_step':key,'roi':roi,'roi_suppressed':suppress,'age_origin_utc':iso(age_origin),'effective_utc':iso(effective)})
            if float(r.open)<=stop:fill('SELL',r.open,'trailing_stop' if active else 'stoploss','open')
            elif pending and pending['side']=='SELL' and float(r.open)>=pending['limit']:fill('SELL',r.open,'exit_signal','open',pending['limit'])
            elif not suppress and float(r.open)>=target():fill('SELL',r.open,'roi','open',target())
            else:trail(r.open,'open')
        # Deterministic diagnostic path. Prices are ordered; no invented tick timestamps.
        for a,b,phase in [(float(r.open),float(r.low),'open_to_low'),(float(r.low),float(r.high),'low_to_high'),(float(r.high),float(r.close),'high_to_close')]:
            if hold:break
            if qty==0 and pending and pending['side']=='BUY' and not exited and b<=pending['limit']<=a:
                price=pending['limit'];fill('BUY',price,'entry_signal',phase,price);a=price
            if qty<=0:continue
            if b<a:
                if b<=stop<=a:fill('SELL',stop,'trailing_stop' if active else 'stoploss',phase)
            else:
                candidates=[]
                if pending and pending['side']=='SELL' and a<=pending['limit']<=b:candidates.append((pending['limit'],0,'exit_signal'))
                if not suppress and a<=target()<=b:candidates.append((target(),1,'roi'))
                if candidates:
                    level,_,reason=min(candidates);trail(level,phase);fill('SELL',level,reason,phase,level)
                else:trail(b,phase)
        if pending:pending['status']='terminal_cancelled' if opened+BAR_MS>=end else 'timeout_unfilled';pending['resolved_phase']='terminal' if opened+BAR_MS>=end else 'next_effective_open';pending=None
        eq=cash+qty*float(r.close);nav.append({'bar_index':int(k),'bar_open_utc':iso(opened),'timestamp_utc':iso(int(r.close_time)+1),'cash':cash,'quantity':qty,'close':float(r.close),'equity':eq,'nav':eq/spec['execution']['initial_cash']})
    n=pd.DataFrame(nav);t=pd.DataFrame(trades,columns=TRADE_COLUMNS);daily=n.assign(date=pd.to_datetime(n.bar_open_utc,utc=True).dt.strftime('%Y-%m-%d')).groupby('date',sort=True).tail(1)
    eq=np.r_[spec['execution']['initial_cash'],n.equity.to_numpy()];ret=eq[1:]/eq[:-1]-1;deq=np.r_[spec['execution']['initial_cash'],daily.equity.to_numpy()];dr=deq[1:]/deq[:-1]-1
    def sharpe(x,scale):return float(x.mean()/x.std(ddof=1)*np.sqrt(scale)) if len(x)>1 and x.std(ddof=1)>0 else None
    m={'total_return':float(eq[-1]/eq[0]-1),'annualized_return':float((eq[-1]/eq[0])**(365/((end-start)/86400000))-1),'max_drawdown':float(np.max(1-eq/np.maximum.accumulate(eq))),'sharpe_daily':sharpe(dr,365),'sharpe_4h':sharpe(ret,2190),'final_equity':float(eq[-1]),'final_cash':cash,'final_quantity':qty,'fill_events':len(t),'completed_roundtrips':len(roundtrips),'winning_roundtrip_fraction':float(np.mean(np.array(roundtrips)>0)) if roundtrips else None,'fees_paid':totalfees,'position_bar_fraction':float((n.quantity>0).mean()),'orders':len(orders),'timeout_orders':sum(x['status']=='timeout_unfilled' for x in orders),'trailing_activations':activation_count,'roi_suppressed_position_bars':roi_suppressed,'observations':len(n),'daily_observations':len(daily)}
    return n,daily,t,m,{'orders':orders,'risk':risk,'roi_boundaries':boundaries}

def run(input_path,outdir,spec_path):
    out=pathlib.Path(outdir);out.mkdir(parents=True,exist_ok=False);spec=json.loads(pathlib.Path(spec_path).read_text())
    for p,h in spec['frozen_file_hashes'].items():assert sha(ROOT/p)==h,p
    for name,v in spec['dependencies']['packages'].items():assert md.version(name)==v,name
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    d=load_input(input_path,spec);z=features(d);z[['open_time','hl2','rsi','ema5','ema10','adx','entry_signal','exit_signal']].to_csv(out/'signals.csv',index=False,float_format='%.17g');results={}
    for case in spec['cases']:
        n,daily,t,m,events=replay(z,spec,case);name=case['name']
        for suffix,frame in [('nav',n),('daily-nav',daily),('trades',t)]:frame.to_csv(out/f'{name}-{suffix}.csv',index=False,float_format='%.17g')
        write(out/f'{name}-events.json',events);results[name]={'case':case,'metrics':m}
    s={'id':'M0316','origin_run_id':spec['run_id'],'variant_id':spec['variant_id'],'fidelity_class':'HYPOTHESIS','data_quality_status':'DIAGNOSTIC_ONLY','strict_reproductions':0,'trusted':False,'oos_claim':False,'promotion':False,'protocol_sha256':sha(spec_path),'input_sha256':sha(input_path),'engine_sha256':sha(__file__),'actual_strategy_ids':1,'strategy_configurations':4,'controls':1,'parameter_searches':0,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'results':results}
    write(out/'summary.json',s);return s
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--spec',default=str(ROOT/'specs/protocol.json'));a=p.parse_args();print(json.dumps(run(a.input,a.output,a.spec),ensure_ascii=False,indent=2))
