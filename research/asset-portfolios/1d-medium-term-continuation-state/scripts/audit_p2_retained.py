"""只读重构保留P1/P2产物；不生成信号、不重跑账户或策略实验。"""

from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

F = Path(__file__).resolve().parents[1]
P1 = F / "artifacts/p1-research"
P2 = F / "artifacts/p2-capture"


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(2**20), b""):
            h.update(b)
    return h.hexdigest()


out = {}
manifest = json.loads((P2 / "artifact-manifest.json").read_text())
checks = {str(p): sha(P2 / p) == v["sha256"] for p, v in manifest["files"].items()}
complete = json.loads((P2 / "completed.json").read_text())
checks["artifact_manifest_anchor"] = (
    sha(P2 / "artifact-manifest.json") == complete["artifact_manifest_sha256"]
)
started = json.loads((P2 / "started.json").read_text())
checks.update(
    {f"pin:{p}": sha(F / p) == digest for p, digest in started["pinned_files"].items()}
)
out["file_hashes"] = {
    "checked": len(checks),
    "failed": [p for p, v in checks.items() if not v],
}
assert all(checks.values()), out["file_hashes"]
panel = pd.read_pickle(P1 / "panel.pkl.gz", compression="gzip")
tr = pd.read_csv(P2 / "trades.csv.gz")
s = pd.read_csv(P2 / "summary.csv").set_index("account_id")
a = pd.read_csv(P2 / "aggregate.csv")
point = pd.read_csv(P1 / "point-summary.csv").set_index("group")
metrics = {}


def check(name, x, y, rtol=1e-10, atol=1e-10):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isclose(x, y, rtol=rtol, atol=atol, equal_nan=True)
    metrics[name] = {
        "n": int(ok.size),
        "max_abs_error": float(np.nanmax(np.abs(x - y)))
        if ok.size and np.isfinite(x - y).any()
        else 0.0,
        "failures": int((~ok).sum()),
    }
    assert ok.all(), (name, metrics[name])


