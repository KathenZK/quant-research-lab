"""P1：独立验算与中文结论；附加归因不改变冻结规则。"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
OUT = FAMILY / "artifacts/p1-20260907"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump(p, obj):
    p.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        + "\n"
    )


def table(df, cols, labels):
    rows = [
        "| " + " | ".join(labels) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for vals in df[cols].itertuples(index=False, name=None):
        cells = []
        for v in vals:
            if pd.isna(v):
                cells.append("—")
            elif isinstance(v, (float, np.floating)):
                cells.append(f"{v:.2f}")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def fee_return(r, bps=4):
    z = (1 + r) * (1 - bps / 10000) / (1 + bps / 10000)
    return z - 1 - 0.001 * (1 + z)


def verify(daily, four, events, trades):
    m = json.loads((OUT / "input-manifest.json").read_text())
    for n, h in m["artifacts"].items():
        assert sha(OUT / n) == h, n
    for n, h in m["prefit"].items():
        assert sha(FAMILY / n) == h, n
    parent = json.loads((FAMILY / "specs/p1-parent-protection.json").read_text())
    for n, h in parent.items():
        assert sha(FAMILY / n) == h, n
    dg = {s: g.set_index("ts") for s, g in daily.groupby("symbol")}
    checked = 0
    for h, g in events[events.valid].groupby("horizon_days"):
        for _, e in g.sample(min(200, len(g)), random_state=907 + h).iterrows():
            a = e.available_at
            b = a + pd.Timedelta(days=int(h))
            bars = dg[e.symbol]
            x = bars.loc[a, "open"]
            z = bars.loc[b, "open"] / x - 1
            assert np.isclose(z, e.gross_return, rtol=0, atol=1e-12)
            path = bars.loc[(bars.index >= a) & (bars.index < b)]
            assert len(path) == h
            assert np.isclose(path.low.min() / x - 1, e.mae, rtol=0, atol=1e-12)
            assert np.isclose(path.high.max() / x - 1, e.mfe, rtol=0, atol=1e-12)
            checked += 1
    assert (four.daily_available_key <= four.signal_time).all()
    assert ((four.signal_time - four.daily_available_key) < pd.Timedelta(days=1)).all()
    fg = four.set_index(["symbol", "ts"])
    closed = trades[trades.status.eq("closed")]
    for _, t in trades.iterrows():
        assert t.entry_time - t.signal_bar_open == pd.Timedelta(hours=4)
        signal = fg.loc[(t.symbol, t.signal_bar_open)]
        assert signal.admission
        assert 0 < t.initial_stop < min(t.entry_raw, signal.close)
        assert np.isclose(t.initial_stop, signal.stop_band, rtol=0, atol=1e-12)
        assert t.notional <= 0.2 * t.initial_budget_equity + 1e-7
        assert t.entry_risk <= 0.005 * t.initial_budget_equity + 1e-7
        assert t.risk_before + t.entry_risk <= 0.02 * t.initial_budget_equity + 1e-7
        if t.variant in ["rsi14_pullback", "rsi14_atr_pullback"]:
            assert signal.rsi14 <= 30
        if t.variant == "rsi14_atr_pullback":
            assert signal.atr_down
        if t.variant == "rsi14_reclaim":
            assert signal.rsi14 > 30
    for (v, bps), g in trades.groupby(["variant", "slippage_bps"]):
        hist = pd.read_parquet(OUT / f"p1-budget-path-{v}-{bps}bp.parquet")
        assert hist.position_count.max() <= 5
        assert hist.cash_ex_funding.min() >= -1e-7
        c = g[g.status.eq("closed")]
        ratio = c.exit_fill / c.entry_fill
        assert np.allclose(
            c.return_ex_funding, ratio - 1 - 0.001 * (1 + ratio), atol=1e-12, rtol=0
        )
        assert np.allclose(
            c.pnl_ex_funding,
            c.qty * (c.exit_fill - c.entry_fill)
            - 0.001 * c.qty * (c.exit_fill + c.entry_fill),
            atol=1e-7,
            rtol=0,
        )
        recon = (
            100000
            + c.pnl_ex_funding.sum()
            + g.loc[g.status.eq("censored"), "mark_pnl_ex_funding"].sum()
        )
        assert np.isclose(
            recon,
            hist.hypothetical_liquidation_value_ex_funding.iloc[-1],
            atol=1e-6,
            rtol=0,
        )
        for _, a in c.groupby("symbol"):
            a = a.sort_values("entry_time")
            assert (
                a.entry_time.iloc[1:].reset_index(drop=True)
                > a.exit_bar_open.iloc[:-1].reset_index(drop=True)
            ).all()
    return {
        "status": "PASS_FOR_ENGINE_ARITHMETIC_NOT_STRATEGY",
        "sampled_independent_forward_labels": checked,
        "verified_entry_records": len(trades),
        "closed_records": len(closed),
        "p0_protected_files": len(parent),
        "daily_information_time_checked_rows": len(four),
        "scope": "price and cost timing only; funding/PIT and real execution not verified",
    }


def attribution(four, trades):
    # New descriptive attribution after the main results: no new trading rule is selected.
    frames = {s: g.set_index("ts") for s, g in four.groupby("symbol")}
    rows = []
    for _, t in trades[
        (trades.slippage_bps == 4) & trades.status.eq("closed")
    ].iterrows():
        g = frames[t.symbol]
        for h in [3, 7, 14]:
            end = t.entry_time + pd.Timedelta(days=h)
            if end not in g.index:
                continue
            path = g.loc[(g.index >= t.entry_time) & (g.index <= end)]
            if (
                len(path) != 6 * h + 1
                or path.research_segment_id.isna().any()
                or path.research_segment_id.nunique() != 1
            ):
                continue
            fixed = fee_return(g.loc[end, "open"] / t.entry_raw - 1)
            rows.append(
                {
                    "variant": t.variant,
                    "symbol": t.symbol,
                    "entry_time": t.entry_time,
                    "horizon_days": h,
                    "fixed_horizon_ex_funding": fixed,
                    "actual_stop_return_ex_funding": t.return_ex_funding,
                    "difference_stop_minus_fixed": t.return_ex_funding - fixed,
                }
            )
    a = pd.DataFrame(rows)
    a.to_parquet(OUT / "p1-same-entry-exit-attribution.parquet", index=False)
    result = (
        a.groupby(["variant", "horizon_days"])
        .agg(
            pairs=("symbol", "size"),
            fixed_mean=("fixed_horizon_ex_funding", "mean"),
            actual_stop_mean=("actual_stop_return_ex_funding", "mean"),
            stop_minus_fixed=("difference_stop_minus_fixed", "mean"),
        )
        .reset_index()
    )
    for c in ["fixed_mean", "actual_stop_mean", "stop_minus_fixed"]:
        result[c] *= 100
    result.to_csv(OUT / "p1-same-entry-exit-attribution.csv", index=False)
    return result


def main():
    daily = pd.read_parquet(OUT / "daily-features.parquet")
    four = pd.read_parquet(OUT / "four-hour-features.parquet")
    events = pd.read_parquet(OUT / "p1-events.parquet")
    trades = pd.concat(
        [pd.read_parquet(p) for p in sorted(OUT.glob("p1-trades-*.parquet"))],
        ignore_index=True,
    )
    audit = verify(daily, four, events, trades)
    attr = attribution(four, trades)
    d = pd.read_parquet(OUT / "p1-day-comparisons.parquet")
    effect = json.loads((OUT / "p1-state-inference.json").read_text())
    y = pd.read_csv(OUT / "p1-by-year.csv")
    market = pd.read_csv(OUT / "p1-market-effect.csv")
    strength = pd.read_csv(OUT / "p1-strength-effect.csv")
    entry = pd.read_csv(OUT / "p1-entry-summary.csv")
    validity = pd.read_csv(OUT / "p1-validity-counts.csv")
    nonoverlap = json.loads((OUT / "p1-nonoverlap-sensitivity.json").read_text())
    seven = d[(d.horizon_days == 7) & (d.valid > 0)]
    periods = []
    for label, a, b in [
        ("2020–2022", 2020, 2022),
        ("2023–2024", 2023, 2024),
        ("2025+", 2025, 2026),
    ]:
        all_ = seven[seven.entry_year.between(a, b)]
        bull = all_[all_.bull]
        periods.append(
            {
                "period": label,
                "bull_days": len(bull),
                "all_mean_pct": all_.all_cost4_ex_funding.mean() * 100,
                "bull_mean_pct": bull.all_cost4_ex_funding.mean() * 100,
                "strong_mean_pct": bull.strong_cost4_ex_funding.mean() * 100,
            }
        )
    pd.DataFrame(periods).to_csv(OUT / "p1-historical-cohorts.csv", index=False)
    excl = seven[seven.entry_year.ne(2021)]
    audit["exclude_2021"] = {
        "bull_mean_pct": excl[excl.bull].all_cost4_ex_funding.mean() * 100,
        "all_mean_pct": excl.all_cost4_ex_funding.mean() * 100,
    }
    # Same-date paired ranking sensitivity after removing a historically biggest contributor.
    selected = events[
        (events.horizon_days == 7) & events.valid & events.bull & events.strong
    ]
    coin = (
        selected.groupby("symbol")
        .cost4_ex_funding.agg(["size", "mean", "sum"])
        .sort_values("sum", ascending=False)
    )
    coin.to_csv(OUT / "p1-selected-coin-contributions.csv")
    audit["largest_selected_coin_by_unweighted_event_sum"] = str(coin.index[0])
    remaining = events[
        (events.horizon_days == 7)
        & events.valid
        & events.bull
        & events.symbol.ne(coin.index[0])
    ]
    pairs = []
    for _, g in remaining.groupby("available_at"):
        a = g[g.strong]
        rest = g[~g.strong]
        if len(a) >= 3 and len(rest) >= 3:
            pairs.append(a.cost4_ex_funding.mean() - g.cost4_ex_funding.mean())
    audit["remove_largest_coin_strong_minus_pool_pp"] = float(np.mean(pairs) * 100)
    # Latest detector output is a dated observation, not a current trading instruction.
    latest = daily[daily.ts.eq(daily.ts.max()) & daily.pool].sort_values(
        ["mom30", "symbol"], ascending=[False, True]
    )
    latest[
        [
            "symbol",
            "available_at",
            "mom30",
            "strong",
            "strong_last5_count",
            "breadth",
            "state",
        ]
    ].to_csv(OUT / "p1-latest-ranked-watchlist.csv", index=False)
    latest_names = latest[
        latest.symbol.isin(
            [s + "/USDT:USDT" for s in ["BTC", "HYPE", "LIT", "UNI", "ARB", "ZEC"]]
        )
    ].copy()
    latest_names["momentum_pct"] = latest_names.mom30 * 100
    dump(OUT / "p1-acceptance.json", audit)
    m7 = next(v for v in effect["market"] if v["horizon_days"] == 7)
    s7 = next(v for v in effect["strength"] if v["horizon_days"] == 7)
    base = entry[entry.slippage_bps.eq(4)].copy()
    names = {
        "direct": "合格后直接做多",
        "rsi14_pullback": "RSI14超卖",
        "rsi14_reclaim": "RSI14回升确认",
        "rsi14_atr_pullback": "RSI14超卖＋ATR下降",
    }
    base["entry_rule_zh"] = base.variant.map(names)
    attr["entry_rule_zh"] = attr.variant.map(names)
    validation = json.loads((OUT / "p1-validation.json").read_text())
    scanner = validation["trusted_consumers"]
    known = validity[validity.reason.eq("gap_or_identity_or_symbol_end")].events.sum()
    tail = validity[validity.reason.eq("right_censor_cutoff")].events.sum()
    report = f"""# BIN-4H-BSRAP P1：牛市、强势币识别与入场研究

