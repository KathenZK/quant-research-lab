"""核验简单30日研究，分开报告轮次证据和未贯通账户。"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
OUT = FAMILY / "artifacts/p0-20260907"
NAMES = {"bull_top10": "牛市才买Top10", "always_top10": "一直轮动Top10"}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump(p, obj):
    p.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        + "\n"
    )


def table(df, cols, labels):
    lines = [
        "| " + " | ".join(labels) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for row in df[cols].itertuples(index=False, name=None):
        lines.append(
            "| "
            + " | ".join(
                "—"
                if pd.isna(x)
                else f"{x:.2f}"
                if isinstance(x, (float, np.floating))
                else str(x)
                for x in row
            )
            + " |"
        )
    return "\n".join(lines)


def main():
    frozen = json.loads((FAMILY / "specs/p0-replay-prefit.json").read_text())
    assert sha(FAMILY / frozen["source"]) == frozen["sha256"]
    manifest = json.loads((OUT / "result-manifest.json").read_text())
    assert sha(FAMILY / "scripts/replay_p0.py") == manifest["source_sha256"]
    for n, h in manifest["artifacts"].items():
        assert sha(OUT / n) == h, n
    for n, h in json.loads(
        (FAMILY / "specs/p0-prefit-hashes.json").read_text()
    ).items():
        assert sha(FAMILY / n) == h, n
    parent = json.loads((FAMILY / "specs/parent-protection.json").read_text())
    for n, h in parent.items():
        assert sha(ROOT / n) == h, n
    daily = pd.read_parquet(OUT / "daily-features.parquet")
    four = pd.read_parquet(OUT / "four-hour-prices.parquet")
    prices = four.set_index(["symbol", "ts"])
    summary = json.loads((OUT / "summary.json").read_text())
    rounds = pd.read_csv(
        OUT / "round-labels.csv", parse_dates=["entry_time", "scheduled_exit"]
    )
    decisions = json.loads((OUT / "decisions.json").read_text())
    markets = pd.read_parquet(OUT / "market-states.parquet").set_index("signal_time")
    checked = 0
    for dec in decisions:
        signal = pd.Timestamp(dec["signal_time"])
        execution = pd.Timestamp(dec["execution_time"])
        assert execution - signal == pd.Timedelta(hours=4)
        if dec["selected"]:
            sample = daily[daily.signal_time.eq(signal) & daily.pool].sort_values(
                ["mom30", "symbol"], ascending=[False, True]
            )
            assert dec["selected"] == sample.symbol.head(10).tolist()
            assert markets.loc[signal, "state_valid"]
            if dec["variant"] == "bull_top10":
                assert markets.loc[signal, "bull"]
        assert set(dec["filled"]) | set(dec["cancelled"]) == set(dec["selected"])
    for item in summary:
        v, bps = item["variant"], item["bps"]
        tx = pd.read_parquet(OUT / f"trades-{v}-{bps}bp.parquet")
        hist = pd.read_parquet(OUT / f"budget-path-{v}-{bps}bp.parquet")
        assert hist.cash.min() >= -1e-6 and hist.positions.max() <= 10
        for _, t in tx.iterrows():
            assert t.entry_time - t.signal_time == pd.Timedelta(hours=4)
            assert np.isclose(t.spent, 0.1 * t.budget_start, atol=1e-7, rtol=0)
            assert t.entry_raw == prices.loc[(t.symbol, t.entry_time), "open"]
            if t.status == "closed":
                assert t.exit_time - t.entry_time == pd.Timedelta(days=30)
                assert t.exit_raw == prices.loc[(t.symbol, t.exit_time), "open"]
                z = (
                    t.exit_raw
                    / t.entry_raw
                    * (1 - bps / 10000)
                    / (1 + bps / 10000)
                    * 0.999
                    / 1.001
                    - 1
                )
                assert np.isclose(z, t.return_ex_funding, atol=1e-12, rtol=0)
            checked += 1
        assert (
            item["full_price_contribution_pct"] is None
            if not item["path_valid"]
            else True
        )
    # All complete round labels are independently recomputed from raw opens.
    decision_map = {
        (d["variant"], pd.Timestamp(d["execution_time"])): d for d in decisions
    }
    labels = 0
    for _, r in rounds[rounds.valid].iterrows():
        dec = decision_map[(r.variant, r.entry_time)]
        val = 0
        for symbol in dec["filled"]:
            a = prices.loc[(symbol, r.entry_time), "open"]
            z = prices.loc[(symbol, r.scheduled_exit), "open"]
            val += 0.1 * (
                z / a * (1 - r.bps / 10000) / (1 + r.bps / 10000) * 0.999 / 1.001 - 1
            )
        assert np.isclose(val, r.return_ex_funding, atol=1e-12, rtol=0)
        labels += 1
    stats = []
    for (v, bps), g in rounds.groupby(["variant", "bps"]):
        valid = g[g.valid]
        missing = g.status.eq("holding_gap").sum()
        matured = len(valid) + int(missing)
        stats.append(
            {
                "variant": v,
                "name": NAMES[v],
                "bps": bps,
                "complete": len(valid),
                "holding_gap": int(missing),
                "right_censor": int(g.status.eq("right_censor").sum()),
                "mean_pct": valid.return_ex_funding.mean() * 100,
                "median_pct": valid.return_ex_funding.median() * 100,
                "win_pct": valid.return_ex_funding.gt(0).mean() * 100,
                "whole_bad_round_minus100_mean_lower_pct": (
                    valid.return_ex_funding.sum() - missing
                )
                / matured
                * 100,
                "mean_excluding_2021_pct": valid.loc[
                    valid.entry_time.dt.year.ne(2021), "return_ex_funding"
                ].mean()
                * 100,
            }
        )
    stats = pd.DataFrame(stats)
    stats.to_csv(OUT / "round-summary.csv", index=False)
    years = []
    valid4 = rounds[rounds.valid & rounds.bps.eq(4)]
    for (v, y), g in valid4.groupby(["variant", valid4.entry_time.dt.year]):
        years.append(
            {
                "variant": v,
                "year": int(y),
                "count": len(g),
                "mean_pct": g.return_ex_funding.mean() * 100,
            }
        )
    years = pd.DataFrame(years)
    years.to_csv(OUT / "round-by-year.csv", index=False)
    joined = years[years.variant.eq("bull_top10")].merge(
        years[years.variant.eq("always_top10")], on="year", suffixes=("_bull", "_all")
    )
    recent = []
    cutoff = pd.Timestamp("2026-09-05T12:00:00Z")
    for label, delta in [
        ("1d", pd.Timedelta(days=1)),
        ("7d", pd.Timedelta(days=7)),
        ("1m", pd.DateOffset(months=1)),
        ("3m", pd.DateOffset(months=3)),
        ("6m", pd.DateOffset(months=6)),
        ("1y", pd.DateOffset(years=1)),
    ]:
        for v, g in rounds[rounds.bps.eq(4)].groupby("variant"):
            s = g[g.entry_time.ge(cutoff - delta)]
            ok = s[s.valid]
            recent.append(
                {
                    "variant": v,
                    "slice": label,
                    "rounds": len(s),
                    "complete": len(ok),
                    "incomplete": int((~s.valid).sum()),
                    "mean_pct": ok.return_ex_funding.mean() * 100
                    if len(ok)
                    else np.nan,
                }
            )
    pd.DataFrame(recent).to_csv(OUT / "recent-round-cohorts.csv", index=False)
    bnx = four[
        four.symbol.eq("BNX/USDT:USDT")
        & (
            four.ts.between("2023-02-10T16:00:00Z", "2023-02-11T12:00:00Z")
            | four.ts.between("2025-03-17T04:00:00Z", "2025-03-17T20:00:00Z")
        )
    ]
    bnx.to_csv(OUT / "bnx-discontinuities.csv", index=False)
    audit = {
        "status": "ENGINE_CHECKS_PASS_FULL_ACCOUNT_DATA_FAILURE",
        "checked_records": checked,
        "verified_round_labels": labels,
        "protected_parent_files": len(parent),
        "funding_verified": False,
        "full_account_paths_pass": False,
        "reason": "BNX termination/settlement value is not verified; no fabricated continuation",
    }
    dump(OUT / "acceptance.json", audit)
    s4 = stats[stats.bps.eq(4)]
    bull = s4[s4.variant.eq("bull_top10")].iloc[0]
    plain = s4[s4.variant.eq("always_top10")].iloc[0]
    report = f"""# 牛市买Top10、持有30天：简化规则研究