assert s.index.is_unique and len(s) == 13180
slip = tr.cost.map({"base": 0.0004, "stress": 0.0008}).to_numpy()
check(
    "entry_fill",
    tr.entry_fill_price,
    tr.entry_reference_price * (1 + tr.direction * slip),
)
check("entry_quantity_budget", tr.entry_notional + tr.entry_fee, tr.entry_nav)
check("entry_notional", tr.entry_notional, tr.quantity * tr.entry_fill_price)
check("entry_fee", tr.entry_fee, 0.001 * tr.entry_notional)
check(
    "price_pnl_linear",
    tr.price_pnl,
    tr.direction * tr.quantity * (tr.terminal_mark_price - tr.entry_fill_price),
)
check(
    "net_trade_pnl",
    tr.pnl_after_fee_slippage,
    tr.price_pnl - tr.entry_fee - tr.exit_fee,
)
check(
    "terminal_nav",
    tr.terminal_nav_after_fee_slippage,
    tr.entry_nav + tr.pnl_after_fee_slippage,
)
check(
    "entry_slippage_cost",
    tr.entry_slippage_cost,
    tr.quantity * (tr.entry_fill_price - tr.entry_reference_price).abs(),
)
check("entry_after_signal", tr.entry_index, tr.signal_index + 1)
completed = tr.completed
natural = tr.loc[completed]
check("natural_20bars", natural.holding_bars_observed, np.full(len(natural), 20))
check("natural_exit_index", natural.exit_index, natural.entry_index + 19)
check(
    "natural_exit_fill",
    natural.exit_fill_price,
    natural.exit_reference_price
    * (1 - natural.direction * natural.cost.map({"base": 0.0004, "stress": 0.0008})),
)
check("natural_exit_fee", natural.exit_fee, 0.001 * natural.exit_notional)
check(
    "natural_exit_notional",
    natural.exit_notional,
    natural.quantity * natural.exit_fill_price,
)
check(
    "natural_20day_duration",
    (
        pd.to_datetime(natural.exit_ts, utc=True)
        - pd.to_datetime(natural.entry_ts, utc=True)
    ).dt.total_seconds(),
    np.full(len(natural), 20 * 86400),
)
unfinished = tr.loc[~completed]
assert (
    pd.to_datetime(unfinished.exit_ts, utc=True, errors="coerce").isna().all()
    and unfinished.exit_fill_price.isna().all()
    and unfinished.exit_fee.eq(0).all()
)
assert tr.completed.eq(tr.status.eq("COMPLETED_HORIZON")).all()
by = tr.groupby("account_id").agg(
    pnl=("pnl_after_fee_slippage", "sum"),
    fees=("total_fees", "sum"),
    slippage=("total_slippage_cost", "sum"),
    entered=("trade_id", "size"),
    completed=("completed", "sum"),
)
by = by.reindex(s.index, fill_value=0)
check("summary_nav_from_all_trades", s.final_equity_after_fee_slippage, 1 + by.pnl)
check("summary_fees_from_all_trades", s.total_fees, by.fees)
check("summary_slippage_from_all_trades", s.total_slippage_cost, by.slippage)
check("summary_entered", s.entered_trades, by.entered)
check("summary_completed", s.completed_trades, by.completed)
check(
    "signal_disposition_partition",
    s.selected_signals,
    s.entered_trades
    + s.ignored_signals_while_open
    + s.ignored_signals_after_halt
    + s.pending_signals_at_segment_end,
)
# 正序逐持仓列表中的资金承接和无重叠；不是重跑信号/账户。
prev = tr.groupby("account_id", sort=False).shift()
first = tr.groupby("account_id", sort=False).cumcount().eq(0)
check(
    "trade_capital_sequential",
    tr.entry_nav,
    np.where(first, 1.0, prev.terminal_nav_after_fee_slippage),
)
assert (
    tr.loc[~first, "entry_index"].to_numpy() > prev.loc[~first, "exit_index"].to_numpy()
).all()
# 用已保存观察面板独立核对入场信号及未来不完整入场的留存。
lookup = panel.set_index(["symbol", "ts"])
keys = pd.MultiIndex.from_arrays(
    [tr.symbol, pd.to_datetime(tr.signal_bar_ts, utc=True)]
)
at_signal = lookup.reindex(keys).reset_index(drop=True)
assert at_signal.feature_valid.all()
assert all(at_signal.loc[tr.group.eq(g).to_numpy(), g].all() for g in point.index)
invalid_entered = tr.loc[~at_signal.valid20.to_numpy()]
out["future_incomplete_entered"] = {
    "all_costs": len(invalid_entered),
    "base": int(invalid_entered.cost.eq("base").sum()),
    "status_by_cost": invalid_entered.groupby(["cost", "status"]).size().to_dict(),
}
# 每组合摘要分母与量化分布独立重算。
for _, ar in a.iterrows():
    ss = s.loc[s.group.eq(ar.group) & s.cost.eq(ar.cost)]
    active = ss.loc[ss.entered_trades > 0]
    for col in [
        "selected_signals",
        "entered_trades",
        "completed_trades",
        "censored_open_trades",
        "halted_open_trades",
        "ignored_signals_while_open",
        "ignored_signals_after_halt",
        "pending_signals_at_segment_end",
    ]:
        assert ss[col].sum() == ar[col]
    assert len(ss) == ar.segments and len(active) == ar.segments_with_entries
    assert ss.halted.sum() == ar.halted_segments
    assert (
        ss.intraday_insolvency_breach.sum()
        == ar.segments_with_intraday_insolvency_breach
    )
    check(
        f"aggregate_active_median:{ar.group}:{ar.cost}",
        [ar.terminal_mark_return_median_entered_segments],
        [np.median(active.final_equity_after_fee_slippage - 1)],
    )
    check(
        f"aggregate_active_dd:{ar.group}:{ar.cost}",
        [ar.median_max_drawdown_entered_segments],
        [np.median(active.max_drawdown_after_fee_slippage)],
    )
    check(
        f"aggregate_active_profit_fraction:{ar.group}:{ar.cost}",
        [ar.profitable_terminal_mark_fraction_entered_segments],
        [(active.final_equity_after_fee_slippage > 1).mean()],
    )
