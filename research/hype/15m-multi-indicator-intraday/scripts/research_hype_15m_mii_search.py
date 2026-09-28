from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from strategy_lab.data import DataLakeLayout, DuckDBWarehouse, MarketType
from strategy_lab.data.settings import load_settings

SYMBOL = "HYPEUSDT"
DISPLAY_SYMBOL = "HYPE/USDT:USDT"
INTERVAL = "15m"
INTERVAL_MS = 15 * 60 * 1000
FAPI_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
DEFAULT_START = datetime(2025, 5, 1, tzinfo=timezone.utc)

COMMISSION_PER_SIDE = 0.001
SLIPPAGE_PER_SIDE = 0.0004
ROUND_TRIP_COST = 2 * (COMMISSION_PER_SIDE + SLIPPAGE_PER_SIDE)

TARGET_ANNUAL_RETURN_PCT = 2_000.0
TARGET_ANNUAL_EQUITY_MULTIPLE = 20.0
TARGET_MAX_DRAWDOWN_PCT = -20.0
TARGET_WIN_RATE_PCT = 70.0
PREFERRED_MIN_TRADES_PER_DAY = 0.75
PREFERRED_MAX_TRADES_PER_DAY = 2.25


@dataclass(frozen=True, slots=True)
class SignalSpec:
    name: str
    kind: str
    fast: int = 0
    slow: int = 0
    signal: int = 0
    window: int = 0
    lookback: int = 0
    low: float = 0.0
    high: float = 0.0
    k: float = 0.0
    touch_pct: float = 0.0


@dataclass(frozen=True, slots=True)
class ExitSpec:
    kind: str
    stop_pct: float
    max_hold_bars: int
    take_profit_pct: float | None = None
    activation_pct: float | None = None
    trail_pct: float | None = None

    @property
    def name(self) -> str:
        if self.kind == "fixed":
            return (
                f"fixed_tp{pct_slug(self.take_profit_pct)}"
                f"_sl{pct_slug(self.stop_pct)}_hold{self.max_hold_bars}"
            )
        return (
            f"trail_act{pct_slug(self.activation_pct)}"
            f"_trail{pct_slug(self.trail_pct)}"
            f"_sl{pct_slug(self.stop_pct)}_hold{self.max_hold_bars}"
        )


@dataclass(frozen=True, slots=True)
class FilterSpec:
    side: str = "both"
    min_adx14: float = 0.0
    min_rvol96: float = 0.0
    min_h1_dir_spread: float = -99.0
    min_h4_dir_spread: float = -99.0
    min_dir_ret16: float = -99.0
    min_dir_ret48: float = -99.0
    min_dir_ret96: float = -99.0
    min_dir_macd: float = -99.0
    min_dir_rsi14: float = 0.0
    max_dir_rsi14: float = 100.0
    min_atr_pct96: float = 0.0
    max_atr_pct96: float = 99.0
    max_atr_ratio96_672: float = 99.0
    min_previous_signal_age: float = 0.0
    max_churn192: float = 999.0
    cooldown_bars: int = 0

    @property
    def name(self) -> str:
        parts: list[str] = []
        if self.side != "both":
            parts.append(self.side)
        if self.min_adx14:
            parts.append(f"adx{value_slug(self.min_adx14)}")
        if self.min_rvol96:
            parts.append(f"rvol{value_slug(self.min_rvol96)}")
        if self.min_h1_dir_spread > -90:
            parts.append(f"h1{pct_slug(self.min_h1_dir_spread)}")
        if self.min_h4_dir_spread > -90:
            parts.append(f"h4{pct_slug(self.min_h4_dir_spread)}")
        if self.min_dir_ret16 > -90:
            parts.append(f"ret16{pct_slug(self.min_dir_ret16)}")
        if self.min_dir_ret48 > -90:
            parts.append(f"ret48{pct_slug(self.min_dir_ret48)}")
        if self.min_dir_ret96 > -90:
            parts.append(f"ret96{pct_slug(self.min_dir_ret96)}")
        if self.min_dir_macd > -90:
            parts.append(f"macd{pct_slug(self.min_dir_macd)}")
        if self.min_dir_rsi14 > 0 or self.max_dir_rsi14 < 100:
            parts.append(
                f"rsi{value_slug(self.min_dir_rsi14)}to"
                f"{value_slug(self.max_dir_rsi14)}"
            )
        if self.min_atr_pct96 or self.max_atr_pct96 < 90:
            parts.append(
                f"atr{pct_slug(self.min_atr_pct96)}to"
                f"{pct_slug(self.max_atr_pct96)}"
            )
        if self.max_atr_ratio96_672 < 90:
            parts.append(f"atrR{value_slug(self.max_atr_ratio96_672)}")
        if self.min_previous_signal_age:
            parts.append(f"age{value_slug(self.min_previous_signal_age)}")
        if self.max_churn192 < 900:
            parts.append(f"churn{value_slug(self.max_churn192)}")
        if self.cooldown_bars:
            parts.append(f"cool{self.cooldown_bars}")
        return "base" if not parts else "_".join(parts)


@dataclass(slots=True)
class SignalState:
    spec: SignalSpec
    signal_i: np.ndarray
    directions: np.ndarray
    previous_signal_age: np.ndarray
    churn192: np.ndarray


@dataclass(slots=True)
class MarketArrays:
    ts: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    adx14: np.ndarray
    rvol96: np.ndarray
    ret16: np.ndarray
    ret48: np.ndarray
    ret96: np.ndarray
    h1_spread: np.ndarray
    h4_spread: np.ndarray
    macd_hist: np.ndarray
    rsi14: np.ndarray
    atr_pct96: np.ndarray
    atr_ratio96_672: np.ndarray


@dataclass(slots=True)
class EventTrade:
    signal_i: int
    entry_i: int
    exit_i: int
    direction: int
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_price: float
    exit_price: float
    raw_return: float
    min_path_return: float
    max_path_return: float
    bars_held: int
    exit_reason: str
    signal_name: str
    signal_kind: str
    adx14: float
    rvol96: float
    h1_dir_spread: float
    h4_dir_spread: float
    dir_ret16: float
    dir_ret48: float
    dir_ret96: float
    dir_macd: float
    dir_rsi14: float
    atr_pct96: float
    atr_ratio96_672: float
    previous_signal_age: float
    churn192: float


@dataclass(slots=True)
class SearchResult:
    name: str
    signal_name: str
    signal_kind: str
    exit_name: str
    exit_kind: str
    filter_name: str
    exposure: float
    final_equity: float
    total_return_pct: float
    annual_return_pct: float
    annual_equity_multiple: float
    max_drawdown_pct: float
    win_rate_pct: float
    trades: int
    trades_per_day: float
    profit_factor: float
    avg_trade_pct: float
    median_trade_pct: float
    worst_trade_pct: float
    stop_trades: int
    tp_trades: int
    trail_trades: int
    max_hold_trades: int
    score: float
    target_return_pass: bool
    target_equity_multiple_pass: bool
    target_drawdown_pass: bool
    target_win_rate_pass: bool
    frequency_preference_pass: bool
    meets_core_target: bool
    meets_full_preference: bool
    start_ts: str
    end_ts: str


