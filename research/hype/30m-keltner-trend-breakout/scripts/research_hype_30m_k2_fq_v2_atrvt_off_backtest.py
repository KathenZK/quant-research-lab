from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from http.client import IncompleteRead
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/hype/30m-keltner-trend-breakout"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
CACHE_DIR = ROOT / "data/cache/hype_30m_k2_fq_v2_atrvt_off"
CACHE_PATH = CACHE_DIR / "HYPEUSDT_1m_closed_klines.parquet"
SUMMARY_PATH = ARTIFACT_DIR / "hype_30m_k2_fq_v2_atrvt_off_backtest_2026-07-08.json"
TRADES_PATH = ARTIFACT_DIR / "hype_30m_k2_fq_v2_atrvt_off_trades_2026-07-08.csv"

SYMBOL = "HYPEUSDT"
DISPLAY_SYMBOL = "HYPE/USDT:USDT"
BASE_URL = "https://fapi.binance.com"
KLINES_PATH = "/fapi/v1/klines"
TIME_PATH = "/fapi/v1/time"
USER_AGENT = "quant-research-lab-hype-k2-30m/0.1"

INTERVAL_MS = 60_000
M30_PER_YEAR = 365 * 24 * 2
PHASES = (0, 5, 10, 15, 20, 25)
RECENT_WINDOWS = {
    "1d": pd.Timedelta(days=1),
    "7d": pd.Timedelta(days=7),
    "1m": pd.Timedelta(days=30),
    "3m": pd.Timedelta(days=90),
    "6m": pd.Timedelta(days=180),
    "1y": pd.Timedelta(days=365),
}


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    keltner_ema: int = 10
    keltner_atr: int = 10
    keltner_mult: float = 2.0
    h1_ema_fast: int = 16
    h1_ema_slow: int = 48
    h1_slope_lag: int = 4
    leverage_atr: int = 96
    atr_target_pct: float = 0.030
    min_leverage: float = 1.0
    max_leverage: float = 3.0
    take_profit_pct: float = 0.10
    stop_loss_pct: float = 0.025
    max_hold_bars: int = 30


@dataclass(slots=True)
class Position:
    direction: int
    entry_i: int
    entry_ts: pd.Timestamp
    entry_price: float
    leverage: float
    equity_before: float
    equity_after_entry_cost: float
    tp: float
    sl: float


@dataclass(frozen=True, slots=True)
class BacktestResult:
    name: str
    phase_min: int | None
    cost_side: float
    metrics: dict[str, Any]
    slices: list[dict[str, Any]]
    trades: pd.DataFrame
    equity: pd.Series
    quality: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2025-05-30T00:00:00Z")
    parser.add_argument("--until", default="")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--timeout", type=float, default=45.0)
    return parser.parse_args()


def request_json(
    path: str,
    *,
    params: dict[str, object] | None = None,
    timeout: float = 45.0,
    attempts: int = 6,
) -> object:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{BASE_URL}{path}{query}"
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            IncompleteRead,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(min(8.0, 0.75 * 2**attempt))
    raise RuntimeError(f"Binance request failed after {attempts} attempts: {url}") from last_error


def server_time_ms(timeout: float) -> int:
    payload = request_json(TIME_PATH, timeout=timeout)
    if not isinstance(payload, dict) or "serverTime" not in payload:
        raise RuntimeError(f"Unexpected server-time payload: {payload!r}")
    return int(payload["serverTime"])


def to_ms(value: str) -> int:
    return int(pd.Timestamp(value).tz_convert("UTC").timestamp() * 1000)


