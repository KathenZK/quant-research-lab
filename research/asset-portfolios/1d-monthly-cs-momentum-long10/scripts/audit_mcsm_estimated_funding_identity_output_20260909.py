"""独立复核修正版观察资金费输入；不计算收益、不认证未知日历。"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-long10/artifacts/baseline-estimate-20260909"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = RUN / "funding-identity-corrected"
    dest = out / "independent-output-audit.json"
    assert not dest.exists()
    summary = json.loads((out / "summary.json").read_text())
    plan_path = ROOT / summary["plan_path"]
    plan = json.loads(plan_path.read_text())
    assert sha(plan_path) == summary["plan_sha256"]
    holdings_path = ROOT / plan["holdings_path"]
    assert sha(holdings_path) == plan["holdings_sha256"]
    holdings = pd.read_parquet(holdings_path)
    events_path = out / "estimated-funding-events.parquet"
    assert sha(events_path) == summary["events_sha256"]
    events = pd.read_parquet(events_path)
    observed_path = out / "observed-held-events-v2.parquet"
    assert sha(observed_path) == plan["observed_event_projection_sha256"]
    observed = pd.read_parquet(observed_path)
    assert len(events) == len(observed)
    assert events.event_id.is_unique
    assert not events.duplicated(["symbol", "ts", "rate_type"]).any()
    assert set(events.event_id) == set(observed.event_id)
    assert events.rate_type.isin(["Regular", "Special"]).all()
    assert np.isfinite(events[["funding_rate", "mark_low", "mark_center", "mark_high"]]).all().all()
    assert events[["mark_low", "mark_center", "mark_high"]].gt(0).all().all()
    assert events.mark_low.le(events.mark_center).all() and events.mark_center.le(events.mark_high).all()
    assert ((events.ts > events.holding_start) & (events.ts <= events.holding_end)).all()
    assert pd.to_datetime(events.minute_ms, unit="ms", utc=True).eq(events.ts.dt.floor("min")).all()
    native = events.mark_quality.eq("NATIVE_MARK_SOURCE_VERIFIED_CALENDAR_NOT_PROVEN")
    assert events.loc[native, "mark_low"].equals(events.loc[native, "mark_center"])
    assert events.loc[native, "mark_high"].equals(events.loc[native, "mark_center"])
    for key in ["ts", "frozen_ts", "funding_rate", "source_rate_type", "frozen_rate_type", "rate_type", "holding_start", "holding_end"]:
        actual = events.set_index("event_id")[key].sort_index()
        frozen = observed.set_index("event_id")[key].sort_index()
        pd.testing.assert_series_equal(actual, frozen, check_names=False)
    sources = events[["mark_raw_path", "mark_raw_sha256"]].drop_duplicates()
    assert not sources.mark_raw_path.duplicated().any()
    verified_bytes = 0
    for row in sources.itertuples(index=False):
        source_path = ROOT / row.mark_raw_path
        raw = source_path.read_bytes()
        if source_path.suffix == ".gz":
            raw = gzip.decompress(raw)
        assert hashlib.sha256(raw).hexdigest() == row.mark_raw_sha256
        verified_bytes += len(raw)
    old = pd.read_parquet(RUN / "funding/estimated-funding-events.parquet")
    old_holdings = pd.read_parquet(RUN / "inputs/holdings.parquet")
    common = set(zip(holdings.symbol, holdings.entry_ts, holdings.exit_ts)) & set(zip(old_holdings.symbol, old_holdings.entry_ts, old_holdings.exit_ts))
    assert len(common) == 758
    def common_subset(frame):
        include = [(r.symbol, r.holding_start, r.holding_end) in common for r in frame.itertuples()]
        cols = ["ts", "symbol", "funding_rate", "rate_type", "source_rate_type", "frozen_rate_type", "mark_center", "mark_low", "mark_high"]
        return frame.loc[include].set_index("event_id")[cols].sort_index()
    pd.testing.assert_frame_equal(common_subset(events), common_subset(old), check_exact=True)
    old_indexed, new_indexed = old.set_index("event_id"), events.set_index("event_id")
    common_ids = common_subset(events).index
    source_changed = common_ids[new_indexed.loc[common_ids, "mark_raw_sha256"].ne(old_indexed.loc[common_ids, "mark_raw_sha256"])]
    # Adding May LAYER expands its existing May1 00:00 source query from a
    # single API minute to a complete archive month. Both source bytes are
    # retained, and all cash-relevant numbers must still match exactly above.
    assert len(source_changed) == 1
    changed = new_indexed.loc[source_changed[0]]
    prior = old_indexed.loc[source_changed[0]]
    assert changed.symbol == "LAYER/USDT:USDT" and changed.ts == pd.Timestamp("2025-05-01T00:00:00Z")
    assert prior.mark_source == "FAPI_MARK_1M_WINDOW" and changed.mark_source == "VISION_MARK_1M_MONTH"
    source_change_evidence = [{"event_id": source_changed[0], "symbol": changed.symbol, "ts": str(changed.ts),
                               "old_raw_sha256": prior.mark_raw_sha256, "new_raw_sha256": changed.mark_raw_sha256,
                               "reason": "New May LAYER holding expands source demand to monthly ZIP; old Apr exit-minute values exactly identical"}]
    old_ids, new_ids = set(old.event_id), set(events.event_id)
    removed, added = old.loc[~old.event_id.isin(new_ids)], events.loc[~events.event_id.isin(old_ids)]
    def difference_counts(frame):
        return [{"symbol": symbol, "holding_start": str(start), "events": len(group)} for (symbol, start), group in frame.groupby(["symbol", "holding_start"])]
    result = {
        "status": "PASS_EXPLORATORY_FUNDING_INPUT_INTEGRITY_NOT_NET_VALIDATION",
        "events": len(events), "holdings_sha256": sha(holdings_path), "events_sha256": sha(events_path),
        "plan_sha256": sha(plan_path), "summary_sha256": sha(out / "summary.json"),
        "observed_ids_no_drop_or_duplicate": True, "economic_event_keys_unique": True,
        "original_types_timestamps_rates_preserved": True, "all_events_inside_corrected_holding_windows": True,
        "minute_keys_exact_utc_roundtrip": True, "all_mark_scenarios_finite_positive_ordered": True,
        "native_mark_bounds_equal": True, "unique_mark_source_raws_rehashed": len(sources),
        "mark_source_bytes_rehashed": verified_bytes,
        "unchanged_holding_windows": len(common), "unchanged_events_identical": len(common_subset(events)),
        "unchanged_values_but_source_container_changes": source_change_evidence,
        "removed_event_count": len(removed), "added_event_count": len(added),
        "removed_windows": difference_counts(removed), "added_windows": difference_counts(added),
        "full_calendar_certified": False, "native_settlement_mark_certified_for_all_events": False,
        "pit_or_live_ready": False, "source_script_sha256": sha(Path(__file__)),
    }
    with dest.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
