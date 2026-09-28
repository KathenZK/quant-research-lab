"""Render retained continuous-account estimates and their literal limitations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/baseline-estimate-20260909"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pct(value):
    return f"{value * 100:+,.2f}%"


def money(value):
    return f"{value:,.2f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=Path, default=OUT / "accounts")
    parser.add_argument("--output", type=Path, default=OUT / "presentation")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    source = args.accounts / "summary.json"
    summary = json.loads(source.read_text())
    started = json.loads((args.accounts / "started.json").read_text())
    for name, digest in summary["output_sha256"].items():
        if sha(args.accounts / name) != digest:
            raise ValueError(f"account output hash changed: {name}")
    metrics = {row["scenario"]: row for row in summary["results"]}
    required = {"price_only", "estimated_center", "estimated_adverse", "estimated_favorable"}
    if set(metrics) != required:
        raise ValueError("all four frozen account scenarios required for final presentation")
    args.output.mkdir()
    labels = {"price_only": "仅价格＋交易成本（不计资金费）", "estimated_center": "含观察资金费：中心估算",
              "estimated_adverse": "含观察资金费：不利情景", "estimated_favorable": "含观察资金费：有利情景"}
    price, center = metrics["price_only"], metrics["estimated_center"]
    navs = {name: pd.read_parquet(args.accounts / name / "nav.parquet") for name in metrics}
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    fig.patch.set_facecolor("#faf9f6")
    for ax in axes:
        ax.set_facecolor("#faf9f6")
        ax.grid(alpha=.18)
        ax.spines[["top", "right"]].set_visible(False)
    for name, label, color in (("price_only", "Price after trading costs; funding excluded", "#888888"),
                                ("estimated_center", "Observed funding included; estimated account", "#125f8c")):
        nav = navs[name]
        axes[0].plot(nav.ts, nav.equity, color=color, linewidth=1.4, label=label)
        dd = nav.equity / nav.equity.cummax() - 1
        axes[1].plot(nav.ts, dd * 100, color=color, linewidth=1.2)
    axes[0].set_yscale("log")
    axes[0].set_ylabel("Equity (USDT, log scale)")
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    axes[1].set_ylabel("Drawdown (%)")
    axes[1].set_ylim(-101, 3)
    axes[0].set_title("Monthly Top10 | 100,000 USDT initial | March 2020 - June 2026", loc="left", fontsize=13)
    fig.text(.085, .012, "Exploratory estimate: native/minute funding marks, estimated terminal settlement; no liquidation model.", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, .035, 1, 1))
    figure = args.output / "equity-and-drawdown.png"
    fig.savefig(figure, dpi=170)
    plt.close(fig)
    rows = ["| 账户口径 | 10万期末权益 USDT | 总收益 | 年化 | 日末及换仓点最大回撤 | 月胜率 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name in ("price_only", "estimated_center", "estimated_adverse", "estimated_favorable"):
        m = metrics[name]
        rows.append(f"| {labels[name]} | {money(m['final_equity'])} | {pct(m['total_return'])} | {pct(m['cagr_365_25'])} | {pct(m['max_drawdown_daily_and_rebalance'])} | {m['monthly_win_rate']:.2%} |")
    yearly = ["| 年份 | 不计资金费 | 含观察资金费中心估算 |", "| --- | ---: | ---: |"]
    year_records = []
    for a, b in zip(price["yearly"], center["yearly"]):
        label = str(a["year"]) + ("（3–12月）" if a["year"] == 2020 else "（上半年）" if a["year"] == 2026 else "")
        yearly.append(f"| {label} | {pct(a['return'])} | {pct(b['return'])} |")
        year_records.append({"year": label, "price_only": a["return"], "estimated_center": b["return"]})
    contribution = ["| 累计现金归因（USDT） | 不计资金费 | 含观察资金费中心估算 |", "| --- | ---: | ---: |"]
    for key, label in (("price_pnl_usdt", "价格损益"), ("funding_pnl_usdt", "资金费现金"),
                       ("fees_usdt", "手续费（扣减）"), ("slippage_usdt", "滑点（扣减）"),
                       ("net_profit_model_usdt", "最终模型利润")):
        contribution.append(f"| {label} | {money(price[key])} | {money(center[key])} |")
    funding_summary = json.loads(Path(started["paths"]["funding_summary"]).read_text())
    fund_cash = pd.read_parquet(args.accounts / "estimated_center/funding.parquet")
    fund_cash["holding_month"] = (fund_cash.ts - pd.Timedelta(minutes=15)
                                  - pd.Timedelta(nanoseconds=1)).dt.strftime("%Y-%m")
    funded_asset_months = fund_cash.groupby(["holding_month", "symbol"]).funding_cash.sum().sort_values(ascending=False)
    funding_concentration = ["| 中心估算资金费贡献（持有月） | 资产 | 净资金现金 USDT |",
                             "| --- | --- | ---: |"]
    for (month, symbol), value in funded_asset_months.head(8).items():
        funding_concentration.append(f"| {month} | {symbol.split('/')[0]} | {money(value)} |")
    funded_asset_months.rename("funding_cash_usdt").to_csv(args.output / "funding-by-asset-month.csv")
    coverage_note = f"观察事件 {funding_summary['events']:,} 条，其中原生 mark {funding_summary['native_mark_events']:,} 条、官方分钟代理 {funding_summary['minute_proxy_events']:,} 条；缺 mark {funding_summary['missing_mark_events']:,} 条。"
    price_2021 = next(x["period_end_equity"] for x in price["yearly"] if x["year"] == 2021)
    center_2021 = next(x["period_end_equity"] for x in center["yearly"] if x["year"] == 2021)
    profit_statement = ("这份历史模型中，Top10是赚钱的：不计资金费和计入观察资金费两种口径都为正收益。"
                        if min(price["total_return"], center["total_return"]) > 0
                        else "不能笼统说Top10赚钱：价格账和资金账必须按上表分别判断。")
    content = f"""# Top10 基线收益补交：76个月连续账户估算

