"""Read-only audit of saved R2 artifacts; this script never invokes simulation."""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd


BASE = Path(__file__).resolve().parents[1]
ROOT = BASE / "artifacts/r2_slowdown_tightening_20260909"
R1 = BASE / "artifacts/results_20260909"
SUPPLEMENT = BASE / "artifacts/r2_post_result_stress_20260909"
OUT = BASE / "artifacts/r2_audit_20260909.json"
checks = []
failures = []
maximum = {"account_error": 0.0, "trade_net_error": 0.0,
           "summary_error": 0.0, "stop_formula_error": 0.0}


def check(label, condition, detail=None):
    ok = bool(condition)
    checks.append({"check": label, "pass": ok})
    if not ok:
        failures.append({"check": label, "detail": detail})


def close(label, actual, expected, tolerance=1e-8, maximum_key=None):
    a = np.asarray(actual, dtype=float)
    b = np.asarray(expected, dtype=float)
    diff = float(np.max(np.abs(a - b))) if a.size else 0.0
    if maximum_key:
        maximum[maximum_key] = max(maximum[maximum_key], diff)
    check(label, np.isfinite(diff) and diff <= tolerance, {"max_absolute_difference": diff})


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_key(row):
    return (row["entry_mode"], row["tighten_mode"], bool(row["reverse"]), float(row["profit_trigger_atr"]))


manifest = json.loads((ROOT / "run_manifest.json").read_text())
hashes = json.loads((ROOT / "artifact_checksums.json").read_text())
for name, expected in hashes.items():
    path = ROOT / name
    check(f"checksum:{name}", path.is_file() and digest(path) == expected)
current_files = {str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and p.name != "artifact_checksums.json"}
check("checksum_inventory_complete", set(hashes) == current_files)
for name, path in {
    "contract_sha256": BASE / "specs/r2-slowdown-tightening-20260909.md",
    "engine_sha256": BASE / "scripts/engine_r2.py",
    "run_script_sha256": BASE / "scripts/run_r2.py",
    "r1_engine_sha256": BASE / "scripts/engine.py",
    "r1_run_manifest_sha256": R1 / "run_manifest.json",
}.items():
    check(f"source_pin:{name}", digest(path) == manifest[name])

grid = pd.read_csv(ROOT / "all_results.csv")
sensitivity = pd.read_csv(ROOT / "sensitivity.csv")
daily = pd.read_csv(ROOT / "daily_features.csv")
daily["timestamp"] = pd.to_datetime(daily.timestamp, utc=True)
daily = daily.set_index("timestamp", drop=False)
expected_configs = set(itertools.product(
    ["original", "opposite_slowdown", "absolute_slowdown", "no_slope"],
    ["fixed", "stall_only", "armed_daily"], [False, True], [0.0],
)) | set(itertools.product(["opposite_slowdown"], ["stall_only", "armed_daily"], [False, True], [1.0]))
check("exactly_84_primary_rows", len(grid) == 84)
check("exactly_28_predeclared_configs", {config_key(c) for c in manifest["configs"]} == expected_configs and len(manifest["configs"]) == 28)
check("exact_grid_cross_product", {
    (*config_key(row), row["window"]) for row in grid.to_dict("records")
} == {(*c, window) for c in expected_configs for window in manifest["windows"]})
check("exactly_16_sensitivity_rows", len(sensitivity) == 16)
check("exact_sensitivity_cross_product", {
    (bool(row.reverse), row.tighten_mode, row.scenario) for row in sensitivity.itertuples()
} == set(itertools.product([False, True], ["stall_only", "armed_daily"], [
    "slippage_10bp", "daily_signal_delay_1h", "adverse_carry_5bp_day", "observed_funding_unverified",
])))

reproduction = json.loads((ROOT / "r1_reproduction.json").read_text())
check("six_recorded_baseline_reproductions", len(reproduction) == 6 and all(
    x["live_r1_r2_exact_equal"] and x["frozen_csv_max_abs_difference"] <= 1e-8 for x in reproduction
))
r1_grid = pd.read_csv(R1 / "all_results.csv")
anchors = grid[(grid.entry_mode == "original") & (grid.tighten_mode == "fixed")]
economics = ["return_pct", "ending_equity", "max_drawdown_pct", "adverse_hour_check_pct",
             "annualized_return_pct", "trades", "win_rate_pct", "profit_factor", "exposure_pct",
             "fee_total", "funding_paid", "carry_paid", "reversal_entries", "short_tp_exits",
             "long_trades", "long_pnl", "long_wins", "short_trades", "short_pnl", "short_wins"]