2026-09-07。**简单规则的30日轮次结果值得继续验证；完整账户收益暂时不能确认。** 原因是BNX历史自动结算事件缺少已核验结算价值，不是这条交易想法已被证明失败。

## 规则只保留这些

- 沿用牛市条件：BTC日线>SMA100、SMA50高于5日前，且活跃币池超过60%站上SMA50。
- 空仓时每天检查；牛市就等权买过去30日涨幅前10，每币10%，不再加涨幅为正的过滤。
- 持满30个自然日。到期仍牛市就换新的前10，否则退出等下一次牛市；期间不设RSI、ATR或移动止损。
- 活跃池沿用过去20日成交额中位数≥1000万USDT、连续60日、成交额前100。信号UTC 00:00已闭合日线产生，04:00执行；全卖再买，包括留榜币也扣成本。

只有一个对照：不判断牛市，每30日直接轮动Top10。空仓等待使两者后续日期不完全相同，不能把全部差异都称为同日市场过滤的因果收益。[事前契约](../specs/p0-contract.md) · [配置](../specs/p0-config.json)。

## 30日完整轮次的结果

以下每一轮独立等权计算，从实际04:00开盘到30天后04:00开盘；均扣每边0.1%手续费与4bps滑点，**未扣资金费率**。它们是轮次样本平均，不是完整账户复利收益。

