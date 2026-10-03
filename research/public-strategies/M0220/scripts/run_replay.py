"""M0220 source-anchored hypothesis. Closed UTC weeks; cash-inclusive fees."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

INPUT_HASH = '48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5'
CASES = [('base',10,1,False),('fee0',0,1,False),('fee20',20,1,False),('lag2',10,2,False),('buyhold',10,1,True)]
FIRST_DECISION = '2023-04-24'
FIRST_MARK = '2023-04-25'


def indicators(frame):
    n = len(frame)
    daily = np.zeros(n)
    daily[0] = frame.iloc[0].close
    tr = np.zeros(n)
    for i,row in frame.iterrows():
        if i:
            daily[i] = daily[i-1]*19/21 + row.close*2/21
        tr[i] = max(row.high-row.low,abs(row.high-frame.iloc[i-1].close),abs(row.low-frame.iloc[i-1].close)) if i else row.high-row.low
    atr = np.full(n,np.nan)
    atr[4] = tr[:5].mean()
    for i in range(5,n):
        atr[i] = (atr[i-1]*4+tr[i])/5
    dates = pd.to_datetime(frame.date,utc=True)
    starts = dates-pd.to_timedelta(dates.dt.weekday,unit='D')
    weeks = pd.DataFrame({'start':starts,'close':frame.close}).groupby('start').agg(count=('close','size'),close=('close','last'))
    weekmap = {}
    value = None
    count = 0
    for start,row in weeks.iterrows():
        if row['count'] != 7:
            continue
        value = row.close if value is None else value*19/21+row.close*2/21
        count += 1
        weekmap[start+pd.Timedelta(days=7)] = (value,count)
    weekly = np.array([weekmap.get(s,(np.nan,0))[0] for s in starts])
    counts = np.array([weekmap.get(s,(np.nan,0))[1] for s in starts])
    hi = frame.high.rolling(7).max().to_numpy()
    lo = frame.low.rolling(7).max().to_numpy()
    bull = frame.close.to_numpy()>weekly
    caution = bull & ((hi-frame.low.to_numpy()>atr*1.5) | (frame.close.to_numpy()<daily))
    return dict(daily_ema=daily,weekly_ema=weekly,weekly_count=counts,atr=atr,highest_low=lo,bull=bull,caution=caution)


def ratchet(previous, highest_low, atr, previous_caution):
    proposal = highest_low-atr*(.2 if previous_caution else 1.)
    return proposal if previous is None else max(previous,proposal)


def run(frame,fee_bps=10,lag=1,benchmark=False):
    ind = indicators(frame)
    cash,qty,peak = 10000.,0.,10000.
    stop = None
    queue,nav,trades = {},[],[]
    for i,row in frame.iterrows():
        if row.date < FIRST_DECISION:
            continue
        action,signal_date = queue.pop(i,(0,None))
        if benchmark and row.date == FIRST_MARK:
            action = 1
        if action==1 and qty==0:
            price = row.open*1.0002
            amount = cash/(1+fee_bps/10000)
            delta = amount/price
        elif action==-1 and qty>0:
            price = row.open*.9998
            delta = -qty
            amount = -delta*price
        else:
            delta = 0.
        if delta:
            fee = amount*fee_bps/10000
            cash -= delta*price+fee
            if abs(cash)<1e-9:
                cash = 0.
            qty += delta
            trades.append(dict(date=row.date,signal_date=signal_date,side='BUY' if delta>0 else 'SELL',quantity=abs(delta),price=price,fee=fee,cash_after=cash,position_after=qty))
        signal = 0
        if not benchmark and ind['weekly_count'][i]>=20:
            if qty>0:
                stop = ratchet(stop,ind['highest_low'][i],ind['atr'][i],bool(ind['caution'][i-1]))
                if row.close<stop or row.close<ind['weekly_ema'][i]:
                    signal = -1
            elif ind['bull'][i] and not ind['caution'][i]:
                signal = 1
                stop = None
            if signal and i+lag<len(frame):
                queue[i+lag] = (signal,row.date)
        equity = cash+qty*row.close
        peak = max(peak,equity)
        assert cash>=-1e-8 and qty>=0 and np.isfinite(equity)
        if row.date >= FIRST_MARK:
            nav.append(dict(date=row.date,equity=equity,cash=cash,quantity=qty,drawdown=equity/peak-1,signal=signal,trail_stop=stop,daily_ema=ind['daily_ema'][i],weekly_ema=ind['weekly_ema'][i],weekly_count=int(ind['weekly_count'][i]),atr=ind['atr'][i],caution=bool(ind['caution'][i])))
    return pd.DataFrame(nav),pd.DataFrame(trades,columns=['date','signal_date','side','quantity','price','fee','cash_after','position_after'])


def metrics(nav):
    values = np.r_[10000.,nav.equity.to_numpy()]
    rets = values[1:]/values[:-1]-1
    return dict(total_return=float(values[-1]/values[0]-1),cagr=float((values[-1]/values[0])**(365/len(nav))-1),max_drawdown=float(min(values/np.maximum.accumulate(values)-1)),sharpe_zero_cash=float(rets.mean()/rets.std(ddof=1)*np.sqrt(365)) if rets.std(ddof=1)>0 else None,final_equity=float(values[-1]),observations=len(nav),start=FIRST_MARK,end='2024-12-31')


def load(path):
    assert hashlib.sha256(path.read_bytes()).hexdigest()==INPUT_HASH
    frame = pd.read_csv(path)
    assert len(frame)==762 and np.all(np.diff(frame.open_time)==86400000)
    frame['date'] = pd.to_datetime(frame.open_time,unit='ms',utc=True).dt.strftime('%Y-%m-%d')
    return frame


def main(path,out):
    frame = load(path)
    out.mkdir(parents=True,exist_ok=False)
    summary = {}
    for name,fee,lag,bench in CASES:
        nav,trades = run(frame,fee,lag,bench)
        assert len(nav)==617
        nav.to_csv(out/f'{name}-nav.csv',index=False,float_format='%.12g')
        trades.to_csv(out/f'{name}-trades.csv',index=False,float_format='%.12g')
        summary[name] = dict(metrics=metrics(nav),fills=len(trades),completed_round_trips=int((trades.side=='SELL').sum()))
    (out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]),Path(sys.argv[2]))
