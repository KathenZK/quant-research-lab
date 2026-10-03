"""M0233 source-derived long-only adaptation; offline research, no exchange access."""
import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev

FAMILY = Path(__file__).resolve().parents[1]
INPUT_SHA = "48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def load(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != INPUT_SHA:
        raise ValueError("Frozen input hash mismatch")
    with path.open() as f:
        rows = list(csv.DictReader(f))
    previous = None
    for r in rows:
        t = int(r["open_time"])
        if previous is not None and t - previous != 86400000:
            raise ValueError("Non-contiguous or duplicate daily grid")
        previous = t
        for k in ("open", "high", "low", "close", "volume"):
            r[k] = float(r[k])
            if not math.isfinite(r[k]):
                raise ValueError("Nonfinite input")
        if not (0 < r["low"] <= min(r["open"], r["close"]) <= max(r["open"], r["close"]) <= r["high"] and r["volume"] > 0):
            raise ValueError("Invalid OHLCV")
        if int(r["close_time"]) != t + 86399999:
            raise ValueError("Unexpected close time")
        r["date"] = datetime.fromtimestamp(t / 1000, timezone.utc).date().isoformat()
    if len(rows) != 762 or rows[0]["date"] != "2022-12-01" or rows[-1]["date"] != "2024-12-31":
        raise ValueError("Unexpected scope")
    return rows


def signals(rows, config):
    out = []
    closes = [r["close"] for r in rows]
    w = config["window"]
    for i in range(len(rows)):
        if i < w - 1:
            out.append(dict(z=None, source_position=0, long_target=0))
            continue
        values = closes[i-w+1:i+1]
        m = math.fsum(values) / w
        variance = math.fsum((x-m)**2 for x in values) / (w-1)
        z = (closes[i]-m) / math.sqrt(variance) if variance else None
        pos = 0 if z is None else (1 if z < -config["z_entry"] else -1 if z > config["z_entry"] else 0)
        # Source initializes each row to zero: z_exit is redundant, no hysteresis.
        if z is not None and abs(z) < config["z_exit"]:
            pos = 0
        out.append(dict(z=z, source_position=pos, long_target=max(pos, 0)))
    return out


def run(rows, config, fee_bps=8, lag=1, benchmark=False):
    sig = signals(rows, config)
    cash = float(config["initial_cash"])
    qty = 0.0
    peak = cash
    nav, trades = [], []
    fee = fee_bps / 10000
    slip = config["slippage_bps"] / 10000
    for i, row in enumerate(rows):
        if row["date"] < config["evaluation_start"]:
            continue
        target = 1 if benchmark else sig[i-lag]["long_target"]
        if target and qty == 0:
            price = row["open"] * (1+slip)
            notional = cash * config["buy_fraction_cash"]
            qty = notional / price
            charge = notional * fee
            cash -= notional + charge
            trades.append(dict(date=row["date"], signal_date=rows[i-lag]["date"] if not benchmark else None, side="BUY", quantity=qty, price=price, fee=charge, cash_after=cash, position_after=qty))
        elif not target and qty > 0:
            price = row["open"] * (1-slip)
            notional = qty * price
            charge = notional * fee
            cash += notional-charge
            trades.append(dict(date=row["date"], signal_date=rows[i-lag]["date"], side="SELL", quantity=qty, price=price, fee=charge, cash_after=cash, position_after=0.0))
            qty = 0.0
        equity = cash+qty*row["close"]
        peak = max(peak, equity)
        assert cash >= 0 and qty >= 0 and math.isfinite(equity)
        nav.append(dict(date=row["date"], equity=equity, cash=cash, quantity=qty, drawdown=equity/peak-1, target=target))
    return nav, trades


def metrics(nav, initial):
    previous = initial
    returns = []
    peak = initial
    dd = 0.0
    for r in nav:
        returns.append(r["equity"] / previous - 1)
        previous = r["equity"]
        peak = max(peak, previous)
        dd = min(dd, previous / peak - 1)
    return dict(observations=len(nav), final_equity=previous, total_return=previous / initial - 1, cagr=(previous / initial) ** (365 / len(nav)) - 1, max_drawdown=dd, sharpe_zero_cash=mean(returns) / stdev(returns) * math.sqrt(365) if stdev(returns) else None)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    rows = load(args.input)
    config = json.loads((FAMILY / "specs/M0233-first-replay.json").read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    summary = {}
    for name, fee, lag, benchmark in (("base",8,1,False),("fee0",0,1,False),("fee20",20,1,False),("lag2",8,2,False),("buy_hold",8,1,True)):
        nav, trades = run(rows, config, fee, lag, benchmark)
        for suffix, records in (("nav",nav),("trades",trades)):
            with (args.output / f"{name}-{suffix}.csv").open("w",newline="") as f:
                w = csv.DictWriter(f,fieldnames=list(records[0]))
                w.writeheader()
                w.writerows(records)
        summary[name] = {"full":metrics(nav,config["initial_cash"]),"trade_records":len(trades),"round_trips":sum(t["side"]=="SELL" for t in trades),"terminal_position":nav[-1]["quantity"]}
        initial = config["initial_cash"]
        for year in ("2023","2024"):
            sample = [r for r in nav if r["date"].startswith(year)]
            summary[name][year] = metrics(sample,initial)
            initial = sample[-1]["equity"]
    write_json(args.output / "summary.json",summary)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