日期：2026-09-07。独立观察P1；P0保持不变。本报告只包含回顾性价格诊断，所有“扣成本”均扣每边0.1%手续费和4bps不利滑点、**未扣资金费率**。不构成永续净收益或实盘策略验证。

## 结论

**目前三个问题的答案不同：市场状态有历史区分度；30日涨幅前20%未证明稳定的额外选币价值；四种带MA7−2ATR止损的资金约束入场回放仍全部亏损。** 不能推导出“识别牛市和强势币之后找个买点就一定可以”。

- 市场：牛市条件下未来7日活跃币池平均 +2.60%，全时期 +0.32%，非牛市 −0.63%；差值 +2.27个百分点，月份整块重抽样95%区间约[{m7["interval"]["ci95_pp"][0]:.2f}, {m7["interval"]["ci95_pp"][1]:.2f}]个百分点。预先固定的市场继续研究筛查通过，只表示值得进一步验证。
- 强势：同样牛市日期，前20%强势币7日均值 +2.63%，一般活跃池 +2.60%，差值只有 +0.031个百分点；95%区间约[{s7["interval"]["ci95_pp"][0]:.2f}, {s7["interval"]["ci95_pp"][1]:.2f}]个百分点，包含零。14日差值为负，强势筛查未通过。
- 稳定性：牛市条件选出的7日收益在2025、2026分别仍为 −1.88%、−0.55%；2025+合并为 −1.44%。总体正均值不能代替近期可盈利性。去掉2021后牛市均值降至 +{audit["exclude_2021"]["bull_mean_pct"]:.2f}%，显著弱于全历史。
- 入场：直接参与、RSI超卖、RSI回升确认和超卖+ATR下降，资金约束价格贡献均为负。回升确认亏损较少，但平均敞口也更低，不能据亏损金额较小就宣布买点有效。

