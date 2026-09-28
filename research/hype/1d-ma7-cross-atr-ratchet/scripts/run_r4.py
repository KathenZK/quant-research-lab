"""Predeclared close-versus-high/low progress study with complete controls."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path

import numpy as np
import pandas as pd

import engine_r3 as r3
import engine_r4 as r4
from run_r2 import BASE, INPUT, WINDOWS, save_result, sha, verify_anchor, write_json
from run_r3 import global_trade_review, load_r3_inputs

PARENT = BASE / "artifacts/r3_price_progress_20260909"
CONTRACT = BASE / "specs/r4-close-progress-20260909.md"
OUTPUT = BASE / "artifacts/r4_close_progress_20260909"
PRIMARY = "C1_ma"


def load_r4_inputs():
    hashes = json.loads((PARENT / "artifact_checksums.json").read_text())
    for name, expected in hashes.items():
        assert sha(PARENT / name) == expected, f"Frozen R3 output changed: {name}"
    manifest = json.loads((PARENT / "run_manifest.json").read_text())
    for key, path in {
        "engine_sha256": BASE / "scripts/engine_r3.py",
        "run_script_sha256": BASE / "scripts/run_r3.py",
        "contract_sha256": BASE / "specs/r3-price-progress-20260909.md",
        "input_checksums_sha256": INPUT / "checksums.json",
    }.items():
        assert sha(path) == manifest[key], f"Frozen R3 source/input changed: {key}"
    return load_r3_inputs()


def case_list():
    fixed = r4.Config(reverse=False, tighten_mode="fixed")
    cases = [("B0_r2_stall", "原R2：MA停滞且盈利才收紧", replace(fixed, tighten_mode="stall_only"))]
    for source, prefix, label in [("high_low", "H", "日K高低价"), ("close", "C", "收盘价")]:
        for days in [1, 2, 3, 4]:
            cases.append((f"{prefix}{days}_ma", f"{label}连续{days}日未刷新后收紧",
                          replace(fixed, progress_days=days, progress_source=source)))
    assert len(cases) == 9 and len({c.name for _, _, c in cases}) == 9
    return cases


def source_trade_pairs(full):
    """Outer joins retain changed opportunities; dollar PnL is not attribution."""
    rows = []
    for n in [1, 2, 3, 4]:
        low_case, close_case = f"H{n}_ma", f"C{n}_ma"
        left = full[low_case][1].copy()
        right = full[close_case][1].copy()
        fields = ["entry_time", "side", "trade_id", "exit_time", "entry_price", "exit_price",
                  "return_on_entry_equity", "arm_day", "tightening_days", "net_pnl", "exit_reason"]
        pair = left[fields].merge(right[fields], how="outer", on=["entry_time", "side"],
                                  suffixes=("_high_low", "_close"), indicator=True)
        for row in pair.to_dict("records"):
            item = {"days": n, "high_low_case": low_case, "close_case": close_case, **row}
            item["match_type"] = item.pop("_merge")
            matched = item["match_type"] == "both"
            item["close_exit_earlier"] = bool(matched and pd.Timestamp(item["exit_time_close"]) < pd.Timestamp(item["exit_time_high_low"]))
            item["close_exit_later"] = bool(matched and pd.Timestamp(item["exit_time_close"]) > pd.Timestamp(item["exit_time_high_low"]))
            item["close_minus_high_low_trade_return_pp"] = (
                (item["return_on_entry_equity_close"] - item["return_on_entry_equity_high_low"]) * 100 if matched else None)
            rows.append(item)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error("Use a new output directory; frozen results must not be overwritten")
    h, d, f = load_r4_inputs()
    cases = case_list()
    out.mkdir(parents=True)
    write_json(out / "run_manifest.json", {
        "family": "HYPE-1D-MA7-CAR", "round": "R4", "created_before_new_results_utc": str(pd.Timestamp.now(tz="UTC")),
        "contract_sha256": sha(CONTRACT), "engine_sha256": sha(BASE / "scripts/engine_r4.py"),
        "run_script_sha256": sha(Path(__file__)), "r3_checksum_manifest_sha256": sha(PARENT / "artifact_checksums.json"),
        "input_checksums_sha256": sha(INPUT / "checksums.json"), "windows": WINDOWS,
        "cases": [{"case_id": i, "label": label, "config": asdict(c)} for i, label, c in cases],
        "primary_case": PRIMARY, "sensitivity_cases": [i for i, _, _ in cases],
        "classification": "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS", "funding_window_verified": False,
    })
    d.to_csv(out / "daily_features.csv", index=False)
    anchors, cached = [], {}
    saved = pd.read_csv(PARENT / "all_results.csv")
    for case_id, _, c in cases[:5]:
        old_config = asdict(c)
        old_config.pop("progress_source")
        prior_c = r3.Config(**old_config)
        prior_id = "B0_r2_stall" if case_id == "B0_r2_stall" else f"P{c.progress_days}_ma"
        for window, (lo, hi) in WINDOWS.items():
            old = r3.simulate(h, d, prior_c, pd.Timestamp(lo), pd.Timestamp(hi))
            new = r4.simulate(h, d, c, pd.Timestamp(lo), pd.Timestamp(hi))
            verify_anchor(old, new)
            for key, value in old[0].items():
                if key != "name":
                    assert new[0][key] == value, f"R3 economic/control field mismatch: {key}"
            frozen = saved[(saved.case_id == prior_id) & (saved.window == window)]
            diff = None
            if len(frozen):
                keys = ["return_pct", "ending_equity", "max_drawdown_pct", "fee_total", "long_pnl", "short_pnl"]
                diff = max(abs(float(new[0][key]) - float(frozen.iloc[0][key])) for key in keys)
                assert diff <= 1e-8
            anchors.append({"case_id": case_id, "prior_case_id": prior_id, "window": window,
                            "live_r3_r4_exact_equal": True, "has_frozen_r3_result": bool(len(frozen)),
                            "frozen_csv_max_absolute_difference": diff})
            cached[(case_id, window)] = new
    assert len(anchors) == 15 and sum(a["has_frozen_r3_result"] for a in anchors) == 12
    write_json(out / "baseline_reproduction.json", anchors)
    print("Exact R3 controls: 15/15 PASS; saved anchors: 12/12 PASS", flush=True)
    rows, full = [], {}
    for case_id, label, c in cases:
        for window, (lo, hi) in WINDOWS.items():
            result = cached.get((case_id, window))
            if result is None:
                result = r4.simulate(h, d, c, pd.Timestamp(lo), pd.Timestamp(hi))
            save_result(out / "runs" / case_id / window, result)
            rows.append({"case_id": case_id, "label": label, "window": window, **result[0]})
            if window == "full":
                full[case_id] = result
        print("completed " + case_id, flush=True)
    grid = pd.DataFrame(rows)
    assert len(grid) == 27
    grid.to_csv(out / "all_results.csv", index=False)
    review, review_metrics = global_trade_review(h, full)
    review.to_csv(out / "all_full_window_trades.csv", index=False)
    review_metrics.to_csv(out / "global_trade_metrics.csv", index=False)
    review.groupby(["case_id", "side", "exit_reason"]).size().rename("count").reset_index().to_csv(out / "exit_reason_counts.csv", index=False)
    source_trade_pairs(full).to_csv(out / "source_trade_pairs.csv", index=False)
    comparisons = []
    for n in [1, 2, 3, 4]:
        for window in WINDOWS:
            old = grid[(grid.case_id == f"H{n}_ma") & (grid.window == window)].iloc[0]
            new = grid[(grid.case_id == f"C{n}_ma") & (grid.window == window)].iloc[0]
            comparisons.append({"days": n, "window": window,
                                "high_low_return_pct": old.return_pct, "close_return_pct": new.return_pct,
                                "return_change_pp": new.return_pct - old.return_pct,
                                "high_low_drawdown_pct": old.max_drawdown_pct, "close_drawdown_pct": new.max_drawdown_pct,
                                "drawdown_reduction_pp": new.max_drawdown_pct - old.max_drawdown_pct,
                                "high_low_trades": int(old.trades), "close_trades": int(new.trades)})
    pd.DataFrame(comparisons).to_csv(out / "source_comparison.csv", index=False)
    stress = []
    for case_id, _, c in cases:
        for scenario, variant, funding, carry in [
            ("slippage_10bp", replace(c, slip=.001), None, 0),
            ("daily_signal_delay_1h", replace(c, delay_hours=1), None, 0),
            ("adverse_carry_5bp_day", c, None, .0005),
            ("observed_funding_unverified", c, f, 0),
        ]:
            result = r4.simulate(h, d, variant, pd.Timestamp(WINDOWS["full"][0]), pd.Timestamp(WINDOWS["full"][1]), funding, carry)
            save_result(out / "sensitivity" / case_id / scenario, result)
            stress.append({"case_id": case_id, "scenario": scenario, **result[0]})
        print("stress complete " + case_id, flush=True)
    assert len(stress) == 36
    pd.DataFrame(stress).to_csv(out / "sensitivity.csv", index=False)
    assert not grid.bankrupt.any() and np.isfinite(grid.return_pct).all()
    write_json(out / "artifact_checksums.json", {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()})
    print(grid[grid.window == "full"][["case_id", "return_pct", "max_drawdown_pct", "trades"]].to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
