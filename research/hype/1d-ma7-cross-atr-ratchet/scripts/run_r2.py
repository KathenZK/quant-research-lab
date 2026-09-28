"""Finite R2 comparison with exact R1 controls and a new output directory."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import itertools
import json
from pathlib import Path

import pandas as pd

import engine as r1
import engine_r2 as r2
from run_study import BASE, INPUT, load_inputs

CONTRACT = BASE / "specs/r2-slowdown-tightening-20260909.md"
PARENT = BASE / "artifacts/results_20260909"
DEFAULT_OUT = BASE / "artifacts/r2_slowdown_tightening_20260909"
WINDOWS = {
    "full": ("2025-06-29T00:00:00Z", "2026-09-05T00:00:00Z"),
    "early60": ("2025-06-29T00:00:00Z", "2026-03-15T00:00:00Z"),
    "late40": ("2026-03-15T00:00:00Z", "2026-09-05T00:00:00Z"),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str, allow_nan=False) + "\n")


def load_r2_inputs():
    manifest = json.loads((PARENT / "run_manifest.json").read_text())
    for key, path in {"engine_sha256": BASE / "scripts/engine.py", "run_script_sha256": BASE / "scripts/run_study.py",
                      "contract_sha256": BASE / "specs/contract-20260909.md"}.items():
        if sha(path) != manifest[key]:
            raise ValueError(f"Frozen R1 source mismatch: {key}")
    hashes = json.loads((PARENT / "artifact_checksums.json").read_text())
    for name, expected in hashes.items():
        if sha(PARENT / name) != expected:
            raise ValueError(f"Frozen R1 output mismatch: {name}")
    h, d, f = load_inputs()
    return h, r2.enrich_features(d), f


def configuration_list():
    cases = [r2.Config(entry_mode=entry, tighten_mode=tighten, reverse=reverse)
             for entry, tighten, reverse in itertools.product(
                 ["original", "opposite_slowdown", "absolute_slowdown", "no_slope"],
                 ["fixed", "stall_only", "armed_daily"], [False, True])]
    cases += [r2.Config(entry_mode="opposite_slowdown", tighten_mode=tighten, reverse=reverse, profit_trigger_atr=1.0)
              for tighten, reverse in itertools.product(["stall_only", "armed_daily"], [False, True])]
    assert len(cases) == 28 and len({c.name for c in cases}) == 28
    return cases


def save_result(directory, result):
    directory.mkdir(parents=True, exist_ok=False)
    summary, trades, equity, stops, funding = result
    write_json(directory / "summary.json", summary)
    trades.to_csv(directory / "trades.csv", index=False)
    equity.to_parquet(directory / "equity.parquet", index=False)
    stops.to_csv(directory / "stops.csv", index=False)
    if len(funding):
        funding.to_csv(directory / "funding.csv", index=False)


def verify_anchor(a, b):
    keys = ["return_pct", "ending_equity", "max_drawdown_pct", "adverse_hour_check_pct", "annualized_return_pct",
            "trades", "win_rate_pct", "profit_factor", "exposure_pct", "fee_total", "funding_paid", "carry_paid",
            "reversal_entries", "short_tp_exits", "long_trades", "long_pnl", "long_wins", "short_trades", "short_pnl", "short_wins"]
    for key in keys:
        if a[0][key] != b[0][key]:
            raise AssertionError(f"R1 exact control mismatch: {key}: {a[0][key]} != {b[0][key]}")
    old_trades, new_trades = a[1], b[1]
    pd.testing.assert_frame_equal(old_trades.reset_index(drop=True), new_trades[old_trades.columns].reset_index(drop=True), check_exact=True)
    pd.testing.assert_frame_equal(a[2], b[2], check_exact=True)
    pd.testing.assert_frame_equal(a[3], b[3][a[3].columns], check_exact=True)


def opportunity_inventory(d):
    rows = []
    for signal in d.itertuples():
        if not signal.ready or not signal.cross:
            continue
        row = signal._asdict()
        # An event on the final daily close cannot open within the frozen window.
        executable = signal.timestamp + pd.Timedelta(days=1) < pd.Timestamp(WINDOWS["full"][1])
        item = {"signal_day": signal.timestamp, "entry_open_day": signal.timestamp + pd.Timedelta(days=1),
                "side": int(signal.cross), "close": signal.close, "ma": signal.ma, "atr": signal.atr,
                "ma_step": signal.ma_step, "prev_ma_step": signal.prev_ma_step,
                "slope": signal.slope, "entry_open_in_window": executable}
        for mode in ["original", "opposite_slowdown", "absolute_slowdown", "no_slope"]:
            reason = r2.entry_qualification(pd.Series(row), int(signal.cross), r2.Config(entry_mode=mode))
            item[mode] = reason is not None
            item[mode + "_reason"] = reason
        rows.append(item)
    return pd.DataFrame(rows)


def exact_entry_comparison(trades, control):
    lookup = {(str(t.entry_time), int(t.side)): t for t in control.itertuples()}
    common, earlier, added = 0, 0, 0
    for t in trades.itertuples():
        previous = lookup.get((str(t.entry_time), int(t.side)))
        if previous is None:
            added += 1
        else:
            common += 1
            earlier += pd.Timestamp(t.exit_time) < pd.Timestamp(previous.exit_time)
    return {"same_entry_as_control": common, "earlier_exit_on_same_entry": int(earlier), "different_entry_events": added,
            "interpretation": "Descriptive matched entry times; downstream paths and quantities can differ, not independent causal profits"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error("Output already exists; use a new directory to preserve prior evidence")
    h, d, f = load_r2_inputs()
    cases = configuration_list()
    out.mkdir(parents=True)
    write_json(out / "run_manifest.json", {"family": "HYPE-1D-MA7-CAR", "round": "R2",
               "created_before_new_results_utc": str(pd.Timestamp.now(tz="UTC")), "contract_sha256": sha(CONTRACT),
               "engine_sha256": sha(BASE / "scripts/engine_r2.py"), "run_script_sha256": sha(Path(__file__)),
               "r1_engine_sha256": sha(BASE / "scripts/engine.py"), "r1_run_manifest_sha256": sha(PARENT / "run_manifest.json"),
               "input_checksums_sha256": sha(INPUT / "checksums.json"), "windows": WINDOWS,
               "configs": [asdict(c) for c in cases], "primary_entry": "opposite_slowdown",
               "primary_tighten": "stall_only", "classification": "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS",
               "funding_window_verified": False})
    d.to_csv(out / "daily_features.csv", index=False)
    opportunities = opportunity_inventory(d)
    opportunities.to_csv(out / "signal_opportunities.csv", index=False)
    inventory = {}
    active = opportunities[opportunities.entry_open_in_window]
    for mode in ["original", "opposite_slowdown", "absolute_slowdown", "no_slope"]:
        accepted = active[active[mode]]
        additional = accepted[~accepted.original]
        inventory[mode] = {"all_crosses": len(active), "accepted_crosses": len(accepted), "new_crosses": len(additional),
                           "accepted_long": int((accepted.side == 1).sum()), "accepted_short": int((accepted.side == -1).sum())}
    write_json(out / "opportunity_counts.json", inventory)

    anchors, anchor_results = [], {}
    frozen_grid = pd.read_csv(PARENT / "all_results.csv")
    for reverse, (window, (lo, hi)) in itertools.product([False, True], WINDOWS.items()):
        old = r1.simulate(h, d, r1.Config(reverse=reverse), pd.Timestamp(lo), pd.Timestamp(hi))
        new = r2.simulate(h, d, r2.Config(reverse=reverse, entry_mode="original", tighten_mode="fixed"), pd.Timestamp(lo), pd.Timestamp(hi))
        verify_anchor(old, new)
        saved = frozen_grid[(frozen_grid.slope == .05) & (frozen_grid.reverse == reverse) & (frozen_grid.short_exit == "accel1_rsi30") & (frozen_grid.window == window)].iloc[0]
        differences = [abs(float(new[0][key]) - float(saved[key])) for key in ["return_pct", "ending_equity", "max_drawdown_pct", "fee_total", "long_pnl", "short_pnl"]]
        assert max(differences) <= 1e-8
        anchors.append({"reverse": reverse, "window": window, "live_r1_r2_exact_equal": True,
                        "frozen_csv_max_abs_difference": max(differences), "return_pct": new[0]["return_pct"]})
        anchor_results[(reverse, window)] = new
    write_json(out / "r1_reproduction.json", anchors)
    print("R1 exact controls: 6/6 PASS", flush=True)

    rows, full = [], {}
    for c in cases:
        for window, (lo, hi) in WINDOWS.items():
            if c.entry_mode == "original" and c.tighten_mode == "fixed":
                result = anchor_results[(c.reverse, window)]
            else:
                result = r2.simulate(h, d, c, pd.Timestamp(lo), pd.Timestamp(hi))
            rows.append({"window": window, **result[0]})
            save_result(out / "runs" / c.name / window, result)
            if window == "full":
                full[c.name] = result
        print(f"completed {c.name}", flush=True)
    grid = pd.DataFrame(rows)
    grid.to_csv(out / "all_results.csv", index=False)
    primary = grid[(grid.entry_mode.isin(["original", "opposite_slowdown"])) & (grid.tighten_mode.isin(["fixed", "stall_only"])) & (grid.profit_trigger_atr == 0)]
    primary.to_csv(out / "core_comparison.csv", index=False)

    paired = []
    for c in cases:
        same_entry_control = r2.Config(entry_mode=c.entry_mode, tighten_mode="fixed", reverse=c.reverse)
        overall_control = r2.Config(entry_mode="original", tighten_mode="fixed", reverse=c.reverse)
        compared = exact_entry_comparison(full[c.name][1], full[same_entry_control.name][1])
        parent = full[overall_control.name][0]
        score = full[c.name][0]
        paired.append({"name": c.name, **asdict(c), **compared,
                       "return_delta_pp_vs_r1": score["return_pct"] - parent["return_pct"],
                       "drawdown_reduction_pp_vs_r1": score["max_drawdown_pct"] - parent["max_drawdown_pct"]})
    pd.DataFrame(paired).to_csv(out / "matched_entries.csv", index=False)

    sensitivities = []
    for reverse, tighten in itertools.product([False, True], ["stall_only", "armed_daily"]):
        c = r2.Config(entry_mode="opposite_slowdown", tighten_mode=tighten, reverse=reverse)
        for scenario, variant, funding, carry in [
            ("slippage_10bp", replace(c, slip=.001), None, 0),
            ("daily_signal_delay_1h", replace(c, delay_hours=1), None, 0),
            ("adverse_carry_5bp_day", c, None, .0005),
            ("observed_funding_unverified", c, f, 0),
        ]:
            result = r2.simulate(h, d, variant, pd.Timestamp(WINDOWS["full"][0]), pd.Timestamp(WINDOWS["full"][1]), funding, carry)
            sensitivities.append({"scenario": scenario, **result[0]})
            save_result(out / "sensitivity" / c.name / scenario, result)
    pd.DataFrame(sensitivities).to_csv(out / "sensitivity.csv", index=False)
    # Validate all new output pins after generation without changing parent evidence.
    hashes = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
    write_json(out / "artifact_checksums.json", hashes)
    print(primary[primary.window == "full"].to_json(orient="records", indent=2, force_ascii=False), flush=True)


if __name__ == "__main__":
    main()