主状态保持 `explore / diagnostic-only / not promoted / not live-ready`。P0失败未被撤销，P1也没有注册版本或进入runner。

## 固定定义

[完整契约](../specs/p1-contract.md)和[配置](../specs/p1-config.json)均先于P1结果写入；没有根据收益更改阈值。

| 模块 | P1规则 |
| --- | --- |
| 活跃池 | 同一有效段至少60根日线，过去20完整日成交额中位数≥1000万USDT；按成交额前100 |
| BTC趋势 | 已完成日线close>SMA100，且SMA50>SMA50的5日前值 |
| 市场广度 | 活跃池close>SMA50的比例；至少20币才判断，>60%为广 |
| 牛市 | BTC趋势与广度同时满足 |
| 强势 | 活跃池30日收益>0，按30日收益前20%（人数向上取整，平手按代码） |
| 日线信息可用 | 日K开盘+1天后才可使用；4h只用最近已完成日线，不跨缺失日长期前填 |
| 入场 | 4h收盘信号、下一相邻4h开盘；主比较直接、RSI14≤30、超卖后首次上穿30；加ATR低于6根前为固定对照 |
| 退出 | 4h SMA7−2ATR14只上移；盘中触及旧有效stop退出，跳空用更差open；新线已超过close时下一open退出 |
| 重复信号 | RSI组每轮超卖最多成功开仓一次，RSI>30后重置；回升组需之前合格超卖并在上穿时仍合格 |

