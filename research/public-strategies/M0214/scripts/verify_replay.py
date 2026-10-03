"""Independent Decimal HA/SMA and account ledger. Does not import strategy engine."""
import csv
from datetime import datetime, timezone
from decimal import Decimal as D
import json
import math
from pathlib import Path
import sys


def verify(source, directory):
    bars = list(csv.DictReader(source.open()))
    dates = [datetime.fromtimestamp(int(b['open_time'])/1000, timezone.utc).date().isoformat() for b in bars]
    close = [D(b['close']) for b in bars]
    ha_open, ha_close, fast, slow = [], [], [], []
    for i,b in enumerate(bars):
        ha_close.append(sum(D(b[k]) for k in ['open','high','low','close'])/4)
        ha_open.append((D(b['open'])+D(b['close']))/2 if i == 0 else (ha_open[-1]+ha_close[-2])/2)
        fast.append(None if i < 9 else sum(close[i-9:i+1])/10)
        slow.append(None if i < 19 else sum(close[i-19:i+1])/20)
    checks = {}
    for name, fee, lag, benchmark in [('base','.0008',1,False),('fee0','0',1,False),('fee20','.002',1,False),('lag2','.0008',2,False),('buyhold','.0008',1,True)]:
        cash, qty, peak = D(100000),D(0),D(100000)
        queue, expected, trades = {},[],[]
        for i,b in enumerate(bars):
            if dates[i] < '2023-01-01':
                continue
            action, signaldate = queue.pop(i,(0,None))
            if benchmark and not expected:
                action = 1
            if action == 1 and qty == 0:
                price = D(b['open'])*D('1.0002')
                amount = cash*D('.95')
                change = amount/price
            elif action == -1 and qty > 0:
                price = D(b['open'])*D('.9998')
                change = -qty
                amount = -change*price
            else:
                change = D(0)
            if change:
                charge = amount*D(fee)
                qty += change
                cash -= change*price+charge
                trades.append(dict(date=dates[i],signal_date=signaldate or '',side='BUY' if change>0 else 'SELL',quantity=float(abs(change)),price=float(price),fee=float(charge),cash_after=float(cash),position_after=float(qty)))
            total = cash+qty*D(b['close'])
            peak = max(peak,total)
            signal = 0
            if not benchmark:
                if qty > 0 and (ha_close[i]<ha_open[i] or close[i]<=fast[i] or fast[i]<=slow[i]):
                    signal = -1
                elif qty == 0 and (fast[i]>slow[i] and close[i]>fast[i] and close[i-1]<=fast[i-1] and ha_close[i]>ha_open[i] and ha_close[i-1]<=ha_open[i-1]):
                    signal = 1
                if signal and i+lag < len(bars):
                    queue[i+lag] = (signal,dates[i])
            expected.append(dict(date=dates[i],equity=float(total),cash=float(cash),quantity=float(qty),drawdown=float(total/peak-1),ha_open=float(ha_open[i]),ha_close=float(ha_close[i]),sma10=float(fast[i]),sma20=float(slow[i]),signal=signal))
        actual = list(csv.DictReader((directory/f'{name}-nav.csv').open()))
        actualtrades = list(csv.DictReader((directory/f'{name}-trades.csv').open()))
        assert len(actual) == len(expected) == 731
        assert len(actualtrades) == len(trades)
        maximum = 0.
        for a,e in zip(actual+actualtrades, expected+trades, strict=True):
            for key,value in e.items():
                if isinstance(value,str):
                    assert a[key] == value,(name,key,a,e)
                else:
                    assert math.isclose(float(a[key]),value,rel_tol=1e-10,abs_tol=1e-6),(name,key,a,e)
            if 'equity' in e:
                maximum = max(maximum,abs(float(a['equity'])-e['equity']))
        checks[name] = dict(status='PASS',daily_rows=len(actual),fills=len(trades),max_equity_error=maximum)
    return checks


if __name__ == '__main__':
    print(json.dumps(verify(Path(sys.argv[1]),Path(sys.argv[2])),indent=2))
