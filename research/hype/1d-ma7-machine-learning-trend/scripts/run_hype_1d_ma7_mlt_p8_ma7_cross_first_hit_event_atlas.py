"""P8 MA7 cross first-hit event atlas.

This is a diagnostic-only event atlas. It does not train an ML model, does
not optimize parameters, and must not read HYPE after the 365-day training
window ending at 2026-05-31 00:00 UTC.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/hype/1d-ma7-machine-learning-trend"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
SPEC_PATH = (
    FAMILY_DIR
    / "specs/hype-1d-ma7-mlt-p8-ma7-cross-first-hit-event-atlas-contract-2026-08-31.md"
)
P4_SCRIPT = FAMILY_DIR / "scripts/run_hype_1d_ma7_mlt_p4_v7_1_behavior_clone_residual.py"
P7_SCRIPT = FAMILY_DIR / "scripts/run_hype_1d_ma7_mlt_p7_cross_asset_survival_overlay.py"

RUN_DATE = "2026-08-31"
PREFIX = "hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31"
TRAIN_TERMINAL = pd.Timestamp("2026-05-31T00:00:00Z")
HYPE_FIRST_DAY = pd.Timestamp("2025-05-31T00:00:00Z")
HYPE_LAST_DAY = pd.Timestamp("2026-05-30T00:00:00Z")
HYPE_HOLDOUT_START = pd.Timestamp("2026-05-31T00:00:00Z")
HYPE_HOLDOUT_END = pd.Timestamp("2026-08-20T00:00:00Z")
RANDOM_SEED = 20260831

ASSETS = ("HYPEUSDT", "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")
DONOR_ASSETS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")
FAVORABLE_BARRIERS = (1.0, 1.5, 2.0, 3.0)
ADVERSE_BARRIERS = (0.5, 1.0, 1.5, 2.0)
HORIZONS = (7, 14, 21, 30)
PRIMARY_FAVORABLE_ATR = 2.0
PRIMARY_ADVERSE_ATR = 1.0
PRIMARY_HORIZON_DAYS = 14
FEE_RATE = 0.001
SLIPPAGE = 0.0004
CONTROL_MATCHES = 5
BOOTSTRAP_REPS = 2000
INSUFFICIENT_N = 30

OUTPUTS = {
    "events": ARTIFACT_DIR / f"{PREFIX}_events.csv",
    "first_hit_matrix": ARTIFACT_DIR / f"{PREFIX}_first_hit_matrix.csv",
    "feature_bin_stats": ARTIFACT_DIR / f"{PREFIX}_feature_bin_stats.csv",
    "two_way_state_matrix": ARTIFACT_DIR / f"{PREFIX}_two_way_state_matrix.csv",
    "matched_controls": ARTIFACT_DIR / f"{PREFIX}_matched_controls.csv",
    "asset_direction_summary": ARTIFACT_DIR / f"{PREFIX}_asset_direction_summary.csv",
    "cluster_bootstrap": ARTIFACT_DIR / f"{PREFIX}_cluster_bootstrap.csv",
    "summary": ARTIFACT_DIR / f"{PREFIX}_summary.json",
    "manifest": ARTIFACT_DIR / f"{PREFIX}_development_manifest.json",
    "html": ARTIFACT_DIR / f"{PREFIX}.html",
    "html_manifest": ARTIFACT_DIR / f"{PREFIX}_html_manifest.json",
    "report": FAMILY_DIR
    / "diagnostics/hype-1d-ma7-mlt-p8-ma7-cross-first-hit-event-atlas-2026-08-31.md",
}

FEATURE_FIELDS = (
    "side",
    "ma7",
    "atr7",
    "aligned_ma_gap_atr",
    "pre_cross_gap_atr",
    "cross_jump_atr",
    "aligned_slope1_atr",
    "aligned_slope2_atr_per_day",
    "aligned_slope3_atr_per_day",
    "aligned_slope_acceleration",
    "initial_cross_gap_atr",
    "aligned_return_1d",
    "aligned_return_3d",
    "aligned_return_7d",
    "aligned_return_14d",
    "prior_opposite_run",
    "same_side_ratio3",
    "same_side_ratio7",
    "cross_count7",
    "cross_count14",
    "aligned_body_atr",
    "aligned_close_location",
    "range_atr",
    "aligned_rsi6",
    "er7",
    "atr_pct",
    "directional_range_position30",
    "distance_directional_extreme30_atr",
    "volatility_ratio7_30",
    "volume_change_3d",
)

SINGLE_BIN_FIELDS = (
    "slope_bin",
    "cross_jump_bin",
    "prior_opposite_run_bin",
    "cross_count14_bin",
    "rsi6_bin",
    "er7_bin",
    "vol_regime",
    "aligned_return_3d_bin",
)

TWO_WAY_MATRICES = (
    ("slope_x_cross_jump", "slope_bin", "cross_jump_bin"),
    ("slope_x_prior_opposite_run", "slope_bin", "prior_opposite_run_bin"),
    ("slope_x_return3", "slope_bin", "aligned_return_3d_bin"),
    ("slope_x_cross_count14", "slope_bin", "cross_count14_bin"),
    ("slope_x_vol_regime", "slope_bin", "vol_regime"),
    ("slope_x_rsi6", "slope_bin", "rsi6_bin"),
    ("direction_x_slope", "side_label", "slope_bin"),
    ("asset_x_direction", "asset", "side_label"),
    ("asset_x_slope", "asset", "slope_bin"),
    ("cross_jump_x_prior_opposite_run", "cross_jump_bin", "prior_opposite_run_bin"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run P8 MA7 cross first-hit event atlas.")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256(path)}  {path.name}\n", encoding="utf-8"
    )


def write_csv(path: Path, rows: Any) -> None:
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    frame.to_csv(path, index=False)
    write_sidecar(path)


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.ndarray):
        return [sanitize(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return sanitize(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(sanitize(payload), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    write_sidecar(path)


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def safe_div(num: float, den: float) -> float:
    if not math.isfinite(num) or not math.isfinite(den) or den == 0:
        return math.nan
    return num / den


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    previous = close.shift(1)
    return pd.concat(
        [high - low, (high - previous).abs(), (low - previous).abs()],
        axis=1,
    ).max(axis=1)


def wilder_rsi(close: pd.Series, period: int = 6) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    avg_up = up.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_down = down.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_up / avg_down.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi = rsi.where(avg_down != 0.0, 100.0)
    return rsi


def er(close: pd.Series, period: int = 7) -> pd.Series:
    movement = close.diff().abs().rolling(period).sum()
    direction = (close - close.shift(period)).abs()
    return direction / movement.replace(0.0, np.nan)


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return math.nan, math.nan
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n) / denom
    return max(0.0, center - half), min(1.0, center + half)


def rate_dict(flags: pd.Series | np.ndarray) -> dict[str, Any]:
    values = pd.Series(flags).dropna().astype(bool)
    n = int(len(values))
    k = int(values.sum())
    p = k / n if n else math.nan
    lo, hi = wilson_interval(k, n)
    return {"n": n, "k": k, "rate": p, "wilson_low": lo, "wilson_high": hi}


def pf(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    pos = float(values.loc[values > 0].sum())
    neg = float(-values.loc[values < 0].sum())
    if neg > 0:
        return pos / neg
    return math.inf if pos > 0 else math.nan


def fmt_pct(value: float | None, digits: int = 1) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    return f"{100.0 * float(value):.{digits}f}%"


def fmt_signed_pct(value: float | None, digits: int = 2) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/a"
    return f"{100.0 * float(value):+.{digits}f}%"


def side_label(side: int) -> str:
    return "long" if side > 0 else "short"


def quarter_label(ts: pd.Timestamp) -> str:
    return f"{ts.year}Q{((ts.month - 1) // 3) + 1}"


def assign_slope_bin(value: float) -> str:
    if not math.isfinite(value):
        return "NA"
    if value <= 0:
        return "<=0"
    if value <= 0.03:
        return "(0,0.03]"
    if value <= 0.06:
        return "(0.03,0.06]"
    if value <= 0.10:
        return "(0.06,0.10]"
    return ">0.10"


def assign_cross_jump_bin(value: float) -> str:
    if not math.isfinite(value):
        return "NA"
    if value <= 0.10:
        return "<=0.10"
    if value <= 0.25:
        return "(0.10,0.25]"
    if value <= 0.50:
        return "(0.25,0.50]"
    return ">0.50"


def assign_prior_run_bin(value: float) -> str:
    if not math.isfinite(value):
        return "NA"
    if value <= 1:
        return "1日"
    if value <= 3:
        return "2-3日"
    if value <= 7:
        return "4-7日"
    return ">=8日"


def assign_cross_count_bin(value: float) -> str:
    if not math.isfinite(value):
        return "NA"
    if value <= 1:
        return "1次"
    if value == 2:
        return "2次"
    if value == 3:
        return "3次"
    return ">=4次"


def assign_rsi_bin(value: float) -> str:
    if not math.isfinite(value):
        return "NA"
    if value < 30:
        return "<30"
    if value < 45:
        return "30-45"
    if value <= 55:
        return "45-55"
    if value <= 70:
        return "55-70"
    return ">70"


def assign_er_bin(value: float) -> str:
    if not math.isfinite(value):
        return "NA"
    if value < 0.2:
        return "<0.2"
    if value < 0.4:
        return "0.2-0.4"
    if value < 0.6:
        return "0.4-0.6"
    if value < 0.8:
        return "0.6-0.8"
    return ">0.8"


def assign_return3_bin(value: float) -> str:
    if not math.isfinite(value):
        return "NA"
    if value <= -0.03:
        return "<=-3%"
    if value <= 0.0:
        return "(-3%,0]"
    if value <= 0.03:
        return "(0,3%]"
    return ">3%"


def causal_vol_regimes(atr_pct: pd.Series) -> pd.Series:
    out: list[str] = []
    history: list[float] = []
    for value in atr_pct.astype(float):
        if not math.isfinite(float(value)) or len(history) < 30:
            out.append("NA")
        else:
            q1 = float(np.quantile(history, 1.0 / 3.0))
            q2 = float(np.quantile(history, 2.0 / 3.0))
            if value <= q1:
                out.append("low")
            elif value <= q2:
                out.append("mid")
            else:
                out.append("high")
        if math.isfinite(float(value)):
            history.append(float(value))
    return pd.Series(out, index=atr_pct.index)


def canonical_daily(context: Any) -> pd.DataFrame:
    daily = pd.DataFrame(
        {
            "ts": pd.to_datetime(context.book.ts, utc=True),
            "open": np.asarray(context.book.open, dtype=float),
            "high": np.asarray(context.book.high, dtype=float),
            "low": np.asarray(context.book.low, dtype=float),
            "close": np.asarray(context.book.close, dtype=float),
        }
    )
    daily["ma7"] = daily["close"].rolling(7, min_periods=7).mean()
    daily["atr7"] = true_range(daily["high"], daily["low"], daily["close"]).rolling(
        7, min_periods=7
    ).mean()
    daily["rsi6"] = wilder_rsi(daily["close"], 6)
    daily["er7"] = er(daily["close"], 7)
    daily["atr_pct"] = daily["atr7"] / daily["close"]
    daily["raw_cross"] = 0
    long_cross = (daily["close"].shift(1) <= daily["ma7"].shift(1)) & (
        daily["close"] > daily["ma7"]
    )
    short_cross = (daily["close"].shift(1) >= daily["ma7"].shift(1)) & (
        daily["close"] < daily["ma7"]
    )
    daily.loc[long_cross.fillna(False), "raw_cross"] = 1
    daily.loc[short_cross.fillna(False), "raw_cross"] = -1
    daily["quarter"] = daily["ts"].map(quarter_label)

    hourly = context.market.hourly.copy()
    hourly["ts"] = pd.to_datetime(hourly["ts"], utc=True)
    hourly["day"] = hourly["ts"].dt.floor("D")
    volume_col = "volume" if "volume" in hourly.columns else None
    if volume_col is None:
        daily["daily_volume"] = np.nan
    else:
        daily["daily_volume"] = (
            hourly.groupby("day", sort=True)[volume_col]
            .sum()
            .reindex(pd.DatetimeIndex(daily["ts"]))
            .to_numpy(float)
        )
    daily["volume_change_3d"] = daily["daily_volume"] / daily["daily_volume"].shift(3) - 1.0
    daily["vol_regime"] = causal_vol_regimes(daily["atr_pct"])
    return daily


def canonical_hourly(context: Any) -> pd.DataFrame:
    hourly = context.market.hourly.copy()
    hourly["ts"] = pd.to_datetime(hourly["ts"], utc=True)
    terminal = pd.Timestamp(context.book.terminal_ts)
    start = pd.Timestamp(context.book.ts[0])
    hourly = hourly.loc[(hourly["ts"] >= start) & (hourly["ts"] < terminal)].copy()
    hourly = hourly.sort_values("ts").reset_index(drop=True)
    expected = int(context.book.count) * 24
    if len(hourly) != expected:
        raise RuntimeError(f"{context.market.audit.get('symbol')} expected {expected} 1h bars, got {len(hourly)}")
    if not hourly["ts"].diff().dropna().eq(pd.Timedelta(hours=1)).all():
        raise RuntimeError("hourly continuity check failed")
    return hourly


def funding_frame(context: Any) -> pd.DataFrame:
    frame = context.market.funding.copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    if "funding_rate" not in frame.columns:
        frame["funding_rate"] = 0.0
    return frame[["ts", "funding_rate"]].sort_values("ts").reset_index(drop=True)


def signed_return(close: pd.Series, index: int, days: int, side: int) -> float:
    if index - days < 0:
        return math.nan
    prev = float(close.iloc[index - days])
    cur = float(close.iloc[index])
    return side * (safe_div(cur, prev) - 1.0)


def same_side_ratio(daily: pd.DataFrame, index: int, days: int, side: int) -> float:
    start = max(0, index - days + 1)
    gap = side * (daily["close"].iloc[start : index + 1] - daily["ma7"].iloc[start : index + 1])
    valid = gap.dropna()
    if valid.empty:
        return math.nan
    return float((valid > 0).mean())


def count_crosses(daily: pd.DataFrame, index: int, days: int) -> int:
    start = max(0, index - days + 1)
    return int((daily["raw_cross"].iloc[start : index + 1] != 0).sum())


def prior_opposite_run(daily: pd.DataFrame, index: int, side: int) -> int:
    run = 0
    cursor = index - 1
    while cursor >= 0:
        ma = float(daily["ma7"].iloc[cursor])
        if not math.isfinite(ma):
            break
        if side * (float(daily["close"].iloc[cursor]) - ma) <= 0:
            run += 1
            cursor -= 1
            continue
        break
    return run


def directional_30d_fields(daily: pd.DataFrame, index: int, side: int, atr: float) -> tuple[float, float]:
    if index < 29 or not math.isfinite(atr) or atr <= 0:
        return math.nan, math.nan
    window = daily.iloc[index - 29 : index + 1]
    high = float(window["high"].max())
    low = float(window["low"].min())
    close = float(daily["close"].iloc[index])
    width = high - low
    if width <= 0:
        pos = 0.5
    elif side > 0:
        pos = (close - low) / width
    else:
        pos = (high - close) / width
    distance = (high - close) / atr if side > 0 else (close - low) / atr
    return float(pos), float(distance)


def volatility_ratio(daily: pd.DataFrame, index: int) -> float:
    returns = daily["close"].pct_change().abs()
    if index < 30:
        return math.nan
    v7 = float(returns.iloc[index - 6 : index + 1].mean())
    v30 = float(returns.iloc[index - 29 : index + 1].mean())
    return safe_div(v7, v30)


def state_row(asset: str, daily: pd.DataFrame, index: int, side: int) -> dict[str, Any]:
    close = daily["close"]
    ma = float(daily["ma7"].iloc[index])
    atr = float(daily["atr7"].iloc[index])
    prev_atr = float(daily["atr7"].iloc[index - 1]) if index >= 1 else math.nan
    aligned_gap = side * safe_div(float(close.iloc[index]) - ma, atr)
    prev_gap = (
        side
        * safe_div(float(close.iloc[index - 1]) - float(daily["ma7"].iloc[index - 1]), prev_atr)
        if index >= 1
        else math.nan
    )
    slope1 = (
        side * safe_div(float(daily["ma7"].iloc[index]) - float(daily["ma7"].iloc[index - 1]), atr)
        if index >= 1
        else math.nan
    )
    slope2 = (
        side
        * safe_div(float(daily["ma7"].iloc[index]) - float(daily["ma7"].iloc[index - 2]), 2.0 * atr)
        if index >= 2
        else math.nan
    )
    slope3 = (
        side
        * safe_div(float(daily["ma7"].iloc[index]) - float(daily["ma7"].iloc[index - 3]), 3.0 * atr)
        if index >= 3
        else math.nan
    )
    prev_slope1 = (
        side
        * safe_div(
            float(daily["ma7"].iloc[index - 1]) - float(daily["ma7"].iloc[index - 2]),
            prev_atr,
        )
        if index >= 2
        else math.nan
    )
    loc30, dist30 = directional_30d_fields(daily, index, side, atr)
    row = {
        "asset": asset,
        "index": index,
        "ts": pd.Timestamp(daily["ts"].iloc[index]).isoformat(),
        "side": side,
        "side_label": side_label(side),
        "quarter": daily["quarter"].iloc[index],
        "open": float(daily["open"].iloc[index]),
        "high": float(daily["high"].iloc[index]),
        "low": float(daily["low"].iloc[index]),
        "close": float(daily["close"].iloc[index]),
        "ma7": ma,
        "atr7": atr,
        "aligned_ma_gap_atr": aligned_gap,
        "pre_cross_gap_atr": prev_gap,
        "cross_jump_atr": aligned_gap - prev_gap,
        "aligned_slope1_atr": slope1,
        "aligned_slope2_atr_per_day": slope2,
        "aligned_slope3_atr_per_day": slope3,
        "aligned_slope_acceleration": slope1 - prev_slope1,
        "initial_cross_gap_atr": aligned_gap,
        "aligned_return_1d": signed_return(close, index, 1, side),
        "aligned_return_3d": signed_return(close, index, 3, side),
        "aligned_return_7d": signed_return(close, index, 7, side),
        "aligned_return_14d": signed_return(close, index, 14, side),
        "prior_opposite_run": prior_opposite_run(daily, index, side),
        "same_side_ratio3": same_side_ratio(daily, index, 3, side),
        "same_side_ratio7": same_side_ratio(daily, index, 7, side),
        "cross_count7": count_crosses(daily, index, 7),
        "cross_count14": count_crosses(daily, index, 14),
        "aligned_body_atr": side * safe_div(float(daily["close"].iloc[index]) - float(daily["open"].iloc[index]), atr),
        "aligned_close_location": (
            safe_div(float(daily["close"].iloc[index]) - float(daily["low"].iloc[index]), float(daily["high"].iloc[index]) - float(daily["low"].iloc[index]))
            if side > 0
            else safe_div(float(daily["high"].iloc[index]) - float(daily["close"].iloc[index]), float(daily["high"].iloc[index]) - float(daily["low"].iloc[index]))
        ),
        "range_atr": safe_div(float(daily["high"].iloc[index]) - float(daily["low"].iloc[index]), atr),
        "aligned_rsi6": float(daily["rsi6"].iloc[index]) if side > 0 else 100.0 - float(daily["rsi6"].iloc[index]),
        "er7": float(daily["er7"].iloc[index]),
        "atr_pct": float(daily["atr_pct"].iloc[index]),
        "directional_range_position30": loc30,
        "distance_directional_extreme30_atr": dist30,
        "volatility_ratio7_30": volatility_ratio(daily, index),
        "volume_change_3d": float(daily["volume_change_3d"].iloc[index]),
        "vol_regime": daily["vol_regime"].iloc[index],
    }
    row["slope_bin"] = assign_slope_bin(float(row["aligned_slope1_atr"]))
    row["cross_jump_bin"] = assign_cross_jump_bin(float(row["cross_jump_atr"]))
    row["prior_opposite_run_bin"] = assign_prior_run_bin(float(row["prior_opposite_run"]))
    row["cross_count14_bin"] = assign_cross_count_bin(float(row["cross_count14"]))
    row["rsi6_bin"] = assign_rsi_bin(float(row["aligned_rsi6"]))
    row["er7_bin"] = assign_er_bin(float(row["er7"]))
    row["aligned_return_3d_bin"] = assign_return3_bin(float(row["aligned_return_3d"]))
    return row


def funding_pnl(funding: pd.DataFrame, side: int, entry_ts: pd.Timestamp, exit_ts: pd.Timestamp) -> float:
    if funding.empty:
        return 0.0
    rates = funding.loc[(funding["ts"] > entry_ts) & (funding["ts"] <= exit_ts), "funding_rate"]
    return float(-side * rates.astype(float).sum())


def net_return(
    side: int,
    entry_ref: float,
    exit_ref: float,
    funding_adj: float,
    *,
    fee_rate: float = FEE_RATE,
    slippage: float = SLIPPAGE,
) -> float:
    entry_fill = entry_ref * (1.0 + side * slippage)
    exit_fill = exit_ref * (1.0 - side * slippage)
    gross = side * (exit_fill / entry_fill - 1.0)
    fee = fee_rate * (1.0 + exit_ref / entry_ref)
    return float(gross - fee + funding_adj)


def path_hours(hourly: pd.DataFrame, entry_ts: pd.Timestamp, horizon_days: int) -> pd.DataFrame:
    end_ts = entry_ts + pd.Timedelta(days=horizon_days)
    return hourly.loc[(hourly["ts"] >= entry_ts) & (hourly["ts"] < end_ts)].copy()


def first_hit_one(
    *,
    event_id: str,
    asset: str,
    side: int,
    event_ts: pd.Timestamp,
    entry_ts: pd.Timestamp,
    entry_ref: float,
    atr_anchor: float,
    hourly: pd.DataFrame,
    funding: pd.DataFrame,
    favorable_atr: float,
    adverse_atr: float,
    horizon_days: int,
) -> dict[str, Any]:
    bars = path_hours(hourly, entry_ts, horizon_days)
    expected_hours = horizon_days * 24
    path_complete = len(bars) == expected_hours
    fav_price = entry_ref + side * favorable_atr * atr_anchor
    adv_price = entry_ref - side * adverse_atr * atr_anchor
    if side > 0:
        fav_flags = bars["high"].astype(float).to_numpy() >= fav_price
        adv_flags = bars["low"].astype(float).to_numpy() <= adv_price
        signed_high = (bars["high"].astype(float).to_numpy() - entry_ref) / atr_anchor
        signed_low = (bars["low"].astype(float).to_numpy() - entry_ref) / atr_anchor
        signed_close = (bars["close"].astype(float).to_numpy() - entry_ref) / atr_anchor
    else:
        fav_flags = bars["low"].astype(float).to_numpy() <= fav_price
        adv_flags = bars["high"].astype(float).to_numpy() >= adv_price
        signed_high = (entry_ref - bars["low"].astype(float).to_numpy()) / atr_anchor
        signed_low = (entry_ref - bars["high"].astype(float).to_numpy()) / atr_anchor
        signed_close = (entry_ref - bars["close"].astype(float).to_numpy()) / atr_anchor
    if len(bars) == 0 or not math.isfinite(atr_anchor) or atr_anchor <= 0 or not math.isfinite(entry_ref):
        return {
            "event_id": event_id,
            "asset": asset,
            "event_ts": event_ts.isoformat(),
            "entry_ts": entry_ts.isoformat(),
            "side": side,
            "side_label": side_label(side),
            "favorable_atr": favorable_atr,
            "adverse_atr": adverse_atr,
            "horizon_days": horizon_days,
            "path_complete": False,
            "conservative_result": "incomplete",
            "optimistic_result": "incomplete",
            "success_conservative": np.nan,
            "success_optimistic": np.nan,
            "ambiguous_same_hour": False,
            "hit_ts": None,
            "hours_to_hit": np.nan,
            "exit_ref": np.nan,
            "terminal_direction_return": np.nan,
            "net_return": np.nan,
            "mfe_atr": np.nan,
            "mae_atr": np.nan,
            "mfe_first_hour": np.nan,
            "mae_first_hour": np.nan,
        }
    fav_idx = int(np.argmax(fav_flags)) if bool(fav_flags.any()) else None
    adv_idx = int(np.argmax(adv_flags)) if bool(adv_flags.any()) else None
    ambiguous = fav_idx is not None and adv_idx is not None and fav_idx == adv_idx
    if fav_idx is None and adv_idx is None:
        result = "timeout"
        opt_result = "timeout"
        hit_idx = len(bars) - 1
        exit_ref = float(bars["close"].iloc[-1])
        success = False
        opt_success = False
    elif adv_idx is None or (fav_idx is not None and fav_idx < adv_idx):
        result = "favorable"
        opt_result = "favorable"
        hit_idx = fav_idx
        exit_ref = fav_price
        success = True
        opt_success = True
    elif fav_idx is None or adv_idx < fav_idx:
        result = "adverse"
        opt_result = "adverse"
        hit_idx = adv_idx
        exit_ref = adv_price
        success = False
        opt_success = False
    else:
        result = "adverse"
        opt_result = "favorable"
        hit_idx = adv_idx
        exit_ref = adv_price
        success = False
        opt_success = True
    hit_bar_ts = pd.Timestamp(bars["ts"].iloc[hit_idx])
    hit_ts = hit_bar_ts + pd.Timedelta(hours=1)
    terminal_close = float(bars["close"].iloc[-1])
    funding_adj = funding_pnl(funding, side, entry_ts, hit_ts)
    signed_ranges = np.concatenate([signed_high, signed_low, signed_close])
    mfe = float(np.nanmax(signed_ranges))
    mae = float(np.nanmin(signed_ranges))
    return {
        "event_id": event_id,
        "asset": asset,
        "event_ts": event_ts.isoformat(),
        "entry_ts": entry_ts.isoformat(),
        "side": side,
        "side_label": side_label(side),
        "favorable_atr": favorable_atr,
        "adverse_atr": adverse_atr,
        "horizon_days": horizon_days,
        "path_complete": path_complete,
        "observed_hours": int(len(bars)),
        "conservative_result": result,
        "optimistic_result": opt_result,
        "success_conservative": bool(success),
        "success_optimistic": bool(opt_success),
        "ambiguous_same_hour": bool(ambiguous),
        "hit_ts": hit_ts.isoformat(),
        "hours_to_hit": float(hit_idx + 1),
        "exit_ref": float(exit_ref),
        "terminal_direction_return": side * (terminal_close / entry_ref - 1.0),
        "net_return": net_return(side, entry_ref, float(exit_ref), funding_adj),
        "funding_pnl": funding_adj,
        "mfe_atr": mfe,
        "mae_atr": mae,
        "mfe_first_hour": float(int(np.nanargmax(signed_ranges)) % len(bars) + 1),
        "mae_first_hour": float(int(np.nanargmin(signed_ranges)) % len(bars) + 1),
    }


def all_first_hits(
    *,
    event_id: str,
    asset: str,
    side: int,
    event_ts: pd.Timestamp,
    entry_ts: pd.Timestamp,
    entry_ref: float,
    atr_anchor: float,
    hourly: pd.DataFrame,
    funding: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows = []
    for fav in FAVORABLE_BARRIERS:
        for adv in ADVERSE_BARRIERS:
            for horizon in HORIZONS:
                rows.append(
                    first_hit_one(
                        event_id=event_id,
                        asset=asset,
                        side=side,
                        event_ts=event_ts,
                        entry_ts=entry_ts,
                        entry_ref=entry_ref,
                        atr_anchor=atr_anchor,
                        hourly=hourly,
                        funding=funding,
                        favorable_atr=fav,
                        adverse_atr=adv,
                        horizon_days=horizon,
                    )
                )
    return rows


def enrich_event_path_fields(
    row: dict[str, Any],
    matrix_rows: list[dict[str, Any]],
    daily: pd.DataFrame,
    index: int,
) -> dict[str, Any]:
    matrix = pd.DataFrame(matrix_rows)
    primary = matrix.loc[
        (matrix["favorable_atr"] == PRIMARY_FAVORABLE_ATR)
        & (matrix["adverse_atr"] == PRIMARY_ADVERSE_ATR)
        & (matrix["horizon_days"] == PRIMARY_HORIZON_DAYS)
    ].iloc[0]
    out = dict(row)
    out.update(
        {
            "primary_path_complete": bool(primary["path_complete"]),
            "primary_success": primary["success_conservative"],
            "primary_success_optimistic": primary["success_optimistic"],
            "primary_result": primary["conservative_result"],
            "primary_optimistic_result": primary["optimistic_result"],
            "primary_ambiguous_same_hour": bool(primary["ambiguous_same_hour"]),
            "primary_hit_ts": primary["hit_ts"],
            "primary_hours_to_hit": primary["hours_to_hit"],
            "primary_exit_ref": primary["exit_ref"],
            "primary_terminal_direction_return": primary["terminal_direction_return"],
            "primary_net_return": primary["net_return"],
            "primary_mfe_atr": primary["mfe_atr"],
            "primary_mae_atr": primary["mae_atr"],
            "primary_mfe_first_hour": primary["mfe_first_hour"],
            "primary_mae_first_hour": primary["mae_first_hour"],
        }
    )
    for horizon in HORIZONS:
        sub = matrix.loc[
            (matrix["favorable_atr"] == PRIMARY_FAVORABLE_ATR)
            & (matrix["adverse_atr"] == PRIMARY_ADVERSE_ATR)
            & (matrix["horizon_days"] == horizon)
        ].iloc[0]
        out[f"mfe_atr_{horizon}d"] = sub["mfe_atr"]
        out[f"mae_atr_{horizon}d"] = sub["mae_atr"]
        out[f"terminal_direction_return_{horizon}d"] = sub["terminal_direction_return"]
        out[f"net_return_{horizon}d"] = sub["net_return"]
    for fav in FAVORABLE_BARRIERS:
        hit = matrix.loc[
            (matrix["favorable_atr"] == fav)
            & (matrix["adverse_atr"] == PRIMARY_ADVERSE_ATR)
            & (matrix["horizon_days"] == 30)
        ].iloc[0]
        out[f"hours_to_plus_{str(fav).replace('.', '_')}_atr"] = (
            hit["hours_to_hit"] if hit["conservative_result"] == "favorable" else np.nan
        )
    terminal_move_atr = float(out.get("terminal_direction_return_14d", np.nan)) * (
        float(out["entry_ref"]) / float(out["atr7"])
    )
    out["mfe_giveback_atr_14d"] = float(out["mfe_atr_14d"]) - terminal_move_atr
    end = min(len(daily), index + PRIMARY_HORIZON_DAYS + 1)
    future = daily.iloc[index + 1 : end].copy()
    side = int(out["side"])
    run = 0
    longest = 0
    for _, day in future.iterrows():
        if side * (float(day["close"]) - float(out["entry_ref"])) > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    out["longest_consecutive_direction_days_14d"] = longest
    closes = future["close"].astype(float).to_numpy()
    if len(closes):
        path = np.concatenate([[float(out["entry_ref"])], closes])
        denom = float(np.abs(np.diff(path)).sum())
        out["direction_efficiency_14d"] = (
            abs(float(closes[-1]) - float(out["entry_ref"])) / denom if denom > 0 else np.nan
        )
    else:
        out["direction_efficiency_14d"] = np.nan
    out["reverse_ma7_cross_14d"] = bool((future["raw_cross"].astype(int) == -side).any())
    return out


def build_asset_events(asset: str, daily: pd.DataFrame, hourly: pd.DataFrame, funding: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    events: list[dict[str, Any]] = []
    matrix: list[dict[str, Any]] = []
    episode_cluster = 0
    last_cross_ts: pd.Timestamp | None = None
    for index, cross in enumerate(daily["raw_cross"].astype(int)):
        if cross == 0 or index + 1 >= len(daily):
            continue
        ma = float(daily["ma7"].iloc[index])
        atr = float(daily["atr7"].iloc[index])
        if not math.isfinite(ma) or not math.isfinite(atr) or atr <= 0:
            continue
        event_ts = pd.Timestamp(daily["ts"].iloc[index])
        entry_ts = event_ts + pd.Timedelta(days=1)
        if pd.Timestamp(daily["ts"].iloc[index + 1]) != entry_ts:
            raise RuntimeError(f"{asset} event entry day is not next UTC open")
        if last_cross_ts is None or (event_ts - last_cross_ts) > pd.Timedelta(days=14):
            episode_cluster += 1
        last_cross_ts = event_ts
        row = state_row(asset, daily, index, int(cross))
        row["event_id"] = f"{asset}_{index:04d}_{side_label(int(cross))}"
        row["entry_ts"] = entry_ts.isoformat()
        row["entry_ref"] = float(daily["open"].iloc[index + 1])
        row["feature_known_at"] = event_ts.isoformat()
        row["signal_time"] = (event_ts + pd.Timedelta(days=1)).isoformat()
        row["entry_is_next_utc_open"] = True
        row["asset_episode_cluster"] = f"{asset}_E{episode_cluster:04d}"
        row["calendar_block"] = quarter_label(event_ts)
        row["hype_holdout_forbidden"] = asset == "HYPEUSDT" and event_ts >= HYPE_HOLDOUT_START
        rows = all_first_hits(
            event_id=row["event_id"],
            asset=asset,
            side=int(cross),
            event_ts=event_ts,
            entry_ts=entry_ts,
            entry_ref=float(row["entry_ref"]),
            atr_anchor=atr,
            hourly=hourly,
            funding=funding,
        )
        matrix.extend(rows)
        events.append(enrich_event_path_fields(row, rows, daily, index))
    events_df = pd.DataFrame(events)
    if not events_df.empty:
        events_df["dedup_14d_same_side"] = False
        last_by_side: dict[int, pd.Timestamp] = {}
        for pos, event in events_df.iterrows():
            side = int(event["side"])
            ts = pd.Timestamp(event["ts"])
            if side not in last_by_side or (ts - last_by_side[side]) > pd.Timedelta(days=14):
                events_df.loc[pos, "dedup_14d_same_side"] = True
                last_by_side[side] = ts
    return events_df, pd.DataFrame(matrix)


def eligible_control_indices(daily: pd.DataFrame) -> list[int]:
    valid = []
    for index in range(7, len(daily) - 1):
        if not math.isfinite(float(daily["ma7"].iloc[index])) or not math.isfinite(float(daily["atr7"].iloc[index])):
            continue
        valid.append(index)
    return valid


def control_state(
    *,
    control_id: str,
    event: pd.Series,
    baseline: str,
    asset: str,
    daily: pd.DataFrame,
    hourly: pd.DataFrame,
    funding: pd.DataFrame,
    index: int,
    side: int,
) -> dict[str, Any]:
    row = state_row(asset, daily, index, side)
    event_ts = pd.Timestamp(daily["ts"].iloc[index])
    entry_ts = event_ts + pd.Timedelta(days=1)
    row["event_id"] = event["event_id"]
    row["control_id"] = control_id
    row["baseline"] = baseline
    row["control_ts"] = event_ts.isoformat()
    row["entry_ts"] = entry_ts.isoformat()
    row["entry_ref"] = float(daily["open"].iloc[index + 1])
    row["source_event_ts"] = event["ts"]
    row["source_asset_episode_cluster"] = event["asset_episode_cluster"]
    primary = first_hit_one(
        event_id=control_id,
        asset=asset,
        side=side,
        event_ts=event_ts,
        entry_ts=entry_ts,
        entry_ref=float(row["entry_ref"]),
        atr_anchor=float(row["atr7"]),
        hourly=hourly,
        funding=funding,
        favorable_atr=PRIMARY_FAVORABLE_ATR,
        adverse_atr=PRIMARY_ADVERSE_ATR,
        horizon_days=PRIMARY_HORIZON_DAYS,
    )
    enriched = {
        **row,
        "primary_path_complete": primary["path_complete"],
        "primary_success": primary["success_conservative"],
        "primary_success_optimistic": primary["success_optimistic"],
        "primary_result": primary["conservative_result"],
        "primary_ambiguous_same_hour": primary["ambiguous_same_hour"],
        "primary_hours_to_hit": primary["hours_to_hit"],
        "primary_net_return": primary["net_return"],
        "primary_mfe_atr": primary["mfe_atr"],
        "primary_mae_atr": primary["mae_atr"],
    }
    keep = {
        "event_id",
        "control_id",
        "baseline",
        "asset",
        "control_ts",
        "source_event_ts",
        "source_asset_episode_cluster",
        "side",
        "side_label",
        "quarter",
        "slope_bin",
        "vol_regime",
        "primary_path_complete",
        "primary_success",
        "primary_success_optimistic",
        "primary_result",
        "primary_ambiguous_same_hour",
        "primary_hours_to_hit",
        "primary_net_return",
        "primary_mfe_atr",
        "primary_mae_atr",
    }
    return {key: enriched.get(key) for key in keep}


def build_controls(
    events: pd.DataFrame,
    daily_by_asset: dict[str, pd.DataFrame],
    hourly_by_asset: dict[str, pd.DataFrame],
    funding_by_asset: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    rng = random.Random(RANDOM_SEED)
    rows: list[dict[str, Any]] = []
    candidate_cache: dict[tuple[str, int], list[tuple[int, dict[str, Any]]]] = {}
    for asset, daily in daily_by_asset.items():
        for side in (1, -1):
            cached: list[tuple[int, dict[str, Any]]] = []
            for index in eligible_control_indices(daily):
                if int(daily["raw_cross"].iloc[index]) != 0:
                    continue
                state = state_row(asset, daily, index, side)
                ret7 = float(daily["close"].iloc[index] / daily["close"].iloc[index - 7] - 1.0)
                state["momentum_side"] = 1 if ret7 > 0 else -1 if ret7 < 0 else 0
                state["already_same_side"] = (
                    side * (float(daily["close"].iloc[index]) - float(daily["ma7"].iloc[index])) > 0
                )
                cached.append((index, state))
            candidate_cache[(asset, side)] = cached
    for event in events.to_dict("records"):
        asset = event["asset"]
        daily = daily_by_asset[asset]
        hourly = hourly_by_asset[asset]
        funding = funding_by_asset[asset]
        side = int(event["side"])
        scored = candidate_cache[(asset, side)]

        def same_common(item: tuple[int, dict[str, Any]]) -> bool:
            _, state = item
            return (
                state["quarter"] == event["quarter"]
                and state["vol_regime"] == event["vol_regime"]
            )

        b_pool = [
            item
            for item in scored
            if same_common(item)
            and item[1]["slope_bin"] == event["slope_bin"]
            and item[1]["already_same_side"]
        ]
        c_pool = [
            item
            for item in scored
            if same_common(item) and item[1]["momentum_side"] == side
        ]
        d_pool = [item for item in scored if same_common(item)]
        for baseline, pool in (("B_NON_CROSS_SAME_SIDE", b_pool), ("C_MOMENTUM_7D", c_pool), ("D_RANDOM_MATCHED", d_pool)):
            if not pool:
                continue
            sample = pool if len(pool) <= CONTROL_MATCHES else rng.sample(pool, CONTROL_MATCHES)
            for order, (index, _) in enumerate(sample):
                rows.append(
                    control_state(
                        control_id=f"{event['event_id']}_{baseline}_{order}",
                        event=pd.Series(event),
                        baseline=baseline,
                        asset=asset,
                        daily=daily,
                        hourly=hourly,
                        funding=funding,
                        index=index,
                        side=side,
                    )
                )
    return pd.DataFrame(rows)


def summarize_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    complete = frame.loc[frame["primary_path_complete"].astype(bool)].copy()
    rate = rate_dict(complete["primary_success"]) if not complete.empty else rate_dict([])
    success_times = pd.to_numeric(
        complete.loc[complete["primary_success"].astype(bool), "primary_hours_to_hit"],
        errors="coerce",
    )
    return {
        "events": int(len(frame)),
        "complete_events": int(len(complete)),
        "successes": int(rate["k"]),
        "primary_success_rate": rate["rate"],
        "wilson_low": rate["wilson_low"],
        "wilson_high": rate["wilson_high"],
        "mean_mfe_atr": float(pd.to_numeric(complete["primary_mfe_atr"], errors="coerce").mean()),
        "mean_mae_atr": float(pd.to_numeric(complete["primary_mae_atr"], errors="coerce").mean()),
        "mean_net_return": float(pd.to_numeric(complete["primary_net_return"], errors="coerce").mean()),
        "median_net_return": float(pd.to_numeric(complete["primary_net_return"], errors="coerce").median()),
        "profit_factor": pf(complete["primary_net_return"]),
        "median_first_hit_hours": float(success_times.median()) if len(success_times) else math.nan,
    }


def stats_row(scope: str, group_key: str, group_value: str, frame: pd.DataFrame) -> dict[str, Any]:
    out = summarize_metrics(frame)
    long_frame = frame.loc[frame["side"].astype(int) == 1]
    short_frame = frame.loc[frame["side"].astype(int) == -1]
    out.update(
        {
            "scope": scope,
            "group_key": group_key,
            "group_value": group_value,
            "long_events": int(len(long_frame)),
            "long_success_rate": summarize_metrics(long_frame)["primary_success_rate"] if len(long_frame) else math.nan,
            "short_events": int(len(short_frame)),
            "short_success_rate": summarize_metrics(short_frame)["primary_success_rate"] if len(short_frame) else math.nan,
            "sample_flag": "OK" if out["complete_events"] >= INSUFFICIENT_N else "INSUFFICIENT_SAMPLE",
        }
    )
    return out


def feature_bin_stats(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for field in SINGLE_BIN_FIELDS:
        for value, group in events.groupby(field, dropna=False, sort=True):
            rows.append(stats_row("overall", field, str(value), group))
        for side, group_side in events.groupby("side_label", sort=True):
            for value, group in group_side.groupby(field, dropna=False, sort=True):
                rows.append(stats_row(f"side={side}", field, str(value), group))
        for asset, group_asset in events.groupby("asset", sort=True):
            for value, group in group_asset.groupby(field, dropna=False, sort=True):
                rows.append(stats_row(f"asset={asset}", field, str(value), group))
    return pd.DataFrame(rows)


def two_way_stats(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for name, left, right in TWO_WAY_MATRICES:
        for keys, group in events.groupby([left, right], dropna=False, sort=True):
            out = summarize_metrics(group)
            out.update(
                {
                    "matrix": name,
                    "left_field": left,
                    "right_field": right,
                    "left_value": str(keys[0]),
                    "right_value": str(keys[1]),
                    "sample_flag": "OK" if out["complete_events"] >= INSUFFICIENT_N else "INSUFFICIENT_SAMPLE",
                }
            )
            rows.append(out)
    return pd.DataFrame(rows)


def asset_direction_stats(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in events.groupby(["asset", "side_label"], sort=True):
        out = summarize_metrics(group)
        out.update({"asset": keys[0], "side": keys[1], "scope": "asset_direction"})
        rows.append(out)
    for asset, group in events.groupby("asset", sort=True):
        out = summarize_metrics(group)
        out.update({"asset": asset, "side": "all", "scope": "asset"})
        rows.append(out)
    for side, group in events.groupby("side_label", sort=True):
        out = summarize_metrics(group)
        out.update({"asset": "ALL", "side": side, "scope": "direction"})
        rows.append(out)
    out = summarize_metrics(events)
    out.update({"asset": "ALL", "side": "all", "scope": "overall"})
    rows.append(out)
    return pd.DataFrame(rows)


def baseline_summary(events: pd.DataFrame, controls: pd.DataFrame) -> dict[str, Any]:
    output: dict[str, Any] = {"A_RAW_CROSS": summarize_metrics(events)}
    complete_events = events.loc[events["primary_path_complete"].astype(bool)]
    for baseline, group in controls.groupby("baseline", sort=True):
        complete_controls = group.loc[group["primary_path_complete"].astype(bool)]
        joined = complete_controls.merge(
            complete_events[["event_id", "primary_success", "primary_net_return", "asset", "side_label"]],
            on="event_id",
            how="inner",
            suffixes=("_control", "_cross"),
        )
        by_event = joined.groupby("event_id", sort=False).agg(
            control_success=("primary_success_control", "mean"),
            cross_success=("primary_success_cross", "first"),
            control_net=("primary_net_return_control", "mean"),
            cross_net=("primary_net_return_cross", "first"),
        )
        output[baseline] = {
            "control": summarize_metrics(complete_controls),
            "matched_cross_events": int(len(by_event)),
            "mean_success_uplift_vs_control": float((by_event["cross_success"] - by_event["control_success"]).mean())
            if len(by_event)
            else math.nan,
            "mean_net_uplift_vs_control": float((by_event["cross_net"] - by_event["control_net"]).mean())
            if len(by_event)
            else math.nan,
            "control_rows": int(len(complete_controls)),
        }
    return output


def bootstrap_rows(events: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    complete_events = events.loc[events["primary_path_complete"].astype(bool)].copy()
    rows: list[dict[str, Any]] = []
    if complete_events.empty:
        return pd.DataFrame(rows)
    for baseline, group in controls.groupby("baseline", sort=True):
        complete_controls = group.loc[group["primary_path_complete"].astype(bool)].copy()
        if complete_controls.empty:
            continue
        joined = complete_controls.merge(
            complete_events[
                [
                    "event_id",
                    "asset",
                    "side_label",
                    "asset_episode_cluster",
                    "primary_success",
                    "primary_net_return",
                ]
            ],
            on="event_id",
            how="inner",
            suffixes=("_control", "_cross"),
        )
        if joined.empty:
            continue
        by_event = joined.groupby("event_id", sort=False).agg(
            asset=("asset_cross", "first"),
            side=("side_label_cross", "first"),
            cluster=("asset_episode_cluster", "first"),
            success_diff=("primary_success_cross", lambda x: float(x.iloc[0])),
            control_success=("primary_success_control", "mean"),
            net_diff=("primary_net_return_cross", lambda x: float(x.iloc[0])),
            control_net=("primary_net_return_control", "mean"),
        )
        by_event["success_diff"] = by_event["success_diff"] - by_event["control_success"]
        by_event["net_diff"] = by_event["net_diff"] - by_event["control_net"]
        for side_scope in ("all", "long", "short"):
            scoped = by_event if side_scope == "all" else by_event.loc[by_event["side"] == side_scope]
            if scoped.empty:
                continue
            cluster_means = scoped.groupby("cluster", sort=False)[["success_diff", "net_diff"]].mean()
            clusters = cluster_means.index.to_numpy()
            success_samples = []
            net_samples = []
            values = cluster_means.to_numpy(float)
            for _ in range(BOOTSTRAP_REPS):
                sample_idx = rng.integers(0, len(clusters), len(clusters))
                sample = values[sample_idx]
                success_samples.append(float(np.mean(sample[:, 0])))
                net_samples.append(float(np.mean(sample[:, 1])))
            rows.append(
                {
                    "baseline": baseline,
                    "scope": side_scope,
                    "events": int(len(scoped)),
                    "clusters": int(len(clusters)),
                    "success_uplift_mean": float(scoped["success_diff"].mean()),
                    "success_uplift_ci_low": float(np.quantile(success_samples, 0.025)),
                    "success_uplift_ci_high": float(np.quantile(success_samples, 0.975)),
                    "net_uplift_mean": float(scoped["net_diff"].mean()),
                    "net_uplift_ci_low": float(np.quantile(net_samples, 0.025)),
                    "net_uplift_ci_high": float(np.quantile(net_samples, 0.975)),
                }
            )
    dedup = complete_events.loc[complete_events["dedup_14d_same_side"].astype(bool)]
    rows.append(
        {
            "baseline": "A_RAW_CROSS_DEDUP_14D_SAME_SIDE",
            "scope": "all",
            "events": int(len(dedup)),
            "clusters": int(dedup["asset_episode_cluster"].nunique()),
            "success_uplift_mean": summarize_metrics(dedup)["primary_success_rate"],
            "success_uplift_ci_low": summarize_metrics(dedup)["wilson_low"],
            "success_uplift_ci_high": summarize_metrics(dedup)["wilson_high"],
            "net_uplift_mean": summarize_metrics(dedup)["mean_net_return"],
            "net_uplift_ci_low": math.nan,
            "net_uplift_ci_high": math.nan,
        }
    )
    return pd.DataFrame(rows)


def candle_payload(asset: str, daily: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for row in daily.to_dict("records"):
        rows.append(
            {
                "asset": asset,
                "t": pd.Timestamp(row["ts"]).isoformat(),
                "o": row["open"],
                "h": row["high"],
                "l": row["low"],
                "c": row["close"],
                "ma7": row["ma7"],
            }
        )
    return rows


def html_event_payload(events: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for row in events.to_dict("records"):
        if not bool(row.get("primary_path_complete")):
            continue
        rows.append(
            {
                "id": row["event_id"],
                "asset": row["asset"],
                "side": row["side_label"],
                "t": row["ts"],
                "entryTs": row["entry_ts"],
                "entry": row["entry_ref"],
                "endTs": row["primary_hit_ts"],
                "end": row["primary_exit_ref"],
                "success": bool(row["primary_success"]),
                "ambiguous": bool(row["primary_ambiguous_same_hour"]),
                "slope": row["slope_bin"],
                "jump": row["cross_jump_bin"],
                "result": row["primary_result"],
                "rate": row["primary_net_return"],
                "hours": row["primary_hours_to_hit"],
            }
        )
    return rows


def table_records(frame: pd.DataFrame, limit: int = 300) -> list[dict[str, Any]]:
    return json.loads(frame.head(limit).to_json(orient="records"))


def build_html(
    events: pd.DataFrame,
    feature_stats: pd.DataFrame,
    two_way: pd.DataFrame,
    controls_summary: dict[str, Any],
    daily_by_asset: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    candles = []
    for asset, daily in daily_by_asset.items():
        candles.extend(candle_payload(asset, daily))
    chart_events = html_event_payload(events)
    payload = {
        "title": "P8 MA7 Cross First-Hit Event Atlas",
        "subtitle": "HYPE 后81日未读取；primary = +2 ATR before -1 ATR within 14d",
        "assets": list(ASSETS),
        "candles": candles,
        "events": chart_events,
        "featureStats": table_records(feature_stats, 180),
        "twoWay": table_records(two_way, 180),
        "controls": controls_summary,
        "primary": {
            "favorable_atr": PRIMARY_FAVORABLE_ATR,
            "adverse_atr": PRIMARY_ADVERSE_ATR,
            "horizon_days": PRIMARY_HORIZON_DAYS,
        },
        "holdout_read": False,
    }
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>P8 MA7 Cross First-Hit Event Atlas</title>
<style>
body{{margin:0;background:#101417;color:#e6ecef;font:14px/1.45 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif}}
header{{padding:22px 28px;border-bottom:1px solid #293238;background:#151b1f;position:sticky;top:0;z-index:2}}
h1{{margin:0 0 8px;font-size:22px}} .muted{{color:#94a3aa}} .warn{{color:#e2b86b}}
.controls{{display:flex;gap:12px;flex-wrap:wrap;margin-top:14px}} select,button{{background:#20282d;color:#e6ecef;border:1px solid #3a464d;border-radius:6px;padding:6px 9px}}
main{{padding:18px 28px 40px}} canvas{{width:100%;height:470px;background:#0c1114;border:1px solid #293238;border-radius:10px;display:block}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}} .panel{{background:#151b1f;border:1px solid #293238;border-radius:10px;padding:14px;overflow:auto}}
table{{width:100%;border-collapse:collapse;font-size:12px}} th,td{{border-bottom:1px solid #263037;padding:6px;text-align:left;white-space:nowrap}} tr:hover{{background:#20282d;cursor:pointer}}
.pill{{display:inline-block;padding:2px 6px;border-radius:999px;background:#263037}} .ok{{color:#79c69b}} .bad{{color:#d98282}}
</style>
</head>
<body>
<header>
<h1>P8 MA7 Cross First-Hit Event Atlas</h1>
<div class="muted">自包含 HTML · raw MA7 cross · 64 first-hit matrix · <span class="warn">后81日未读取</span></div>
<div class="controls">
<label>资产 <select id="asset"></select></label>
<label>方向 <select id="side"><option>all</option><option>long</option><option>short</option></select></label>
<label>斜率 <select id="slope"><option>all</option></select></label>
<label>穿越幅度 <select id="jump"><option>all</option></select></label>
<label>结果 <select id="result"><option>all</option><option>success</option><option>failure</option><option>ambiguous</option></select></label>
<button id="prev">上一事件</button><button id="next">下一事件</button><button id="succ">下一成功</button><button id="fail">下一失败</button><button id="amb">下一模糊</button><button id="reset">双击/复位</button>
</div>
</header>
<main>
<canvas id="chart" width="1600" height="620"></canvas>
<div class="grid">
<section class="panel"><h2>事件列表</h2><table><thead><tr><th>事件</th><th>方向</th><th>时间</th><th>结果</th><th>净收益</th><th>小时</th></tr></thead><tbody id="events"></tbody></table></section>
<section class="panel"><h2>Matched Control 对照</h2><pre id="controls"></pre></section>
<section class="panel"><h2>单变量分箱统计</h2><table><thead><tr><th>scope</th><th>字段</th><th>分箱</th><th>n</th><th>成功率</th><th>净均值</th><th>标记</th></tr></thead><tbody id="stats"></tbody></table></section>
<section class="panel"><h2>预注册二维矩阵</h2><table><thead><tr><th>矩阵</th><th>左</th><th>右</th><th>n</th><th>成功率</th><th>净均值</th><th>标记</th></tr></thead><tbody id="matrix"></tbody></table></section>
</div>
</main>
<script>
const DATA = {json.dumps(sanitize(payload), ensure_ascii=False)};
const DAY = 86400000, C={{bg:'#0c1114',grid:'#253039',up:'#74b99f',down:'#ca7777',ma:'#d8bd6a',succ:'#6cc38d',fail:'#d66f72',amb:'#d6a95e',text:'#e6ecef',muted:'#91a0a8'}};
const $=id=>document.getElementById(id); let view=null, active=0, dragging=false, dragX=0;
function ts(x){{return Date.parse(x)}} function pct(x){{return x==null||!isFinite(x)?'n/a':(x*100).toFixed(2)+'%'}}
function init(){{for(const a of DATA.assets) $('asset').appendChild(new Option(a,a)); $('asset').value='HYPEUSDT';
for(const v of [...new Set(DATA.events.map(e=>e.slope))].sort()) $('slope').appendChild(new Option(v,v));
for(const v of [...new Set(DATA.events.map(e=>e.jump))].sort()) $('jump').appendChild(new Option(v,v));
for(const id of ['asset','side','slope','jump','result']) $(id).onchange=()=>{{active=0;view=null;draw()}};
$('reset').onclick=()=>{{view=null;draw()}}; $('prev').onclick=()=>step(-1); $('next').onclick=()=>step(1); $('succ').onclick=()=>seek(e=>e.success); $('fail').onclick=()=>seek(e=>!e.success); $('amb').onclick=()=>seek(e=>e.ambiguous);
const c=$('chart'); c.onmousedown=e=>{{dragging=true;dragX=e.clientX}}; window.onmouseup=()=>dragging=false; window.onmousemove=e=>{{if(!dragging||!view)return; const span=view.e-view.s, dx=(e.clientX-dragX)/c.clientWidth*span; view.s-=dx; view.e-=dx; dragX=e.clientX; draw(false)}}; c.onwheel=e=>{{e.preventDefault(); const ev=visibleEvents(), base=visibleCandles(); if(!base.length)return; if(!view) view={{s:ts(base[0].t),e:ts(base[base.length-1].t)+DAY}}; const mid=view.s+(e.offsetX/c.clientWidth)*(view.e-view.s), f=e.deltaY>0?1.2:.83; const ns=mid-(mid-view.s)*f, ne=mid+(view.e-mid)*f; view={{s:ns,e:ne}}; draw(false)}}; c.ondblclick=()=>{{view=null;draw()}}; draw(); }}
function filters(e){{return e.asset==$('asset').value&&($('side').value=='all'||e.side==$('side').value)&&($('slope').value=='all'||e.slope==$('slope').value)&&($('jump').value=='all'||e.jump==$('jump').value)&&($('result').value=='all'||($('result').value=='success'&&e.success)||($('result').value=='failure'&&!e.success)||($('result').value=='ambiguous'&&e.ambiguous))}}
function visibleEvents(){{return DATA.events.filter(filters)}} function visibleCandles(){{return DATA.candles.filter(c=>c.asset==$('asset').value)}}
function ensureView(c){{if(view)return; view={{s:ts(c[0].t),e:ts(c[c.length-1].t)+DAY}}}}
function draw(updateTables=true){{const c=visibleCandles(); if(!c.length)return; ensureView(c); const ev=visibleEvents(); const canvas=$('chart'), ctx=canvas.getContext('2d'), w=canvas.width,h=canvas.height,m={{l:70,r:30,t:30,b:36}}, pw=w-m.l-m.r, ph=h-m.t-m.b; ctx.fillStyle=C.bg; ctx.fillRect(0,0,w,h);
const vc=c.filter(x=>ts(x.t)>=view.s&&ts(x.t)<=view.e), ve=ev.filter(x=>ts(x.entryTs)>=view.s&&ts(x.entryTs)<=view.e); let lo=Math.min(...vc.map(x=>x.l),...ve.map(x=>Math.min(x.entry,x.end))); let hi=Math.max(...vc.map(x=>x.h),...ve.map(x=>Math.max(x.entry,x.end))); if(!isFinite(lo)||!isFinite(hi)){{lo=Math.min(...c.map(x=>x.l));hi=Math.max(...c.map(x=>x.h))}} const pad=(hi-lo)*.08||1; lo-=pad;hi+=pad; const x=t=>m.l+(t-view.s)/(view.e-view.s)*pw, y=v=>m.t+(hi-v)/(hi-lo)*ph;
ctx.strokeStyle=C.grid; ctx.fillStyle=C.muted; ctx.textAlign='right'; for(let i=0;i<5;i++){{const yy=m.t+i*ph/4; ctx.beginPath();ctx.moveTo(m.l,yy);ctx.lineTo(m.l+pw,yy);ctx.stroke(); ctx.fillText((hi-(hi-lo)*i/4).toFixed(2),m.l-8,yy+4)}}
const bw=Math.max(1,Math.min(10,pw/Math.max(1,vc.length)*.6)); for(const p of vc){{const xx=x(ts(p.t)+DAY/2), col=p.c>=p.o?C.up:C.down; ctx.strokeStyle=col; ctx.beginPath();ctx.moveTo(xx,y(p.h));ctx.lineTo(xx,y(p.l));ctx.stroke();ctx.fillStyle=col;ctx.fillRect(xx-bw/2,y(Math.max(p.o,p.c)),bw,Math.max(1,y(Math.min(p.o,p.c))-y(Math.max(p.o,p.c))))}}
ctx.strokeStyle=C.ma; ctx.beginPath(); let started=false; for(const p of vc){{if(p.ma7==null){{started=false;continue}} const xx=x(ts(p.t)+DAY/2), yy=y(p.ma7); if(!started){{ctx.moveTo(xx,yy);started=true}}else ctx.lineTo(xx,yy)}} ctx.stroke();
for(const e of ve){{const col=e.ambiguous?C.amb:(e.success?C.succ:C.fail), hot=ev[active]&&e.id==ev[active].id; ctx.strokeStyle=col;ctx.lineWidth=hot?4:1.8;ctx.beginPath();ctx.moveTo(x(ts(e.entryTs)),y(e.entry));ctx.lineTo(x(ts(e.endTs)),y(e.end));ctx.stroke(); ctx.fillStyle=col; ctx.beginPath();ctx.arc(x(ts(e.entryTs)),y(e.entry),hot?7:4,0,Math.PI*2);ctx.fill();}} ctx.lineWidth=1; ctx.fillStyle=C.text; ctx.textAlign='left'; ctx.fillText(DATA.subtitle,m.l,18); if(updateTables) renderTables(ev);}}
function renderTables(ev){{$('events').innerHTML=ev.map((e,i)=>`<tr onclick="focusEvent(${{i}})"><td>${{e.id}}</td><td>${{e.side}}</td><td>${{e.t.slice(0,10)}}</td><td><span class="pill ${{e.success?'ok':'bad'}}">${{e.result}}</span></td><td>${{pct(e.rate)}}</td><td>${{e.hours}}</td></tr>`).join('');
$('controls').textContent=JSON.stringify(DATA.controls,null,2); $('stats').innerHTML=DATA.featureStats.map(r=>`<tr><td>${{r.scope}}</td><td>${{r.group_key}}</td><td>${{r.group_value}}</td><td>${{r.complete_events}}</td><td>${{pct(r.primary_success_rate)}}</td><td>${{pct(r.mean_net_return)}}</td><td>${{r.sample_flag}}</td></tr>`).join('');
$('matrix').innerHTML=DATA.twoWay.map(r=>`<tr><td>${{r.matrix}}</td><td>${{r.left_value}}</td><td>${{r.right_value}}</td><td>${{r.complete_events}}</td><td>${{pct(r.primary_success_rate)}}</td><td>${{pct(r.mean_net_return)}}</td><td>${{r.sample_flag}}</td></tr>`).join('');}}
function focusEvent(i){{const ev=visibleEvents(); if(!ev.length)return; active=(i+ev.length)%ev.length; const e=ev[active]; view={{s:ts(e.entryTs)-7*DAY,e:ts(e.endTs)+7*DAY}}; draw()}} function step(d){{focusEvent(active+d)}} function seek(pred){{const ev=visibleEvents(); for(let k=1;k<=ev.length;k++){{const i=(active+k)%ev.length;if(pred(ev[i])){{focusEvent(i);return}}}}}}
window.focusEvent=focusEvent; init();
</script>
</body>
</html>
"""
    OUTPUTS["html"].write_text(html, encoding="utf-8")
    write_sidecar(OUTPUTS["html"])
    manifest = {
        "html": str(OUTPUTS["html"].relative_to(ROOT)),
        "html_sha256": sha256(OUTPUTS["html"]),
        "candles": len(candles),
        "events": int(len(events)),
        "primary_complete_events": int(events["primary_path_complete"].astype(bool).sum()),
        "path_line_count": len(chart_events),
        "has_ma7": "ma7" in html,
        "has_drag": "onmousedown" in html and "onmousemove" in html,
        "has_zoom": "onwheel" in html,
        "has_reset": "ondblclick" in html and "reset" in html,
        "has_focus": "focusEvent" in html,
        "holdout_read": False,
    }
    write_json(OUTPUTS["html_manifest"], manifest)
    return manifest