{table(s4, ["name", "complete", "holding_gap", "right_censor", "mean_pct", "median_pct", "win_pct"], ["规则", "完整轮次", "缺价轮次", "未到期", "平均收益%", "中位数%", "盈利轮次%"])}

主规则共35轮，其中33轮完整、1轮因BNX无完整退出而无效、最后1轮尚未满30日；对照共74轮，其中72轮完整、1轮BNX事件无效、1轮未到期。没有把无效轮次改成零或在选币前剔除BNX。

主规则的均值高于中位数，收益仍偏向少数大上涨。剔除2021后的完整轮次均值为{bull.mean_excluding_2021_pct:+.2f}%，仅用于集中度诊断。8bps压力下主规则完整轮次均值为{stats[(stats.variant.eq("bull_top10")) & stats.bps.eq(8)].mean_pct.iloc[0]:+.2f}%。

事后缺失敏感性：即使将那1个缺价轮次的**整个组合**算成−100%，主规则所有已到期轮次的算术平均仍至少{bull.whole_bad_round_minus100_mean_lower_pct:+.2f}%，对照为{plain.whole_bad_round_minus100_mean_lower_pct:+.2f}%。这是无杠杆价格预算的算术下界，不是补造交易，也不能生成账户净值；真实funding尚不在此边界内。

## 分年看，仍有亏损年份

{table(joined, ["year", "count_bull", "mean_pct_bull", "count_all", "mean_pct_all"], ["入场年份", "牛市组完整轮数", "牛市组平均%", "对照完整轮数", "对照平均%"])}

2026牛市组只有2个完整轮次，不能凭较高均值认定稳定；2025仍为负。逐年数字为按入场年分组的30日样本均值，不是自然年账户收益。[逐轮记录](../artifacts/p0-20260907/round-labels.csv) · [每轮持币明细](../artifacts/p0-20260907/decisions.json) · [最近1d/7d/1m/3m/6m/1y入场批次](../artifacts/p0-20260907/recent-round-cohorts.csv)。未到期批次没有完整收益。