相对P0，P1改变了市场与强势定义、日线信息时点和超卖阶段重复入场规则；P0只作为受保护历史，不与P1混成一个固定参数版本。

## 输入、窗口与质量

本次重新通过固定组合 `binance.v3.research_inputs.v2` 的两个启动请求，实际消费其返回帧。日线598,035行，4h 3,592,113行，652个观测COIN库存；日线最后完整收盘2026-09-05 00:00UTC，4h最后收盘2026-09-05 12:00UTC。数据不是更新到运行当日。

日线与4h均在缺口、零成交和已知身份边界重置；LIT不拼接旧同名资产，只允许2025-12-23 17:30UTC之后新Lighter区间。PONS未确认且不在该输入库存，不纳入。动态币池依赖当时已观测行情，但观测分类和完整历史身份仍未证明PIT；不宣称无幸存者偏差。

[日线启动检查](../artifacts/p1-20260907/startup-1d.json) · [4h启动检查](../artifacts/p1-20260907/startup-4h.json) · [输入清单](../artifacts/p1-20260907/input-manifest.json)。从2020-01-01开始允许研究，实际主7日完整市场样本为2020-08-09至2026-08-28的2211个决策日，牛市656日，均为UTC零点；早期币数/预热不足日不当熊市。

615,251个币种×日期×期限标签完整；{known}个因缺口/身份/币种历史终点无效，{tail}个因数据右端不足未来窗口无效。每个期限独立判有效性；不使用未来缺失决定历史成员，也不将无效标签算亏损或零收益。见[有效性分母](../artifacts/p1-20260907/p1-validity-counts.csv)。不完整标签仍限制精确历史结论。