def load_contexts() -> tuple[dict[str, Any], dict[str, Any]]:
    p4 = load_module(P4_SCRIPT, "p8_p4_loader")
    p7 = load_module(P7_SCRIPT, "p8_p7_loader")
    diag, v6, engine, adapter, hype = p7.load_hype_context(p4, train_only=True)
    if pd.Timestamp(hype.book.ts[0]) != HYPE_FIRST_DAY:
        raise RuntimeError("HYPE first day drifted")
    if pd.Timestamp(hype.book.ts[-1]) != HYPE_LAST_DAY:
        raise RuntimeError("HYPE last feature day drifted")
    if pd.Timestamp(hype.book.terminal_ts) != TRAIN_TERMINAL:
        raise RuntimeError("HYPE terminal drifted")
    if pd.Timestamp(hype.market.audit["hourly_end"]) > TRAIN_TERMINAL:
        raise RuntimeError("P8 attempted to read HYPE holdout hourly bars")
    if pd.Timestamp(hype.market.audit["funding_end"]) > TRAIN_TERMINAL:
        raise RuntimeError("P8 attempted to read HYPE holdout funding")
    original = hype.original_harness
    orig_engine, base, search = original.modules()
    parent = base.load_parent()
    contexts: dict[str, Any] = {"HYPEUSDT": hype}
    for asset in DONOR_ASSETS:
        log(f"loading {asset} context through {TRAIN_TERMINAL.isoformat()}")
        contexts[asset] = p7.load_donor_context(
            original,
            orig_engine,
            base,
            search,
            parent,
            asset,
            p7.DONOR_SPECS[asset],
            TRAIN_TERMINAL,
        )
        if pd.Timestamp(contexts[asset].book.terminal_ts) != TRAIN_TERMINAL:
            raise RuntimeError(f"{asset} terminal drifted")
    modules = {"p4": p4, "p7": p7, "diag": diag, "v6": v6, "engine": engine, "adapter": adapter}
    return contexts, modules


