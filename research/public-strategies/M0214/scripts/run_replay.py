"""M0214 spot long-only ADAPTATION, raw opening prices for execution."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

INPUT_HASH = "48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5"
CASES = [("base", 8, 1, False), ("fee0", 0, 1, False),
         ("fee20", 20, 1, False), ("lag2", 8, 2, False), ("buyhold", 8, 1, True)]


def indicators(frame):
    hac = frame[['open','high','low','close']].mean(axis=1).to_numpy()
    hao = np.zeros(len(frame))
    hao[0] = (frame.iloc[0].open + frame.iloc[0].close)/2
    for i in range(1,len(frame)):
        hao[i] = (hao[i-1]+hac[i-1])/2
    fast, slow = frame.close.rolling(10).mean(), frame.close.rolling(20).mean()
    green = hac > hao
    turn_green = green & ~np.r_[True,green[:-1]]
    cross = (frame.close > fast) & (frame.close.shift() <= fast.shift())
    entry = (fast > slow) & cross & turn_green
    leave = (hac < hao) | (frame.close <= fast) | (fast <= slow)
    return hao,hac,fast.to_numpy(),slow.to_numpy(),entry.to_numpy(),leave.to_numpy()


def run(frame, fee_bps=8, lag=1, benchmark=False):
    hao,hac,fast,slow,entries,exits = indicators(frame)
    cash, qty, peak = 100000., 0., 100000.
    pending, nav, fills = {}, [], []
    for i, row in frame.iterrows():
        if row.date < "2023-01-01":
            continue
        action, decision = pending.pop(i, (0, None))
        if benchmark and not nav:
            action = 1
        if action == 1 and qty == 0:
            price = row.open * 1.0002
            amount = cash * .95
            delta = amount / price
        elif action == -1 and qty > 0:
            price = row.open * .9998
            delta = -qty
            amount = -delta * price
        else:
            delta = 0
        if delta:
            charge = amount * fee_bps / 10000
            cash -= delta * price + charge
            qty += delta
            fills.append(dict(date=row.date, signal_date=decision,
                              side="BUY" if delta > 0 else "SELL", quantity=abs(delta),
                              price=price, fee=charge, cash_after=cash, position_after=qty))
        equity = cash + qty * row.close
        peak = max(peak, equity)
        signal = 0
        if not benchmark:
            if qty > 0 and exits[i]:
                signal = -1
            elif qty == 0 and entries[i]:
                signal = 1
            if signal and i + lag < len(frame):
                pending[i+lag] = (signal, row.date)
        assert cash >= 0 and qty >= 0 and np.isfinite(equity)
        nav.append(dict(date=row.date, equity=equity, cash=cash, quantity=qty,
                        drawdown=equity/peak-1, ha_open=hao[i],ha_close=hac[i],sma10=fast[i],sma20=slow[i],entry_condition=bool(entries[i]),exit_condition=bool(exits[i]),signal=signal))
    return pd.DataFrame(nav), pd.DataFrame(fills,columns=['date','signal_date','side','quantity','price','fee','cash_after','position_after'])


def metrics(nav):
    values = np.r_[100000., nav.equity.to_numpy()]
    rets = values[1:] / values[:-1] - 1
    return dict(total_return=float(values[-1]/values[0]-1),
                cagr=float((values[-1]/values[0])**(365/len(nav))-1),
                max_drawdown=float(min(values/np.maximum.accumulate(values)-1)),
                sharpe_zero_cash=float(rets.mean()/rets.std(ddof=1)*np.sqrt(365)) if rets.std(ddof=1)>0 else None,
                final_equity=float(values[-1]), observations=len(nav))


def load(path):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == INPUT_HASH
    f = pd.read_csv(path)
    assert len(f) == 762 and f.open_time.is_monotonic_increasing
    assert np.all(np.diff(f.open_time) == 86400000)
    f['date'] = pd.to_datetime(f.open_time, unit='ms', utc=True).dt.strftime('%Y-%m-%d')
    return f


def main(path, out):
    frame = load(path)
    out.mkdir(parents=True, exist_ok=False)
    summary = {}
    for name, fee, lag, bench in CASES:
        nav, fills = run(frame, fee, lag, bench)
        nav.to_csv(out/f'{name}-nav.csv', index=False, float_format='%.12g')
        fills.to_csv(out/f'{name}-trades.csv', index=False, float_format='%.12g')
        summary[name] = dict(metrics=metrics(nav), fills=len(fills),
                             completed_round_trips=int((fills.side == 'SELL').sum()))
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))