## 为什么暂时不给完整总收益

牛市组在2023-02-11 04:00UTC遇到BNX原合约终止，恰好是该轮预定退出时刻；对照则在2025-03-17的BNX终止事件中断。价格文件随后出现零成交占位，不能当作真实卖出价格继续复利。

Binance公告确认旧BNX永续于2023-02-11 04:00自动结算并下架；另一公告确认2025-03-17 09:00自动结算。4H数据对第二个事件到12:00才显式变成无效占位，说明4H桶边界也不能代替精确合约事件时间。[2023官方公告](https://www.binance.com/en/support/announcement/detail/4d23ada51a2e4fa182835c77d51ba1a9) · [2025官方公告](https://www.binance.com/en/square/post/20809735768641)。公告验证了事件，尚未验证实际结算价，因此没有拼接BNX新旧资产或提前预知平仓。

两条账户路径均已标INVALID，**不发布2020—2026总收益、年化或Sharpe**。主规则在首个断点之前的价格预算曾有约−56.40%的4H收盘最大回撤：即使加牛市过滤，固定持有30日仍可能经历很深的回撤。该回撤仅覆盖2020-08-09至2023-02-11的有效前缀，不代表全窗最大回撤。原始前缀值保留在[路径汇总](../artifacts/p0-20260907/summary.json)供验算，不当作跨不同终点的策略排名。

断点之后的轮次来自只依赖已知市场状态的预定日历，分别从单位预算计算，用于研究价格延续；没有将这些轮次接回已中断的资金账户。[断点价格](../artifacts/p0-20260907/bnx-discontinuities.csv)。

## 数据、验证与结论

独立通过组合v2日线与4H启动，实际消费652个观测币的返回数据；日线598035行、4H3592113行，最后完整收盘分别为2026-09-05 00:00和12:00UTC。LIT不拼旧资产，PONS身份未确认而未纳入。观测库存仍不是完整历史PIT；funding、订单容量和完整上市/下架结算账没有通过。

9项策略定向测试与输入组合测试通过；逐笔独立检查{checked}条持仓记录和{labels}个完整轮次标签，原4H研究{len(parent)}份保护文件未改变。[验算](../artifacts/p0-20260907/acceptance.json) · [测试和消费者扫描](../artifacts/p0-20260907/validation.json)。工程通过不代表策略通过，2025+仍是已观察历史，没有新样本外验证。

结论：这条简单规则在完整轮次上呈现了更清楚的历史收益信号，可以作为后续验证的基线；当前阻塞的是完整账户结算链与交易验证，不能把它解释为已经稳定盈利，也不能因此否定这条简化假设。下一步应核验BNX等终止合约的实际结算价值，再完整重放同一套规则；不增加指标或搜索参数。本次状态为`explore / diagnostic-only / not promoted / not live-ready`，完整账户证据为`DATA_OR_REPRODUCTION_FAILURE`。

复现入口：[输入构建](../scripts/build_p0_inputs.py) → [两规则回放](../scripts/replay_p0.py) → [独立汇总](../scripts/package_p0.py)。启动拒绝覆盖已有输入；完整重建需保留原证据，在独立工作区执行。数据湖未修改。
"""
    target = FAMILY / "diagnostics/p0-results-2026-09-07.md"
    target.write_text(report)
    (OUT / "provenance/package_p0.py.txt").write_bytes(Path(__file__).read_bytes())
    dump(
        OUT / "delivery-manifest.json",
        {
            "report_sha256": sha(target),
            "artifacts": {
                str(p.relative_to(OUT)): sha(p)
                for p in OUT.rglob("*")
                if p.is_file() and p.name != "delivery-manifest.json"
            },
        },
    )
    print(stats.to_string(index=False), flush=True)
    print(json.dumps(audit, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
