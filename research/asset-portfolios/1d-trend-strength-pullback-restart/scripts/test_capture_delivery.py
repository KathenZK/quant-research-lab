"""只用合成行情核对新入口/独立审计；不读取本家族真实研究产物。"""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

import run_capture as producer
import audit_capture as audit


def frame(prices, symbol="SYNTH", segment="1"):
    x = np.asarray(prices, float)
    f = pd.DataFrame({"symbol": symbol, "research_segment_id": segment,
                      "ts": pd.date_range("2020-01-01", periods=len(x), freq="D", tz="UTC"),
                      "open": x, "high": x, "low": x, "close": x, "volume": 1.,
                      "eligible": True, "feature_valid": True, "valid20": False})
    f["signal_time"] = f.ts + pd.Timedelta(days=1)
    for group in producer.GROUPS:
        f[group] = np.arange(len(x)) % 3 == 0
    return f


def dataset():
    # 三个段分别含20日退出与段尾截尾、空头日内亏尽后恢复、收盘不利亏尽。
    ordinary = frame(100 + np.arange(67), "SYNTH", "1")
    recovery = frame([100.] * 27, "SYNTH", "2")
    recovery["ts"] += pd.Timedelta(days=100)
    recovery["signal_time"] = recovery.ts + pd.Timedelta(days=1)
    recovery.loc[3, "high"] = 230
    failure = frame([100, 100, 250, 80, 70, 60], "FAIL", "1")
    return pd.concat([ordinary, recovery, failure], ignore_index=True)


def synth_run(panel):
    summaries, trades, equities = [], [], {}
    for (symbol, segment), bars in panel.groupby(["symbol", "research_segment_id"], sort=False):
        bars = bars.reset_index(drop=True)
        for group in producer.GROUPS:
            for cost, rates in producer.COSTS.items():
                result = producer.run_hold20_account(bars, bars[group].to_numpy(bool), 1 if group.endswith("LONG") else -1, **rates)
                checked = producer.validate_result(result, len(bars), int(bars[group].sum()))
                identity = hashlib.sha256(json.dumps([symbol, str(segment), group, cost], ensure_ascii=False).encode()).hexdigest()
                meta = dict(zip(producer.META_COLUMNS, [symbol, str(segment), group, cost, identity]))
                row = {**meta, **result["summary"], "censored_positive_terminal_marks": checked["censored_positive_terminal_marks"]}
                summaries.append(row)
                trades.append(result["trades"].assign(**meta))
                equities[identity] = result["equity"].assign(**meta)
    return pd.concat(trades, ignore_index=True), pd.DataFrame(summaries), equities


def test_full_independent_synthetic_ledger_and_every_synthetic_equity():
    panel = dataset()
    trades, summaries, equities = synth_run(panel)
    checks = audit.Checks()
    result = audit.audit_ledger(trades, summaries, panel, checks)
    assert result["future_incomplete_entered"] == len(trades)
    assert summaries.halted.any()
    assert (summaries.intraday_insolvency_breach & ~summaries.halted).any()
    assert summaries.censored_open_trades.sum() > 0
    audit.audit_aggregates(summaries, producer.aggregate_summaries(summaries), checks)
    for s in summaries.itertuples(index=False):
        eq = equities[s.account_id]
        bars = panel.loc[panel.symbol.eq(s.symbol) & panel.research_segment_id.eq(s.research_segment_id)].reset_index(drop=True)
        pt = trades.loc[trades.account_id.eq(s.account_id)].reset_index(drop=True)
        audit.audit_equity_account(eq, pt, bars, s.group, checks)
    assert all(x["failures"] == 0 for x in checks.metrics.values())


@pytest.mark.parametrize("kind", ["entry_fee", "reciprocal_short", "fake_censor_exit", "double_count_fee", "entry_future_filter", "source_open", "short_intraday_boundary", "ignored_signal", "signal_timing"])
def test_independent_ledger_rejects_economic_or_timing_corruption(kind):
    panel = dataset()
    tr, s, _ = synth_run(panel)
    if kind == "entry_fee":
        tr.loc[0, "entry_fee"] = 0
    elif kind == "reciprocal_short":
        i = tr.loc[tr.direction.eq(-1) & tr.completed].index[0]
        t = tr.loc[i]
        tr.loc[i, "price_pnl"] = t.entry_nav * (t.entry_fill_price / t.terminal_mark_price - 1)
    elif kind == "fake_censor_exit":
        tr.loc[tr.status.eq("OPEN_CENSORED_SEGMENT_END"), "exit_fee"] = .001
    elif kind == "double_count_fee":
        s.loc[0, "total_fees"] *= 2
    elif kind == "entry_future_filter":
        # 即便伪造对应汇总使纯代数看似一致，完整空仓信号机会仍然不能消失。
        account = s.account_id.iloc[0]
        tr = tr.loc[~tr.account_id.eq(account)].copy()
        idx = s.index[s.account_id.eq(account)][0]
        for k in ["entered_trades", "completed_trades", "censored_open_trades", "total_fees", "total_slippage_cost", "censored_positive_terminal_marks"]:
            s.loc[idx, k] = 0
        s.loc[idx, "final_equity_after_fee_slippage"] = 1
        s.loc[idx, "total_return_after_fee_slippage"] = 0
    elif kind == "source_open":
        panel.loc[1, "open"] = 102
    elif kind == "short_intraday_boundary":
        tr.loc[tr.intraday_insolvency_breach, "intraday_insolvency_breach"] = False
    elif kind == "ignored_signal":
        tr.loc[0, "ignored_signals"] += 1
    else:
        tr.loc[0, "signal_close_ts"] += pd.Timedelta(days=1)
    with pytest.raises(ValueError):
        audit.audit_ledger(tr, s, panel, audit.Checks())