日期：2026-09-09。状态：`EXPLORATORY_ESTIMATED_ACCOUNT_NOT_VERIFIED_NET`。

## 先给收益数字

**2020-03-01 00:15 UTC 至2026-07-01 00:15 UTC，100,000 USDT 起步：含观察资金费的中心估算期末 {money(center['final_equity'])} USDT，总收益 {pct(center['total_return'])}，年化 {pct(center['cagr_365_25'])}，日末及换仓点最大回撤 {pct(center['max_drawdown_daily_and_rebalance'])}。**

不计资金费、只看价格与交易成本，期末 {money(price['final_equity'])} USDT，总收益 {pct(price['total_return'])}。这次是76个月全部连接、实际持仓数量连续、期末清仓的账户，不是月收益算术平均或删除缺月后连乘。

{chr(10).join(rows)}

年化按实际时间/365.25天；回撤包含全部完整日末及月初换仓边界，**不是盘中最大回撤**。三条资金费情景各自用自身权益调仓；不利/有利只测试指定代理和结算价，**不是所有真实净收益的上下界或置信区间**。

![连续权益和回撤](../artifacts/baseline-estimate-20260909/presentation/equity-and-drawdown.png)

## 分年与利润保留

{chr(10).join(yearly)}

年界使用上一自然日close（UTC次年1日00:00记录），月度换仓收益则以00:15边界切分，二者不能混用。2026上半年包含最终00:15清仓成本。

价格账最大回撤从 {price['drawdown_peak_time']} 的 {money(price['drawdown_peak_equity'])} USDT 降至 {price['drawdown_trough_time']} 的 {money(price['drawdown_trough_equity'])} USDT。中心估算对应峰值 {money(center['drawdown_peak_equity'])}、谷值 {money(center['drawdown_trough_equity'])} USDT。

2021年末至本次结束，价格账收益 {pct(price['final_equity']/price_2021-1)}，含观察资金费中心估算 {pct(center['final_equity']/center_2021-1)}。这用于揭示历史利润保留，**不是另选窗口的策略优化或样本外验证**。

## 钱来自哪里

{chr(10).join(contribution)}

恒等式为初始本金＋价格损益＋资金现金－手续费－滑点＝最终权益。不同账户的资金费会改变未来月初资本和交易量，不能把两个账户最终权益差直接称为累计资金费金额。中心账户日末/换仓点最高gross/equity为 {center['max_gross_to_equity_sampled']:.4f}；月初目标1x不等于全过程保证金风险已模拟。

**资金费不是本轮的小额修正。** 中心估算净资金现金为 {money(center['funding_pnl_usdt'])} USDT，占最终模型净利润的 {center['funding_pnl_usdt']/center['net_profit_model_usdt']:.2%}（现金归因，不是把资金费删除后的反事实收益）。负费率时多头收款，正费率时多头付款；各次金额严格为 `-实际数量×事件mark×费率`，没有每天重置等权。

{chr(10).join(funding_concentration)}

因此，要分别研究“价格领涨延续”和“持有领涨币时收到的资金费”；不能把含资金费曲线直接归因为单一趋势Alpha。明细按月初00:15持有边界归属，次月00:00事件仍计入旧持有月。

## 固定规则、修正与估算边界

