"""独立核对本家族保留的P2资金账；不计算信号、不重跑策略或调用捕获内核。"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[2]
KERNEL = REPO / "research/_shared-kernels/trend-strength-pullback-restart/v1"
GROUPS = tuple(f"{p}_{d}" for p in ("ALL", "HIGH", "HIGH_P", "HIGH_PM")
               for d in ("LONG", "SHORT"))
COSTS = {"base": (0.001, 0.0004), "stress": (0.001, 0.0008)}
CAPTURE_SHA256 = "42585a7289aacdb8b6a3727fcc575ec8b97294bcd70912fbf713799ef91dc351"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(2**20), b""):
            h.update(chunk)
    return h.hexdigest()


def contained(root, name):
    relative = Path(name)
    target = (root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts or not target.is_relative_to(root.resolve()):
        raise ValueError(f"Uncontained evidence path: {name}")
    return target


class Checks:
    """累积核对数量和数值误差；失败即停止，不能输出通过报告。"""

    def __init__(self):
        self.metrics = {}

    def close(self, name, actual, expected, atol=1e-10, rtol=1e-10):
        actual, expected = np.broadcast_arrays(np.asarray(actual, float), np.asarray(expected, float))
        ok = np.isclose(actual, expected, atol=atol, rtol=rtol, equal_nan=True)
        difference = np.abs(actual - expected)
        error = float(difference[np.isfinite(difference)].max()) if np.isfinite(difference).any() else 0.0
        item = self.metrics.setdefault(name, {"n": 0, "max_abs_error": 0.0, "failures": 0})
        item["n"] += int(ok.size)
        item["max_abs_error"] = max(item["max_abs_error"], error)
        item["failures"] += int((~ok).sum())
        if not ok.all():
            raise ValueError(f"Audit failed: {name}: {item}")

    def require(self, name, condition):
        self.close(name, np.asarray(condition, bool).astype(int), 1, atol=0, rtol=0)


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_retained(p2, checks):
    """先验锁→P1来源→P2开始/完成收据→所有输出文件的完整链。"""
    lock_path = FAMILY / "specs/computation-lock.json"
    lock = _json(lock_path)
    checks.require("lock_nonempty", isinstance(lock.get("files"), dict) and bool(lock["files"]))
    required = [FAMILY / "specs/input-contract.md", FAMILY / "specs/research-contract.md", FAMILY / "specs/statistics-contract.md",
                FAMILY / "scripts/run_capture.py", FAMILY / "scripts/audit_capture.py", KERNEL / "capture.py"]
    checks.require("lock_capture_chain", all(str(p.relative_to(REPO)) in lock["files"] for p in required))
    for relative, expected in lock["files"].items():
        checks.require("computation_hash", sha(contained(REPO, relative)) == expected)
    km = lock["kernel_manifest"]
    km_path = contained(REPO, km["path"])
    checks.require("kernel_manifest_location", km_path.parent == KERNEL.resolve())
    checks.require("kernel_manifest_hash", sha(km_path) == km["sha256"])
    kernel_files = _json(km_path)["files"]
    actual_py = {p.relative_to(KERNEL).as_posix() for p in KERNEL.rglob("*.py")}
    checks.require("complete_kernel_python_inventory", actual_py == {n for n in kernel_files if Path(n).suffix == ".py"})
    checks.require("original_capture_bytes", kernel_files.get("capture.py") == CAPTURE_SHA256)
    for relative, expected in kernel_files.items():
        checks.require("kernel_file_hash", sha(contained(KERNEL, relative)) == expected)
        checks.require("kernel_in_computation_lock", lock["files"].get(str((KERNEL / relative).relative_to(REPO))) == expected)
    complete, started, manifest = (_json(p2 / n) for n in ("completed.json", "started.json", "artifact-manifest.json"))
    checks.require("completion_state", complete["status"] == "SEGMENT_PRICE_CAPTURE_DIAGNOSTIC_COMPLETE")
    checks.require("completion_checks", complete["output_contract_checks_passed"] and not complete["changed_files"])
    checks.require("output_manifest_anchor", sha(p2 / "artifact-manifest.json") == complete["artifact_manifest_sha256"])
    checks.require("immutable_run", manifest["pinned_files_unchanged"])
    expected_pins = {**lock["files"], km["path"]: km["sha256"], str(lock_path.relative_to(REPO)): sha(lock_path)}
    checks.require("started_full_computation_chain", all(started["pinned_files"].get(n) == v for n, v in expected_pins.items()))
    for relative, expected in started["pinned_files"].items():
        checks.require("started_input_hash", sha(contained(REPO, relative)) == expected)
    required_outputs = {"summary.csv", "aggregate.csv", "trades.csv.gz", "position-exceptions.csv.gz",
                        "equity-manifest.json", "started.json"}
    required_outputs.update(f"equity/{g}-{c}.csv.gz" for g in GROUPS for c in COSTS)
    checks.require("output_inventory", set(manifest["files"]) == required_outputs)
    for relative, meta in manifest["files"].items():
        checks.require("retained_output_hash", sha(contained(p2, relative)) == meta["sha256"])
    em = _json(p2 / "equity-manifest.json")
    checks.require("equity_inventory", set(em["files"]) == {f"equity/{g}-{c}.csv.gz" for g in GROUPS for c in COSTS})
    for relative, meta in em["files"].items():
        checks.require("equity_manifest_consistency", meta == manifest["files"][relative])
    checks.close("equity_declared_total", em["total_rows"], sum(v["rows"] for v in em["files"].values()))
    checks.close("completed_equity_total", complete["equity_rows"], em["total_rows"])
    checks.require("cost_contract", started["costs"] == {k: {"fee": v[0], "slippage": v[1]} for k, v in COSTS.items()})
    checks.require("group_contract", list(started["groups"]) == list(GROUPS))
    checks.require("entry_is_past_only", started["entry_uses_future_validity"] is False)
    checks.require("independent_segment_capital", started["initial_equity_per_segment"] == 1 and not started["segment_wealth_chained"])
    checks.require("no_fullcost_or_execution_claim", not complete["funding_included"] and not complete["fullcost_verified"] and not complete["executable_certification"])
    pm = started["panel"]
    panel_path, pm_path = contained(FAMILY, pm["path"]), contained(FAMILY, pm["manifest_path"])
    checks.require("own_family_panel", panel_path.parent.parent == (FAMILY / "artifacts").resolve())
    checks.require("panel_receipt_hash", sha(pm_path) == pm["manifest_sha256"])
    panel_manifest = _json(pm_path)
    checks.require("panel_full_computation_pins", panel_manifest.get("pins") == lock["files"])
    checks.require("panel_computation_lock", panel_manifest["computation_lock_sha256"] == sha(lock_path))
    checks.require("panel_content_hash", sha(panel_path) == pm["sha256"] == panel_manifest["sha256"])
    for path, digest in ((panel_path, pm["sha256"]), (pm_path, pm["manifest_sha256"])):
        checks.require("started_panel_anchor", started["pinned_files"].get(str(path.relative_to(REPO))) == digest)
    for relative, expected in panel_manifest.get("pins", {}).items():
        checks.require("panel_source_pin", sha(contained(REPO, relative)) == expected)
    p1_summary_path = panel_path.parent / "summary.json"
    p1_summary = _json(p1_summary_path)
    checks.require("p1_completion_state", p1_summary.get("status") == "FIXED_HISTORY_STATE_PANEL_COMPLETE")
    checks.require("p1_completed_panel_hashes", p1_summary.get("files", {}).get("panel.pkl.gz") == pm["sha256"] and p1_summary.get("files", {}).get("panel-manifest.json") == pm["manifest_sha256"])
    input_manifest_path = FAMILY / "artifacts/p0-inputs/frame-manifest.json"
    checks.require("p1_input_manifest_hash", sha(input_manifest_path) == panel_manifest.get("input_manifest_sha256"))
    for path in (p1_summary_path, input_manifest_path):
        checks.require("started_upstream_receipts", started["pinned_files"].get(str(path.relative_to(REPO))) == sha(path))
    panel = pd.read_pickle(panel_path, compression="gzip")
    checks.close("panel_rows", len(panel), panel_manifest["rows"])
    return panel, complete, manifest, em


def _as_bool(frame, columns, checks):
    for column in columns:
        checks.require(f"boolean:{column}", pd.api.types.is_bool_dtype(frame[column].dtype) and not frame[column].isna().any())


def _segment_frames(panel):
    return {(str(symbol), str(segment)): frame.reset_index(drop=True)
            for (symbol, segment), frame in panel.loc[panel.eligible].groupby(["symbol", "research_segment_id"], sort=False)}


def audit_ledger(trades, summary, panel, checks):
    """全部交易独立公式/原始K线/全部账户时序核对；不使用未来标签筛入场。"""
    tr, s = trades.reset_index(drop=True), summary.reset_index(drop=True)
    _as_bool(s, ["halted", "intraday_insolvency_breach", "executable_certification"], checks)
    if len(tr):
        _as_bool(tr, ["completed", "intraday_insolvency_breach"], checks)
    checks.require("unique_accounts", s.account_id.is_unique)
    checks.require("unique_trade_ids", not tr.duplicated(["account_id", "trade_id"]).any())
    checks.require("known_groups_costs", s.group.isin(GROUPS).all() and s.cost.isin(COSTS).all())
    checks.require("trade_account_membership", tr.account_id.isin(s.account_id).all())
    checks.require("not_execution_certified", ~s.executable_certification)
    checks.close("account_initial_capital", s.initial_equity, 1)
    checks.close("account_horizon", s.horizon, 20)
    slip = tr.cost.map({k: v[1] for k, v in COSTS.items()}).to_numpy(float)
    fee = tr.cost.map({k: v[0] for k, v in COSTS.items()}).to_numpy(float)
    checks.close("entry_fill", tr.entry_fill_price, tr.entry_reference_price * (1 + tr.direction * slip))
    checks.close("entry_budget", tr.entry_notional + tr.entry_fee, tr.entry_nav)
    checks.close("entry_notional", tr.entry_notional, tr.quantity * tr.entry_fill_price)
    checks.close("entry_fee", tr.entry_fee, fee * tr.entry_notional)
    checks.require("positive_entry_nav_quantity", tr.entry_nav.gt(0) & tr.quantity.gt(0))
    checks.close("linear_directional_price_pnl", tr.price_pnl, tr.direction * tr.quantity * (tr.terminal_mark_price - tr.entry_fill_price))
    checks.close("all_fees", tr.total_fees, tr.entry_fee + tr.exit_fee)
    checks.close("net_pnl", tr.pnl_after_fee_slippage, tr.price_pnl - tr.total_fees)
    checks.close("terminal_nav", tr.terminal_nav_after_fee_slippage, tr.entry_nav + tr.pnl_after_fee_slippage)
    checks.close("return_on_entry_nav", tr.return_on_entry_nav_after_fee_slippage, tr.pnl_after_fee_slippage / tr.entry_nav)
    checks.close("entry_slippage", tr.entry_slippage_cost, tr.quantity * (tr.entry_fill_price - tr.entry_reference_price).abs())
    checks.close("all_slippage", tr.total_slippage_cost, tr.entry_slippage_cost + tr.exit_slippage_cost)
    checks.close("next_open_index", tr.entry_index, tr.signal_index + 1)
    checks.close("scheduled_twentieth_bar", tr.scheduled_exit_index, tr.entry_index + 19)
    checks.require("completed_status", tr.completed.eq(tr.status.eq("COMPLETED_HORIZON")))
    natural, unfinished = tr.loc[tr.completed.astype(bool)], tr.loc[~tr.completed.astype(bool)]
    checks.close("natural_twenty_bars", natural.holding_bars_observed, 20)
    checks.close("natural_exit_index", natural.exit_index, natural.entry_index + 19)
    checks.close("natural_exit_fill", natural.exit_fill_price, natural.exit_reference_price * (1 - natural.direction * natural.cost.map({k: v[1] for k, v in COSTS.items()})))
    checks.close("natural_exit_notional", natural.exit_notional, natural.quantity * natural.exit_fill_price)
    checks.close("natural_exit_fee", natural.exit_fee, natural.cost.map({k: v[0] for k, v in COSTS.items()}) * natural.exit_notional)
    checks.close("natural_exit_slippage", natural.exit_slippage_cost, natural.quantity * (natural.exit_fill_price - natural.exit_reference_price).abs())
    checks.close("natural_twenty_days", (pd.to_datetime(natural.exit_ts, utc=True) - pd.to_datetime(natural.entry_ts, utc=True)).dt.total_seconds(), 20 * 86400)
    for column in ("exit_ts",):
        checks.require("unfinished_no_exit_timestamp", pd.to_datetime(unfinished[column], utc=True, errors="coerce").isna())
    for column in ("exit_index", "exit_reference_price", "exit_fill_price"):
        checks.require(f"unfinished_no_{column}", unfinished[column].isna())
    for column in ("exit_notional", "exit_fee", "exit_slippage_cost"):
        checks.close(f"unfinished_zero_{column}", unfinished[column], 0)
    checks.require("unfinished_status", unfinished.status.isin(["OPEN_CENSORED_SEGMENT_END", "OPEN_HALTED_NONPOSITIVE_CLOSE_NAV"]))
    segs = _segment_frames(panel)
    expected_accounts = {(symbol, segment, group, cost) for symbol, segment in segs for group in GROUPS for cost in COSTS}
    actual_accounts = set(zip(s.symbol.astype(str), s.research_segment_id.astype(str), s.group, s.cost))
    checks.require("complete_segment_inventory", actual_accounts == expected_accounts and len(s) == len(expected_accounts))
    by_account = {a: f.reset_index(drop=True) for a, f in tr.groupby("account_id", sort=False)}
    future_incomplete = []
    for sr in s.itertuples(index=False):
        bars = segs[str(sr.symbol), str(sr.research_segment_id)]
        pt = by_account.get(sr.account_id, tr.iloc[:0])
        direction = 1 if sr.group.endswith("_LONG") else -1
        expected_id = hashlib.sha256(json.dumps([sr.symbol, str(sr.research_segment_id), sr.group, sr.cost], ensure_ascii=False).encode()).hexdigest()
        checks.require("account_identity", expected_id == sr.account_id)
        checks.close("direction_and_cost", [sr.direction, sr.fee, sr.slippage], [direction, *COSTS[sr.cost]])
        checks.close("account_bar_count", sr.n_bars, len(bars))
        checks.require("continuous_source_segment", bars.ts.diff().dropna().eq(pd.Timedelta(days=1)).all())
        checks.require("source_timezones", isinstance(bars.ts.dtype, pd.DatetimeTZDtype))
        selected = bars[sr.group].to_numpy(bool)
        checks.close("selected_source_count", sr.selected_signals, selected.sum())
        checks.close("summary_nav_from_trades", sr.final_equity_after_fee_slippage, 1 + pt.pnl_after_fee_slippage.sum())
        checks.close("summary_return", sr.total_return_after_fee_slippage, sr.final_equity_after_fee_slippage - 1)
        checks.close("summary_fees", sr.total_fees, pt.total_fees.sum())
        checks.close("summary_slippage", sr.total_slippage_cost, pt.total_slippage_cost.sum())
        checks.close("summary_entered", sr.entered_trades, len(pt))
        for status, column in [("COMPLETED_HORIZON", "completed_trades"), ("OPEN_CENSORED_SEGMENT_END", "censored_open_trades"), ("OPEN_HALTED_NONPOSITIVE_CLOSE_NAV", "halted_open_trades")]:
            checks.close(f"summary_{column}", getattr(sr, column), pt.status.eq(status).sum())
        checks.close("summary_censored_positive_marks", sr.censored_positive_terminal_marks, (pt.status.eq("OPEN_CENSORED_SEGMENT_END") & pt.pnl_after_fee_slippage.gt(0)).sum())
        close, high, low = (bars[k].to_numpy(float) for k in ("close", "high", "low"))
        previous_nav, previous_exit, breach_bars = 1.0, -1, 0
        expected_halt = None
        for ti, t in enumerate(pt.itertuples(index=False)):
            entry, last, sig = int(t.entry_index), int(t.last_observed_index), int(t.signal_index)
            checks.require("trade_metadata", (t.symbol, str(t.research_segment_id), t.group, t.cost) == (sr.symbol, str(sr.research_segment_id), sr.group, sr.cost))
            checks.close("sequential_trade_id", t.trade_id, ti + 1)
            checks.close("trade_direction", t.direction, direction)
            checks.close("sequential_capital", t.entry_nav, previous_nav)
            checks.require("nonoverlapping_entries", previous_exit < entry and 0 <= sig < entry <= last < len(bars))
            checks.require("past_selected_signal", selected[sig] and bool(bars.feature_valid.iloc[sig]))
            checks.require("source_signal_timestamp", pd.Timestamp(t.signal_bar_ts) == bars.ts.iloc[sig])
            checks.require("source_signal_close", pd.Timestamp(t.signal_close_ts) == bars.ts.iloc[sig] + pd.Timedelta(days=1))
            checks.require("source_entry_timestamp", pd.Timestamp(t.entry_ts) == bars.ts.iloc[entry])
            checks.require("source_last_timestamp", pd.Timestamp(t.last_observed_bar_ts) == bars.ts.iloc[last])
            checks.close("source_entry_open", t.entry_reference_price, bars.open.iloc[entry])
            checks.close("observed_holding_count", t.holding_bars_observed, last - entry + 1)
            base = t.entry_nav - t.entry_fee
            path = base + direction * t.quantity * (close[entry:last + 1] - t.entry_fill_price)
            adverse = low[entry:last + 1] if direction == 1 else high[entry:last + 1]
            favorable = high[entry:last + 1] if direction == 1 else low[entry:last + 1]
            min_path = base + direction * t.quantity * (adverse - t.entry_fill_price)
            breaches = int((min_path <= 0).sum())
            breach_bars += breaches
            checks.close("source_min_intraday_nav", t.min_intraday_nav, min_path.min())
            checks.close("source_max_favorable_pnl", t.max_favorable_price_pnl, (direction * t.quantity * (favorable - t.entry_fill_price)).max())
            checks.close("source_max_adverse_pnl", t.max_adverse_price_pnl, (direction * t.quantity * (adverse - t.entry_fill_price)).min())
            checks.require("source_intraday_breach", bool(t.intraday_insolvency_breach) == bool(breaches))
            checks.require("no_earlier_nonpositive_close", (path[:-1] > 0).all())
            if t.completed:
                checks.require("completed_before_insolvency", (path > 0).all())
                checks.close("source_exit_close", t.exit_reference_price, close[last])
                checks.close("completed_terminal_fill", t.terminal_mark_price, t.exit_fill_price)
                checks.require("source_exit_timestamp", pd.Timestamp(t.exit_ts) == bars.ts.iloc[last] + pd.Timedelta(days=1))
            else:
                checks.close("open_terminal_close", t.terminal_mark_price, close[last])
                if t.status == "OPEN_CENSORED_SEGMENT_END":
                    checks.require("censored_at_segment_end", last == len(bars) - 1 and last < t.scheduled_exit_index and (path > 0).all())
                else:
                    checks.require("halt_nonpositive_unclipped", path[-1] <= 0)
            if t.terminal_nav_after_fee_slippage <= 0:
                expected_halt = last
                checks.require("no_trade_after_halt", ti == len(pt) - 1)
            stop = last if t.completed or expected_halt is not None else last + 1
            checks.close("trade_ignored_signals", t.ignored_signals, selected[entry:stop].sum())
            if not bool(bars.valid20.iloc[sig]):
                future_incomplete.append({"account_id": sr.account_id, "cost": sr.cost, "status": t.status})
            previous_nav, previous_exit = t.terminal_nav_after_fee_slippage, last
        checks.require("summary_halt_state", bool(sr.halted) == (expected_halt is not None))
        checks.close("summary_halt_index", sr.halt_index, np.nan if expected_halt is None else expected_halt)
        checks.require("summary_failure_snapshot", bool(sr.final_equity_is_frozen_failure_snapshot) == bool(sr.halted))
        checks.close("summary_intraday_bars", sr.intraday_insolvency_breach_bars, breach_bars)
        checks.require("summary_intraday_state", bool(sr.intraday_insolvency_breach) == bool(breach_bars))
        # 按事前选中日和已核实退出日独立核对全部空仓机会，禁止未成熟事件偷筛。
        next_available, entered, ignored_open, ignored_halt, pending = 0, 0, 0, 0, 0
        for sig in np.flatnonzero(selected):
            if expected_halt is not None and sig >= expected_halt:
                ignored_halt += 1
            elif sig < next_available:
                ignored_open += 1
            elif sig + 1 == len(bars):
                pending += 1
            else:
                checks.require("every_flat_signal_entered", entered < len(pt))
                t = pt.iloc[entered]
                checks.close("first_available_nextopen", t.entry_index, sig + 1)
                next_available = int(t.last_observed_index) if t.completed else len(bars)
                entered += 1
        checks.close("source_signal_dispositions", [sr.entered_trades, sr.ignored_signals_while_open, sr.ignored_signals_after_halt, sr.pending_signals_at_segment_end], [entered, ignored_open, ignored_halt, pending])
    return {"trade_rows": len(tr), "accounts": len(s), "independent_segments": len(segs),
            "future_incomplete_entered": len(future_incomplete),
            "future_incomplete_by_cost_status": pd.DataFrame(future_incomplete).groupby(["cost", "status"]).size().rename("n").reset_index().to_dict("records") if future_incomplete else []}


def audit_aggregates(summary, aggregate, checks):
    checks.require("aggregate_inventory", set(zip(aggregate.group, aggregate.cost)) == {(g, c) for g in GROUPS for c in COSTS} and len(aggregate) == len(GROUPS) * len(COSTS))
    sums = ["selected_signals", "entered_trades", "completed_trades", "censored_open_trades", "halted_open_trades",
            "pending_signals_at_segment_end", "ignored_signals_while_open", "ignored_signals_after_halt", "censored_positive_terminal_marks"]
    for a in aggregate.itertuples(index=False):
        s = summary.loc[summary.group.eq(a.group) & summary.cost.eq(a.cost)]
        active = s.loc[s.entered_trades.gt(0)]
        checks.close("aggregate_counts", [a.segments, a.symbols, a.segments_with_entries, a.segments_without_entries, a.equity_rows, a.halted_segments, a.segments_with_intraday_insolvency_breach], [len(s), s.symbol.nunique(), len(active), len(s) - len(active), s.n_bars.sum(), s.halted.sum(), s.intraday_insolvency_breach.sum()])
        checks.close("aggregate_sums", [getattr(a, k) for k in sums], [s[k].sum() for k in sums])
        checks.close("aggregate_nav_count", [a.positive_final_equity_segments_all, a.profitable_terminal_mark_segments_all], [s.final_equity_after_fee_slippage.gt(0).sum(), s.final_equity_after_fee_slippage.gt(1).sum()])
        for label, f in (("all_segments", s), ("entered_segments", active)):
            nav = f.final_equity_after_fee_slippage.to_numpy(float)
            for quantile, name in ((0, "min"), (.05, "p05"), (.5, "median"), (.95, "p95"), (1, "max")):
                checks.close("aggregate_return_distribution", getattr(a, f"terminal_mark_return_{name}_{label}"), np.quantile(nav - 1, quantile) if len(nav) else np.nan)
            checks.close("aggregate_profit_fraction", getattr(a, f"profitable_terminal_mark_fraction_{label}"), float((nav > 1).mean()) if len(nav) else np.nan)
            checks.close("aggregate_positive_nav_fraction", getattr(a, f"positive_final_equity_fraction_{label}"), float((nav > 0).mean()) if len(nav) else np.nan)
            checks.close("aggregate_drawdown", getattr(a, f"median_max_drawdown_{label}"), f.max_drawdown_after_fee_slippage.median() if len(f) else np.nan)
        checks.require("aggregate_not_certified", not a.fullcost_verified and not a.executable_certification)


def audit_equity_account(eq, trades, bars, group, checks):
    """从独立账本与源K线重构一个完整账户日路径，无捕获内核调用。"""
    n = len(bars)
    checks.close("sample_row_count", len(eq), n)
    checks.close("sample_row_order", eq.row_index, np.arange(n))
    checks.require("sample_timestamp", pd.to_datetime(eq.ts, utc=True).eq(bars.ts.reset_index(drop=True)).all())
    checks.close("sample_observed_close", eq.observed_close, bars.close)
    selected = bars[group].to_numpy(bool)
    checks.require("sample_original_signals", np.array_equal(eq.signal_selected.to_numpy(bool), selected))
    nav, op, intraday = (np.ones(n) for _ in range(3))
    fees, slip = np.zeros(n), np.zeros(n)
    mark = bars.close.to_numpy(float).copy()
    entries, exits, breaches, halted = (np.zeros(n, bool) for _ in range(4))
    actions = np.where(selected, "QUEUED_NEXT_OPEN", "NOT_SELECTED").astype(object)
    for t in trades.itertuples(index=False):
        start, end = int(t.entry_index), int(t.last_observed_index)
        ix = slice(start, end + 1)
        d, q, fill, base = t.direction, t.quantity, t.entry_fill_price, t.entry_nav - t.entry_fee
        nav[ix] = base + d * q * (bars.close.to_numpy(float)[ix] - fill)
        op[ix] = base + d * q * (bars.open.to_numpy(float)[ix] - fill)
        adverse = bars.low if d == 1 else bars.high
        intraday[ix] = base + d * q * (adverse.to_numpy(float)[ix] - fill)
        breaches[ix] = intraday[ix] <= 0
        entries[start] = True
        fees[start] += t.entry_fee
        slip[start] += t.entry_slippage_cost
        nav[end:] = t.terminal_nav_after_fee_slippage
        op[end + 1:] = intraday[end + 1:] = t.terminal_nav_after_fee_slippage
        if t.completed:
            exits[end] = True
            fees[end] += t.exit_fee
            slip[end] += t.exit_slippage_cost
            mark[end] = t.exit_fill_price
            actions[start:end] = np.where(selected[start:end], "IGNORED_OPEN_POSITION", "NOT_SELECTED")
        else:
            actions[start:end + 1] = np.where(selected[start:end + 1], "IGNORED_OPEN_POSITION", "NOT_SELECTED")
        if t.terminal_nav_after_fee_slippage <= 0:
            halted[end:] = True
            mark[end + 1:] = op[end + 1:] = intraday[end + 1:] = np.nan
            actions[end:] = np.where(selected[end:], "IGNORED_HALTED", "NOT_SELECTED")
    checks.close("sample_close_nav", eq.equity_after_fee_slippage, nav)
    checks.close("sample_entry_exit_fee", eq.fee_paid, fees)
    checks.close("sample_slippage", eq.slippage_cost, slip)
    checks.close("sample_open_nav", eq.equity_open_after_fee_slippage, op)
    checks.close("sample_intraday_min", eq.min_intraday_equity_after_entry_fee, intraday)
    checks.close("sample_mark", eq.mark_price, mark)
    checks.require("sample_entry_flags", np.array_equal(eq.entry_executed.to_numpy(bool), entries))
    checks.require("sample_exit_flags", np.array_equal(eq.exit_executed.to_numpy(bool), exits))
    checks.require("sample_breach_flags", np.array_equal(eq.intraday_insolvency_breach.to_numpy(bool), breaches))
    checks.require("sample_halt_flags", np.array_equal(eq.halted.to_numpy(bool), halted))
    checks.require("sample_signal_actions", np.array_equal(eq.signal_action.to_numpy(str), actions))
    previous = np.r_[1., nav[:-1]]
    returns = np.full(n, np.nan)
    np.divide(nav, previous, out=returns, where=previous > 0)
    returns -= 1
    checks.close("sample_daily_returns", eq.daily_return_after_fee_slippage, returns)
    checks.close("sample_drawdown", eq.drawdown_after_fee_slippage, nav / np.maximum.accumulate(np.r_[1., nav])[1:] - 1)
    return {"rows": n, "trades": len(trades), "final_equity_after_fee_slippage": float(nav[-1])}


def choose_samples(summary):
    """每组每成本固定最多交易账户，加三类例外；不以样本估计发生率。"""
    chosen = {}
    for group in GROUPS:
        for cost in COSTS:
            ss = summary.loc[summary.group.eq(group) & summary.cost.eq(cost)]
            for label, mask in [("most_entries", np.ones(len(ss), bool)), ("censored", ss.censored_open_trades.gt(0)),
                                ("halted", ss.halted), ("intraday_recovered", ss.intraday_insolvency_breach & ~ss.halted)]:
                candidates = ss.loc[mask].sort_values(["entered_trades", "account_id"], ascending=[False, True])
                if len(candidates):
                    row = candidates.iloc[0]
                    chosen.setdefault(row.account_id, {"account_id": row.account_id, "symbol": row.symbol,
                        "research_segment_id": str(row.research_segment_id), "group": group, "cost": cost, "criteria": []})["criteria"].append(label)
    return list(chosen.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="p2-capture")
    parser.add_argument("--audit-id", default="p2-independent-audit")
    args = parser.parse_args()
    if any(Path(v).name != v or v in (".", "..") for v in (args.run_id, args.audit_id)):
        raise ValueError("Run/audit IDs must be single directory/file names")
    p2 = FAMILY / "artifacts" / args.run_id
    out = FAMILY / "artifacts" / f"{args.audit_id}.json"
    report_path = FAMILY / "diagnostics" / f"{args.audit_id}.md"
    if out.exists() or report_path.exists():
        raise FileExistsError("Audit evidence exists; use a new audit-id")
    checks = Checks()
    panel, complete, manifest, em = verify_retained(p2, checks)
    trades = pd.read_csv(p2 / "trades.csv.gz", dtype={"research_segment_id": str})
    summary = pd.read_csv(p2 / "summary.csv", dtype={"research_segment_id": str})
    aggregate = pd.read_csv(p2 / "aggregate.csv")
    exceptions = pd.read_csv(p2 / "position-exceptions.csv.gz", dtype={"research_segment_id": str})
    for name, frame in [("trades.csv.gz", trades), ("summary.csv", summary), ("aggregate.csv", aggregate), ("position-exceptions.csv.gz", exceptions)]:
        checks.close("table_row_receipts", len(frame), manifest["files"][name]["rows"])
    expected_exceptions = trades.loc[~trades.completed | trades.intraday_insolvency_breach].reset_index(drop=True)
    pd.testing.assert_frame_equal(exceptions, expected_exceptions)
    checks.close("completion_trade_counts", [complete["accounts"], complete["trade_rows"], complete["exception_rows"], complete["completed_trades"], complete["censored_open_trades"], complete["halted_open_trades"]], [len(summary), len(trades), len(exceptions), summary.completed_trades.sum(), summary.censored_open_trades.sum(), summary.halted_open_trades.sum()])
    ledger = audit_ledger(trades, summary, panel, checks)
    checks.close("completion_segment_count", complete["independent_segments"], ledger["independent_segments"])
    audit_aggregates(summary, aggregate, checks)
    samples, sampled, segs = choose_samples(summary), [], _segment_frames(panel)
    for relative, filemeta in em["files"].items():
        targets = {r["account_id"]: r for r in samples if r["group"] == filemeta["group"] and r["cost"] == filemeta["cost"]}
        parts = {a: [] for a in targets}
        actual_rows, account_rows = 0, Counter()
        for chunk in pd.read_csv(p2 / relative, chunksize=100000, dtype={"research_segment_id": str}):
            actual_rows += len(chunk)
            account_rows.update(chunk.account_id.value_counts().to_dict())
            checks.require("all_equity_file_group_cost", chunk.group.eq(filemeta["group"]).all() and chunk.cost.eq(filemeta["cost"]).all())
            for account in targets:
                selected = chunk.loc[chunk.account_id.eq(account)]
                if len(selected):
                    parts[account].append(selected)
        checks.close("all_equity_file_dimensions", [actual_rows, len(account_rows)], [filemeta["rows"], filemeta["accounts"]])
        ss = summary.loc[summary.group.eq(filemeta["group"]) & summary.cost.eq(filemeta["cost"])]
        checks.require("all_equity_account_inventory", set(account_rows) == set(ss.account_id))
        checks.close("all_equity_account_row_counts", [account_rows[a] for a in ss.account_id], ss.n_bars)
        for account, sample in targets.items():
            eq = pd.concat(parts[account], ignore_index=True)
            bars = segs[str(sample["symbol"]), sample["research_segment_id"]]
            pt = trades.loc[trades.account_id.eq(account)].reset_index(drop=True)
            result = audit_equity_account(eq, pt, bars, sample["group"], checks)
            sr = summary.loc[summary.account_id.eq(account)].iloc[0]
            checks.close("sample_summary_drawdown", sr.max_drawdown_after_fee_slippage, -eq.drawdown_after_fee_slippage.min())
            sampled.append({**sample, **result})
    # 验证审计期间未变更输入或输出，结果不能附着在混合版本上。
    for relative, meta in manifest["files"].items():
        checks.require("end_output_hash", sha(contained(p2, relative)) == meta["sha256"])
    for relative, digest in _json(p2 / "started.json")["pinned_files"].items():
        checks.require("end_source_pin", sha(contained(REPO, relative)) == digest)
    report = {"status": "PASS_RETAINED_ACCOUNTING_AUDIT", "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "artifact_manifest_sha256": sha(p2 / "artifact-manifest.json"), "completed_sha256": sha(p2 / "completed.json"),
              "audit_source_sha256": sha(Path(__file__)), "full_ledger": ledger, "checks": checks.metrics,
              "equity_sample_accounts": sampled, "sampled_equity_rows": sum(v["rows"] for v in sampled),
              "total_equity_rows": complete["equity_rows"], "exception_rows": len(exceptions),
              "scope": "全部文件hash/表行数/交易资金公式/源K线/账户信号时序；日权益数值按每组成本及例外账户抽样重构",
              "not_checked": ["未逐行重构全部账户日权益数值", "不重新计算强度、P、M和P1价格标签", "未验证资金费、强平、成交可得性和容量", "不把独立连续段分布连接成跨币组合或年化收益"],
              "economic_rows": aggregate.loc[aggregate.cost.eq("base"), ["group", "segments_with_entries", "entered_trades", "completed_trades", "censored_open_trades", "halted_segments", "segments_with_intraday_insolvency_breach", "terminal_mark_return_median_entered_segments", "profitable_terminal_mark_fraction_entered_segments", "median_max_drawdown_entered_segments"]].to_dict("records")}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    lines = ["# BIN-1D-TSPR P2 独立核算审计", "", "状态：PASS_RETAINED_ACCOUNTING_AUDIT。仅表示已检查范围内保留产物自洽。", "",
             f"完整核对 {len(trades):,} 条交易、{len(summary):,} 个独立段账户；逐组逐成本和例外抽样复算 {len(sampled)} 个账户、{report['sampled_equity_rows']:,} 条日权益，全部日权益共 {complete['equity_rows']:,} 条。", "",
             f"事前信号入场中，保留 {ledger['future_incomplete_entered']:,} 条未来20日不完整入场记录（两个成本场景重复计算，不是独立事件数）。逐账户检查每次空仓可用信号的下一开盘接续，不以 valid20 筛掉未成熟入场。", "",
             "逐笔使用固定数量、含入场费预算、线性多空盈亏和双边真实成交名义费用；截尾不造退出收费，经济NAV<=0保持不利失败快照。日内触及非正权益即使收盘恢复也单独标识；这不是交易所强平模拟。", "",
             "下表分母是发生过入场的独立连续段账户，段长度不同、币种相关；期末资金标记可含未完成持仓或失败快照。不能解释为一条跨币投资组合收益、年化收益或完整净利润。", "",
             "| 组 | 有入场段 | 期末资金标记收益中位数 | 期末NAV>1占比 | 收盘亏尽段 | 日内非正边界段 |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in report["economic_rows"]:
        lines.append(f"| {row['group']} | {row['segments_with_entries']} | {row['terminal_mark_return_median_entered_segments']:.2%} | {row['profitable_terminal_mark_fraction_entered_segments']:.2%} | {row['halted_segments']} | {row['segments_with_intraday_insolvency_breach']} |")
    lines += ["", "未查全范围：全部日权益数值只做分层例外抽样；不重算P1信号或标签；未核资金费、保证金强平、成交可得性与容量。两个成本场景不是独立研究样本。事件均值与顺序账户的统计对象不同，不能相乘或互换。", "",
              f"[机器审计证据](../artifacts/{out.name})；[P2产物收据](../artifacts/{args.run_id}/artifact-manifest.json)。", ""]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": report["status"], "ledger": ledger, "sample_accounts": len(sampled), "sample_rows": report["sampled_equity_rows"], "report": str(report_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