## 1．牛市识别结果

先每天对合格币等权求未来收益，再跨决策日等权；下表是条件前瞻事件均值，不是可直接复利的账户收益。3/7/14日标签重叠，主期限事前固定为7日。

{table(market, ["horizon_days", "all_days", "bull_days", "all_mean_pct", "bull_mean_pct", "nonbull_mean_pct", "bull_increment_pp"], ["未来天数", "完整日数", "牛市日数", "全时期均值%", "牛市均值%", "非牛市均值%", "牛市增量百分点"])}

牛市占主样本时间29.67%，保留了40.24%的正向市场前瞻收益总和，单位时间的正向收益保留约为全时期的1.36倍。但仍漏掉约59.76%的正向前瞻收益；这个比例是重叠事件的机会指标，不是账户利润捕获率。

四状态7日均值：BTC向上+广度强 +2.60%，BTC向上+广度弱 +0.46%，BTC向下+广度强 −2.12%，BTC向下+广度弱 −0.93%。广度在本定义下提供了区分，不能把“许多币站上均线”单独等同于可盈利牛市。[全部状态](../artifacts/p1-20260907/p1-state-summary.csv)。

{table(y[y.horizon_days.eq(7)], ["entry_year", "bull_days", "market_all_mean_pct", "market_bull_mean_pct", "market_increment_pp"], ["年份", "牛市日数", "全年均值%", "牛市均值%", "牛市差值百分点"])}

市场继续筛查满足“至少100日、跨3年、7日均值/增量为正、至少3年增量为正、3/14日增量同向”。但2020/2022/2024年度增量为负，2025/2026绝对收益仍负，故只能称有回顾性的条件分层，不能叫已可靠识别未来牛市。

## 2．强势币识别结果

下表严格比较同一天、同样牛市环境。先计算强势篮子、一般池和其余币的均值，再跨日期求配对差值，避免只因选择了不同市场月份而把市场收益当选币收益。

{table(strength, ["horizon_days", "paired_days", "strong_mean_pct", "pool_mean_pct", "rest_mean_pct", "strong_minus_pool_pp"], ["未来天数", "配对日数", "强势均值%", "一般池均值%", "其余币均值%", "强势增量百分点"])}

3/7/14日差值的月份整块bootstrap区间都包含0；7日增量仅0.031个百分点，14日变负。逐年有的年份为正、有的为负，不能认为“过去30日最强”就能持续跑赢。原目标的总做多机会筛选也完整保留：牛市强势组合绝对均值为正，但其收益几乎没有超出牛市一般池，主要证据落在市场状态上。

