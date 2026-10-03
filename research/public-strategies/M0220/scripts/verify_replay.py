"""Independent csv/Decimal weekly EMA, ATR and account reconstruction."""
import csv
from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
import json
import math
from pathlib import Path
import sys


def verify(source,results):
    bars = list(csv.DictReader(source.open()))
    dates = [datetime.fromtimestamp(int(b['open_time'])/1000,timezone.utc).date() for b in bars]
    opens,highs,lows,closes = [[D(b[key]) for b in bars] for key in ['open','high','low','close']]
    weekly = {}
    for i,date in enumerate(dates):
        start = date-timedelta(days=date.weekday())
        weekly.setdefault(start,[]).append(i)
    week_values = {}
    we = None
    count = 0
    for start,indices in sorted(weekly.items()):
        if len(indices)==7:
            last = closes[indices[-1]]
            we = last if we is None else we+D(2)/21*(last-we)
            count += 1
            week_values[start+timedelta(days=7)] = (we,count)
    day,atr,true_ranges,caution,higher = [],[],[],[],[]
    for i,date in enumerate(dates):
        day.append(closes[i] if i==0 else day[-1]+D(2)/21*(closes[i]-day[-1]))
        tr = highs[i]-lows[i]
        if i:
            tr = max(tr,abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1]))
        true_ranges.append(tr)
        atr.append(None if i<4 else sum(true_ranges[:5])/5 if i==4 else (atr[-1]*4+tr)/5)
        start = date-timedelta(days=date.weekday())
        hw,num = week_values.get(start,(None,0))
        higher.append((hw,num))
        caution.append(bool(hw is not None and closes[i]>hw and atr[i] is not None and (max(highs[max(0,i-6):i+1])-lows[i]>atr[i]*D('1.5') or closes[i]<day[i])))
    reports = {}
    for name,fee,lag,bench in [('base','.001',1,False),('fee0','0',1,False),('fee20','.002',1,False),('lag2','.001',2,False),('buyhold','.001',1,True)]:
        cash,qty,peak = D(10000),D(0),D(10000)
        stop = None
        queue,expected,fills = {},[],[]
        for i,date in enumerate(dates):
            dt = date.isoformat()
            if dt<'2023-04-24':
                continue
            action,decision = queue.pop(i,(0,None))
            if bench and dt=='2023-04-25':
                action = 1
            if action==1 and qty==0:
                price = opens[i]*D('1.0002')
                notional = cash/(1+D(fee))
                delta = notional/price
            elif action==-1 and qty>0:
                price = opens[i]*D('.9998')
                delta = -qty
                notional = -delta*price
            else:
                delta = D(0)
            if delta:
                charge = notional*D(fee)
                cash -= delta*price+charge
                if abs(cash)<D('1e-20'):
                    cash = D(0)
                qty += delta
                fills.append(dict(date=dt,signal_date=decision or '',side='BUY' if delta>0 else 'SELL',quantity=float(abs(delta)),price=float(price),fee=float(charge),cash_after=float(cash),position_after=float(qty)))
            hw,num = higher[i]
            signal = 0
            if not bench and num>=20:
                if qty>0:
                    candidate = max(lows[i-6:i+1])-atr[i]*(D('.2') if caution[i-1] else D(1))
                    stop = candidate if stop is None else max(stop,candidate)
                    if closes[i]<stop or closes[i]<hw:
                        signal = -1
                elif closes[i]>hw and not caution[i]:
                    signal = 1
                    stop = None
                if signal and i+lag<len(bars):
                    queue[i+lag] = (signal,dt)
            total = cash+qty*closes[i]
            peak = max(peak,total)
            if dt>='2023-04-25':
                expected.append(dict(date=dt,equity=float(total),cash=float(cash),quantity=float(qty),drawdown=float(total/peak-1),signal=signal,trail_stop=None if stop is None else float(stop),daily_ema=float(day[i]),weekly_ema=float(hw),weekly_count=num,atr=float(atr[i]),caution=str(caution[i])))
        actual = list(csv.DictReader((results/f'{name}-nav.csv').open()))
        actualfills = list(csv.DictReader((results/f'{name}-trades.csv').open()))
        assert len(actual)==len(expected)==617 and len(actualfills)==len(fills)
        error = 0.
        for a,e in zip(actual+actualfills,expected+fills,strict=True):
            for key,value in e.items():
                if value is None:
                    assert a[key]=='',(name,key,a,e)
                elif isinstance(value,str):
                    assert a[key]==value,(name,key,a,e)
                else:
                    assert math.isclose(float(a[key]),value,rel_tol=1e-10,abs_tol=1e-6),(name,key,a,e)
            if 'equity' in e:
                error = max(error,abs(float(a['equity'])-e['equity']))
        reports[name] = dict(status='PASS',daily_rows=len(actual),fills=len(fills),max_equity_error=error)
    return reports


if __name__=='__main__':
    print(json.dumps(verify(Path(sys.argv[1]),Path(sys.argv[2])),indent=2))
