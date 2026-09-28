"""BIN-1D-MA7-CTP：四币日K SMA7 穿越后趋势发生率 SCOUT 诊断。

冻结口径见同目录上一级 specs/ 与本文件常量。跑完后写 diagnostics 与 artifacts。
本脚本不搜索阈值、不做账户、不扣成本、不构成策略版本。
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from strategy_lab.data.quality import audit_ohlcv_frame


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
FEATURE_DIR = ROOT / "data/features/binance_1d_ma7_rsi6_dapml_p0"
RUN_DATE = "2026-08-31"
FAMILY_NAME = "Binance-1D-MA7-Cross-Trend-Probability"
FAMILY_ALIAS = "BIN-1D-MA7-CTP"

SYMBOLS = {
    "BTCUSDT": ("BTC", "BTC/USDT:USDT", "btcusdt"),
    "ETHUSDT": ("ETH", "ETH/USDT:USDT", "ethusdt"),
    "BNBUSDT": ("BNB", "BNB/USDT:USDT", "bnbusdt"),
    "SOLUSDT": ("SOL", "SOL/USDT:USDT", "solusdt"),
}

SMA_PERIOD = 7
ATR_PERIOD = 7
VOLUME_MEDIAN_PERIOD = 20
SLOPE_ATR_THRESHOLD = 0.02
VOLUME_MULTS = (1.2, 1.5, 2.0)
PATH_WINDOWS = (7, 30, 60, 90)
BARRIER_HORIZONS = (10, 20)
PRIMARY_HORIZON = 20
FAVORABLE_ATR = 2.0
ADVERSE_ATR = 1.0
MIN_N_HIGHLIGHT = 20
COMMON_START = pd.Timestamp("2020-09-15T00:00:00Z")
RECENT_DAYS = 365

RATIO_BINS = (
    ("R<0.5 回撤主导", 0.0, 0.5),
    ("0.5≤R<1 偏回撤", 0.5, 1.0),
    ("1≤R<2 偏上涨", 1.0, 2.0),
    ("R≥2 上涨主导", 2.0, math.inf),
)
LOCATION_BINS = (
    ("近低点 <0.25", 0.0, 0.25),
    ("中下 0.25–0.5", 0.25, 0.5),
    ("中上 0.5–0.75", 0.5, 0.75),
    ("近高点 ≥0.75", 0.75, 1.0000001),
)
DD_BINS = {
    7: ((" <3%", 0.0, 0.03), ("3–8%", 0.03, 0.08), ("≥8%", 0.08, math.inf)),
    30: ((" <8%", 0.0, 0.08), ("8–20%", 0.08, 0.20), ("≥20%", 0.20, math.inf)),
    60: ((" <12%", 0.0, 0.12), ("12–25%", 0.12, 0.25), ("≥25%", 0.25, math.inf)),
    90: ((" <15%", 0.0, 0.15), ("15–30%", 0.15, 0.30), ("≥30%", 0.30, math.inf)),
}
RU_BINS = DD_BINS
STACK_ADVERSE_WINDOW = 30
STACK_ADVERSE_MIN = 0.10
STACK_VOLUME_MULT = 1.5

OUTPUTS = {
    "events": FAMILY_DIR / "artifacts" / f"binance_1d_ma7_ctp_events_{RUN_DATE}.csv",
    "rates": FAMILY_DIR / "artifacts" / f"binance_1d_ma7_ctp_rates_{RUN_DATE}.csv",
    "path_rates": FAMILY_DIR / "artifacts" / f"binance_1d_ma7_ctp_path_rates_{RUN_DATE}.csv",
    "summary": FAMILY_DIR / "artifacts" / f"binance_1d_ma7_ctp_summary_{RUN_DATE}.json",
    "report": FAMILY_DIR
    / "diagnostics"
    / f"binance-1d-ma7-cross-trend-probability-{RUN_DATE}.md",
}


@dataclass(frozen=True)
class Rate:
    n: int
    k: int
    p: float
    lo: float
    hi: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "n": self.n,
            "k": self.k,
            "p": self.p,
            "ci_low": self.lo,
            "ci_high": self.hi,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Run {FAMILY_ALIAS} scout diagnostic.")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def make_rate(flags: np.ndarray | pd.Series) -> Rate:
    values = np.asarray(flags, dtype=float)
    valid = np.isfinite(values)
    n = int(valid.sum())
    k = int(np.round(values[valid].sum())) if n else 0
    p = k / n if n else float("nan")
    lo, hi = wilson_interval(k, n)
    return Rate(n=n, k=k, p=p, lo=lo, hi=hi)


def fmt_pct(value: float, digits: int = 1) -> str:
    if not np.isfinite(value):
        return "n/a"
    return f"{100.0 * value:.{digits}f}%"


def fmt_rate(rate: Rate) -> str:
    if rate.n <= 0:
        return "n=0"
    mark = "" if rate.n >= MIN_N_HIGHLIGHT else " n<20"
    return (
        f"{rate.k}/{rate.n} = {fmt_pct(rate.p)} "
        f"[{fmt_pct(rate.lo)}–{fmt_pct(rate.hi)}]{mark}"
    )


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    previous = close.shift(1)
    return pd.concat(
        [high - low, (high - previous).abs(), (low - previous).abs()],
        axis=1,
    ).max(axis=1)


def rolling_excursions(close: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    drawdown = np.full(len(close), np.nan)
    runup = np.full(len(close), np.nan)
    location = np.full(len(close), np.nan)
    if len(close) <= window:
        return drawdown, runup, location
    views = np.lib.stride_tricks.sliding_window_view(close, window)
    ok = np.isfinite(views).all(axis=1)
    max_dd = np.full(len(views), np.nan)
    max_ru = np.full(len(views), np.nan)
    loc = np.full(len(views), np.nan)
    if ok.any():
        valid_views = views[ok]
        running_max = np.maximum.accumulate(valid_views, axis=1)
        running_min = np.minimum.accumulate(valid_views, axis=1)
        peak = np.max(valid_views, axis=1)
        trough = np.min(valid_views, axis=1)
        width = peak - trough
        max_dd[ok] = np.max(1.0 - valid_views / np.maximum(running_max, 1e-12), axis=1)
        max_ru[ok] = np.max(valid_views / np.maximum(running_min, 1e-12) - 1.0, axis=1)
        loc[ok] = np.divide(
            valid_views[:, -1] - trough,
            width,
            out=np.full(ok.sum(), 0.5),
            where=width > 0.0,
        )
    drawdown[window:] = max_dd[:-1]
    runup[window:] = max_ru[:-1]
    location[window:] = loc[:-1]
    return drawdown, runup, location


def forward_barrier(
    close: np.ndarray,
    atr_pre: np.ndarray,
    horizon: int,
    favor_sign: np.ndarray,
) -> dict[str, np.ndarray]:
    size = len(close)
    trend = np.full(size, np.nan)
    mfe2 = np.full(size, np.nan)
    win = np.full(size, np.nan)
    mfe = np.full(size, np.nan)
    mae = np.full(size, np.nan)
    if size <= horizon:
        return {
            "trend": trend,
            "mfe2": mfe2,
            "win": win,
            "mfe": mfe,
            "mae": mae,
        }
    views = np.lib.stride_tricks.sliding_window_view(close, horizon + 1)
    base = views[:, 0]
    future = views[:, 1:]
    count = len(views)
    denom = atr_pre[:count]
    sign = favor_sign[:count]
    valid = (
        np.isfinite(denom)
        & (denom > 0)
        & np.isfinite(sign)
        & (sign != 0)
        & np.isfinite(future).all(axis=1)
        & np.isfinite(base)
    )
    signed = np.full_like(future, np.nan)
    signed[valid] = sign[valid, None] * (future[valid] - base[valid, None]) / denom[valid, None]
    favorable = signed >= FAVORABLE_ATR
    adverse = signed <= -ADVERSE_ATR
    first_fav = np.where(favorable.any(axis=1), favorable.argmax(axis=1), horizon + 1)
    first_adv = np.where(adverse.any(axis=1), adverse.argmax(axis=1), horizon + 1)
    trend[:count] = np.where(valid, (first_fav < first_adv).astype(float), np.nan)
    mfe_vals = np.full(count, np.nan)
    mae_vals = np.full(count, np.nan)
    if valid.any():
        mfe_vals[valid] = np.nanmax(signed[valid], axis=1)
        mae_vals[valid] = np.nanmin(signed[valid], axis=1)
    mfe[:count] = mfe_vals
    mae[:count] = mae_vals
    mfe2[:count] = np.where(valid, (mfe_vals >= FAVORABLE_ATR).astype(float), np.nan)
    win[:count] = np.where(valid, (signed[:, -1] > 0.0).astype(float), np.nan)
    return {
        "trend": trend,
        "mfe2": mfe2,
        "win": win,
        "mfe": mfe,
        "mae": mae,
    }


def next_flag_delay(flags: np.ndarray) -> np.ndarray:
    delay = np.full(len(flags), np.nan)
    last = None
    for index in range(len(flags) - 1, -1, -1):
        if last is not None:
            delay[index] = float(last - index)
        if flags[index]:
            last = index
    return delay


def ratio_value(runup: float, drawdown: float) -> float:
    if not np.isfinite(runup) or not np.isfinite(drawdown):
        return float("nan")
    if drawdown <= 1e-12:
        return math.inf if runup > 1e-12 else float("nan")
    return float(runup / drawdown)


def assign_bin(value: float, bins: tuple[tuple[str, float, float], ...]) -> str:
    if not np.isfinite(value) and not (isinstance(value, float) and math.isinf(value)):
        return "NA"
    if isinstance(value, float) and math.isinf(value) and value > 0:
        return bins[-1][0]
    for label, low, high in bins:
        if low <= value < high:
            return label
    return "NA"


def load_daily(symbol: str, slug: str, display: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = FEATURE_DIR / f"{slug}_perp_1d.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_parquet(path)
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame = frame.sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True)
    closed = frame.loc[frame["is_closed"].astype(bool)].copy().reset_index(drop=True)
    audit = audit_ohlcv_frame(closed, expected_timeframe="1d", require_closed=True)
    expected = pd.date_range(closed["ts"].min(), closed["ts"].max(), freq="1D", tz="UTC")
    missing = expected.difference(pd.DatetimeIndex(closed["ts"]))
    if len(missing):
        raise RuntimeError(f"{symbol} has {len(missing)} missing daily bars")
    if not bool(audit.trusted):
        raise RuntimeError(f"{symbol} daily audit failed: {audit.to_dict()}")
    quality = {
        "symbol": symbol,
        "display": display,
        "path": str(path.relative_to(ROOT)),
        "rows": int(len(closed)),
        "start": closed["ts"].min().isoformat(),
        "end": closed["ts"].max().isoformat(),
        "source": sorted(closed["source"].astype(str).unique()),
        "audit_trusted": True,
        "missing_bars": 0,
    }
    return closed, quality


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    close = out["close"].astype(float)
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    tr = true_range(high, low, close)
    out["sma7"] = close.rolling(SMA_PERIOD, min_periods=SMA_PERIOD).mean()
    out["atr7"] = tr.rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean()
    out["atr_pre"] = out["atr7"].shift(1)
    out["sma7_prev"] = out["sma7"].shift(1)
    out["close_prev"] = close.shift(1)
    out["slope_atr"] = (out["sma7"] - out["sma7_prev"]) / out["atr7"]
    quote = out["quote_volume"].astype(float)
    vol_median = quote.rolling(VOLUME_MEDIAN_PERIOD, min_periods=VOLUME_MEDIAN_PERIOD).median()
    out["quote_vol_ratio_20"] = quote / vol_median
    close_np = close.to_numpy(dtype=float)
    for window in PATH_WINDOWS:
        dd, ru, loc = rolling_excursions(close_np, window)
        out[f"max_dd_{window}"] = dd
        out[f"max_ru_{window}"] = ru
        out[f"loc_{window}"] = loc
        ru_arr = np.asarray(ru, dtype=float)
        dd_arr = np.asarray(dd, dtype=float)
        ratio = np.full(len(out), np.nan)
        good = np.isfinite(ru_arr) & np.isfinite(dd_arr)
        positive_dd = good & (dd_arr > 1e-12)
        zero_dd = good & (dd_arr <= 1e-12) & (ru_arr > 1e-12)
        ratio[positive_dd] = ru_arr[positive_dd] / dd_arr[positive_dd]
        ratio[zero_dd] = np.inf
        out[f"ratio_{window}"] = ratio
    return out


def assign_bin_array(values: np.ndarray, bins: tuple[tuple[str, float, float], ...]) -> np.ndarray:
    labels = np.full(len(values), "NA", dtype=object)
    finite = np.isfinite(values)
    pos_inf = np.isposinf(values)
    labels[pos_inf] = bins[-1][0]
    for label, low, high in bins:
        labels[finite & (values >= low) & (values < high)] = label
    return labels


def persist_same_side(
    mask: np.ndarray,
    close: np.ndarray,
    sma: np.ndarray,
    *,
    long_side: bool,
) -> np.ndarray:
    persist = np.full(len(close), np.nan)
    for index in np.flatnonzero(mask):
        end = index + 5
        if end >= len(close):
            continue
        future_close = close[index + 1 : end + 1]
        future_sma = sma[index + 1 : end + 1]
        if not (np.isfinite(future_close).all() and np.isfinite(future_sma).all()):
            continue
        if long_side:
            persist[index] = float(np.all(future_close > future_sma))
        else:
            persist[index] = float(np.all(future_close < future_sma))
    return persist


def recross_flags(delay: np.ndarray, remain: np.ndarray, bars: int) -> np.ndarray:
    result = np.full(len(delay), np.nan)
    known = np.isfinite(delay)
    result[known] = (delay[known] >= bars).astype(float)
    unknown = ~known
    result[unknown] = np.where(remain[unknown] >= bars, 1.0, np.nan)
    return result


def build_events(symbol: str, frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["close"].to_numpy(dtype=float)
    sma = frame["sma7"].to_numpy(dtype=float)
    sma_prev = frame["sma7_prev"].to_numpy(dtype=float)
    close_prev = frame["close_prev"].to_numpy(dtype=float)
    slope = frame["slope_atr"].to_numpy(dtype=float)
    atr7 = frame["atr7"].to_numpy(dtype=float)
    atr_pre = frame["atr_pre"].to_numpy(dtype=float)
    vol_ratio = frame["quote_vol_ratio_20"].to_numpy(dtype=float)
    ts = frame["ts"].to_numpy()
    long_cross = (
        np.isfinite(sma)
        & np.isfinite(sma_prev)
        & (close_prev < sma_prev)
        & (close > sma)
    )
    short_cross = (
        np.isfinite(sma)
        & np.isfinite(sma_prev)
        & (close_prev > sma_prev)
        & (close < sma)
    )
    delay_to_short = next_flag_delay(short_cross)
    delay_to_long = next_flag_delay(long_cross)
    remain = (len(frame) - 1) - np.arange(len(frame))
    path = {
        window: {
            "dd": frame[f"max_dd_{window}"].to_numpy(dtype=float),
            "ru": frame[f"max_ru_{window}"].to_numpy(dtype=float),
            "loc": frame[f"loc_{window}"].to_numpy(dtype=float),
            "ratio": frame[f"ratio_{window}"].to_numpy(dtype=float),
        }
        for window in PATH_WINDOWS
    }
    chunks: list[pd.DataFrame] = []
    for side, mask, favor, delay in (
        ("long", long_cross, 1.0, delay_to_short),
        ("short", short_cross, -1.0, delay_to_long),
    ):
        selected = np.flatnonzero(mask)
        if selected.size == 0:
            continue
        favor_sign = np.where(mask, favor, 0.0)
        labels = {
            horizon: forward_barrier(close, atr_pre, horizon, favor_sign)
            for horizon in BARRIER_HORIZONS
        }
        persist5 = persist_same_side(mask, close, sma, long_side=side == "long")
        recross5 = recross_flags(delay, remain, 5)
        recross10 = recross_flags(delay, remain, 10)
        slope_sel = slope[selected]
        if side == "long":
            slope_sign = np.isfinite(slope_sel) & (slope_sel > 0)
            slope_002 = np.isfinite(slope_sel) & (slope_sel >= SLOPE_ATR_THRESHOLD)
        else:
            slope_sign = np.isfinite(slope_sel) & (slope_sel < 0)
            slope_002 = np.isfinite(slope_sel) & (slope_sel <= -SLOPE_ATR_THRESHOLD)
        item: dict[str, Any] = {
            "symbol": np.full(selected.size, symbol),
            "ts": ts[selected],
            "side": np.full(selected.size, side),
            "close": close[selected],
            "sma7": sma[selected],
            "atr7": atr7[selected],
            "atr_pre": atr_pre[selected],
            "slope_atr": slope_sel,
            "quote_vol_ratio_20": vol_ratio[selected],
            "slope_sign": slope_sign,
            "slope_002": slope_002,
            "recross_delay": delay[selected],
            "persist_5": persist5[selected],
            "recross_ge_5": recross5[selected],
            "recross_ge_10": recross10[selected],
        }
        for window in PATH_WINDOWS:
            dd = path[window]["dd"][selected]
            ru = path[window]["ru"][selected]
            loc = path[window]["loc"][selected]
            ratio = path[window]["ratio"][selected]
            item[f"max_dd_{window}"] = dd
            item[f"max_ru_{window}"] = ru
            item[f"loc_{window}"] = loc
            item[f"ratio_{window}"] = ratio
            item[f"aligned_adverse_{window}"] = dd if side == "long" else ru
            item[f"aligned_favorable_{window}"] = ru if side == "long" else dd
            item[f"ratio_bin_{window}"] = assign_bin_array(ratio, RATIO_BINS)
            item[f"dd_bin_{window}"] = assign_bin_array(dd, DD_BINS[window])
            item[f"ru_bin_{window}"] = assign_bin_array(ru, RU_BINS[window])
            item[f"loc_bin_{window}"] = assign_bin_array(loc, LOCATION_BINS)
        for horizon in BARRIER_HORIZONS:
            pack = labels[horizon]
            item[f"trend_{horizon}"] = pack["trend"][selected]
            item[f"mfe2_{horizon}"] = pack["mfe2"][selected]
            item[f"win_{horizon}"] = pack["win"][selected]
            if horizon == PRIMARY_HORIZON:
                item["mfe_atr"] = pack["mfe"][selected]
                item["mae_atr"] = pack["mae"][selected]
        vol_sel = vol_ratio[selected]
        for multiple in VOLUME_MULTS:
            key = f"vol_{str(multiple).replace('.', 'p')}"
            item[key] = np.isfinite(vol_sel) & (vol_sel >= multiple)
        chunks.append(pd.DataFrame(item))
    if not chunks:
        return pd.DataFrame()
    events = pd.concat(chunks, ignore_index=True)
    events["ts"] = pd.to_datetime(events["ts"], utc=True)
    return events.sort_values(["symbol", "ts", "side"]).reset_index(drop=True)


def filter_mask(events: pd.DataFrame, name: str) -> pd.Series:
    true = pd.Series(True, index=events.index)
    vol_1p5 = events["vol_1p5"] if "vol_1p5" in events.columns else true
    if name == "cross":
        return true
    if name == "slope_sign":
        return events["slope_sign"]
    if name == "slope_002":
        return events["slope_002"]
    if name == "vol_1p2":
        return events["vol_1p2"]
    if name == "vol_1p5":
        return events["vol_1p5"]
    if name == "vol_2p0":
        return events["vol_2p0"]
    if name == "slope_002+vol_1p5":
        return events["slope_002"] & vol_1p5
    if name == "slope_002+vol_1p5+aligned_dd30_ge_10":
        adverse = events[f"aligned_adverse_{STACK_ADVERSE_WINDOW}"]
        return events["slope_002"] & vol_1p5 & adverse.ge(STACK_ADVERSE_MIN)
    if name == "path_ratio30_reclaim_or_fade":
        long_reclaim = events["side"].eq("long") & events["ratio_30"].lt(1.0)
        short_fade = events["side"].eq("short") & events["ratio_30"].gt(1.0)
        return long_reclaim | short_fade
    if name == "slope_002+vol_1p5+ratio30_reclaim_or_fade":
        long_reclaim = events["side"].eq("long") & events["ratio_30"].lt(1.0)
        short_fade = events["side"].eq("short") & events["ratio_30"].gt(1.0)
        return events["slope_002"] & vol_1p5 & (long_reclaim | short_fade)
    raise KeyError(name)


FILTER_ORDER = (
    "cross",
    "slope_sign",
    "slope_002",
    "vol_1p2",
    "vol_1p5",
    "vol_2p0",
    "slope_002+vol_1p5",
    "path_ratio30_reclaim_or_fade",
    "slope_002+vol_1p5+aligned_dd30_ge_10",
    "slope_002+vol_1p5+ratio30_reclaim_or_fade",
)

FILTER_ZH = {
    "cross": "裸穿越 SMA7",
    "slope_sign": "同向斜率（符号）",
    "slope_002": "同向斜率 ≥ 0.02×ATR7",
    "vol_1p2": "quote 成交额 ≥ 1.2×20日中位",
    "vol_1p5": "quote 成交额 ≥ 1.5×20日中位",
    "vol_2p0": "quote 成交额 ≥ 2.0×20日中位",
    "slope_002+vol_1p5": "斜率0.02 + 放量1.5×",
    "path_ratio30_reclaim_or_fade": "30日上涨/回撤比：多头R<1 / 空头R>1",
    "slope_002+vol_1p5+aligned_dd30_ge_10": "斜率+放量 + 30日逆向≥10%",
    "slope_002+vol_1p5+ratio30_reclaim_or_fade": "斜率+放量 + 30日R方向过滤",
}

LABELS = (
    ("trend_20", "20日先到+2ATR、未先到-1ATR"),
    ("mfe2_20", "20日最大顺向偏移≥2ATR"),
    ("win_20", "20日后收盘仍顺向"),
    ("trend_10", "10日先到+2ATR、未先到-1ATR"),
    ("persist_5", "随后5日收盘仍在SMA7同侧"),
    ("recross_ge_5", "5日内不再反向穿越"),
)


def window_slice(events: pd.DataFrame, name: str, data_end: pd.Timestamp) -> pd.DataFrame:
    if name == "full":
        return events
    if name == "common":
        return events.loc[events["ts"].ge(COMMON_START)].copy()
    if name == "1y":
        start = data_end - pd.Timedelta(days=RECENT_DAYS)
        return events.loc[events["ts"].ge(start)].copy()
    raise KeyError(name)


def rate_table(
    events: pd.DataFrame,
    sample: str,
    symbols: list[str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if symbols is None:
        symbols = ["ALL", *SYMBOLS]
    sides = ("both", "long", "short")
    for symbol in symbols:
        subset = events if symbol == "ALL" else events.loc[events["symbol"].eq(symbol)]
        for side in sides:
            side_frame = subset if side == "both" else subset.loc[subset["side"].eq(side)]
            for filter_name in FILTER_ORDER:
                if side_frame.empty:
                    masked = side_frame
                else:
                    masked = side_frame.loc[filter_mask(side_frame, filter_name)]
                row: dict[str, Any] = {
                    "sample": sample,
                    "symbol": symbol,
                    "side": side,
                    "filter": filter_name,
                    "filter_zh": FILTER_ZH[filter_name],
                    "events": int(len(masked)),
                }
                for column, _label in LABELS:
                    rate = make_rate(masked[column] if not masked.empty else [])
                    row[f"{column}_n"] = rate.n
                    row[f"{column}_k"] = rate.k
                    row[f"{column}_p"] = rate.p
                    row[f"{column}_ci_low"] = rate.lo
                    row[f"{column}_ci_high"] = rate.hi
                    row[f"{column}_txt"] = fmt_rate(rate)
                if not masked.empty and masked["mfe_atr"].notna().any():
                    row["mfe_atr_median"] = float(masked["mfe_atr"].median())
                    row["mae_atr_median"] = float(masked["mae_atr"].median())
                else:
                    row["mfe_atr_median"] = float("nan")
                    row["mae_atr_median"] = float("nan")
                rows.append(row)
    return rows


def path_table(
    events: pd.DataFrame,
    sample: str,
    symbols: list[str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if symbols is None:
        symbols = ["ALL", *SYMBOLS]
    for symbol in symbols:
        subset = events if symbol == "ALL" else events.loc[events["symbol"].eq(symbol)]
        for side in ("both", "long", "short"):
            side_frame = subset if side == "both" else subset.loc[subset["side"].eq(side)]
            for window in PATH_WINDOWS:
                specs = (
                    (f"ratio_bin_{window}", "ratio", f"{window}日上涨/回撤比"),
                    (f"dd_bin_{window}", "drawdown", f"{window}日最大回撤"),
                    (f"ru_bin_{window}", "runup", f"{window}日最大上涨"),
                    (f"loc_bin_{window}", "location", f"{window}日价格位置"),
                )
                for column, kind, title in specs:
                    if side_frame.empty:
                        continue
                    for bin_name, group in side_frame.groupby(column, dropna=False, sort=False):
                        rate = make_rate(group["trend_20"])
                        rows.append(
                            {
                                "sample": sample,
                                "symbol": symbol,
                                "side": side,
                                "window": window,
                                "kind": kind,
                                "title": title,
                                "bin": str(bin_name),
                                "events": int(len(group)),
                                "trend_20_txt": fmt_rate(rate),
                                "trend_20_n": rate.n,
                                "trend_20_k": rate.k,
                                "trend_20_p": rate.p,
                                "trend_20_ci_low": rate.lo,
                                "trend_20_ci_high": rate.hi,
                            }
                        )
    return rows


def pick_rate(rates: pd.DataFrame, sample: str, symbol: str, side: str, filt: str) -> pd.Series:
    hit = rates.loc[
        rates["sample"].eq(sample)
        & rates["symbol"].eq(symbol)
        & rates["side"].eq(side)
        & rates["filter"].eq(filt)
    ]
    if hit.empty:
        raise KeyError((sample, symbol, side, filt))
    return hit.iloc[0]


def markdown_filter_table(rates: pd.DataFrame, sample: str, symbols: list[str], filt: str) -> list[str]:
    lines = [
        f"| 资产 | 多头 {LABELS[0][1]} | 空头 | 多空合计 |",
        "| --- | --- | --- | --- |",
    ]
    for symbol in symbols:
        long_row = pick_rate(rates, sample, symbol, "long", filt)
        short_row = pick_rate(rates, sample, symbol, "short", filt)
        both_row = pick_rate(rates, sample, symbol, "both", filt)
        label = "合计" if symbol == "ALL" else symbol
        lines.append(
            f"| {label} | {long_row['trend_20_txt']} | {short_row['trend_20_txt']} | {both_row['trend_20_txt']} |"
        )
    return lines


def markdown_stack_table(rates: pd.DataFrame, sample: str, symbol: str) -> list[str]:
    lines = [
        "| 过滤 | 多头 | 空头 | 合计 | 事件数合计 |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for filt in FILTER_ORDER:
        long_row = pick_rate(rates, sample, symbol, "long", filt)
        short_row = pick_rate(rates, sample, symbol, "short", filt)
        both_row = pick_rate(rates, sample, symbol, "both", filt)
        lines.append(
            f"| {FILTER_ZH[filt]} | {long_row['trend_20_txt']} | "
            f"{short_row['trend_20_txt']} | {both_row['trend_20_txt']} | {int(both_row['events'])} |"
        )
    return lines


def markdown_path_table(
    path_rates: pd.DataFrame,
    sample: str,
    symbol: str,
    side: str,
    window: int,
    kind: str,
) -> list[str]:
    subset = path_rates.loc[
        path_rates["sample"].eq(sample)
        & path_rates["symbol"].eq(symbol)
        & path_rates["side"].eq(side)
        & path_rates["window"].eq(window)
        & path_rates["kind"].eq(kind)
    ]
    title = subset["title"].iloc[0] if not subset.empty else kind
    order = {
        "ratio": [item[0] for item in RATIO_BINS],
        "location": [item[0] for item in LOCATION_BINS],
        "drawdown": [item[0] for item in DD_BINS[window]],
        "runup": [item[0] for item in RU_BINS[window]],
    }[kind]
    lines = [
        f"| {title} | 事件 | 20日趋势发生率 |",
        "| --- | ---: | --- |",
    ]
    lookup = {str(row["bin"]): row for _, row in subset.iterrows()}
    for bin_name in order:
        row = lookup.get(bin_name)
        if row is None:
            lines.append(f"| {bin_name} | 0 | n=0 |")
        else:
            lines.append(f"| {bin_name} | {int(row['events'])} | {row['trend_20_txt']} |")
    return lines


def equal_weight_mean(rates: pd.DataFrame, sample: str, side: str, filt: str) -> float:
    values = []
    for symbol in SYMBOLS:
        row = pick_rate(rates, sample, symbol, side, filt)
        if np.isfinite(row["trend_20_p"]):
            values.append(float(row["trend_20_p"]))
    return float(np.mean(values)) if values else float("nan")


def write_report(
    *,
    qualities: list[dict[str, Any]],
    rates: pd.DataFrame,
    path_rates: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    data_start = min(item["start"] for item in qualities)
    data_end = max(item["end"] for item in qualities)
    symbols_line = "、".join(SYMBOLS)
    lines = [
        f"# {FAMILY_NAME}：日K穿越 MA7 后趋势发生率",
        "",
        f"> SCOUT 事件统计，{RUN_DATE}。状态：`explore / diagnostic-only / not promoted / not live-ready`。",
        "> 本报告不是策略、不扣成本、不登记版本、不构成 promotion。",
        "",
        "## 大白话结论",
        "",
        summary["headline"],
        "",
        "## 冻结口径",
        "",
        "- 市场：Binance USD-M 永续；交易对 "
        f"`{symbols_line}`；完整 UTC 日K，由已审计 24 根闭合 `1h` 聚合。",
        f"- 数据来源：`binance_futures_kline_api_direct` feature 层；闭合 K 线 only；缺日即 blocker。",
        f"- 样本：各币上市日至 `{data_end[:10]}`；共同窗口从 `{COMMON_START.date()}` 起；最近 `{RECENT_DAYS}` 日只作审计切片。",
        "- 穿越：前一日收盘在 SMA7 反侧，当日收盘严格站到目标侧；等号不算穿越。`SMA7=mean(close[t-6:t])`。",
        "- 斜率：`(SMA7[t]-SMA7[t-1])/ATR7[t]`；门槛沿用 HYPE SNC02 的 `0.02`。符号过滤只要求同向。",
        "- 放量：当日 `quote_volume` / 近20日 `quote_volume` 中位数；门槛 `1.2/1.5/2.0`，主看 `1.5`。",
        "- 前置路径：窗口 `7/30/60/90` 日，只用 `t-W…t-1` 收盘，不含穿越日。最大回撤=路径峰值到谷值；最大上涨=谷值到峰值；`R=最大上涨/最大回撤`。",
        f"- 主标签 `trend_20`：与 [BIN-1D-TPSA-P1](../../1d-trend-prebreakout-state-atlas/diagnostics/binance-1d-trend-prebreakout-state-atlas-p1-barrier-ml-2026-08-25.md) 相同——以穿越日收盘为原点、穿越前 ATR7 为尺度，随后 {PRIMARY_HORIZON} 个收盘先碰到顺向 `+{FAVORABLE_ATR:g} ATR`，且没有先碰到反向 `-{ADVERSE_ATR:g} ATR`。",
        "- 辅标签：`mfe2_20`（不管顺序，只要顺向走过 2ATR）、`win_20`（第20日收盘仍顺向）、`persist_5`（随后5日收盘仍在 SMA7 同侧）、`recross_ge_5`（5日内不反向穿越）。",
        "- 斜率与放量是穿越当日已知量；前置涨跌是 `t-1` 已知量。标签从下一根日K开始，不用穿越日剩余盘中路径。",
        "- 本统计无手续费、滑点、资金费、下一开盘成交。概率抬升不等于可交易 edge。",
        "- 阈值全部预先写死，不按结果回改。`n<20` 的格子只作观察。",
        "",
        "## 数据质量",
        "",
        "| 交易对 | 日K数 | UTC 起 | UTC 止 | 缺日 | 来源 |",
        "| --- | ---: | --- | --- | ---: | --- |",
    ]
    for item in qualities:
        lines.append(
            f"| {item['symbol']} | {item['rows']} | {item['start'][:10]} | {item['end'][:10]} | "
            f"{item['missing_bars']} | `{item['source'][0]}` |"
        )
    lines.extend(
        [
            "",
            f"共同窗口与最近一年均锚定数据集终点 `{data_end[:10]}`，不是脚本运行时的墙上时钟。",
            "",
            "## 1. 裸穿越后发生趋势的几率",
            "",
            "全历史、每个币自己的上市日起：",
            "",
        ]
    )
    lines.extend(markdown_filter_table(rates, "full", ["ALL", *SYMBOLS], "cross"))
    lines.extend(
        [
            "",
            "共同窗口（四币对齐，从 SOL 上市日 2020-09-15 起）合计：",
            "",
        ]
    )
    lines.extend(markdown_filter_table(rates, "common", ["ALL", *SYMBOLS], "cross"))
    full_both = pick_rate(rates, "full", "ALL", "both", "cross")
    common_both = pick_rate(rates, "common", "ALL", "both", "cross")
    ew_full = equal_weight_mean(rates, "full", "both", "cross")
    lines.extend(
        [
            "",
            (
                f"事件加权全历史合计 `{full_both['trend_20_txt']}`；"
                f"四币等权平均 `{fmt_pct(ew_full)}`；共同窗口合计 `{common_both['trend_20_txt']}`。"
            ),
            "对照：全市场永续 TPSA-P1 的 MA7 趋势发生率是多头 27.90%、空头 31.04%。本四币合计同量级，但这里多头高于空头，与全市场样本方向相反。",
            "",
            "同一批裸穿越的辅标签（四币合计，全历史）：",
            "",
            "| 标签 | 含义 | 合计 |",
            "| --- | --- | --- |",
            f"| `trend_20` | 先到 +2ATR 且未先到 -1ATR | {full_both['trend_20_txt']} |",
            f"| `mfe2_20` | 20 日内顺向走过 2ATR（不管顺序） | {full_both['mfe2_20_txt']} |",
            f"| `win_20` | 第 20 日收盘仍顺向 | {full_both['win_20_txt']} |",
            f"| `persist_5` | 随后 5 日收盘仍在 SMA7 同侧 | {full_both['persist_5_txt']} |",
            f"| `recross_ge_5` | 5 日内不再反向穿越 | {full_both['recross_ge_5_txt']} |",
            "",
            "`win_20` 接近一半，说明“20 日后还在顺向”几乎是抛硬币；主标签更严，要求先走出一段顺向波动而不是先被打回。事件数略大于有标签样本，因为最后 20 根日K没有完整前瞻。",
            "",
            "## 2. 要求 MA7 同向斜率之后",
            "",
            "全历史，斜率符号：",
            "",
        ]
    )
    lines.extend(markdown_filter_table(rates, "full", ["ALL", *SYMBOLS], "slope_sign"))
    lines.extend(["", f"全历史，斜率 ≥ `{SLOPE_ATR_THRESHOLD}×ATR7`：", ""])
    lines.extend(markdown_filter_table(rates, "full", ["ALL", *SYMBOLS], "slope_002"))
    lines.extend(
        [
            "",
            "## 3. 再加上成交额放大之后",
            "",
            "全历史，quote 成交额 ≥ 1.5×20 日中位：",
            "",
        ]
    )
    lines.extend(markdown_filter_table(rates, "full", ["ALL", *SYMBOLS], "vol_1p5"))
    lines.extend(["", "全历史，斜率 0.02 + 放量 1.5×：", ""])
    lines.extend(markdown_filter_table(rates, "full", ["ALL", *SYMBOLS], "slope_002+vol_1p5"))
    lines.extend(
        [
            "",
            "## 4. 前置上涨/回撤后再穿越",
            "",
            "比值 `R = 窗口内最大上涨 / 最大回撤`。多头 R<1 表示穿越前这段更像先跌后修；空头 R>1 表示穿越前这段更像先涨后转弱。",
            "",
            "### 30 日比值（全历史，四币合计）",
            "",
            "多头：",
            "",
        ]
    )
    lines.extend(markdown_path_table(path_rates, "full", "ALL", "long", 30, "ratio"))
    lines.extend(["", "空头：", ""])
    lines.extend(markdown_path_table(path_rates, "full", "ALL", "short", 30, "ratio"))
    lines.extend(["", "多空合计：", ""])
    lines.extend(markdown_path_table(path_rates, "full", "ALL", "both", 30, "ratio"))
    lines.extend(
        [
            "",
            "### 30 日最大回撤 / 最大上涨（全历史，四币合计）",
            "",
            "多头、按穿越前 30 日最大回撤：",
            "",
        ]
    )
    lines.extend(markdown_path_table(path_rates, "full", "ALL", "long", 30, "drawdown"))
    lines.extend(["", "空头、按穿越前 30 日最大上涨：", ""])
    lines.extend(markdown_path_table(path_rates, "full", "ALL", "short", 30, "runup"))
    lines.extend(
        [
            "",
            "### 7 / 60 / 90 日比值（全历史，四币合计，多空合并）",
            "",
        ]
    )
    for window in (7, 60, 90):
        lines.append(f"#### {window} 日")
        lines.append("")
        lines.extend(markdown_path_table(path_rates, "full", "ALL", "both", window, "ratio"))
        lines.append("")
    lines.extend(
        [
            "预先指定的“多头 R<1 / 空头 R>1”并没有抬升合计发生率。格子里真正偏离基准的是："
            "7 日回撤主导 `R<0.5` 合计 37.2%；多头 30 日 `R≥2` 39.1%，而多头 30 日 `R<0.5` 只有 24.4%；"
            "空头 30 日 `R≥2` 降到 20.6%。四个大币更像“顺势延续”，深回撤或大涨之后的反向穿越更差。"
            "这些是预指定分桶的观察，不是新搜索出的过滤器。",
            "",
            "分币、分方向、分回撤/上涨/位置的完整格子见 [path rates CSV]("
            f"../artifacts/binance_1d_ma7_ctp_path_rates_{RUN_DATE}.csv)。",
            "",
            "## 5. 分币过滤栈（全历史）",
            "",
        ]
    )
    for symbol in ["ALL", *SYMBOLS]:
        title = "四币合计" if symbol == "ALL" else symbol
        lines.append(f"### {title}")
        lines.append("")
        lines.extend(markdown_stack_table(rates, "full", symbol))
        lines.append("")
    lines.extend(
        [
            "## 6. 最近一年审计切片",
            "",
            "只报告，不用于挑选过滤。四币合计、裸穿越：",
            "",
        ]
    )
    lines.extend(markdown_filter_table(rates, "1y", ["ALL", *SYMBOLS], "cross"))
    lines.extend(["", "最近一年、斜率 0.02 + 放量 1.5×：", ""])
    lines.extend(markdown_filter_table(rates, "1y", ["ALL", *SYMBOLS], "slope_002+vol_1p5"))
    lines.extend(
        [
            "",
            "## 与已有结论的关系",
            "",
            "- [HYPE 对称裸 cross+slope](../../../hype/1d-ma7-asymmetric-body-trend/specs/hype-1d-ma7-symmetric-naked-cross-slope-diagnostic-contract-2026-08-20.md) 把 `0.02×ATR7` 斜率当作入场资格，不是趋势发生率估计。",
            "- [BIN-1D-TPSA-P1](../../1d-trend-prebreakout-state-atlas/diagnostics/binance-1d-trend-prebreakout-state-atlas-p1-barrier-ml-2026-08-25.md) 在全市场永续上给出同类 `trend_20` 基准，并指出更像“下跌/回撤后的低波稳定区向上脱离”，而不是高效率现成趋势。本四币 30 日 `R<1` 过滤并未复制该结构。",
            "- [BIN-1D-MA7-RC-P3](../../1d-ma7-regime-continuation/diagnostics/binance-1d-ma7-regime-continuation-p3-confirmatory-2026-08-25.md) 已经否决把斜率/效率/波动路径写成跨资产可交易规则。本统计即使看到条件概率抬升，也不撤回该 NO-GO。",
            "",
            "## 裁决",
            "",
            summary["verdict_block"],
            "",
            "## 文件",
            "",
            f"- [事件表](../artifacts/binance_1d_ma7_ctp_events_{RUN_DATE}.csv)",
            f"- [过滤发生率](../artifacts/binance_1d_ma7_ctp_rates_{RUN_DATE}.csv)",
            f"- [路径分桶](../artifacts/binance_1d_ma7_ctp_path_rates_{RUN_DATE}.csv)",
            f"- [汇总 JSON](../artifacts/binance_1d_ma7_ctp_summary_{RUN_DATE}.json)",
            f"- [复现脚本](../scripts/research_binance_1d_ma7_cross_trend_probability.py)",
            "",
        ]
    )
    OUTPUTS["report"].parent.mkdir(parents=True, exist_ok=True)
    OUTPUTS["report"].write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_headline(rates: pd.DataFrame) -> tuple[str, str]:
    base = pick_rate(rates, "full", "ALL", "both", "cross")
    long_base = pick_rate(rates, "full", "ALL", "long", "cross")
    short_base = pick_rate(rates, "full", "ALL", "short", "cross")
    slope = pick_rate(rates, "full", "ALL", "both", "slope_002")
    vol = pick_rate(rates, "full", "ALL", "both", "vol_1p5")
    stack = pick_rate(rates, "full", "ALL", "both", "slope_002+vol_1p5")
    path = pick_rate(rates, "full", "ALL", "both", "path_ratio30_reclaim_or_fade")
    stacked_path = pick_rate(
        rates, "full", "ALL", "both", "slope_002+vol_1p5+ratio30_reclaim_or_fade"
    )
    per_coin = []
    for symbol in SYMBOLS:
        row = pick_rate(rates, "full", symbol, "both", "cross")
        per_coin.append(f"`{symbol}` {row['trend_20_txt']}")
    headline = (
        f"四个永续日K在收盘穿越 SMA7 之后，约有 **{fmt_pct(float(base['trend_20_p']))}** 会在 20 日内先走出顺向 2 个 ATR、且没有先被反向 1 个 ATR 打掉"
        f"（多头 {fmt_pct(float(long_base['trend_20_p']))}，空头 {fmt_pct(float(short_base['trend_20_p']))}）。"
        f"要求 MA7 同向斜率 ≥ 0.02×ATR7 后为 {fmt_pct(float(slope['trend_20_p']))}；"
        f"要求穿越日成交额放大 1.5 倍后为 {fmt_pct(float(vol['trend_20_p']))}；"
        f"两者同时要求后为 {fmt_pct(float(stack['trend_20_p']))}。"
        f"若再按 30 日上涨/回撤比做方向过滤（多头 R<1、空头 R>1），单独使用为 {fmt_pct(float(path['trend_20_p']))}，"
        f"与斜率+放量叠加后为 {fmt_pct(float(stacked_path['trend_20_p']))}。"
        "这些过滤最多是把“会走出一段趋势”的条件概率轻轻挪动，没有把多数穿越变成高把握趋势。"
    )
    lifts = []
    for name, row in (
        ("斜率0.02", slope),
        ("放量1.5×", vol),
        ("斜率+放量", stack),
        ("30日R方向", path),
        ("斜率+放量+30日R", stacked_path),
    ):
        if np.isfinite(row["trend_20_p"]) and np.isfinite(base["trend_20_p"]) and base["trend_20_p"] > 0:
            lifts.append(f"{name} {float(row['trend_20_p']) / float(base['trend_20_p']):.2f}×")
    verdict = (
        "Verdict: **ITERATE / 不是策略**。\n\n"
        f"- 裸穿越并不是废事件，四币合计 20 日趋势发生率 {base['trend_20_txt']}；分币为 "
        + "；".join(per_coin)
        + "。\n"
        f"- 斜率、放量、前置涨跌比都能改变发生率，但抬升有限（相对裸穿越：{', '.join(lifts)}），且样本随过滤快速变薄。\n"
        "- Confidence: **MEDIUM**。口径与 TPSA 可对照，四币历史完整、无缺日；这不是 OOS，也不是扣成本后的交易期望。\n"
        "- Warning：把条件概率当成入场胜率会高估；`win_20` 和 `trend_20` 不是一回事，先走出 2ATR 仍可能在第20日亏钱。\n"
        "- Next：不要在本样本上继续堆过滤。若继续，应另冻一条假设（例如 7 日回撤后再上穿，或拒绝 30 日极端延伸后的反向穿越），用未揭示窗口确认。"
    )
    return headline, verdict


def self_test() -> None:
    idx = pd.date_range("2024-01-01", periods=40, freq="1D", tz="UTC")
    close = np.full(40, 100.0)
    close[10:17] = np.linspace(100.0, 90.0, 7)
    close[17:] = np.linspace(90.0, 130.0, 23)
    frame = pd.DataFrame(
        {
            "ts": idx,
            "open": close,
            "high": close + 0.4,
            "low": close - 0.4,
            "close": close,
            "volume": 1000.0,
            "quote_volume": np.linspace(1.0e6, 3.0e6, 40),
            "trade_count": 10,
            "vwap": close,
            "is_closed": True,
            "source": "self-test",
        }
    )
    framed = add_indicators(frame)
    events = build_events("TESTUSDT", framed)
    long_events = events.loc[events["side"].eq("long")]
    if long_events.empty:
        raise RuntimeError("self-test expected at least one long SMA7 cross")
    if not (long_events["trend_20"].fillna(0.0) > 0).any():
        raise RuntimeError("self-test expected a long trend_20 success after the forced rally")


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return

    qualities: list[dict[str, Any]] = []
    event_frames: list[pd.DataFrame] = []
    for symbol, (_base, display, slug) in SYMBOLS.items():
        daily, quality = load_daily(symbol, slug, display)
        qualities.append(quality)
        events = build_events(symbol, add_indicators(daily))
        if events.empty:
            raise RuntimeError(f"{symbol} produced no MA7 crosses")
        event_frames.append(events)
    all_events = pd.concat(event_frames, ignore_index=True)
    data_end = pd.to_datetime(max(item["end"] for item in qualities), utc=True)

    rate_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    sliced = {
        "full": window_slice(all_events, "full", data_end),
        "common": window_slice(all_events, "common", data_end),
        "1y": window_slice(all_events, "1y", data_end),
    }
    for sample, frame in sliced.items():
        rate_rows.extend(rate_table(frame, sample))
        path_rows.extend(path_table(frame, sample))
    rates = pd.DataFrame(rate_rows)
    path_rates = pd.DataFrame(path_rows)
    headline, verdict = build_headline(rates)
    summary = {
        "family": FAMILY_NAME,
        "alias": FAMILY_ALIAS,
        "run_date": RUN_DATE,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "explore / diagnostic-only / not promoted / not live-ready",
        "data": qualities,
        "common_start": COMMON_START.isoformat(),
        "primary_label": "trend_20",
        "headline": headline,
        "verdict_block": verdict,
        "event_counts": {
            sample: {
                "rows": int(len(frame)),
                "long": int(frame["side"].eq("long").sum()),
                "short": int(frame["side"].eq("short").sum()),
            }
            for sample, frame in sliced.items()
        },
        "outputs": {key: str(path.relative_to(ROOT)) for key, path in OUTPUTS.items()},
    }

    for path in OUTPUTS.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    all_events.to_csv(OUTPUTS["events"], index=False)
    rates.to_csv(OUTPUTS["rates"], index=False)
    path_rates.to_csv(OUTPUTS["path_rates"], index=False)
    OUTPUTS["summary"].write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(qualities=qualities, rates=rates, path_rates=path_rates, summary=summary)
    print(json.dumps({"events": int(len(all_events)), "report": str(OUTPUTS["report"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
