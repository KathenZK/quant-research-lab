"""Independent contract checks for the fixed Top10 mechanism research round."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/mechanism-round-20260910"
PLAN = FAMILY / "specs/binance-1d-mcsm-mechanism-round-20260910.md"
PLAN_SHA = "9df5e3fcf02c88e68d00467a04a4e9fd2f20eb33001cf07effb589d5bd7f5956"
DAY = pd.Timedelta(days=1)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def independent_targets(daily, holdings):
    """Literal day-by-day contract, with no import of candidate signal code."""
    if daily.duplicated(["symbol", "ts"]).any():
        raise ValueError("duplicate daily evidence")
    records = {}
    for row in daily.itertuples(index=False):
        key = (row.symbol, int(pd.Timestamp(row.ts).value // DAY.value))
        records[key] = (float(row.close), bool(row.eligible), row.research_segment_id)
    cached = {}

    def window(symbol, day, count):
        values = [records.get((symbol, d)) for d in range(day - count + 1, day + 1)]
        if any(v is None or not v[1] or pd.isna(v[2]) or not np.isfinite(v[0]) or v[0] <= 0 for v in values):
            return None
        if len({v[2] for v in values}) != 1:
            return None
        return [v[0] for v in values]

    def features(symbol, day):
        key = (symbol, day)
        if key not in cached:
            short = window(symbol, day, 8)
            long = window(symbol, day, 21)
            cached[key] = (
                None if short is None else short[-1] / short[0] - 1,
                None if long is None else long[-1] < min(long[:-1]),
            )
        return cached[key]

    targets = []
    for month, basket in holdings.groupby("month", sort=True):
        symbols = sorted(basket.symbol)
        if len(symbols) != 10 or len(set(symbols)) != 10:
            raise ValueError("exact original ten symbols required")
        for row in basket.itertuples(index=False):
            streak = 0
            for date in pd.date_range(pd.Timestamp(row.entry_ts).floor("D"), pd.Timestamp(row.exit_ts).floor("D"), freq="D"):
                close_time = date + DAY
                execution_time = close_time + pd.Timedelta(minutes=15)
                if execution_time >= pd.Timestamp(row.exit_ts):
                    break
                day = int(date.value // DAY.value)
                ret, breakdown = features(row.symbol, day)
                peers = [features(symbol, day)[0] for symbol in symbols if symbol != row.symbol]
                known = ret is not None and breakdown is not None and all(v is not None for v in peers)
                weak = known and breakdown and ret < float(np.median(peers))
                streak = streak + 1 if weak else 0
                if streak == 2:
                    targets.append({"month": pd.Timestamp(month), "symbol": row.symbol,
                                    "signal_close": close_time, "exit_ts": execution_time})
                    break
    return pd.DataFrame(targets, columns=["month", "symbol", "signal_close", "exit_ts"])


def main():
    if sha(PLAN) != PLAN_SHA:
        raise ValueError("pre-result contract changed")
    from verify_mcsm_baseline_20260908 import load_verified_returned_daily

    parent = FAMILY / "artifacts/baseline-estimate-20260909/accounts/started.json"
    started = json.loads(parent.read_text())
    holdings_path = Path(started["paths"]["holdings"])
    if sha(holdings_path) != started["sha256"]["holdings"]:
        raise ValueError("original holdings changed")
    holdings = pd.read_parquet(holdings_path)
    targets = independent_targets(load_verified_returned_daily(), holdings)
    output = OUT / "independent-audit"
    output.mkdir(parents=True, exist_ok=False)
    targets.to_parquet(output / "independent-exit-targets.parquet", index=False)
    result = {"status": "INDEPENDENT_SIGNAL_RECONSTRUCTION_NOT_ACCOUNT_APPROVAL",
              "contract_sha256": PLAN_SHA, "script_sha256": sha(Path(__file__)),
              "original_holdings_sha256": sha(holdings_path), "exit_targets": len(targets),
              "targets_sha256": sha(output / "independent-exit-targets.parquet")}
    with (output / "signal-summary.json").open("x") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