for anchor in anchors.itertuples():
    original = r1_grid[(r1_grid.slope == 0.05) & (r1_grid.reverse == anchor.reverse)
                       & (r1_grid.short_exit == "accel1_rsi30") & (r1_grid.window == anchor.window)].iloc[0]
    close(f"independent_saved_baseline:{anchor.reverse}:{anchor.window}",
          [getattr(anchor, k) for k in economics], original[economics], maximum_key="summary_error")
    if anchor.window == "full":
        prefix = "primary" if anchor.reverse else "no_reverse_accel1"
        directory = ROOT / "runs" / anchor.name / "full"
        old, new = pd.read_csv(R1 / f"{prefix}_trades.csv"), pd.read_csv(directory / "trades.csv")
        try:
            pd.testing.assert_frame_equal(old, new[old.columns], check_exact=True)
            pd.testing.assert_frame_equal(pd.read_parquet(R1 / f"{prefix}_equity.parquet"), pd.read_parquet(directory / "equity.parquet"), check_exact=True)
            old_stops = pd.read_csv(R1 / f"{prefix}_stops.csv")
            pd.testing.assert_frame_equal(old_stops, pd.read_csv(directory / "stops.csv")[old_stops.columns], check_exact=True)
            equal = True
        except AssertionError as exc:
            equal = False
            failures.append({"check": "saved_full_baseline_exact", "detail": str(exc)})
        check(f"saved_full_baseline_exact:{anchor.reverse}", equal)

run_directories = sorted((ROOT / "runs").glob("*/*")) + sorted((ROOT / "sensitivity").glob("*/*"))
check("100_saved_run_directories", len(run_directories) == 100)
supplement_hashes = json.loads((SUPPLEMENT / "artifact_checksums.json").read_text())
supplement_manifest = json.loads((SUPPLEMENT / "run_manifest.json").read_text())
supplement_grid = pd.read_csv(SUPPLEMENT / "sensitivity.csv")
for name, expected in supplement_hashes.items():
    check(f"supplement_checksum:{name}", digest(SUPPLEMENT / name) == expected)
