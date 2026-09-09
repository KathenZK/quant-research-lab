"""MTCS P2：同信号、同20日持有规则的独立连续段资金捕获诊断。"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import csv
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np
import pandas as pd

from capture import EQUITY_COLUMNS, TRADE_COLUMNS, run_hold20_account


FAMILY = Path(__file__).resolve().parents[1]
GROUPS = tuple(f"{prefix}_{side}" for prefix in ("U", "M", "S1", "S2", "S3")
               for side in ("LONG", "SHORT"))
COSTS = {"base": {"fee": 0.001, "slippage": 0.0004},
         "stress": {"fee": 0.001, "slippage": 0.0008}}
META_COLUMNS = ["symbol", "research_segment_id", "group", "cost", "account_id"]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_json(path: Path, value: Any) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite retained evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def directory_name(value: str) -> str:
    if not value or Path(value).name != value or value in (".", ".."):
        raise ValueError("Artifact directory must be a single directory name")
    return value


def load_panel(panel_dir: str) -> tuple[pd.DataFrame, dict]:
    source = FAMILY / "artifacts" / directory_name(panel_dir)
    path, manifest_path = source / "panel.pkl.gz", source / "panel-manifest.json"
    manifest_sha = sha(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = sha(path)
    if actual != manifest.get("sha256"):
        raise ValueError("Own-family panel SHA256 differs from its manifest")
    if type(manifest.get("rows")) is not int or manifest["rows"] < 1:
        raise ValueError("Panel manifest must declare a positive integer row count")
    panel = pd.read_pickle(path, compression="gzip")
    if not isinstance(panel, pd.DataFrame) or len(panel) != manifest["rows"]:
        raise ValueError("Panel type or row count differs from manifest")
    required = {"symbol", "ts", "signal_time", "open", "high", "low", "close", "volume",
                "eligible", "research_segment_id", "feature_valid", "valid20", *GROUPS}
    if not required.issubset(panel.columns):
        raise ValueError(f"Panel missing required columns: {sorted(required - set(panel.columns))}")
    if panel.symbol.isna().any() or not panel.symbol.map(lambda s: isinstance(s, str)).all():
        raise ValueError("Panel symbol identity must be explicit strings")
    for column in ("ts", "signal_time"):
        if not isinstance(panel[column].dtype, pd.DatetimeTZDtype) or panel[column].isna().any():
            raise ValueError(f"{column} must have explicit timezone-aware, nonmissing timestamps")
    if not panel.signal_time.eq(panel.ts + pd.Timedelta(days=1)).all():
        raise ValueError("Panel signals must be known at the daily close")
    if panel.duplicated(["symbol", "ts"]).any():
        raise ValueError("Panel has duplicate symbol/time rows")
    delta = panel.groupby("symbol", sort=False).ts.diff()
    if (delta.dropna() <= pd.Timedelta(0)).any():
        raise ValueError("Panel is nonmonotonic; do not sort away an input error")
    for column in ("eligible", "feature_valid", "valid20", *GROUPS):
        if not pd.api.types.is_bool_dtype(panel[column].dtype) or panel[column].isna().any():
            raise ValueError(f"{column} must be an explicit nonmissing boolean")
    if panel.loc[panel.eligible, "research_segment_id"].isna().any():
        raise ValueError("Eligible rows require a research segment identity")
    if (panel.feature_valid & ~panel.eligible).any():
        raise ValueError("Feature-valid rows cannot be ineligible")
    signal_matrix = panel.loc[:, list(GROUPS)].to_numpy(dtype=bool)
    if (signal_matrix.any(axis=1) & ~panel.feature_valid.to_numpy(dtype=bool)).any():
        raise ValueError("A selected signal lies outside the past-only feature eligibility")
    metadata = {
        "path": str(path.relative_to(FAMILY)), "sha256": actual, "rows": len(panel),
        "manifest_path": str(manifest_path.relative_to(FAMILY)), "manifest_sha256": manifest_sha,
        "symbols": int(panel.symbol.nunique()), "eligible_rows": int(panel.eligible.sum()),
        "feature_valid_rows": int(panel.feature_valid.sum()),
        "signals": {group: int(signal_matrix[:, i].sum()) for i, group in enumerate(GROUPS)},
        "valid20_used_for_entry": False,
    }
    return panel, metadata


def validate_result(result: dict, n_bars: int, selected_count: int) -> dict:
    trades, equity, summary = result["trades"], result["equity"], result["summary"]
    if list(trades.columns) != TRADE_COLUMNS or list(equity.columns) != EQUITY_COLUMNS:
        raise ValueError("Capture output schema changed")
    if len(equity) != n_bars or summary["n_bars"] != n_bars:
        raise ValueError("Capture dropped equity rows")
    if summary["initial_equity"] != 1.0 or summary["horizon"] != 20:
        raise ValueError("Capture changed the frozen capital or holding horizon")
    if summary["selected_signals"] != selected_count or int(equity.signal_selected.sum()) != selected_count:
        raise ValueError("Capture changed the supplied past-only signal mask")
    if len(trades) != summary["entered_trades"]:
        raise ValueError("Entered positions are missing from the full trade ledger")
    status_counts = trades.status.value_counts().to_dict()
    expected_counts = {
        "COMPLETED_HORIZON": summary["completed_trades"],
        "OPEN_CENSORED_SEGMENT_END": summary["censored_open_trades"],
        "OPEN_HALTED_NONPOSITIVE_CLOSE_NAV": summary["halted_open_trades"],
    }
    if set(status_counts) - set(expected_counts):
        raise ValueError("Unexpected trade status")
    if any(status_counts.get(k, 0) != v for k, v in expected_counts.items()):
        raise ValueError("Completed/censored/halted counts do not reconcile")
    completed = trades.completed.to_numpy(dtype=bool)
    if not np.array_equal(completed, trades.status.eq("COMPLETED_HORIZON").to_numpy(dtype=bool)):
        raise ValueError("An unfinished position was classified as completed")
    if len(trades):
        natural = trades.loc[completed]
        unfinished = trades.loc[~completed]
        if (not natural.holding_bars_observed.eq(20).all() or natural.exit_ts.isna().any()
                or not natural.exit_index.eq(natural.scheduled_exit_index).all()):
            raise ValueError("A completed trade lacks its natural 20-bar exit")
        if unfinished.exit_ts.notna().any() or unfinished.exit_fee.ne(0).any():
            raise ValueError("An unfinished position contains a fabricated exit")
        if not trades.entry_index.eq(trades.signal_index + 1).all():
            raise ValueError("Entry is not the next bar after its signal")
    nav = equity.equity_after_fee_slippage.to_numpy(dtype=float)
    if not np.isfinite(nav).all() or not np.isclose(nav[-1], summary["final_equity_after_fee_slippage"], rtol=0, atol=1e-12):
        raise ValueError("Summary and final equity row do not agree")
    if summary["halted"]:
        halt = int(summary["halt_index"])
        if nav[halt] > 0 or not np.equal(nav[halt:], nav[halt]).all():
            raise ValueError("Nonpositive economic NAV was clipped or resurrected")
        if equity.entry_executed.iloc[halt + 1:].any() or equity.exit_executed.iloc[halt + 1:].any():
            raise ValueError("Orders continued after an economic halt")
    if summary["executable_certification"]:
        raise ValueError("Price capture cannot certify executability")
    return {
        "equity_rows": len(equity), "trade_rows": len(trades),
        "censored_positive_terminal_marks": int((
            trades.status.eq("OPEN_CENSORED_SEGMENT_END")
            & trades.pnl_after_fee_slippage.gt(0)
        ).sum()),
    }


def write_rows(writer: Any, metadata: tuple, frame: pd.DataFrame) -> None:
    writer.writerows((*metadata, *values) for values in frame.itertuples(index=False, name=None))


def fraction(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else np.nan


def aggregate_summaries(summary: pd.DataFrame) -> pd.DataFrame:
    output = []
    for group in GROUPS:
        for cost in COSTS:
            rows = summary.loc[summary.group.eq(group) & summary.cost.eq(cost)]
            active = rows.loc[rows.entered_trades.gt(0)]
            all_nav = rows.final_equity_after_fee_slippage.to_numpy(dtype=float)
            active_nav = active.final_equity_after_fee_slippage.to_numpy(dtype=float)
            all_dd = rows.max_drawdown_after_fee_slippage.to_numpy(dtype=float)
            active_dd = active.max_drawdown_after_fee_slippage.to_numpy(dtype=float)
            row = {
                "group": group, "cost": cost, "segments": len(rows),
                "symbols": int(rows.symbol.nunique()), "segments_with_entries": len(active),
                "segments_without_entries": len(rows) - len(active),
                "equity_rows": int(rows.n_bars.sum()),
                "selected_signals": int(rows.selected_signals.sum()),
                "entered_trades": int(rows.entered_trades.sum()),
                "completed_trades": int(rows.completed_trades.sum()),
                "censored_open_trades": int(rows.censored_open_trades.sum()),
                "halted_open_trades": int(rows.halted_open_trades.sum()),
                "halted_segments": int(rows.halted.sum()),
                "segments_with_intraday_insolvency_breach": int(rows.intraday_insolvency_breach.sum()),
                "pending_signals_at_segment_end": int(rows.pending_signals_at_segment_end.sum()),
                "ignored_signals_while_open": int(rows.ignored_signals_while_open.sum()),
                "ignored_signals_after_halt": int(rows.ignored_signals_after_halt.sum()),
                "positive_final_equity_segments_all": int((all_nav > 0).sum()),
                "positive_final_equity_fraction_all_segments": fraction(int((all_nav > 0).sum()), len(rows)),
                "positive_final_equity_fraction_entered_segments": fraction(int((active_nav > 0).sum()), len(active)),
                "profitable_terminal_mark_segments_all": int((all_nav > 1).sum()),
                "profitable_terminal_mark_fraction_all_segments": fraction(int((all_nav > 1).sum()), len(rows)),
                "profitable_terminal_mark_fraction_entered_segments": fraction(int((active_nav > 1).sum()), len(active)),
                "median_max_drawdown_all_segments": float(np.median(all_dd)) if len(all_dd) else np.nan,
                "median_max_drawdown_entered_segments": float(np.median(active_dd)) if len(active_dd) else np.nan,
                "censored_positive_terminal_marks": int(rows.censored_positive_terminal_marks.sum()),
                "distribution_denominator": "independent segments; active distribution requires >=1 entry; no cross-segment wealth chaining",
                "terminal_mark_warning": "may include unfinished positions or frozen failure snapshots; not completed-trade profit",
                "cost_scope": "after fee/slippage only; funding unverified and not assumed zero",
                "fullcost_verified": False, "executable_certification": False,
            }
            for label, values in (("all_segments", all_nav - 1), ("entered_segments", active_nav - 1)):
                for quantile, name in ((0, "min"), (0.05, "p05"), (0.5, "median"), (0.95, "p95"), (1, "max")):
                    row[f"terminal_mark_return_{name}_{label}"] = float(np.quantile(values, quantile)) if len(values) else np.nan
            output.append(row)
    return pd.DataFrame(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-dir", default="p1-research")
    parser.add_argument("--run-id", default="p2-capture")
    args = parser.parse_args()
    out = FAMILY / "artifacts" / directory_name(args.run_id)
    if out.exists():
        raise FileExistsError(f"Retained output exists; choose a new run-id: {out}")
    panel, panel_metadata = load_panel(args.panel_dir)
    if not panel_metadata["eligible_rows"]:
        raise ValueError("Panel has no eligible segments to replay")
    pins = {
        "scripts/run_capture.py": sha(Path(__file__)),
        "scripts/capture.py": sha(Path(__file__).with_name("capture.py")),
        "specs/research-contract.md": sha(FAMILY / "specs" / "research-contract.md"),
        panel_metadata["path"]: panel_metadata["sha256"],
        panel_metadata["manifest_path"]: panel_metadata["manifest_sha256"],
    }
    started = time.time()
    save_json(out / "started.json", {
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "python": sys.version, "executable": sys.executable,
        "numpy": np.__version__, "pandas": pd.__version__,
        "panel": panel_metadata, "pinned_files": pins, "groups": GROUPS, "costs": COSTS,
        "initial_equity_per_segment": 1.0, "horizon": 20,
        "entry_uses_future_validity": False, "segment_wealth_chained": False,
        "cost_scope": "fee/slippage-only price capture; no funding or execution certification",
    })
    summary_rows = []
    equity_files = {}
    trades_path = out / "trades.csv.gz"
    trade_rows = 0
    account_count = 0
    bars_columns = ["symbol", "research_segment_id", "ts", "open", "high", "low", "close", "volume"]
    try:
        with ExitStack() as stack:
            trade_handle = stack.enter_context(gzip.open(trades_path, "wt", encoding="utf-8", newline="", compresslevel=6))
            trade_writer = csv.writer(trade_handle)
            trade_writer.writerow(META_COLUMNS + TRADE_COLUMNS)
            equity_writers = {}
            for group in GROUPS:
                for cost in COSTS:
                    relative = f"equity/{group}-{cost}.csv.gz"
                    path = out / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    handle = stack.enter_context(gzip.open(path, "wt", encoding="utf-8", newline="", compresslevel=6))
                    writer = csv.writer(handle)
                    writer.writerow(META_COLUMNS + EQUITY_COLUMNS)
                    equity_writers[group, cost] = writer
                    equity_files[relative] = {"group": group, "cost": cost, "rows": 0, "accounts": 0}
            for symbol_number, (symbol, symbol_frame) in enumerate(panel.groupby("symbol", sort=False), start=1):
                for segment, frame in symbol_frame.loc[symbol_frame.eligible].groupby("research_segment_id", sort=False):
                    bars = frame.loc[:, bars_columns].reset_index(drop=True)
                    signals = frame.loc[:, list(GROUPS)].to_numpy(dtype=bool)
                    segment_id = str(segment)
                    for group_index, group in enumerate(GROUPS):
                        selected = signals[:, group_index]
                        selected_count = int(np.count_nonzero(selected))
                        direction = 1 if group.endswith("_LONG") else -1
                        for cost, costs in COSTS.items():
                            account_id = hashlib.sha256(json.dumps([symbol, segment_id, group, cost], ensure_ascii=False).encode("utf-8")).hexdigest()
                            result = run_hold20_account(bars, selected, direction, horizon=20, **costs)
                            checked = validate_result(result, len(bars), selected_count)
                            meta = (symbol, segment_id, group, cost, account_id)
                            write_rows(trade_writer, meta, result["trades"])
                            write_rows(equity_writers[group, cost], meta, result["equity"])
                            relative = f"equity/{group}-{cost}.csv.gz"
                            equity_files[relative]["rows"] += checked["equity_rows"]
                            equity_files[relative]["accounts"] += 1
                            trade_rows += checked["trade_rows"]
                            account_count += 1
                            row = dict(zip(META_COLUMNS, meta))
                            row.update(result["summary"])
                            row.update(first_bar_open=bars.ts.iloc[0], last_bar_open=bars.ts.iloc[-1],
                                       first_feature_valid_signal_day=frame.loc[frame.feature_valid, "ts"].min(),
                                       censored_positive_terminal_marks=checked["censored_positive_terminal_marks"])
                            row["execution_blockers"] = json.dumps(row["execution_blockers"], ensure_ascii=False)
                            summary_rows.append(row)
                if symbol_number % 50 == 0 or symbol_number == panel_metadata["symbols"]:
                    print(f"CAPTURE symbols={symbol_number}/{panel_metadata['symbols']} accounts={account_count} trades={trade_rows} elapsed={time.time()-started:.1f}s", flush=True)
        summary = pd.DataFrame(summary_rows)
        if len(summary) != account_count or int(summary.entered_trades.sum()) != trade_rows:
            raise ValueError("Global summary and ledger counters do not reconcile")
        expected_rows_per_file = panel_metadata["eligible_rows"]
        if any(file["rows"] != expected_rows_per_file for file in equity_files.values()):
            raise ValueError("An equity group lost eligible bar rows")
        if len({file["accounts"] for file in equity_files.values()}) != 1:
            raise ValueError("Groups/costs do not share the same independent segment inventory")
        summary_path, aggregate_path = out / "summary.csv", out / "aggregate.csv"
        summary.to_csv(summary_path, index=False)
        aggregate = aggregate_summaries(summary)
        aggregate.to_csv(aggregate_path, index=False)
        for relative, metadata in equity_files.items():
            metadata["sha256"] = sha(out / relative)
            metadata["columns"] = META_COLUMNS + EQUITY_COLUMNS
        save_json(out / "equity-manifest.json", {
            "files": equity_files, "total_rows": sum(file["rows"] for file in equity_files.values()),
            "row_time_semantics": "ts is original UTC bar open; close mark becomes known at ts+1 day",
            "includes_warmup_and_halted_snapshot_rows": True,
        })
        changed_files = [relative for relative, digest in pins.items() if sha(FAMILY / relative) != digest]
        manifest = {
            "source_panel": panel_metadata, "pinned_files_unchanged": not changed_files,
            "files": {
                "summary.csv": {"sha256": sha(summary_path), "rows": len(summary)},
                "aggregate.csv": {"sha256": sha(aggregate_path), "rows": len(aggregate)},
                "trades.csv.gz": {"sha256": sha(trades_path), "rows": trade_rows, "columns": META_COLUMNS + TRADE_COLUMNS},
                "equity-manifest.json": {"sha256": sha(out / "equity-manifest.json")},
                "started.json": {"sha256": sha(out / "started.json")},
                **equity_files,
            },
        }
        save_json(out / "artifact-manifest.json", manifest)
        completed = {
            "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "seconds": time.time() - started,
            "status": "SEGMENT_PRICE_CAPTURE_DIAGNOSTIC_COMPLETE" if not changed_files else "SOURCE_CHANGED_INVALID_OUTPUT",
            "symbols": panel_metadata["symbols"], "independent_segments": account_count // (len(GROUPS) * len(COSTS)),
            "accounts": account_count, "trade_rows": trade_rows,
            "completed_trades": int(summary.completed_trades.sum()),
            "censored_open_trades": int(summary.censored_open_trades.sum()),
            "halted_open_trades": int(summary.halted_open_trades.sum()),
            "equity_rows": sum(file["rows"] for file in equity_files.values()),
            "changed_files": changed_files, "output_contract_checks_passed": True,
            "artifact_manifest_sha256": sha(out / "artifact-manifest.json"),
            "funding_included": False, "fullcost_verified": False,
            "executable_certification": False, "segment_wealth_chained": False,
            "new_candidate_selected": False,
        }
        save_json(out / "completed.json", completed)
        print(json.dumps(completed, ensure_ascii=False, indent=2), flush=True)
        return 0 if not changed_files else 2
    except Exception as exc:
        save_json(out / "failure.json", {
            "failed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "error": f"{type(exc).__name__}: {exc}", "seconds": time.time() - started,
            "completed_account_calls": account_count, "partial_trade_rows": trade_rows,
            "status": "INCOMPLETE_OUTPUTS_NOT_INTERPRETABLE", "fallback_used": False,
        })
        raise


if __name__ == "__main__":
    raise SystemExit(main())
