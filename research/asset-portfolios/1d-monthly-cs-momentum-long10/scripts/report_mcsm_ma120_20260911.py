"""Export audited MA120 monthly/annual evidence as Chinese Markdown, not a new strategy."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research_mcsm_single_asset_exit_20260910 import FAMILY, save, sha

OUT = FAMILY / "artifacts/ma120-round-20260911"


def pct(value):
    return f"{value * 100:+,.2f}%"


def write_new(path, body):
    with path.open("x") as handle:
        handle.write(body + "\n")


def main():
    audit = json.loads((OUT / "independent-audit.json").read_text())
    assert audit["status"] == "PASS_ALL_8_ACCOUNTS_AND_DIRECT_MA120_SIGNALS"
    assert sha(OUT / "summary.json") == audit["summary_sha256"]
    summary = json.loads((OUT / "summary.json").read_text())
    for name, digest in summary["source_sha256"].items():
        assert sha(OUT / name) == digest, name
    entries = pd.read_parquet(OUT / "entry-decisions.parquet")
    exits = pd.read_parquet(OUT / "exit-plan.parquet")
    metrics = {(r["scenario"], r["strategy"], r["slippage_rate"]): r for r in summary["results"]}
    data = {}
    for s in ["price_only", "estimated_center"]:
        for v in ["baseline", "ma120"]:
            p = OUT / f"{s}-{v}-4bp"
            data[(s, v)] = pd.read_parquet(p / "monthly.parquet").set_index("month")
    monthly = ["# MA120：全部76个月的买入、卖出和账户盈亏", "",
               "时间：2020-03-01至2026-07-01 00:15 UTC；初始10万USDT；单边手续费0.10%、滑点0.04%。每份10%，空缺留现金，不重新均分。价格收益不计资金费；含费列只记已观察资金费，仍是估算。", "",
               "月份按当月月初00:15至下月月初00:15换仓后的账户权益变化归属。因此除首月外，下月开仓成本计在前一个持有月；年度按下表月收益复合。与历史按00:00自然年切割的数字不能混用。", "",
               "## 逐月账户盈亏", "",
               "| 月份 | 原版价格收益 | MA120价格收益 | MA120价格盈亏USDT | 原版含资金费估算收益 | MA120含资金费估算收益 | MA120估算盈亏USDT | 月初买入数 |",
               "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for m in sorted(entries.month.unique()):
        p0, p1, f0, f1 = [data[key].loc[m] for key in [("price_only", "baseline"), ("price_only", "ma120"),
                                                    ("estimated_center", "baseline"), ("estimated_center", "ma120")]]
        n = int(entries.loc[entries.month.eq(m), "admitted"].sum())
        monthly.append(f"| {m:%Y-%m} | {pct(p0.account_return)} | {pct(p1.account_return)} | {p1.pnl_usdt:,.2f} | {pct(f0.account_return)} | {pct(f1.account_return)} | {f1.pnl_usdt:,.2f} | {n} |")
    monthly += ["", "## 逐月持仓与提前卖出", "", "符号省略USDT后缀；日期为UTC实际卖出日，均按00:15参考价。未买入的10%份额及卖出所得留空，不补币。", "",
                "| 月份 | 实际买入标的 | 月内提前卖出（日期） | 因不在均线上方未买 | 因没有有效MA120未买 |",
                "| --- | --- | --- | --- | --- |"]
    def short(symbol):
        return symbol.split("/")[0]
    for m, g in entries.groupby("month", sort=True):
        eg = exits.loc[exits.month.eq(m)]
        bought = "、".join(short(s) for s in g.loc[g.admitted, "symbol"]) or "全现金"
        sold = "、".join(f"{short(r.symbol)}({r.exit_ts:%m-%d})" for r in eg.itertuples(index=False)) or "无"
        below = "、".join(short(s) for s in g.loc[g.entry_reason.eq("AT_OR_BELOW_MA120"), "symbol"]) or "无"
        unknown = "、".join(short(s) for s in g.loc[~g.ma120_valid, "symbol"]) or "无"
        monthly.append(f"| {m:%Y-%m} | {bought} | {sold} | {below} | {unknown} |")
    write_new(OUT / "monthly-holdings-and-pnl.md", "\n".join(monthly))
    years = ["# MA120：年度结果", "", "与月度表相同，使用月初00:15换仓后至下一年度月初00:15。2020只含3—12月，2026只含1—6月。", "",
             "| 年份 | 原版价格收益 | MA120价格收益 | 原版含资金费估算 | MA120含资金费估算 | MA120月初平均买入数 |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    yearly_records = []
    for year in range(2020, 2027):
        values = [next(y["return"] for y in metrics[(s, v, .0004)]["yearly"] if y["year"] == year)
                  for s, v in [("price_only", "baseline"), ("price_only", "ma120"), ("estimated_center", "baseline"), ("estimated_center", "ma120")]]
        slots = entries.loc[entries.month.dt.year.eq(year)].groupby("month").admitted.sum()
        years.append(f"| {year} | " + " | ".join(pct(v) for v in values) + f" | {slots.mean():.2f} |")
        yearly_records.append({"year": year, "baseline_price": values[0], "ma120_price": values[1],
                               "baseline_funding_estimate": values[2], "ma120_funding_estimate": values[3],
                               "mean_entry_slots": float(slots.mean())})
    write_new(OUT / "yearly-results.md", "\n".join(years))
    effects, mechanism_details = [], []
    for s in ["price_only", "estimated_center"]:
        legs = pd.read_parquet(OUT / f"legs-{s}-4bp.parquet")
        top = legs.sort_values(["original_net_return", "symbol", "month"], ascending=[False, True, True]).head(76)
        sold = legs.loc[legs.early_exit]
        mechanism_details.append({"scenario": s,
                                  "missed_top76_reasons": top.loc[~top.admitted, "reason"].value_counts().to_dict(),
                                  "early_exit_price_return_median": float(sold.candidate_price_return.median()),
                                  "early_exit_below_minus20_count": int(sold.candidate_price_return.lt(-.2).sum()),
                                  "early_exit_direct_equal_slot_change": float(sold.net_return_difference.sum()),
                                  "early_exit_direct_mean_change": float(sold.net_return_difference.mean())})
        for reason, g in legs.groupby("reason"):
            effects.append({"scenario": s, "reason": reason, "legs": len(g),
                            "original_equal_slot_sum": float(g.original_net_return.sum()),
                            "candidate_equal_slot_sum": float(g.candidate_net_return.sum()),
                            "direct_equal_slot_difference": float(g.net_return_difference.sum()),
                            "original_winning_legs": int(g.original_net_return.gt(0).sum())})
    cash = entries.groupby("month").admitted.sum()
    rows = ["# MA120本轮材料", "", "仅执行用户指定的Top10加MA120入场/退出，不搜索参数，不叠加原弱币退出或20%止损。", "",
            "- [规格](../../specs/binance-1d-mcsm-ma120-round-20260911.md)",
            "- [本轮报告](../../diagnostics/binance-1d-mcsm-ma120-round-20260911.md)",
            "- [全部月度持仓与盈亏](monthly-holdings-and-pnl.md)",
            "- [年度汇总](yearly-results.md)",
            "- [8条账户摘要](summary.json)",
            "- [独立信号与现金核查](independent-audit.json)",
            "- [月初买入判断](entry-decisions.parquet) / [每日退出判断](signal-days.parquet) / [退出计划](exit-plan.parquet)",
            "- [已实际返回的成交参考价](execution-prices.parquet) / [请求及目标预先保存](plan.json)", "",
            "每条账户目录保存净值、交易、资金费、逐月与年度记录；legs文件记录全部760个候选及未买入原因、实际数量、价格与资金盈亏。", "",
            "输入复用原哈希绑定的返回帧；新增只保留16批请求需要的价格切片，没有复制日线或完整资金费。最多50MiB，本地证据不加入普通Git。可按规格复制到外置对象存储并验证恢复后再决定迁移；本次不删除或迁移旧文件。", "",
            "生成：在项目根目录，以src和本家族scripts为模块路径，运行research_mcsm_ma120_20260911.py prepare、execute，随后audit_mcsm_ma120_20260911.py和report_mcsm_ma120_20260911.py。已存在的冻结结果不能覆盖；复现应指定独立工作副本。"]
    write_new(OUT / "README.md", "\n".join(rows))
    bought = entries.loc[entries.admitted]
    distance = 1 - bought.ma120_known_at_0000 / bought.month_0000_open
    save(OUT / "report-details.json", {"yearly": yearly_records, "entry_reason_effects": effects,
                                       "mechanism_details": mechanism_details,
                                       "initial_price_drop_to_fixed_entry_ma_median": float(distance.median()),
                                       "initial_price_drop_to_fixed_entry_ma_over20_count": int(distance.gt(.2).sum()),
                                       "mean_entry_names": float(cash.mean()), "all_cash_months": [f"{m:%Y-%m}" for m in cash.index[cash.eq(0)]],
                                       "min_entry_names": int(cash.min()), "max_entry_names": int(cash.max()),
                                       "monthly_records": len(data[("price_only", "ma120")]),
                                       "monthly_table_cumulative_return_verified": bool(np.isclose(np.prod(1 + data[("price_only", "ma120")].account_return),
                                                                                                   1 + metrics[("price_only", "ma120", .0004)]["total_return"])),
                                       "script_sha256": sha(Path(__file__))})
    print(json.dumps({"mean_entry_names": float(cash.mean()), "yearly": yearly_records, "entry_reason_effects": effects}), flush=True)


if __name__ == "__main__":
    main()
