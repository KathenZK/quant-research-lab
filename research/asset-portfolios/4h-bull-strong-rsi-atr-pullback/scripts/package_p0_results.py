"""汇总已固定回放产物、独立验算经济结果，生成中文研究报告。"""

from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/p0-20260907"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def table(df, cols, names=None):
    head = names or cols
    rows = [
        "| " + " | ".join(head) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for values in df[cols].itertuples(index=False, name=None):
        cells = []
        for x in values:
            if pd.isna(x):
                cells.append("—")
            elif isinstance(x, (float, np.floating)):
                cells.append(f"{x:.2f}")
            else:
                cells.append(str(x))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def main():
    result = json.loads((OUT / "result-manifest.json").read_text())
    for name, digest in result["artifacts"].items():
        assert sha(OUT / name) == digest, name
    spec = importlib.util.spec_from_file_location(
        "replay", FAMILY / "scripts/replay_p0.py"
    )
    r = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r)
    trades = pd.read_parquet(OUT / "trades.parquet")
    s = pd.read_csv(OUT / "summary.csv").set_index("variant")
    y = pd.read_csv(OUT / "by-year.csv")
    by = pd.read_csv(OUT / "by-symbol.csv")
    recent = pd.read_csv(OUT / "recent-entry-cohorts.csv")
    primary = trades[trades.variant.eq("primary")]
    named = trades[trades.variant.eq("named_observation")]
    closed = trades[trades.status.eq("closed")]
    # Independent arithmetic verification, using original raw entry/exit prices.
    raw = closed.exit_price_before_slip / closed.entry_open
    assert np.allclose(closed.gross_return, raw - 1, atol=1e-12, rtol=0)
    ratio = raw * (1 - 0.0004) / (1 + 0.0004)
    assert np.allclose(
        closed.cost_adjusted_ex_funding_4bps,
        ratio - 1 - 0.001 * (1 + ratio),
        atol=1e-12,
        rtol=0,
    )
    assert trades.trade_id.is_unique
    assert (trades.entry_time > trades.signal_bar_open).all()
    assert (trades.entry_time - trades.signal_bar_open).eq(pd.Timedelta(hours=4)).all()
    assert (trades.initial_stop > 0).all() and (
        trades.initial_stop < trades.entry_open
    ).all()
    assert (closed.exit_bar_open >= closed.entry_time).all()
    for (_, _), g in closed.groupby(["variant", "symbol"]):
        g = g.sort_values("entry_time")
        assert (
            g.entry_time.iloc[1:].reset_index(drop=True)
            > g.exit_bar_open.iloc[:-1].reset_index(drop=True)
        ).all()
    for name, g in trades.groupby("variant"):
        checked = r.statistics(g)
        assert np.isclose(
            checked["cost4_ex_funding_mean_pct"],
            s.loc[name, "cost4_ex_funding_mean_pct"],
        )
        assert checked["closed"] == s.loc[name, "closed"]
    # Censored positions stay censored. A hypothetical terminal close is a separate valuation.
    marked = []
    for name, g in trades.groupby("variant"):
        values = []
        for _, t in g.iterrows():
            if t.status == "closed":
                values.append(t.cost_adjusted_ex_funding_4bps)
            elif t.reason == "right_censor_cutoff":
                values.append(
                    r.cost_return(t.entry_open, t.entry_open * (1 + t.last_mark_gross))
                )
            else:
                values.append(np.nan)
        marked.append(
            {
                "variant": name,
                "trades": len(g),
                "unresolved_gap_positions": int(np.isnan(values).sum()),
                "terminal_mark_cost4_ex_funding_mean_pct": float(np.mean(values) * 100)
                if not np.isnan(values).any()
                else None,
                "is_account_return": False,
                "is_realized_return": False,
            }
        )
    pd.DataFrame(marked).to_csv(OUT / "terminal-mark-diagnostic.csv", index=False)
    cyc = []
    for label, a, b in [
        ("2020–2022", 2020, 2022),
        ("2023–2024", 2023, 2024),
        ("2025+", 2025, 2026),
    ]:
        for v in ["primary", "without_atr", "named_observation", "named_rsi6"]:
            g = trades[trades.variant.eq(v) & trades.entry_year.between(a, b)]
            cyc.append({"period": label, "variant": v, **r.statistics(g)})
    pd.DataFrame(cyc).to_csv(OUT / "historical-cohorts.csv", index=False)
    yy = y[y.variant.isin(["primary", "without_atr"])].pivot(
        index="entry_year", columns="variant", values="cost4_ex_funding_mean_pct"
    )
    yy["atr_increment_pct"] = yy.primary - yy.without_atr
    gate = {
        "sample_100": int(s.loc["primary", "closed"]) >= 100,
        "three_entry_years": primary.entry_year.nunique() >= 3,
        "positive_cost4_mean": bool(s.loc["primary", "cost4_ex_funding_mean_pct"] > 0),
        "positive_cost4_median": bool(
            s.loc["primary", "cost4_ex_funding_median_pct"] > 0
        ),
        "positive_cost8_mean": bool(s.loc["primary", "cost8_ex_funding_mean_pct"] > 0),
        "atr_increment_two_years": int(yy.atr_increment_pct.gt(0).sum()) >= 2,
    }
    v = named.cost_adjusted_ex_funding_4bps.dropna().sort_values(ascending=False)
    concentration = {
        "named_top3_share_positive_pnl_pct": float(
            v.head(3).sum() / v[v > 0].sum() * 100
        ),
        "named_mean_after_removing_top1_pct": float(v.iloc[1:].mean() * 100),
        "named_mean_after_removing_top3_pct": float(v.iloc[3:].mean() * 100),
        "named_mean_after_removing_top5_pct": float(v.iloc[5:].mean() * 100),
    }
    audit = {
        "status": "REPLAY_ARITHMETIC_AND_TIMING_CHECKS_PASS",
        "closed_trades": len(closed),
        "total_records": len(trades),
        "prefrozen_continuation_screen": gate,
        "screen_pass": all(gate.values()),
        "main_result": "HARD-GATE-FAILED",
        "not_a_live_promotion_review": True,
        "funding_verified": False,
        "pit_proven": False,
        "concentration": concentration,
        "known_implementation_repairs": [
            "Before first completed replay: pandas read-only signal array changed to an owned boolean copy. No rule changed.",
            "Formatting after execution checked by AST equivalence; original executed sources retained.",
        ],
        "added_descriptive_audits": "Month bootstrap, concentration and terminal marks are diagnostic summaries, not searched parameters or clean OOS.",
    }
    (OUT / "acceptance.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    )
    named_by = by[by.variant.eq("named_observation")].copy()
    named_by["symbol"] = named_by.symbol.str.split("/").str[0]
    named_by = pd.concat(
        [named_by, pd.DataFrame([{"symbol": "LIT", "closed": 0}])], ignore_index=True
    )
    show = s.reset_index()
    recent_primary = recent[recent.variant.eq("primary")]
    open_names = trades[
        trades.variant.eq("named_rsi6") & trades.status.eq("censored")
    ].copy()
    open_names["gross_mark_pct"] = open_names.last_mark_gross * 100
    open_names.to_csv(OUT / "named-open-positions.csv", index=False)
    events = pd.read_parquet(OUT / "forward-events.parquet")
    forward = []
    for (h, a), g in events[events.valid].groupby(["horizon_days", "atr_declining"]):
        forward.append(
            {
                "days": h,
                "atr_down": a,
                "n": len(g),
                "mean": g.gross_return.mean() * 100,
                "median": g.gross_return.median() * 100,
                "btc_excess": g.btc_excess.mean() * 100,
            }
        )
    bootstrap = json.loads((OUT / "bootstrap.json").read_text())
    report = f"""# BIN-4H-BSRAP P0：牛市强势币 RSI 超卖、ATR 下降做多研究

日期：2026-09-07。家族：`Binance-4H-Bull-Strong-RSI-ATR-Pullback`。状态：`explore / diagnostic-only / HARD-GATE-FAILED / not promoted / not live-ready`。

## 结论

**你的近期观察有对应案例，但本轮固定的动态强势币规则未显示通用收益优势。** RSI14 主规则 247 笔已平仓交易，平均毛收益 −1.14%；扣每边0.1%手续费及4bps滑点、未扣资金费率后平均 −1.41%，中位数 −3.40%，胜率19.03%。去掉 ATR 下降过滤后平均为 −0.52%，本轮 ATR 条件没有改善整体结果。

点名币种的回顾组 52 笔交易平均 +2.65%，但中位数 −2.06%；收益集中于少数 UNI/ZEC/HYPE 行情。该组是用户在观察行情后点名，不能作为事前选币证明。最大的3笔贡献全部正收益的 {concentration["named_top3_share_positive_pnl_pct"]:.1f}%；去掉最大3笔后平均仅 {concentration["named_mean_after_removing_top3_pct"]:.2f}%，去掉最大5笔后为 {concentration["named_mean_after_removing_top5_pct"]:.2f}%。这些删除只检验集中度，不修改策略或否认趋势系统可以依赖大盈利。

**RSI 周期会改变你看到的案例。** RSI14 的点名组最近1个月和3个月没有入场；事前固定的 RSI6 对照则捕捉到 HYPE 与 ZEC 的近期上涨：截至2026-09-05 12:00 UTC，两笔仍未触发止损，分别有约6.04%和26.95%的毛浮盈。不能把仍持有交易排除后，仅凭近期已平仓均值否认这些案例；也不能把浮盈当已实现净利润。

{table(open_names, ["symbol", "entry_time", "gross_mark_pct", "reason"], ["币种", "入场 UTC", "截至截止毛浮盈 %", "状态"])}

同一 RSI6 点名组最近30天还有11笔已平仓交易，扣成本未扣资金费率平均 −1.46%；完整历史427笔已平仓平均 −0.36%，另有上述2笔持仓。把全历史未平仓两笔按截止价假想平仓单列估值后，均值仍非正，详见[终点估值诊断](../artifacts/p0-20260907/terminal-mark-diagnostic.csv)。这不是正式退出规则，也不是账户收益。

## 研究规则与边界

完整、在结果前固定的定义见[P0契约](../specs/p0-contract.md)、[配置](../specs/p0-config.json)、[冻结哈希](../specs/p0-prefit-hashes.json)。未搜索参数，没有据结果选择“最佳版本”。

1. 牛市：BTC 4H close>SMA360（60天），SMA360高于30根前（5天前），过去180根（30天）收益>0。它只是本轮可复现的牛市代理，不是对所有牛市起点的唯一认定。
2. 流动性：已完成至少187根连续有效4H历史，过去7日平均每日成交额≥1000万USDT；每根按成交额前100。
3. 强势：截至上一天的过去30日收益为正，并在该成交活跃样本排名前20%。只用当时已知价格，避开本次4H超卖即时下跌对强势排名的部分影响。
4. 入场：已收盘4H Wilder RSI14≤30，ATR14小于6根前；下一根相邻4H开盘市价做多。
5. 止损：初始 SMA7−2ATR14，后续每根收盘只允许上移。下一根开盘跳空穿线按更差开盘，否则盘中low触线即退出；新线若已在收盘之上则下一开盘市价退出。未触发就持有，不止盈、不超时、不因排名或牛市过滤消失卖出。
6. 一个币同一时间最多一笔；没有组合资金分配、杠杆或调仓净值。初始止损≥下一开盘或≤0时不买入。

点名组使用同样的牛市、流动性、RSI和ATR规则，但不再要求动态前20%排名，因为名单本身已经是事后观察选择。两组差异同时包含选币方式，不能只把均值差异归因于某一指标。

## 输入与质量

- 市场：Binance USD-M USDT永续。请求库存652个观测 COIN；实际读取3,592,113根4H，严格启动检查通过。应用零成交、缺口、LIT身份切分后有效行3,293,263，187根完整预热后3,170,480行；3个代码无足够预热，不贡献入场。
- 输入：固定 `binance.v3.research_inputs.v2`，4H为 `binance.perp.ohlcv.4h.from_15m.v2`，唯一源于15m V3；五组文件内容哈希与本次价格窗口验证通过。[启动报告](../artifacts/p0-20260907/startup-report.json)、[特征清单](../artifacts/p0-20260907/features-manifest.json)、[逐币覆盖](../artifacts/p0-20260907/data-coverage.csv)。
- UTC价格范围：2019-09-08 20:00至2026-09-05 12:00，2020-01-01起计交易。北京时间最后收盘为9月5日20:00，**不覆盖9月6–7日的新行情**。
- LIT旧历史不当作Lighter：只允许2025-12-23 17:30 UTC新合约边界之后的数据；[币安上线公告](https://www.binance.com/en-NZ/support/announcement/detail/6a33be00231c4539b3a4a625538e4d1e)明确新合约标的是Lighter。其盘前时段仍只作价格诊断，未证明标准交易条件。主RSI14点名规则下LIT没有交易。
- PONS未确认且不在固定组合库存；未替换成相似代码，结论不覆盖PONS。
- 652代码没有按今天TRADING筛选，但观测分类、合约身份和幸存库存仍不等于完整历史PIT。不得将动态行情排序称为已经核实可交易的历史全市场。
- 资金费率历史日历与独立身份窗口未完成；本轮从开始就选择价格诊断模式，没有在净收益门禁失败后偷偷降级。**所有 cost4/cost8 都是扣手续费滑点、未扣funding，不是净收益。** 资金费率未填0，也不报告账户CAGR、Sharpe、最大回撤或净值。

## 全部预先固定对照

下表为独立交易等入场名义金额的均值，不可累加或当作组合回报。gross为不含任何成本；cost4/cost8均未扣funding。未完成数量包含研究截止或缺口不确定事件。

{table(show, ["variant", "closed", "censored", "gross_mean_pct", "cost4_ex_funding_mean_pct", "cost4_ex_funding_median_pct", "cost4_ex_funding_win_pct", "cost4_ex_funding_pf", "cost8_ex_funding_mean_pct"], ["规则", "已平仓", "未完成", "毛均值%", "成本4bp均值%", "成本4bp中位数%", "胜率%", "等名义PF", "压力8bp均值%"])}

`primary`为主规则；`without_atr/strong/bull`各去掉对应过滤；`trend_state_only`保留牛市+强势但去掉RSI/ATR；`rsi6_30`和`rsi14_35`改变RSI；`natr_decline`比较ATR/close；`unratcheted_band`允许原始MA7−2ATR带下移；`named_*`为事后点名组。敏感性都不是新的OOS或选优许可。

主规则共有492个信号，233次出现在已有持仓时，11次因下一开盘已在初始止损下方而跳过，实际248次入场、247次平仓和1次截止持仓。主规则没有跨缺口而被静默删掉的盈利/亏损交易；其他组的缺口不确定持仓仍单列，终点估值遇到这类缺口保持无效。见[信号计数](../artifacts/p0-20260907/signal-counts.csv)。

## 年份与近期窗口

{table(yy.reset_index(), ["entry_year", "primary", "without_atr", "atr_increment_pct"], ["入场年", "主规则均值%", "无ATR均值%", "ATR差值百分点"])}

主规则2020/2021为正但仅8/7笔，2022–2026各年均为负。历史三段见[2020–2022、2023–2024、2025+](../artifacts/p0-20260907/historical-cohorts.csv)。全部为回顾诊断，2025+是已观察/复用历史，不存在新揭示盲OOS。

{table(recent_primary, ["window", "closed", "censored", "carried_in", "cost4_ex_funding_mean_pct"], ["近期窗口", "本窗口入场且已平仓", "本窗口入场未完成", "窗口前入场后续仍持有过", "成本4bp均值%"])}

这些是以最后收盘锚定的**入场批次**，不等于期间完整账户收益。1/3/6月分别按30/90/180天，长期持仓跨窗口另列carried_in；成交退出时点在4H内只知区间，不能伪装为精确分钟成交。

## 点名币种明细

{table(named_by, ["symbol", "closed", "cost4_ex_funding_mean_pct", "cost4_ex_funding_median_pct", "cost4_ex_funding_win_pct"], ["币种", "已平仓数", "成本4bp均值%", "中位数%", "胜率%"])}

HYPE正均值只有4笔支撑；UNI中位数仍为负，ZEC最大一笔2026-04-29至05-11毛收益约73.33%。BTC/ARB在本定义下没有显示正收益。原始逐笔记录见[交易CSV](../artifacts/p0-20260907/trades.csv)。

## 将入场现象与止损结果分开

同样在牛市+动态强势+RSI14≤30的候选时点，从下一开盘计算固定1/3/7日收益，按ATR是否下降分组。未来窗口独立验证，不影响入场选择；这是可重叠事件统计，样本数不等于策略交易数。

{table(pd.DataFrame(forward), ["days", "atr_down", "n", "mean", "median", "btc_excess"], ["持有天数", "ATR下降", "完整事件", "毛均值%", "毛中位数%", "同期BTC超额均值%"])}

ATR下降组1日均值为正，但3/7日中位数为负，7日对BTC的平均超额也为负。可见“超卖后反弹”与“在指定移动止损下持续拿住并获利”是不同的待检验环节；本结果没有授权事后删除止损或改用最优持有天数。见[完整标签](../artifacts/p0-20260907/forward-events.parquet)。

主规则按入场月份成组重抽样2000次（固定种子9072026）的每笔成本后未扣资金费率均值95%区间约[{bootstrap["ci95_mean_pct"][0]:.2f}%, {bootstrap["ci95_mean_pct"][1]:.2f}%]，包含0。月份聚类保留同月币种联动，但跨月依赖和38个有交易月份限制推断；这不是独立交易显著性证明。[bootstrap记录](../artifacts/p0-20260907/bootstrap.json)。

## 裁决与下一步

预先固定的继续研究筛查：样本数与跨年数满足；均值、中位数和8bps压力均值为正三项均失败。ATR差值在至少两年为正满足，但整体差值为负。因此本轮固定主规则结果标签为 `HARD-GATE-FAILED`，主状态仍为 `explore`，不登记、不晋升、不上线。它否定的是本轮明确的牛市/强势/RSI14/ATR14/盘中触线组合，不能证明你使用的任何其他指标定义都无效。

后续应先确认你图表的RSI周期及PONS身份，核对近期两个成功案例与原始观察是否一致。若继续，保持这批历史结果冻结，先补全可审核的合约身份、结算日历和有资金上限的组合规则，再用尚未观察的未来区间验证。当前没有证据支持继续围绕这批历史大规模搜索阈值。

## 复现与验证

定向执行/因果测试与组合输入门禁测试合计 **62 passed**；两次完整回放的12份核心产物SHA逐一一致。本家族消费者已登记且扫描无错误；全仓治理扫描仍有6个其他家族脚本未登记，故不宣称全仓检查通过，详见[验证记录](../artifacts/p0-20260907/validation.json)。

- [构建脚本](../scripts/build_p0_features.py)调用启动API并直接使用返回帧；[回放脚本](../scripts/replay_p0.py)只读该家族有SHA校验的特征快照；[汇总验算](../scripts/package_p0_results.py)重新从开平原价验算全部交易毛收益及双边成本、时序、互斥持仓和汇总一致性。
- 11项定向测试覆盖下一开盘、入场K触线、禁止同K未来止损、跳空更差成交、只上移止损、线已穿价、缺口持仓无效、信号不跨缺口、恢复不卖出、指标前缀不变和分段预热。原始执行源码已保留；后续格式整理有[AST等价证据](../artifacts/p0-20260907/format-equivalence.json)。
- 首次未完成回放遇到pandas只读数组写入问题，改为显式自有布尔副本后重跑；没有变更指标或交易规则。没有将失败输出作为结果。
- [验算与筛查](../artifacts/p0-20260907/acceptance.json) · [结果清单](../artifacts/p0-20260907/result-manifest.json)。完整运行输入依赖本地数据湖，产物被Git忽略，不随代码自动分发。

```bash
.venv/bin/pytest -q tests/test_binance_4h_bsrap_p0.py tests/test_research_bundle.py tests/test_trusted_consumers.py
.venv/bin/python research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts/replay_p0.py
.venv/bin/python research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts/package_p0_results.py
```

首次构建运行build_p0_features.py；它拒绝覆盖既有目录。重新完整构建应使用独立输出目录并保留已有输入请求；禁止先删除本次证据。回放再现同一冻结结果可重复执行，不能修改配置后覆盖同名产物。
"""
    target = FAMILY / "diagnostics/p0-results-2026-09-07.md"
    target.write_text(report)
    # Snapshots are textual evidence, not active consumers discoverable as .py modules.
    for p in (OUT / "provenance").glob("*.py"):
        p.rename(p.with_suffix(".py.txt"))
    (OUT / "delivery-manifest.json").write_text(
        json.dumps(
            {
                "artifacts": {
                    str(p.relative_to(OUT)): sha(p)
                    for p in OUT.rglob("*")
                    if p.is_file() and p.name != "delivery-manifest.json"
                },
                "report_sha256": sha(target),
            },
            indent=2,
        )
        + "\n"
    )
    print(
        "Report and independent arithmetic checks complete; screen pass:",
        all(gate.values()),
    )


if __name__ == "__main__":
    main()