check("supplement_discloses_post_result_timing", supplement_manifest["timing"].startswith("POST_RESULT_DIAGNOSTIC"))
check("supplement_preserves_primary_result_pin", supplement_manifest["r2_artifact_checksums_sha256"] == digest(ROOT / "artifact_checksums.json"))
check("supplement_engine_pin", supplement_manifest["engine_sha256"] == digest(BASE / "scripts/engine_r2.py"))
check("supplement_script_pin", supplement_manifest["script_sha256"] == digest(BASE / "scripts/r2_post_result_stress.py"))
check("supplement_exactly_eight_rows", len(supplement_grid) == 8 and {
    (bool(x.reverse), x.scenario) for x in supplement_grid.itertuples()
} == set(itertools.product([False, True], supplement_manifest["scenarios"])))
supplement_directories = sorted(SUPPLEMENT.glob("s0.05*/*"))
check("eight_supplement_saved_run_directories", len(supplement_directories) == 8)
run_directories += supplement_directories
totals = {"runs": 0, "trade_records": 0, "stop_records": 0, "equity_marks": 0, "funding_records": 0}
supplement_totals = dict(totals)
for directory in run_directories:
    is_supplement = directory.is_relative_to(SUPPLEMENT)
    label = "supplement/" + str(directory.relative_to(SUPPLEMENT)) if is_supplement else str(directory.relative_to(ROOT))
    summary = json.loads((directory / "summary.json").read_text())
    trades = pd.read_csv(directory / "trades.csv")
    stops = pd.read_csv(directory / "stops.csv")
    equity = pd.read_parquet(directory / "equity.parquet")
    funding = pd.read_csv(directory / "funding.csv") if (directory / "funding.csv").exists() else pd.DataFrame()
    for column in ["entry_time", "exit_time", "exit_interval_end", "signal_day", "cross_day"]:
        trades[column] = pd.to_datetime(trades[column], utc=True)
    for column in ["timestamp", "signal_day"]:
        stops[column] = pd.to_datetime(stops[column], utc=True)
    if len(funding):
        funding["timestamp"] = pd.to_datetime(funding.timestamp, utc=True, format="mixed")
    lo, hi = pd.Timestamp(summary["start"]), pd.Timestamp(summary["end_exclusive"])
    totals["runs"] += 1
    totals["trade_records"] += len(trades)
    totals["stop_records"] += len(stops)
    totals["equity_marks"] += len(equity)
    totals["funding_records"] += len(funding)
    if is_supplement:
        for key, number in zip(supplement_totals, [1, len(trades), len(stops), len(equity), len(funding)]):
            supplement_totals[key] += number
    check(f"{label}:trade_count", len(trades) == summary["trades"])
    check(f"{label}:trade_window", ((trades.entry_time >= lo) & (trades.entry_time < hi)
          & (trades.exit_time >= trades.entry_time) & (trades.exit_interval_end >= trades.exit_time)
          & (trades.exit_interval_end <= hi)).all())
    check(f"{label}:nonoverlapping_positions", (trades.entry_time.iloc[1:].reset_index(drop=True)
          >= trades.exit_interval_end.iloc[:-1].reset_index(drop=True)).all())
    check(f"{label}:equity_window", equity.timestamp.min() >= lo and equity.timestamp.max() == hi
          and equity.timestamp.is_monotonic_increasing)
    check(f"{label}:closed_day_stop_timing", (stops.signal_day + pd.Timedelta(days=1) <= stops.timestamp).all())
    check(f"{label}:stop_never_widens", (stops.side * (stops.new_stop - stops.old_stop) >= -1e-10).all())
    check(f"{label}:multiplier_bounds_and_step", ((stops.new_mult >= 0.5) & (stops.old_mult <= 1.5)
          & (stops.new_mult <= stops.old_mult)).all()
          and np.isin(np.round(stops.old_mult - stops.new_mult, 10), [0.0, 0.2]).all())
    close(f"{label}:trade_gross", trades.gross_pnl,
          trades.side * trades.qty * (trades.exit_price - trades.entry_price), maximum_key="trade_net_error")
    close(f"{label}:trade_net", trades.net_pnl,
          trades.gross_pnl - trades.entry_fee - trades.exit_fee - trades.funding_paid - trades.carry_paid,
          maximum_key="trade_net_error")
    close(f"{label}:entry_fill", trades.entry_price, trades.entry_reference * (1 + trades.side * summary["slip"]))
    close(f"{label}:exit_fill", trades.exit_price, trades.exit_reference * (1 - trades.side * summary["slip"]))
    close(f"{label}:entry_fee", trades.entry_fee, trades.qty * trades.entry_price * summary["fee"])
    close(f"{label}:exit_fee", trades.exit_fee, trades.qty * trades.exit_price * summary["fee"])
    close(f"{label}:quantity", trades.qty, trades.entry_equity / (trades.entry_price * (1 + summary["fee"])))
    close(f"{label}:entry_cash_chain", trades.entry_equity, np.r_[10000.0, trades.end_equity.iloc[:-1]])
    close(f"{label}:trade_cash_chain", trades.end_equity, 10000.0 + trades.net_pnl.cumsum(), maximum_key="account_error")
    close(f"{label}:trade_return", trades.return_on_entry_equity, trades.net_pnl / trades.entry_equity)
    close(f"{label}:final_cash", [equity.equity.iloc[-1], 10000.0 + trades.net_pnl.sum()], summary["ending_equity"], maximum_key="account_error")
    close(f"{label}:summary_return", summary["return_pct"], (summary["ending_equity"] / 10000.0 - 1) * 100, maximum_key="summary_error")
    eq = equity.equity.to_numpy()
    dd = 100 * np.min(eq / np.maximum.accumulate(np.r_[10000.0, eq])[1:] - 1)
    close(f"{label}:summary_drawdown", summary["max_drawdown_pct"], dd, maximum_key="summary_error")
    close(f"{label}:summary_costs", [summary["fee_total"], summary["funding_paid"], summary["carry_paid"]],
          [trades.entry_fee.sum() + trades.exit_fee.sum(), trades.funding_paid.sum(), trades.carry_paid.sum()], maximum_key="account_error")
    close(f"{label}:funding_ledger_total", trades.funding_paid.sum(), funding.cost.sum() if len(funding) else 0.0,
          maximum_key="account_error")
    if label.startswith("runs/"):
        row = grid[(grid.name == summary["name"]) & (grid.window == directory.name)].iloc[0]
    elif not is_supplement:
        row = sensitivity[(sensitivity.reverse == summary["reverse"])
                          & (sensitivity.tighten_mode == summary["tighten_mode"])
                          & (sensitivity.scenario == directory.name)].iloc[0]
    else:
        row = supplement_grid[(supplement_grid.reverse == summary["reverse"])
                              & (supplement_grid.scenario == directory.name)].iloc[0]
    close(f"{label}:aggregate_matches_saved_run", row[economics], [summary[k] for k in economics], maximum_key="summary_error")
    for trade in trades.itertuples():
        tag = f"{label}:trade{trade.trade_id}"
        updates = stops[stops.trade_id == trade.trade_id]
        first = updates.iloc[0]
        check(f"{tag}:reset", first.timestamp == trade.entry_time and first.new_mult == 1.5
              and first.old_mult == 1.5 and not first.old_armed and not first.new_armed
              and trade.initial_stop_mult == 1.5 and first.tightening_trigger == "entry")
        check(f"{tag}:stop_time_within_position", ((updates.timestamp >= trade.entry_time) & (updates.timestamp <= trade.exit_time)).all())
        close(f"{tag}:stop_chain", updates.old_stop.iloc[1:], updates.new_stop.iloc[:-1])
        close(f"{tag}:multiplier_chain", updates.old_mult.iloc[1:], updates.new_mult.iloc[:-1])
        close(f"{tag}:final_state", [trade.stop, trade.stop_mult, trade.tightening_days],
              [updates.new_stop.iloc[-1], updates.new_mult.iloc[-1], updates.tightened.sum()])
        signal = daily.loc[trade.signal_day]
        close(f"{tag}:initial_atr", trade.entry_atr, signal.atr)
        check(f"{tag}:signal_known_at_entry", trade.signal_day + pd.Timedelta(days=1) <= trade.entry_time)
        if trade.entry_reason == "daily_cross":
            check(f"{tag}:fresh_cross_and_delay", signal.cross == trade.side
                  and trade.entry_time == trade.signal_day + pd.Timedelta(days=1, hours=summary["delay_hours"]))
        step = signal.ma_step
        previous_step = signal.prev_ma_step
        reason = None
        if trade.side * signal.slope > summary["slope"]:
            reason = "original"
        elif summary["entry_mode"] == "no_slope":
            reason = "no_slope"
        elif summary["entry_mode"] == "opposite_slowdown" and trade.side * previous_step < 0 and trade.side * (step - previous_step) > 0:
            reason = "opposite_slowdown"
        elif summary["entry_mode"] == "absolute_slowdown" and abs(step) < abs(previous_step):
            reason = "absolute_slowdown"
        check(f"{tag}:independent_entry_qualification", reason is not None and reason == trade.qualification)
        if len(funding):
            events = funding[funding.trade_id == trade.trade_id]
            close(f"{tag}:funding_reconciliation", trade.funding_paid, events.cost.sum(), maximum_key="account_error")
            close(f"{tag}:funding_event_arithmetic", events.cost,
                  trade.side * trade.qty * events.mark_price_used * events.rate, maximum_key="account_error")
            check(f"{tag}:funding_time_within_position", ((events.timestamp >= trade.entry_time)
                  & (events.timestamp <= trade.exit_interval_end)).all())
        for update in updates.itertuples():
            signal = daily.loc[update.signal_day]
            candidate = signal.ma - trade.side * update.new_mult * signal.atr
            expected_stop = max(update.old_stop, candidate) if trade.side == 1 else min(update.old_stop, candidate)
            close(f"{tag}:stop_formula:{update.timestamp}", update.new_stop, expected_stop, maximum_key="stop_formula_error")
            if update.tightening_trigger == "entry":
                continue
            natural = signal.ma - trade.side * update.old_mult * signal.atr
            close(f"{tag}:natural_candidate:{update.timestamp}", update.natural_candidate, natural)
            stalled = trade.side * (natural - update.old_stop) <= 1e-12 * max(1.0, abs(update.old_stop))
            eligible = (update.expected_profit_at_close > 0 and update.favorable_move_atr >= summary["profit_trigger_atr"])
            check(f"{tag}:stall_and_profit:{update.timestamp}", stalled == update.stalled and eligible == update.profit_eligible)
            should_tighten = summary["tighten_mode"] != "fixed" and update.old_mult > 0.5 and (
                (summary["tighten_mode"] == "armed_daily" and update.old_armed) or (eligible and stalled))
            check(f"{tag}:tightening_eligibility:{update.timestamp}", should_tighten == update.tightened)
            expected_mult = max(0.5, round(update.old_mult - 0.2, 10)) if should_tighten else update.old_mult
            close(f"{tag}:multiplier_update:{update.timestamp}", update.new_mult, expected_mult)
            if summary["tighten_mode"] == "fixed":
                check(f"{tag}:fixed_multiplier:{update.timestamp}", update.new_mult == 1.5)
            close(f"{tag}:favorable_entry_atr:{update.timestamp}", update.favorable_move_atr,
                  trade.side * (signal.close - trade.entry_price) / trade.entry_atr)
            if summary["carry_paid"] == 0.0:
                prior_funding = events[events.timestamp < update.timestamp].cost.sum() if len(funding) else 0.0
                hypothetical_fill = signal.close * (1 - trade.side * summary["slip"])
                hypothetical_profit = (trade.side * trade.qty * (hypothetical_fill - trade.entry_price)
                                       - trade.entry_fee - trade.qty * hypothetical_fill * summary["fee"] - prior_funding)
                close(f"{tag}:close_profit_before_boundary_funding:{update.timestamp}",
                      update.expected_profit_at_close, hypothetical_profit, maximum_key="account_error")

