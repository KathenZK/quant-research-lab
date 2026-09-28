from __future__ import annotations

import json
import sys
import time
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import research_hype_15m_mii_clean_evolution as evolution  # noqa: E402
import research_hype_15m_mii_v1_full_ablation as v1  # noqa: E402
from research_hype_15m_mii_search import (  # noqa: E402
    COMMISSION_PER_SIDE,
    FAPI_KLINES_URL,
    INTERVAL,
    INTERVAL_MS,
    ROUND_TRIP_COST,
    SLIPPAGE_PER_SIDE,
    build_market_arrays,
    signal_state,
)


FAMILY = "HYPE-15M-Multi-Indicator-Intraday"
ALIAS = "HYPE-15M-MII"
VERSION = "HYPE-15M-MII-V1.1"
RUN_DATE = "2026-06-30"
FAMILY_DIR = Path("research/hype/15m-multi-indicator-intraday")
SCRIPT_PATH = FAMILY_DIR / "scripts" / "research_hype_15m_mii_v1_1_btc_eth_cross_asset.py"
ARTIFACTS_DIR = FAMILY_DIR / "artifacts"
NOTES_DIR = FAMILY_DIR / "notes"
CSV_PATH = ARTIFACTS_DIR / "hype_15m_mii_v1_1_btc_eth_cross_asset_2026-06-30.csv"
JSON_PATH = ARTIFACTS_DIR / "hype_15m_mii_v1_1_btc_eth_cross_asset_2026-06-30.json"
MARKDOWN_PATH = NOTES_DIR / "hype-15m-mii-v1-1-btc-eth-cross-asset-2026-06-30.md"

SYMBOLS = ("BTCUSDT", "ETHUSDT")
START_TS = pd.Timestamp("2025-05-30T10:30:00Z")
END_TS = pd.Timestamp("2026-06-26T04:00:00Z")
WINDOWS: tuple[tuple[str, pd.Timedelta | None], ...] = (
    ("最近1周", pd.Timedelta(days=7)),
    ("最近1月", pd.Timedelta(days=30)),
    ("最近3月", pd.Timedelta(days=90)),
    ("最近6月", pd.Timedelta(days=182)),
    ("最近1年", pd.Timedelta(days=365)),
    ("全样本", None),
)
ENTRY_DELAYS = ((1, "K+1"), (2, "K+2"))

BASE_CONFIG = evolution.CleanConfig(
    rsi_window=7,
    rsi_low=40.0,
    rsi_high=60.0,
    min_atr_pct96=0.0075,
    min_rvol96=1.0,
    h1_confirm=False,
    rsi14_band=False,
    take_profit_pct=0.012,
    stop_pct=0.036,
    max_hold_bars=16,
    exposure=2.0,
)


