from __future__ import annotations

# pyright: reportMissingImports=false

import json
import math
import sys
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

HYPE_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[3]
    / "hype"
    / "15m-multi-indicator-intraday"
    / "scripts"
)
if str(HYPE_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(HYPE_SCRIPTS_DIR))

import research_hype_15m_mii_clean_evolution as evolution  # noqa: E402
import research_hype_15m_mii_v1_full_ablation as v1  # noqa: E402
from research_hype_15m_mii_search import (  # noqa: E402
    COMMISSION_PER_SIDE,
    FAPI_KLINES_URL,
    FilterSpec,
    INTERVAL,
    INTERVAL_MS,
    ROUND_TRIP_COST,
    SLIPPAGE_PER_SIDE,
    SignalSpec,
    build_market_arrays,
    signal_state,
)


FAMILY = "Binance-15M-Multi-Indicator-Intraday-Transfer"
RUN_DATE = "2026-06-30"
RESEARCH_DIR = Path("research/asset-portfolios/15m-multi-indicator-intraday")
SCRIPT_PATH = RESEARCH_DIR / "scripts" / "research_binance_15m_mii_btc_eth_constrained_search.py"
ARTIFACTS_DIR = RESEARCH_DIR / "artifacts"
DIAGNOSTICS_DIR = RESEARCH_DIR / "diagnostics"
RANKING_CSV_PATH = ARTIFACTS_DIR / "binance_15m_mii_btc_eth_constrained_search_ranking_2026-06-30.csv"
FINALISTS_CSV_PATH = ARTIFACTS_DIR / "binance_15m_mii_btc_eth_constrained_search_finalists_2026-06-30.csv"
SLICES_CSV_PATH = ARTIFACTS_DIR / "binance_15m_mii_btc_eth_constrained_search_slices_2026-06-30.csv"
JSON_PATH = ARTIFACTS_DIR / "binance_15m_mii_btc_eth_constrained_search_2026-06-30.json"
MARKDOWN_PATH = DIAGNOSTICS_DIR / "binance-15m-mii-btc-eth-constrained-search-2026-06-30.md"

SYMBOLS = ("BTCUSDT", "ETHUSDT")
START_TS = pd.Timestamp("2025-05-30T10:30:00Z")
END_TS = pd.Timestamp("2026-06-26T04:00:00Z")
TIMEFRAME_MINUTES = 15
MAX_ATR_PCT_GUARDRAIL = 0.028
ENTRY_DELAYS = ((1, "K+1"), (2, "K+2"))
WINDOWS: tuple[tuple[str, pd.Timedelta | None], ...] = (
    ("full", None),
    ("first_half", "first_half"),
    ("second_half", "second_half"),
    ("last90", pd.Timedelta(days=90)),
    ("recent30", pd.Timedelta(days=30)),
)

RSI_WINDOWS = (7, 9)
RSI_LOWS = (35.0, 40.0, 45.0)
RSI_HIGHS = (55.0, 60.0, 65.0)
SIDES = ("both", "long", "short")
MIN_ATR_PCT96 = (0.0, 0.0015, 0.0025, 0.0035, 0.0045)
MIN_RVOL96 = (0.0, 0.5, 1.0)
TAKE_PROFIT_PCT = (0.0045, 0.006, 0.0075, 0.009)
STOP_PCT = (0.009, 0.012, 0.018, 0.024)
MAX_HOLD_BARS = (8, 16, 24)
EXPOSURE = 1.0


