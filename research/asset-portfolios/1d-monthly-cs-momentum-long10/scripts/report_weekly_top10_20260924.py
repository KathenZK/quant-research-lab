"""Export audited weekly holdings, monthly/yearly accounts and concentration."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from complete_weekly_top10_20260924 import END, FAMILY, OUT, START, validate_prior
from research_mcsm_weekly_20260911 import pin, save, sha


def write(path, lines):
    with path.open("x") as f:
        f.write("\n".join(lines) + "\n")


def names(value):
    return value.replace("/USDT:USDT", "")


def pct(value):
    return f"{value:+.2%}"


def main():
    validate_prior()
    audit = json.loads((OUT / "independent-audit.json").read_text())
    assert len(audit["results"]) == 8 and all(r["status"] == "PASS_INDEPENDENT_CASH_AND_REPORTING" for r in audit["results"])
    pin(OUT / "summary.json", audit["summary_sha256"])
    summary = json.loads((OUT / "summary.json").read_text())
    for name, digest in summary["files_sha256"].items():
        pin(OUT / name, digest)
    metrics = {r["strategy"]: r for r in summary["accounts"] if r["slippage_rate"] == .0004 and r["terminal_scenario"] == "center"}
    hold = pd.read_parquet(OUT / "holding-windows.parquet")
    month_tables, concentrations, top_tables, risks = {}, {}, {}, {}
    for strategy in ["B0", "W7"]:
        d = OUT / (strategy + "-center-4bp")
        month_tables[strategy] = pd.read_parquet(d / "monthly.parquet")
        legs = pd.read_parquet(d / "leg-price-pnl.parquet")
        p = legs.period_price_pnl_usdt
        n = math.ceil(.1 * len(legs))
        concentrations[strategy] = {"legs": len(legs), "positive_legs": int(p.gt(0).sum()), "top_n": n,
                                    "top_n_share_of_positive_price_pnl": float(p.nlargest(n).sum() / p.clip(lower=0).sum()),
                                    "monthly_win_rate": float(month_tables[strategy]["return"].gt(0).mean())}
        top_tables[strategy] = legs.nlargest(10, "period_price_pnl_usdt")
        nav = pd.read_parquet(d / "nav.parquet")
        m = metrics[strategy]
        peak = float(nav.loc[nav.ts.eq(pd.Timestamp(m["drawdown_peak"])), "equity"].iloc[0])
        trough = float(nav.loc[nav.ts.eq(pd.Timestamp(m["drawdown_trough"])), "equity"].iloc[0])
        recovered = nav.loc[nav.ts.gt(pd.Timestamp(m["drawdown_trough"])) & nav.equity.ge(peak), "ts"]
        risks[strategy] = {"peak_equity": peak, "trough_equity": trough, "recovery": str(recovered.iloc[0]) if len(recovered) else None}
        assert np.isclose(100000 + m["price_pnl_usdt"] - m["fees_usdt"] - m["slippage_usdt"], m["final_equity"])

    years = ["# 每周Top10与月Top10：年度账户结果", "",
             "初始各100,000 USDT；中心终止估算；单边费0.10%+滑点0.04%；不含资金费。2020仅6–12月，2026仅1–6月。", "",
             "| 年份 | 周Top10收益 | 周Top10盈亏 USDT | 周期末权益 | 月Top10收益 | 月Top10盈亏 USDT | 月期末权益 |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for w, b in zip(metrics["W7"]["yearly"], metrics["B0"]["yearly"], strict=True):
        assert w["year"] == b["year"]
        label = str(w["year"]) + ("（6–12月）" if w["year"] == 2020 else "（上半年）" if w["year"] == 2026 else "")
        years.append(f"| {label} | {pct(w['return'])} | {w['pnl_usdt']:+,.2f} | {w['end_equity']:,.2f} | {pct(b['return'])} | {b['pnl_usdt']:+,.2f} | {b['end_equity']:,.2f} |")
    years += ["", "按自然月00:00 UTC估值，首尾实际00:15。盈亏包括未平仓浮动与已实现损益，不只是当年卖出成交。年度收益应连乘，不相加。"]
    write(OUT / "yearly-results.md", years)

    months = ["# 全部73个月：持仓币种与账户盈亏", "",
              "中心结算条件估算，已扣单边0.10%手续费和0.04%滑点，不含资金费。月界自然月00:00 UTC、首尾00:15；周策略月内会多次换币，列出当月实际持有过的全部币，不代表同时持有或月初全部持有。", "",
              "| 月份 | 周Top10收益 | 周盈亏 USDT | 周期末权益 | 月Top10收益 | 月盈亏 USDT | 月期末权益 |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for w, b in zip(month_tables["W7"].itertuples(), month_tables["B0"].itertuples(), strict=True):
        assert w.month == b.month
        # itertuples renames the reserved `return` column; read it explicitly below.
        wr = float(month_tables["W7"].loc[w.Index, "return"])
        br = float(month_tables["B0"].loc[b.Index, "return"])
        months.append(f"| {w.month:%Y-%m} | {pct(wr)} | {w.pnl_usdt:+,.2f} | {w.end_equity:,.2f} | {pct(br)} | {b.pnl_usdt:+,.2f} | {b.end_equity:,.2f} |")
    months += ["", "## 每月实际持有过的币", "", "| 月份 | 周Top10 | 月Top10 |", "| --- | --- | --- |"]
    for w, b in zip(month_tables["W7"].itertuples(), month_tables["B0"].itertuples(), strict=True):
        months.append(f"| {w.month:%Y-%m} | {names(w.held_symbols_during_month)} | {names(b.held_symbols_during_month)} |")
    write(OUT / "monthly-holdings-and-pnl.md", months)

    periods = pd.read_parquet(OUT / "W7-center-4bp/periods.parquet")
    weekly = ["# 全部318次周选币及盈亏", "",
              "UTC每周一00:15买入上一完整周Top10，每币成本后权益10%，只做多；不加MA120。中心结算估算，不含资金费。", "",
              "每期账户盈亏为本次换仓后到下次换仓后，因此包含下次换仓费用；首期另外含初始建仓费，最后一周于2026-07-01清仓，仅2日。同币只交易净差额，下面的‘持有’不等于每周全卖再全买。", "",
              "| 买入日 | 下一换仓/最终清仓日 | 十币名单 | 账户收益 | 盈亏 USDT | 期末权益 | 提前自动结算 |",
              "| --- | --- | --- | ---: | ---: | ---: | --- |"]
    for r in periods.to_dict("records"):
        t = hold.loc[hold.strategy.eq("W7") & hold.entry_ts.eq(r["entry_ts"]) & hold.terminal]
        terminal = "; ".join(f"{names(x.symbol)} {x.exit_ts:%Y-%m-%d %H:%M}" for x in t.itertuples()) or "无"
        weekly.append(f"| {r['entry_ts']:%Y-%m-%d} | {r['exit_ts']:%Y-%m-%d} | {names(r['selected_symbols'])} | {pct(r['return'])} | {r['pnl_usdt']:+,.2f} | {r['end_equity']:,.2f} | {terminal} |")
    assert len(periods) == 318
    write(OUT / "weekly-holdings-and-pnl.md", weekly)

    report = ["# 每周涨幅Top10：结果与月频比较，2026-09-24", "",
              "## 结论", "",
              "每周买上一周Top10没有改善本轮价格表现：累计+64.51%、年化8.53%，最大回撤-97.42%；同期月Top10累计+925.13%、年化46.63%，回撤-95.43%。周频不采纳为当前实盘方案。这个结论只针对本轮固定规则，不等于所有周频或趋势策略无效。", "",
              "## 到底测了什么", "",
              "[原固定规则](../specs/binance-1d-mcsm-weekly-top10-20260924.md)：上一完整UTC周涨幅排名，周一00:15买前10，持有数量到下周一；每币10%，保留原31日有效历史/ADV30至少1,000万/事前活动检查，不加MA120、止损或弱币退出。股票/传统资产类别不另行剔除，仍是币安原生USDT永续观察池，不是外部现货美股。", "",
              "同起点2020-06-01 00:15至2026-07-01 00:15 UTC（73个月），各10万USDT。6月1日是原样本开始后首个同时为月初和周一的日期，非看收益选起点；周318次、月73次。此前76个月月基线+912.33%和75个月+1,428.03%已完整重现，本次+925.13%只是73个月同日起步结果，不能混比。", "",
              "所有下表均已扣单边手续费0.10%及对应滑点，但没有资金费。最大回撤按共同日末/月初/周一网格采样，不包括日内极值；不模拟保证金强平或实际成交容量。", "",
              "## 收益及成本压力", "", "| 策略 | 单边滑点 | 累计收益 | 年化 | 最大回撤 | 10万期末变成 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for r in summary["accounts"]:
        if r["terminal_scenario"] == "center":
            report.append(f"| {'每周Top10' if r['strategy']=='W7' else '每月Top10'} | {r['slippage_rate']:.2%} | {pct(r['total_return'])} | {pct(r['cagr_365_25'])} | {pct(r['max_drawdown_common_grid'])} | {r['final_equity']:,.2f} USDT |")
    report += ["", "终止价格低/高敏感性：周频累计+63.38%至+65.68%，月频+921.46%至+928.65%。是指定指数分钟代理的条件情景，不是真实收益上下界或置信区间，不改变此处周/月排序。", "",
               "## 每年结果", "", *years[4:-2], "", "## 差距在哪里", "",
               "1. 周频同样能在牛市赚钱，但利润没守住。2021周频+834.50%，之后2022亏82.97%；2023周频-13.42%而月频+75.49%，2026上半年周频-47.18%而月频+47.07%。不是单靠2022市场暴跌就能解释所有差距。", "",
               "2. 交易次数显著增加。每次换仓净额成交/当时权益约1.68倍与1.70倍相近，周频全期累计535.17倍、月频125.65倍，约4.26倍。滑点从0.04%升至0.08%后周频收益降至+32.84%，成本更敏感。倍数含买卖两边、初始建仓和最终清仓，不是杠杆。", "",
               "| 真实账户现金拆分（USDT） | 周Top10 | 月Top10 |", "| --- | ---: | ---: |"]
    for title, key in [("全部价格盈亏", "price_pnl_usdt"), ("累计手续费", "fees_usdt"), ("累计滑点", "slippage_usdt")]:
        report.append(f"| {title} | {metrics['W7'][key]:+,.2f} | {metrics['B0'][key]:+,.2f} |")
    report += [f"| 扣上述成本后的盈亏 | {metrics['W7']['final_equity']-100000:+,.2f} | {metrics['B0']['final_equity']-100000:+,.2f} |", "",
               "这是同一已扣费路径的现金恒等式，成本已影响后续仓位。不能把累计费用简单加回后宣称跑过一个无手续费复利策略。尤其2023年，周频价格盈亏约-1,285 USDT，另付手续费与滑点约67,896 USDT，全年转为-13.42%。", "",
               "3. 盈利仍集中在少数大涨持仓。按实际账户数量的单次持仓价格利润，最高10%腿贡献的全部正价格利润占比如下；这不是净收益贡献比例，也不是与月频赢家一一匹配后的‘利润保留率’。", "",
               "| 策略 | 总持仓腿 | 盈利腿 | 最高10%腿数 | 占全部正价格利润 |", "| --- | ---: | ---: | ---: | ---: |"]
    for s, c in concentrations.items():
        report.append(f"| {s} | {c['legs']} | {c['positive_legs']} | {c['top_n']} | {c['top_n_share_of_positive_price_pnl']:.2%} |")
    report += ["", "周频盈利持有周167/318（52.52%），但这没能转化为可承受的长期账户：2021-05-12高点约595.54万，2026-06-24低点约15.34万USDT，样本结束仍未恢复。", "",
               "本轮同时把‘排名回看期’和‘换仓持有期’都从月改成周，不能据此单独断言是短期反转、过早卖赢家还是交易成本造成全部差额。证据支持的是：这个最直接的周Top10表达，价格账户表现比月Top10差；尚未识别独立因果比例。", "",
               "## 下架交易没有删除", "",
               "旧周频因BZRX/KEEP缺结算价停止；补取官方指数后，又发现COCOS/MEMEFI。首次失败保留，[补充规则](../specs/binance-1d-mcsm-weekly-top10-terminal-amendment-20260924.md)在新价格和全期周收益之前固定。", "",
               "[COCOS公告](https://www.binance.com/en/support/announcement/detail/45852dc155b641bc9e1c23bc41d8ded6)确认2023-05-25 09:00 UTC自动结算；[MEMEFI公告](https://www.binance.com/en/support/announcement/detail/21e399dcea734230a3c181daf5407b64)确认2025-08-11 09:00 UTC结算。另两只[旧BZRX](https://www.binance.com/en/support/announcement/detail/dff27dc6bcbb432c902bcbea5e24ddfa)、[KEEP](https://www.binance.com/en/support/announcement/detail/96698a6a80f64cb1ae27f813032bfaa9)公告和完整官方指数窗口一并留存。", "",
               "周账户实际6次自动结算为BZRX、KEEP、COCOS、BNX、ALPACA、MEMEFI，结算后该份额留现金到下周；不拼新币、不把零成交占位K线当卖出。分钟指数只能提供条件结算估算，仍非原始结算回单。", "",
               "## 核验与交付", "",
               "全部318次周榜由另一个直接取过去日期的算法重建一致；八个成本/结算情景逐一用独立数量×价差和净额手续费重算，全部2,601个权益时点、逐笔调仓、逐腿价格盈亏、73个月与7个年度对齐。月/周共44,358条日估值需求核完；原76月/75月基线与首次73月月账完整复现，旧代码和旧结果未改。独立重算证明本次记账一致，不证明完整历史资产身份、资金费、强平或实盘可交易性。", "",
               "- [每周币种与盈亏，318期](../artifacts/weekly-top10-20260924/terminal-complete/weekly-holdings-and-pnl.md)",
               "- [每月持仓与盈亏，73个月](../artifacts/weekly-top10-20260924/terminal-complete/monthly-holdings-and-pnl.md)",
               "- [年度汇总](../artifacts/weekly-top10-20260924/terminal-complete/yearly-results.md)",
               "- [独立核账](../artifacts/weekly-top10-20260924/terminal-complete/independent-audit.json)",
               "- [材料与复现入口](../artifacts/weekly-top10-20260924/README.md)", "",
               "当前裁决：研究计算完成；每周Top10不采纳为实盘候选。资金费全量口径仍缺，不将价格收益冒充永续净收益，也不据此推翻月频资金费曾有正贡献的既有结果。全部是已揭示历史，非未见样本验证。下一轮若继续，应把形成期与持有期拆开，只验证一个机制问题，而不是为这条曲线继续搜索参数。"]
    for s, table in top_tables.items():
        report += ["", f"### {s} 最高10笔价格利润（实际数量，未分摊费用）", "", "| 买入 | 币种 | 退出 | 价格利润 USDT |", "| --- | --- | --- | ---: |"]
        for r in table.itertuples():
            report.append(f"| {r.entry_ts:%Y-%m-%d} | {names(r.symbol)} | {r.exit_ts:%Y-%m-%d} | {r.period_price_pnl_usdt:+,.2f} |")
    target = FAMILY / "diagnostics/binance-1d-mcsm-weekly-top10-20260924.md"
    write(target, report)
    files = [target, OUT / "weekly-holdings-and-pnl.md", OUT / "monthly-holdings-and-pnl.md", OUT / "yearly-results.md"]
    save(OUT / "report-details.json", {"start": START, "end": END, "months": 73, "weeks": 318,
                                       "concentrations": concentrations, "drawdowns": risks,
                                       "audit_sha256": sha(OUT / "independent-audit.json"),
                                       "report_script_sha256": sha(Path(__file__)),
                                       "delivery_sha256": {str(p.relative_to(FAMILY)): sha(p) for p in files}})
    print(json.dumps({"delivered_weeks": 318, "months": 73, "years": 7}), flush=True)


if __name__ == "__main__":
    main()