固定每14日一个日期的非重叠敏感性中，7日强势增量为 {next(x for x in nonoverlap["strength"] if x["horizon_days"] == 7)["strong_minus_pool_pp"]:.2f}个百分点，14日也为负。去掉按7日强势事件简单加总贡献最大的币 {audit["largest_selected_coin_by_unweighted_event_sum"]} 后，配对增量为 {audit["remove_largest_coin_strong_minus_pool_pp"]:.3f}个百分点。删除只作集中度诊断，不据此更换币池。[重叠敏感性](../artifacts/p1-20260907/p1-nonoverlap-sensitivity.json) · [币种贡献](../artifacts/p1-20260907/p1-selected-coin-contributions.csv)。

## 3．入场与资金约束回放

共同预算：初始100000USDT，不借现金，同时最多5币；单币名义≤估算权益20%，每笔预计stop风险≤0.5%，新增后组合stop风险≤2%。同一时刻按已知日线30日收益排序。4bp与8bp分别完整回放。这里的预算只累计价格与成交费用，未知funding没有被替代为零；因此结果是**缺少资金结算项的条件性价格贡献**，不能解释为实际永续资金净值或实盘可用现金。

{table(base, ["entry_rule_zh", "closed", "open_or_censored", "mean_trade_return_ex_funding_pct", "price_contribution_pct_initial_budget", "mean_exposure_pct"], ["入场规则", "已平仓", "未平仓", "单笔均值%", "价格贡献/初始预算%", "平均敞口%"])}

全部资本路径没有遭遇持仓缺价而被中断，盘中释放的现金未倒流供同根开盘使用；仓位与风险门槛逐笔验算通过。期末持仓按假想清算成本估值，仍不计入已平仓胜率。8bp压力下四组价格贡献分别为−46.58%、−20.99%、−6.65%、−10.66%，仍全部为负。

回升确认组亏损较少，但平均敞口仅1.28%、交易也更少；不能把缩小参与规模或频率当作已经发现正收益买点。ATR过滤也没有形成正期望。完整[交易](../artifacts/p1-20260907/p1-entry-trades.csv)、[入场汇总](../artifacts/p1-20260907/p1-entry-summary.csv)、[近期入场批次](../artifacts/p1-20260907/p1-recent-entry-cohorts.csv)和[逐年](../artifacts/p1-20260907/p1-entry-by-year.csv)保留。

### 相同实际入场的退出归因

在看到主结果后，另做一项明确标为事后描述的核对：只固定本轮实际成交的相同币、相同入场时刻，对比其后3/7/14日价格标签与实际移动止损回报。不重选币、不改变任何交易结果；以下7日配对只使用两边均完整的记录。

{table(attr[attr.horizon_days.eq(7)], ["entry_rule_zh", "pairs", "fixed_mean", "actual_stop_mean", "stop_minus_fixed"], ["入场规则", "配对笔数", "固定7日均值%", "实际止损均值%", "止损减固定百分点"])}

固定持有承受的路径风险与实际止损不同、退出时间不同；这些标签不能复用原资金账户，因为持有时间会改变后续可用现金。这里仅选原回放已平仓且后续完整的样本，同币事件还可能重叠，因此不能当作替代策略的完整收益估计。它用于定位进入后的路径问题，不把7日改成新的优胜策略。

## 历史三段与近期边界

{table(pd.DataFrame(periods), ["period", "bull_days", "all_mean_pct", "bull_mean_pct", "strong_mean_pct"], ["历史段", "牛市日数", "一般时期7日%", "牛市一般池7日%", "牛市强势池7日%"])}

所有历史都是回顾诊断，2025+为复用已观察历史，未提供新盲OOS。主7日期末不足未来的日期仍列候选，但不伪造收益；最近1d/7d/1m/3m/6m/1y均锚定数据截止，详见[近期状态批次](../artifacts/p1-20260907/p1-recent-state-cohorts.csv)。入场批次也不是完整账户期间收益。

按最后可用日线，2026-09-05 00:00UTC时BTC趋势条件成立、活跃100币的广度为80%，分类为BTC_UP_BROAD。这只是截至该时刻的识别器读数，随后的7/14日结果尚未包含在本数据中，也不等于2026-09-07实时交易建议。

