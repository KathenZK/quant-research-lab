"""Reconstruct all joint research windows from retained, hash-checked API frames."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from common import load_engine

FAMILY = Path(__file__).resolve().parents[1]
LAB = Path(__file__).resolve().parents[4]
INPUT = FAMILY / "artifacts/inputs_20260909"
OUTPUT = FAMILY / "artifacts/input_audit_20260909.json"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_inputs():
    checksums = json.loads((INPUT / "checksums.json").read_text())
    for name, digest in checksums.items():
        if sha(INPUT / name) != digest:
            raise ValueError(f"Prepared input changed: {name}")
    plan = json.loads((INPUT / "frozen_plan.json").read_text())
    manifest = json.loads((INPUT / "frames_manifest.json").read_text())
    return plan, manifest, checksums


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    plan, manifest, checksums = load_inputs()
    failure_symbols = set()
    for path in (INPUT / "failures").glob("*.json"):
        failure = json.loads(path.read_text())
        req = json.loads((INPUT / failure["request_path"]).read_text())
        symbol = failure["symbol"]
        if (symbol not in req["symbols"] or failure["error"] != f"{symbol}: no complete eligible feature/label window"
                or failure["data_returned"] is not False or failure["fallback_used"] is not False):
            raise ValueError("Invalid single-symbol unavailable-window evidence")
        failure_symbols.add((req["timeframe"], symbol))
    scope = pd.read_csv(INPUT / "scope.csv")
    segments = pd.read_csv(INPUT / "segments.csv")
    universe = pd.read_csv(INPUT / "universe.csv")
    if len(universe) != 874 or set(universe.loc[universe.included, "symbol"]) != set(plan["symbols"]):
        raise ValueError("Observed universe/COIN denominator mismatch")
    if len(plan["symbols"]) != 652:
        raise ValueError("Frozen explicit coin denominator changed")
    errors, records, feature_issues = [], [], []
    engine = load_engine()
    for window in plan["windows"]:
        window_id = window["window_id"]
        context = json.loads((INPUT / f"startup_context_{window_id}.json").read_text())
        rows = scope.loc[scope.window_id.eq(window_id)]
        if len(rows) != 652 or set(rows.symbol) != set(plan["symbols"]) or rows.symbol.duplicated().any():
            raise ValueError("Scope omitted or duplicated requested coins")
        for row in rows.itertuples(index=False):
            files = manifest[f"{window_id}/{row.symbol}"]
            coin = row.symbol.split("/")[0]
            for tf in ("1d", "1h"):
                if tf not in files:
                    continue
                receipt = files[tf]
                req = json.loads((INPUT / receipt["request_path"]).read_text())
                report = json.loads((INPUT / receipt["startup_report_path"]).read_text())
                if (report["request"] != req or report["status"] != "PRICE_DIAGNOSTIC_BATCH_EVALUATED"
                        or report["symbol_status"][row.symbol]["status"] != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"
                        or row.symbol not in req["symbols"] or req["timeframe"] != tf
                        or req["start"] != window["input_start"] or req["end"] != window["end"]
                        or report["funding_window_verified"] is not False):
                    raise ValueError(f"Invalid startup provenance {row.symbol} {tf}")
                if report["scope_token_sha256"] != context["catalog_receipts"][tf]["scope_token_sha256"]:
                    raise ValueError("Batch frame does not trace to verified exact-scope context")
                if receipt["path"] != f"returned/{window_id}/{tf}/{coin}.parquet":
                    raise ValueError("Unexpected returned frame location")
                if checksums[receipt["path"]] != receipt["sha256"]:
                    raise ValueError("Frame manifest/checksums disagreement")
            if "joint_daily" not in files:
                if row.status != "NO_USABLE_WINDOW":
                    errors.append(f"{row.symbol}: missing joint frame without explicit unavailable status")
                if not any((tf, row.symbol) in failure_symbols and tf not in files for tf in ("1d", "1h")):
                    raise ValueError("Unavailable coin lacks original-validator error evidence")
                records.append({"symbol": row.symbol, "status": row.status, "rows": 0})
                continue
            d = pd.read_parquet(INPUT / files["1d"]["path"])
            h = pd.read_parquet(INPUT / files["1h"]["path"])
            j = pd.read_parquet(INPUT / files["joint_daily"]["path"])
            if not d.ts.equals(j.ts):
                raise ValueError("Projection changed daily timestamps")
            for col in ("open", "high", "low", "close", "volume", "quote_volume", "trade_count", "eligible"):
                if not d[col].equals(j[col]):
                    raise ValueError(f"Projection changed original {col}")
            hourly_dates = h.ts.dt.floor("D")
            groups = h.groupby(hourly_dates, sort=True)
            counts = groups.size().reindex(pd.DatetimeIndex(d.ts)).fillna(0).to_numpy()
            eligible_counts = h.eligible.groupby(hourly_dates).sum().reindex(pd.DatetimeIndex(d.ts)).fillna(0).to_numpy()
            # Startup already verifies each timestamp's one-hour grid and uniqueness.
            expected_valid = d.eligible.to_numpy() & (counts == 24) & (eligible_counts == 24)
            if not np.array_equal(expected_valid, j.joint_eligible.to_numpy()):
                raise ValueError(f"Joint valid-day disagreement {row.symbol}")
            expected_windows, spans, start_index = [], [], None
            for i, valid in enumerate(expected_valid):
                is_next = (i > 0 and expected_valid[i-1]
                           and d.ts.iloc[i] - d.ts.iloc[i-1] == pd.Timedelta(days=1)
                           and d.research_segment_id.iloc[i] == d.research_segment_id.iloc[i-1])
                if valid and not is_next:
                    if start_index is not None:
                        spans.append((start_index, i))
                    start_index = i
                if not valid and start_index is not None:
                    spans.append((start_index, i))
                    start_index = None
                expected_windows.append(bool(valid and i - start_index + 1 >= 29))
            if start_index is not None:
                spans.append((start_index, len(d)))
            if expected_windows != j.research_window_valid.tolist():
                raise ValueError(f"Joint warmup disagreement {row.symbol}")
            expected_segments = []
            for a, b in spans:
                start = d.ts.iloc[a]
                end = d.ts.iloc[b-1] + pd.Timedelta(days=1)
                trade_start = max(pd.Timestamp(window["trade_start"]), start + pd.Timedelta(days=29))
                expected_segments.append({"input_start": start, "trade_start": trade_start, "end": end,
                                          "trading_days": max(0, (end-trade_start).days)})
            expected_segments.sort(key=lambda r: (-r["trading_days"], r["input_start"]))
            reported = segments.loc[segments.window_id.eq(window_id) & segments.symbol.eq(row.symbol)]
            if len(reported) != len(expected_segments):
                raise ValueError(f"Missing joint segments {row.symbol}")
            for expected in expected_segments:
                match = reported.loc[pd.to_datetime(reported.input_start, utc=True).eq(expected["input_start"])]
                if (len(match) != 1 or int(match.trading_days.iloc[0]) != expected["trading_days"]
                        or pd.Timestamp(match.end.iloc[0]) != expected["end"]
                        or pd.Timestamp(match.trade_start.iloc[0]) != expected["trade_start"]):
                    raise ValueError(f"Segment extent mismatch {row.symbol}")
            selected = expected_segments[0] if expected_segments and expected_segments[0]["trading_days"] > 0 else None
            if selected:
                if (int(row.trading_days) != selected["trading_days"]
                        or pd.Timestamp(row.selected_input_start) != selected["input_start"]
                        or pd.Timestamp(row.selected_trade_start) != selected["trade_start"]
                        or pd.Timestamp(row.selected_end) != selected["end"]):
                    raise ValueError(f"Selected segment differs from fixed longest/earliest rule {row.symbol}")
                selected_daily = j[j.joint_segment_id.eq(row.selected_segment_id)].copy().reset_index(drop=True)
                feature = engine.features(selected_daily.rename(columns={"ts": "timestamp"}))
                mask = selected_daily.research_window_valid.to_numpy(bool)
                ready = feature.ready.to_numpy(bool)
                zero_atr = int((mask & feature.atr.le(0).to_numpy()).sum())
                if zero_atr or not np.array_equal(mask, ready):
                    feature_issues.append({"symbol": row.symbol,
                                           "warm_mask_nonpositive_atr_rows": zero_atr,
                                           "warmup_and_feature_ready_equal": np.array_equal(mask, ready),
                                           "indicator_unready_inside_warm_mask": int((mask & ~ready).sum())})
            elif row.status != "NO_USABLE_WINDOW":
                raise ValueError(f"Unavailable coin incorrectly tradable {row.symbol}")
            records.append({"symbol": row.symbol, "status": row.status, "rows": len(d),
                            "joint_valid_days": int(expected_valid.sum()), "segments": len(spans)})
    result = {"status": "PASS" if not errors else "FAIL", "errors": errors,
              "input_checksums_sha256": sha(INPUT / "checksums.json"),
              "audit_script_sha256": sha(Path(__file__)), "checked_files": len(checksums),
              "symbol_windows": len(records), "observed_contracts": 874, "included_coins": 652,
              "cohorts": scope.cohort.value_counts().to_dict(), "candidate_results_computed": False,
              "funding_window_verified": False, "feature_issues": feature_issues,
              "records": records}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "records"}, indent=2))
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