@dataclass(frozen=True, slots=True)
class TransferConfig:
    rsi_window: int
    rsi_low: float
    rsi_high: float
    side: str
    min_atr_pct96: float
    min_rvol96: float
    take_profit_pct: float
    stop_pct: float
    max_hold_bars: int
    exposure: float = EXPOSURE

    @property
    def signal(self) -> SignalSpec:
        return SignalSpec(
            name=(
                f"rsi_reversal_w{self.rsi_window}_lo{value_slug(self.rsi_low)}"
                f"_hi{value_slug(self.rsi_high)}"
            ),
            kind="rsi_reversal",
            window=self.rsi_window,
            low=self.rsi_low,
            high=self.rsi_high,
        )

    @property
    def filter(self) -> FilterSpec:
        return FilterSpec(
            side=self.side,
            min_rvol96=self.min_rvol96,
            min_dir_macd=0.0,
            min_atr_pct96=self.min_atr_pct96,
            max_atr_pct96=MAX_ATR_PCT_GUARDRAIL,
        )

    @property
    def exit(self) -> Any:
        return v1.ExitSpec(
            kind="fixed",
            take_profit_pct=self.take_profit_pct,
            stop_pct=self.stop_pct,
            max_hold_bars=self.max_hold_bars,
        )

    @property
    def name(self) -> str:
        side = "" if self.side == "both" else f"_{self.side}"
        return (
            f"btceth_mii_rsi{self.rsi_window}_{value_slug(self.rsi_low)}_"
            f"{value_slug(self.rsi_high)}{side}_atrmin{pct_slug(self.min_atr_pct96)}_"
            f"rvol{value_slug(self.min_rvol96)}_tp{pct_slug(self.take_profit_pct)}_"
            f"sl{pct_slug(self.stop_pct)}_hold{self.max_hold_bars}_x{value_slug(self.exposure)}"
        )


@dataclass(slots=True)
class EvalContext:
    features: pd.DataFrame
    market: Any
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    signal_cache: dict[str, Any]
    trade_cache: OrderedDict[tuple[str, str, int], list[Any]]


def value_slug(value: float) -> str:
    return f"{value:g}".replace("-", "m").replace(".", "p")


def pct_slug(value: float) -> str:
    return value_slug(value * 10_000)


def fetch_fapi_klines(symbol: str) -> pd.DataFrame:
    start = int(START_TS.timestamp() * 1000)
    end = int(END_TS.timestamp() * 1000)
    rows: list[list[Any]] = []
    while start <= end:
        params = urlencode(
            {"symbol": symbol, "interval": INTERVAL, "startTime": start, "endTime": end, "limit": 1500}
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
    frame = frame[["ts", "open", "high", "low", "close", "volume", "quote_volume", "trade_count"]].copy()
    frame["ts"] = pd.to_datetime(frame["ts"], unit="ms", utc=True)
    for column in ["open", "high", "low", "close", "volume", "quote_volume", "trade_count"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
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
    return frame.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


def data_quality(frame: pd.DataFrame, symbol: str) -> dict[str, Any]:
    gaps = frame["ts"].diff().dropna()
    expected = pd.Timedelta(minutes=15)
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
            & (frame["vwap"].lt(frame["low"]) | frame["vwap"].gt(frame["high"]))
        )
    )
    report = {
        "symbol": symbol,
        "source": "binance_futures_kline_api_direct",
        "target_first_ts": START_TS.isoformat(),
        "target_last_ts": END_TS.isoformat(),
        "rows": int(len(frame)),
        "first_ts": frame["ts"].min().isoformat(),
        "last_ts": frame["ts"].max().isoformat(),
        "gap_count": int(gaps.ne(expected).sum()),
        "duplicates": int(frame["ts"].duplicated().sum()),
        "critical_nulls": int(frame[["ts", *numeric_columns, "source", "is_closed"]].isna().sum().sum()),
        "invalid_ohlc_rows": int(invalid_ohlc.sum()),
        "open_bar_rows": int((~frame["is_closed"].astype(bool)).sum()),
        "unknown_source_rows": int(frame["source"].astype(str).str.strip().eq("").sum()),
    }
    report["quality_gate_pass"] = not any(
        [
            report["rows"] == 0,
            report["gap_count"],
            report["duplicates"],
            report["critical_nulls"],
            report["invalid_ohlc_rows"],
            report["open_bar_rows"],
            report["unknown_source_rows"],
        ]
    )
    return report


