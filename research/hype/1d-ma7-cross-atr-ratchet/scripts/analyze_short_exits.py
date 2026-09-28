"""Paired, fixed-quantity diagnostic of the primary short take-profit exits.

This does not rerun portfolio allocation or alter the frozen strategy. Each
observed early exit is compared with independently carrying that same short
until its existing ratcheting MA7 + 1.5 ATR14 stop or the sample endpoint.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
import math
from pathlib import Path

import pandas as pd

from run_study import BASE, INPUT, OUT, digest, load_inputs, write_json


def close_enough(a, b, label, absolute=1e-8):
    if not math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=absolute):
        raise AssertionError(f"{label}: {a} != {b}")


def source_pins(allow_drift=False):
    manifest = json.loads((OUT / "run_manifest.json").read_text())
    files = {
        "engine_sha256": BASE / "scripts/engine.py",
        "run_script_sha256": BASE / "scripts/run_study.py",
        "contract_sha256": BASE / "specs/contract-20260909.md",
        "input_checksums_file_sha256": INPUT / "checksums.json",
    }
    observed = {name: digest(path) for name, path in files.items()}
    mismatch = {key: {"original_run": manifest[key], "current": value}
                for key, value in observed.items() if manifest[key] != value}
    if mismatch and not allow_drift:
        raise ValueError(f"Parent run source changed; complete its rerun first: {mismatch}")
    artifact_checksum_path = OUT / "artifact_checksums.json"
    if not allow_drift:
        artifact_checksums = json.loads(artifact_checksum_path.read_text())
        for filename in ["primary_trades.csv", "primary_stops.csv", "run_manifest.json"]:
            if artifact_checksums[filename] != digest(OUT / filename):
                raise ValueError(f"Parent artifact differs from its recorded checksum: {filename}")
    return manifest, {
        "parent_run_manifest_sha256": digest(OUT / "run_manifest.json"),
        "parent_primary_trades_sha256": digest(OUT / "primary_trades.csv"),
        "parent_primary_stops_sha256": digest(OUT / "primary_stops.csv"),
        "analysis_script_sha256": digest(Path(__file__)),
        "parent_artifact_checksums_sha256": digest(artifact_checksum_path),
        "current_parent_sources": observed,
        "parent_source_mismatches": mismatch,
        "input_access": "run_study.load_inputs; only this family's pinned input copies",
    }


def verify_trade_stop_history(trade, stops, daily_map):
    history = stops[stops.trade_id == trade.trade_id].sort_values("timestamp")
    if history.empty or history.timestamp.iloc[0] != trade.entry_time:
        raise AssertionError("Missing original entry stop")
    previous = None
    for record in history.itertuples(index=False):
        if record.timestamp > trade.exit_time or record.side != -1:
            raise AssertionError("Invalid stop history for primary short")
        signal = daily_map[record.timestamp.floor("D") - pd.Timedelta(days=1)]
        proposal = float(signal.ma + 1.5 * signal.atr)
        if previous is None:
            expected = proposal
            close_enough(record.old_stop, expected, "Entry old stop")
        else:
            close_enough(record.old_stop, previous, "Historical old stop")
            expected = min(previous, proposal)
        close_enough(record.new_stop, expected, "Historical ratchet")
        previous = expected
    close_enough(previous, trade.stop, "Stop recorded at actual RSI exit")
    return previous, len(history)


def analyze_trade(trade, h, daily_map, stops, config, end):
    if trade.side != -1 or trade.funding_paid != 0 or trade.carry_paid != 0:
        raise AssertionError("Expected a price-only primary short with zero booked carry")
    fee, slip = config["fee"], config["slip"]
    stop, stop_records_checked = verify_trade_stop_history(trade, stops, daily_map)
    initial_stop = stop
    remaining = h[(h.timestamp >= trade.exit_time) & (h.timestamp < end)]
    if remaining.empty or remaining.timestamp.iloc[0] != trade.exit_time:
        raise AssertionError("Actual exit hour missing from pinned execution data")
    close_enough(remaining.iloc[0].open, trade.exit_reference, "Actual exit open")
    close_enough(trade.exit_reference * (1 + slip), trade.exit_price, "Actual exit fill")
    actual_pnl = trade.qty * (trade.entry_price - trade.exit_price) - trade.entry_fee - trade.qty * trade.exit_price * fee
    close_enough(actual_pnl, trade.net_pnl, "Actual trade PnL reconstruction")

    # Complete surviving hours give a known low before the stop. For a stop
    # triggered inside its last hour, that hour's low may occur after the exit;
    # retain separate lower/upper excursion bounds rather than inventing order.
    known_low = float(trade.exit_reference)
    terminal_low_included = known_low
    ratchet_updates = 0
    terminal_hour_order_unknown = False
    cf_reason, cf_time, cf_interval_end, cf_reference = None, None, None, None
    for bar in remaining.itertuples(index=False):
        if bar.timestamp.hour == 0:
            row = daily_map[bar.timestamp.floor("D") - pd.Timedelta(days=1)]
            proposed = float(row.ma + 1.5 * row.atr)
            next_stop = min(stop, proposed)
            if next_stop > stop + 1e-12:
                raise AssertionError("Counterfactual short stop widened")
            ratchet_updates += next_stop < stop
            stop = next_stop
        if float(bar.open) >= stop:
            cf_reason = "stop_gap"
            cf_time = cf_interval_end = bar.timestamp
            cf_reference = float(bar.open)
            terminal_low_included = known_low
            break
        known_low = min(known_low, float(bar.open))
        if float(bar.high) >= stop:
            cf_reason = "stop_intrahour"
            cf_time = bar.timestamp
            cf_interval_end = bar.timestamp + pd.Timedelta(hours=1)
            cf_reference = stop
            terminal_low_included = min(known_low, float(bar.low))
            terminal_hour_order_unknown = float(bar.low) < known_low
            break
        known_low = min(known_low, float(bar.low))
        terminal_low_included = known_low
    if cf_reason is None:
        cf_reason = "sample_end"
        cf_time = cf_interval_end = end
        cf_reference = float(remaining.iloc[-1].close)
    cf_fill = cf_reference * (1 + slip)
    cf_fee = trade.qty * cf_fill * fee
    cf_pnl = trade.qty * (trade.entry_price - cf_fill) - trade.entry_fee - cf_fee
    difference = actual_pnl - cf_pnl
    close_enough(difference, trade.qty * (cf_fill - trade.exit_price) * (1 + fee), "Paired exit-only identity")
    return {
        "trade_id": int(trade.trade_id),
        "entry_time": trade.entry_time,
        "entry_price": trade.entry_price,
        "qty_unchanged": trade.qty,
        "entry_equity": trade.entry_equity,
        "entry_fee_unchanged": trade.entry_fee,
        "actual_exit_time": trade.exit_time,
        "actual_exit_reference": trade.exit_reference,
        "actual_exit_fill": trade.exit_price,
        "actual_exit_fee": trade.exit_fee,
        "actual_net_pnl_excluding_funding": actual_pnl,
        "rsi6_signal": trade.tp_signal_rsi,
        "stop_at_actual_exit": initial_stop,
        "counterfactual_exit_time": cf_time,
        "counterfactual_exit_interval_end": cf_interval_end,
        "counterfactual_exit_reason": cf_reason,
        "counterfactual_exit_reference": cf_reference,
        "counterfactual_exit_fill": cf_fill,
        "counterfactual_exit_fee": cf_fee,
        "counterfactual_net_pnl_excluding_funding": cf_pnl,
        "early_exit_minus_continuation_pnl": difference,
        "early_exit_advantage_pct_entry_equity": difference / trade.entry_equity * 100,
        "continuation_hours_min": (cf_time - trade.exit_time).total_seconds() / 3600,
        "continuation_hours_max": (cf_interval_end - trade.exit_time).total_seconds() / 3600,
        "known_low_before_counterfactual_exit": known_low,
        "low_including_ambiguous_terminal_hour": terminal_low_included,
        "max_further_decline_pct_lower_bound": max(0.0, (1 - known_low / trade.exit_reference) * 100),
        "max_further_decline_pct_upper_bound": max(0.0, (1 - terminal_low_included / trade.exit_reference) * 100),
        "terminal_hour_low_order_unknown": terminal_hour_order_unknown,
        "historical_stop_records_verified": stop_records_checked,
        "counterfactual_strict_stop_tightenings": ratchet_updates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print validation only; permit a parent rerun in progress")
    args = parser.parse_args()
    manifest, pins = source_pins(allow_drift=args.dry_run)
    h, d, _unused_funding = load_inputs()
    h["timestamp"] = pd.to_datetime(h.timestamp, utc=True)
    if h.timestamp.duplicated().any() or not h.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all():
        raise AssertionError("Execution input is not a continuous hourly grid")
    daily_map = {row.timestamp: row for row in d.itertuples(index=False)}
    trades = pd.read_csv(OUT / "primary_trades.csv")
    for column in ["entry_time", "exit_time"]:
        trades[column] = pd.to_datetime(trades[column], utc=True)
    stops = pd.read_csv(OUT / "primary_stops.csv")
    stops["timestamp"] = pd.to_datetime(stops.timestamp, utc=True)
    selected = trades[trades.exit_reason == "accel1_rsi30"]
    if len(selected) != 6:
        raise AssertionError(f"Expected the 6 recorded primary early exits, got {len(selected)}")
    end = pd.Timestamp(manifest["end"])
    config = manifest["primary"]
    results = pd.DataFrame([analyze_trade(t, h, daily_map, stops, config, end)
                            for t in selected.itertuples(index=False)])
    first = results.iloc[0]
    # One independent decimal hand calculation verifies both transaction fee
    # direction and the matched-quantity difference without the simulator.
    manual = (Decimal(str(first.qty_unchanged))
              * (Decimal(str(first.counterfactual_exit_fill)) - Decimal(str(first.actual_exit_fill)))
              * (1 + Decimal(str(config["fee"]))))
    close_enough(float(manual), first.early_exit_minus_continuation_pnl, "Decimal hand check")
    overlap_pairs = []
    records = results.to_dict("records")
    for index, left in enumerate(records):
        for right in records[index + 1:]:
            if max(left["actual_exit_time"], right["actual_exit_time"]) < min(left["counterfactual_exit_interval_end"], right["counterfactual_exit_interval_end"]):
                overlap_pairs.append([left["trade_id"], right["trade_id"]])
    summary = {
        "family": "HYPE-1D-MA7-CAR",
        "classification": "POST_RUN_EXIT_MECHANISM_DIAGNOSTIC",
        "created_at_utc": pd.Timestamp.now(tz="UTC"),
        "sample_end_exclusive": end,
        "source_pins": pins,
        "method": "Each recorded early exit independently retains its original entry and quantity; only the original ratcheting MA7+1.5ATR14 stop remains active. No new entries, reversals, or reinvestment.",
        "costs": {"fee_each_fill": config["fee"], "slippage_each_fill": config["slip"], "funding_included": False},
        "excursion_method": "Lower bound uses actual exit open and completed surviving hours; upper bound additionally includes a terminal intrahour-stop bar low whose order against the stop is unknown.",
        "observations": len(results),
        "early_exit_better": int((results.early_exit_minus_continuation_pnl > 0).sum()),
        "continuation_better": int((results.early_exit_minus_continuation_pnl < 0).sum()),
        "actual_net_pnl_sum_excluding_funding": float(results.actual_net_pnl_excluding_funding.sum()),
        "counterfactual_net_pnl_sum_excluding_funding": float(results.counterfactual_net_pnl_excluding_funding.sum()),
        "paired_difference_sum": float(results.early_exit_minus_continuation_pnl.sum()),
        "median_advantage_pct_entry_equity": float(results.early_exit_advantage_pct_entry_equity.median()),
        "aggregate_is_portfolio_return": False,
        "overlapping_counterfactual_trade_id_pairs": overlap_pairs,
        "interpretation": "Sums describe these six actual-sized matched positions only. They do not equal the return difference between full strategy variants, which also change later entries, reversals, quantities and compounding. Six outcome-reused trades do not establish stable out-of-sample effectiveness.",
        "manual_check": {"trade_id": int(first.trade_id), "formula": "qty * (continuation_buyback_fill - actual_buyback_fill) * (1 + exit_fee_rate)", "decimal_result": str(manual), "observed_difference": float(first.early_exit_minus_continuation_pnl), "passed": True},
    }
    if not args.dry_run:
        # Fail if parent artifacts/source changed while this diagnostic ran.
        _, final_pins = source_pins()
        if pins != final_pins:
            raise AssertionError("Parent artifacts changed during analysis")
        results.to_csv(OUT / "short_exit_counterfactual.csv", index=False)
        summary["counterfactual_csv_sha256"] = digest(OUT / "short_exit_counterfactual.csv")
        write_json(OUT / "short_exit_counterfactual.json", summary)
    print(results[["trade_id", "actual_exit_time", "counterfactual_exit_time", "actual_net_pnl_excluding_funding", "counterfactual_net_pnl_excluding_funding", "early_exit_minus_continuation_pnl", "max_further_decline_pct_lower_bound", "max_further_decline_pct_upper_bound"]].to_string(index=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str, allow_nan=False))


if __name__ == "__main__":
    main()