def fetch_fapi_klines(symbol: str) -> pd.DataFrame:
    start = int(START_TS.timestamp() * 1000)
    end = int(END_TS.timestamp() * 1000)
    rows: list[list[Any]] = []
    while start <= end:
        params = urlencode(
            {
                "symbol": symbol,
                "interval": INTERVAL,
                "startTime": start,
                "endTime": end,
                "limit": 1500,
            }
        )
        request = Request(
            f"{FAPI_KLINES_URL}?{params}",
            headers={"User-Agent": "quant-research-lab/0.1"},
        )
        with urlopen(request, timeout=45) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        if not payload:
            break
        rows.extend(payload)
        next_start = int(payload[-1][0]) + INTERVAL_MS
        if next_start <= start:
            break
        start = next_start
        time.sleep(0.05)
    if not rows:
        raise RuntimeError(f"Binance FAPI returned no rows for {symbol}.")

    frame = pd.DataFrame(
        rows,
        columns=[
            "ts",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trade_count",
            "taker_base",
            "taker_quote",
            "ignore",
        ],
    )
    keep = [
        "ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
    ]
    frame = frame[keep].copy()
    frame["ts"] = pd.to_datetime(frame["ts"], unit="ms", utc=True)
    for column in ["open", "high", "low", "close", "volume", "quote_volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["trade_count"] = pd.to_numeric(frame["trade_count"], errors="coerce")
    frame["exchange"] = "binance"
    frame["symbol"] = f"{symbol[:-4]}/USDT:USDT"
    frame["market_type"] = "perp"
    frame["timeframe"] = "15m"
    frame["source"] = "binance_futures_kline_api_direct"
    frame["is_closed"] = True
    frame["vwap"] = np.where(
        frame["volume"].to_numpy("float64") > 0,
        frame["quote_volume"].to_numpy("float64") / frame["volume"].to_numpy("float64"),
        np.nan,
    )
    frame = frame.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    return frame


def data_quality(frame: pd.DataFrame, symbol: str) -> dict[str, Any]:
    expected = pd.Timedelta(minutes=15)
    gaps = frame["ts"].diff().dropna()
    numeric_columns = ["open", "high", "low", "close", "volume", "quote_volume", "trade_count", "vwap"]
    invalid_ohlc = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
        | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (frame["volume"] < 0)
        | (frame["quote_volume"] < 0)
        | (frame["trade_count"] < 0)
        | (
            frame["volume"].gt(0)
            & (
                frame["vwap"].lt(frame["low"])
                | frame["vwap"].gt(frame["high"])
            )
        )
    )
    report = {
        "symbol": symbol,
        "source": "binance_futures_kline_api_direct",
        "target_first_ts": START_TS.isoformat(),
        "target_last_ts": END_TS.isoformat(),
        "rows": int(len(frame)),
        "first_ts": frame["ts"].min().isoformat() if len(frame) else None,
        "last_ts": frame["ts"].max().isoformat() if len(frame) else None,
        "gap_count": int(gaps.ne(expected).sum()),
        "duplicates": int(frame["ts"].duplicated().sum()),
        "critical_nulls": int(frame[["ts", *numeric_columns, "source", "is_closed"]].isna().sum().sum()),
        "invalid_ohlc_rows": int(invalid_ohlc.sum()),
        "open_bar_rows": int((~frame["is_closed"].astype(bool)).sum()),
        "unknown_source_rows": int(frame["source"].astype(str).str.strip().eq("").sum()),
    }
    blockers = [
        report["rows"] == 0,
        report["gap_count"],
        report["duplicates"],
        report["critical_nulls"],
        report["invalid_ohlc_rows"],
        report["open_bar_rows"],
        report["unknown_source_rows"],
    ]
    report["quality_gate_pass"] = not any(blockers)
    return report


def build_context(frame: pd.DataFrame) -> evolution.EvalContext:
    features = evolution.add_rsi_features(evolution.add_features(frame, []))
    return evolution.EvalContext(
        features=features,
        market=build_market_arrays(features),
        start_ts=pd.Timestamp(features["ts"].min()),
        end_ts=pd.Timestamp(features["ts"].max()) + pd.Timedelta(minutes=15),
        signal_cache={},
        trade_cache=OrderedDict(),
    )