点名币在最后状态中的位置如下；未列入表示当时未进入冻结活跃池。完整[当时排序](../artifacts/p1-20260907/p1-latest-ranked-watchlist.csv)可核对，但不是推荐买入名单。

{table(latest_names, ["symbol", "momentum_pct", "strong", "strong_last5_count"], ["币种", "30日涨幅%", "是否前20%且上涨", "最近5日满足次数"])}

## 验证与后续决定

12项P1定向测试通过；加上P0与输入组合测试合计74项通过。独立抽查600个真实前瞻标签的开盘价、MAE/MFE，逐笔核对所有{audit["verified_entry_records"]}条成交记录的因果时序、初始止损、单币/组合风险，以及现金和期末价格贡献恒等式。P0的{audit["p0_protected_files"]}份受保护文件SHA未变。测试通过证明工程行为，不证明交易有效。[机器验收](../artifacts/p1-20260907/p1-acceptance.json)。

受控输入消费者扫描：本家族{len(scanner["family_errors"])}个错误，仓库全量仍有{scanner["repository_error_count"]}个其他家族错误，全量扫描未通过；另有8项扫描器单元测试通过。实际输出另存[验证记录](../artifacts/p1-20260907/p1-validation.json)，不将本家族通过扩大为全仓库通过。

这次可保留的研究方向是市场状态的条件分层；应冻结P1，再用未观察未来验证其收益保留与失效行为。“30日涨幅前20%”和本轮四种移动止损入场没有达到可用策略证据要求，不继续围绕已揭示结果批量搜参。其他强势定义是否有效仍是新问题，不能因本定义失败一概否定，也不能在没有证据时改称已识别强势。

如需进入净收益阶段，必须先完成独立身份、结算日历、真实资金约束与执行验证，不能把本轮价格贡献更名为净收益。Binance官方历史费率接口分别提供fundingTime、fundingRate与关联markPrice，本轮仅核对该接口定义，未下载或验收其历史完整性；见[官方接口说明](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)。

## 复现入口

- [输入构建](../scripts/build_p1_inputs.py)：重新调用两个启动请求，拒绝覆盖输出目录。
- [状态与强势研究](../scripts/research_p1_states.py)：哈希校验后读取本家族输入，生成逐事件与逐日配对。
- [统一预算入场](../scripts/replay_p1_entries.py)：同一退出/风险预算回放四种入场和两档滑点。
- [汇总验算](../scripts/package_p1_results.py)：独立经济验算、明确标记的同入场退出归因及本中文报告。

```bash
.venv/bin/pytest -q tests/test_binance_4h_bsrap_p0.py tests/test_binance_4h_bsrap_p1.py tests/test_research_bundle.py
.venv/bin/python research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts/research_p1_states.py
.venv/bin/python research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts/replay_p1_entries.py
.venv/bin/python research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts/package_p1_results.py
```

首次完整输入构建运行build_p1_inputs.py；该链使用固定P1输出路径，完整重建应在保留源数据访问的独立工作区进行，不删除或覆盖本次原始证据。数据湖与大部分artifacts不随Git自动分发。
"""
    target = FAMILY / "diagnostics/p1-market-strength-entry-2026-09-07.md"
    target.write_text(report)
    (OUT / "provenance/package_p1_results.py.txt").write_bytes(
        Path(__file__).read_bytes()
    )
    dump(
        OUT / "p1-delivery-manifest.json",
        {
            "report_sha256": sha(target),
            "source_hashes": {
                p.name: sha(p) for p in (FAMILY / "scripts").glob("*p1*.py")
            },
            "artifacts": {
                str(p.relative_to(OUT)): sha(p)
                for p in OUT.rglob("*")
                if p.is_file() and p.name != "p1-delivery-manifest.json"
            },
        },
    )
    print(
        "Independent checks passed:", json.dumps(audit, ensure_ascii=False), flush=True
    )
    print(attr[attr.horizon_days.eq(7)].to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
