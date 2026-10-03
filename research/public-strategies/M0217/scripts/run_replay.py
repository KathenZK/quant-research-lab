"""M0217 explicit OHLC fill hypothesis; offline research, no exchange access."""
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


def run(rows, config, fee_bps=8, benchmark=False):
    fee = fee_bps / 10000
    slip = config["slippage_bps"] / 10000
    cash = float(config["initial_cash"])
    peak = cash
    quantity = 0.0
    nav, trades = [], []
    for i, row in enumerate(rows):
        if row["date"] < config["evaluation_start"]:
            continue
        previous = rows[i - 1]
        level = previous["close"] + config["range_multiplier"] * (previous["high"] - previous["low"])
        triggered = (not nav) if benchmark else row["high"] >= level
        if triggered:
            entry = (row["open"] if benchmark else max(row["open"], level)) * (1 + slip)
            notional = cash * config["buy_fraction_cash"]
            quantity = notional / entry
            charge = notional * fee
            cash -= notional + charge
            trades.append(dict(date=row["date"], phase="OPEN" if benchmark else "INTRADAY_UNKNOWN", side="BUY", signal_date=previous["date"], quantity=quantity, price=entry, fee=charge, cash_after=cash, position_after=quantity))
            if not benchmark:
                exit_price = row["close"] * (1 - slip)
                proceeds = quantity * exit_price
                charge = proceeds * fee
                cash += proceeds - charge
                trades.append(dict(date=row["date"], phase="CLOSE", side="SELL", signal_date=previous["date"], quantity=quantity, price=exit_price, fee=charge, cash_after=cash, position_after=0.0))
                quantity = 0.0
        equity = cash + quantity * row["close"]
        peak = max(peak, equity)
        if cash < -1e-8 or not math.isfinite(equity):
            raise ValueError("Invalid account")
        nav.append(dict(date=row["date"], equity=equity, cash=cash, quantity=quantity, drawdown=equity / peak - 1, triggered=triggered))
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    config = json.loads((FAMILY / "specs/M0217-first-replay.json").read_text())
    rows = load(args.input)
    summary = {}
    for name, fee, benchmark in (("base", 8, False), ("fee0", 0, False), ("fee20", 20, False), ("buy_hold", 8, True)):
        nav, trades = run(rows, config, fee, benchmark)
        for suffix, records in (("nav", nav), ("trades", trades)):
            with (args.output / f"{name}-{suffix}.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(records[0]))
                w.writeheader()
                w.writerows(records)
        summary[name] = {"full": metrics(nav, config["initial_cash"]), "trade_records": len(trades), "round_trips": len(trades) // 2 if not benchmark else 0}
        previous = config["initial_cash"]
        for year in ("2023", "2024"):
            sample = [r for r in nav if r["date"].startswith(year)]
            summary[name][year] = metrics(sample, previous)
            previous = sample[-1]["equity"]
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
