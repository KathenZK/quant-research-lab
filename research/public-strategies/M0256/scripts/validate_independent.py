#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent Decimal EMA and event ledger; never imports replay engine, numpy,
pandas, TA-Lib or qtpylib. Verifies every field/bar/fill and summary metrics.
"""
import argparse,csv,datetime,decimal,hashlib,json,math,pathlib,statistics
D=decimal.Decimal; decimal.getcontext().prec=42
ROOT=pathlib.Path(__file__).resolve().parents[1]
def readcsv(p):
    with open(p,newline='') as f:return list(csv.DictReader(f))
def stamp(ms):return datetime.datetime.fromtimestamp(int(ms)/1000,datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
def epoch(s):return int(datetime.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000)
def close(a,b,tolerance=1e-6):
    assert abs(float(a)-float(b))<=max(tolerance,abs(float(b))*1e-10),(a,b)
def ema(vals,n):
    out=[None]*len(vals); state=sum(vals[:n])/D(n);out[n-1]=state;alpha=D(2)/D(n+1)
    for i in range(n,len(vals)):state=state+(vals[i]-state)*alpha;out[i]=state
    return out

def indicators(rows):
    prices=[D(r['close']) for r in rows];a=ema(prices,8);b=ema(prices,21);entry=[];exit=[]
    for i,r in enumerate(rows):
        ready=i>0 and b[i-1] is not None and D(r['volume'])>0
        entry.append(bool(ready and a[i]>b[i] and a[i-1]<=b[i-1]));exit.append(bool(ready and b[i]>a[i] and b[i-1]<=a[i-1]))
    return a,b,entry,exit

def ledger(rows,signals,spec,case):
    f=D(str(case['fee_bps']))/10000;slip=D(str(spec['execution']['slippage_bps']))/10000
    capital=D(str(spec['execution']['initial_cash']));cash=capital;q=D(0);entry_price=D(0);paid=D(0);cost=D(0);wins=[];events=[];curve=[];amb=0;unresolved=0
    begin=epoch(spec['evaluation']['start']);end=epoch(spec['evaluation']['end_exclusive']);ix=[i for i,r in enumerate(rows) if begin<=int(r['open_time'])<end];first=ix[0]
    for i in ix:
        r=rows[i];override=spec['execution'].get('open_execution_overrides',{}).get(str(int(r['open_time'])))
        effective=int(override['effective_open_ms']) if override else int(r['open_time'])
        o,h,l,c=[D(r[x]) for x in ('open','high','low','close')];src=i-case['delay_bars'];entry=src>=first and signals[2][src];exit=src>=first and signals[3][src];hold=case.get('buy_hold',False)
        if hold:entry=i==first;exit=False
        closed=False
        def event(side,px,why,phase,signal=None):
            nonlocal cash,q,entry_price,paid,cost,closed
            p=px*(D(1)+slip if side=='BUY' else D(1)-slip)
            if side=='BUY':
                budget=cash*D(str(spec['execution']['cash_budget_fraction']));qty=budget/(p*(1+f));value=qty*p;fee=value*f;cash-=value+fee;q=qty;entry_price=p;cost=value+fee
            else:
                qty=q;value=qty*p;fee=value*f;cash+=value-fee;q=D(0);closed=True;wins.append((value-fee)/cost-1)
            paid+=fee
            events.append(dict(trade_id=len(events)+1,bar_index=i,side=side,reason=why,phase=phase,signal_bar_index=signal,reference_price=px,fill_price=p,quantity=qty,notional=value,fee=fee,cash_after=cash,quantity_after=q))
        if q and exit:event('SELL',o,'exit_signal','open',src)
        if not q and entry and not exit and not closed:event('BUY',o,'buy_hold' if hold else 'entry_signal','open',None if hold else src)
        if q and not hold:
            stop=entry_price*(1+D(str(spec['risk']['stoploss'])));target=entry_price*(1+f)*(1+D(str(spec['risk']['minimal_roi']['0'])))/(1-f)
            low=l<=stop;high=h>=target;amb+=int(low and high);unresolved+=int(low and high and stop<o<target)
            if o<=stop:event('SELL',o,'stoploss','open_gap')
            elif o>=target:event('SELL',o,'roi','open_gap')
            elif low:event('SELL',stop,'stoploss','intrabar_unknown')
            elif high:event('SELL',target,'roi','intrabar_unknown')
        curve.append(dict(bar_index=i,cash=cash,quantity=q,close=c,equity=cash+q*c,nav=(cash+q*c)/capital))
    daily=[a for j,a in enumerate(curve) if j==len(curve)-1 or int(rows[curve[j+1]['bar_index']]['open_time'])//86400000!=int(rows[a['bar_index']]['open_time'])//86400000]
    values=[capital]+[a['equity'] for a in curve];dailyvalues=[capital]+[a['equity'] for a in daily]
    returns=[float(b/a-1) for a,b in zip(values,values[1:])];dailyreturns=[float(b/a-1) for a,b in zip(dailyvalues,dailyvalues[1:])]
    peak=capital;dd=D(0)
    for x in values:peak=max(x,peak);dd=max(dd,1-x/peak)
    sharpe=lambda r,s:statistics.mean(r)/statistics.stdev(r)*math.sqrt(s) if statistics.stdev(r)>0 else None
    result={'observations':len(curve),'daily_observations':len(daily),'total_return':float(values[-1]/capital-1),'annualized_return':float(values[-1]/capital)**(365/((end-begin)/86400000))-1,
            'max_drawdown':float(dd),'sharpe':sharpe(dailyreturns,365),'sharpe_4h':sharpe(returns,2190),'final_equity':float(values[-1]),'trades':len(events),'round_trips':len(wins),
            'winning_round_trip_fraction':sum(x>0 for x in wins)/len(wins) if wins else None,'fees_paid':float(paid),'position_bar_fraction':sum(x['quantity']>0 for x in curve)/len(curve),
            'final_cash':float(cash),'final_quantity':float(q),'same_bar_stop_roi_hits':amb,'intrabar_stop_roi_ambiguities':unresolved}
    return curve,daily,events,result

def validate(input_path,result_path,spec_path):
    spec=json.loads(pathlib.Path(spec_path).read_text());assert hashlib.sha256(pathlib.Path(input_path).read_bytes()).hexdigest()==spec['input']['sha256']
    rows=readcsv(input_path);signal=indicators(rows);reported=readcsv(pathlib.Path(result_path)/'signals.csv');assert len(rows)==len(reported)
    max_errors={}
    for j,k in enumerate(['ema8','ema21']):
        errors=[]
        for i,r in enumerate(reported):
            expected=signal[j][i]
            if expected is None:assert r[k]==''
            else:close(expected,r[k],1e-8);errors.append(abs(float(expected)-float(r[k])))
        max_errors[k]=max(errors)
    for i,r in enumerate(reported):assert int(r['entry_signal'])==signal[2][i] and int(r['exit_signal'])==signal[3][i],i
    summary=json.loads((pathlib.Path(result_path)/'summary.json').read_text());checks={}
    assert summary['protocol_sha256']==hashlib.sha256(pathlib.Path(spec_path).read_bytes()).hexdigest()
    assert summary['input_sha256']==spec['input']['sha256']
    assert summary['dependency_runtime']['TA-Lib']==spec['dependencies']['TA-Lib']=='0.6.8'
    assert summary['dependency_runtime']['ta_library'].startswith(spec['dependencies']['ta_library']) and spec['dependencies']['ta_library']=='0.6.4'
    for case in spec['cases']:
        name=case['name'];curve,daily,events,metrics=ledger(rows,signal,spec,case)
        pairs=[('nav',curve),('daily-nav',daily),('trades',events)]
        if name=='base':pairs.append(('nav-light',daily))
        for suffix,expect in pairs:
            actual=readcsv(pathlib.Path(result_path)/f'{name}-{suffix}.csv');assert len(actual)==len(expect),(name,suffix)
            for i,(a,b) in enumerate(zip(actual,expect)):
                for k,v in b.items():
                    if v is None:assert a[k]=='', (name,suffix,i,k)
                    elif isinstance(v,str):assert a[k]==v
                    else:close(a[k],v)
                if suffix=='trades':
                    idx=int(a['bar_index']);assert epoch(a['bar_open_utc'])==int(rows[idx]['open_time'])
                    shift=spec['execution'].get('open_execution_overrides',{}).get(str(int(rows[idx]['open_time'])))
                    effective=int(shift['effective_open_ms']) if shift else int(rows[idx]['open_time'])
                    assert epoch(a['execution_earliest_utc'])==effective
                    if a['phase'] in ('open','open_gap'):
                        assert epoch(a['execution_time_utc'])==epoch(a['execution_latest_utc'])==effective
                    else:
                        latest=spec['execution'].get('intrabar_execution_latest_overrides',{}).get(str(int(rows[idx]['open_time'])),int(rows[idx]['close_time']))
                        assert a['execution_time_utc']=='' and epoch(a['execution_latest_utc'])==int(latest)
                    assert a['execution_time_basis']==(shift['basis'] if shift else 'native_4h_open_proxy')
                    if a['signal_bar_index']:
                        source=int(float(a['signal_bar_index']));assert epoch(a['signal_close_utc'])==int(rows[source]['close_time']);assert int(rows[source]['close_time'])<int(rows[idx]['open_time'])
                else:assert epoch(a['timestamp_utc'])==int(rows[int(a['bar_index'])]['close_time'])+1
        for k,v in metrics.items():
            if v is None:assert summary['results'][name]['metrics'][k] is None
            else:close(summary['results'][name]['metrics'][k],v)
        checks[name]={'bar_ledger_rows':len(curve),'daily_rows':len(daily),'fills':len(events),'summary_metrics_checked':len(metrics),'status':'PASS'}
    return {'status':'PASS','method':'independent stdlib Decimal EMA + Decimal event ledger, no engine/TA-Lib/qtpylib import','indicator_max_absolute_errors':max_errors,'signals_rows':len(rows),'cases':checks,'tolerance':'max(1e-6 absolute, 1e-10 relative); indicators 1e-8 absolute or 1e-10 relative'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--results',required=True);p.add_argument('--spec',default=str(ROOT/'specs/M0256-first-replay.json'));p.add_argument('--output',required=True);a=p.parse_args()
    result=validate(a.input,a.results,a.spec);pathlib.Path(a.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