@pytest.mark.parametrize("column", ["equity_after_fee_slippage", "fee_paid", "min_intraday_equity_after_entry_fee", "daily_return_after_fee_slippage", "signal_action", "entry_executed"])
def test_independent_equity_rejects_saved_row_corruption(column):
    panel = frame(100 + np.arange(25))
    tr, s, equities = synth_run(panel)
    account = s.account_id.iloc[0]
    eq = equities[account].copy()
    if column == "signal_action":
        eq.loc[1, column] = "NOT_AN_ACCOUNT_ACTION"
    elif column == "entry_executed":
        eq.loc[1, column] = False
    else:
        eq.loc[1, column] += .01
    with pytest.raises(ValueError):
        audit.audit_equity_account(eq, tr.loc[tr.account_id.eq(account)], panel, s.group.iloc[0], audit.Checks())


def test_no_entry_accounts_remain_in_all_segment_denominator():
    panel = frame([100.] * 5)
    panel[list(producer.GROUPS)] = False
    tr, s, equities = synth_run(panel)
    a = producer.aggregate_summaries(s)
    assert a.segments.eq(1).all() and a.segments_with_entries.eq(0).all()
    assert a.terminal_mark_return_median_all_segments.eq(0).all()
    assert a.terminal_mark_return_median_entered_segments.isna().all()
    audit.audit_ledger(tr, s, panel, audit.Checks())
    audit.audit_aggregates(s, a, audit.Checks())
    first = s.iloc[0]
    audit.audit_equity_account(equities[first.account_id], tr, panel, first.group, audit.Checks())


def test_active_segment_profit_denominator_is_not_positive_nav_or_all_segments():
    panel = frame(100 + np.arange(25))
    idle = frame([100.] * 5, symbol="IDLE")
    idle[list(producer.GROUPS)] = False
    tr, s, _ = synth_run(pd.concat([panel, idle], ignore_index=True))
    a = producer.aggregate_summaries(s)
    long = a.loc[a.group.eq("ALL_LONG") & a.cost.eq("base")].iloc[0]
    assert long.profitable_terminal_mark_fraction_entered_segments == 1
    assert long.profitable_terminal_mark_fraction_all_segments == .5
    assert long.positive_final_equity_fraction_all_segments == 1
    broken = a.copy()
    broken.loc[0, "profitable_terminal_mark_fraction_entered_segments"] = .5
    with pytest.raises(ValueError):
        audit.audit_aggregates(s, broken, audit.Checks())


