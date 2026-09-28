"""Read-only frozen-account extraction for the requested recent 36-month table."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
SOURCE = FAMILY / "artifacts/weekly-top10-20260924/terminal-complete"
OUT = FAMILY / "artifacts/recent36-monthly-holdings-20260924"
START = pd.Timestamp("2023-07-01T00:00Z")
END = pd.Timestamp("2026-07-01T00:15Z")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        f.write("\n")


def code(s):
    return s.replace("/USDT:USDT", "")


def main():
    assert sha(SOURCE / "summary.json") == "ff4783fbb9a90f03727d9fcf5f7ec8cdc12c1ea5f805b6b1aea2f54dda4a83bd"
    summary = json.loads((SOURCE / "summary.json").read_text())
    audit = json.loads((SOURCE / "independent-audit.json").read_text())
    assert audit["summary_sha256"] == sha(SOURCE / "summary.json")
    assert all(r["status"] == "PASS_INDEPENDENT_CASH_AND_REPORTING" for r in audit["results"])
    source_pins = {}

    def read(name):
        p = SOURCE / name
        assert sha(p) == summary["files_sha256"][name]
        source_pins[str(p.relative_to(ROOT))] = sha(p)
        return pd.read_parquet(p)

    all_h = read("holding-windows.parquet")
    h = all_h.loc[all_h.strategy.eq("B0")].copy()
    trades = read("B0-center-4bp/trades.parquet")
    legs = read("B0-center-4bp/leg-price-pnl.parquet")
    monthly = read("B0-center-4bp/monthly.parquet")
    nav = read("B0-center-4bp/nav.parquet")
    periods = read("B0-center-4bp/periods.parquet")
    months = monthly.loc[monthly.month.ge(START)].copy()
    assert len(months) == 36 and months.month.tolist() == list(pd.date_range(START, periods=36, freq="MS"))
    records, details = [], []
    for m in months.to_dict("records"):
        day, ts = m["month"], m["month"] + pd.Timedelta(minutes=15)
        current = h.loc[h.entry_ts.eq(ts)].copy()
        assert len(current) == 10 and current.symbol.nunique() == 10
        prior = h.loc[h.entry_ts.eq(ts - pd.offsets.MonthBegin(1))]
        assert len(prior) == 10
        active = set(prior.loc[prior.exit_ts.ge(ts), "symbol"])
        chosen = set(current.symbol)
        new, kept, removed = chosen - active, chosen & active, active - chosen
        actual = trades.loc[trades.ts.eq(ts)]
        assert set(actual.loc[actual.old_quantity.eq(0) & actual.new_quantity.gt(0), "symbol"]) == new
        assert set(actual.loc[actual.old_quantity.gt(0) & actual.new_quantity.eq(0), "symbol"]) == removed
        assert set(actual.loc[actual.old_quantity.gt(0) & actual.new_quantity.gt(0), "symbol"]) == kept
        assert set(actual.loc[actual.new_quantity.gt(0), "symbol"]) == chosen
        late = current.loc[current.terminal]
        previous_early = prior.loc[prior.terminal & prior.exit_ts.lt(ts)]
        gl = legs.loc[legs.entry_ts.eq(ts)].copy()
        assert set(gl.symbol) == chosen and len(gl) == 10
        top, bottom = gl.loc[gl.gross_price_return.idxmax()], gl.loc[gl.gross_price_return.idxmin()]
        p = periods.loc[periods.entry_ts.eq(ts)].iloc[0]
        rec = {"month": day.strftime("%Y-%m"), "date": day.isoformat(),
               "selected": sorted(map(code, chosen)), "new": sorted(map(code, new)),
               "retained": sorted(map(code, kept)), "exited": sorted(map(code, removed)),
               "early_exits": [{"symbol": code(r.symbol), "date": r.exit_ts.isoformat()} for r in late.itertuples()],
               "prior_early_exits": [{"symbol": code(r.symbol), "date": r.exit_ts.isoformat()} for r in previous_early.itertuples()],
               "return": m["return"], "start_equity": m["start_equity"], "end_equity": m["end_equity"],
               "pnl_usdt": m["pnl_usdt"], "price_pnl_usdt": m["price_pnl_usdt"],
               "fees_usdt": m["fees_usdt"], "slippage_usdt": m["slippage_usdt"],
               "holding_period_return": float(p["return"]),
               "top_symbol": code(top.symbol), "top_gross_return": float(top.gross_price_return),
               "bottom_symbol": code(bottom.symbol), "bottom_gross_return": float(bottom.gross_price_return)}
        records.append(rec)
        for r in gl.itertuples():
            details.append({"month": rec["month"], "date": rec["date"], "symbol": code(r.symbol),
                            "action": "新买入" if r.symbol in new else "续持调仓",
                            "entry_price": r.entry_reference_price, "exit_price": r.exit_reference_price,
                            "gross_return": r.gross_price_return, "exit_date": r.exit_ts.isoformat(),
                            "exit_reason": "下架自动结算（估算）" if r.terminal else "下次换仓边界（非必然全卖）",
                            "weight": r.weight, "quantity": r.account_entry_quantity,
                            "price_pnl_usdt": r.period_price_pnl_usdt})
    initial = float(months.start_equity.iloc[0])
    selected_nav = nav.loc[nav.ts.ge(START) & nav.ts.le(END)].copy()
    assert selected_nav.ts.iloc[0] == START and selected_nav.equity.iloc[0] == initial
    equity = selected_nav.equity.to_numpy(float)
    dd = equity / np.maximum.accumulate(equity) - 1
    trough = int(np.argmin(dd)); peak = int(np.argmax(equity[:trough+1]))
    total = float(months.end_equity.iloc[-1] / initial - 1)
    assert np.isclose(np.prod(1 + months["return"]) - 1, total, rtol=1e-11)
    years = []
    for y, g in months.groupby(months.month.dt.year):
        years.append({"year": int(y), "months": len(g), "return": float(g.end_equity.iloc[-1] / g.start_equity.iloc[0] - 1),
                      "pnl_usdt": float(g.pnl_usdt.sum()), "positive_months": int(g["return"].gt(0).sum())})
    recent_legs = legs.loc[legs.entry_ts.ge(START)]
    contribution = recent_legs.groupby("symbol").period_price_pnl_usdt.agg(["sum", "count"])
    top_symbols = [{"symbol": code(s), "price_pnl_usdt": float(r["sum"]), "months_held": int(r["count"])}
                   for s, r in contribution.sort_values("sum", ascending=False).head(10).iterrows()]
    stats = {"total_return": total, "annualized_365_25": (1+total) ** (365.25*86400/(END-START).total_seconds())-1,
             "max_drawdown": float(dd.min()), "drawdown_peak": selected_nav.ts.iloc[peak],
             "drawdown_trough": selected_nav.ts.iloc[trough], "positive_months": int(months["return"].gt(0).sum()),
             "new_entries": sum(len(r["new"]) for r in records), "retained_slots": sum(len(r["retained"]) for r in records),
             "scheduled_full_exits": sum(len(r["exited"]) for r in records), "terminal_exits": sum(len(r["early_exits"]) for r in records),
             "average_new_names": float(np.mean([len(r["new"]) for r in records])),
             "average_retained_names": float(np.mean([len(r["retained"]) for r in records])),
             "distinct_symbols": recent_legs.symbol.nunique(), "top_symbols_by_actual_price_pnl": top_symbols,
             "best_month": max(records, key=lambda r: r["return"])["month"], "worst_month": min(records, key=lambda r: r["return"])["month"],
             "calendar_start_equity": initial, "calendar_end_equity": float(months.end_equity.iloc[-1])}
    OUT.mkdir(parents=True, exist_ok=True)
    result = {"status": "FROZEN_MONTHLY_ACCOUNT_REPORT_EXTRACT_NOT_NEW_BACKTEST", "start": START, "end": END,
              "funding_included": False, "source_summary_sha256": sha(SOURCE / "summary.json"),
              "source_audit_sha256": sha(SOURCE / "independent-audit.json"), "script_sha256": sha(Path(__file__)),
              "source_files_sha256": source_pins, "months": records, "legs": details, "years": years, "stats": stats,
              "final_liquidation": {"date": END, "symbols": records[-1]["selected"], "reason": "样本结束清仓，不是2026年7月信号"}}
    save(OUT / "report-data.json", result)
    lines = ["# 月频Top10最近36个月：买入、续持与换出", "",
             "区间：2023年7月至2026年6月。原始月频Top10，不加MA120；每边手续费0.10%+滑点0.04%，不含资金费，终止价格含条件估算。本表复用2026-09-24独立核对后的月频账，不是新回测。", "",
             "收益沿用自然月00:00 UTC、最后实际清仓00:15口径；持仓名单为月初00:15换仓后的十币。新买入与换出均按真实调仓前后的数量核对，续持也可能加减仓。", "",
             f"36个月复合收益 **{total:+.2%}**，年化 **{stats['annualized_365_25']:.2%}**，日末及换仓采样最大回撤 **{stats['max_drawdown']:.2%}**。盈利月 **{stats['positive_months']}/36**，平均每月新买 **{stats['average_new_names']:.2f}** 个，续持 **{stats['average_retained_names']:.2f}** 个。", "",
             "## 年度分段", "", "| 区间 | 收益 | 盈利月 |", "| --- | ---: | ---: |"]
    for y in years:
        label = str(y["year"]) + ("下半年" if y["year"] == 2023 else "上半年" if y["year"] == 2026 else "全年")
        lines.append(f"| {label} | {y['return']:+.2%} | {y['positive_months']}/{y['months']} |")
    lines += ["", "## 全部月度换仓", "", "**加粗为本月新买入**；未加粗为续持。本月十币按代码排序，不表示涨幅名次。月初换出不重复列此前已下架结算的币。", "",
              "| 月份 | 本月十币（加粗为新买） | 月初换出 | 自然月收益 |", "| --- | --- | --- | ---: |"]
    table = lines[-2:].copy()
    for r in records:
        selected = "、".join(f"**{s}**" if s in r["new"] else s for s in r["selected"])
        row = f"| {r['month']} | {selected} | {'、'.join(r['exited']) or '无'} | {r['return']:+.2%} |"
        lines.append(row); table.append(row)
    lines += ["", "## 下架与末尾清仓", ""]
    for r in records:
        for e in r["early_exits"]:
            lines.append(f"- {e['date'][:16]} UTC：{e['symbol']}自动结算，之后该份额留现金至下月。不是下月再次卖出。")
    lines += ["- 2026-07-01 00:15 UTC是样本结束，清空6月所有剩余仓位，不代表7月选币信号。", "",
              "## 单币盈亏口径", "",
              "工作簿的单币页保存360笔月持仓，给出新买/续持、参考价格、区间价格涨跌与实际数量下价格盈亏。价格盈亏未分摊费用，也不是含资金费收益。换仓边界价不代表该币必然全卖出。", "",
              "为保持前轮口径，月度收益仍按自然月；单币从当月换仓到下次换仓，因此跨越的月初15分钟不同，单币盈亏不能直接求和冒充自然月净盈亏。", "",
              "## 来源与保存", "",
              "[已核对完整账户](../weekly-top10-20260924/terminal-complete/summary.json) · [独立核对](../weekly-top10-20260924/terminal-complete/independent-audit.json) · [逐行输出及源哈希](report-data.json)。本次只新增小型可再生报表，预算5MiB，不覆盖任何已有回测、计划或结论，不复制行情，不进入生产。"]
    with (OUT / "monthly-table.md").open("x") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps({"stats": stats, "years": years}, default=str, ensure_ascii=False, indent=2))
    print("\n".join(table))


if __name__ == "__main__":
    main()