comparisons = []
for reverse, entry, tighten in itertools.product([False, True], ["original", "opposite_slowdown"], ["fixed", "stall_only", "armed_daily"]):
    candidate = grid[(grid.reverse == reverse) & (grid.entry_mode == entry)
                     & (grid.tighten_mode == tighten) & (grid.profit_trigger_atr == 0)].set_index("window")
    control = grid[(grid.reverse == reverse) & (grid.entry_mode == "original")
                   & (grid.tighten_mode == "fixed")].set_index("window")
    windows = []
    for window in manifest["windows"]:
        c, b = candidate.loc[window], control.loc[window]
        windows.append({"window": window, "return_pct": c.return_pct,
                        "maximum_drawdown_magnitude_pct": -c.max_drawdown_pct,
                        "return_change_percentage_points": c.return_pct - b.return_pct,
                        "drawdown_reduction_percentage_points": c.max_drawdown_pct - b.max_drawdown_pct,
                        "return_not_worse": bool(c.return_pct >= b.return_pct - 1e-10),
                        "drawdown_not_worse": bool(c.max_drawdown_pct >= b.max_drawdown_pct - 1e-10)})
    comparisons.append({"reverse": reverse, "entry_mode": entry, "tighten_mode": tighten,
                        "all_three_windows_not_worse": all(x["return_not_worse"] and x["drawdown_not_worse"] for x in windows),
                        "windows": windows})

