"""Frozen M0212 execution-anchor V2 hypothesis; independent spot diagnostic, no external services."""

import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

HASH = "48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5"
CONFIGS = [
    ("base", 8, 1, False),
    ("fee0", 0, 1, False),
    ("fee20", 20, 1, False),
    ("lag2", 8, 2, False),
    ("buyhold", 8, 1, True),
]


def features(df):
    return df.close.ewm(span=3, adjust=False).mean().to_numpy()


def run(df, fee=8, lag=1, benchmark=False):
    ema3 = features(df)
    cash, qty = 100000.0, 0.0
    entry_index = None
    pending = None
    nav, trades = [], []
    for i, row in df.iterrows():
        date = pd.to_datetime(row.open_time, unit="ms", utc=True).strftime("%Y-%m-%d")
        if not "2023-01-01" <= date <= "2024-12-31":
            continue
        order = "BUY" if benchmark and not nav else None
        signal = None
        if pending and pending[0] == i:
            _, order, signal = pending
            pending = None
        if order:
            px = row.open * (1.0002 if order == "BUY" else 0.9998)
            size = cash * 0.95 / px if order == "BUY" else qty
            charge = size * px * fee / 10000
            if order == "BUY":
                cash -= size * px + charge
                qty += size
                entry_index = i
            else:
                cash += size * px - charge
                qty = 0.0
                entry_index = None
            trades.append(
                dict(
                    date=date,
                    side=order,
                    quantity=size,
                    price=px,
                    fee=charge,
                    signal_index=signal,
                )
            )
        nav.append(
            dict(date=date, cash=cash, quantity=qty, equity=cash + qty * row.close)
        )
        if not benchmark and pending is None:
            if (
                qty == 0
                and df.volume.iloc[i] <= df.volume.iloc[i - 3]
                and df.close.iloc[i] <= df.low.iloc[i - 1]
            ):
                pending = (i + lag, "BUY", i)
            elif qty > 0 and (df.close.iloc[i] > ema3[i] or i - entry_index + 1 >= 6):
                pending = (i + lag, "SELL", i)
    return pd.DataFrame(nav), pd.DataFrame(
        trades, columns=["date", "side", "quantity", "price", "fee", "signal_index"]
    )


def metrics(nav, trades):
    e = np.r_[100000.0, nav.equity.to_numpy()]
    ret = e[1:] / e[:-1] - 1
    return dict(
        days=len(nav),
        return_pct=(e[-1] / e[0] - 1) * 100,
        cagr_pct=((e[-1] / e[0]) ** (365 / len(nav)) - 1) * 100,
        max_drawdown_pct=float((1 - e / np.maximum.accumulate(e)).max() * 100),
        sharpe_daily_365=float(ret.mean() / ret.std(ddof=1) * np.sqrt(365)),
        fills=len(trades),
        fees=float(trades.fee.sum()),
        terminal_quantity=float(nav.quantity.iloc[-1]),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    raw = Path(a.input).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == HASH
    df = pd.read_csv(a.input)
    assert len(df) == 762 and df.open_time.diff().dropna().eq(86400000).all()
    assert df.close_time.sub(df.open_time).eq(86399999).all()
    assert (df[["open", "high", "low", "close", "volume"]] > 0).all().all()
    assert (df.high >= df[["open", "close", "low"]].max(axis=1)).all() and (
        df.low <= df[["open", "close", "high"]].min(axis=1)
    ).all()
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    summary = {}
    for name, fee, lag, bm in CONFIGS:
        nav, trades = run(df, fee, lag, bm)
        nav.to_csv(out / f"{name}-nav.csv", index=False)
        trades.to_csv(out / f"{name}-trades.csv", index=False)
        summary[name] = metrics(nav, trades)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