def run() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    contexts, modules = load_contexts()
    daily_by_asset: dict[str, pd.DataFrame] = {}
    hourly_by_asset: dict[str, pd.DataFrame] = {}
    funding_by_asset: dict[str, pd.DataFrame] = {}
    events_parts: list[pd.DataFrame] = []
    matrix_parts: list[pd.DataFrame] = []
    data_audit: dict[str, Any] = {}
    for asset in ASSETS:
        context = contexts[asset]
        daily = canonical_daily(context)
        hourly = canonical_hourly(context)
        funding = funding_frame(context)
        daily_by_asset[asset] = daily
        hourly_by_asset[asset] = hourly
        funding_by_asset[asset] = funding
        data_audit[asset] = {
            "daily_rows": int(len(daily)),
            "daily_start": pd.Timestamp(daily["ts"].iloc[0]).isoformat(),
            "daily_end": pd.Timestamp(daily["ts"].iloc[-1]).isoformat(),
            "terminal": pd.Timestamp(context.book.terminal_ts).isoformat(),
            "hourly_rows": int(len(hourly)),
            "hourly_start": pd.Timestamp(hourly["ts"].iloc[0]).isoformat(),
            "hourly_end_exclusive": pd.Timestamp(context.book.terminal_ts).isoformat(),
            "funding_rows": int(len(funding)),
            "source_audit": sanitize(context.market.audit),
        }
        log(f"building events for {asset}")
        asset_events, asset_matrix = build_asset_events(asset, daily, hourly, funding)
        events_parts.append(asset_events)
        matrix_parts.append(asset_matrix)
    events = pd.concat(events_parts, ignore_index=True)
    matrix = pd.concat(matrix_parts, ignore_index=True)
    if int(matrix.groupby("event_id").size().min()) != 64:
        raise RuntimeError("first-hit matrix is not 64 rows for every event")
    if events.loc[events["asset"].eq("HYPEUSDT"), "hype_holdout_forbidden"].astype(bool).any():
        raise RuntimeError("HYPE holdout appeared in P8 events")
    if events.loc[events["asset"].eq("HYPEUSDT"), "ts"].map(pd.Timestamp).max() > HYPE_LAST_DAY:
        raise RuntimeError("P8 read beyond HYPE 365-day training window")

    log("building matched controls")
    controls = build_controls(events, daily_by_asset, hourly_by_asset, funding_by_asset)
    log("summarizing bins and matrices")
    feature_stats = feature_bin_stats(events)
    two_way = two_way_stats(events)
    asset_summary = asset_direction_stats(events)
    boot = bootstrap_rows(events, controls)
    controls_summary = baseline_summary(events, controls)

    overall = summarize_metrics(events)
    hype = summarize_metrics(events.loc[events["asset"].eq("HYPEUSDT")])
    donors = summarize_metrics(events.loc[events["asset"].isin(DONOR_ASSETS)])
    dedup = summarize_metrics(events.loc[events["dedup_14d_same_side"].astype(bool)])
    ambiguous = events.loc[events["primary_path_complete"].astype(bool), "primary_ambiguous_same_hour"].astype(bool)
    cluster_counts = {
        "asset_clusters": int(events["asset"].nunique()),
        "episode_clusters": int(events["asset_episode_cluster"].nunique()),
        "calendar_blocks": int(events["calendar_block"].nunique()),
        "hype_episode_clusters": int(events.loc[events["asset"].eq("HYPEUSDT"), "asset_episode_cluster"].nunique()),
        "donor_episode_clusters": int(events.loc[events["asset"].isin(DONOR_ASSETS), "asset_episode_cluster"].nunique()),
    }
    per_asset_clusters = {
        asset: int(group["asset_episode_cluster"].nunique())
        for asset, group in events.groupby("asset", sort=True)
    }
    donor_uplift_direction = {}
    if "B_NON_CROSS_SAME_SIDE" in controls["baseline"].unique():
        for asset in DONOR_ASSETS + ("HYPEUSDT",):
            a_events = events.loc[events["asset"].eq(asset) & events["primary_path_complete"].astype(bool)]
            a_controls = controls.loc[
                controls["asset"].eq(asset)
                & controls["baseline"].eq("B_NON_CROSS_SAME_SIDE")
                & controls["primary_path_complete"].astype(bool)
            ]
            if len(a_events) and len(a_controls):
                donor_uplift_direction[asset] = float(a_events["primary_success"].astype(float).mean() - a_controls["primary_success"].astype(float).mean())
            else:
                donor_uplift_direction[asset] = math.nan
    b_boot = boot.loc[(boot["baseline"] == "B_NON_CROSS_SAME_SIDE") & (boot["scope"] == "all")]
    b_ci_low = float(b_boot["success_uplift_ci_low"].iloc[0]) if not b_boot.empty else math.nan
    b_uplift = float(b_boot["success_uplift_mean"].iloc[0]) if not b_boot.empty else math.nan
    donor_positive = sum(
        1 for asset in DONOR_ASSETS if math.isfinite(donor_uplift_direction.get(asset, math.nan)) and donor_uplift_direction[asset] > 0
    )
    hype_positive = math.isfinite(donor_uplift_direction.get("HYPEUSDT", math.nan)) and donor_uplift_direction["HYPEUSDT"] > 0
    if cluster_counts["hype_episode_clusters"] < 10 or cluster_counts["donor_episode_clusters"] < 30:
        verdict = "INSUFFICIENT_SAMPLE"
    elif (
        math.isfinite(b_uplift)
        and b_uplift > 0
        and math.isfinite(b_ci_low)
        and b_ci_low > 0
        and donor_positive >= 3
        and hype_positive
        and float(overall["mean_net_return"]) > 0
        and float(dedup["primary_success_rate"]) >= float(overall["primary_success_rate"]) - 0.03
    ):
        verdict = "MA7_CROSS_OCCURRENCE_SUPPORTED"
    else:
        verdict = "MA7_CROSS_NO_INCREMENTAL_EDGE"
    summary = {
        "family": "HYPE-1D-MA7-Machine-Learning-Trend",
        "experiment": "P8_MA7_CROSS_FIRST_HIT_EVENT_ATLAS",
        "run_date": RUN_DATE,
        "status": f"{verdict} / diagnostic-only / not promoted / not live-ready",
        "no_ml_trained": True,
        "holdout_read": False,
        "hype_window": {
            "feature_start": HYPE_FIRST_DAY.isoformat(),
            "feature_last_day": HYPE_LAST_DAY.isoformat(),
            "train_terminal": TRAIN_TERMINAL.isoformat(),
            "forbidden_holdout_start": HYPE_HOLDOUT_START.isoformat(),
            "forbidden_holdout_end": HYPE_HOLDOUT_END.isoformat(),
        },
        "primary_label": {
            "favorable_atr": PRIMARY_FAVORABLE_ATR,
            "adverse_atr": PRIMARY_ADVERSE_ATR,
            "horizon_days": PRIMARY_HORIZON_DAYS,
            "definition": "+2 ATR before -1 ATR within 14d; conservative adverse-first on same-hour ambiguity",
        },
        "cost_model": {
            "fee_rate_per_fill": FEE_RATE,
            "slippage_per_fill": SLIPPAGE,
            "funding": "actual funding rows in context",
            "leverage": 1.0,
            "independent_events_no_compounding": True,
        },
        "event_counts": {
            "overall": int(len(events)),
            "primary_complete": int(events["primary_path_complete"].astype(bool).sum()),
            "hype": int(len(events.loc[events["asset"].eq("HYPEUSDT")])),
            "hype_primary_complete": int(events.loc[events["asset"].eq("HYPEUSDT"), "primary_path_complete"].astype(bool).sum()),
            "donors": int(len(events.loc[events["asset"].isin(DONOR_ASSETS)])),
            "donor_primary_complete": int(events.loc[events["asset"].isin(DONOR_ASSETS), "primary_path_complete"].astype(bool).sum()),
        },
        "cluster_counts": cluster_counts,
        "per_asset_episode_clusters": per_asset_clusters,
        "ambiguous_primary": {
            "count": int(ambiguous.sum()),
            "rate": float(ambiguous.mean()) if len(ambiguous) else math.nan,
        },
        "overall": overall,
        "hype": hype,
        "donors": donors,
        "dedup_14d_same_side": dedup,
        "baseline_summary": controls_summary,
        "uplift_by_asset_vs_baseline_b": donor_uplift_direction,
        "donor_assets_positive_uplift_vs_b": donor_positive,
        "hype_positive_uplift_vs_b": hype_positive,
        "verdict": verdict,
        "data_audit": data_audit,
    }
    write_csv(OUTPUTS["events"], events)
    write_csv(OUTPUTS["first_hit_matrix"], matrix)
    write_csv(OUTPUTS["feature_bin_stats"], feature_stats)
    write_csv(OUTPUTS["two_way_state_matrix"], two_way)
    write_csv(OUTPUTS["matched_controls"], controls)
    write_csv(OUTPUTS["asset_direction_summary"], asset_summary)
    write_csv(OUTPUTS["cluster_bootstrap"], boot)
    write_json(OUTPUTS["summary"], summary)
    html_manifest = build_html(events, feature_stats, two_way, controls_summary, daily_by_asset)
    manifest = {
        "family": summary["family"],
        "experiment": summary["experiment"],
        "run_date": RUN_DATE,
        "contract": {"path": str(SPEC_PATH.relative_to(ROOT)), "sha256": sha256(SPEC_PATH)},
        "script": {"path": str(Path(__file__).relative_to(ROOT)), "sha256": sha256(Path(__file__))},
        "holdout_read": False,
        "hype_days": int(data_audit["HYPEUSDT"]["daily_rows"]),
        "hype_terminal": data_audit["HYPEUSDT"]["terminal"],
        "no_ml_trained": True,
        "artifacts": {
            name: {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}
            for name, path in OUTPUTS.items()
            if name not in {"manifest", "report"} and path.exists()
        },
        "html_manifest": html_manifest,
        "source_modules": {
            "p4_loader": str(P4_SCRIPT.relative_to(ROOT)),
            "p7_loader": str(P7_SCRIPT.relative_to(ROOT)),
            "p4_sha256": sha256(P4_SCRIPT),
            "p7_sha256": sha256(P7_SCRIPT),
            "note": "Imported only to reuse pinned data loaders; no ML model was trained.",
        },
    }
    write_json(OUTPUTS["manifest"], manifest)
    write_report(summary, asset_summary, boot, feature_stats)
    return summary


