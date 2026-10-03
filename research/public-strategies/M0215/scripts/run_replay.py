"""M0215 BTC leg hypothesis. Offline, frozen input only."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
INPUT_HASH = "48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5"
CASES = [("base", 8, 1, False), ("fee0", 0, 1, False),
         ("fee20", 20, 1, False), ("lag2", 8, 2, False), ("buyhold", 8, 1, True)]


def rsi2(prices):
    delta = np.diff(prices)
    gains, losses = np.maximum(delta, 0), np.maximum(-delta, 0)
    result = np.full(len(prices), np.nan)
    g, loss = float(gains[:2].mean()), float(losses[:2].mean())
    for i in range(2, len(prices)):
        if i > 2:
            g, loss = (g + gains[i-1])/2, (loss + losses[i-1])/2
        result[i] = 50 if g == loss == 0 else 100*g/(g+loss)
    return result


def run(frame, fee_bps=8, lag=1, benchmark=False):
    indicator = rsi2(frame.close.to_numpy())
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
            if qty > 0 and row.close > frame.iloc[i-1].high:
                signal = -1
            elif qty == 0 and indicator[i] < 10:
                signal = 1
            if signal and i + lag < len(frame):
                pending[i+lag] = (signal, row.date)
        assert cash >= 0 and qty >= 0 and np.isfinite(equity)
        nav.append(dict(date=row.date, equity=equity, cash=cash, quantity=qty,
                        drawdown=equity/peak-1, rsi2=indicator[i], signal=signal))
    return pd.DataFrame(nav), pd.DataFrame(fills)


def metrics(nav):
    values = np.r_[100000., nav.equity.to_numpy()]
    rets = values[1:] / values[:-1] - 1
    return dict(total_return=float(values[-1]/values[0]-1),
                cagr=float((values[-1]/values[0])**(365/len(nav))-1),
                max_drawdown=float(min(values/np.maximum.accumulate(values)-1)),
                sharpe_zero_cash=float(rets.mean()/rets.std(ddof=1)*np.sqrt(365)),
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