def pct_slug(value: float | None) -> str:
    if value is None:
        return "na"
    return str(round(value * 10_000, 4)).replace(".", "p").replace("-", "m")


def value_slug(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(round(value, 6)).replace(".", "p").replace("-", "m")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search Binance HYPEUSDT 15m multi-indicator intraday strategies."
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("data/cache/hypeusdt_15m_fapi.csv"),
        help="Legacy compatibility path; trusted research loads ignore it.",
    )
    parser.add_argument(
        "--refresh-data",
        action="store_true",
        help="Legacy compatibility option; trusted research loads ignore it.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("research/hype/15m-multi-indicator-intraday/artifacts"),
    )
    parser.add_argument("--stage1-keep", type=int, default=600)
    parser.add_argument("--stage2-keep", type=int, default=300)
    parser.add_argument("--stage2-signal-keep", type=int, default=40)
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--max-signals", type=int, default=0)
    return parser.parse_args()


def fetch_fapi_klines(cache_path: Path) -> pd.DataFrame:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    start = int(DEFAULT_START.timestamp() * 1000)
    end = int(pd.Timestamp.now(tz="UTC").floor("15min").timestamp() * 1000)
    rows: list[list[object]] = []
    while start < end:
        params = urlencode(
            {
                "symbol": SYMBOL,
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
        raise RuntimeError("Binance FAPI returned no HYPEUSDT rows.")

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
    frame = frame[["ts", "open", "high", "low", "close", "volume"]].copy()
    frame["ts"] = pd.to_datetime(frame["ts"], unit="ms", utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna().drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    frame.to_csv(cache_path, index=False)
    return frame


def load_data(cache_path: Path, *, refresh: bool) -> tuple[pd.DataFrame, dict[str, object]]:
    # Parameters remain for CLI compatibility. Refreshing/ingesting data is a
    # separate producer concern; research always consumes the trusted lake.
    del refresh
    warehouse = DuckDBWarehouse(
        DataLakeLayout.from_settings(load_settings(None))
    )
    trusted = warehouse.load_trusted_ohlcv(
        exchange="binance",
        market_type=MarketType.PERP,
        symbol=DISPLAY_SYMBOL,
        timeframe=INTERVAL,
    )
    frame = trusted[
        ["ts", "open", "high", "low", "close", "volume"]
    ].reset_index(drop=True)
    frame.attrs.update(trusted.attrs)
    metadata = {
        "symbol": DISPLAY_SYMBOL,
        "timeframe": INTERVAL,
        "source": "trusted_normalized_data_lake",
        "legacy_cache_argument": str(cache_path),
        "rows": int(len(frame)),
        "first_ts": str(frame["ts"].min()),
        "last_ts": str(frame["ts"].max()),
        "gap_count": 0,
        "ohlcv_audit": trusted.attrs.get("ohlcv_audit", {}),
        "source_counts": trusted.attrs.get("source_counts", {}),
        "commission_per_side": COMMISSION_PER_SIDE,
        "slippage_per_side": SLIPPAGE_PER_SIDE,
        "round_trip_cost": ROUND_TRIP_COST,
    }
    return frame, metadata


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    previous_close = close.shift(1)
    return pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)


def rsi(close: pd.Series, window: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100 - 100 / (1 + rs)


def adx_di(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    tr = true_range(high, low, close)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=high.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=high.index,
    )
    atr = tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    plus_di = (
        100
        * plus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
        / atr.replace(0.0, np.nan)
    )
    minus_di = (
        100
        * minus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
        / atr.replace(0.0, np.nan)
    )
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx = dx.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    return adx, plus_di, minus_di


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std(ddof=0)
    return (series - mean) / std.replace(0.0, np.nan)


def add_htf_features(frame: pd.DataFrame, rule: str, prefix: str) -> pd.DataFrame:
    ohlcv = (
        frame.set_index("ts")[["open", "high", "low", "close", "volume"]]
        .resample(rule, label="left", closed="left")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )
    htf = pd.DataFrame(index=ohlcv.index)
    htf[f"{prefix}_ema24"] = ohlcv.close.ewm(
        span=24,
        adjust=False,
        min_periods=24,
    ).mean()
    htf[f"{prefix}_ema96"] = ohlcv.close.ewm(
        span=96,
        adjust=False,
        min_periods=96,
    ).mean()
    htf[f"{prefix}_spread"] = (
        htf[f"{prefix}_ema24"] / htf[f"{prefix}_ema96"].replace(0.0, np.nan) - 1
    )
    htf[f"{prefix}_ret12"] = ohlcv.close.pct_change(12)
    aligned = htf.shift(1).reindex(pd.DatetimeIndex(frame.ts), method="ffill")
    return aligned.reset_index(drop=True)


def add_features(frame: pd.DataFrame, ema_spans: list[int]) -> pd.DataFrame:
    enriched = frame.sort_values("ts").drop_duplicates("ts").reset_index(drop=True).copy()
    close = enriched["close"].astype("float64")
    high = enriched["high"].astype("float64")
    low = enriched["low"].astype("float64")
    volume = enriched["volume"].astype("float64")

    for span in sorted(set(ema_spans + [21, 55, 96, 384])):
        enriched[f"ema{span}"] = close.ewm(span=span, adjust=False, min_periods=span).mean()

    for window in (16, 48, 96, 192):
        enriched[f"ret{window}"] = close.pct_change(window)
    for window in (48, 96, 192):
        enriched[f"rvol{window}"] = (
            volume / volume.rolling(window, min_periods=window).mean().replace(0.0, np.nan)
        )

    tr = true_range(high, low, close)
    for window in (14, 48, 96, 336, 672):
        enriched[f"atr{window}"] = tr.rolling(window, min_periods=window).mean()
        enriched[f"atr_pct{window}"] = enriched[f"atr{window}"] / close.replace(0.0, np.nan)
    enriched["atr_ratio96_672"] = enriched["atr_pct96"] / enriched[
        "atr_pct672"
    ].replace(0.0, np.nan)

    enriched["adx14"], enriched["pdi14"], enriched["mdi14"] = adx_di(high, low, close, 14)
    enriched["adx28"], enriched["pdi28"], enriched["mdi28"] = adx_di(high, low, close, 28)
    for window in (7, 14, 21):
        enriched[f"rsi{window}"] = rsi(close, window)

    for fast, slow, signal in macd_sets():
        macd = close.ewm(span=fast, adjust=False, min_periods=fast).mean() - close.ewm(
            span=slow,
            adjust=False,
            min_periods=slow,
        ).mean()
        enriched[f"macd_{fast}_{slow}_{signal}"] = macd
        enriched[f"macd_{fast}_{slow}_{signal}_signal"] = macd.ewm(
            span=signal,
            adjust=False,
            min_periods=signal,
        ).mean()
        enriched[f"macd_{fast}_{slow}_{signal}_hist"] = (
            enriched[f"macd_{fast}_{slow}_{signal}"]
            - enriched[f"macd_{fast}_{slow}_{signal}_signal"]
        )

    for window in (20, 48, 96):
        mid = close.rolling(window, min_periods=window).mean()
        std = close.rolling(window, min_periods=window).std(ddof=0)
        enriched[f"bb_mid{window}"] = mid
        enriched[f"bb_std{window}"] = std
        enriched[f"bb_width{window}"] = 4 * std / mid.replace(0.0, np.nan)
        enriched[f"bb_width_z{window}"] = rolling_zscore(enriched[f"bb_width{window}"], 192)

    for window in (24, 48, 96, 192, 384):
        enriched[f"donchian_high{window}"] = high.shift(1).rolling(
            window,
            min_periods=window,
        ).max()
        enriched[f"donchian_low{window}"] = low.shift(1).rolling(
            window,
            min_periods=window,
        ).min()

    htf = pd.concat(
        [add_htf_features(enriched, "1h", "h1"), add_htf_features(enriched, "4h", "h4")],
        axis=1,
    )
    enriched = pd.concat([enriched, htf], axis=1)
    return enriched


def ema_pairs() -> list[tuple[int, int]]:
    fast_spans = [5, 8, 13, 21, 34, 55, 89, 144]
    slow_spans = [21, 34, 55, 89, 144, 233, 377, 610]
    return [(fast, slow) for fast in fast_spans for slow in slow_spans if slow > fast * 1.55]


def macd_sets() -> list[tuple[int, int, int]]:
    return [(8, 21, 5), (12, 26, 9), (21, 55, 9), (34, 89, 13)]


def signal_specs() -> list[SignalSpec]:
    specs: list[SignalSpec] = []
    for fast, slow in ema_pairs():
        specs.append(
            SignalSpec(
                name=f"ema_cross_f{fast}_s{slow}",
                kind="ema_cross",
                fast=fast,
                slow=slow,
            )
        )
    for fast, slow, signal in macd_sets():
        specs.append(
            SignalSpec(
                name=f"macd_zero_f{fast}_s{slow}_sig{signal}",
                kind="macd_zero",
                fast=fast,
                slow=slow,
                signal=signal,
            )
        )
        specs.append(
            SignalSpec(
                name=f"macd_signal_f{fast}_s{slow}_sig{signal}",
                kind="macd_signal",
                fast=fast,
                slow=slow,
                signal=signal,
            )
        )
    for window in (24, 48, 96, 192, 384):
        specs.append(
            SignalSpec(
                name=f"donchian_break_w{window}",
                kind="donchian_break",
                window=window,
            )
        )
    for window, low, high in product((7, 14, 21), (20.0, 30.0, 40.0), (60.0, 70.0, 80.0)):
        if low >= 50 or high <= 50 or high - low < 20:
            continue
        specs.append(
            SignalSpec(
                name=f"rsi_reversal_w{window}_lo{value_slug(low)}_hi{value_slug(high)}",
                kind="rsi_reversal",
                window=window,
                low=low,
                high=high,
            )
        )
    for window, k in product((20, 48, 96), (1.5, 2.0, 2.5)):
        specs.append(
            SignalSpec(
                name=f"bb_reversion_w{window}_k{value_slug(k)}",
                kind="bb_reversion",
                window=window,
                k=k,
            )
        )
        specs.append(
            SignalSpec(
                name=f"bb_breakout_w{window}_k{value_slug(k)}",
                kind="bb_breakout",
                window=window,
                k=k,
            )
        )
    for fast, slow, touch_pct in product((21, 34, 55), (96, 144, 233), (0.006, 0.012, 0.02)):
        if slow <= fast * 1.55:
            continue
        specs.append(
            SignalSpec(
                name=(
                    f"ema_pullback_f{fast}_s{slow}"
                    f"_touch{pct_slug(touch_pct)}"
                ),
                kind="ema_pullback",
                fast=fast,
                slow=slow,
                touch_pct=touch_pct,
                lookback=16,
            )
        )
    for window in (20, 48, 96):
        specs.append(
            SignalSpec(
                name=f"squeeze_release_w{window}",
                kind="squeeze_release",
                window=window,
            )
        )
    return specs


def coarse_exit_specs() -> list[ExitSpec]:
    specs: list[ExitSpec] = []
    for take_profit_pct, stop_pct, max_hold_bars in product(
        [0.006, 0.012, 0.026, 0.05],
        [0.005, 0.011, 0.022],
        [8, 32, 128],
    ):
        specs.append(
            ExitSpec(
                kind="fixed",
                take_profit_pct=take_profit_pct,
                stop_pct=stop_pct,
                max_hold_bars=max_hold_bars,
            )
        )
    for activation_pct, trail_pct, stop_pct, max_hold_bars in product(
        [0.01, 0.024, 0.05],
        [0.005, 0.012],
        [0.008, 0.018],
        [32, 128],
    ):
        specs.append(
            ExitSpec(
                kind="trailing",
                activation_pct=activation_pct,
                trail_pct=trail_pct,
                stop_pct=stop_pct,
                max_hold_bars=max_hold_bars,
            )
        )
    return specs


def full_exit_specs() -> list[ExitSpec]:
    specs: list[ExitSpec] = []
    for take_profit_pct, stop_pct, max_hold_bars in product(
        [0.004, 0.006, 0.009, 0.012, 0.018, 0.026, 0.04, 0.06],
        [0.0035, 0.005, 0.008, 0.012, 0.018, 0.028],
        [4, 8, 16, 32, 64],
    ):
        specs.append(
            ExitSpec(
                kind="fixed",
                take_profit_pct=take_profit_pct,
                stop_pct=stop_pct,
                max_hold_bars=max_hold_bars,
            )
        )
    for activation_pct, trail_pct, stop_pct, max_hold_bars in product(
        [0.01, 0.024, 0.04],
        [0.005, 0.012],
        [0.008, 0.018],
        [16, 64],
    ):
        specs.append(
            ExitSpec(
                kind="trailing",
                activation_pct=activation_pct,
                trail_pct=trail_pct,
                stop_pct=stop_pct,
                max_hold_bars=max_hold_bars,
            )
        )
    return specs


def filter_specs() -> list[FilterSpec]:
    specs: list[FilterSpec] = [FilterSpec()]
    atr_bands = [(0.0, 99.0), (0.0035, 0.04), (0.006, 0.028), (0.009, 0.035)]
    rsi_bands = [(0.0, 100.0), (42.0, 82.0), (48.0, 78.0), (52.0, 88.0)]
    for (
        side,
        min_adx14,
        min_rvol96,
        min_h1,
        min_h4,
        min_ret48,
        min_macd,
        rsi_band,
        atr_band,
        max_atr_ratio,
        age,
        churn,
        cooldown,
    ) in product(
        ["both", "long", "short"],
        [0.0, 16.0, 22.0, 28.0, 34.0],
        [0.0, 0.75, 1.0, 1.3],
        [-99.0, 0.0, 0.0015, 0.004],
        [-99.0, 0.0, 0.002],
        [-99.0, -0.004, 0.0, 0.006],
        [-99.0, 0.0],
        rsi_bands,
        atr_bands,
        [99.0, 2.2, 1.6, 1.2],
        [0.0, 4.0, 16.0, 48.0],
        [999.0, 8.0, 4.0],
        [0, 4, 12, 24],
    ):
        active_filters = sum(
            [
                side != "both",
                min_adx14 > 0,
                min_rvol96 > 0,
                min_h1 > -90,
                min_h4 > -90,
                min_ret48 > -90,
                min_macd > -90,
                rsi_band != (0.0, 100.0),
                atr_band != (0.0, 99.0),
                max_atr_ratio < 90,
                age > 0,
                churn < 900,
                cooldown > 0,
            ]
        )
        if active_filters > 2:
            continue
        specs.append(
            FilterSpec(
                side=side,
                min_adx14=min_adx14,
                min_rvol96=min_rvol96,
                min_h1_dir_spread=min_h1,
                min_h4_dir_spread=min_h4,
                min_dir_ret48=min_ret48,
                min_dir_macd=min_macd,
                min_dir_rsi14=rsi_band[0],
                max_dir_rsi14=rsi_band[1],
                min_atr_pct96=atr_band[0],
                max_atr_pct96=atr_band[1],
                max_atr_ratio96_672=max_atr_ratio,
                min_previous_signal_age=age,
                max_churn192=churn,
                cooldown_bars=cooldown,
            )
        )
    seen: set[str] = set()
    unique: list[FilterSpec] = []
    for spec in specs:
        if spec.name in seen:
            continue
        seen.add(spec.name)
        unique.append(spec)
    return unique


def build_market_arrays(features: pd.DataFrame) -> MarketArrays:
    return MarketArrays(
        ts=features["ts"].array.to_numpy(),
        open=features["open"].to_numpy("float64"),
        high=features["high"].to_numpy("float64"),
        low=features["low"].to_numpy("float64"),
        adx14=features["adx14"].to_numpy("float64"),
        rvol96=features["rvol96"].to_numpy("float64"),
        ret16=features["ret16"].to_numpy("float64"),
        ret48=features["ret48"].to_numpy("float64"),
        ret96=features["ret96"].to_numpy("float64"),
        h1_spread=features["h1_spread"].to_numpy("float64"),
        h4_spread=features["h4_spread"].to_numpy("float64"),
        macd_hist=features["macd_12_26_9_hist"].to_numpy("float64"),
        rsi14=features["rsi14"].to_numpy("float64"),
        atr_pct96=features["atr_pct96"].to_numpy("float64"),
        atr_ratio96_672=features["atr_ratio96_672"].to_numpy("float64"),
    )


def signal_state(features: pd.DataFrame, spec: SignalSpec) -> SignalState:
    close = features["close"].to_numpy("float64")
    high = features["high"].to_numpy("float64")
    low = features["low"].to_numpy("float64")
    n = len(features)
    signal = np.zeros(n, dtype=np.int8)

    if spec.kind == "ema_cross":
        fast = features[f"ema{spec.fast}"].to_numpy("float64")
        slow = features[f"ema{spec.slow}"].to_numpy("float64")
        spread = fast / slow - 1
        sign = np.sign(spread)
        previous = np.r_[np.nan, sign[:-1]]
        signal[(sign > 0) & (previous <= 0) & np.isfinite(spread)] = 1
        signal[(sign < 0) & (previous >= 0) & np.isfinite(spread)] = -1
    elif spec.kind == "macd_zero":
        macd = features[f"macd_{spec.fast}_{spec.slow}_{spec.signal}"].to_numpy("float64")
        previous = np.r_[np.nan, macd[:-1]]
        signal[(macd > 0) & (previous <= 0)] = 1
        signal[(macd < 0) & (previous >= 0)] = -1
    elif spec.kind == "macd_signal":
        hist = features[f"macd_{spec.fast}_{spec.slow}_{spec.signal}_hist"].to_numpy(
            "float64"
        )
        previous = np.r_[np.nan, hist[:-1]]
        signal[(hist > 0) & (previous <= 0)] = 1
        signal[(hist < 0) & (previous >= 0)] = -1
    elif spec.kind == "donchian_break":
        hi = features[f"donchian_high{spec.window}"].to_numpy("float64")
        lo = features[f"donchian_low{spec.window}"].to_numpy("float64")
        prev_close = np.r_[np.nan, close[:-1]]
        signal[(close > hi) & (prev_close <= hi)] = 1
        signal[(close < lo) & (prev_close >= lo)] = -1
    elif spec.kind == "rsi_reversal":
        values = features[f"rsi{spec.window}"].to_numpy("float64")
        previous = np.r_[np.nan, values[:-1]]
        signal[(values > spec.low) & (previous <= spec.low)] = 1
        signal[(values < spec.high) & (previous >= spec.high)] = -1
    elif spec.kind in {"bb_reversion", "bb_breakout"}:
        mid = features[f"bb_mid{spec.window}"].to_numpy("float64")
        std = features[f"bb_std{spec.window}"].to_numpy("float64")
        upper = mid + spec.k * std
        lower = mid - spec.k * std
        prev_close = np.r_[np.nan, close[:-1]]
        if spec.kind == "bb_reversion":
            signal[(close > lower) & (prev_close <= lower)] = 1
            signal[(close < upper) & (prev_close >= upper)] = -1
        else:
            signal[(close > upper) & (prev_close <= upper)] = 1
            signal[(close < lower) & (prev_close >= lower)] = -1
    elif spec.kind == "ema_pullback":
        fast = features[f"ema{spec.fast}"].to_numpy("float64")
        slow = features[f"ema{spec.slow}"].to_numpy("float64")
        trend_long = fast > slow
        trend_short = fast < slow
        touch_long = low <= fast * (1 + spec.touch_pct)
        touch_short = high >= fast * (1 - spec.touch_pct)
        recent_touch_long = (
            pd.Series(touch_long).shift(1).rolling(spec.lookback, min_periods=1).max()
        ).fillna(False).to_numpy(bool)
        recent_touch_short = (
            pd.Series(touch_short).shift(1).rolling(spec.lookback, min_periods=1).max()
        ).fillna(False).to_numpy(bool)
        prev_close = np.r_[np.nan, close[:-1]]
        signal[trend_long & recent_touch_long & (close > fast) & (prev_close <= fast)] = 1
        signal[trend_short & recent_touch_short & (close < fast) & (prev_close >= fast)] = -1
    elif spec.kind == "squeeze_release":
        width_z = features[f"bb_width_z{spec.window}"].to_numpy("float64")
        mid = features[f"bb_mid{spec.window}"].to_numpy("float64")
        recent_squeeze = (
            pd.Series(width_z < -0.8).shift(1).rolling(48, min_periods=1).max()
        ).fillna(False).to_numpy(bool)
        ret16 = features["ret16"].to_numpy("float64")
        signal[recent_squeeze & (close > mid) & (ret16 > 0)] = 1
        signal[recent_squeeze & (close < mid) & (ret16 < 0)] = -1
        same_as_previous = signal == np.r_[0, signal[:-1]]
        signal[same_as_previous] = 0
    else:
        raise ValueError(f"unsupported signal kind: {spec.kind}")

    signal_i = np.flatnonzero(signal != 0)
    directions = signal[signal_i].astype(np.int8)
    previous_signal_age = np.full(n, np.nan)
    last_signal = None
    for idx in signal_i:
        if last_signal is not None:
            previous_signal_age[idx] = idx - last_signal
        last_signal = idx
    churn192 = pd.Series((signal != 0).astype(float)).shift(1).rolling(
        192,
        min_periods=1,
    ).sum()
    return SignalState(
        spec=spec,
        signal_i=signal_i,
        directions=directions,
        previous_signal_age=previous_signal_age,
        churn192=churn192.to_numpy("float64"),
    )


def finite(value: float, default: float = 0.0) -> float:
    return float(value) if np.isfinite(value) else default


def simulate_trades(
    market: MarketArrays,
    state: SignalState,
    exit_spec: ExitSpec,
) -> list[EventTrade]:
    if len(state.signal_i) == 0:
        return []

    trades: list[EventTrade] = []
    n = len(market.open)
    for signal_idx, direction in zip(state.signal_i, state.directions, strict=False):
        entry_i = int(signal_idx + 1)
        if entry_i >= n - 1:
            continue
        forced_exit_i = min(entry_i + exit_spec.max_hold_bars, n - 1)
        if forced_exit_i <= entry_i:
            continue

        direction = int(direction)
        entry_price = float(market.open[entry_i])
        stop_price = entry_price * (1 - direction * exit_spec.stop_pct)
        take_profit_price = None
        if exit_spec.kind == "fixed":
            take_profit_price = entry_price * (1 + direction * float(exit_spec.take_profit_pct))

        trail_stop: float | None = None
        best_price = entry_price
        min_path = 0.0
        max_path = 0.0
        exit_i = forced_exit_i
        exit_price = float(market.open[forced_exit_i])
        exit_reason = "max_hold"

        for i in range(entry_i, forced_exit_i + 1):
            high = float(market.high[i])
            low = float(market.low[i])
            if direction == 1:
                min_path = min(min_path, low / entry_price - 1)
                max_path = max(max_path, high / entry_price - 1)
                if low <= stop_price:
                    exit_i = i
                    exit_price = stop_price
                    exit_reason = "stop_loss"
                    break
                if trail_stop is not None and low <= trail_stop:
                    exit_i = i
                    exit_price = trail_stop
                    exit_reason = "trailing_stop"
                    break
                if take_profit_price is not None and high >= take_profit_price:
                    exit_i = i
                    exit_price = take_profit_price
                    exit_reason = "take_profit"
                    break
                if exit_spec.kind == "trailing":
                    best_price = max(best_price, high)
                    if best_price / entry_price - 1 >= float(exit_spec.activation_pct):
                        candidate = best_price * (1 - float(exit_spec.trail_pct))
                        trail_stop = candidate if trail_stop is None else max(trail_stop, candidate)
            else:
                min_path = min(min_path, entry_price / high - 1)
                max_path = max(max_path, entry_price / low - 1)
                if high >= stop_price:
                    exit_i = i
                    exit_price = stop_price
                    exit_reason = "stop_loss"
                    break
                if trail_stop is not None and high >= trail_stop:
                    exit_i = i
                    exit_price = trail_stop
                    exit_reason = "trailing_stop"
                    break
                if take_profit_price is not None and low <= take_profit_price:
                    exit_i = i
                    exit_price = take_profit_price
                    exit_reason = "take_profit"
                    break
                if exit_spec.kind == "trailing":
                    best_price = min(best_price, low)
                    if entry_price / best_price - 1 >= float(exit_spec.activation_pct):
                        candidate = best_price * (1 + float(exit_spec.trail_pct))
                        trail_stop = candidate if trail_stop is None else min(trail_stop, candidate)

        raw_return = direction * (exit_price / entry_price - 1)
        signal_i = int(signal_idx)
        trades.append(
            EventTrade(
                signal_i=signal_i,
                entry_i=entry_i,
                exit_i=int(exit_i),
                direction=direction,
                entry_ts=pd.Timestamp(market.ts[entry_i]),
                exit_ts=pd.Timestamp(market.ts[exit_i]),
                entry_price=entry_price,
                exit_price=float(exit_price),
                raw_return=float(raw_return),
                min_path_return=float(min_path),
                max_path_return=float(max_path),
                bars_held=int(max(exit_i - entry_i, 0)),
                exit_reason=exit_reason,
                signal_name=state.spec.name,
                signal_kind=state.spec.kind,
                adx14=finite(market.adx14[signal_i]),
                rvol96=finite(market.rvol96[signal_i]),
                h1_dir_spread=finite(market.h1_spread[signal_i]) * direction,
                h4_dir_spread=finite(market.h4_spread[signal_i]) * direction,
                dir_ret16=finite(market.ret16[signal_i]) * direction,
                dir_ret48=finite(market.ret48[signal_i]) * direction,
                dir_ret96=finite(market.ret96[signal_i]) * direction,
                dir_macd=finite(market.macd_hist[signal_i]) * direction,
                dir_rsi14=(
                    finite(market.rsi14[signal_i], default=50.0)
                    if direction == 1
                    else 100.0 - finite(market.rsi14[signal_i], default=50.0)
                ),
                atr_pct96=finite(market.atr_pct96[signal_i]),
                atr_ratio96_672=finite(market.atr_ratio96_672[signal_i], default=99.0),
                previous_signal_age=finite(
                    state.previous_signal_age[signal_i],
                    default=0.0,
                ),
                churn192=finite(state.churn192[signal_i], default=999.0),
            )
        )
    return trades


def passes_filter(trade: EventTrade, spec: FilterSpec) -> bool:
    if spec.side == "long" and trade.direction != 1:
        return False
    if spec.side == "short" and trade.direction != -1:
        return False
    return (
        trade.adx14 >= spec.min_adx14
        and trade.rvol96 >= spec.min_rvol96
        and trade.h1_dir_spread >= spec.min_h1_dir_spread
        and trade.h4_dir_spread >= spec.min_h4_dir_spread
        and trade.dir_ret16 >= spec.min_dir_ret16
        and trade.dir_ret48 >= spec.min_dir_ret48
        and trade.dir_ret96 >= spec.min_dir_ret96
        and trade.dir_macd >= spec.min_dir_macd
        and trade.dir_rsi14 >= spec.min_dir_rsi14
        and trade.dir_rsi14 <= spec.max_dir_rsi14
        and trade.atr_pct96 >= spec.min_atr_pct96
        and trade.atr_pct96 <= spec.max_atr_pct96
        and trade.atr_ratio96_672 <= spec.max_atr_ratio96_672
        and trade.previous_signal_age >= spec.min_previous_signal_age
        and trade.churn192 <= spec.max_churn192
    )


def selected_trades(
    trades: list[EventTrade],
    filter_spec: FilterSpec,
) -> list[EventTrade]:
    selected: list[EventTrade] = []
    available_i = -1
    for trade in trades:
        if trade.entry_i < available_i:
            continue
        if not passes_filter(trade, filter_spec):
            continue
        selected.append(trade)
        available_i = trade.exit_i + filter_spec.cooldown_bars
    return selected


def evaluate_trades(
    *,
    trades: list[EventTrade],
    filter_spec: FilterSpec,
    exposure: float,
    period_days: float,
    exit_spec: ExitSpec,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> SearchResult | None:
    picked = selected_trades(trades, filter_spec)
    if not picked:
        return None

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    net_returns: list[float] = []
    gross_wins = 0.0
    gross_losses = 0.0

    for trade in picked:
        min_mark_return = exposure * (trade.min_path_return - ROUND_TRIP_COST)
        mark_equity = equity * max(0.0, 1.0 + min_mark_return)
        if peak > 0:
            max_drawdown = min(max_drawdown, mark_equity / peak - 1)

        net_return = exposure * (trade.raw_return - ROUND_TRIP_COST)
        equity *= max(0.0, 1.0 + net_return)
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = min(max_drawdown, equity / peak - 1)
        net_returns.append(net_return)
        if net_return >= 0:
            gross_wins += net_return
        else:
            gross_losses += abs(net_return)

    final_equity = float(equity)
    if period_days > 0 and final_equity > 0:
        annual_equity_multiple = final_equity ** (365.25 / period_days)
    else:
        annual_equity_multiple = 0.0
    annual_return_pct = (annual_equity_multiple - 1.0) * 100.0
    total_return_pct = (final_equity - 1.0) * 100.0
    wins = [value for value in net_returns if value > 0]
    win_rate_pct = len(wins) / len(net_returns) * 100.0
    max_drawdown_pct = max_drawdown * 100.0
    trades_per_day = len(picked) / period_days if period_days > 0 else 0.0
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else math.inf

    stop_trades = sum(1 for trade in picked if trade.exit_reason == "stop_loss")
    tp_trades = sum(1 for trade in picked if trade.exit_reason == "take_profit")
    trail_trades = sum(1 for trade in picked if trade.exit_reason == "trailing_stop")
    max_hold_trades = sum(1 for trade in picked if trade.exit_reason == "max_hold")

    target_return_pass = annual_return_pct >= TARGET_ANNUAL_RETURN_PCT
    target_equity_multiple_pass = annual_equity_multiple >= TARGET_ANNUAL_EQUITY_MULTIPLE
    target_drawdown_pass = max_drawdown_pct >= TARGET_MAX_DRAWDOWN_PCT
    target_win_rate_pass = win_rate_pct >= TARGET_WIN_RATE_PCT
    frequency_preference_pass = (
        PREFERRED_MIN_TRADES_PER_DAY <= trades_per_day <= PREFERRED_MAX_TRADES_PER_DAY
    )
    meets_core_target = (
        target_return_pass and target_drawdown_pass and target_win_rate_pass
    )
    meets_full_preference = meets_core_target and frequency_preference_pass

    return_gap = max(0.0, TARGET_ANNUAL_RETURN_PCT - annual_return_pct) / 1000.0
    dd_gap = max(0.0, TARGET_MAX_DRAWDOWN_PCT - max_drawdown_pct) / 5.0
    win_gap = max(0.0, TARGET_WIN_RATE_PCT - win_rate_pct) / 10.0
    if trades_per_day <= 0:
        frequency_gap = 2.0
    elif trades_per_day < PREFERRED_MIN_TRADES_PER_DAY:
        frequency_gap = (PREFERRED_MIN_TRADES_PER_DAY - trades_per_day) * 1.5
    elif trades_per_day > PREFERRED_MAX_TRADES_PER_DAY:
        frequency_gap = (trades_per_day - PREFERRED_MAX_TRADES_PER_DAY) * 0.7
    else:
        frequency_gap = 0.0
    score = (
        math.log(max(annual_equity_multiple, 1e-9))
        + win_rate_pct / 100.0
        + max_drawdown_pct / 100.0
        - return_gap
        - dd_gap
        - win_gap
        - frequency_gap
    )
    if meets_core_target:
        score += 8.0
    if meets_full_preference:
        score += 2.0

    first = picked[0]
    name = (
        f"HYPE_15M_MII_{first.signal_name}_{exit_spec.name}"
        f"_{filter_spec.name}_x{value_slug(exposure)}"
    )
    return SearchResult(
        name=name,
        signal_name=first.signal_name,
        signal_kind=first.signal_kind,
        exit_name=exit_spec.name,
        exit_kind=exit_spec.kind,
        filter_name=filter_spec.name,
        exposure=exposure,
        final_equity=final_equity,
        total_return_pct=total_return_pct,
        annual_return_pct=annual_return_pct,
        annual_equity_multiple=annual_equity_multiple,
        max_drawdown_pct=max_drawdown_pct,
        win_rate_pct=win_rate_pct,
        trades=len(picked),
        trades_per_day=trades_per_day,
        profit_factor=profit_factor,
        avg_trade_pct=float(np.mean(net_returns) * 100.0),
        median_trade_pct=float(np.median(net_returns) * 100.0),
        worst_trade_pct=float(np.min(net_returns) * 100.0),
        stop_trades=stop_trades,
        tp_trades=tp_trades,
        trail_trades=trail_trades,
        max_hold_trades=max_hold_trades,
        score=score,
        target_return_pass=target_return_pass,
        target_equity_multiple_pass=target_equity_multiple_pass,
        target_drawdown_pass=target_drawdown_pass,
        target_win_rate_pass=target_win_rate_pass,
        frequency_preference_pass=frequency_preference_pass,
        meets_core_target=meets_core_target,
        meets_full_preference=meets_full_preference,
        start_ts=str(start_ts),
        end_ts=str(end_ts),
    )


def result_sort_key(result: SearchResult) -> tuple[int, int, float, float, float, int]:
    return (
        int(result.meets_full_preference),
        int(result.meets_core_target),
        result.score,
        result.annual_equity_multiple,
        result.win_rate_pct,
        result.trades,
    )


def top_results(results: list[SearchResult], keep: int) -> list[SearchResult]:
    return sorted(results, key=result_sort_key, reverse=True)[:keep]


def maybe_prune_results(results: list[SearchResult], keep: int) -> list[SearchResult]:
    if len(results) <= keep * 3:
        return results
    return top_results(results, keep)


def trades_to_frame(
    trades: list[EventTrade],
    *,
    result: SearchResult,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for trade in trades:
        rows.append(
            {
                "strategy": result.name,
                "signal_name": trade.signal_name,
                "signal_kind": trade.signal_kind,
                "entry_ts": trade.entry_ts,
                "exit_ts": trade.exit_ts,
                "direction": "long" if trade.direction == 1 else "short",
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "raw_return_pct": trade.raw_return * 100.0,
                "net_return_pct": result.exposure
                * (trade.raw_return - ROUND_TRIP_COST)
                * 100.0,
                "min_path_return_pct": trade.min_path_return * 100.0,
                "max_path_return_pct": trade.max_path_return * 100.0,
                "bars_held": trade.bars_held,
                "exit_reason": trade.exit_reason,
                "adx14": trade.adx14,
                "rvol96": trade.rvol96,
                "h1_dir_spread": trade.h1_dir_spread,
                "h4_dir_spread": trade.h4_dir_spread,
                "dir_ret16": trade.dir_ret16,
                "dir_ret48": trade.dir_ret48,
                "dir_ret96": trade.dir_ret96,
                "dir_macd": trade.dir_macd,
                "dir_rsi14": trade.dir_rsi14,
                "atr_pct96": trade.atr_pct96,
                "atr_ratio96_672": trade.atr_ratio96_672,
                "previous_signal_age": trade.previous_signal_age,
                "churn192": trade.churn192,
            }
        )
    return pd.DataFrame(rows)


def empty_window_result(start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> dict[str, object]:
    return {
        "start_ts": str(start_ts),
        "end_ts": str(end_ts),
        "trades": 0,
        "final_equity": 1.0,
        "total_return_pct": 0.0,
        "annual_return_pct": 0.0,
        "annual_equity_multiple": 1.0,
        "max_drawdown_pct": 0.0,
        "win_rate_pct": 0.0,
        "trades_per_day": 0.0,
    }


def evaluate_window(
    *,
    trades: list[EventTrade],
    filter_spec: FilterSpec,
    exposure: float,
    exit_spec: ExitSpec,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> dict[str, object]:
    window_trades = [
        trade for trade in trades if start_ts <= trade.entry_ts <= end_ts
    ]
    period_days = max((end_ts - start_ts).total_seconds() / 86_400, 1.0)
    result = evaluate_trades(
        trades=window_trades,
        filter_spec=filter_spec,
        exposure=exposure,
        period_days=period_days,
        exit_spec=exit_spec,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    if result is None:
        return empty_window_result(start_ts, end_ts)
    return asdict(result)


def window_diagnostics(
    *,
    trades: list[EventTrade],
    filter_spec: FilterSpec,
    exposure: float,
    exit_spec: ExitSpec,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> dict[str, object]:
    midpoint = start_ts + (end_ts - start_ts) / 2
    quarter_delta = (end_ts - start_ts) / 4
    windows: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {
        "first_half": (start_ts, midpoint),
        "second_half": (midpoint, end_ts),
        "last_90d": (max(start_ts, end_ts - pd.Timedelta(days=90)), end_ts),
    }
    for idx in range(4):
        left = start_ts + quarter_delta * idx
        right = start_ts + quarter_delta * (idx + 1)
        windows[f"q{idx + 1}"] = (left, right)

    return {
        name: evaluate_window(
            trades=trades,
            filter_spec=filter_spec,
            exposure=exposure,
            exit_spec=exit_spec,
            start_ts=left,
            end_ts=right,
        )
        for name, (left, right) in windows.items()
    }


def base_filter_specs() -> list[FilterSpec]:
    return [
        FilterSpec(),
        FilterSpec(side="long"),
        FilterSpec(side="short"),
        FilterSpec(min_h1_dir_spread=0.0),
        FilterSpec(min_h4_dir_spread=0.0),
        FilterSpec(min_adx14=22.0),
        FilterSpec(min_adx14=28.0),
        FilterSpec(min_rvol96=1.0),
        FilterSpec(min_dir_ret48=0.0),
        FilterSpec(min_dir_macd=0.0),
        FilterSpec(max_atr_ratio96_672=1.6),
        FilterSpec(min_dir_rsi14=48.0, max_dir_rsi14=78.0),
        FilterSpec(min_h1_dir_spread=0.0, min_adx14=22.0),
        FilterSpec(min_h1_dir_spread=0.0, min_rvol96=1.0),
    ]


def exposures() -> list[float]:
    return [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    raw, metadata = load_data(args.cache, refresh=args.refresh_data)
    start_ts = pd.Timestamp(raw["ts"].min())
    end_ts = pd.Timestamp(raw["ts"].max())
    period_days = max((end_ts - start_ts).total_seconds() / 86_400, 1.0)

    signals = signal_specs()
    if args.max_signals:
        signals = signals[: args.max_signals]
    spans = sorted({value for spec in signals for value in (spec.fast, spec.slow) if value})
    features = add_features(raw, spans)
    market = build_market_arrays(features)

    states: dict[str, SignalState] = {}
    for spec in signals:
        state = signal_state(features, spec)
        if len(state.signal_i) >= 3:
            states[spec.name] = state

    print(
        f"loaded rows={len(raw)} start={start_ts} end={end_ts} "
        f"period_days={period_days:.2f} signals={len(states)}",
        flush=True,
    )

    base_filters = base_filter_specs()
    exp_values = exposures()
    stage1_results: list[SearchResult] = []
    coarse_exits = coarse_exit_specs()

    for signal_no, state in enumerate(states.values(), start=1):
        for exit_spec in coarse_exits:
            raw_trades = simulate_trades(market, state, exit_spec)
            if len(raw_trades) < 3:
                continue
            for filter_spec in base_filters:
                for exposure in exp_values:
                    result = evaluate_trades(
                        trades=raw_trades,
                        filter_spec=filter_spec,
                        exposure=exposure,
                        period_days=period_days,
                        exit_spec=exit_spec,
                        start_ts=start_ts,
                        end_ts=end_ts,
                    )
                    if result is not None:
                        stage1_results.append(result)
                        stage1_results = maybe_prune_results(
                            stage1_results,
                            args.stage1_keep,
                        )
        if signal_no % 10 == 0:
            print(
                f"stage1 signals={signal_no}/{len(states)} "
                f"kept={len(stage1_results)}",
                flush=True,
            )

    stage1_top = top_results(stage1_results, args.stage1_keep)
    top_signal_names: list[str] = []
    seen_signal_names: set[str] = set()
    for result in stage1_top:
        if result.signal_name in seen_signal_names:
            continue
        seen_signal_names.add(result.signal_name)
        top_signal_names.append(result.signal_name)
        if len(top_signal_names) >= args.stage2_signal_keep:
            break
    full_exits = full_exit_specs()
    stage2_base: list[tuple[SearchResult, ExitSpec, list[EventTrade]]] = []
    stage2_seen: dict[tuple[str, str], int] = {}

    print(
        f"stage1 done results_kept={len(stage1_top)} "
        f"top_signals={len(top_signal_names)} full_exits={len(full_exits)}",
        flush=True,
    )

    for signal_no, signal_name in enumerate(top_signal_names, start=1):
        state = states[signal_name]
        for exit_spec in full_exits:
            raw_trades = simulate_trades(market, state, exit_spec)
            if len(raw_trades) < 3:
                continue
            best_for_exit: tuple[SearchResult, ExitSpec, list[EventTrade]] | None = None
            for filter_spec in base_filters:
                for exposure in exp_values:
                    result = evaluate_trades(
                        trades=raw_trades,
                        filter_spec=filter_spec,
                        exposure=exposure,
                        period_days=period_days,
                        exit_spec=exit_spec,
                        start_ts=start_ts,
                        end_ts=end_ts,
                    )
                    if result is None:
                        continue
                    if best_for_exit is None or result_sort_key(result) > result_sort_key(
                        best_for_exit[0]
                    ):
                        best_for_exit = (result, exit_spec, raw_trades)
            if best_for_exit is None:
                continue
            key = (best_for_exit[0].signal_name, best_for_exit[0].exit_name)
            existing_i = stage2_seen.get(key)
            if existing_i is None:
                stage2_seen[key] = len(stage2_base)
                stage2_base.append(best_for_exit)
            elif result_sort_key(best_for_exit[0]) > result_sort_key(stage2_base[existing_i][0]):
                stage2_base[existing_i] = best_for_exit
            if len(stage2_base) > args.stage2_keep * 3:
                stage2_base = sorted(
                    stage2_base,
                    key=lambda item: result_sort_key(item[0]),
                    reverse=True,
                )[: args.stage2_keep]
                stage2_seen = {
                    (item[0].signal_name, item[0].exit_name): idx
                    for idx, item in enumerate(stage2_base)
                }
        print(
            f"stage2 signals={signal_no}/{len(top_signal_names)} "
            f"base={len(stage2_base)}",
            flush=True,
        )

    stage2_base = sorted(
        stage2_base,
        key=lambda item: result_sort_key(item[0]),
        reverse=True,
    )[: args.stage2_keep]
    all_filters = filter_specs()
    final_keep = max(args.top * 20, 1000)
    final_results: list[SearchResult] = []
    final_evaluated = 0
    final_with_trades = 0
    core_targets = 0
    full_targets = 0

    print(
        f"stage2 done base={len(stage2_base)} filters={len(all_filters)}",
        flush=True,
    )

    for base_no, (_seed, exit_spec, raw_trades) in enumerate(stage2_base, start=1):
        for filter_spec in all_filters:
            for exposure in exp_values:
                final_evaluated += 1
                result = evaluate_trades(
                    trades=raw_trades,
                    filter_spec=filter_spec,
                    exposure=exposure,
                    period_days=period_days,
                    exit_spec=exit_spec,
                    start_ts=start_ts,
                    end_ts=end_ts,
                )
                if result is None:
                    continue
                final_with_trades += 1
                core_targets += int(result.meets_core_target)
                full_targets += int(result.meets_full_preference)
                final_results.append(result)
                final_results = maybe_prune_results(final_results, final_keep)
        if base_no % 10 == 0:
            print(
                f"final base={base_no}/{len(stage2_base)} "
                f"evaluated={final_evaluated} with_trades={final_with_trades} "
                f"core_targets={core_targets} full_targets={full_targets}",
                flush=True,
            )

    final_results = top_results(final_results, final_keep)
    ranking = top_results(final_results, args.top)
    ranking_path = args.output_dir / "hype_15m_mii_search_ranking.csv"
    pd.DataFrame([asdict(result) for result in ranking]).to_csv(ranking_path, index=False)

    best = ranking[0] if ranking else None
    top_trades_path = args.output_dir / "hype_15m_mii_search_top_trades.csv"
    diagnostics: dict[str, object] = {}
    if best is not None:
        best_filter = next(spec for spec in all_filters if spec.name == best.filter_name)
        best_exit = next(spec for spec in full_exits if spec.name == best.exit_name)
        best_state = states[best.signal_name]
        best_raw_trades = simulate_trades(market, best_state, best_exit)
        best_selected = selected_trades(best_raw_trades, best_filter)
        trades_to_frame(best_selected, result=best).to_csv(top_trades_path, index=False)
        diagnostics = window_diagnostics(
            trades=best_raw_trades,
            filter_spec=best_filter,
            exposure=best.exposure,
            exit_spec=best_exit,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    summary = {
        "metadata": metadata,
        "target": {
            "annual_return_pct": TARGET_ANNUAL_RETURN_PCT,
            "annual_equity_multiple": TARGET_ANNUAL_EQUITY_MULTIPLE,
            "max_drawdown_pct": TARGET_MAX_DRAWDOWN_PCT,
            "win_rate_pct": TARGET_WIN_RATE_PCT,
            "preferred_trades_per_day": [
                PREFERRED_MIN_TRADES_PER_DAY,
                PREFERRED_MAX_TRADES_PER_DAY,
            ],
        },
        "search_space": {
            "signals_total": len(signals),
            "signals_with_events": len(states),
            "coarse_exit_specs": len(coarse_exits),
            "full_exit_specs": len(full_exits),
            "base_filter_specs": len(base_filters),
            "full_filter_specs": len(all_filters),
            "exposures": exp_values,
            "stage1_kept": len(stage1_top),
            "stage2_base_kept": len(stage2_base),
            "final_evaluated": final_evaluated,
            "final_with_trades": final_with_trades,
            "core_targets": core_targets,
            "full_preference_targets": full_targets,
        },
        "cost_assumption": {
            "commission_per_side": COMMISSION_PER_SIDE,
            "slippage_per_side": SLIPPAGE_PER_SIDE,
            "round_trip_cost": ROUND_TRIP_COST,
            "execution": [
                "signal on closed 15m bar",
                "entry at next 15m open",
                "fixed stop/take-profit tested on intrabar high/low",
                "same-bar stop and take-profit resolves to stop first",
                "one position at a time after filter/cooldown selection",
            ],
        },
        "best": asdict(best) if best is not None else None,
        "diagnostics": diagnostics,
        "ranking_csv": str(ranking_path),
        "top_trades_csv": str(top_trades_path) if best is not None else None,
    }
    summary_path = args.output_dir / "hype_15m_mii_search_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