def fetch_1m_klines(*, since_ms: int, until_ms: int, timeout: float) -> pd.DataFrame:
    rows: list[list[object]] = []
    cursor = since_ms
    while cursor < until_ms:
        payload = request_json(
            KLINES_PATH,
            params={
                "symbol": SYMBOL,
                "interval": "1m",
                "startTime": cursor,
                "endTime": until_ms,
                "limit": 1500,
            },
            timeout=timeout,
        )
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1][0]) + INTERVAL_MS
        if next_cursor <= cursor:
            raise RuntimeError("Binance kline pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1500:
            break
        time.sleep(0.05)
    if not rows:
        raise RuntimeError("Binance returned no 1m HYPEUSDT klines")
    frame = pd.DataFrame(
        rows,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trade_count",
            "taker_buy_volume",
            "taker_buy_quote_volume",
            "ignore",
        ],
    )
    frame["ts"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    numeric = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["vwap"] = frame["quote_volume"] / frame["volume"].replace(0.0, np.nan)
    frame["vwap"] = frame["vwap"].fillna(frame["close"])
    cutoff = pd.to_datetime(until_ms, unit="ms", utc=True)
    frame = frame.loc[frame["close_time"] < cutoff].copy()
    frame["exchange"] = "binance"
    frame["symbol"] = DISPLAY_SYMBOL
    frame["market_type"] = "perp"
    frame["timeframe"] = "1m"
    frame["source"] = "binance_futures_kline_api"
    frame["is_closed"] = True
    return (
        frame[
            [
                "ts",
                "exchange",
                "symbol",
                "market_type",
                "timeframe",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "quote_volume",
                "trade_count",
                "vwap",
                "is_closed",
                "source",
            ]
        ]
        .sort_values("ts")
        .drop_duplicates("ts", keep="last")
        .reset_index(drop=True)
    )


def load_or_fetch_1m(args: argparse.Namespace) -> pd.DataFrame:
    until_ms = to_ms(args.until) if args.until else server_time_ms(args.timeout)
    since_ms = to_ms(args.since)
    if CACHE_PATH.exists() and not args.refresh_cache:
        cached = pd.read_parquet(CACHE_PATH)
        cached["ts"] = pd.to_datetime(cached["ts"], utc=True)
        since_ts = pd.to_datetime(since_ms, unit="ms", utc=True)
        until_ts = pd.to_datetime(until_ms, unit="ms", utc=True)
        cached = cached.loc[(cached["ts"] >= since_ts) & (cached["ts"] < until_ts)]
        if not cached.empty:
            return cached.reset_index(drop=True)
    frame = fetch_1m_klines(since_ms=since_ms, until_ms=until_ms, timeout=args.timeout)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(CACHE_PATH, index=False)
    return frame


def data_quality(frame: pd.DataFrame) -> dict[str, Any]:
    ts = pd.to_datetime(frame["ts"], utc=True)
    expected = pd.date_range(ts.min(), ts.max(), freq="1min", tz="UTC")
    unique_ts = ts.drop_duplicates()
    missing = expected.difference(pd.DatetimeIndex(unique_ts))
    duplicate_rows = int(ts.duplicated().sum())
    invalid_ohlc = int(
        (
            frame["open"].isna()
            | frame["high"].isna()
            | frame["low"].isna()
            | frame["close"].isna()
            | frame["high"].lt(frame[["open", "close", "low"]].max(axis=1))
            | frame["low"].gt(frame[["open", "close", "high"]].min(axis=1))
        ).sum()
    )
    return {
        "exchange": "binance",
        "market_type": "perp",
        "symbol": DISPLAY_SYMBOL,
        "timeframe": "1m",
        "source": sorted(frame.get("source", pd.Series(["unknown"])).dropna().unique().tolist()),
        "start": str(ts.min()),
        "end": str(ts.max()),
        "rows": int(len(frame)),
        "expected_rows": int(len(expected)),
        "missing_1m_bars": int(len(missing)),
        "first_missing_1m_bars": [str(item) for item in missing[:10]],
        "duplicate_ts_rows": duplicate_rows,
        "invalid_ohlc_rows": invalid_ohlc,
        "critical_null_rows": int(frame[["open", "high", "low", "close", "volume"]].isna().any(axis=1).sum()),
    }


def aggregate_ohlcv(frame: pd.DataFrame, *, freq: str, phase_min: int, expected_rows: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    source = frame.copy()
    source["ts"] = pd.to_datetime(source["ts"], utc=True)
    source = source.sort_values("ts").set_index("ts")
    grouped = source.resample(
        freq,
        origin="epoch",
        offset=pd.Timedelta(minutes=phase_min),
        label="left",
        closed="left",
    )
    bars = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        quote_volume=("quote_volume", "sum"),
        trade_count=("trade_count", "sum"),
        minute_count=("open", "count"),
    )
    total_bins = int(len(bars))
    complete = bars.loc[bars["minute_count"].eq(expected_rows)].copy()
    complete = complete.dropna(subset=["open", "high", "low", "close"])
    quality = {
        "freq": freq,
        "phase_min": phase_min,
        "total_bins": total_bins,
        "complete_bins": int(len(complete)),
        "dropped_incomplete_bins": int(total_bins - len(complete)),
        "start": str(complete.index.min()) if not complete.empty else None,
        "end": str(complete.index.max()) if not complete.empty else None,
    }
    return complete, quality


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(alpha=2 / (window + 1), adjust=False, min_periods=window).mean()


def rma(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def true_range(frame: pd.DataFrame) -> pd.Series:
    prev_close = frame["close"].shift(1)
    return pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def build_features(b30: pd.DataFrame, h1: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    frame = b30.copy()
    tr30 = true_range(frame)
    frame["mid"] = ema(frame["close"], cfg.keltner_ema)
    frame["atr10"] = rma(tr30, cfg.keltner_atr)
    frame["upper"] = frame["mid"] + cfg.keltner_mult * frame["atr10"]
    frame["lower"] = frame["mid"] - cfg.keltner_mult * frame["atr10"]
    frame["atr96"] = rma(tr30, cfg.leverage_atr)

    htf = h1.copy()
    htf["ema_fast"] = ema(htf["close"], cfg.h1_ema_fast)
    htf["ema_slow"] = ema(htf["close"], cfg.h1_ema_slow)
    htf["slope"] = htf["ema_slow"] - htf["ema_slow"].shift(cfg.h1_slope_lag)
    htf["long_regime"] = htf["ema_fast"].gt(htf["ema_slow"]) & htf["close"].gt(htf["ema_slow"]) & htf["slope"].gt(0.0)
    htf["short_regime"] = htf["ema_fast"].lt(htf["ema_slow"]) & htf["close"].lt(htf["ema_slow"]) & htf["slope"].lt(0.0)

    h1_close_times = (htf.index + pd.Timedelta(hours=1)).to_numpy()
    b30_close_times = (frame.index + pd.Timedelta(minutes=30)).to_numpy()
    mapped = np.searchsorted(h1_close_times, b30_close_times, side="right") - 1
    long_reg = np.zeros(len(frame), dtype=bool)
    short_reg = np.zeros(len(frame), dtype=bool)
    valid = mapped >= 0
    long_values = htf["long_regime"].fillna(False).to_numpy()
    short_values = htf["short_regime"].fillna(False).to_numpy()
    long_reg[valid] = long_values[mapped[valid]]
    short_reg[valid] = short_values[mapped[valid]]
    frame["long_regime_1h"] = long_reg
    frame["short_regime_1h"] = short_reg

    frame["break_up"] = frame["close"].gt(frame["upper"])
    frame["break_down"] = frame["close"].lt(frame["lower"])
    frame["long_signal"] = frame["long_regime_1h"] & frame["break_up"] & ~frame["short_regime_1h"]
    frame["short_signal"] = frame["short_regime_1h"] & frame["break_down"] & ~frame["long_regime_1h"]
    return frame


def gross_return(direction: int, entry_price: float, exit_price: float) -> float:
    if direction == 1:
        return exit_price / entry_price - 1.0
    return 1.0 - exit_price / entry_price


def mark_equity(position: Position, price: float) -> float:
    gross = gross_return(position.direction, position.entry_price, price)
    return position.equity_after_entry_cost * (1.0 + position.leverage * gross)


def exit_equity(position: Position, exit_price: float, cost_side: float) -> float:
    gross = gross_return(position.direction, position.entry_price, exit_price)
    return position.equity_after_entry_cost * (1.0 + position.leverage * (gross - cost_side))


def run_phase(
    *,
    name: str,
    phase_min: int,
    m1: pd.DataFrame,
    cfg: StrategyConfig,
    cost_side: float,
) -> BacktestResult:
    b30, q30 = aggregate_ohlcv(m1, freq="30min", phase_min=phase_min, expected_rows=30)
    h1, q1h = aggregate_ohlcv(m1, freq="60min", phase_min=phase_min, expected_rows=60)
    features = build_features(b30, h1, cfg)

    equity = 1.0
    position: Position | None = None
    pending_direction = 0
    curve: list[tuple[pd.Timestamp, float]] = []
    trades: list[dict[str, Any]] = []

    for i, (ts, row) in enumerate(features.iterrows()):
        if pending_direction and position is None and i > 0:
            atr = float(features["atr96"].iloc[i - 1])
            entry_price = float(row["open"])
            if np.isfinite(atr) and atr > 0.0 and np.isfinite(entry_price) and entry_price > 0.0:
                raw_leverage = cfg.atr_target_pct / (atr / entry_price)
                leverage = float(np.clip(raw_leverage, cfg.min_leverage, cfg.max_leverage))
                equity_before = equity
                equity_after_entry_cost = equity_before * (1.0 - leverage * cost_side)
                if pending_direction == 1:
                    tp = entry_price * (1.0 + cfg.take_profit_pct)
                    sl = entry_price * (1.0 - cfg.stop_loss_pct)
                else:
                    tp = entry_price * (1.0 - cfg.take_profit_pct)
                    sl = entry_price * (1.0 + cfg.stop_loss_pct)
                position = Position(
                    direction=pending_direction,
                    entry_i=i,
                    entry_ts=ts,
                    entry_price=entry_price,
                    leverage=leverage,
                    equity_before=equity_before,
                    equity_after_entry_cost=equity_after_entry_cost,
                    tp=tp,
                    sl=sl,
                )
                equity = equity_after_entry_cost
            pending_direction = 0

        if position is not None:
            exit_reason: str | None = None
            exit_price: float | None = None
            if position.direction == 1:
                if float(row["low"]) <= position.sl:
                    exit_reason = "sl"
                    exit_price = position.sl
                elif float(row["high"]) >= position.tp:
                    exit_reason = "tp"
                    exit_price = position.tp
            else:
                if float(row["high"]) >= position.sl:
                    exit_reason = "sl"
                    exit_price = position.sl
                elif float(row["low"]) <= position.tp:
                    exit_reason = "tp"
                    exit_price = position.tp
            if exit_reason is None and i - position.entry_i >= cfg.max_hold_bars:
                exit_reason = "time"
                exit_price = float(row["close"])
            if exit_reason is not None and exit_price is not None:
                equity_after = exit_equity(position, exit_price, cost_side)
                trades.append(
                    {
                        "phase_min": phase_min,
                        "direction": "long" if position.direction == 1 else "short",
                        "entry_ts": position.entry_ts,
                        "exit_ts": ts,
                        "entry_price": position.entry_price,
                        "exit_price": exit_price,
                        "exit_reason": exit_reason,
                        "hold_bars": i - position.entry_i,
                        "leverage": position.leverage,
                        "gross_return_pct": gross_return(position.direction, position.entry_price, exit_price) * 100.0,
                        "net_account_return_pct": (equity_after / position.equity_before - 1.0) * 100.0,
                        "equity_before": position.equity_before,
                        "equity_after": equity_after,
                    }
                )
                equity = equity_after
                position = None

        curve_equity = mark_equity(position, float(row["close"])) if position is not None else equity
        curve.append((ts, curve_equity))

        if position is None:
            if bool(row["long_signal"]):
                pending_direction = 1
            elif bool(row["short_signal"]):
                pending_direction = -1

    equity_curve = pd.Series(dict(curve), name=name).sort_index()
    trades_frame = pd.DataFrame(trades)
    quality = {"phase_min": phase_min, "bar30": q30, "bar1h": q1h}
    metrics = compute_metrics(equity_curve, trades_frame)
    slices = compute_slices(equity_curve)
    return BacktestResult(
        name=name,
        phase_min=phase_min,
        cost_side=cost_side,
        metrics=metrics,
        slices=slices,
        trades=trades_frame,
        equity=equity_curve,
        quality=quality,
    )


def compute_metrics(equity: pd.Series, trades: pd.DataFrame) -> dict[str, Any]:
    if equity.empty:
        return {
            "return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe": 0.0,
            "trades": 0,
            "win_rate_pct": 0.0,
            "avg_leverage": 0.0,
            "worst_trade_pct": 0.0,
            "exit_counts": {},
        }
    returns = equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    sharpe = 0.0
    if not returns.empty and float(returns.std(ddof=1)) > 0.0:
        periods_per_year = inferred_periods_per_year(equity.index)
        sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(periods_per_year))
    drawdown = equity / equity.cummax() - 1.0
    if trades.empty:
        win_rate = 0.0
        avg_leverage = 0.0
        worst_trade = 0.0
        exit_counts: dict[str, int] = {}
    else:
        trade_returns = pd.to_numeric(trades["net_account_return_pct"], errors="coerce")
        win_rate = float(trade_returns.gt(0.0).mean() * 100.0)
        avg_leverage = float(pd.to_numeric(trades["leverage"], errors="coerce").mean())
        worst_trade = float(trade_returns.min())
        exit_counts = {str(key): int(value) for key, value in trades["exit_reason"].value_counts().sort_index().items()}
    return {
        "return_pct": float((equity.iloc[-1] / equity.iloc[0] - 1.0) * 100.0),
        "max_drawdown_pct": float(drawdown.min() * 100.0),
        "sharpe": sharpe,
        "trades": int(len(trades)),
        "win_rate_pct": win_rate,
        "avg_leverage": avg_leverage,
        "worst_trade_pct": worst_trade,
        "exit_counts": exit_counts,
    }


def inferred_periods_per_year(index: pd.DatetimeIndex) -> float:
    if len(index) < 3:
        return float(M30_PER_YEAR)
    deltas = index.to_series().diff().dropna().dt.total_seconds()
    median_seconds = float(deltas.median()) if not deltas.empty else 0.0
    if median_seconds <= 0.0:
        return float(M30_PER_YEAR)
    return float(365 * 24 * 60 * 60 / median_seconds)


def compute_slices(equity: pd.Series) -> list[dict[str, Any]]:
    if equity.empty:
        return []
    end = equity.index.max()
    rows: list[dict[str, Any]] = []
    for label, delta in RECENT_WINDOWS.items():
        start = end - delta
        sliced = equity.loc[equity.index >= start]
        if len(sliced) < 2:
            continue
        drawdown = sliced / sliced.cummax() - 1.0
        rows.append(
            {
                "window": label,
                "start": str(sliced.index.min()),
                "end": str(sliced.index.max()),
                "return_pct": float((sliced.iloc[-1] / sliced.iloc[0] - 1.0) * 100.0),
                "max_drawdown_pct": float(drawdown.min() * 100.0),
            }
        )
    return rows


def combine_phases(name: str, results: list[BacktestResult], cost_side: float) -> BacktestResult:
    curves = pd.concat(
        [result.equity.rename(f"phase_{result.phase_min}") for result in results],
        axis=1,
        sort=True,
    ).sort_index()
    curves = curves.ffill().fillna(1.0)
    portfolio = curves.mean(axis=1).rename(name)
    trade_frames = [result.trades for result in results if not result.trades.empty]
    trades = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    quality = {"phase_qualities": {str(result.phase_min): result.quality for result in results}}
    return BacktestResult(
        name=name,
        phase_min=None,
        cost_side=cost_side,
        metrics=compute_metrics(portfolio, trades),
        slices=compute_slices(portfolio),
        trades=trades,
        equity=portfolio,
        quality=quality,
    )


def run_suite(m1: pd.DataFrame, *, cost_side: float, cfg: StrategyConfig) -> tuple[BacktestResult, BacktestResult, list[BacktestResult]]:
    cost_bps = round(cost_side * 10_000)
    phase_results = [
        run_phase(name=f"phase_{phase:02d}_cost_{cost_bps}bps", phase_min=phase, m1=m1, cfg=cfg, cost_side=cost_side)
        for phase in PHASES
    ]
    single = phase_results[0]
    multi = combine_phases(f"six_phase_cost_{cost_bps}bps", phase_results, cost_side)
    return single, multi, phase_results


def serializable_result(result: BacktestResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "phase_min": result.phase_min,
        "cost_side": result.cost_side,
        "metrics": result.metrics,
        "slices": result.slices,
        "quality": result.quality,
        "last_trades": result.trades.tail(8).to_dict(orient="records") if not result.trades.empty else [],
    }


def print_result(result: BacktestResult) -> None:
    metrics = result.metrics
    exits = metrics["exit_counts"]
    print(
        f"{result.name:>24}  ret {metrics['return_pct']:>10.2f}%  "
        f"mdd {metrics['max_drawdown_pct']:>7.2f}%  sharpe {metrics['sharpe']:>5.2f}  "
        f"trades {metrics['trades']:>4}  win {metrics['win_rate_pct']:>6.2f}%  "
        f"avg_lev {metrics['avg_leverage']:>4.2f}  worst {metrics['worst_trade_pct']:>6.2f}%  exits {exits}"
    )


def main() -> None:
    args = parse_args()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = StrategyConfig()
    m1 = load_or_fetch_1m(args)
    quality = data_quality(m1)
    if quality["missing_1m_bars"] or quality["duplicate_ts_rows"] or quality["invalid_ohlc_rows"] or quality["critical_null_rows"]:
        print("DATA QUALITY WARNING:", quality)

    results: list[BacktestResult] = []
    all_phase_results: list[BacktestResult] = []
    for cost_side in (0.0006, 0.0015):
        single, multi, phase_results = run_suite(m1, cost_side=cost_side, cfg=cfg)
        results.extend([single, multi])
        all_phase_results.extend(phase_results)

    summary = {
        "strategy_family": "HYPE-30M-Keltner-Trend-Breakout",
        "strategy_id": "K2-FQ-V2-ATRVT-OFF",
        "source_spec": "/Users/ZK/Downloads/2-k2-fq-v2-atrvt-off-20260707.md",
        "data_quality": quality,
        "assumptions": {
            "data": "Binance USDM HYPEUSDT 1m closed klines, resampled to complete 30m and 1h bars.",
            "phase_mapping": "For shifted phases, both 30m signal bars and 1h regime bars use the same minute offset.",
            "execution": "Signal on 30m close, enter next 30m open, TP/SL checked from entry bar, SL wins same-bar conflicts, hold=30 exits on bar close.",
            "costs": "Runs use 6 bps/side and 15 bps/side; funding is not included.",
            "portfolio": "Six-phase portfolio is equal-weight independent sleeves, using the mean of phase equity curves.",
        },
        "config": asdict(cfg),
        "headline_results": [serializable_result(result) for result in results],
        "phase_results": [serializable_result(result) for result in all_phase_results],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    trade_frames = []
    for result in all_phase_results:
        if not result.trades.empty:
            trade_frames.append(result.trades.assign(run=result.name, cost_side=result.cost_side))
    if trade_frames:
        pd.concat(trade_frames, ignore_index=True).to_csv(TRADES_PATH, index=False)

    print(f"data: {quality['start']} ~ {quality['end']} rows={quality['rows']} missing_1m={quality['missing_1m_bars']}")
    for result in results:
        print_result(result)
    print(f"summary -> {SUMMARY_PATH}")
    print(f"trades  -> {TRADES_PATH}")


if __name__ == "__main__":
    main()