def selected_net_returns_pct(trades: list[Any], start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> list[float]:
    window_trades = [trade for trade in trades if start_ts <= trade.entry_ts < end_ts]
    selected = v1.selected_trades_live(window_trades, BASE_CONFIG.filter)
    return [
        float(BASE_CONFIG.exposure * (trade.raw_return - ROUND_TRIP_COST) * 100.0)
        for trade in selected
    ]


def evaluate_symbol(symbol: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    frame = fetch_fapi_klines(symbol)
    quality = data_quality(frame, symbol)
    if not quality["quality_gate_pass"]:
        raise ValueError(f"data-quality blocker for {symbol}: {json.dumps(quality, ensure_ascii=False)}")
    context = build_context(frame)
    state = signal_state(context.features, BASE_CONFIG.signal)
    rows: list[dict[str, Any]] = []
    for entry_delay_bars, entry_label in ENTRY_DELAYS:
        trades = v1.simulate_trades_live(
            context.market,
            state,
            BASE_CONFIG.exit,
            entry_delay_bars=entry_delay_bars,
        )
        for window_name, duration in WINDOWS:
            end_ts = context.end_ts
            start_ts = context.start_ts if duration is None else max(context.start_ts, end_ts - duration)
            metrics = evolution.evaluate_window(
                context,
                BASE_CONFIG,
                trades,
                start_ts,
                end_ts,
                purge_end=False,
            )
            net_returns = selected_net_returns_pct(trades, start_ts, end_ts)
            if int(metrics["trades"]) == 0:
                metrics = {
                    **metrics,
                    "annual_return_pct": 0.0,
                    "total_return_pct": 0.0,
                    "max_drawdown_pct": 0.0,
                    "win_rate_pct": 0.0,
                    "profit_factor": 0.0,
                }
            rows.append(
                {
                    "asset": symbol.replace("USDT", ""),
                    "symbol": symbol,
                    "version": VERSION,
                    "engine_name": BASE_CONFIG.name,
                    "window": window_name,
                    "entry_timing": entry_label,
                    "entry_delay_bars": entry_delay_bars,
                    "start_ts": start_ts.isoformat(),
                    "end_ts": end_ts.isoformat(),
                    "period_days": max((end_ts - start_ts).total_seconds() / 86400.0, 0.0),
                    **asdict(BASE_CONFIG),
                    "annual_return_pct": float(metrics["annual_return_pct"]),
                    "total_return_pct": float(metrics["total_return_pct"]),
                    "max_drawdown_pct": float(metrics["max_drawdown_pct"]),
                    "win_rate_pct": float(metrics["win_rate_pct"]),
                    "trades": int(metrics["trades"]),
                    "trades_per_day": float(metrics["trades_per_day"]),
                    "profit_factor": float(metrics["profit_factor"]),
                    "avg_trade_pct": float(np.mean(net_returns)) if net_returns else 0.0,
                    "worst_trade_pct": float(np.min(net_returns)) if net_returns else 0.0,
                }
            )
    return rows, quality


def metric_table(rows: pd.DataFrame, entry_timing: str) -> list[str]:
    subset = rows.loc[rows["entry_timing"].eq(entry_timing)]
    lines = [
        f"### {entry_timing}",
        "",
        "| 资产 | 窗口 | 年化 | 总收益 | 最大回撤 | 胜率 | 交易数 | 笔/天 | PF | 平均单笔 | 最差单笔 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in subset.to_dict(orient="records"):
        lines.append(
            f"| `{row['asset']}` | `{row['window']}` | "
            f"`{row['annual_return_pct']:.2f}%` | "
            f"`{row['total_return_pct']:.2f}%` | "
            f"`{row['max_drawdown_pct']:.2f}%` | "
            f"`{row['win_rate_pct']:.2f}%` | "
            f"`{int(row['trades'])}` | "
            f"`{row['trades_per_day']:.3f}` | "
            f"`{row['profit_factor']:.3f}` | "
            f"`{row['avg_trade_pct']:.3f}%` | "
            f"`{row['worst_trade_pct']:.3f}%` |"
        )
    return lines


def lookup(rows: pd.DataFrame, asset: str, window: str, entry_timing: str) -> pd.Series:
    selected = rows.loc[
        rows["asset"].eq(asset)
        & rows["window"].eq(window)
        & rows["entry_timing"].eq(entry_timing)
    ]
    if selected.empty:
        raise ValueError(f"missing row {asset=} {window=} {entry_timing=}")
    return selected.iloc[0]


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [json_safe(child) for child in value]
    if isinstance(value, tuple):
        return [json_safe(child) for child in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def render_markdown(rows: pd.DataFrame, qualities: dict[str, Any]) -> str:
    btc_all = lookup(rows, "BTC", "全样本", "K+1")
    eth_all = lookup(rows, "ETH", "全样本", "K+1")
    btc_k2 = lookup(rows, "BTC", "全样本", "K+2")
    eth_k2 = lookup(rows, "ETH", "全样本", "K+2")
    lines = [
        f"# HYPE-15M-MII V1.1 BTC/ETH 跨资产回测 {RUN_DATE}",
        "",
        f"Family：`{FAMILY}`（alias：`{ALIAS}`）",
        "",
        "## 结论",
        "",
        "`HYPE-15M-MII-V1.1` 是为 HYPE 选择的 `15m` 参数。这里直接套到 Binance USD-M `BTCUSDT`、`ETHUSDT`，只作为跨资产 sanity check，不是新策略搜索或 promotion。",
        "",
        (
            f"- BTC K+1 全样本：年化 `{btc_all['annual_return_pct']:.2f}%`、总收益 "
            f"`{btc_all['total_return_pct']:.2f}%`、回撤 `{btc_all['max_drawdown_pct']:.2f}%`、"
            f"胜率 `{btc_all['win_rate_pct']:.2f}%`、交易 `{int(btc_all['trades'])}` 笔；"
            f"K+2 年化 `{btc_k2['annual_return_pct']:.2f}%`、回撤 `{btc_k2['max_drawdown_pct']:.2f}%`。"
        ),
        (
            f"- ETH K+1 全样本：年化 `{eth_all['annual_return_pct']:.2f}%`、总收益 "
            f"`{eth_all['total_return_pct']:.2f}%`、回撤 `{eth_all['max_drawdown_pct']:.2f}%`、"
            f"胜率 `{eth_all['win_rate_pct']:.2f}%`、交易 `{int(eth_all['trades'])}` 笔；"
            f"K+2 年化 `{eth_k2['annual_return_pct']:.2f}%`、回撤 `{eth_k2['max_drawdown_pct']:.2f}%`。"
        ),
        "- 数据来自 Binance futures kline API 直接拉取，不是本仓库标准 raw/normalized 数据湖；因此结果只可作为迁移诊断。",
        "",
        "## 策略参数",
        "",
        "- Signal：`RSI(7)` 上穿 `40` 做多，下穿 `60` 做空。",
        "- Filter：`side=both`；`MACD(12,26,9)` 方向过滤；`ATR96 pct` 在 `0.75%-2.80%`；`RVOL96 >= 1.0`。",
        "- Exit：固定 `TP=1.20%`、`SL=3.60%`、最长 `16` 根 `15m` K。",
        "- Exposure：`2x` 权益暴露；手续费 `0.1000%`/fill，滑点 `0.0400%`/fill，资金费未计入。",
        "",
        "## 数据质量",
        "",
    ]
    for symbol, quality in qualities.items():
        lines.append(
            f"- `{symbol}`：`{quality['first_ts']}` 到 `{quality['last_ts']}`，rows `{quality['rows']}`，"
            f"gap `{quality['gap_count']}`，duplicates `{quality['duplicates']}`，critical nulls `{quality['critical_nulls']}`，"
            f"invalid OHLC `{quality['invalid_ohlc_rows']}`，quality gate `{quality['quality_gate_pass']}`。"
        )
    lines.extend(["", "## 分窗口结果", ""])
    lines.extend(metric_table(rows, "K+1"))
    lines.append("")
    lines.extend(metric_table(rows, "K+2"))
    lines.extend(
        [
            "",
            "## 状态",
            "",
            "本报告是跨资产 diagnostic。若 BTC/ETH 表现弱，说明 HYPE 参数未自然迁移；若表现强，也仍需标准数据湖复验、资金费和真实成交审计。",
            "",
            "## 产物",
            "",
            f"- 脚本：`{SCRIPT_PATH}`",
            f"- CSV：`{CSV_PATH}`",
            f"- JSON：`{JSON_PATH}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    all_rows: list[dict[str, Any]] = []
    qualities: dict[str, Any] = {}
    for symbol in SYMBOLS:
        rows, quality = evaluate_symbol(symbol)
        all_rows.extend(rows)
        qualities[symbol] = quality
    result = pd.DataFrame(all_rows)
    result["asset_order"] = result["asset"].map({"BTC": 0, "ETH": 1})
    result["entry_order"] = result["entry_delay_bars"]
    result["window_order"] = result["window"].map(
        {name: index for index, (name, _duration) in enumerate(WINDOWS)}
    )
    result = result.sort_values(["asset_order", "entry_order", "window_order"]).drop(
        columns=["asset_order", "entry_order", "window_order"]
    )

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(CSV_PATH, index=False)
    summary = {
        "family": FAMILY,
        "alias": ALIAS,
        "version": VERSION,
        "run_date": RUN_DATE,
        "status": "btc_eth_cross_asset_diagnostic_not_promoted",
        "data_source": "binance_futures_kline_api_direct",
        "target_range": {"start": START_TS.isoformat(), "end": END_TS.isoformat()},
        "costs": {
            "commission_per_fill": COMMISSION_PER_SIDE,
            "slippage_per_fill": SLIPPAGE_PER_SIDE,
            "round_trip_cost": ROUND_TRIP_COST,
        },
        "base_config": asdict(BASE_CONFIG),
        "data_quality": qualities,
        "rows": result.to_dict(orient="records"),
        "outputs": {
            "script": str(SCRIPT_PATH),
            "csv": str(CSV_PATH),
            "markdown": str(MARKDOWN_PATH),
        },
    }
    JSON_PATH.write_text(
        json.dumps(json_safe(summary), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    MARKDOWN_PATH.write_text(render_markdown(result, qualities), encoding="utf-8")
    print(result.to_string(index=False))
    print(f"Wrote {CSV_PATH}")
    print(f"Wrote {JSON_PATH}")
    print(f"Wrote {MARKDOWN_PATH}")


if __name__ == "__main__":
    main()