drawdown_explanations = []
for reverse in [False, True]:
    records = {}
    curves = {}
    for mode in ["fixed", "stall_only"]:
        directory = ROOT / "runs" / f"s0.05_rev{int(reverse)}_accel1_rsi30_original_{mode}_p0" / "full"
        e = pd.read_parquet(directory / "equity.parquet")
        curves[mode] = e
        values = e.equity.to_numpy()
        peaks = np.maximum.accumulate(np.r_[10000.0, values])[1:]
        trough_index = int(np.argmin(values / peaks - 1))
        peak_index = int(np.argmax(values[:trough_index + 1]))
        records[mode] = {"peak_time_utc": str(e.timestamp.iloc[peak_index]),
                         "peak_equity": values[peak_index], "trough_time_utc": str(e.timestamp.iloc[trough_index]),
                         "trough_equity": values[trough_index],
                         "maximum_drawdown_magnitude_pct": (1 - values[trough_index] / peaks[trough_index]) * 100}
    a = curves["fixed"][curves["fixed"].kind == "hour_close"].set_index("timestamp")
    b = curves["stall_only"][curves["stall_only"].kind == "hour_close"].set_index("timestamp")
    different = np.abs(a.equity - b.equity) > 1e-10
    first_difference = a.index[different][0]
    cutoff = pd.Timestamp(records["fixed"]["trough_time_utc"])
    before_a = curves["fixed"][curves["fixed"].timestamp <= cutoff]
    before_b = curves["stall_only"][curves["stall_only"].timestamp <= cutoff]
    check(f"maximum_drawdown_path_identical_before_trough:{reverse}", before_a.equals(before_b))
    directory = ROOT / "runs" / f"s0.05_rev{int(reverse)}_accel1_rsi30_original_stall_only_p0" / "full"
    updates = pd.read_csv(directory / "stops.csv")
    first_tightening = updates[updates.tightened].iloc[0]
    drawdown_explanations.append({"reverse": reverse, **records,
        "first_different_hour_close_equity_utc": str(first_difference),
        "first_multiplier_reduction_utc": first_tightening.timestamp,
        "actual_stop_at_first_multiplier_reduction": first_tightening.new_stop,
        "actual_stop_changed_at_first_multiplier_reduction": bool(first_tightening.old_stop != first_tightening.new_stop),
        "explanation": "Both saved equity paths are identical through their maximum drawdown trough. The first multiplier reduction did not change the actual stop. The first altered exit happened later, at 2025-12-29 01:00 UTC."})

