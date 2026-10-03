"""Frozen M0216 spot historical hypothesis; no exchange or credential access."""

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]


def run(frame, config, fee_bps=8, lag=1, benchmark=False):
    fast = frame.close.rolling(config["short"]).mean()
    slow = frame.close.rolling(config["long"]).mean()
    signals = np.where(
        (fast > slow) & (fast.shift() <= slow.shift()),
        1,
        np.where((fast < slow) & (fast.shift() >= slow.shift()), -1, 0),
    )
    cash = float(config["initial_cash"])
    quantity = 0.0
    peak = cash
    halt = False
    queue = {}
    nav = []
    trades = []
    events = []
    fee = fee_bps / 10000
    slip = config["slippage_bps"] / 10000
    for i, row in frame.iterrows():
        if row.date < "2023-01-01":
            continue
        action = queue.pop(i, 0)
        if benchmark and not nav:
            action = 1
        if action == 1 and quantity == 0:
            price = row.open * (1 + slip)
            notional = cash * config["buy_fraction_cash"]
            delta = notional / price
        elif action == -1 and quantity > 0:
            price = row.open * (1 - slip)
            delta = -quantity
            notional = abs(delta) * price
        else:
            delta = 0
        if delta:
            charge = notional * fee
            cash -= delta * price + charge
            quantity += delta
            trades.append(
                dict(
                    date=row.date,
                    signal_date=frame.iloc[i - lag].date if not benchmark else None,
                    side="BUY" if delta > 0 else "SELL",
                    quantity=abs(delta),
                    price=price,
                    fee=charge,
                    cash_after=cash,
                    position_after=quantity,
                )
            )
        equity = cash + quantity * row.close
        peak = max(peak, equity)
        if not benchmark and not halt and 1 - equity / peak >= config["max_drawdown"]:
            halt = True
            events.append(
                dict(
                    date=row.date,
                    event="PERMANENT_HALT_BLOCKS_ALL_ORDERS",
                    equity=equity,
                    position=quantity,
                )
            )
        if (
            not benchmark
            and not halt
            and i >= config["minimum_bars"] - 1
            and signals[i]
            and i + lag < len(frame)
        ):
            queue[i + lag] = int(signals[i])
        assert cash >= -1e-8 and quantity >= 0 and np.isfinite(equity)
        nav.append(
            dict(
                date=row.date,
                equity=equity,
                cash=cash,
                quantity=quantity,
                drawdown=equity / peak - 1,
                halted=halt,
                signal=int(signals[i]),
            )
        )
    return pd.DataFrame(nav), pd.DataFrame(trades), events


def metrics(nav, initial):
    values = np.r_[initial, nav.equity.to_numpy()]
    returns = values[1:] / values[:-1] - 1
    return dict(
        total_return=float(values[-1] / initial - 1),
        cagr=float((values[-1] / initial) ** (365 / len(nav)) - 1),
        max_drawdown=float(np.min(values / np.maximum.accumulate(values) - 1)),
        sharpe_zero_cash=float(returns.mean() / returns.std(ddof=1) * np.sqrt(365))
        if returns.std(ddof=1) > 0
        else None,
        observations=len(nav),
        final_equity=float(values[-1]),
    )


def main(out):
    config = json.loads((FAMILY / "specs/M0216-first-replay.json").read_text())
    inputs = FAMILY / "artifacts/20261003-first-replay"
    manifest = json.loads((inputs / "input-manifest.json").read_text())
    assert (
        hashlib.sha256((inputs / "input.csv").read_bytes()).hexdigest()
        == manifest["input_sha256"]
    )
    frame = pd.read_csv(inputs / "input.csv")
    frame["date"] = pd.to_datetime(frame.open_time, unit="ms", utc=True).dt.strftime(
        "%Y-%m-%d"
    )
    out.mkdir(parents=True, exist_ok=False)
    results = {}
    for name, fee, lag, bench in [
        ("base", 8, 1, False),
        ("fee0", 0, 1, False),
        ("fee20", 20, 1, False),
        ("lag2", 8, 2, False),
        ("buyhold", 8, 1, True),
    ]:
        nav, trades, events = run(frame, config, fee, lag, bench)
        nav.to_csv(out / f"{name}-nav.csv", index=False, float_format="%.12g")
        trades.to_csv(out / f"{name}-trades.csv", index=False, float_format="%.12g")
        periods = {}
        for year in ["2023", "2024"]:
            section = nav[nav.date.str.startswith(year)]
            first = section.index[0]
            initial = (
                config["initial_cash"] if first == 0 else nav.iloc[first - 1].equity
            )
            periods[year] = metrics(section, initial)
        results[name] = dict(
            metrics=metrics(nav, config["initial_cash"]),
            fills=len(trades),
            completed_round_trips=int((trades.side == "SELL").sum()),
            events=events,
            periods=periods,
        )
    (out / "summary.json").write_text(
        json.dumps(results, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
