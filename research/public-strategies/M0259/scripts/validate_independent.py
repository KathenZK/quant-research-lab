#!/usr/bin/env python3
"""Independent M0259 oracle. Standard library only; NEVER imports replay/talib/qtpylib.
Recomputes Wilder RSI, direct-window sample BB, and the full event/account ledger.
Authored 2026-10-03; GPL-3.0-or-later.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from statistics import mean,stdev

CASES=[('base',.0008,1,False),('fee0',0.,1,False),('fee20',.002,1,False),('delay2',.0008,2,False),('buyhold',.0008,1,True)]

def read(path):
    with open(path,newline='') as f:return list(csv.DictReader(f))

def reference_indicators(data):
    prices=[float(r['close']) for r in data]
    tp=[(float(r['high'])+float(r['low'])+float(r['close']))/3 for r in data]
    rsi=[None]*len(prices)
    gain=loss=0.
    for i in range(1,len(prices)):
        d=prices[i]-prices[i-1]
        if i<=14:
            gain+=max(d,0);loss+=max(-d,0)
            if i<14:continue
            gain/=14;loss/=14
        else:
            gain=(gain*13+max(d,0))/14
            loss=(loss*13+max(-d,0))/14
        rsi[i]=100*gain/(gain+loss) if gain+loss else 0.
    rows=[]
    for i,p in enumerate(prices):
        w=tp[max(0,i-19):i+1]
        mid=math.fsum(w)/len(w)
        sd=math.sqrt(math.fsum((x-mid)**2 for x in w)/(len(w)-1)) if len(w)>1 else None
        lo=mid-2*sd if sd is not None else None
        hi=mid+2*sd if sd is not None else None
        rows.append({'rsi':rsi[i],'bb_lower':lo,'bb_mid':mid,'bb_upper':hi,
                     'entry':rsi[i] is not None and rsi[i]<30 and lo is not None and p<lo,
                     'exit':rsi[i] is not None and rsi[i]>70})
    return rows

def same_number(actual,expected,abs_tol=2e-6,rel_tol=2e-10):
    if expected is None:
        assert actual=='',('Expected null',actual)
    else:
        assert math.isclose(float(actual),float(expected),abs_tol=abs_tol,rel_tol=rel_tol),(actual,expected)

def oracle(data,ind,fee,delay,bh):
    balance=100000.
    rolling_peak=100000.
    units=0.
    pos=None
    nav=[]
    fills=[]
    transactions=[]
    indexes=[i for i,r in enumerate(data) if '2023-01-01T00:00:00Z'<=r['ts']<'2025-01-01T00:00:00Z']
    for ordinal,i in enumerate(indexes):
        r=data[i]; t=r['ts']; op,hi,lo,cl=[float(r[k]) for k in ['open','high','low','close']]
        trigger=ind[i-delay]
        ref=data[i-delay]['ts']
        entered=False
        liquidate=None
        # Handle only inventory that existed when this bar began.
        if units>0 and not bh:
            floor=pos['entry_fill']*.75
            ceiling=pos['entry_fill']*(1+fee)*1.1/(1-fee)
            candidates=[]
            if trigger['exit']:candidates.append((0,'exit_signal',op,'open'))
            if op<=floor:candidates.append((1,'stop_gap',op,'open'))
            elif op>=ceiling:candidates.append((1,'roi_gap',op,'open'))
            if lo<=floor:candidates.append((2,'stoploss',floor,'intrabar'))
            if hi>=ceiling:candidates.append((3,'roi',ceiling,'intrabar'))
            if candidates:liquidate=min(candidates,key=lambda x:x[0])[1:]
        elif units==0 and ((bh and ordinal==0) or (not bh and trigger['entry'] and not trigger['exit'])):
            allocation=.95*balance
            px=op*1.0002
            units=allocation/(px*(1+fee))
            f=units*px*fee
            balance=balance-allocation
            pos={'entry_ts':t,'entry_signal_ts':None if bh else ref,'entry_fill':px,'entry_raw':op,
                 'qty':units,'entry_fee':f,'entry_budget':allocation,'entry_index':i}
            fills.append(dict(ts=t,side='buy',phase='open',reason='buyhold' if bh else 'entry_signal',
                              signal_ts=None if bh else ref,raw_price=op,fill_price=px,qty=units,fee=f,cash_after=balance))
            entered=True
        if entered and not bh:
            floor=pos['entry_fill']*.75
            ceiling=pos['entry_fill']*(1+fee)*1.1/(1-fee)
            if lo<=floor:liquidate=('stoploss',floor,'intrabar')
            elif hi>=ceiling:liquidate=('roi',ceiling,'intrabar')
        if liquidate:
            why,quote,phase=liquidate
            px=quote*.9998
            f=units*px*fee
            settled=units*px-f
            balance+=settled
            transactions.append({**pos,'exit_ts':t,'exit_signal_ts':ref if why=='exit_signal' else None,
                'exit_raw':quote,'exit_fill':px,'exit_fee':f,'exit_reason':why,'exit_phase':phase,
                'pnl':settled-pos['entry_budget'],'return':settled/pos['entry_budget']-1,
                'holding_bars':i-pos['entry_index']})
            fills.append(dict(ts=t,side='sell',phase=phase,reason=why,signal_ts=ref if why=='exit_signal' else None,
                              raw_price=quote,fill_price=px,qty=units,fee=f,cash_after=balance))
            units=0.;pos=None
        equity=balance+units*cl
        rolling_peak=max(rolling_peak,equity)
        close_ts=(dt.datetime.fromisoformat(t.replace('Z','+00:00'))+dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        nav.append(dict(ts=t,close_ts=close_ts,cash=balance,qty=units,close=cl,equity=equity,drawdown=equity/rolling_peak-1,
                        net_liquidation_equity=balance+units*cl*.9998*(1-fee)))
    return nav,fills,transactions

def compare_rows(actual,expected,columns=None):
    assert len(actual)==len(expected),(len(actual),len(expected))
    for row,ref in zip(actual,expected):
        for key in columns or ref:
            val=ref[key]
            if isinstance(val,(int,float)):same_number(row[key],val)
            else:assert row[key]==('' if val is None else val),(key,row[key],val)

def main():
    a=argparse.ArgumentParser();a.add_argument('--input',required=True);a.add_argument('--results',required=True);a.add_argument('--out',required=True)
    args=a.parse_args();d=read(args.input);out=Path(args.results)
    ind=reference_indicators(d);actual=read(out/'indicators.csv')
    errors={k:0. for k in ['rsi','bb_lower','bb_mid','bb_upper']}
    assert len(actual)==len(ind)
    for a,r in zip(actual,ind):
        for k in errors:
            same_number(a[k],r[k])
            if r[k] is not None:errors[k]=max(errors[k],abs(float(a[k])-r[k]))
        for k in ['entry','exit']:assert a[k]==str(r[k]),(a['ts'],k,a[k],r[k])
    summary=json.loads((out/'summary.json').read_text());cases={}
    for name,fee,lag,bh in CASES:
        nav,fills,trades=oracle(d,ind,fee,lag,bh)
        compare_rows(read(out/(name+'_equity_hourly.csv')),nav)
        compare_rows(read(out/(name+'_fills.csv')),fills)
        if trades:compare_rows(read(out/(name+'_trades.csv')),trades)
        else:assert (out/(name+'_trades.csv')).read_text()=='\n'
        daily_rows={r['ts'][:10]:r for r in nav}
        compare_rows(read(out/(name+'_equity_daily.csv')),list(daily_rows.values()))
        daily={day:r['equity'] for day,r in daily_rows.items()};daily_values=list(daily.values())
        returns=[b/a-1 for a,b in zip([100000.]+daily_values[:-1],daily_values)]
        sharpe=mean(returns)/stdev(returns)*math.sqrt(365) if stdev(returns) else None
        peak=100000.;dd=0.
        for r in nav:peak=max(peak,r['equity']);dd=min(dd,r['equity']/peak-1)
        s=summary['cases'][name]['metrics']
        same_number(s['total_return'],nav[-1]['equity']/100000-1)
        same_number(s['max_drawdown'],dd)
        if sharpe is not None:same_number(s['sharpe'],sharpe)
        same_number(s['total_fees'],sum(f['fee'] for f in fills))
        cases[name]={'status':'PASS','hourly_nav_rows':len(nav),'fills':len(fills),'closed_trades':len(trades),
                     'daily_rows':len(daily),'daily_export_equity_drawdown_close_ts':'PASS','cash_min':min(r['cash'] for r in nav),
                     'independent_total_return':nav[-1]['equity']/100000-1,
                     'independent_daily_sharpe':sharpe,'independent_hourly_max_drawdown':dd}
    result={'status':'PASS','implementation':'stdlib-only separate RSI/BB/event-ledger; no replay/talib/qtpylib imports',
            'input_sha256':hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
            'all_input_indicator_rows':len(ind),'entry_and_exit_signal_mismatches':0,
            'maximum_absolute_indicator_error_after_CSV_roundtrip':errors,'cases':cases,
            'coverage':'every indicator, signal, fill, transaction fee, realized PnL, cash, quantity and hourly NAV; each public daily CSV cash/qty/close/equity/drawdown/close_ts; daily Sharpe and hourly max drawdown'}
    Path(args.out).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':'PASS','cases':len(cases),'indicator_rows':len(ind)}))
if __name__=='__main__':main()
