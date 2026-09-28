"""Prepare all available historical price segments; never run strategy accounts.

The primary 29-day startup request retains its original acceptance rule.
Short histories may be returned by an explicitly separate backward=1 inventory
request; joint eligibility is always recomputed with the fixed 29-day warmup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import pandas as pd

from prepare_inputs_v4 import (LAB, FAMILY, sha, save_json, save_frame,
                              joint_daily_projection, segment_rows)
from startup_batch import create_startup_context, require_research_startup_batch
from strategy_lab.data.research_bundle import read_bundle_contract, require_research_startup


def returned_batch(request, context, out, label):
    request_path = out / "requests" / (label + ".json")
    save_json(request_path, request)
    result = require_research_startup_batch(request, context=context)
    assert set(result.prices) | set(result.failures) == set(request["symbols"])
    report_path = out / "startup_reports" / (label + ".json")
    save_json(report_path, result.report)
    receipt = {"request_path": str(request_path.relative_to(out)), "request_sha256": sha(request_path),
               "startup_report_path": str(report_path.relative_to(out)), "startup_report_sha256": sha(report_path),
               "frame_role": "primary_startup_return"}
    prices, receipts = dict(result.prices), {s: dict(receipt) for s in result.prices}
    # No result is accepted after arbitrary failures. The batch wrapper itself
    # permits only the precise no-complete-window rejection.
    if result.failures:
        assert request["timeframe"] == "1d", "Unexpected hourly no-window rejection"
        for symbol, error in result.failures.items():
            assert error == f"{symbol}: no complete eligible feature/label window"
        retention = {**request, "symbols": list(result.failures), "backward_bars": 1}
        rp = out / "requests" / (label + "_inventory_only.json")
        save_json(rp, retention)
        retained = require_research_startup(retention, project_root=LAB)
        rr = out / "startup_reports" / (label + "_inventory_only.json")
        save_json(rr, retained.report)
        assert set(retained.prices) == set(result.failures)
        for symbol, frame in retained.prices.items():
            prices[symbol] = frame
            receipts[symbol] = {"request_path": str(rp.relative_to(out)), "request_sha256": sha(rp),
                "startup_report_path": str(rr.relative_to(out)), "startup_report_sha256": sha(rr),
                "frame_role": "inventory_retention_only_not_primary_29day_approved",
                "primary_rejection": result.failures[symbol], **{
                    "primary_request_path": receipt["request_path"],
                    "primary_startup_report_path": receipt["startup_report_path"]}}
    return prices, receipts, result.failures


def preserve_frame(out, frame, relative, receipt):
    saved = save_frame(out, frame, relative, receipt)
    reread = pd.read_parquet(out / relative)
    pd.testing.assert_frame_equal(frame.reset_index(drop=True), reread.reset_index(drop=True),
                                  check_exact=True)
    return {**saved, "saved_roundtrip_exact": True}


def prepare(plan_path, out):
    if out.exists():
        raise FileExistsError(f"Preserve prior preparation directory: {out}")
    plan = json.loads(plan_path.read_text())
    for relative, digest in plan["source_pins"].items():
        assert sha(LAB / relative) == digest, "Source changed: " + relative
    bundle, pin = read_bundle_contract(LAB, pin=plan["bundle_pin"])
    symbols = sorted(s for s, cls in bundle["observed_asset_classes"].items() if cls == "COIN")
    assert symbols == plan["symbols"] and len(symbols) == 652
    assert plan["start"] == "2019-09-09T00:00:00Z" and plan["end"] == "2026-09-05T00:00:00Z"
    assert plan["warmup_days"] == 29 and plan["batch_size"] == 8
    assert plan["selection"] == "all_joint_contiguous_segments_no_longest_selection"
    assert plan["mode"] == "price_diagnostic" and not plan["account_backtest"]
    parity_path = FAMILY / "artifacts/startup_batch_parity_20260909.json"
    parity = json.loads(parity_path.read_text())
    assert parity["status"] == "PASS" and parity["compared_frames"] == 6
    assert parity["source_sha256"]["startup_batch.py"] == sha(FAMILY / "scripts/startup_batch.py")
    out.mkdir(parents=True)
    begin = time.monotonic()
    save_json(out / "started.json", {"created_utc": datetime.now(timezone.utc).isoformat(),
        "plan_path": str(plan_path.relative_to(LAB)), "plan_sha256": sha(plan_path),
        "script_sha256": sha(Path(__file__)), "parity_report_sha256": sha(parity_path),
        "candidate_results_computed": False})
    save_json(out / "frozen_plan.json", plan)
    save_json(out / "source_pins.json", plan["source_pins"])
    observed = bundle["observed_asset_classes"]
    universe = pd.DataFrame([{"symbol": s, "observed_class": cls, "included": cls == "COIN",
                             "reason": "FROZEN_OBSERVED_COIN" if cls == "COIN" else "EXCLUDED_NOT_RECLASSIFIED"}
                            for s, cls in sorted(observed.items())])
    universe.to_csv(out / "universe.csv", index=False)
    universe.loc[universe.observed_class.eq("UNKNOWN")].to_csv(out / "unknown_separate_inventory.csv", index=False)
    context = create_startup_context(project_root=LAB, data_root=LAB / "data", pin=pin,
        symbols=symbols, start=plan["start"], end=plan["end"])
    save_json(out / "startup_context_initial.json", context.receipt())
    frames, scopes, segments = {}, [], []
    window = {"window_id": "history", "input_start": plan["start"],
              "trade_start": plan["start"], "end": plan["end"]}
    for offset in range(0, len(symbols), plan["batch_size"]):
        subset = symbols[offset:offset + plan["batch_size"]]
        batch_frames, batch_receipts, failures = {}, {}, {}
        for tf, backward in (("1d", 29), ("1h", 1)):
            request = {"schema_version": 1, **pin, "mode": "price_diagnostic", "timeframe": tf,
                       "symbols": subset, "start": plan["start"], "end": plan["end"],
                       "gap_policy": "contiguous_segments", "asset_policy": "crypto_only",
                       "backward_bars": backward, "forward_bars": 0}
            prices, receipts, rejected = returned_batch(request, context, out, f"{offset:04d}_{tf}")
            batch_frames[tf], batch_receipts[tf], failures[tf] = prices, receipts, rejected
            for symbol in subset:
                slug = symbol.split("/")[0]
                frames.setdefault(symbol, {})[tf] = preserve_frame(out, prices[symbol],
                    f"returned/{tf}/{slug}.parquet", receipts[symbol])
        for symbol in subset:
            slug = symbol.split("/")[0]
            daily, hourly = batch_frames["1d"][symbol], batch_frames["1h"][symbol]
            joint, stats = joint_daily_projection(daily, hourly, 29)
            frames[symbol]["joint_daily"] = preserve_frame(out, joint, f"joint/{slug}.parquet",
                {"source_daily_sha256": frames[symbol]["1d"]["sha256"],
                 "source_hourly_sha256": frames[symbol]["1h"]["sha256"]})
            coin_segments = segment_rows(joint, window, 29)
            for segment in coin_segments:
                segment["has_trading_window"] = segment["trade_days"] > 0
                segment["retained"] = True
            segments.extend(coin_segments)
            row = {"symbol": symbol, "slug": slug, "observed_class": "COIN",
                   "primary_29day_startup_approved": symbol not in failures["1d"],
                   "daily_frame_role": batch_receipts["1d"][symbol]["frame_role"],
                   "daily_first": daily.ts.iloc[0], "daily_last": daily.ts.iloc[-1],
                   "hourly_first": hourly.ts.iloc[0], "hourly_last": hourly.ts.iloc[-1],
                   **{k: v for k, v in stats.items() if k != "aggregation_max_abs_differences"},
                   "all_retained_segments": len(coin_segments),
                   "segments_with_trading_window": sum(s["trade_days"] > 0 for s in coin_segments),
                   "total_trade_days_across_all_segments": sum(s["trade_days"] for s in coin_segments),
                   "max_segment_trade_days": max((s["trade_days"] for s in coin_segments), default=0),
                   "aggregation_max_abs_difference": max(stats["aggregation_max_abs_differences"].values())}
            row["status"] = "JOINT_PRICE_WINDOWS_VERIFIED" if row["total_trade_days_across_all_segments"] else "RETAINED_NO_TRADING_WINDOW"
            scopes.append(row)
        save_json(out / "batch_progress" / f"{offset:04d}.json",
            {"coins_completed": len(scopes), "elapsed_seconds": time.monotonic() - begin,
             "coin_rows": scopes[-len(subset):], "frames": {s: frames[s] for s in subset}})
        print(f"PREPARED {len(scopes)}/{len(symbols)} coins; {len(segments)} retained segments; seconds={time.monotonic()-begin:.1f}", flush=True)
    pd.DataFrame(scopes).to_csv(out / "scope.csv", index=False)
    pd.DataFrame(segments).to_csv(out / "segments.csv", index=False)
    save_json(out / "frames_manifest.json", frames)
    save_json(out / "startup_context.json", context.receipt())
    for relative, digest in plan["source_pins"].items():
        assert sha(LAB / relative) == digest, "Source changed during preparation: " + relative
    assert json.loads(plan_path.read_text()) == plan
    summary = {"complete": True, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.monotonic() - begin, "observed_contracts": len(observed), "included_coins": 652,
        "unknown_excluded_and_preserved_separately": 31, "time_range": [plan["start"], plan["end"]],
        "coins_with_trading_windows": sum(s["total_trade_days_across_all_segments"] > 0 for s in scopes),
        "coins_retained_without_trading_window": sum(s["total_trade_days_across_all_segments"] == 0 for s in scopes),
        "retained_joint_segments": len(segments),
        "joint_segments_with_trading_windows": sum(s["trade_days"] > 0 for s in segments),
        "total_trading_days_across_all_segments": sum(s["trade_days"] for s in segments),
        "api_frames_saved": sum(len(v) - 1 for v in frames.values()),
        "joint_frames_saved": len(frames), "all_saved_frames_roundtrip_exact": True,
        "no_longest_segment_selection": True, "candidate_results_computed": False,
        "funding_window_verified": False, "historical_identity_verified": False,
        "pit_universe_proven": False, "tradability_proven": False}
    save_json(out / "completion.json", summary)
    save_json(out / "checksums.json", {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()})
    print(json.dumps(summary), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.plan.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