def setup_frozen_fixture(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    family = repo / "research/asset-portfolios/synth"
    kernel = repo / "research/_shared-kernels/synth/v1"
    for module in (producer, audit):
        monkeypatch.setattr(module, "REPO", repo)
        monkeypatch.setattr(module, "FAMILY", family)
        monkeypatch.setattr(module, "KERNEL", kernel)
    files = {}
    for name in ("specs/input-contract.md", "specs/research-contract.md", "specs/statistics-contract.md", "scripts/run_capture.py", "scripts/audit_capture.py"):
        path = family / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("SYNTHETIC FIXTURE ONLY\n")
        files[str(path.relative_to(repo))] = producer.sha(path)
    kernel.mkdir(parents=True)
    (kernel / "capture.py").write_text("# frozen synthetic placeholder; never executed\n")
    capture_hash = producer.sha(kernel / "capture.py")
    for module in (producer, audit):
        monkeypatch.setattr(module, "CAPTURE_SHA256", capture_hash)
    files[str((kernel / "capture.py").relative_to(repo))] = capture_hash
    (kernel / "manifest.json").write_text(json.dumps({"files": {"capture.py": capture_hash}}))
    lock = {"files": files, "kernel_manifest": {"path": str((kernel / "manifest.json").relative_to(repo)), "sha256": producer.sha(kernel / "manifest.json")}}
    (family / "specs/computation-lock.json").write_text(json.dumps(lock))
    return repo, family, kernel


@pytest.mark.parametrize("tamper", ["none", "contract", "kernel", "undeclared_kernel", "lock_missing_chain", "escape"])
def test_frozen_lock_rejects_changes_before_panel_loading(tmp_path, monkeypatch, tamper):
    repo, family, kernel = setup_frozen_fixture(tmp_path, monkeypatch)
    path = family / "specs/computation-lock.json"
    lock = json.loads(path.read_text())
    if tamper == "contract":
        (family / "specs/research-contract.md").write_text("changed")
    elif tamper == "kernel":
        (kernel / "capture.py").write_text("changed")
    elif tamper == "undeclared_kernel":
        (kernel / "other.py").write_text("undeclared")
    elif tamper == "lock_missing_chain":
        del lock["files"][str((family / "scripts/audit_capture.py").relative_to(repo))]
        path.write_text(json.dumps(lock))
    elif tamper == "escape":
        lock["files"]["../escape"] = "unreachable"
        path.write_text(json.dumps(lock))
    if tamper == "none":
        assert producer.verify_computation_lock()["lock_sha256"] == producer.sha(path)
    else:
        with pytest.raises(ValueError):
            producer.verify_computation_lock()


def write_panel_fixture(family, panel):
    out = family / "artifacts/p1-research"
    out.mkdir(parents=True)
    inp = family / "artifacts/p0-inputs/frame-manifest.json"
    inp.parent.mkdir(parents=True)
    inp.write_text(json.dumps({"synthetic": True}))
    path = out / "panel.pkl.gz"
    panel.to_pickle(path, compression="gzip")
    lock = json.loads((family / "specs/computation-lock.json").read_text())
    manifest = {"path": path.name, "sha256": producer.sha(path), "rows": len(panel), "symbols": panel.symbol.nunique(),
                "pins": lock["files"], "input_manifest_sha256": producer.sha(inp),
                "computation_lock_sha256": producer.sha(family / "specs/computation-lock.json")}
    (out / "panel-manifest.json").write_text(json.dumps(manifest))
    (out / "summary.json").write_text(json.dumps({"status": "FIXED_HISTORY_STATE_PANEL_COMPLETE", "rows": len(panel),
        "files": {"panel.pkl.gz": producer.sha(path), "panel-manifest.json": producer.sha(out / "panel-manifest.json")}}))
    return out


@pytest.mark.parametrize("tamper", ["none", "future_validity_only", "mismatched_hash", "unfinished", "ineligible_signal", "duplicate", "timezone", "unordered"])
def test_panel_boundary_and_future_validity_not_an_entry_filter(tmp_path, monkeypatch, tamper):
    _, family, _ = setup_frozen_fixture(tmp_path, monkeypatch)
    panel = frame([100.] * 25)
    if tamper == "future_validity_only":
        panel["valid20"] = False
    elif tamper == "ineligible_signal":
        panel.loc[0, "feature_valid"] = False
    elif tamper == "duplicate":
        panel.loc[1, "ts"] = panel.loc[0, "ts"]
        panel["signal_time"] = panel.ts + pd.Timedelta(days=1)
    elif tamper == "timezone":
        panel["ts"] = panel.ts.dt.tz_localize(None)
    elif tamper == "unordered":
        panel = panel.iloc[::-1]
    out = write_panel_fixture(family, panel)
    if tamper == "mismatched_hash":
        (out / "panel.pkl.gz").write_bytes(b"tampered; must never deserialize")
    elif tamper == "unfinished":
        (out / "summary.json").write_text(json.dumps({"status": "INCOMPLETE"}))
    if tamper in ("none", "future_validity_only"):
        loaded, meta = producer.load_panel("p1-research")
        assert not meta["valid20_used_for_entry"]
        assert loaded.ALL_LONG.any() and not loaded.valid20.any()
    else:
        with pytest.raises(ValueError):
            producer.load_panel("p1-research")


def test_full_synthetic_file_delivery_and_independent_audit(tmp_path, monkeypatch):
    _, family, _ = setup_frozen_fixture(tmp_path, monkeypatch)
    write_panel_fixture(family, dataset())
    monkeypatch.setattr("sys.argv", ["run_capture.py"])
    assert producer.main() == 0
    monkeypatch.setattr("sys.argv", ["audit_capture.py"])
    assert audit.main() == 0
    result = json.loads((family / "artifacts/p2-independent-audit.json").read_text())
    assert result["status"] == "PASS_RETAINED_ACCOUNTING_AUDIT"
    assert result["sampled_equity_rows"] > 0
    assert result["exception_rows"] > 0
    assert (family / "diagnostics/p2-independent-audit.md").is_file()
    with pytest.raises(FileExistsError):
        audit.main()
