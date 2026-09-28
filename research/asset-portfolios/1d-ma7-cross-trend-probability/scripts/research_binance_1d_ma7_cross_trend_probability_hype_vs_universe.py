"""BIN-1D-MA7-CTP：用已冻结的全市场事件表，把 HYPE 和其它币比较。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
FOUR_ASSET_SCRIPT = (
    FAMILY_DIR / "scripts/research_binance_1d_ma7_cross_trend_probability.py"
)
RUN_DATE = "2026-08-31"
EVENTS_PATH = (
    FAMILY_DIR / "artifacts" / f"binance_1d_ma7_ctp_all_market_events_{RUN_DATE}.parquet"
)
QUALITY_PATH = (
    FAMILY_DIR / "artifacts" / f"binance_1d_ma7_ctp_all_market_quality_{RUN_DATE}.json"
)
SYMBOL_RATES_PATH = (
    FAMILY_DIR
    / "artifacts"
    / f"binance_1d_ma7_ctp_all_market_symbol_rates_{RUN_DATE}.csv"
)
OUTPUT_JSON = (
    FAMILY_DIR
    / "artifacts"
    / f"binance_1d_ma7_ctp_hype_vs_universe_{RUN_DATE}.json"
)
OUTPUT_REPORT = (
    FAMILY_DIR
    / "diagnostics"
    / f"binance-1d-ma7-cross-trend-probability-hype-vs-universe-{RUN_DATE}.md"
)
PANEL_END = pd.Timestamp("2026-06-30T00:00:00Z")
LISTING_WINDOW_DAYS = 90
SIMILAR_N = (50, 150)
COMPARE_SYMBOLS = ("HYPE", "BTC", "ETH", "BNB", "SOL")


def load_four_asset_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "binance_1d_ma7_ctp_four_asset", FOUR_ASSET_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {FOUR_ASSET_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare HYPE MA7-cross trend rates with the frozen all-market events."
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def rate_pack(ctp: Any, frame: pd.DataFrame) -> dict[str, Any]:
    packs: dict[str, Any] = {"events": int(len(frame))}
    for side in ("both", "long", "short"):
        subset = frame if side == "both" else frame.loc[frame["side"].eq(side)]
        rate = ctp.make_rate(subset["trend_20"])
        packs[side] = {
            "n": rate.n,
            "k": rate.k,
            "p": rate.p,
            "lo": rate.lo,
            "hi": rate.hi,
            "txt": ctp.fmt_rate(rate),
        }
    return packs


def percentile_below(values: pd.Series, target: float) -> float:
    finite = values.dropna()
    if finite.empty or not pd.notna(target):
        return float("nan")
    return float((finite < target).mean())


def binomial_greater(k: int, n: int, p0: float) -> float:
    if n <= 0 or not (0.0 < p0 < 1.0):
        return float("nan")
    from scipy.stats import binomtest

    return float(binomtest(k, n, p0, alternative="greater").pvalue)


def self_test(ctp: Any) -> None:
    dummy = pd.DataFrame(
        {
            "side": ["long", "long", "short"],
            "trend_20": [1.0, 0.0, 1.0],
        }
    )
    pack = rate_pack(ctp, dummy)
    if pack["both"]["n"] != 3 or pack["both"]["k"] != 2:
        raise RuntimeError("self-test rate pack mismatch")
    if abs(percentile_below(pd.Series([0.2, 0.3, 0.4]), 0.35) - 2 / 3) > 1e-12:
        raise RuntimeError("self-test percentile mismatch")


def write_report(summary: dict[str, Any], ctp: Any) -> None:
    hype = summary["hype"]
    market = summary["market_full"]
    window = summary["same_window"]
    cohort = summary["listing_cohort"]
    similar = summary["similar_n"]
    lines = [
        "# BIN-1D-MA7-CTP：HYPE 穿越 MA7 后是否更容易走出趋势",
        "",
        f"> SCOUT 对照，{RUN_DATE}。状态：`explore / diagnostic-only / not promoted / not live-ready`。",
        "> 事件和标签沿用全市场冻结口径；只读已落盘的全市场事件表，不搜新阈值，不另立家族。",
        "",
        "## 大白话结论",
        "",
        summary["headline"],
        "",
        "## 口径",
        "",
        "- 事件/标签与 [冻结口径](../specs/binance-1d-ma7-cross-trend-probability-contract-2026-08-31.md) 相同。",
        "- 数据：全市场缓存完整日，面板到 `2026-06-30`。HYPE 只在 overlay 日K 里，不在 Vision 月档；入选 396 个完整日，跨度内不缺日。",
        f"- 同日历窗口：从 HYPE 第一个完整日 `{summary['hype_start'][:10]}` 到面板终点，避免拿六年 BTC 历史去比十三个月的 HYPE。",
        f"- 上市队列：第一个完整日落在 HYPE 前后 {LISTING_WINDOW_DAYS} 日的入选合约。",
        "- 最近一年几乎覆盖 HYPE 全部可标签样本，只作审计。",
        "",
        "## HYPE 本身",
        "",
        f"- 完整日 {hype['complete_days']}，事件 {hype['events']} 笔，可标签 `trend_20` {hype['both']['txt']}。",
        f"- 多头 {hype['long']['txt']}；空头 {hype['short']['txt']}。",
        f"- 辅标签：`mfe2_20` {hype['aux']['mfe2_20']}，`win_20` {hype['aux']['win_20']}，`persist_5` {hype['aux']['persist_5']}。",
        "",
        "| 过滤 | HYPE |",
        "| --- | --- |",
    ]
    for row in summary["hype_filters"]:
        lines.append(f"| {row['filter_zh']} | {row['txt']} |")
    lines.extend(
        [
            "",
            "## 和其它币比",
            "",
            "| 对照 | 合计 | 多头 | 空头 |",
            "| --- | --- | --- | --- |",
            f"| HYPE | {hype['both']['txt']} | {hype['long']['txt']} | {hype['short']['txt']} |",
            (
                f"| 全市场事件加权 | {market['both']['txt']} | "
                f"{market['long']['txt']} | {market['short']['txt']} |"
            ),
            (
                f"| 同窗口事件加权（其它币） | {window['others']['both']['txt']} | "
                f"{window['others']['long']['txt']} | {window['others']['short']['txt']} |"
            ),
            (
                f"| 上市±{LISTING_WINDOW_DAYS}日队列事件加权 | {cohort['pooled']['both']['txt']} | "
                f"{cohort['pooled']['long']['txt']} | {cohort['pooled']['short']['txt']} |"
            ),
            "",
        ]
    )
    lines.extend(
        [
            "同窗口里的大币（样本都不大）：",
            "",
            "| 资产 | 合计 | 多头 | 空头 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for symbol in COMPARE_SYMBOLS:
        row = window["per_symbol"][symbol]
        lines.append(
            f"| {symbol} | {row['both']['txt']} | {row['long']['txt']} | {row['short']['txt']} |"
        )
    lines.extend(
        [
            "",
            "分位数（`trend_20` 样本 ≥ 20 的合约）：",
            "",
            (
                f"- 全历史：HYPE 合计 {ctp.fmt_pct(hype['both']['p'])}，"
                f"高于 {ctp.fmt_pct(summary['ranks']['full_below'])} 的合约"
                f"（{summary['ranks']['full_n']} 个里有 {summary['ranks']['full_ge']} 个 ≥ HYPE）。"
            ),
            (
                f"- 同窗口：HYPE 高于 {ctp.fmt_pct(summary['ranks']['window_below'])} 的合约"
                f"（{summary['ranks']['window_n']} 个里有 {summary['ranks']['window_ge']} 个 ≥ HYPE）。"
            ),
            (
                f"- 上市队列等权平均 {ctp.fmt_pct(cohort['equal_weight'])}；"
                f"相近事件数（{SIMILAR_N[0]}–{SIMILAR_N[1]} 笔）等权平均 {ctp.fmt_pct(similar['equal_weight'])}。"
            ),
            (
                f"- 相对全市场合计的单侧二项 `P(K≥{hype['both']['k']} | n={hype['both']['n']}, p={market['both']['p']:.3f})` "
                f"= {summary['tests']['full_greater']:.3f}。"
            ),
            (
                f"- 相对同窗口其它币合计：单侧 {summary['tests']['window_greater']:.3f}，"
                f"双侧 {summary['tests']['window_two_sided']:.3f}。"
            ),
            (
                f"- 多头相对同窗口其它多头：单侧 {summary['tests']['window_long_greater']:.3f}，"
                f"双侧 {summary['tests']['window_long_two_sided']:.3f}。这是事后拆方向，不是预注册。"
            ),
            "",
            "## 裁决",
            "",
            summary["verdict_block"],
            "",
            "## 文件",
            "",
            f"- [对照摘要](../artifacts/binance_1d_ma7_ctp_hype_vs_universe_{RUN_DATE}.json)",
            f"- [全市场事件表](../artifacts/binance_1d_ma7_ctp_all_market_events_{RUN_DATE}.parquet)",
            f"- [分币裸穿越](../artifacts/binance_1d_ma7_ctp_all_market_symbol_rates_{RUN_DATE}.csv)",
            f"- [全市场诊断](binance-1d-ma7-cross-trend-probability-all-market-{RUN_DATE}.md)",
            "- [本脚本](../scripts/research_binance_1d_ma7_cross_trend_probability_hype_vs_universe.py)",
            "",
        ]
    )
    OUTPUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    ctp = load_four_asset_module()
    if args.self_test:
        self_test(ctp)
        print("self-test passed")
        return
    if not EVENTS_PATH.exists():
        raise FileNotFoundError(EVENTS_PATH)

    events = pd.read_parquet(EVENTS_PATH)
    events["ts"] = pd.to_datetime(events["ts"], utc=True)
    quality = pd.DataFrame(json.loads(QUALITY_PATH.read_text(encoding="utf-8"))["symbols"])
    symbol_rates = pd.read_csv(SYMBOL_RATES_PATH)
    hype_quality = quality.loc[quality["symbol"].eq("HYPE")]
    if hype_quality.empty:
        raise RuntimeError("HYPE missing from all-market quality file")
    hype_quality = hype_quality.iloc[0]
    hype_start = pd.Timestamp(hype_quality["start"])
    hype = events.loc[events["symbol"].eq("HYPE")].copy()
    if hype.empty:
        raise RuntimeError("HYPE missing from all-market events")

    hype_pack = rate_pack(ctp, hype)
    hype_pack["complete_days"] = int(hype_quality["complete_days"])
    hype_pack["aux"] = {
        column: ctp.fmt_rate(ctp.make_rate(hype[column]))
        for column in ("mfe2_20", "win_20", "persist_5", "recross_ge_5")
    }
    hype_filters = []
    for filt in (
        "cross",
        "slope_sign",
        "slope_002",
        "vol_1p5",
        "slope_002+vol_1p5",
        "path_ratio30_reclaim_or_fade",
    ):
        masked = hype.loc[ctp.filter_mask(hype, filt)]
        hype_filters.append(
            {
                "filter": filt,
                "filter_zh": ctp.FILTER_ZH[filt],
                "txt": ctp.fmt_rate(ctp.make_rate(masked["trend_20"])),
                "events": int(len(masked)),
            }
        )

    market = rate_pack(ctp, events)
    window = events.loc[events["ts"].ge(hype_start)].copy()
    others = window.loc[window["symbol"].ne("HYPE")]
    window_pack = {
        "all": rate_pack(ctp, window),
        "others": rate_pack(ctp, others),
        "per_symbol": {
            symbol: rate_pack(ctp, window.loc[window["symbol"].eq(symbol)])
            for symbol in COMPARE_SYMBOLS
        },
    }

    quality["start_ts"] = pd.to_datetime(quality["start"], utc=True)
    cohort_symbols = quality.loc[
        quality["eligible"]
        & quality["start_ts"].between(
            hype_start - pd.Timedelta(days=LISTING_WINDOW_DAYS),
            hype_start + pd.Timedelta(days=LISTING_WINDOW_DAYS),
        ),
        "symbol",
    ].tolist()
    cohort_events = events.loc[events["symbol"].isin(cohort_symbols)]
    cohort_symbol_p = []
    for symbol in cohort_symbols:
        rate = ctp.make_rate(events.loc[events["symbol"].eq(symbol), "trend_20"])
        cohort_symbol_p.append(rate.p if rate.n >= ctp.MIN_N_HIGHLIGHT else float("nan"))
    cohort_p = pd.Series(cohort_symbol_p, dtype=float)

    eligible = symbol_rates.loc[symbol_rates["trend_20_both_n"].ge(ctp.MIN_N_HIGHLIGHT)]
    similar = eligible.loc[
        eligible["trend_20_both_n"].between(SIMILAR_N[0], SIMILAR_N[1])
    ]
    window_rows = []
    for symbol, group in window.groupby("symbol"):
        rate = ctp.make_rate(group["trend_20"])
        window_rows.append({"symbol": symbol, "n": rate.n, "p": rate.p})
    window_ok = pd.DataFrame(window_rows)
    window_ok = window_ok.loc[window_ok["n"].ge(ctp.MIN_N_HIGHLIGHT)]

    hype_p = float(hype_pack["both"]["p"])
    ranks = {
        "full_n": int(len(eligible)),
        "full_below": percentile_below(eligible["trend_20_both_p"], hype_p),
        "full_ge": int(eligible["trend_20_both_p"].ge(hype_p).sum()),
        "window_n": int(len(window_ok)),
        "window_below": percentile_below(window_ok["p"], hype_p),
        "window_ge": int(window_ok["p"].ge(hype_p).sum()),
        "cohort_n": int(cohort_p.notna().sum()),
        "cohort_below": percentile_below(cohort_p, hype_p),
        "similar_n": int(len(similar)),
        "similar_below": percentile_below(similar["trend_20_both_p"], hype_p),
        "long_n": int(symbol_rates["trend_20_long_n"].ge(ctp.MIN_N_HIGHLIGHT).sum()),
        "long_below": percentile_below(
            symbol_rates.loc[
                symbol_rates["trend_20_long_n"].ge(ctp.MIN_N_HIGHLIGHT),
                "trend_20_long_p",
            ],
            float(hype_pack["long"]["p"]),
        ),
        "short_below": percentile_below(
            symbol_rates.loc[
                symbol_rates["trend_20_short_n"].ge(ctp.MIN_N_HIGHLIGHT),
                "trend_20_short_p",
            ],
            float(hype_pack["short"]["p"]),
        ),
    }
    from scipy.stats import binomtest

    tests = {
        "full_greater": binomial_greater(
            hype_pack["both"]["k"], hype_pack["both"]["n"], market["both"]["p"]
        ),
        "window_greater": binomial_greater(
            hype_pack["both"]["k"],
            hype_pack["both"]["n"],
            window_pack["others"]["both"]["p"],
        ),
        "window_two_sided": float(
            binomtest(
                hype_pack["both"]["k"],
                hype_pack["both"]["n"],
                window_pack["others"]["both"]["p"],
                alternative="two-sided",
            ).pvalue
        ),
        "window_long_greater": binomial_greater(
            hype_pack["long"]["k"],
            hype_pack["long"]["n"],
            window_pack["others"]["long"]["p"],
        ),
        "window_long_two_sided": float(
            binomtest(
                hype_pack["long"]["k"],
                hype_pack["long"]["n"],
                window_pack["others"]["long"]["p"],
                alternative="two-sided",
            ).pvalue
        ),
    }
    start_1y = PANEL_END - pd.Timedelta(days=ctp.RECENT_DAYS)
    year_hype = rate_pack(ctp, hype.loc[hype["ts"].ge(start_1y)])
    year_all = rate_pack(ctp, events.loc[events["ts"].ge(start_1y)])

    headline = (
        f"HYPE 点估计确实高一些：裸穿越后 `trend_20` 为 **{ctp.fmt_pct(hype_p)}**"
        f"（{hype_pack['both']['k']}/{hype_pack['both']['n']}），"
        f"全市场是 {ctp.fmt_pct(market['both']['p'])}，同窗口其它币是 "
        f"{ctp.fmt_pct(window_pack['others']['both']['p'])}。"
        f"但它只排在全历史样本够的合约大约 {ctp.fmt_pct(ranks['full_below'])} 分位，"
        f"Wilson 区间 {hype_pack['both']['txt']} 盖住了全市场中枢，"
        f"同窗口单侧二项 p={tests['window_greater']:.2f}。"
        f"多头 {ctp.fmt_pct(hype_pack['long']['p'])} 看起来更偏高，空头 "
        f"{ctp.fmt_pct(hype_pack['short']['p'])} 并不突出。"
        "还不能说 HYPE 穿越后天生比别的币更容易走出趋势。"
    )
    verdict = (
        "Verdict: **ITERATE / 点估计偏高，统计上分不出来**。\n\n"
        f"- Why：HYPE `{hype_pack['both']['txt']}`，比全市场高约 "
        f"{100.0 * (hype_p - market['both']['p']):.1f}pp，但 n={hype_pack['both']['n']}，"
        f"区间与全市场 {market['both']['txt']} 重叠。\n"
        f"- 同窗口其它币 {window_pack['others']['both']['txt']}；"
        f"上市±{LISTING_WINDOW_DAYS}日队列 {rate_pack(ctp, cohort_events)['both']['txt']}。"
        "HYPE 不是这个时期的唯一高点，只是偏右尾。\n"
        f"- 多头相对同窗口多头单侧 p={tests['window_long_greater']:.3f}，"
        "但这是事后拆方向，且只有 43 个可标签多头，不能升级成 HYPE 多头规则。\n"
        "- Confidence: **LOW–MEDIUM**。HYPE 历史短、事件少，过滤器格子 `n<20`。\n"
        "- Warning：不要把 `HYPE-1D-MA7-MLT` P8 的 first-hit 成功率拿来互相继承；标签、窗口和成本口径不同。\n"
        "- Next：若还想问 HYPE 是否特殊，应预注册多头-only 假设，并用未揭示的 HYPE 后期样本确认；不要在全市场分币排行上继续挑冠军。"
    )
    summary = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "run_date": RUN_DATE,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "explore / diagnostic-only / not promoted / not live-ready",
        "hype_start": hype_start.isoformat(),
        "headline": headline,
        "verdict_block": verdict,
        "hype": hype_pack,
        "hype_filters": hype_filters,
        "market_full": market,
        "same_window": window_pack,
        "listing_cohort": {
            "symbols": int(len(cohort_symbols)),
            "pooled": rate_pack(ctp, cohort_events),
            "equal_weight": float(cohort_p.mean()),
        },
        "similar_n": {
            "n_symbols": int(len(similar)),
            "equal_weight": float(similar["trend_20_both_p"].mean()),
        },
        "ranks": ranks,
        "tests": tests,
        "year": {"hype": year_hype, "all": year_all},
        "outputs": {
            "json": str(OUTPUT_JSON.relative_to(ROOT)),
            "report": str(OUTPUT_REPORT.relative_to(ROOT)),
        },
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_report(summary, ctp)
    print(
        json.dumps(
            {
                "hype": hype_pack["both"]["txt"],
                "market": market["both"]["txt"],
                "report": str(OUTPUT_REPORT),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