def build_context(frame: pd.DataFrame) -> EvalContext:
    features = evolution.add_rsi_features(evolution.add_features(frame, []))
    return EvalContext(
        features=features,
        market=build_market_arrays(features),
        start_ts=pd.Timestamp(features["ts"].min()),
        end_ts=pd.Timestamp(features["ts"].max()) + pd.Timedelta(minutes=15),
        signal_cache={},
        trade_cache=OrderedDict(),
    )


def raw_trades(context: EvalContext, config: TransferConfig, entry_delay_bars: int) -> list[Any]:
    key = (config.signal.name, config.exit.name, entry_delay_bars)
    if key in context.trade_cache:
        context.trade_cache.move_to_end(key)
        return context.trade_cache[key]
    if config.signal.name not in context.signal_cache:
        context.signal_cache[config.signal.name] = signal_state(context.features, config.signal)
    trades = v1.simulate_trades_live(
        context.market,
        context.signal_cache[config.signal.name],
        config.exit,
        entry_delay_bars=entry_delay_bars,
    )
    context.trade_cache[key] = trades
    context.trade_cache.move_to_end(key)
    while len(context.trade_cache) > 512:
        context.trade_cache.popitem(last=False)
    return trades


def empty_metrics() -> dict[str, float | int]:
    return {
        "annual_return_pct": 0.0,
        "total_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "win_rate_pct": 0.0,
        "trades": 0,
        "trades_per_day": 0.0,
        "profit_factor": 0.0,
    }