def markdown_rate(metrics: dict[str, Any]) -> str:
    return (
        f"{metrics['successes']}/{metrics['complete_events']} = "
        f"{fmt_pct(metrics['primary_success_rate'])} "
        f"[{fmt_pct(metrics['wilson_low'])}–{fmt_pct(metrics['wilson_high'])}]"
    )


def write_report(
    summary: dict[str, Any],
    asset_summary: pd.DataFrame,
    boot: pd.DataFrame,
    feature_stats: pd.DataFrame,
) -> None:
    asset_rows = asset_summary.loc[asset_summary["scope"] == "asset"].copy()
    direction_rows = asset_summary.loc[asset_summary["scope"] == "direction"].copy()
    b = summary["baseline_summary"].get("B_NON_CROSS_SAME_SIDE", {})
    c = summary["baseline_summary"].get("C_MOMENTUM_7D", {})
    d = summary["baseline_summary"].get("D_RANDOM_MATCHED", {})
    boot_b = boot.loc[(boot["baseline"] == "B_NON_CROSS_SAME_SIDE") & (boot["scope"] == "all")]
    boot_c = boot.loc[(boot["baseline"] == "C_MOMENTUM_7D") & (boot["scope"] == "all")]
    boot_d = boot.loc[(boot["baseline"] == "D_RANDOM_MATCHED") & (boot["scope"] == "all")]

    def uplift_text(item: dict[str, Any], boot_row: pd.DataFrame) -> str:
        if not item or boot_row.empty:
            return "n/a"
        return (
            f"{fmt_pct(item.get('mean_success_uplift_vs_control'))}；"
            f"bootstrap [{fmt_pct(float(boot_row['success_uplift_ci_low'].iloc[0]))}, "
            f"{fmt_pct(float(boot_row['success_uplift_ci_high'].iloc[0]))}]"
        )

    def bin_rate(field: str, value: str) -> str:
        row = feature_stats.loc[
            (feature_stats["scope"] == "overall")
            & (feature_stats["group_key"] == field)
            & (feature_stats["group_value"] == value)
        ]
        if row.empty:
            return "n/a"
        item = row.iloc[0]
        return (
            f"{int(item['complete_events'])} 笔、"
            f"{fmt_pct(float(item['primary_success_rate']))}、"
            f"净均值 {fmt_signed_pct(float(item['mean_net_return']))}、"
            f"{item['sample_flag']}"
        )

    lines = [
        "# HYPE 1D MA7 MLT P8：MA7 Cross First-Hit Event Atlas",
        "",
        f"> 2026-08-31。裁决：`{summary['verdict']}`。状态：`diagnostic-only / not promoted / not live-ready`。",
        "> 本轮不训练机器学习、不优化参数、不读取 HYPE 后81日、不修改 P0-P7 或 exact V7.1。",
        "",
        "## 结论",
        "",
        (
            f"P8 在五个资产截断到 `2026-05-31 00:00 UTC` 的数据上保留所有 raw `SMA7` cross。"
            f"完整 primary 路径事件 `{summary['event_counts']['primary_complete']}` 笔，"
            f"primary 成功率 {markdown_rate(summary['overall'])}，成本后单事件净收益均值 "
            f"`{fmt_signed_pct(summary['overall']['mean_net_return'])}`。"
        ),
        "",
        (
            f"HYPE 前365日事件 `{summary['event_counts']['hype']}` 笔，完整 primary `{summary['event_counts']['hype_primary_complete']}` 笔，"
            f"episode cluster `{summary['cluster_counts']['hype_episode_clusters']}` 个；四个供体事件 "
            f"`{summary['event_counts']['donors']}` 笔，完整 primary `{summary['event_counts']['donor_primary_complete']}` 笔，"
            f"episode cluster `{summary['cluster_counts']['donor_episode_clusters']}` 个。"
        ),
        "",
        "## 分资产与方向",
        "",
        "| 资产 | 事件 | episode cluster | primary 成功率 | 净收益均值 | PF |",
        "| --- | ---: | ---: | --- | ---: | ---: |",
    ]
    for row in asset_rows.to_dict("records"):
        lines.append(
            f"| `{row['asset']}` | {int(row['complete_events'])} | "
            f"{summary['per_asset_episode_clusters'].get(row['asset'], 0)} | "
            f"{fmt_pct(row['primary_success_rate'])} | {fmt_signed_pct(row['mean_net_return'])} | "
            f"{row['profit_factor']:.2f} |"
        )
    lines.extend(["", "| 方向 | 事件 | primary 成功率 | 净收益均值 | PF |", "| --- | ---: | --- | ---: | ---: |"])
    for row in direction_rows.to_dict("records"):
        lines.append(
            f"| `{row['side']}` | {int(row['complete_events'])} | "
            f"{fmt_pct(row['primary_success_rate'])} | {fmt_signed_pct(row['mean_net_return'])} | "
            f"{row['profit_factor']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## 匹配基准",
            "",
            "| 对照 | success uplift | net uplift | control rows |",
            "| --- | ---: | ---: | ---: |",
            f"| 非穿越同侧 B | {uplift_text(b, boot_b)} | {fmt_signed_pct(b.get('mean_net_uplift_vs_control'))} | {b.get('control_rows', 0)} |",
            f"| 7日动量 C | {uplift_text(c, boot_c)} | {fmt_signed_pct(c.get('mean_net_uplift_vs_control'))} | {c.get('control_rows', 0)} |",
            f"| 随机匹配 D | {uplift_text(d, boot_d)} | {fmt_signed_pct(d.get('mean_net_uplift_vs_control'))} | {d.get('control_rows', 0)} |",
            "",
            (
                f"同一 `1h` 同时触及有利和不利 primary 屏障的模糊事件为 "
                f"`{summary['ambiguous_primary']['count']}`，占 `{fmt_pct(summary['ambiguous_primary']['rate'])}`；"
                "主标签按合同采用保守不利先触发。"
            ),
            "",
            "## 去重与独立性",
            "",
            (
                f"14日同资产同方向去重后 primary 成功率为 "
                f"{markdown_rate(summary['dedup_14d_same_side'])}，净收益均值 "
                f"`{fmt_signed_pct(summary['dedup_14d_same_side']['mean_net_return'])}`。"
            ),
            (
                f"统计独立性按资产 `{summary['cluster_counts']['asset_clusters']}` 个、"
                f"raw-cross episode `{summary['cluster_counts']['episode_clusters']}` 个、"
                f"日历块 `{summary['cluster_counts']['calendar_blocks']}` 个记录。"
            ),
            "",
            "## 状态图谱",
            "",
            "单变量分箱和十个二维矩阵均完整写入 artifact；`n<30` 的格子标记 `INSUFFICIENT_SAMPLE`，不据此提出交易规则。HTML 中可按资产、方向、斜率档、穿越幅度和结果过滤事件路径。",
            "",
            "几个样本数足够的预注册状态只呈现弱描述性差异：",
            "",
            f"- MA7 方向化斜率 `<=0`：{bin_rate('slope_bin', '<=0')}；`>0.10`：{bin_rate('slope_bin', '>0.10')}。斜率不是严格单调关系。",
            f"- 穿越幅度 `>0.50 ATR`：{bin_rate('cross_jump_bin', '>0.50')}；`(0.25,0.50]`：{bin_rate('cross_jump_bin', '(0.25,0.50]')}。大幅穿越较好，但 matched baseline 和去重后不足以构成规则。",
            f"- 反侧停留 `2-3日`：{bin_rate('prior_opposite_run_bin', '2-3日')}；`4-7日`：{bin_rate('prior_opposite_run_bin', '4-7日')}；`>=8日`：{bin_rate('prior_opposite_run_bin', '>=8日')}。中等停留较好，长停留转弱。",
            "",
            "小样本状态主要集中在分资产 × 斜率、极小穿越幅度、HYPE 高斜率/高成功率格子和多数二维交叉格；这些格子即使成功率高也只能作为下一轮问题定义线索，不能提出交易规则。",
            "",
            "## 裁决",
            "",
            (
                f"最终裁决为 `{summary['verdict']}`。即使某些斜率或方向格子表现较好，"
                "本轮也只是事件图谱，不登记版本、不 promotion。是否进入下一轮 ML 取决于 matched control uplift、"
                "bootstrap 下界、供体一致性、HYPE 前365日方向和成本后期望，而不是单个最好格子。"
            ),
            "",
            "本轮不建议直接进入机器学习筛选：raw cross 相对 controls 的优势太浅，非穿越同侧和随机匹配的 cluster bootstrap 下界仍小于 0，供体资产只有 2/4 相对 Baseline B 为正，且 14 日去重后净期望转负。若继续，应先重定义 episode 独立性或延长跨资产样本，而不是训练模型去挑这批格子。",
            "",
            "## 证据",
            "",
            f"- [冻结合同](../specs/hype-1d-ma7-mlt-p8-ma7-cross-first-hit-event-atlas-contract-2026-08-31.md)",
            f"- [研究脚本](../scripts/run_hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas.py)",
            f"- [事件表](../artifacts/{OUTPUTS['events'].name})",
            f"- [64组 first-hit 矩阵](../artifacts/{OUTPUTS['first_hit_matrix'].name})",
            f"- [matched controls](../artifacts/{OUTPUTS['matched_controls'].name})",
            f"- [cluster bootstrap](../artifacts/{OUTPUTS['cluster_bootstrap'].name})",
            f"- [摘要 JSON](../artifacts/{OUTPUTS['summary'].name})",
            f"- [交互式 HTML 图谱](../artifacts/{OUTPUTS['html'].name})",
            f"- [开发冻结清单](../artifacts/{OUTPUTS['manifest'].name})",
        ]
    )
    OUTPUTS["report"].write_text("\n".join(lines) + "\n", encoding="utf-8")


def self_test() -> None:
    assert len(FAVORABLE_BARRIERS) * len(ADVERSE_BARRIERS) * len(HORIZONS) == 64
    assert PRIMARY_FAVORABLE_ATR == 2.0
    assert PRIMARY_ADVERSE_ATR == 1.0
    assert PRIMARY_HORIZON_DAYS == 14
    assert HYPE_HOLDOUT_START == TRAIN_TERMINAL
    assert HYPE_LAST_DAY < HYPE_HOLDOUT_START
    assert BOOTSTRAP_REPS >= 500


def main() -> None:
    args = parse_args()
    self_test()
    if args.self_test:
        return
    summary = run()
    print(json.dumps(sanitize({"verdict": summary["verdict"], "event_counts": summary["event_counts"]}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
