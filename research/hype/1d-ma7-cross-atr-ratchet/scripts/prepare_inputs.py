#!/usr/bin/env python3
"""Freeze verified HYPE price inputs and separately audit observed funding.

No strategy, returns, parameters, or global data-lake writes occur here.
Published input frames are consumed directly from the startup API.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_lab.data.funding_v2 import load_funding_v2
from strategy_lab.data.manifest import sha256_file
from strategy_lab.data.research_bundle import read_json, require_research_startup

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "research/hype/1d-ma7-cross-atr-ratchet"
SYMBOL = "HYPE/USDT:USDT"
START = "2025-05-31T00:00:00Z"
END = "2026-09-05T00:00:00Z"


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")


def load_prices(request: dict):
    """Only the frames returned by this full request gate are consumed."""
    return require_research_startup(request, project_root=ROOT, data_root=ROOT / "data")


def attempt_net_startup(request: dict):
    """The full-history net request must reject absent reviewed identity evidence."""
    return require_research_startup(request, project_root=ROOT, data_root=ROOT / "data")


def load_observed_funding(bundle: dict):
    """Verify published event content without claiming full-window coverage."""
    component = bundle["components"]["funding"]
    return load_funding_v2(
        ROOT / "data" / component["root"],
        expected_manifest_sha256=component["manifest_sha256"],
    )


def audit_price(frame: pd.DataFrame, tf: str) -> dict:
    step = pd.Timedelta(hours=1) if tf == "1h" else pd.Timedelta(days=1)
    grid = pd.date_range(START, END, freq=step, inclusive="left")
    values = frame[["open", "high", "low", "close", "volume", "quote_volume", "trade_count", "vwap"]]
    invalid_ohlc = (frame.high.lt(frame[["open", "close", "low"]].max(axis=1))
                    | frame.low.gt(frame[["open", "close", "high"]].min(axis=1)))
    audit = {
        "rows": len(frame), "start_utc": frame.ts.min().isoformat(),
        "last_open_utc": frame.ts.max().isoformat(),
        "last_close_utc": (frame.ts.max() + step).isoformat(),
        "expected_rows": len(grid), "missing_grid_rows": len(grid.difference(frame.ts)),
        "unexpected_grid_rows": len(pd.DatetimeIndex(frame.ts).difference(grid)),
        "duplicate_timestamps": int(frame.ts.duplicated().sum()),
        "critical_nonfinite_values": int((~np.isfinite(values.to_numpy(dtype=float))).sum()),
        "invalid_ohlc_rows": int(invalid_ohlc.sum()),
        "nonpositive_price_rows": int(frame[["open", "high", "low", "close"]].le(0).any(axis=1).sum()),
        "zero_volume_rows": int(frame.volume.le(0).sum()),
        "unclosed_rows": int((~frame.is_closed).sum()),
        "ineligible_rows": int((~frame.eligible).sum()),
        "research_segments": int(frame.research_segment_id.nunique()),
        "valid_feature_windows": int(frame.research_window_valid.sum()),
        "columns": list(frame.columns),
    }
    reject = ["missing_grid_rows", "unexpected_grid_rows", "duplicate_timestamps",
              "critical_nonfinite_values", "invalid_ohlc_rows", "nonpositive_price_rows",
              "zero_volume_rows", "unclosed_rows", "ineligible_rows"]
    if any(audit[k] for k in reject) or audit["research_segments"] != 1:
        raise ValueError(f"price audit failed: {audit}")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=FAMILY / "artifacts/inputs_20260909")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"refusing to replace existing input evidence: {out}")
    out.mkdir(parents=True, exist_ok=True)
    frames = {}
    price_audits = {}
    request_hashes = {}
    for role, tf in (("hourly", "1h"), ("daily", "1d")):
        path = FAMILY / "specs" / f"price_request_{tf}_20260909.json"
        request = read_json(path)
        request_hashes[str(path.relative_to(ROOT))] = sha256_file(path)
        write_json(out / f"price_request_{tf}.json", request)
        print(f"Verifying and loading {tf} request", flush=True)
        inputs = load_prices(request)
        frame = inputs.prices[SYMBOL].copy()
        frame.to_parquet(out / f"{role}.parquet", index=False)
        write_json(out / f"startup_{tf}.json", inputs.report)
        price_audits[role] = audit_price(frame, tf)
        frames[role] = frame
        print(f"{tf} verified: {len(frame)} rows", flush=True)

    hourly = frames["hourly"].set_index("ts")
    daily = frames["daily"].set_index("ts")
    aggregate = hourly.resample("1D").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum", "quote_volume": "sum", "trade_count": "sum",
    })
    differences = {column: float((aggregate[column] - daily[column]).abs().max())
                   for column in aggregate.columns}
    if not aggregate.index.equals(daily.index):
        raise ValueError("hourly/daily UTC index mismatch")
    for column in aggregate.columns:
        if not np.allclose(aggregate[column], daily[column], rtol=1e-12, atol=1e-9):
            raise ValueError(f"hourly/daily aggregation mismatch: {column}")

    net_path = FAMILY / "specs/net_request_full_history_20260909.json"
    net_request = read_json(net_path)
    request_hashes[str(net_path.relative_to(ROOT))] = sha256_file(net_path)
    try:
        attempt_net_startup(net_request)
    except ValueError as exc:
        if str(exc) != "net research requires reviewed identity evidence":
            raise
        net_failure = {"status": "NET_INPUTS_REJECTED", "error_type": type(exc).__name__,
                       "error": str(exc), "request": net_request,
                       "funding_window_verified": False, "identity_verified": False,
                       "strategy_approved": False}
        write_json(out / "startup_net_rejected.json", net_failure)
    else:
        raise AssertionError("unreviewed net request must reject")

    bundle_path = ROOT / net_request["bundle_path"]
    bundle = read_json(bundle_path)
    funding = load_observed_funding(bundle)
    a, b = pd.Timestamp(START), pd.Timestamp(END)
    events = funding.events[funding.events.symbol.eq(SYMBOL)
                            & funding.events.ts.gt(a) & funding.events.ts.le(b)].copy().sort_values("ts")
    segments = funding.segments[funding.segments.symbol.eq(SYMBOL)].copy()
    expected = funding.expected[funding.expected.symbol.eq(SYMBOL)].copy()
    events.to_parquet(out / "funding_observed_unverified.parquet", index=False)
    segments.to_parquet(out / "funding_coverage_segments.parquet", index=False)
    expected.to_parquet(out / "funding_coverage_expected_events.parquet", index=False)
    hit = segments[segments.start.le(a) & segments.end.ge(b)]
    if len(hit) != 0:
        raise AssertionError("coverage assessment changed; re-review before any research")
    mark = pd.to_numeric(events.mark_price, errors="coerce")
    source_summary = []
    for source, subset in events.groupby("source", dropna=False):
        subset_mark = pd.to_numeric(subset.mark_price, errors="coerce")
        source_summary.append({"source": source, "events": len(subset),
                               "missing_or_invalid_mark_price": int((~np.isfinite(subset_mark) | subset_mark.le(0)).sum()),
                               "with_raw_receipt_sha256": int(subset.raw_receipt_sha256.fillna("").str.len().eq(64).sum())})
    funding_audit = {
        "status": "OBSERVED_EVENTS_ONLY_FULL_WINDOW_NOT_VERIFIED",
        "dataset_id": funding.manifest["dataset_id"],
        "manifest_sha256": bundle["components"]["funding"]["manifest_sha256"],
        "parquet_inventory_fingerprint": funding.manifest["parquet_inventory_fingerprint"],
        "published_row_quality": "PASS", "full_window_coverage_segment_matches": len(hit),
        "coverage_failure": "historical funding coverage not proven for this full window",
        "identity_verified": False, "funding_window_verified": False,
        "window_semantics": "(start,end] native UTC milliseconds; no event rounding or zero fill",
        "start_utc": START, "end_utc": END, "observed_events": len(events),
        "first_observed_event_utc": events.ts.min().isoformat(),
        "last_observed_event_utc": events.ts.max().isoformat(),
        "ambiguous_events": int((~events.event_unambiguous).sum()),
        "duplicate_event_ids": int(events.event_id.duplicated().sum()),
        "missing_or_invalid_mark_price": int((~np.isfinite(mark) | mark.le(0)).sum()),
        "mark_price_policy": "Preserve published mark_price unchanged. No OHLCV proxy inserted. API builder reads Binance markPrice; monthly archive supplies no mark_price. Missing original receipt hashes remain missing; all historical mark-price provenance was not independently reverified.",
        "mark_price_builder_reference": "research/platform/data-lake-governance/scripts/build_binance_funding_v2.py",
        "source_summary": source_summary,
        "verified_calendar_segments": json.loads(segments.to_json(orient="records", date_format="iso")),
        "columns": list(events.columns),
        "usage": "May be used only for separately labelled observed-funding sensitivity, never full verified net returns.",
    }
    write_json(out / "funding_audit.json", funding_audit)
    audit = {
        "family_id": "HYPE-1D-MA7-CAR", "family_path": str(FAMILY.relative_to(ROOT)),
        "status": "PRICE_DIAGNOSTIC_INPUTS_VERIFIED_NET_INPUTS_REJECTED",
        "exchange": "binance", "market_type": "perp", "symbol": SYMBOL,
        "bundle_id": net_request["bundle_id"], "bundle_sha256": net_request["bundle_sha256"],
        "range_selection": "Use every complete UTC day in the published HYPE hourly history. Exclude first partial date 2025-05-30 and final partial date 2026-09-05.",
        "start_utc": START, "end_exclusive_utc": END,
        "price_audits": price_audits,
        "hourly_to_daily_max_absolute_difference": differences,
        "aggregation_check": "PASS: OHLC and volume/trade totals agree with separately startup-verified published daily data to rtol 1e-12, atol 1e-9",
        "daily_warmup": "backward_bars=29; first 28 days research_window_valid false",
        "net_blockers": ["No independently reviewed full-history identity evidence in this family", "No single verified funding-calendar segment covers full request"],
        "funding_window_verified": False, "strategy_approved": False,
        "no_performance_computed": True, "request_file_sha256": request_hashes,
        "prepare_script_sha256": sha256_file(Path(__file__)),
    }
    write_json(out / "data_audit.json", audit)
    checksums = {str(p.relative_to(out)): sha256_file(p) for p in sorted(out.iterdir()) if p.is_file()}
    write_json(out / "checksums.json", checksums)
    print(json.dumps({"output": str(out), "price_rows": {k: len(v) for k, v in frames.items()},
                      "funding_observed": len(events), "funding_complete": False}), flush=True)


if __name__ == "__main__":
    main()