def evaluate_window(
    trades: list[Any],
    config: TransferConfig,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> dict[str, Any]:
    window_trades = [trade for trade in trades if start_ts <= trade.entry_ts < end_ts]
    period_days = max((end_ts - start_ts).total_seconds() / 86_400, 1.0)
    result = v1.engine.evaluate_trades(
        trades=window_trades,
        filter_spec=config.filter,
        exposure=config.exposure,
        period_days=period_days,
        exit_spec=config.exit,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    if result is None:
        return empty_metrics()
    metrics = asdict(result)
    if int(metrics["trades"]) == 0:
        metrics.update(empty_metrics())
    return metrics


def window_bounds(
    label: str,
    duration: pd.Timedelta | str | None,
    context: EvalContext,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    if duration is None:
        return context.start_ts, context.end_ts
    if duration == "first_half":
        midpoint = context.start_ts + (context.end_ts - context.start_ts) / 2
        return context.start_ts, midpoint
    if duration == "second_half":
        midpoint = context.start_ts + (context.end_ts - context.start_ts) / 2
        return midpoint, context.end_ts
    if isinstance(duration, pd.Timedelta):
        return max(context.start_ts, context.end_ts - duration), context.end_ts
    raise ValueError(f"unknown window {label}: {duration}")


def generate_configs() -> list[TransferConfig]:
    configs: list[TransferConfig] = []
    for values in product(
        RSI_WINDOWS,
        RSI_LOWS,
        RSI_HIGHS,
        SIDES,
        MIN_ATR_PCT96,
        MIN_RVOL96,
        TAKE_PROFIT_PCT,
        STOP_PCT,
        MAX_HOLD_BARS,
    ):
        rsi_window, rsi_low, rsi_high, side, min_atr, min_rvol, tp, stop, hold = values
        if rsi_high - rsi_low < 15.0:
            continue
        if stop < tp:
            continue
        configs.append(
            TransferConfig(
                rsi_window=int(rsi_window),
                rsi_low=float(rsi_low),
                rsi_high=float(rsi_high),
                side=str(side),
                min_atr_pct96=float(min_atr),
                min_rvol96=float(min_rvol),
                take_profit_pct=float(tp),
                stop_pct=float(stop),
                max_hold_bars=int(hold),
            )
        )
    configs.append(
        TransferConfig(
            rsi_window=7,
            rsi_low=40.0,
            rsi_high=60.0,
            side="both",
            min_atr_pct96=0.0075,
            min_rvol96=1.0,
            take_profit_pct=0.012,
            stop_pct=0.036,
            max_hold_bars=16,
        )
    )
    return list(dict.fromkeys(configs))


def safe_log_return(value: float) -> float:
    return math.log(max(0.02, 1.0 + value / 100.0))


def score_pair(k1: dict[str, Any], k2: dict[str, Any]) -> float:
    trades = min(float(k1["trades"]), float(k2["trades"]))
    pf = min(max(float(k1["profit_factor"]), 0.05), 5.0)
    pf2 = min(max(float(k2["profit_factor"]), 0.05), 5.0)
    score = (
        2.0 * safe_log_return(float(k1["annual_return_pct"]))
        + 1.5 * safe_log_return(float(k2["annual_return_pct"]))
        + 0.03 * (float(k1["win_rate_pct"]) - 50.0)
        + 0.02 * (float(k2["win_rate_pct"]) - 50.0)
        + 0.7 * math.log(pf)
        + 0.5 * math.log(pf2)
        + 0.035 * float(k1["max_drawdown_pct"])
        + 0.025 * float(k2["max_drawdown_pct"])
    )
    if float(k1["total_return_pct"]) <= 0:
        score -= 2.5
    if float(k2["total_return_pct"]) <= 0:
        score -= 2.0
    if trades < 12:
        score -= (12.0 - trades) * 0.18
    if trades > 120:
        score -= (trades - 120.0) * 0.01
    return score


def evaluate_stage1(symbol: str, context: EvalContext, configs: list[TransferConfig]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, config in enumerate(configs, start=1):
        k1_trades = raw_trades(context, config, 1)
        k2_trades = raw_trades(context, config, 2)
        k1 = evaluate_window(k1_trades, config, context.start_ts, context.end_ts)
        k2 = evaluate_window(k2_trades, config, context.start_ts, context.end_ts)
        row: dict[str, Any] = {
            "asset": symbol.replace("USDT", ""),
            "symbol": symbol,
            "family": FAMILY,
            "name": config.name,
            **asdict(config),
            "k1_annual_return_pct": float(k1["annual_return_pct"]),
            "k1_total_return_pct": float(k1["total_return_pct"]),
            "k1_max_drawdown_pct": float(k1["max_drawdown_pct"]),
            "k1_win_rate_pct": float(k1["win_rate_pct"]),
            "k1_trades": int(k1["trades"]),
            "k1_trades_per_day": float(k1["trades_per_day"]),
            "k1_profit_factor": float(k1["profit_factor"]),
            "k2_annual_return_pct": float(k2["annual_return_pct"]),
            "k2_total_return_pct": float(k2["total_return_pct"]),
            "k2_max_drawdown_pct": float(k2["max_drawdown_pct"]),
            "k2_win_rate_pct": float(k2["win_rate_pct"]),
            "k2_trades": int(k2["trades"]),
            "k2_trades_per_day": float(k2["trades_per_day"]),
            "k2_profit_factor": float(k2["profit_factor"]),
        }
        row["score"] = score_pair(k1, k2)
        row["strict_transfer_pass"] = bool(
            row["k1_total_return_pct"] > 0
            and row["k2_total_return_pct"] > 0
            and row["k1_max_drawdown_pct"] >= -25.0
            and row["k2_max_drawdown_pct"] >= -30.0
            and row["k1_trades"] >= 20
            and row["k2_trades"] >= 20
        )
        rows.append(row)
        if index % 5000 == 0:
            print(f"{symbol}: evaluated {index}/{len(configs)} configs")
    return pd.DataFrame(rows)


def evaluate_slices(
    symbol: str,
    context: EvalContext,
    configs: list[TransferConfig],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    finalist_rows: list[dict[str, Any]] = []
    slice_rows: list[dict[str, Any]] = []
    for config in configs:
        by_delay: dict[str, dict[str, dict[str, Any]]] = {}
        for entry_delay, entry_label in ENTRY_DELAYS:
            trades = raw_trades(context, config, entry_delay)
            by_delay[entry_label] = {}
            for window_label, duration in WINDOWS:
                start_ts, end_ts = window_bounds(window_label, duration, context)
                metrics = evaluate_window(trades, config, start_ts, end_ts)
                by_delay[entry_label][window_label] = metrics
                slice_rows.append(
                    {
                        "asset": symbol.replace("USDT", ""),
                        "symbol": symbol,
                        "entry_timing": entry_label,
                        "window": window_label,
                        "start_ts": start_ts.isoformat(),
                        "end_ts": end_ts.isoformat(),
                        "name": config.name,
                        **asdict(config),
                        **metrics,
                    }
                )
        k1_full = by_delay["K+1"]["full"]
        k2_full = by_delay["K+2"]["full"]
        k1_second = by_delay["K+1"]["second_half"]
        k2_second = by_delay["K+2"]["second_half"]
        k1_last90 = by_delay["K+1"]["last90"]
        k2_last90 = by_delay["K+2"]["last90"]
        k1_recent30 = by_delay["K+1"]["recent30"]
        k2_recent30 = by_delay["K+2"]["recent30"]
        row = {
            "asset": symbol.replace("USDT", ""),
            "symbol": symbol,
            "family": FAMILY,
            "name": config.name,
            **asdict(config),
            "k1_annual_return_pct": float(k1_full["annual_return_pct"]),
            "k1_total_return_pct": float(k1_full["total_return_pct"]),
            "k1_max_drawdown_pct": float(k1_full["max_drawdown_pct"]),
            "k1_win_rate_pct": float(k1_full["win_rate_pct"]),
            "k1_trades": int(k1_full["trades"]),
            "k1_profit_factor": float(k1_full["profit_factor"]),
            "k2_annual_return_pct": float(k2_full["annual_return_pct"]),
            "k2_total_return_pct": float(k2_full["total_return_pct"]),
            "k2_max_drawdown_pct": float(k2_full["max_drawdown_pct"]),
            "k2_win_rate_pct": float(k2_full["win_rate_pct"]),
            "k2_trades": int(k2_full["trades"]),
            "k2_profit_factor": float(k2_full["profit_factor"]),
            "k1_second_half_total_return_pct": float(k1_second["total_return_pct"]),
            "k2_second_half_total_return_pct": float(k2_second["total_return_pct"]),
            "k1_last90_total_return_pct": float(k1_last90["total_return_pct"]),
            "k2_last90_total_return_pct": float(k2_last90["total_return_pct"]),
            "k1_recent30_total_return_pct": float(k1_recent30["total_return_pct"]),
            "k2_recent30_total_return_pct": float(k2_recent30["total_return_pct"]),
        }
        row["final_score"] = (
            score_pair(k1_full, k2_full)
            + 0.8 * safe_log_return(row["k1_second_half_total_return_pct"])
            + 0.6 * safe_log_return(row["k2_second_half_total_return_pct"])
            + 0.5 * safe_log_return(row["k1_last90_total_return_pct"])
            + 0.35 * safe_log_return(row["k2_last90_total_return_pct"])
        )
        row["balanced_diagnostic_pass"] = bool(
            row["k1_total_return_pct"] > 0
            and row["k2_total_return_pct"] > 0
            and row["k1_second_half_total_return_pct"] > 0
            and row["k1_max_drawdown_pct"] >= -30.0
            and row["k2_max_drawdown_pct"] >= -35.0
            and row["k1_trades"] >= 12
            and row["k2_trades"] >= 12
        )
        finalist_rows.append(row)
    finalists = pd.DataFrame(finalist_rows).sort_values(
        ["balanced_diagnostic_pass", "final_score"], ascending=False
    )
    slices = pd.DataFrame(slice_rows)
    return finalists, slices


def pct(value: float) -> str:
    return f"{value:.2f}%"


def top_table(rows: pd.DataFrame, title: str) -> list[str]:
    lines = [
        f"### {title}",
        "",
        "| 资产 | 策略 | K+1年化 | K+1总收益 | K+1回撤 | K+1笔数 | K+2年化 | K+2总收益 | K+2回撤 | K+2笔数 | 后半段K+1 | Last90 K+1 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows.to_dict(orient="records"):
        lines.append(
            f"| `{row['asset']}` | `{row['name']}` | `{pct(float(row['k1_annual_return_pct']))}` | "
            f"`{pct(float(row['k1_total_return_pct']))}` | `{pct(float(row['k1_max_drawdown_pct']))}` | "
            f"`{int(row['k1_trades'])}` | `{pct(float(row['k2_annual_return_pct']))}` | "
            f"`{pct(float(row['k2_total_return_pct']))}` | `{pct(float(row['k2_max_drawdown_pct']))}` | "
            f"`{int(row['k2_trades'])}` | `{pct(float(row['k1_second_half_total_return_pct']))}` | "
            f"`{pct(float(row['k1_last90_total_return_pct']))}` |"
        )
    return lines


def render_markdown(
    qualities: dict[str, Any],
    ranking: pd.DataFrame,
    finalists: pd.DataFrame,
) -> str:
    btc_top = finalists.loc[finalists["asset"].eq("BTC")].head(5)
    eth_top = finalists.loc[finalists["asset"].eq("ETH")].head(5)
    strict_count = int(ranking["strict_transfer_pass"].sum())
    balanced_count = int(finalists["balanced_diagnostic_pass"].sum())
    lines = [
        f"# Binance 15m MII BTC/ETH 受约束微调搜索 {RUN_DATE}",
        "",
        f"Family：`{FAMILY}`",
        "",
        "## 结论",
        "",
        "本报告不是重新发明策略，而是在 `HYPE-15M-MII-V1.1` 的同一机制内做跨资产微调：保留 RSI 反转、MACD 方向过滤、ATR/RVOL、固定 TP/SL/hold 和下一根 open 入场，只缩放 BTC/ETH 更小波动所需的阈值。",
        "",
        f"- Stage1 共评估 `{len(ranking)}` 个 asset-config 行；全样本 K+1/K+2 strict transfer pass `{strict_count}/{len(ranking)}`。",
        f"- 对 top 配置补做前后半段、Last90 和最近 30 天后，balanced diagnostic pass `{balanced_count}/{len(finalists)}`。",
        "- 数据来自 Binance futures kline API 直接拉取，不是本仓库标准 raw/normalized 数据湖；结果只能作为迁移诊断，不能作为实盘或 paper-live promotion。",
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
    lines.extend(
        [
            "",
            "## 搜索边界",
            "",
            "- RSI：window `7/9`，low `35/40/45`，high `55/60/65`，且 high-low 至少 `15`。",
            "- Filter：side `both/long/short`；`MACD(12,26,9)` 方向过滤；`ATR96 pct` 最低门槛 `0%-0.45%`；`RVOL96` 最低门槛 `0/0.5/1.0`。",
            "- Exit：`TP=0.45%-0.90%`，`SL=0.90%-2.40%`，hold `8/16/24` 根 `15m` K。",
            f"- Exposure：固定 `{EXPOSURE:g}x`；手续费 `{COMMISSION_PER_SIDE:.4%}`/fill，滑点 `{SLIPPAGE_PER_SIDE:.4%}`/fill，round-trip `{ROUND_TRIP_COST:.4%}`；资金费未计入。",
            "",
        ]
    )
    lines.extend(top_table(btc_top, "BTC Top 5"))
    lines.append("")
    lines.extend(top_table(eth_top, "ETH Top 5"))
    lines.extend(
        [
            "",
            "## 状态",
            "",
            "即使找到样本内赚钱版本，也只能称为 `diagnostic`。下一步必须做标准数据湖复验、资金费回放、更多时间窗口、参数邻域和真实成交滑点审计。",
            "",
            "## 产物",
            "",
            f"- 脚本：`{SCRIPT_PATH}`",
            f"- Ranking CSV：`{RANKING_CSV_PATH}`",
            f"- Finalists CSV：`{FINALISTS_CSV_PATH}`",
            f"- Slices CSV：`{SLICES_CSV_PATH}`",
            f"- JSON：`{JSON_PATH}`",
        ]
    )
    return "\n".join(lines) + "\n"


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


def main() -> None:
    v1.engine.selected_trades = v1.selected_trades_live
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)

    configs = generate_configs()
    print(f"Generated {len(configs)} constrained configs")
    all_ranking: list[pd.DataFrame] = []
    all_finalists: list[pd.DataFrame] = []
    all_slices: list[pd.DataFrame] = []
    qualities: dict[str, Any] = {}
    for symbol in SYMBOLS:
        frame = fetch_fapi_klines(symbol)
        quality = data_quality(frame, symbol)
        qualities[symbol] = quality
        if not quality["quality_gate_pass"]:
            raise ValueError(f"data-quality blocker for {symbol}: {json.dumps(quality, ensure_ascii=False)}")
        context = build_context(frame)
        ranking = evaluate_stage1(symbol, context, configs)
        top_configs = [
            TransferConfig(**{key: row[key] for key in TransferConfig.__dataclass_fields__})
            for row in ranking.sort_values("score", ascending=False).head(250).to_dict(orient="records")
        ]
        finalists, slices = evaluate_slices(symbol, context, top_configs)
        all_ranking.append(ranking)
        all_finalists.append(finalists)
        all_slices.append(slices)

    ranking_df = pd.concat(all_ranking, ignore_index=True).sort_values(["asset", "score"], ascending=[True, False])
    finalists_df = pd.concat(all_finalists, ignore_index=True).sort_values(
        ["asset", "balanced_diagnostic_pass", "final_score"], ascending=[True, False, False]
    )
    slices_df = pd.concat(all_slices, ignore_index=True)
    ranking_df.to_csv(RANKING_CSV_PATH, index=False)
    finalists_df.to_csv(FINALISTS_CSV_PATH, index=False)
    slices_df.to_csv(SLICES_CSV_PATH, index=False)

    summary = {
        "family": FAMILY,
        "run_date": RUN_DATE,
        "status": "constrained_parameter_search_diagnostic_not_promoted",
        "data_source": "binance_futures_kline_api_direct",
        "target_range": {"start": START_TS.isoformat(), "end": END_TS.isoformat()},
        "costs": {
            "commission_per_fill": COMMISSION_PER_SIDE,
            "slippage_per_fill": SLIPPAGE_PER_SIDE,
            "round_trip_cost": ROUND_TRIP_COST,
            "funding": "not_included",
        },
        "search_space": {
            "rsi_windows": RSI_WINDOWS,
            "rsi_lows": RSI_LOWS,
            "rsi_highs": RSI_HIGHS,
            "sides": SIDES,
            "min_atr_pct96": MIN_ATR_PCT96,
            "min_rvol96": MIN_RVOL96,
            "take_profit_pct": TAKE_PROFIT_PCT,
            "stop_pct": STOP_PCT,
            "max_hold_bars": MAX_HOLD_BARS,
            "exposure": EXPOSURE,
        },
        "data_quality": qualities,
        "evaluated_asset_config_rows": int(len(ranking_df)),
        "strict_transfer_pass": int(ranking_df["strict_transfer_pass"].sum()),
        "balanced_diagnostic_pass": int(finalists_df["balanced_diagnostic_pass"].sum()),
        "top_finalists": finalists_df.groupby("asset", sort=False).head(10).to_dict(orient="records"),
        "outputs": {
            "script": str(SCRIPT_PATH),
            "ranking_csv": str(RANKING_CSV_PATH),
            "finalists_csv": str(FINALISTS_CSV_PATH),
            "slices_csv": str(SLICES_CSV_PATH),
            "markdown": str(MARKDOWN_PATH),
        },
    }
    JSON_PATH.write_text(
        json.dumps(json_safe(summary), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    MARKDOWN_PATH.write_text(render_markdown(qualities, ranking_df, finalists_df), encoding="utf-8")
    print(finalists_df.groupby("asset", sort=False).head(5).to_string(index=False))
    print(f"Wrote {RANKING_CSV_PATH}")
    print(f"Wrote {FINALISTS_CSV_PATH}")
    print(f"Wrote {SLICES_CSV_PATH}")
    print(f"Wrote {JSON_PATH}")
    print(f"Wrote {MARKDOWN_PATH}")


if __name__ == "__main__":
    main()