for group, pr in point.iterrows():
    pp = panel.loc[panel[group] & panel.valid20]
    d = 1 if group.endswith("LONG") else -1
    assert len(pp) == pr.complete20
    for cost, sliprate in [("base", 0.0004), ("stress", 0.0008)]:
        ep = pp.entry_open * (1 + d * sliprate)
        xp = pp.exit_close20 * (1 - d * sliprate)
        q = 1 / ep
        returns = d * q * (xp - ep) - 0.001 * q * (ep + xp)
        check(
            f"event_mean:{group}:{cost}",
            [pr[f"{cost}_event_mean_after_fee_slippage"]],
            [returns.mean()],
        )
    check(f"point_gross_mean:{group}", [pr.mean_return20], [(d * pp.ret20).mean()])
# 保存便于报告的抽样账户清单：特意覆盖失败/边界/截尾，但不以它们估计频率。
base = s.loc[s.cost.eq("base")]
chosen = []
for group, criterion in [
    ("M_LONG", "long"),
    ("M_SHORT", "halt"),
    ("S1_SHORT", "breach_recovery"),
    ("S1_LONG", "censored"),
]:
    ss = base.loc[base.group.eq(group)]
    if criterion == "halt":
        ss = ss.loc[ss.halted].sort_values("final_equity_after_fee_slippage")
    elif criterion == "breach_recovery":
        ss = ss.loc[ss.intraday_insolvency_breach & ~ss.halted].sort_values(
            "final_equity_after_fee_slippage", ascending=False
        )
    elif criterion == "censored":
        ss = ss.loc[ss.censored_open_trades > 0].sort_values(
            "entered_trades", ascending=False
        )
    else:
        ss = ss.loc[ss.entered_trades > 0].sort_values(
            "entered_trades", ascending=False
        )
    selected = ss.iloc[0]
    chosen.append(
        {
            "account_id": selected.name,
            "group": group,
            "symbol": selected.symbol,
            "segment": selected.research_segment_id,
            "criterion": criterion,
            "nav": selected.final_equity_after_fee_slippage,
        }
    )
out["sample_accounts"] = chosen
out["full_ledger"] = {
    "trade_rows": len(tr),
    "completed": int(completed.sum()),
    "unfinished": len(unfinished),
    "accounts": len(s),
    "checks": metrics,
}
out["economic_rows"] = a.loc[
    a.cost.eq("base"),
    [
        "group",
        "segments_with_entries",
        "halted_segments",
        "segments_with_intraday_insolvency_breach",
        "terminal_mark_return_median_entered_segments",
        "median_max_drawdown_entered_segments",
        "profitable_terminal_mark_fraction_entered_segments",
    ],
].to_dict("records")
# JSON tuple keys stringify for terminal output.
out["future_incomplete_entered"]["status_by_cost"] = {
    f"{k[0]}:{k[1]}": int(v)
    for k, v in out["future_incomplete_entered"]["status_by_cost"].items()
}

print(
    json.dumps(
        {k: v for k, v in out.items() if k not in ["full_ledger", "economic_rows"]},
        indent=2,
        default=str,
    )
)
print(
    "CHECKS",
    len(metrics),
    "WORST_ABS_ERROR",
    max(v["max_abs_error"] for v in metrics.values()),
)
print("ALL_LEDGER_ROWS", len(tr), "ACCOUNTS", len(s))

