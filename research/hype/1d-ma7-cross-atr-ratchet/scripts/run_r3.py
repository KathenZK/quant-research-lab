"""Predeclared R3 price-progress comparison, complete ledgers and global review."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path

import numpy as np
import pandas as pd

import engine_r2 as r2
import engine_r3 as r3
from run_r2 import BASE, INPUT, WINDOWS, load_r2_inputs, save_result, sha, verify_anchor, write_json

PARENT = BASE / "artifacts/r2_slowdown_tightening_20260909"
CONTRACT = BASE / "specs/r3-price-progress-20260909.md"
OUTPUT = BASE / "artifacts/r3_price_progress_20260909"
PRIMARY = "P2_extreme"
STRESS_IDS = ["B0_r2_stall", "P2_ma", "P2_extreme", "P2_extreme_cross", "P2_extreme_cap10", "P2_extreme_cross_cap10"]


def load_r3_inputs():
    hashes = json.loads((PARENT / "artifact_checksums.json").read_text())
    for name, expected in hashes.items():
        assert sha(PARENT / name) == expected, f"Frozen R2 output changed: {name}"
    manifest = json.loads((PARENT / "run_manifest.json").read_text())
    for key, path in {
        "engine_sha256": BASE / "scripts/engine_r2.py",
        "run_script_sha256": BASE / "scripts/run_r2.py",
        "contract_sha256": BASE / "specs/r2-slowdown-tightening-20260909.md",
        "input_checksums_sha256": INPUT / "checksums.json",
    }.items():
        assert sha(path) == manifest[key], f"Frozen R2 source/input changed: {key}"
    return load_r2_inputs()


def case_list():
    old = r3.Config(reverse=False, tighten_mode="stall_only")
    fixed = r3.Config(reverse=False, tighten_mode="fixed")
    cases = [
        ("B0_r2_stall", "原R2：MA停滞且盈利才收紧", old),
        ("B1_r1_fixed", "原R1：固定1.5ATR", fixed),
        ("C1_cross_exit", "原R2＋反向穿越退出", replace(old, exit_opposite_cross=True)),
        ("C2_initial_cap10", "原R2＋初始距离10%上限", replace(old, initial_stop_cap_pct=.10)),
        ("C3_cross_cap10", "原R2＋反穿退出＋初始10%", replace(old, exit_opposite_cross=True, initial_stop_cap_pct=.10)),
    ]
    for anchor in ["ma", "extreme"]:
        for days in [2, 3, 4]:
            label = f"{days}日未创新高低＋" + ("MA止损" if anchor == "ma" else "极值保护")
            cases.append((f"P{days}_{anchor}", label, replace(fixed, progress_days=days, stop_anchor=anchor)))
    main = replace(fixed, progress_days=2, stop_anchor="extreme")
    cases.extend([
        ("P2_extreme_cross", "2日未创新高低＋极值＋反穿退出", replace(main, exit_opposite_cross=True)),
        ("P2_extreme_cap10", "2日未创新高低＋极值＋初始10%", replace(main, initial_stop_cap_pct=.10)),
        ("P2_extreme_cross_cap10", "2日未创新高低＋极值＋反穿＋初始10%", replace(main, exit_opposite_cross=True, initial_stop_cap_pct=.10)),
    ])
    assert len(cases) == 14 and len({c.name for _, _, c in cases}) == 14
    return cases


def global_trade_review(hourly, runs):
    h = hourly.copy()
    h["timestamp"] = pd.to_datetime(h.timestamp, utc=True)
    old = runs["B0_r2_stall"][1]
    old_lookup = {(pd.Timestamp(t.entry_time), int(t.side)): int(t.trade_id) for t in old.itertuples()}
    rows = []
    for case_id, (_, trades, _, _, _) in runs.items():
        for t in trades.itertuples():
            # Exclude the ambiguous exit hour. Full earlier held hours are certain
            # to precede the fill; these give a lower bound on favorable excursion.
            held = h[(h.timestamp >= pd.Timestamp(t.entry_time)) & (h.timestamp + pd.Timedelta(hours=1) <= pd.Timestamp(t.exit_time))]
            extreme = (float(held.high.max()) if t.side == 1 else float(held.low.min())) if len(held) else float(t.entry_price)
            extreme = max(extreme, t.entry_price, t.exit_price) if t.side == 1 else min(extreme, t.entry_price, t.exit_price)
            mfe = max(0.0, t.side * (extreme / t.entry_price - 1) * 100)
            actual_move = t.side * (t.exit_price / t.entry_price - 1) * 100
            rows.append({"case_id": case_id, **t._asdict(),
                         "same_entry_old_trade_id": old_lookup.get((pd.Timestamp(t.entry_time), int(t.side))),
                         "holding_days": (pd.Timestamp(t.exit_time) - pd.Timestamp(t.entry_time)).total_seconds() / 86400,
                         "favorable_price_in_completed_held_hours": extreme,
                         "favorable_excursion_lower_bound_pct": mfe,
                         "realized_price_move_pct": actual_move,
                         "giveback_lower_bound_pct": max(0.0, mfe - actual_move),
                         "excursion_note": "Price movement, not account return; excludes ambiguous exit hour; no future bar used"})
    review = pd.DataFrame(rows).drop(columns="Index", errors="ignore")
    metrics = []
    for case_id, part in review.groupby("case_id", sort=False):
        positive = part[part.net_pnl > 0].net_pnl
        metrics.append({"case_id": case_id, "all_trades": len(part),
                        "same_entry_as_r2": int(part.same_entry_old_trade_id.notna().sum()),
                        "new_entry_events": int(part.same_entry_old_trade_id.isna().sum()),
                        "median_giveback_lower_bound_pct": float(part.giveback_lower_bound_pct.median()),
                        "max_giveback_lower_bound_pct": float(part.giveback_lower_bound_pct.max()),
                        "worst_trade_return_pct": float(part.return_on_entry_equity.min() * 100),
                        "best_trade_return_pct": float(part.return_on_entry_equity.max() * 100),
                        "mean_holding_days": float(part.holding_days.mean()),
                        "sample_end_pnl": float(part.loc[part.exit_reason == "sample_end", "net_pnl"].sum()),
                        "largest_two_share_of_positive_profit_pct": float(positive.nlargest(2).sum() / positive.sum() * 100) if len(positive) else 0})
    return review, pd.DataFrame(metrics)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error("Use a new output directory; frozen results must not be overwritten")
    h, d, f = load_r3_inputs()
    cases = case_list()
    out.mkdir(parents=True)
    write_json(out / "run_manifest.json", {
        "family": "HYPE-1D-MA7-CAR", "round": "R3", "created_before_new_results_utc": str(pd.Timestamp.now(tz="UTC")),
        "contract_sha256": sha(CONTRACT), "engine_sha256": sha(BASE / "scripts/engine_r3.py"),
        "run_script_sha256": sha(Path(__file__)), "r2_checksum_manifest_sha256": sha(PARENT / "artifact_checksums.json"),
        "input_checksums_sha256": sha(INPUT / "checksums.json"), "windows": WINDOWS,
        "cases": [{"case_id": i, "label": label, "config": asdict(c)} for i, label, c in cases],
        "primary_case": PRIMARY, "sensitivity_cases": STRESS_IDS,
        "classification": "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS", "funding_window_verified": False,
    })
    d.to_csv(out / "daily_features.csv", index=False)
    anchors, cached = [], {}
    saved = pd.read_csv(PARENT / "all_results.csv")
    for case_id, label, c in cases[:2]:
        prior_c = r2.Config(reverse=False, tighten_mode=c.tighten_mode)
        for window, (lo, hi) in WINDOWS.items():
            old = r2.simulate(h, d, prior_c, pd.Timestamp(lo), pd.Timestamp(hi))
            new = r3.simulate(h, d, c, pd.Timestamp(lo), pd.Timestamp(hi))
            verify_anchor(old, new)
            for key, value in old[0].items():
                if key != "name":
                    assert new[0][key] == value, f"R2 economic/control field mismatch: {key}"
            row = saved[(saved.entry_mode == "original") & (saved.tighten_mode == c.tighten_mode) & (~saved.reverse) & (saved.window == window)].iloc[0]
            keys = ["return_pct", "ending_equity", "max_drawdown_pct", "fee_total", "long_pnl", "short_pnl"]
            diff = max(abs(float(new[0][key]) - float(row[key])) for key in keys)
            assert diff <= 1e-8
            anchors.append({"case_id": case_id, "window": window, "live_r2_r3_exact_equal": True, "frozen_csv_max_absolute_difference": diff})
            cached[(case_id, window)] = new
    write_json(out / "baseline_reproduction.json", anchors)
    print("Exact old controls: 6/6 PASS", flush=True)
    rows, full = [], {}
    for case_id, label, c in cases:
        for window, (lo, hi) in WINDOWS.items():
            result = cached.get((case_id, window))
            if result is None:
                result = r3.simulate(h, d, c, pd.Timestamp(lo), pd.Timestamp(hi))
            save_result(out / "runs" / case_id / window, result)
            rows.append({"case_id": case_id, "label": label, "window": window, **result[0]})
            if window == "full":
                full[case_id] = result
        print("completed " + case_id, flush=True)
    grid = pd.DataFrame(rows)
    assert len(grid) == 42
    grid.to_csv(out / "all_results.csv", index=False)
    review, review_metrics = global_trade_review(h, full)
    review.to_csv(out / "all_full_window_trades.csv", index=False)
    review_metrics.to_csv(out / "global_trade_metrics.csv", index=False)
    exit_counts = review.groupby(["case_id", "side", "exit_reason"]).size().rename("count").reset_index()
    exit_counts.to_csv(out / "exit_reason_counts.csv", index=False)
    comparisons = []
    for case_id, label, _ in cases:
        one = grid[grid.case_id == case_id]
        control = grid[grid.case_id == "B0_r2_stall"].set_index("window")
        for row in one.itertuples():
            base = control.loc[row.window]
            comparisons.append({"case_id": case_id, "window": row.window,
                                "return_change_pp": row.return_pct - base.return_pct,
                                "drawdown_reduction_pp": row.max_drawdown_pct - base.max_drawdown_pct,
                                "return_not_lower": row.return_pct >= base.return_pct - 1e-10,
                                "drawdown_not_larger": row.max_drawdown_pct >= base.max_drawdown_pct - 1e-10})
    pd.DataFrame(comparisons).to_csv(out / "comparison_to_r2.csv", index=False)
    stress = []
    for case_id, label, c in cases:
        if case_id not in STRESS_IDS:
            continue
        for scenario, variant, funding, carry in [
            ("slippage_10bp", replace(c, slip=.001), None, 0),
            ("daily_signal_delay_1h", replace(c, delay_hours=1), None, 0),
            ("adverse_carry_5bp_day", c, None, .0005),
            ("observed_funding_unverified", c, f, 0),
        ]:
            result = r3.simulate(h, d, variant, pd.Timestamp(WINDOWS["full"][0]), pd.Timestamp(WINDOWS["full"][1]), funding, carry)
            save_result(out / "sensitivity" / case_id / scenario, result)
            stress.append({"case_id": case_id, "scenario": scenario, **result[0]})
    assert len(stress) == 24
    pd.DataFrame(stress).to_csv(out / "sensitivity.csv", index=False)
    assert not grid.bankrupt.any() and np.isfinite(grid.return_pct).all()
    write_json(out / "artifact_checksums.json", {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()})
    print(grid[grid.window == "full"][["case_id", "return_pct", "max_drawdown_pct", "trades"]].to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
