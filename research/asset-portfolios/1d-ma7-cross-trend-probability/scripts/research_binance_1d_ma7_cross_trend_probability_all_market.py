"""BIN-1D-MA7-CTP 全市场宇宙：同一冻结事件口径，数据改为 15m 聚合日K缓存。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
FOUR_ASSET_SCRIPT = (
    FAMILY_DIR / "scripts/research_binance_1d_ma7_cross_trend_probability.py"
)
CACHE_DIR = ROOT / "data/cache/binance_perp_1d_from_15m"
OHLCV_CACHE = CACHE_DIR / "ohlcv_1d"
OHLCV_OVERLAY = OHLCV_CACHE / "overlay_date_partitions.parquet"
CACHE_MARKER = CACHE_DIR / "_build_complete.json"
RUN_DATE = "2026-08-31"
PANEL_START = pd.Timestamp("2020-01-01T00:00:00Z")
PANEL_END = pd.Timestamp("2026-06-30T00:00:00Z")
MIN_COMPLETE_DAYS = 120
BARS_PER_DAY = 96
MAJOR_SYMBOLS = ("BTC", "ETH", "BNB", "SOL")

STABLE_BASES = {
    "USDC",
    "BUSD",
    "TUSD",
    "USDP",
    "FDUSD",
    "DAI",
    "SUSD",
    "EUR",
    "AEUR",
    "GBP",
    "AUD",
    "BRL",
    "USD1",
    "USDE",
    "XUSD",
    "BFUSD",
}
INDEX_BASES = {"BLUEBIRD", "DOTECO", "FOOTBALL"}
US_STOCK_LIKE_BASES = {
    "AAPL",
    "AMZN",
    "COIN",
    "CRCL",
    "GOOGL",
    "HOOD",
    "META",
    "MSFT",
    "MSTR",
    "NVDA",
    "PLTR",
    "TSLA",
}
EXCLUDED_BASES = STABLE_BASES | INDEX_BASES | US_STOCK_LIKE_BASES

OUTPUTS = {
    "events": FAMILY_DIR
    / "artifacts"
    / f"binance_1d_ma7_ctp_all_market_events_{RUN_DATE}.parquet",
    "rates": FAMILY_DIR
    / "artifacts"
    / f"binance_1d_ma7_ctp_all_market_rates_{RUN_DATE}.csv",
    "path_rates": FAMILY_DIR
    / "artifacts"
    / f"binance_1d_ma7_ctp_all_market_path_rates_{RUN_DATE}.csv",
    "symbols": FAMILY_DIR
    / "artifacts"
    / f"binance_1d_ma7_ctp_all_market_symbol_rates_{RUN_DATE}.csv",
    "quality": FAMILY_DIR
    / "artifacts"
    / f"binance_1d_ma7_ctp_all_market_quality_{RUN_DATE}.json",
    "summary": FAMILY_DIR
    / "artifacts"
    / f"binance_1d_ma7_ctp_all_market_summary_{RUN_DATE}.json",
    "report": FAMILY_DIR
    / "diagnostics"
    / f"binance-1d-ma7-cross-trend-probability-all-market-{RUN_DATE}.md",
}


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
        description="All-market MA7 cross trend-probability scout."
    )
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--limit-symbols",
        type=int,
        default=0,
        help="If >0, only process the first N symbols after sort (smoke).",
    )
    parser.add_argument(
        "--only-symbols",
        default="",
        help="Comma-separated sym_key list, e.g. BTC,ETH,BNB,SOL.",
    )
    return parser.parse_args()


def load_cache_panel() -> pd.DataFrame:
    if not CACHE_MARKER.exists():
        raise FileNotFoundError(CACHE_MARKER)
    if not OHLCV_OVERLAY.exists():
        raise FileNotFoundError(OHLCV_OVERLAY)
    con = duckdb.connect()
    frame = con.execute(
        f"""
        SELECT * EXCLUDE (prio) FROM (
            SELECT *, 0 AS prio
            FROM read_parquet('{OHLCV_CACHE}/month=*.parquet')
            UNION ALL BY NAME
            SELECT *, 1 AS prio
            FROM read_parquet('{OHLCV_OVERLAY}')
        )
        QUALIFY row_number() OVER (PARTITION BY sym_key, day ORDER BY prio) = 1
        ORDER BY sym_key, day
        """
    ).fetch_df()
    con.close()
    frame["day"] = pd.to_datetime(frame["day"], utc=True)
    if frame["day"].dt.tz is None:
        frame["day"] = frame["day"].dt.tz_localize("UTC")
    frame = frame.loc[frame["day"].ge(PANEL_START) & frame["day"].le(PANEL_END)].copy()
    dup = int(frame.duplicated(["sym_key", "day"]).sum())
    if dup:
        raise RuntimeError(f"duplicate all-market daily keys: {dup}")
    return frame.reset_index(drop=True)


def complete_symbol_frame(group: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    complete = group.loc[
        group["bars_15m"].eq(BARS_PER_DAY) & group["all_closed"].fillna(False)
    ].copy()
    complete = complete.sort_values("day").drop_duplicates("day").reset_index(drop=True)
    if complete.empty:
        quality = {
            "symbol": str(group["sym_key"].iloc[0]),
            "base_asset": str(group["base_asset"].iloc[0]),
            "complete_days": 0,
            "raw_days": int(len(group)),
            "missing_inside_span": 0,
            "start": None,
            "end": None,
            "eligible": False,
            "skip_reason": "no_complete_days",
        }
        return complete, quality
    first = complete["day"].min()
    last = complete["day"].max()
    expected = int((last - first).days) + 1
    missing = expected - int(len(complete))
    symbol = str(complete["sym_key"].iloc[0])
    base = str(complete["base_asset"].iloc[0])
    skip = None
    if base in EXCLUDED_BASES:
        skip = "excluded_base"
    elif len(complete) < MIN_COMPLETE_DAYS:
        skip = "short_history"
    quality = {
        "symbol": symbol,
        "base_asset": base,
        "complete_days": int(len(complete)),
        "raw_days": int(len(group)),
        "missing_inside_span": int(missing),
        "start": first.isoformat(),
        "end": last.isoformat(),
        "eligible": skip is None,
        "skip_reason": skip,
    }
    daily = pd.DataFrame(
        {
            "ts": complete["day"],
            "open": complete["open"].astype(float),
            "high": complete["high"].astype(float),
            "low": complete["low"].astype(float),
            "close": complete["close"].astype(float),
            "quote_volume": complete["quote_volume"].astype(float),
            "is_closed": True,
        }
    )
    return daily, quality


def symbol_rate_rows(events: pd.DataFrame, ctp: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol, group in events.groupby("symbol", sort=True):
        both = ctp.make_rate(group["trend_20"])
        long = ctp.make_rate(group.loc[group["side"].eq("long"), "trend_20"])
        short = ctp.make_rate(group.loc[group["side"].eq("short"), "trend_20"])
        rows.append(
            {
                "symbol": symbol,
                "events": int(len(group)),
                "trend_20_both_txt": ctp.fmt_rate(both),
                "trend_20_both_n": both.n,
                "trend_20_both_k": both.k,
                "trend_20_both_p": both.p,
                "trend_20_long_txt": ctp.fmt_rate(long),
                "trend_20_long_n": long.n,
                "trend_20_long_k": long.k,
                "trend_20_long_p": long.p,
                "trend_20_short_txt": ctp.fmt_rate(short),
                "trend_20_short_n": short.n,
                "trend_20_short_k": short.k,
                "trend_20_short_p": short.p,
            }
        )
    return rows


def equal_weight(symbol_rates: pd.DataFrame, column: str, min_n: int) -> float:
    eligible = symbol_rates.loc[symbol_rates["trend_20_both_n"].ge(min_n), column]
    values = eligible.to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    return float(np.mean(values)) if len(values) else float("nan")


def write_report(
    *,
    ctp: Any,
    qualities: list[dict[str, Any]],
    rates: pd.DataFrame,
    path_rates: pd.DataFrame,
    symbol_rates: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    eligible = [row for row in qualities if row["eligible"]]
    full_both = ctp.pick_rate(rates, "full", "ALL", "both", "cross")
    full_long = ctp.pick_rate(rates, "full", "ALL", "long", "cross")
    full_short = ctp.pick_rate(rates, "full", "ALL", "short", "cross")
    year_both = ctp.pick_rate(rates, "1y", "ALL", "both", "cross")
    lines = [
        "# BIN-1D-MA7-CTP：全市场日K穿越 MA7 后趋势发生率",
        "",
        f"> SCOUT 宇宙扩展，{RUN_DATE}。状态：`explore / diagnostic-only / not promoted / not live-ready`。",
        "> 事件、斜率、放量、路径分桶与四币报告相同；数据改为 `data/cache/binance_perp_1d_from_15m` 的完整 UTC 日K。",
        "> 不是策略，不扣成本，不登记版本。",
        "",
        "## 大白话结论",
        "",
        summary["headline"],
        "",
        "## 冻结口径",
        "",
        "- 事件/标签/过滤器与 [四币合同](../specs/binance-1d-ma7-cross-trend-probability-contract-2026-08-31.md) 相同。",
        "- 数据：Binance USD-M 永续、Vision 月档 `15m` 聚合成 UTC 日K；月档优先，overlay 只补月档没有的日子。",
        f"- 面板：`{PANEL_START.date()}` 至 `{PANEL_END.date()}`。6 月底切断，避免 7 月以后只剩少数大币、把全市场样本悄悄缩小。",
        f"- 只用 `bars_15m=96` 且 `all_closed=true` 的完整日；每个合约至少 `{MIN_COMPLETE_DAYS}` 个完整日。",
        "- 剔除稳定币、指数合约和美股代币化标的，口径与 MCSM/TPSA 一致。",
        "- 完整日按时间顺序当作 session 序列，与 TPSA 相同；不把不完整日插回日历。",
        "- 最近 365 日锚定面板终点，只作审计。",
        "",
        "## 数据质量",
        "",
        f"- 缓存构建标记：[`data/cache/binance_perp_1d_from_15m/_build_complete.json`](../../../../data/cache/binance_perp_1d_from_15m/_build_complete.json)",
        f"- 原始合约：{summary['universe']['raw_symbols']}；入选：{summary['universe']['eligible_symbols']}；剔除：{summary['universe']['skipped_symbols']}",
        f"- 完整日合计：{summary['universe']['eligible_complete_days']:,}；入选合约跨度内缺完整日：{summary['universe']['eligible_missing_inside_span']:,}",
        (
            f"- 剔除原因：稳定币/指数/美股代币 {summary['universe']['skipped_excluded_base']}，"
            f"历史不足 {summary['universe']['skipped_short_history']}，"
            f"无穿越 {summary['universe']['skipped_no_crosses']}"
        ),
        "",
        "| 对照币 | 完整日 | 起 | 止 | 跨度内缺日 |",
        "| --- | ---: | --- | --- | ---: |",
    ]
    quality_map = {row["symbol"]: row for row in eligible}
    for symbol in MAJOR_SYMBOLS:
        row = quality_map.get(symbol)
        if row is None:
            lines.append(f"| {symbol} | n/a | n/a | n/a | n/a |")
        else:
            lines.append(
                f"| {symbol} | {row['complete_days']} | {row['start'][:10]} | {row['end'][:10]} | {row['missing_inside_span']} |"
            )
    lines.extend(
        [
            "",
            "四币上一轮用的是 API 直连小时K 聚合，终点到 2026-08-09。本轮全市场缓存终点是 2026-06-30，所以大币数字只作对照，不能逐笔对账。",
            "",
            "## 1. 裸穿越后发生趋势的几率",
            "",
            "事件加权（每个穿越一次）：",
            "",
        ]
    )
    lines.extend(
        ctp.markdown_filter_table(
            rates, "full", ["ALL", *MAJOR_SYMBOLS], "cross"
        )
    )
    ew_both = equal_weight(symbol_rates, "trend_20_both_p", ctp.MIN_N_HIGHLIGHT)
    long_eligible = symbol_rates.loc[
        symbol_rates["trend_20_long_n"].ge(ctp.MIN_N_HIGHLIGHT), "trend_20_long_p"
    ]
    short_eligible = symbol_rates.loc[
        symbol_rates["trend_20_short_n"].ge(ctp.MIN_N_HIGHLIGHT), "trend_20_short_p"
    ]
    ew_long = float(long_eligible.mean()) if len(long_eligible) else float("nan")
    ew_short = float(short_eligible.mean()) if len(short_eligible) else float("nan")
    n_ew = int(symbol_rates["trend_20_both_n"].ge(ctp.MIN_N_HIGHLIGHT).sum())
    both_p = symbol_rates.loc[
        symbol_rates["trend_20_both_n"].ge(ctp.MIN_N_HIGHLIGHT), "trend_20_both_p"
    ]
    lines.extend(
        [
            "",
            (
                f"事件加权全市场合计 `{full_both['trend_20_txt']}`；"
                f"多头 `{full_long['trend_20_txt']}`，空头 `{full_short['trend_20_txt']}`。"
            ),
            (
                f"合约等权（`trend_20` 样本 ≥ {ctp.MIN_N_HIGHLIGHT} 的 {n_ew} 个币）"
                f"平均 {ctp.fmt_pct(ew_both)}；多头 {ctp.fmt_pct(ew_long)}，空头 {ctp.fmt_pct(ew_short)}。"
            ),
            (
                "分币分布（合计，n≥20）："
                f"P10 {ctp.fmt_pct(float(both_p.quantile(0.10)))}，"
                f"中位 {ctp.fmt_pct(float(both_p.median()))}，"
                f"P90 {ctp.fmt_pct(float(both_p.quantile(0.90)))}。"
            ),
            "",
            "同一批裸穿越的辅标签（全市场合计）：",
            "",
            "| 标签 | 含义 | 合计 |",
            "| --- | --- | --- |",
            f"| `trend_20` | 先到 +2ATR 且未先到 -1ATR | {full_both['trend_20_txt']} |",
            f"| `mfe2_20` | 20 日顺向走过 2ATR | {full_both['mfe2_20_txt']} |",
            f"| `win_20` | 第 20 日收盘仍顺向 | {full_both['win_20_txt']} |",
            f"| `persist_5` | 随后 5 日仍在 SMA7 同侧 | {full_both['persist_5_txt']} |",
            f"| `recross_ge_5` | 5 日内不再反向穿越 | {full_both['recross_ge_5_txt']} |",
            "",
            "## 2. 要求斜率、放量之后",
            "",
        ]
    )
    lines.extend(
        ctp.markdown_filter_table(
            rates, "full", ["ALL", *MAJOR_SYMBOLS], "slope_002"
        )
    )
    lines.extend(["", "成交额 ≥ 1.5×20 日中位：", ""])
    lines.extend(
        ctp.markdown_filter_table(rates, "full", ["ALL", *MAJOR_SYMBOLS], "vol_1p5")
    )
    lines.extend(["", "斜率 0.02 + 放量 1.5×：", ""])
    lines.extend(
        ctp.markdown_filter_table(
            rates, "full", ["ALL", *MAJOR_SYMBOLS], "slope_002+vol_1p5"
        )
    )
    lines.extend(
        [
            "",
            "全市场过滤栈：",
            "",
        ]
    )
    lines.extend(ctp.markdown_stack_table(rates, "full", "ALL"))
    lines.extend(
        [
            "",
            "## 3. 前置上涨/回撤比",
            "",
            "全市场、30 日比值、多头：",
            "",
        ]
    )
    lines.extend(ctp.markdown_path_table(path_rates, "full", "ALL", "long", 30, "ratio"))
    lines.extend(["", "空头：", ""])
    lines.extend(ctp.markdown_path_table(path_rates, "full", "ALL", "short", 30, "ratio"))
    lines.extend(["", "多空合计：", ""])
    lines.extend(ctp.markdown_path_table(path_rates, "full", "ALL", "both", 30, "ratio"))
    lines.extend(
        [
            "",
            "多头、按穿越前 30 日最大回撤：",
            "",
        ]
    )
    lines.extend(
        ctp.markdown_path_table(path_rates, "full", "ALL", "long", 30, "drawdown")
    )
    lines.extend(["", "空头、按穿越前 30 日最大上涨：", ""])
    lines.extend(ctp.markdown_path_table(path_rates, "full", "ALL", "short", 30, "runup"))
    lines.extend(["", "### 7 / 60 / 90 日比值（全市场合计）", ""])
    for window in (7, 60, 90):
        lines.append(f"#### {window} 日")
        lines.append("")
        lines.extend(
            ctp.markdown_path_table(path_rates, "full", "ALL", "both", window, "ratio")
        )
        lines.append("")
    lines.extend(
        [
            "## 4. 最近一年审计",
            "",
            "全市场裸穿越：",
            "",
        ]
    )
    lines.extend(
        ctp.markdown_filter_table(rates, "1y", ["ALL", *MAJOR_SYMBOLS], "cross")
    )
    lines.extend(["", "最近一年、斜率 0.02 + 放量 1.5×：", ""])
    lines.extend(
        ctp.markdown_filter_table(
            rates, "1y", ["ALL", *MAJOR_SYMBOLS], "slope_002+vol_1p5"
        )
    )
    lines.extend(
        [
            "",
            "## 与四币和 TPSA 的对照",
            "",
            "- 四币 API 日K：合计 30.8%，多头 34.4%，空头 27.2%。见 [四币诊断](binance-1d-ma7-cross-trend-probability-2026-08-31.md)。",
            "- TPSA-P1 全市场（另一套 15m 日K 面板，MA7 事件）：多头 27.90%，空头 31.04%。",
            f"- 本轮全市场缓存：合计 {full_both['trend_20_txt']}，最近一年 {year_both['trend_20_txt']}。",
            "- 四币是多头强于空头；全市场反过来，空头略强，与 TPSA 同向。缓存里的 BTC/ETH/BNB/SOL 对照仍是多头偏强，所以四币不是全市场的方向代表。",
            "- 斜率/放量/30 日 R 方向过滤仍然只是小幅挪动，不能把多数穿越变成高把握趋势。",
            "",
            "## 裁决",
            "",
            summary["verdict_block"],
            "",
            "## 文件",
            "",
            f"- [事件表](../artifacts/binance_1d_ma7_ctp_all_market_events_{RUN_DATE}.parquet)",
            f"- [过滤发生率](../artifacts/binance_1d_ma7_ctp_all_market_rates_{RUN_DATE}.csv)",
            f"- [路径分桶](../artifacts/binance_1d_ma7_ctp_all_market_path_rates_{RUN_DATE}.csv)",
            f"- [分币裸穿越](../artifacts/binance_1d_ma7_ctp_all_market_symbol_rates_{RUN_DATE}.csv)",
            f"- [质量摘要](../artifacts/binance_1d_ma7_ctp_all_market_quality_{RUN_DATE}.json)",
            f"- [汇总 JSON](../artifacts/binance_1d_ma7_ctp_all_market_summary_{RUN_DATE}.json)",
            "- [复现脚本](../scripts/research_binance_1d_ma7_cross_trend_probability_all_market.py)",
            "",
        ]
    )
    OUTPUTS["report"].parent.mkdir(parents=True, exist_ok=True)
    OUTPUTS["report"].write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    ctp = load_four_asset_module()
    if args.self_test:
        ctp.self_test()
        print("self-test passed")
        return

    panel = load_cache_panel()
    qualities: list[dict[str, Any]] = []
    event_frames: list[pd.DataFrame] = []
    groups = list(panel.groupby("sym_key", sort=True))
    if args.only_symbols.strip():
        wanted = {item.strip().upper() for item in args.only_symbols.split(",") if item.strip()}
        groups = [(symbol, group) for symbol, group in groups if str(symbol).upper() in wanted]
        missing = wanted - {str(symbol).upper() for symbol, _ in groups}
        if missing:
            raise RuntimeError(f"requested symbols missing from cache panel: {sorted(missing)}")
    if args.limit_symbols > 0:
        groups = groups[: args.limit_symbols]
    n_groups = len(groups)
    for idx, (symbol, group) in enumerate(groups, start=1):
        if idx == 1 or idx % 50 == 0 or idx == n_groups:
            print(f"processing {idx}/{n_groups} {symbol}", flush=True)
        daily, quality = complete_symbol_frame(group)
        qualities.append(quality)
        if not quality["eligible"] or daily.empty:
            continue
        events = ctp.build_events(str(symbol), ctp.add_indicators(daily))
        if events.empty:
            quality["eligible"] = False
            quality["skip_reason"] = "no_crosses"
            continue
        event_frames.append(events)

    if not event_frames:
        raise RuntimeError("all-market universe produced no MA7 crosses")
    all_events = pd.concat(event_frames, ignore_index=True)
    data_end = PANEL_END
    rate_symbols = ["ALL", *MAJOR_SYMBOLS]
    sliced = {
        "full": all_events,
        "1y": ctp.window_slice(all_events, "1y", data_end),
    }
    rate_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    for sample, frame in sliced.items():
        rate_rows.extend(ctp.rate_table(frame, sample, rate_symbols))
        path_rows.extend(ctp.path_table(frame, sample, rate_symbols))
    rates = pd.DataFrame(rate_rows)
    path_rates = pd.DataFrame(path_rows)
    symbol_rates = pd.DataFrame(symbol_rate_rows(all_events, ctp))

    eligible = [row for row in qualities if row["eligible"]]
    skipped = [row for row in qualities if not row["eligible"]]
    universe = {
        "raw_symbols": int(panel["sym_key"].nunique()),
        "eligible_symbols": int(len(eligible)),
        "skipped_symbols": int(len(skipped)),
        "skipped_excluded_base": int(
            sum(row["skip_reason"] == "excluded_base" for row in skipped)
        ),
        "skipped_short_history": int(
            sum(row["skip_reason"] == "short_history" for row in skipped)
        ),
        "skipped_no_crosses": int(
            sum(row["skip_reason"] == "no_crosses" for row in skipped)
        ),
        "eligible_complete_days": int(sum(row["complete_days"] for row in eligible)),
        "eligible_missing_inside_span": int(
            sum(row["missing_inside_span"] for row in eligible)
        ),
        "panel_start": PANEL_START.isoformat(),
        "panel_end": PANEL_END.isoformat(),
        "cache_marker": str(CACHE_MARKER.relative_to(ROOT)),
    }
    full_both = ctp.pick_rate(rates, "full", "ALL", "both", "cross")
    full_long = ctp.pick_rate(rates, "full", "ALL", "long", "cross")
    full_short = ctp.pick_rate(rates, "full", "ALL", "short", "cross")
    slope = ctp.pick_rate(rates, "full", "ALL", "both", "slope_002")
    vol = ctp.pick_rate(rates, "full", "ALL", "both", "vol_1p5")
    stack = ctp.pick_rate(rates, "full", "ALL", "both", "slope_002+vol_1p5")
    path = ctp.pick_rate(rates, "full", "ALL", "both", "path_ratio30_reclaim_or_fade")
    n_ew = int(symbol_rates["trend_20_both_n"].ge(ctp.MIN_N_HIGHLIGHT).sum())
    ew = equal_weight(symbol_rates, "trend_20_both_p", ctp.MIN_N_HIGHLIGHT)
    headline = (
        f"全市场完整日K上，收盘穿越 SMA7 之后约有 **{ctp.fmt_pct(float(full_both['trend_20_p']))}** "
        f"会在 20 个完整日后先走出顺向 2ATR、且没有先被反向 1ATR 打掉"
        f"（多头 {ctp.fmt_pct(float(full_long['trend_20_p']))}，空头 {ctp.fmt_pct(float(full_short['trend_20_p']))}）。"
        f"这与四币 30.8%/34.4%/27.2% 同量级，也接近 TPSA 全市场的 27.9%/31.0%。"
        f"斜率 0.02 后为 {ctp.fmt_pct(float(slope['trend_20_p']))}，放量 1.5× 后为 {ctp.fmt_pct(float(vol['trend_20_p']))}，"
        f"两者同时要求后为 {ctp.fmt_pct(float(stack['trend_20_p']))}；30 日 R 方向过滤为 {ctp.fmt_pct(float(path['trend_20_p']))}。"
        f"{n_ew} 个有足够样本的合约等权平均 {ctp.fmt_pct(ew)}。"
        "过滤器仍然只是轻轻挪动概率，没有把多数穿越变成高把握趋势。"
    )
    lifts = []
    for name, row in (
        ("斜率0.02", slope),
        ("放量1.5×", vol),
        ("斜率+放量", stack),
        ("30日R方向", path),
    ):
        if np.isfinite(row["trend_20_p"]) and float(full_both["trend_20_p"]) > 0:
            lifts.append(
                f"{name} {float(row['trend_20_p']) / float(full_both['trend_20_p']):.2f}×"
            )
    verdict = (
        "Verdict: **ITERATE / 不是策略**。\n\n"
        f"- 全市场并没有把四币结论翻盘：裸穿越 `trend_20` 仍约三成，{full_both['trend_20_txt']}。\n"
        f"- 斜率、放量、前置涨跌比的抬升仍然有限（相对裸穿越：{', '.join(lifts)}）。\n"
        "- Confidence: **MEDIUM**。宇宙是缓存里的 point-in-time 完整日，缺日已丢掉；这不是扣成本后的交易期望，也不是新 OOS。\n"
        "- Warning：事件加权会被上市更久、穿越更多的币拉动；等权平均已并列报告。\n"
        "- Next：不要在全市场格子上继续堆过滤。若继续，应另冻一条路径假设并用未揭示月份确认。"
    )
    summary = {
        "family": "Binance-1D-MA7-Cross-Trend-Probability",
        "alias": "BIN-1D-MA7-CTP",
        "run_date": RUN_DATE,
        "universe_name": "all-market-cache",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "explore / diagnostic-only / not promoted / not live-ready",
        "universe": universe,
        "headline": headline,
        "verdict_block": verdict,
        "event_counts": {
            sample: {
                "rows": int(len(frame)),
                "symbols": int(frame["symbol"].nunique()),
                "long": int(frame["side"].eq("long").sum()),
                "short": int(frame["side"].eq("short").sum()),
            }
            for sample, frame in sliced.items()
        },
        "outputs": {key: str(path.relative_to(ROOT)) for key, path in OUTPUTS.items()},
    }

    for path in OUTPUTS.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    all_events.to_parquet(OUTPUTS["events"], index=False)
    rates.to_csv(OUTPUTS["rates"], index=False)
    path_rates.to_csv(OUTPUTS["path_rates"], index=False)
    symbol_rates.to_csv(OUTPUTS["symbols"], index=False)
    OUTPUTS["quality"].write_text(
        json.dumps({"universe": universe, "symbols": qualities}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    OUTPUTS["summary"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_report(
        ctp=ctp,
        qualities=qualities,
        rates=rates,
        path_rates=path_rates,
        symbol_rates=symbol_rates,
        summary=summary,
    )
    print(
        json.dumps(
            {
                "events": int(len(all_events)),
                "symbols": universe["eligible_symbols"],
                "report": str(OUTPUTS["report"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