report = out
results = []
for sample in report["sample_accounts"]:
    selected = []
    for chunk in pd.read_csv(
        F / f"artifacts/p2-capture/equity/{sample['group']}-base.csv.gz",
        chunksize=100000,
    ):
        cut = chunk.loc[chunk.account_id.eq(sample["account_id"])]
        if len(cut):
            selected.append(cut)
    eq = pd.concat(selected, ignore_index=True)
    pt = tr.loc[tr.account_id.eq(sample["account_id"])].reset_index(drop=True)
    bars = panel.loc[
        panel.symbol.eq(sample["symbol"])
        & panel.research_segment_id.eq(sample["segment"])
    ].reset_index(drop=True)
    assert len(eq) == len(bars)
    expected_nav = []
    expected_fee = []
    expected_min = []
    expected_open = []
    for i, row in eq.iterrows():
        eligible = pt.loc[pt.entry_index <= i]
        fee = (
            pt.loc[pt.entry_index.eq(i), "entry_fee"].sum()
            + pt.loc[pt.completed & pt.exit_index.eq(i), "exit_fee"].sum()
        )
        expected_fee.append(fee)
        if eligible.empty:
            expected_nav.append(1.0)
            expected_min.append(1.0)
            expected_open.append(1.0)
            continue
        t = eligible.iloc[-1]
        if i > t.last_observed_index:
            expected_nav.append(t.terminal_nav_after_fee_slippage)
            after_halt = (
                t.status == "OPEN_HALTED_NONPOSITIVE_CLOSE_NAV"
                or t.terminal_nav_after_fee_slippage <= 0
            )
            expected_min.append(
                np.nan if after_halt else t.terminal_nav_after_fee_slippage
            )
            expected_open.append(
                np.nan if after_halt else t.terminal_nav_after_fee_slippage
            )
            continue
        b = bars.iloc[i]
        base = t.entry_nav - t.entry_fee
        expected_open.append(
            base + t.direction * t.quantity * (b.open - t.entry_fill_price)
        )
        adverse = b.low if t.direction == 1 else b.high
        expected_min.append(
            base + t.direction * t.quantity * (adverse - t.entry_fill_price)
        )
        if t.completed and i == t.exit_index:
            nav = (
                base
                + t.direction * t.quantity * (t.exit_fill_price - t.entry_fill_price)
                - t.exit_fee
            )
        else:
            nav = base + t.direction * t.quantity * (b.close - t.entry_fill_price)
        expected_nav.append(nav)
    err = {}
    for col, expected in [
        ("equity_after_fee_slippage", expected_nav),
        ("fee_paid", expected_fee),
        ("min_intraday_equity_after_entry_fee", expected_min),
        ("equity_open_after_fee_slippage", expected_open),
    ]:
        expected = np.asarray(expected, float)
        actual = eq[col].to_numpy(float)
        assert np.isclose(
            actual, expected, rtol=1e-10, atol=1e-10, equal_nan=True
        ).all(), (sample["symbol"], col)
        err[col] = float(np.nanmax(np.abs(actual - expected)))
    assert (
        eq.signal_selected.to_numpy(bool).tolist()
        == bars[sample["group"]].to_numpy(bool).tolist()
    )
    assert eq.observed_close.to_numpy().tolist() == bars.close.to_numpy().tolist()
    expected_drawdown = (
        np.asarray(expected_nav) / np.maximum.accumulate(np.r_[1.0, expected_nav])[1:]
        - 1
    )
    assert np.allclose(
        expected_drawdown, eq.drawdown_after_fee_slippage, rtol=1e-10, atol=1e-10
    )
    breaches = eq.loc[eq.intraday_insolvency_breach]
    firstbreach = (
        None
        if breaches.empty
        else breaches.iloc[0][
            [
                "ts",
                "observed_close",
                "equity_after_fee_slippage",
                "min_intraday_equity_after_entry_fee",
            ]
        ].to_dict()
    )
    terminal = pt.iloc[-1][
        [
            "status",
            "entry_ts",
            "entry_reference_price",
            "terminal_mark_price",
            "entry_nav",
            "terminal_nav_after_fee_slippage",
            "holding_bars_observed",
            "pnl_after_fee_slippage",
        ]
    ].to_dict()
    results.append(
        dict(
            **sample,
            equity_rows=len(eq),
            trades=len(pt),
            max_abs_errors=err,
            first_intraday_breach=firstbreach,
            terminal_trade=terminal,
        )
    )
report["equity_sample_checks"] = {
    "accounts": len(results),
    "rows": sum(r["equity_rows"] for r in results),
    "results": results,
}
audit_out = F / "artifacts/p2-independent-audit.json"
rendered = json.dumps(report, default=str, indent=2) + "\n"
if audit_out.exists():
    assert json.loads(audit_out.read_text()) == json.loads(rendered), (
        "retained audit differs"
    )
else:
    audit_out.write_text(rendered)
print(json.dumps(report["equity_sample_checks"], default=str, indent=2))
