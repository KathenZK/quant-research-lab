"""本轮冻结名单的有限源差异/形成期段边界复核；不改名单、不算收益。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

LAB = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))
sys.path.insert(0, str(FAMILY / "scripts"))

import audit_binance_1d_mcsm_funding_source_20260908 as old_audit  # noqa: E402
from strategy_lab.data.catalog import DatasetScope, load_trusted_research_dataset, read_verified_ohlcv, require_passing_trusted  # noqa: E402
from strategy_lab.data.lake import DataLakeLayout  # noqa: E402
from strategy_lab.data.research_bundle import read_bundle_contract, validate_price_frame, verify_bundle_files  # noqa: E402

INPUT = FAMILY / "artifacts/baseline-estimate-20260909/inputs"
OUT = INPUT / "selection-appendix"
HOLDINGS_SHA = "a399e23d2750dd2b9702555c84e27ebfc8deded6ba409747efacbe46d60de046"
PIN = {"bundle_path": "research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json",
       "bundle_id": "binance.v3.research_inputs.v2", "bundle_sha256": "d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008"}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        handle.write("\n")


def legacy_difference(holdings: pd.DataFrame) -> dict:
    frozen = json.loads((FAMILY / "artifacts/funding-source-20260908/summary.json").read_text())
    changed = [row["path"] for row in frozen["legacy_inputs"] if sha(LAB / row["path"]) != row["sha256"]]
    if changed:
        save(OUT / "legacy-reproduction-rejected.json", {"status": "LEGACY_FROZEN_SOURCE_HASH_CHANGED", "changed": changed})
        raise ValueError("Frozen legacy source changed; no reproduction allowed")
    ohlcv, _, prior_h, _, manifest = old_audit.load_legacy_reproduction()
    expected = {r["path"]: r["sha256"] for r in frozen["legacy_inputs"]}
    if any(row["path"] not in expected or row["sha256"] != expected[row["path"]] for row in manifest):
        raise ValueError("Legacy loader manifest differs from frozen source audit")
    save(OUT / "legacy-source-receipt.json", {
        "status": "LEGACY_FROZEN_INPUT_REPRODUCTION_ONLY", "verified_files": len(manifest), "manifest": manifest,
        "legacy_audit_sha256": sha(FAMILY / "artifacts/funding-source-20260908/summary.json"),
        "cache_rebuild_called": False, "current_selection_changed": False})
    legacy = old_audit.legacy
    old_close, old_quote, old_bars = (legacy.pivot(ohlcv, column) for column in ("close", "quote_volume", "bars_15m"))
    old_open = legacy.pivot(ohlcv, "open")
    full = pd.date_range(old_close.index.min(), old_close.index.max(), freq="D")
    old_close, old_quote, old_bars, old_open = [x.reindex(full) for x in (old_close, old_quote, old_bars, old_open)]
    old_adv = old_quote.rolling(30, min_periods=30).mean()
    new = pd.read_parquet(INPUT / "daily-original-buckets.parquet")
    new.ts = new.ts.dt.tz_localize(None)
    new_close, new_quote, new_bars = (new.pivot(index="ts", columns="symbol", values=column) for column in ("close", "quote_volume", "bars_15m"))
    new_adv = new_quote.reindex(full).rolling(30, min_periods=30).mean()
    detail, day_diffs = [], []
    for month in pd.date_range("2022-03-01", "2022-05-01", freq="MS"):
        old_names = set(prior_h.loc[prior_h.rebalance.eq(month)].sym_key)
        current = holdings.loc[holdings.month.eq(month.tz_localize("UTC"))]
        new_names = {symbol.split("/")[0] for symbol in current.symbol}
        names = sorted(old_names | new_names)
        end, begin = month - pd.Timedelta(days=1), month - pd.offsets.MonthBegin(1) - pd.Timedelta(days=1)
        form_start = month - pd.offsets.MonthBegin(1)
        adv_start = end - pd.Timedelta(days=29)
        for base in names:
            symbol = base + "/USDT:USDT"
            old_key = symbol if symbol in old_close.columns else base
            def old_value(frame, day):
                return float(frame.loc[day, old_key]) if old_key in frame.columns and day in frame.index else np.nan
            def new_value(frame, day):
                return float(frame.loc[day, symbol]) if symbol in frame.columns and day in frame.index else np.nan
            ob, oe = old_value(old_close, begin), old_value(old_close, end)
            nb, ne = new_value(new_close, begin), new_value(new_close, end)
            oa, na = old_value(old_adv, end), new_value(new_adv, end)
            ocount = int(old_quote.loc[adv_start:end, old_key].notna().sum()) if old_key in old_quote else 0
            ncount = int(new_quote.loc[adv_start:end, symbol].notna().sum()) if symbol in new_quote else 0
            ocov = float(old_bars.loc[form_start:end, old_key].ge(1).sum() / end.day) if old_key in old_bars else 0.
            ncov = float(new_bars.loc[form_start:end, symbol].ge(1).sum() / end.day) if symbol in new_bars else 0.
            obe, oee = old_value(old_bars, begin), old_value(old_bars, end)
            nbe, nee = new_value(new_bars, begin), new_value(new_bars, end)
            old_reasons = []
            if not np.isfinite(ob) or not np.isfinite(oe) or obe < 48 or oee < 48:
                old_reasons.append("ENDPOINT_MISSING_OR_LT48")
            if not np.isfinite(oa):
                old_reasons.append("ADV30_UNDEFINED_MISSING_DAY_BUCKET")
            elif oa < 10_000_000:
                old_reasons.append("ADV30_BELOW_10M")
            if ocov < .8:
                old_reasons.append("FORMATION_COVERAGE_BELOW_80PCT")
            if not np.isfinite(old_value(old_open, month)):
                old_reasons.append("MONTHSTART_OPEN_MISSING")
            record = {"month": month, "symbol": symbol, "old_selected": base in old_names,
                "new_selected": base in new_names, "old_failure_reasons": ";".join(old_reasons),
                "old_begin_close": ob, "new_begin_close": nb, "old_end_close": oe, "new_end_close": ne,
                "old_formation_return": oe / ob - 1 if np.isfinite(ob) and ob > 0 else np.nan,
                "new_formation_return": ne / nb - 1 if np.isfinite(nb) and nb > 0 else np.nan,
                "old_adv30": oa, "new_adv30": na, "old_adv_day_count": ocount, "new_adv_day_count": ncount,
                "old_coverage": ocov, "new_coverage": ncov, "old_begin_bars": obe, "new_begin_bars": nbe,
                "old_end_bars": oee, "new_end_bars": nee}
            detail.append(record)
            for day in pd.date_range(min(begin, adv_start), end, freq="D"):
                for field, old_frame, new_frame in (("close", old_close, new_close), ("quote_volume", old_quote, new_quote), ("bars_15m", old_bars, new_bars)):
                    ov, nv = old_value(old_frame, day), new_value(new_frame, day)
                    equal = (pd.isna(ov) and pd.isna(nv)) or (np.isfinite(ov) and np.isfinite(nv) and abs(ov-nv) <= max(1e-10, abs(nv)*1e-12))
                    if not equal:
                        day_diffs.append({"month": month, "symbol": symbol, "day": day, "field": field, "old": ov, "new": nv,
                                          "difference_class": "MISSING_OLD_PRESENT_V3" if pd.isna(ov) and pd.notna(nv) else "VALUE_CHANGE"})
    df = pd.DataFrame(detail)
    df.to_csv(OUT / "legacy-v3-selection-metrics.csv", index=False)
    pd.DataFrame(day_diffs).to_csv(OUT / "legacy-v3-day-field-differences.csv", index=False)
    added = df.loc[~df.old_selected & df.new_selected]
    result = {"status": "LEGACY_FROZEN_INPUTS_MATCH_SOURCE_PINS", "compared_months": 3,
              "compared_asset_months": len(df), "newly_selected_asset_months": len(added),
              "newly_selected_details": json.loads(added.to_json(orient="records", date_format="iso")),
              "day_field_differences": len(day_diffs), "no_returns_recalculated": True}
    save(OUT / "legacy-v3-summary.json", result)
    print("LEGACY_DIFFERENCE_READY " + json.dumps(result, ensure_ascii=False), flush=True)
    return result


def formation_segments(holdings: pd.DataFrame) -> dict:
    bundle, _ = read_bundle_contract(LAB, pin=PIN)
    requests = []
    for month, group in holdings.groupby("month", sort=True):
        start = group.formation_start_day.iloc[0] + pd.Timedelta(hours=23, minutes=45)
        end = month
        requests.append({"schema_version": 1, **PIN, "mode": "price_diagnostic", "timeframe": "15m",
                         "symbols": sorted(group.symbol), "start": start.isoformat(), "end": end.isoformat(),
                         "gap_policy": "contiguous_segments", "asset_policy": "observed_mixed_diagnostic",
                         "backward_bars": 1, "forward_bars": 0})
    save(OUT / "formation-requests-frozen.json", {"holdings_sha256": HOLDINGS_SHA, "requests": requests,
         "scope": "760 already-selected formation intervals; no selection changes or future outcome comparisons"})
    verified = verify_bundle_files(bundle, data_root=LAB / "data")
    lake = LAB / "data"
    layout = DataLakeLayout(root_dir=lake, raw_dir=lake / "raw", normalized_dir=lake / "normalized",
                           features_dir=lake / "features", cache_dir=lake / "cache", derived_dir=lake / "derived")
    audit_start = pd.Timestamp(requests[0]["start"])
    audit_end = pd.Timestamp(requests[-1]["end"])
    loaded = require_passing_trusted(load_trusted_research_dataset(
        "binance.perp.ohlcv.15m.history.v3", layout=layout, requested_scope=DatasetScope.FULL_MARKET,
        start=audit_start, end=audit_end, gap_policy="contiguous_segments", max_materialize_rows=0))
    save(OUT / "formation-catalog-receipt.json", {"status": "EXPLORATORY_SCOPED_EQUIVALENT_AUDIT",
         "audit": loaded.audit, "coverage": loaded.coverage, "verified_components": verified,
         "start": audit_start, "end": audit_end, "startup_api_pass_claimed": False,
         "net_inputs_verified": False, "frozen_requests_sha256": sha(OUT / "formation-requests-frozen.json")})
    stats, anomalous, missing_rows, receipt_rows = [], [], [], []
    for i, req in enumerate(requests):
        a, b = pd.Timestamp(req["start"]), pd.Timestamp(req["end"])
        if not audit_start <= a < b <= audit_end:
            raise ValueError("Formation subrequest exceeded same audited extent")
        raw = read_verified_ohlcv(loaded, start=a, end=b)
        raw = raw.loc[raw.symbol.isin(req["symbols"])].copy()
        for symbol in req["symbols"]:
            part = raw.loc[raw.symbol.eq(symbol)]
            frame, report = validate_price_frame(part, req, symbol, [])
            expected = pd.date_range(a, b, freq="15min", inclusive="left")
            missing = expected.difference(pd.DatetimeIndex(frame.ts))
            invalid = frame.loc[~frame.eligible]
            record = {"month": b, "symbol": symbol, "formation_first_15m_open": a,
                      "formation_end_exclusive": b, "expected_bars": len(expected), "observed_bars": len(frame),
                      "missing_bars": len(missing), "ineligible_bars": len(invalid),
                      "zero_volume_bars": int(frame.volume.le(0).sum()),
                      "zero_quote_volume_bars": int(frame.quote_volume.le(0).sum()),
                      "zero_tradecount_bars": int(frame.trade_count.le(0).sum()),
                      "eligible_segments": int(frame.research_segment_id.nunique()),
                      "one_complete_eligible_segment": bool(len(missing) == 0 and frame.eligible.all() and frame.research_segment_id.nunique() == 1),
                      "first_endpoint_valid": bool(frame.ts.iloc[0] == a and frame.eligible.iloc[0]),
                      "last_endpoint_valid": bool(frame.ts.iloc[-1] == b-pd.Timedelta(minutes=15) and frame.eligible.iloc[-1]),
                      "returned_frame_projection_sha256": hashlib.sha256(pd.util.hash_pandas_object(frame[["ts", "symbol", "open", "close", "volume", "quote_volume", "trade_count", "eligible", "research_segment_id"]], index=False).values.tobytes()).hexdigest()}
            stats.append(record)
            for timestamp in missing:
                missing_rows.append({"month": b, "symbol": symbol, "ts": timestamp})
            if not invalid.empty:
                evidence = invalid[["ts", "symbol", "open", "high", "low", "close", "volume", "quote_volume", "trade_count", "is_closed", "eligible", "research_segment_id"]].copy()
                evidence["month"] = b
                anomalous.append(evidence)
            receipt_rows.append({"month": b, "symbol": symbol, "request": req, "validation": report})
        print(f"FORMATION_SEGMENTS {i+1}/76 {b:%Y-%m}", flush=True)
    table = pd.DataFrame(stats)
    table.to_csv(OUT / "selected-formation-segments.csv", index=False)
    pd.DataFrame(missing_rows).to_csv(OUT / "selected-formation-missing-bars.csv", index=False)
    if anomalous:
        pd.concat(anomalous, ignore_index=True).to_parquet(OUT / "selected-formation-ineligible-bars.parquet", index=False, compression="zstd")
    save(OUT / "formation-subwindow-receipts.json", receipt_rows)
    bad = table.loc[~table.one_complete_eligible_segment]
    result = {"status": "SELECTED_FORMATION_SEGMENT_FACTS_ONLY", "selected_intervals": len(table),
              "one_complete_eligible_segment_intervals": int(table.one_complete_eligible_segment.sum()),
              "noncontinuous_or_ineligible_intervals": len(bad),
              "total_missing_15m_bars": int(table.missing_bars.sum()),
              "total_ineligible_15m_bars": int(table.ineligible_bars.sum()),
              "affected_intervals": json.loads(bad.to_json(orient="records", date_format="iso")),
              "selection_changed": False, "no_returns_recalculated": True,
              "compatibility": "Original >=48 endpoints, >=80% daily-bucket coverage, and ADV30 do not require all 15m bars active. A strict one-segment requirement is a stronger condition and has not been silently imposed."}
    save(OUT / "formation-segment-summary.json", result)
    return result


def main() -> None:
    if OUT.exists():
        raise FileExistsError("Refusing to overwrite retained appendix")
    if sha(INPUT / "holdings.parquet") != HOLDINGS_SHA:
        raise ValueError("Frozen current holdings changed")
    holdings = pd.read_parquet(INPUT / "holdings.parquet")
    source = sha(Path(__file__))
    started = time.monotonic()
    save(OUT / "started.json", {"source_sha256": source, "holdings_sha256": HOLDINGS_SHA,
                                "purpose": "selected formation segment facts and legacy/V3 input differences only"})
    legacy = legacy_difference(holdings)
    segments = formation_segments(holdings)
    if sha(INPUT / "holdings.parquet") != HOLDINGS_SHA or sha(Path(__file__)) != source:
        raise ValueError("Frozen holdings or appendix source changed during audit")
    save(OUT / "summary.json", {"status": "BOUNDED_SELECTION_APPENDIX_COMPLETE",
         "legacy_source_status": legacy["status"], "formation_segment_summary": segments,
         "holdings_unchanged": True, "source_sha256": source, "holdings_sha256": HOLDINGS_SHA,
         "elapsed_seconds": time.monotonic()-started, "new_returns_computed": False,
         "files": {p.name: sha(p) for p in OUT.iterdir() if p.is_file()}})
    print("APPENDIX_COMPLETE " + json.dumps(segments, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
