"""Run fixed, predeclared MA7 rules on every verified eligible market segment."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

from common import CONTRACT, ENGINE_PATH, ENGINE_SHA256, INPUT, RESULTS, ROOT, cases, load_engine, sha, write_json

TRADE_COLUMNS = ["trade_id", "side", "entry_time", "exit_time", "entry_price", "exit_price", "entry_reason",
                 "signal_day", "cross_day", "entry_wait_days_used", "net_pnl", "exit_reason", "return_on_entry_equity"]
STOP_COLUMNS = ["timestamp", "trade_id", "side", "new_stop", "old_stop", "new_mult", "old_mult", "tightened"]


def verify_inputs():
    hashes = json.loads((INPUT / "checksums.json").read_text())
    for relative, expected in hashes.items():
        assert sha(INPUT / relative) == expected, "Input artifact changed: " + relative
    plan = json.loads((INPUT / "frozen_plan.json").read_text())
    started = json.loads((INPUT / "started.json").read_text())
    assert started["contract_sha256"] == sha(CONTRACT)
    if "input_loading_supplement_path" in plan:
        assert sha(ROOT / plan["input_loading_supplement_path"]) == plan["input_loading_supplement_sha256"]
    assert len(plan["symbols"]) == 652
    return plan


def select_scope():
    scope = pd.read_csv(INPUT / "scope.csv")
    segments = pd.read_csv(INPUT / "segments.csv")
    records = []
    for row in scope.to_dict("records"):
        symbol = row["symbol"]
        choices = segments[(segments.symbol == symbol) & (segments.trade_days > 0)].copy()
        choices = choices.sort_values(["trade_days", "input_start"], ascending=[False, True])
        clean = {key: None if pd.isna(value) else value for key, value in row.items()}
        item = {**clean, "input_status": row["status"], "slug": symbol.split("/")[0]}
        if not len(choices):
            item.update(status="NO_USABLE_TRADING_WINDOW", cohort="excluded", trade_days=0,
                        selected_segment_id=None, input_start=None, trade_start=None, end=None,
                        boundary_end_due_to_data=None)
        else:
            best = choices.iloc[0]
            complete = bool(best.full_window_contiguous) and int(best.trade_days) == 433
            item.update(status="READY_TO_REPLAY", cohort="main_full" if complete else "partial" if best.trade_days >= 180 else "short",
                        selected_segment_id=best.segment_id, input_start=best.input_start,
                        trade_start=best.first_trade_open, end=best.end, trade_days=int(best.trade_days),
                        boundary_end_due_to_data=bool(best.boundary_end_due_to_data))
        records.append(item)
    selected = pd.DataFrame(records)
    assert len(selected) == 652 and selected.symbol.nunique() == 652
    return selected


def load_selected_frames(item, frame_manifest):
    source = frame_manifest["main/" + item["symbol"]]
    for key in ["joint_daily", "1h"]:
        assert sha(INPUT / source[key]["path"]) == source[key]["sha256"]
    d = pd.read_parquet(INPUT / source["joint_daily"]["path"])
    d = d[d.joint_segment_id == item["selected_segment_id"]].copy().sort_values("ts").reset_index(drop=True)
    h = pd.read_parquet(INPUT / source["1h"]["path"])
    lo, hi = pd.Timestamp(item["input_start"]), pd.Timestamp(item["end"])
    h = h[(h.ts >= lo) & (h.ts < hi)].copy().sort_values("ts").reset_index(drop=True)
    expected_days = pd.date_range(lo, hi, freq="D", inclusive="left")
    expected_hours = pd.date_range(lo, hi, freq="h", inclusive="left")
    assert pd.DatetimeIndex(d.ts).as_unit("ns").equals(expected_days.as_unit("ns"))
    assert pd.DatetimeIndex(h.ts).as_unit("ns").equals(expected_hours.as_unit("ns"))
    assert d.joint_eligible.all() and d.eligible.all() and h.eligible.all()
    assert d.is_closed.all() and h.is_closed.all()
    assert d.iloc[28:].research_window_valid.all() and not d.iloc[:28].research_window_valid.any()
    for frame in [d, h]:
        values = frame[["open", "high", "low", "close"]].to_numpy(float)
        assert np.isfinite(values).all() and (values > 0).all()
        assert frame.high.ge(frame[["open", "close", "low"]].max(axis=1)).all()
        assert frame.low.le(frame[["open", "close", "high"]].min(axis=1)).all()
    h = h.rename(columns={"ts": "timestamp"})
    d = d.rename(columns={"ts": "timestamp"})
    engine = load_engine()
    feature = engine.enrich_features(engine.features(d))
    assert feature.ready.equals(d.research_window_valid), "Strategy and input warmup mismatch"
    assert feature.loc[feature.ready, "atr"].gt(0).all()
    assert pd.Timestamp(item["trade_start"]) >= lo + pd.Timedelta(days=29)
    return h, feature, source


def period_windows(item):
    lo, hi = pd.Timestamp(item["trade_start"]), pd.Timestamp(item["end"])
    windows = {"full": (str(lo), str(hi))}
    if item["trade_days"] >= 180:
        split = pd.Timestamp("2026-03-15T00:00:00Z") if item["cohort"] == "main_full" else lo + pd.Timedelta(days=int(item["trade_days"] * .6))
        windows.update(early60=(str(lo), str(split)), late40=(str(split), str(hi)))
    return windows


def save_result(directory, result):
    directory.mkdir(parents=True, exist_ok=False)
    summary, trades, curve, stops, funds = result
    write_json(directory / "summary.json", summary)
    (trades if len(trades) else pd.DataFrame(columns=TRADE_COLUMNS)).to_csv(directory / "trades.csv", index=False)
    (stops if len(stops) else pd.DataFrame(columns=STOP_COLUMNS)).to_csv(directory / "stops.csv", index=False)
    curve.to_parquet(directory / "equity.parquet", index=False, compression="zstd")
    if len(funds):
        funds.to_csv(directory / "funding.csv", index=False)


def buy_hold(hourly, lo, hi, fee=.0005, slip=.0003):
    h = hourly[(hourly.timestamp >= pd.Timestamp(lo)) & (hourly.timestamp < pd.Timestamp(hi))]
    first, last = float(h.iloc[0].open), float(h.iloc[-1].close)
    fill = first * (1 + slip)
    qty = 10000 / (fill * (1 + fee))
    paid = qty * fill * fee
    open_mark = 10000 - paid + qty * (h.open.to_numpy() - fill)
    close_mark = 10000 - paid + qty * (h.close.to_numpy() - fill)
    prices = np.column_stack([h.open.to_numpy(), h.close.to_numpy()]).ravel()
    times = np.column_stack([h.timestamp.to_numpy(), (h.timestamp + pd.Timedelta(hours=1)).to_numpy()]).ravel()
    values = np.column_stack([open_mark, close_mark]).ravel()
    exit_fill = last * (1 - slip)
    exit_fee = qty * exit_fill * fee
    end_equity = 10000 - paid + qty * (exit_fill - fill) - exit_fee
    curve = pd.DataFrame({"timestamp": [pd.Timestamp(lo), *times, pd.Timestamp(hi)],
                          "equity": [10000., *values, end_equity], "price": [first, *prices, last]})
    eq = curve.equity.to_numpy(float)
    summary = {"case_id": "BUY_HOLD", "start": str(pd.Timestamp(lo)), "end_exclusive": str(pd.Timestamp(hi)),
               "ending_equity": end_equity, "return_pct": (end_equity / 10000 - 1) * 100,
               "max_drawdown_pct": float(np.min(eq / np.maximum.accumulate(eq) - 1) * 100),
               "trades": 1, "fee_total": paid + exit_fee, "fee": fee, "slip": slip,
               "funding_window_verified": False}
    return summary, curve


def verify_original_hype(h, d, out):
    old_path = ROOT / "research/hype/1d-ma7-cross-atr-ratchet/scripts/engine_r4.py"
    assert sha(old_path) == "feb82e01e0b63a55a64c549b1f51bc581b86b9d83e08f77a507681184beec50a"
    spec = importlib.util.spec_from_file_location("ma7_frozen_hype_r4_control", old_path)
    old = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = old
    spec.loader.exec_module(old)
    new = load_engine()
    checks = []
    for case_id, _, cfg in cases()[:2]:
        prior = asdict(cfg)
        prior.pop("entry_wait_days")
        config = old.Config(**prior)
        for window, lo, hi in [("full", "2025-06-29T00:00Z", "2026-09-05T00:00Z"),
                              ("early60", "2025-06-29T00:00Z", "2026-03-15T00:00Z"),
                              ("late40", "2026-03-15T00:00Z", "2026-09-05T00:00Z")]:
            a = old.simulate(h, d, config, pd.Timestamp(lo), pd.Timestamp(hi))
            b = new.simulate(h, d, cfg, pd.Timestamp(lo), pd.Timestamp(hi))
            for key, val in a[0].items():
                if key != "name":
                    assert b[0][key] == val, f"Exact HYPE summary mismatch {key}"
            for idx in range(1, 5):
                pd.testing.assert_frame_equal(a[idx], b[idx][a[idx].columns], check_exact=True)
            checks.append({"case_id": case_id, "window": window, "all_old_columns_exact_equal": True})
    write_json(out / "hype_original_controls.json", checks)


def replay_coin(item, frame_manifest, out_string):
    out = Path(out_string)
    h, d, source = load_selected_frames(item, frame_manifest)
    windows = period_windows(item)
    market = out / "market" / item["slug"]
    market.mkdir(parents=True, exist_ok=False)
    d.to_csv(market / "daily_features.csv", index=False)
    h.to_parquet(market / "hourly.parquet", index=False, compression="zstd")
    write_json(market / "metadata.json", {**item, "windows": windows, "input_source": source,
                                        "daily_features_sha256": sha(market / "daily_features.csv"),
                                        "hourly_sha256": sha(market / "hourly.parquet")})
    engine = load_engine()
    rows, stress, bh = [], [], []
    for case_id, label, c in cases():
        for window, (lo, hi) in windows.items():
            result = engine.simulate(h, d, c, pd.Timestamp(lo), pd.Timestamp(hi))
            assert pd.Timestamp(result[0]["start"]) == pd.Timestamp(lo)
            assert pd.Timestamp(result[0]["end_exclusive"]) == pd.Timestamp(hi)
            save_result(out / "runs" / item["slug"] / case_id / window, result)
            rows.append({"symbol": item["symbol"], "slug": item["slug"], "cohort": item["cohort"],
                         "trade_days": item["trade_days"], "case_id": case_id, "label": label,
                         "window": window, **result[0]})
        lo, hi = windows["full"]
        for scenario, cfg, carry in [("slippage_10bp", replace(c, slip=.001), 0), ("carry_5bp_day", c, .0005)]:
            result = engine.simulate(h, d, cfg, pd.Timestamp(lo), pd.Timestamp(hi), None, carry)
            save_result(out / "sensitivity" / item["slug"] / case_id / scenario, result)
            stress.append({"symbol": item["symbol"], "slug": item["slug"], "cohort": item["cohort"],
                           "case_id": case_id, "scenario": scenario, **result[0]})
    for window, (lo, hi) in windows.items():
        summary, curve = buy_hold(h, lo, hi)
        directory = out / "buy_hold" / item["slug"] / window
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / "summary.json", summary)
        curve.to_parquet(directory / "equity.parquet", index=False, compression="zstd")
        bh.append({"symbol": item["symbol"], "slug": item["slug"], "cohort": item["cohort"], "window": window, **summary})
    return rows, stress, bh


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error("Use a fresh directory; retained results must not be overwritten")
    plan = verify_inputs()
    scope = select_scope()
    frames = json.loads((INPUT / "frames_manifest.json").read_text())
    out.mkdir(parents=True)
    scope.to_csv(out / "scope.csv", index=False)
    write_json(out / "run_manifest.json", {
        "family_id": "BIN-1D-MA7-CAR-GEN", "round": "P1", "created_before_new_results_utc": str(pd.Timestamp.now(tz="UTC")),
        "contract_path": str(CONTRACT.relative_to(ROOT)), "contract_sha256": sha(CONTRACT),
        "engine_path": str(ENGINE_PATH.relative_to(ROOT)), "engine_sha256": ENGINE_SHA256,
        "run_script_sha256": sha(Path(__file__)), "common_sha256": sha(Path(__file__).with_name("common.py")),
        "input_checksums_sha256": sha(INPUT / "checksums.json"), "input_plan_sha256": sha(INPUT / "frozen_plan.json"),
        "input_plan": plan, "cases": [{"case_id": cid, "label": label, "config": asdict(cfg)} for cid, label, cfg in cases()],
        "primary_case": "H4_D0", "primary_entry_extension": "H4_D3", "observed_coins": len(scope),
        "cohort_counts": {str(k): int(v) for k, v in scope.cohort.value_counts().items()},
        "classification": "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS", "funding_window_verified": False,
        "all_symbols_same_stresses": ["slippage_10bp", "carry_5bp_day"], "workers": args.workers,
    })
    hype = scope[scope.symbol == "HYPE/USDT:USDT"].iloc[0].to_dict()
    h, d, _ = load_selected_frames(hype, frames)
    verify_original_hype(h, d, out)
    del h, d
    print("Six HYPE old controls exact; all-cohort scope " + str(scope.cohort.value_counts().to_dict()), flush=True)
    candidates = scope[scope.cohort != "excluded"].to_dict("records")
    rows, stress, buyhold, failures = [], [], [], []
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(replay_coin, item, {"main/" + item["symbol"]: frames["main/" + item["symbol"]]}, str(out)): item
                for item in candidates}
        for n, future in enumerate(as_completed(jobs), start=1):
            item = jobs[future]
            try:
                r, s, b = future.result()
            except Exception as exc:
                failures.append({"symbol": item["symbol"], "slug": item["slug"], "error_type": type(exc).__name__, "error": str(exc)})
                write_json(out / "execution_failures.json", failures)
                print("FAILED " + item["symbol"] + ": " + repr(exc), flush=True)
            else:
                rows.extend(r)
                stress.extend(s)
                buyhold.extend(b)
            if n % 20 == 0 or n == len(jobs):
                print(f"Completed {n}/{len(jobs)} coins; errors={len(failures)}; elapsed={time.monotonic()-started:.1f}s", flush=True)
    pd.DataFrame(rows).sort_values(["symbol", "case_id", "window"]).to_csv(out / "summary.csv", index=False)
    pd.DataFrame(stress).sort_values(["symbol", "case_id", "scenario"]).to_csv(out / "stress.csv", index=False)
    pd.DataFrame(buyhold).sort_values(["symbol", "window"]).to_csv(out / "buy_hold.csv", index=False)
    write_json(out / "execution_failures.json", failures)
    done = set(r["symbol"] for r in rows)
    scope.loc[scope.symbol.isin(done), "status"] = "REPLAY_COMPLETED"
    scope.loc[scope.symbol.isin([r["symbol"] for r in failures]), "status"] = "EXECUTION_FAILED"
    scope.to_csv(out / "scope.csv", index=False)
    write_json(out / "completion.json", {"complete": not failures, "coins_completed": len(done), "coins_failed": len(failures),
               "price_excluded": int((scope.cohort == "excluded").sum()), "strategy_window_runs": len(rows),
               "stress_runs": len(stress), "buyhold_runs": len(buyhold), "seconds": time.monotonic()-started})
    write_json(out / "artifact_checksums.json", {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()})
    if failures:
        raise RuntimeError("Per-coin execution failures retained; do not publish complete-market results")
    print(f"COMPLETE {len(done)} coins, {len(rows)} strategy-window rows, {len(stress)} stress rows", flush=True)


if __name__ == "__main__":
    main()