- 上一完整月涨幅Top10，30日ADV≥1,000万USDT；月初每腿成本后10%名义，月内固定数量、同名净額调仓；单边手续费0.1%、滑点0.04%；没有止损、择时、波动目标或参数搜索。
- 与旧实现不再混用：旧程序每天重置等权；本次遵循买入持有一个月的固定数量语义，月初00:15参考成交代替旧00:00同刻取信号。新价格输入固定V3而非旧cache。
- 原ADA部分上市日资格已恢复。初次重建69个月成员集合与旧ADV名单相同；4个月因已生效终止公告补位；2022-03/04/05共11个新纳入名字则因旧源缺2022-02-26至28或04-01至02，破坏端点/ADV资格。旧新共同存在的所比较数值未变化，不是改排序纳入WAVES/ZIL。详见[新旧输入差异](../artifacts/baseline-estimate-20260909/inputs/selection-appendix/legacy-v3-summary.json)。不能把全部收益差异说成只有资金费。
- 身份复核取得官方证据后，又修正两处伪形成收益：旧LIT为Litentry，新LIT为Lighter；AERGO在旧合约终止后重新上线。旧新价格不能跨合约/跨资产相除。按**已经冻结的原排序**，2025May AERGO→LAYER，2026Jan LIT→Q，其余758腿不变，最终与旧原名单有8个月差异。不是按收益删除亏损腿；四条账户都从头按修正名单重跑。早先报告的价格账+932.52%为修正前对照，不是最终基线数字。见[身份公告原文](../artifacts/baseline-estimate-20260909/inputs/selection-appendix/identity-sources/README.md)和[修正契约](../specs/baseline-estimate-identity-correction-20260909.md)。
- 原日桶形成规则还有短零成交边界：初始760腿中728个形成期为完整15m有效段，30腿跨同期短暂零成交，另两腿长断点已按身份事实修正。原>=48/80%/ADV并不自动认证完整连续趋势；短零成交的官方原因未完整核实，不将其称为已解释维护。即使实际持有期价格可记模型现金，也不能将全市场历史身份或真实Alpha标为已通过。见[形成段边界审计](../artifacts/baseline-estimate-20260909/inputs/selection-appendix/formation-segment-summary.json)。
- BNX/VIDT持有中结算；终止中心价来自官方分钟指数OHLC4窗口均值，低/高为分钟low/high均值。终止手续费按0.1%建模、滑点0；这些不是最终官方现金回单，终止费用假设已单列。
- {coverage_note} 资金费按事件时刻实际数量乘费率及结算标记价记现金。原生mark优先，缺原生mark的中心价用官方同分钟mark-price open；保留原始费率类型，Unspecified常规资金类型属于显式估算假设。
- 未证明的历史结算日历、PIT身份、特殊事件、参考价格实际可成交性和保证金/强平/ADL仍是限制。没有把已知缺事件填零；“已观察事件全计入”不证明没有未观察到的应结算事件。
- 结果是已声明模型下的历史估算，既不是恢复旧失效绩效，也不是宣称已经可实盘部署。原严格核验 `BASELINE_NOT_VERIFIED` 保留。

## 可以下的结论

{profit_statement} 价格账高度依赖2021年的右尾行情，之后利润大幅回吐；含资金费账在2025–2026年另有大量负费率收入并创新高。两种利润来源必须分开，不能把全期正收益解释为稳定的月度优势，也不能再说所有收益都只来自2021年。

下一步要验证领涨延续相对同机会集市场持仓的增量，以及资金费利润是否集中于少数拥挤事件、能否真实执行和在未读新样本延续。这是后续方向，本轮没有借此筛参数或先用降仓把利润和回撤一起压低。

价格账与含资金账分开，避免将手续费、资金费和每日再平衡混为所谓Alpha。历史收益不等于独立于市场的Alpha，更不等于有能力承受上述回撤的实盘策略。独立价格和三条资金现金账复算仅验证模型会计，不能代替尚未通过的输入完整性及实盘约束。

## 可审计证据

- [固定契约](../specs/binance-1d-mcsm-baseline-estimate-20260909.md)、[有界输入补充](../specs/baseline-estimate-scoped-input-addendum-20260909.md)、[资金类型/时间精度补充](../specs/baseline-estimate-funding-type-addendum-20260909.md)。
- [账户汇总](../artifacts/baseline-estimate-20260909/accounts/summary.json)、[身份修正后760腿完整名单](../artifacts/baseline-estimate-20260909/inputs-identity-corrected/holdings.csv)、[原名单结构QA](../artifacts/baseline-estimate-20260909/inputs/independent-selection-qa.json)。
- [身份修正后资金费补证](../artifacts/baseline-estimate-20260909/funding-identity-corrected/summary.json)、[最终独立价格现金账复算](../artifacts/baseline-estimate-20260909/independent-final-price-only-audit/summary.json)、[三条资金估算独立复算](../artifacts/baseline-estimate-20260909/independent-funded-audit/summary.json)。
- [中心估算逐月账户](../artifacts/baseline-estimate-20260909/accounts/estimated_center/monthly.csv)、[价格账逐月账户](../artifacts/baseline-estimate-20260909/accounts/price_only/monthly.csv)。

首次无效资金毫秒计划及首价格结果保留原位；最终产物另存，没有覆盖旧数据或结果。新官方原文大包为本地可再生产物，保留哈希/精简投影/回执，不加入普通Git。不修改生产服务或提交交易。
"""
    report = FAMILY / "diagnostics/binance-1d-mcsm-baseline-estimate-20260909.md"
    with report.open("x") as file:
        file.write(content)
    pd.DataFrame(year_records).to_csv(args.output / "yearly-comparison.csv", index=False)
    with (args.output / "receipt.json").open("x") as file:
        json.dump({"source_sha256": sha(source), "script_sha256": sha(Path(__file__)),
                   "report_sha256": sha(report), "figure_sha256": sha(figure),
                   "status": "ESTIMATE_PRESENTATION_NOT_VERIFIED_NET"}, file, indent=2)
    print(report)


if __name__ == "__main__":
    main()