result = {
    "audit_status": "PASS" if not failures else "FAIL",
    "method": "Independent arithmetic and temporal checks over saved files only; no backtest replay or parameter selection.",
    "source_artifact_checksum_manifest_sha256": digest(ROOT / "artifact_checksums.json"),
    "audit_script_sha256": digest(Path(__file__)),
    "primary_result_rows": len(grid), "configurations": len(expected_configs),
    "sensitivity_rows": len(sensitivity), "baseline_reproductions": len(reproduction),
    "hashed_files_checked": len(hashes), "totals": totals,
    "original_and_prespecified_scope_totals": {key: totals[key] - supplement_totals[key] for key in totals},
    "post_result_supplement": {"rows": len(supplement_grid), "hashed_files_checked": len(supplement_hashes),
                               "totals": supplement_totals, "timing": supplement_manifest["timing"],
                               "results": supplement_grid[["reverse", "scenario", "return_pct", "max_drawdown_pct"]].to_dict("records")},
    "checks_performed": len(checks), "failed_checks": failures,
    "maximum_observed_absolute_errors": maximum,
    "baseline_reproduction_scope": "Six saved aggregate baselines independently compared to frozen R1, plus two full-window trade/equity/stop tables exact. Split-window trade-by-trade replay evidence is the pinned original reproduction record and was not replayed by this audit.",
    "comparisons_against_corresponding_original_fixed": comparisons,
    "unchanged_maximum_drawdown_explanations": drawdown_explanations,
    "limitations": [
        "Repeated historical diagnostic data; improvements are not fresh out-of-sample validation.",
        "Primary results omit funding; observed-funding sensitivity is not a verified complete funding calendar.",
        "Only original entries plus stall_only met the non-worsening return/drawdown check in every window for both reversal settings; full-window maximum drawdown stayed equal, not lower.",
        "Prespecified sensitivities cover the two combined opposite_slowdown variants. Original plus stall_only has eight separately disclosed post-result sensitivity checks, not prespecified validation.",
        "Closed-day profit snapshots were independently reconstructed for all runs without adverse carry. Carry scenarios have complete final trade/cash reconciliation and eligibility arithmetic checks, but the hourly carry accrual was not regenerated.",
    ],
}
OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
print(json.dumps({k: result[k] for k in ["audit_status", "totals", "checks_performed", "failed_checks", "maximum_observed_absolute_errors"]}, indent=2))
