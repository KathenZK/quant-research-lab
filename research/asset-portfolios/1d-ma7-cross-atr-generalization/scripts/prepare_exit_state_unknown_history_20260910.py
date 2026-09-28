"""Prepare independently reviewed UNKNOWN tokens through public price startup.

The bundle's UNKNOWN labels remain intact. This is a separate price diagnostic
queue, never a historical identity, funding, or tradability certification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import pandas as pd

from prepare_inputs_v4 import LAB, FAMILY, sha, save_json, joint_daily_projection, segment_rows
from prepare_exit_state_history_20260910 import preserve_frame
from strategy_lab.data.research_bundle import read_bundle_contract, require_research_startup


def load_subset(out, request, label, role):
    rp = out / "requests" / (label + ".json")
    save_json(rp, request)
    result = require_research_startup(request, project_root=LAB)
    assert set(result.prices) == set(request["symbols"])
    sp = out / "startup_reports" / (label + ".json")
    save_json(sp, result.report)
    receipt = {"request_path": str(rp.relative_to(out)), "request_sha256": sha(rp),
               "startup_report_path": str(sp.relative_to(out)), "startup_report_sha256": sha(sp),
               "frame_role": role}
    return result.prices, {s: dict(receipt) for s in result.prices}


def prepare(plan_path, out):
    assert not out.exists(), "Preserve any earlier preparation directory"
    plan = json.loads(plan_path.read_text())
    for rel, digest in plan["source_pins"].items():
        assert sha(LAB / rel) == digest, "Source changed: " + rel
    bundle, pin = read_bundle_contract(LAB, pin=plan["bundle_pin"])
    evidence = json.loads((LAB / plan["classification_path"]).read_text())
    assert sha(LAB / plan["classification_path"]) == plan["classification_sha256"]
    symbols = sorted(r["symbol"] for r in evidence["evidence"] if r["include_crypto_supplement"])
    assert symbols == plan["symbols"] and len(symbols) == 28
    assert all(bundle["observed_asset_classes"][s] == "UNKNOWN" for s in symbols)
    inventory = pd.read_csv(LAB / plan["daily_inventory_path"])
    assert sha(LAB / plan["daily_inventory_path"]) == plan["daily_inventory_sha256"]
    short = sorted(inventory.loc[inventory.symbol.isin(symbols) & inventory.ready29_days.eq(0), "symbol"])
    assert short == plan["inventory_only_symbols"] == ["BTCST/USDT:USDT"]
    assert plan["start"] == "2019-09-09T00:00:00Z" and plan["end"] == "2026-09-05T00:00:00Z"
    assert plan["warmup_days"] == 29 and plan["batch_size"] == 8
    assert plan["selection"] == "all_joint_contiguous_segments_no_longest_selection"
    assert plan["mode"] == "price_diagnostic" and plan["asset_policy"] == "observed_mixed_diagnostic"
    assert not plan["account_backtest"]
    out.mkdir(parents=True)
    begin = time.monotonic()
    save_json(out / "started.json", {"created_utc": datetime.now(timezone.utc).isoformat(),
        "plan_path": str(plan_path.relative_to(LAB)), "plan_sha256": sha(plan_path),
        "script_sha256": sha(Path(__file__)), "candidate_results_computed": False})
    save_json(out / "frozen_plan.json", plan)
    save_json(out / "classification_review.json", evidence)
    pd.DataFrame(evidence["evidence"]).to_csv(out / "universe.csv", index=False)
    frames, scopes, segments = {}, [], []
    window = {"window_id": "history", "input_start": plan["start"], "trade_start": plan["start"], "end": plan["end"]}
    for offset in range(0, len(symbols), plan["batch_size"]):
        subset = symbols[offset:offset + plan["batch_size"]]
        batch_frames, batch_receipts = {}, {}
        for tf, backward in (("1d", 29), ("1h", 1)):
            prices, receipts = {}, {}
            groups = [(subset, backward, "primary_startup_return")]
            if tf == "1d" and any(s in short for s in subset):
                groups = [([s for s in subset if s not in short], 29, "primary_startup_return"),
                          ([s for s in subset if s in short], 1, "inventory_retention_only_not_primary_29day_approved")]
            for gi, (ss, bb, role) in enumerate(groups):
                if not ss:
                    continue
                request = {"schema_version": 1, **pin, "mode": "price_diagnostic", "timeframe": tf,
                    "symbols": ss, "start": plan["start"], "end": plan["end"],
                    "gap_policy": "contiguous_segments", "asset_policy": "observed_mixed_diagnostic",
                    "backward_bars": bb, "forward_bars": 0}
                pp, rr = load_subset(out, request, f"{offset:04d}_{tf}_{gi}", role)
                prices.update(pp)
                receipts.update(rr)
            assert set(prices) == set(subset)
            batch_frames[tf], batch_receipts[tf] = prices, receipts
            for symbol in subset:
                slug = symbol.split("/")[0]
                frames.setdefault(symbol, {})[tf] = preserve_frame(out, prices[symbol], f"returned/{tf}/{slug}.parquet", receipts[symbol])
        for symbol in subset:
            slug = symbol.split("/")[0]
            daily, hourly = batch_frames["1d"][symbol], batch_frames["1h"][symbol]
            joint, stats = joint_daily_projection(daily, hourly, 29)
            frames[symbol]["joint_daily"] = preserve_frame(out, joint, f"joint/{slug}.parquet",
                {"source_daily_sha256": frames[symbol]["1d"]["sha256"], "source_hourly_sha256": frames[symbol]["1h"]["sha256"]})
            coin_segments = segment_rows(joint, window, 29)
            for segment in coin_segments:
                segment["has_trading_window"] = segment["trade_days"] > 0
                segment["retained"] = True
            segments.extend(coin_segments)
            row = {"symbol": symbol, "slug": slug, "observed_class": "UNKNOWN", "review_class": "VERIFIED_CRYPTO_TOKEN",
                "primary_29day_startup_approved": symbol not in short,
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
        save_json(out / "batch_progress" / f"{offset:04d}.json", {"coins_completed": len(scopes),
            "elapsed_seconds": time.monotonic() - begin, "coin_rows": scopes[-len(subset):],
            "frames": {s: frames[s] for s in subset}})
        print(f"PREPARED SUPPLEMENT {len(scopes)}/{len(symbols)}; segments={len(segments)}; seconds={time.monotonic()-begin:.1f}", flush=True)
    pd.DataFrame(scopes).to_csv(out / "scope.csv", index=False)
    pd.DataFrame(segments).to_csv(out / "segments.csv", index=False)
    save_json(out / "frames_manifest.json", frames)
    for rel, digest in plan["source_pins"].items():
        assert sha(LAB / rel) == digest, "Source changed during preparation: " + rel
    assert json.loads(plan_path.read_text()) == plan
    summary = {"complete": True, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.monotonic() - begin, "reviewed_unknown_contracts": 31, "included_tokens": 28,
        "excluded_verified_indices": ["BLUEBIRD/USDT:USDT", "DOTECO/USDT:USDT", "FOOTBALL/USDT:USDT"],
        "unresolved_symbols": [], "time_range": [plan["start"], plan["end"]],
        "coins_with_trading_windows": sum(s["total_trade_days_across_all_segments"] > 0 for s in scopes),
        "coins_retained_without_trading_window": sum(s["total_trade_days_across_all_segments"] == 0 for s in scopes),
        "retained_joint_segments": len(segments), "joint_segments_with_trading_windows": sum(s["trade_days"] > 0 for s in segments),
        "total_trading_days_across_all_segments": sum(s["trade_days"] for s in segments),
        "api_frames_saved": 2 * len(frames), "joint_frames_saved": len(frames), "all_saved_frames_roundtrip_exact": True,
        "candidate_results_computed": False, "bundle_unchanged": True, "historical_identity_verified": False,
        "funding_window_verified": False, "pit_universe_proven": False, "tradability_proven": False}
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
