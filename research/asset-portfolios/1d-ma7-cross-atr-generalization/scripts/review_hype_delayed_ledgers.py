"""Explain two completed HYPE paths using only saved ledgers; never simulate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
RESULTS = FAMILY / "artifacts/results_20260909"
OUT = FAMILY / "artifacts/hype_delay_ledger_review_20260909"
CASES = ("H4_D0", "H4_D3")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        handle.write("\n")


def load_ledgers():
    data, hashes = {}, {}
    for case in CASES:
        root = f"runs/HYPE/{case}/full"
        for name in ("trades.csv", "summary.json", "equity.parquet"):
            hashes[f"{root}/{name}"] = sha(RESULTS / root / name)
        trades = pd.read_csv(RESULTS / root / "trades.csv")
        for name in ("cross_day", "signal_day", "entry_time", "exit_time"):
            trades[name] = pd.to_datetime(trades[name], utc=True)
        data[case] = {"trades": trades,
                      "summary": json.loads((RESULTS / root / "summary.json").read_text()),
                      "equity": pd.read_parquet(RESULTS / root / "equity.parquet")}
    return data, hashes


def trade(row):
    return {"trade_id": int(row.trade_id), "side": int(row.side),
            "cross_day": row.cross_day, "signal_day": row.signal_day,
            "entry_time": row.entry_time, "exit_time": row.exit_time,
            "entry_price": float(row.entry_price), "exit_price": float(row.exit_price),
            "entry_wait_days_used": int(row.entry_wait_days_used),
            "entry_reason": row.entry_reason, "exit_reason": row.exit_reason,
            "entry_equity": float(row.entry_equity), "end_equity": float(row.end_equity),
            "net_pnl": float(row.net_pnl), "return_on_entry_equity_pct": float(row.return_on_entry_equity * 100)}


def drawdown_record(curve):
    values = curve.equity.to_numpy(float)
    dd = values / np.maximum.accumulate(values) - 1
    trough = int(dd.argmin())
    peak = int(values[:trough+1].argmax())
    return {"max_drawdown_pct": float(dd[trough] * 100),
            "peak": curve.iloc[peak].to_dict(), "trough": curve.iloc[trough].to_dict()}


def block(frame, ids):
    subset = frame[frame.trade_id.isin(ids)]
    assert subset.trade_id.tolist() == ids
    chained = float((np.prod(1 + subset.return_on_entry_equity) - 1) * 100)
    assert np.isclose(subset.end_equity.iloc[-1] / subset.entry_equity.iloc[0] - 1, chained / 100)
    return {"trade_ids": ids, "entry_time": subset.entry_time.iloc[0], "exit_time": subset.exit_time.iloc[-1],
            "entry_equity": float(subset.entry_equity.iloc[0]), "end_equity": float(subset.end_equity.iloc[-1]),
            "net_pnl_sum": float(subset.net_pnl.sum()), "account_change_pct_over_this_block": chained,
            "trades": [trade(row) for row in subset.itertuples(index=False)]}


def review():
    if OUT.exists():
        raise FileExistsError(OUT)
    data, hashes = load_ledgers()
    baseline, extended = data[CASES[0]]["trades"], data[CASES[1]]["trades"]
    delayed = extended[extended.entry_wait_days_used.gt(0)]
    side_groups = []
    for side, rows in delayed.groupby("side"):
        side_groups.append({"side": int(side), "trades": len(rows), "wins": int(rows.net_pnl.gt(0).sum()),
                            "losses": int(rows.net_pnl.lt(0).sum()), "net_pnl_sum": float(rows.net_pnl.sum())})
    same_paths, displaced = [], []
    for row in baseline.itertuples(index=False):
        same = extended[extended.entry_time.eq(row.entry_time) & extended.side.eq(row.side)]
        if len(same):
            assert len(same) == 1
            other = next(same.itertuples(index=False))
            assert row.entry_price == other.entry_price and row.exit_price == other.exit_price
            assert row.exit_time == other.exit_time and row.exit_reason == other.exit_reason
            assert np.isclose(row.return_on_entry_equity, other.return_on_entry_equity, atol=1e-14, rtol=0)
            same_paths.append({"baseline_trade_id": row.trade_id, "extended_trade_id": other.trade_id,
                               "entry_time": row.entry_time, "price_path_and_normalized_return_unchanged": True,
                               "dollar_pnl_can_differ_due_to_entry_equity": True})
            continue
        blockers = extended[extended.entry_time.le(row.entry_time) & extended.exit_time.ge(row.entry_time)]
        assert len(blockers) == 1
        occupied = next(blockers.itertuples(index=False))
        reason = ("existing_position_exits_at_same_execution_timestamp_no_reentry" if occupied.exit_time == row.entry_time
                  else "same_direction_position_already_open" if occupied.side == row.side
                  else "opposite_direction_position_already_open")
        displaced.append({"baseline_trade": trade(row), "blocking_extended_trade": trade(occupied), "reason": reason})
    first_loss_block = block(extended, [17, 18, 19, 20])
    second_loss_block = block(extended, [22, 23])
    final_extended = block(extended, [26, 27])
    final_baseline = block(baseline, [17])
    # Both accounts were flat before August 6. These are observed cash changes,
    # not a new run or hypothetical deletion of earlier trades.
    final_window = {"start": "2026-08-06T00:00:00Z", "end": "2026-09-05T00:00:00Z",
                    "both_accounts_flat_immediately_before_start": True,
                    "baseline": final_baseline, "extended": final_extended}
    comparison = {case: {key: data[case]["summary"][key] for key in (
        "return_pct", "ending_equity", "max_drawdown_pct", "trades", "win_rate_pct", "fee_total",
        "long_trades", "long_pnl", "short_trades", "short_pnl", "delayed_entries")}
        for case in CASES}
    report = {
        "status": "SAVED_LEDGER_COMPARISON_WITH_PINNED_SOURCE_SNAPSHOTS",
        "new_simulations": 0, "source_files_sha256": hashes, "script_sha256": sha(Path(__file__)),
        "scope": {"symbol": "HYPE/USDT:USDT", "start": "2025-06-29T00:00:00Z", "end": "2026-09-05T00:00:00Z",
                  "initial_equity": 10000, "fee_each_side": .0005, "slippage_each_side": .0003,
                  "funding_included": False, "entry_wait_days_only_change": [0, 3]},
        "comparison": comparison,
        "extended_minus_baseline_end_equity": comparison["H4_D3"]["ending_equity"] - comparison["H4_D0"]["ending_equity"],
        "delayed_trades": {"count": len(delayed), "wins": int(delayed.net_pnl.gt(0).sum()),
                           "losses": int(delayed.net_pnl.lt(0).sum()), "net_pnl_sum": float(delayed.net_pnl.sum()),
                           "by_side": side_groups, "rows": [trade(row) for row in delayed.itertuples(index=False)]},
        "same_entry_paths": same_paths, "displaced_baseline_entries": displaced,
        "consecutive_loss_blocks": [first_loss_block, second_loss_block],
        "saved_curve_drawdowns": {case: drawdown_record(data[case]["equity"]) for case in CASES},
        "late_period_observed_account_comparison": final_window,
        "interpretation_limits": [
            "Dollar PnL grouped by delayed entries is an observed ledger subtotal, not a causal decomposition of the strategy equity difference.",
            "Changed entry timing also changes occupied periods, stop timing, later raw-cross opportunities and the equity available for future identical paths.",
            "Seven baseline entries were not executed at the same timestamp; five already had the same direction, one the opposite direction and one exited an earlier position at that timestamp. These are not all lost profitable opportunities.",
            "The April-May four-loss block accounts for a 29.13 percent cash decline; maximum drawdown also includes preceding unrealized-profit giveback and the next long position's initial adverse move.",
            "The final August cash-change comparison uses a common interval in which both accounts begin flat; no earlier trades have been removed or resimulated.",
        ],
        "final_global_checksums_receipt": "results_checksum_validation.json",
    }
    save(OUT / "review.json", report)
    print(json.dumps({"delayed": report["delayed_trades"]["count"], "same_paths": len(same_paths),
                      "displaced": len(displaced), "loss_blocks_pct": [first_loss_block["account_change_pct_over_this_block"], second_loss_block["account_change_pct_over_this_block"]]}, indent=2))


def confirm_global_checksums():
    report = json.loads((OUT / "review.json").read_text())
    completion = json.loads((RESULTS / "completion.json").read_text())
    assert completion["complete"] is True and completion["coins_failed"] == 0
    path = RESULTS / "artifact_checksums.json"
    checksums = json.loads(path.read_text())
    assert checksums["completion.json"] == sha(RESULTS / "completion.json")
    for relative, expected in report["source_files_sha256"].items():
        assert checksums[relative] == expected == sha(RESULTS / relative), relative
    save(OUT / "results_checksum_validation.json", {
        "status": "PASS", "verified_source_files": len(report["source_files_sha256"]),
        "results_artifact_checksums_sha256": sha(path), "review_sha256": sha(OUT / "review.json"),
        "completed_coins": completion["coins_completed"], "new_simulations": 0})
    print("FINAL_GLOBAL_SOURCE_HASHES_PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-results", action="store_true")
    args = parser.parse_args()
    confirm_global_checksums() if args.confirm_results else review()
