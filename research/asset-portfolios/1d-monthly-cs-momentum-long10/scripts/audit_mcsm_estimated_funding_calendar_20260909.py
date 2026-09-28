"""估算账的已证明片段期望事件对照；不把未知日历缺口当零费用。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_lab.data.funding_v2 import load_funding_v2

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-long10/artifacts/baseline-estimate-20260909/funding"
PIN = "398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out:
        OUT = args.out.resolve()
        assert OUT.is_relative_to(ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-long10/artifacts/baseline-estimate-20260909")
    target = OUT / "calendar-observed-audit.json"
    if target.exists():
        raise FileExistsError(target)
    plan = json.loads((OUT / "plan-v2.json").read_text())
    data = load_funding_v2(ROOT / "data/derived/datasets/binance_perp_funding_v3_inputs_v2", expected_manifest_sha256=PIN)
    events_path = OUT / "observed-held-events-v2.parquet"
    assert sha(events_path) == plan["observed_event_projection_sha256"]
    events = pd.read_parquet(events_path)
    holdings = pd.read_parquet(ROOT / plan["holdings_path"])
    assert sha(ROOT / plan["holdings_path"]) == plan["holdings_sha256"]
    expected_groups = {s: g for s, g in data.expected.groupby("symbol", sort=False)}
    event_groups = {i: g for i, g in events.groupby("holding_window_id", sort=False)}
    rows, interval_flags = [], []
    for i, holding in holdings.iterrows():
        expected = expected_groups.get(holding.symbol, data.expected.iloc[:0])
        expected = expected[(expected.ts > holding.entry_ts) & (expected.ts <= holding.exit_ts)]
        actual = event_groups.get(i, events.iloc[:0]).sort_values("frozen_ts")
        expected_ids, actual_ids = set(expected.event_id), set(actual.event_id)
        missing = sorted(expected_ids - actual_ids)
        rows.append({"holding_window_id": int(i), "symbol": holding.symbol, "start": holding.entry_ts, "end": holding.exit_ts,
                     "observed_events": len(actual), "partial_frozen_expected_events": len(expected),
                     "missing_known_expected_event_ids": missing,
                     "events_outside_partial_expected_ids": len(actual_ids - expected_ids),
                     "full_strategy_calendar_certified": False,
                     "empty_observed_window": actual.empty})
        if len(actual) > 1:
            interval = pd.to_numeric(actual.archive_interval_hours, errors="coerce")
            proven_source = actual.archive_evidence_sha256.fillna("").str.len().eq(64)
            same_interval = interval.eq(interval.shift()) & interval.notna() & proven_source & proven_source.shift(fill_value=False)
            gap = actual.frozen_ts.diff().dt.total_seconds()
            discrepancy = same_interval & gap.sub(interval * 3600).abs().gt(2)
            for index in actual.index[discrepancy]:
                position = actual.index.get_loc(index)
                row, previous = actual.loc[index], actual.iloc[position - 1]
                interval_flags.append({"symbol": holding.symbol, "previous_ts": previous.frozen_ts,
                                       "current_ts": row.frozen_ts, "declared_interval_hours": float(interval.loc[index]),
                                       "observed_gap_seconds": float(gap.loc[index]),
                                       "label": "DECLARED_INTERVAL_DISCREPANCY_NOT_ZERO_FILLED_NOT_INDEPENDENT_FULL_CALENDAR"})
    pd.DataFrame(rows).to_csv(OUT / "partial-expected-event-comparison.csv", index=False)
    pd.DataFrame(interval_flags, columns=["symbol", "previous_ts", "current_ts", "declared_interval_hours", "observed_gap_seconds", "label"]).to_csv(OUT / "declared-interval-discrepancies.csv", index=False)
    summary = {"status": "OBSERVED_FUNDING_ESTIMATE_PARTIAL_CALENDAR_AUDIT_ONLY", "plan_path": "plan-v2.json",
               "plan_sha256": sha(OUT / "plan-v2.json"), "funding_manifest_sha256": PIN,
               "holdings_windows": len(rows), "observed_events": len(events),
               "frozen_partial_expected_events_in_holdings": sum(r["partial_frozen_expected_events"] for r in rows),
               "known_missing_expected_events_within_frozen_proven_segments": sum(len(r["missing_known_expected_event_ids"]) for r in rows),
               "missing_expected_event_ids": [e for r in rows for e in r["missing_known_expected_event_ids"]],
               "observed_events_outside_partial_proven_calendar": sum(r["events_outside_partial_expected_ids"] for r in rows),
               "empty_holding_windows": [r for r in rows if r["empty_observed_window"]],
               "same_declared_interval_discrepancies": len(interval_flags),
               "full_calendar_certified": False, "unknown_calendar_as_zero_fee": False,
               "interpretation": "Zero missing expected events is confined to the supplied partial proven segments. Events outside those segments remain unverified coverage, not zero missing fees.",
               "source_script_sha256": sha(Path(__file__))}
    with target.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False, default=str)
        stream.write("\n")
    print(json.dumps(summary, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
