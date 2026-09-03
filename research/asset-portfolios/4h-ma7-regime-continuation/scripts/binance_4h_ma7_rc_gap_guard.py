"""Gap-guard helpers for BIN-4H-MA7-RC.

Preserves P0 add_indicators segment reset and event timing. Corrects recross /
survival timekeeping, per-metric validity, and aggregation denominators.
Does not retune MA, ATR, PIT, costs, or PASS rules.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_P0_PATH = Path(__file__).with_name("research_binance_4h_ma7_regime_continuation_p0.py")


def _load_p0():
    name = "binance_4h_ma7_rc_p0"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _P0_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load P0 script {_P0_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P0 = _load_p0()
ATR_PERIOD = P0.ATR_PERIOD
HORIZONS = P0.HORIZONS
MAX_FUTURE_BARS = P0.MAX_FUTURE_BARS
PRIMARY_MA = P0.PRIMARY_MA
datetime_index_ns = P0.datetime_index_ns
enrich_outcomes = P0.enrich_outcomes
weighted_mean = P0.weighted_mean

FOUR_H_NS = 4 * 3600 * 1_000_000_000
ONE_H_NS = 3600 * 1_000_000_000

EXCLUSIVE_REASON_PRIORITY = (
    "entry_bar_missing",
    "indicator_warmup_insufficient",
    "internal_gap",
    "path_1h_missing",
    "right_censor_cutoff",
    "indicator_undefined",
    "funding_missing",
    "complete",
)

def utc_ns(value: Any) -> int:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return int(ts.value)


def series_utc_ns(values: pd.Series | pd.DatetimeIndex | np.ndarray) -> np.ndarray:
    index = pd.DatetimeIndex(values)
    if index.tz is None:
        index = index.tz_localize("UTC")
    else:
        index = index.tz_convert("UTC")
    return datetime_index_ns(index)


def exclusive_reason(
    *,
    entry_bar_missing: bool = False,
    warmup_insufficient: bool = False,
    internal_gap: bool = False,
    path_1h_missing: bool = False,
    right_censor: bool = False,
    indicator_undefined: bool = False,
    funding_missing: bool = False,
    complete: bool = False,
) -> str:
    flags = {
        "entry_bar_missing": entry_bar_missing,
        "indicator_warmup_insufficient": warmup_insufficient,
        "internal_gap": internal_gap,
        "path_1h_missing": path_1h_missing,
        "right_censor_cutoff": right_censor,
        "indicator_undefined": indicator_undefined,
        "funding_missing": funding_missing,
        "complete": complete,
    }
    for name in EXCLUSIVE_REASON_PRIORITY:
        if flags[name]:
            return name
    return "right_censor_cutoff"


def validate_time_grid(
    frame: pd.DataFrame,
    *,
    step: pd.Timedelta,
    name: str,
    phase_hour: int | None = None,
) -> pd.DataFrame:
    """Reject duplicates and unaligned grids. Integer-multiple holes are gaps."""
    if frame.empty:
        return frame.copy()
    required = {"symbol", "ts"}
    missing = required - set(frame.columns)
    if missing:
        raise RuntimeError(f"{name} missing columns: {sorted(missing)}")
    out = frame.copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    group_cols = ["symbol"]
    if phase_hour is not None or "phase_hour" in out.columns:
        if "phase_hour" not in out.columns:
            out["phase_hour"] = int(phase_hour or 0)
        group_cols.append("phase_hour")
    if out.duplicated(group_cols + ["ts"]).any():
        raise RuntimeError(f"{name} duplicate symbol-phase-ts rows are bad input, not a gap")
    step_ns = int(step.value)
    for key, group in out.groupby(group_cols, sort=True):
        ordered = group.sort_values("ts")
        ts = ordered["ts"]
        if not ts.is_monotonic_increasing:
            raise RuntimeError(f"{name} timestamps are not monotonic for {key}")
        hours = ts.dt.hour.to_numpy()
        minutes = ts.dt.minute.to_numpy()
        seconds = ts.dt.second.to_numpy()
        micros = ts.dt.microsecond.to_numpy()
        if np.any(minutes != 0) or np.any(seconds != 0) or np.any(micros != 0):
            raise RuntimeError(f"{name} timestamps are not on the hour grid for {key}")
        if "phase_hour" in ordered.columns:
            phase = int(ordered["phase_hour"].iloc[0])
            if np.any((hours % 4) != phase):
                raise RuntimeError(
                    f"{name} 4h timestamps are not aligned to phase {phase} for {key}"
                )
        elif step == pd.Timedelta(hours=1) and np.any(hours < 0):
            raise RuntimeError(f"{name} invalid hour-of-day for {key}")
        ns = series_utc_ns(ts)
        if len(ns) >= 2:
            delta = np.diff(ns)
            if np.any(delta <= 0):
                raise RuntimeError(f"{name} non-positive intervals for {key}")
            if np.any(delta % step_ns != 0):
                raise RuntimeError(
                    f"{name} interval is not an integer multiple of {step} for {key}"
                )
    return out.sort_values(group_cols + ["ts"]).reset_index(drop=True)


def assign_contiguous_blocks(frame: pd.DataFrame, step: pd.Timedelta) -> pd.DataFrame:
    """Same continuity rule as P0.add_indicators: reset at non-step intervals."""
    outputs: list[pd.DataFrame] = []
    group_cols = ["symbol"]
    if "phase_hour" in frame.columns:
        group_cols.append("phase_hour")
    for _, group in frame.groupby(group_cols, sort=True):
        block = group.sort_values("ts").copy()
        prior = block["ts"].shift(1)
        block["new_block"] = prior.isna() | ((block["ts"] - prior) != step)
        block["block_id"] = block["new_block"].cumsum().astype(int)
        outputs.append(block)
    if not outputs:
        out = frame.copy()
        out["new_block"] = True
        out["block_id"] = 1
        return out
    return pd.concat(outputs, ignore_index=True)


def window_status(
    ts_ns: np.ndarray,
    start_ns: int,
    n_bars: int,
    step_ns: int,
) -> dict[str, Any]:
    expected = start_ns + np.arange(n_bars, dtype=np.int64) * step_ns
    if n_bars <= 0:
        return {
            "status": "complete",
            "n_present": 0,
            "n_missing": 0,
            "internal_gap": False,
            "right_censor": False,
            "complete": True,
        }
    if ts_ns.size == 0:
        return {
            "status": "right_censor_cutoff",
            "n_present": 0,
            "n_missing": int(n_bars),
            "internal_gap": False,
            "right_censor": True,
            "complete": False,
        }
    idx = np.searchsorted(ts_ns, expected)
    present = (idx < ts_ns.size) & (ts_ns[np.minimum(idx, ts_ns.size - 1)] == expected)
    n_present = int(present.sum())
    n_missing = int((~present).sum())
    if n_missing == 0:
        return {
            "status": "complete",
            "n_present": n_present,
            "n_missing": 0,
            "internal_gap": False,
            "right_censor": False,
            "complete": True,
        }
    last = int(ts_ns[-1])
    missing_expected = expected[~present]
    internal = bool(np.any(missing_expected < last))
    return {
        "status": "internal_gap" if internal else "right_censor_cutoff",
        "n_present": n_present,
        "n_missing": n_missing,
        "internal_gap": internal,
        "right_censor": not internal,
        "complete": False,
    }


def batch_window_status(
    starts_ns: np.ndarray,
    ts_ns: np.ndarray,
    n_bars: int,
    step_ns: int,
) -> dict[str, np.ndarray]:
    n_events = int(len(starts_ns))
    complete = np.zeros(n_events, dtype=bool)
    internal = np.zeros(n_events, dtype=bool)
    right = np.ones(n_events, dtype=bool)
    n_present = np.zeros(n_events, dtype=np.int32)
    if n_events == 0:
        return {
            "complete": complete,
            "internal_gap": internal,
            "right_censor": right,
            "n_present": n_present,
        }
    if n_bars <= 0 or ts_ns.size == 0:
        right[:] = ts_ns.size == 0 or n_bars > 0
        complete[:] = n_bars <= 0
        right &= ~complete
        return {
            "complete": complete,
            "internal_gap": internal,
            "right_censor": right,
            "n_present": n_present,
        }
    expected = starts_ns.astype(np.int64, copy=False)[:, None] + (
        np.arange(n_bars, dtype=np.int64)[None, :] * step_ns
    )
    idx = np.searchsorted(ts_ns, expected)
    in_range = idx < ts_ns.size
    gathered = ts_ns[np.clip(idx, 0, ts_ns.size - 1)]
    present = in_range & (gathered == expected)
    n_present = present.sum(axis=1).astype(np.int32)
    complete = present.all(axis=1)
    last = int(ts_ns[-1])
    missing_before_last = (~present) & (expected < last)
    internal = missing_before_last.any(axis=1) & (~complete)
    right = (~complete) & (~internal)
    return {
        "complete": complete,
        "internal_gap": internal,
        "right_censor": right,
        "n_present": n_present,
    }


def recross_survival_on_grid(
    *,
    signal_bar_ns: int,
    side: int,
    fourh_ts: np.ndarray,
    close: np.ndarray,
    sma7: np.ndarray,
    max_bars: int = MAX_FUTURE_BARS,
) -> dict[str, Any]:
    result = {
        "ma7_recross_bars": math.nan,
        "same_side_survival_bars": math.nan,
        "recross_complete": False,
        "recross_status": "right_censor_cutoff",
        "observed_same_side_bars_before_interrupt": 0,
        "recross_observed_before_interrupt": False,
        "recross_after_gap_bars": math.nan,
        "internal_gap": False,
        "right_censor": False,
        "indicator_undefined": False,
        "exclusive_reason": "right_censor_cutoff",
    }
    if fourh_ts.size == 0:
        result["right_censor"] = True
        return result
    pos = {int(ts): idx for idx, ts in enumerate(fourh_ts.tolist())}
    interrupted = False
    interrupt_reason: str | None = None
    observed = 0
    recross_main = math.nan
    for k in range(1, max_bars + 1):
        expected = signal_bar_ns + k * FOUR_H_NS
        idx = pos.get(int(expected))
        if idx is None:
            has_later = bool(np.any(fourh_ts > expected))
            if not interrupted:
                interrupt_reason = "internal_gap" if has_later else "right_censor_cutoff"
                interrupted = True
            continue
        close_v = float(close[idx])
        sma_v = float(sma7[idx])
        finite = np.isfinite(close_v) and np.isfinite(sma_v)
        hit = False
        if finite:
            hit = close_v <= sma_v if side == 1 else close_v >= sma_v
        if not interrupted:
            if not finite:
                interrupt_reason = "indicator_undefined"
                interrupted = True
                continue
            observed += 1
            if hit:
                recross_main = float(k)
                result["ma7_recross_bars"] = recross_main
                result["same_side_survival_bars"] = float(k - 1)
                result["recross_complete"] = True
                result["recross_status"] = "recross_observed"
                result["recross_observed_before_interrupt"] = True
                result["observed_same_side_bars_before_interrupt"] = observed
                result["exclusive_reason"] = "complete"
                return result
        elif finite and hit and not np.isfinite(result["recross_after_gap_bars"]):
            result["recross_after_gap_bars"] = float(k)

    result["observed_same_side_bars_before_interrupt"] = observed
    if not interrupted and observed == max_bars:
        result["same_side_survival_bars"] = float(max_bars)
        result["recross_complete"] = True
        result["recross_status"] = "completed_no_recross"
        result["exclusive_reason"] = "complete"
        return result
    result["ma7_recross_bars"] = math.nan
    result["same_side_survival_bars"] = math.nan
    result["internal_gap"] = interrupt_reason == "internal_gap"
    result["right_censor"] = interrupt_reason == "right_censor_cutoff"
    result["indicator_undefined"] = interrupt_reason == "indicator_undefined"
    result["recross_status"] = interrupt_reason or "right_censor_cutoff"
    result["exclusive_reason"] = exclusive_reason(
        internal_gap=result["internal_gap"],
        right_censor=result["right_censor"],
        indicator_undefined=result["indicator_undefined"],
    )
    return result


def _cache_fourh(fourh_by_symbol_phase: dict[tuple[str, int], pd.DataFrame]) -> dict[tuple[str, int], dict[str, Any]]:
    cache: dict[tuple[str, int], dict[str, Any]] = {}
    for key, frame in fourh_by_symbol_phase.items():
        ordered = frame.sort_index() if isinstance(frame.index, pd.DatetimeIndex) else frame.sort_values("ts")
        if isinstance(ordered, pd.DataFrame) and not isinstance(ordered.index, pd.DatetimeIndex):
            ts_index = pd.DatetimeIndex(pd.to_datetime(ordered["ts"], utc=True))
        else:
            ts_index = pd.DatetimeIndex(ordered.index)
            if ts_index.tz is None:
                ts_index = ts_index.tz_localize("UTC")
            ordered = ordered.copy()
            if "open" in ordered.columns:
                pass
        ts_ns = datetime_index_ns(ts_index)
        cache[key] = {
            "ts": ts_ns,
            "open": ordered["open"].to_numpy(dtype=float) if "open" in ordered.columns else np.array([]),
            "close": ordered["close"].to_numpy(dtype=float) if "close" in ordered.columns else np.array([]),
            "sma7": ordered["sma7"].to_numpy(dtype=float) if "sma7" in ordered.columns else np.full(len(ts_ns), np.nan),
            "pos": {int(ts): idx for idx, ts in enumerate(ts_ns.tolist())},
        }
    return cache


def _cache_hourly(hourly_by_symbol: dict[str, pd.DataFrame]) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    for symbol, frame in hourly_by_symbol.items():
        ordered = frame.sort_index() if isinstance(frame.index, pd.DatetimeIndex) else frame.sort_values("ts")
        ts_index = (
            pd.DatetimeIndex(ordered.index)
            if isinstance(ordered.index, pd.DatetimeIndex)
            else pd.DatetimeIndex(pd.to_datetime(ordered["ts"], utc=True))
        )
        cache[symbol] = {"ts": datetime_index_ns(ts_index)}
    return cache


def apply_gap_guard(
    events: pd.DataFrame,
    hourly_by_symbol: dict[str, pd.DataFrame],
    fourh_by_symbol_phase: dict[tuple[str, int], pd.DataFrame],
    funding_lookup: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Correct recross/survival and attach per-metric validity. Does not invent fills."""
    del funding_lookup
    output = events.copy().reset_index(drop=True)
    if output.empty:
        return output
    fourh_cache = _cache_fourh(fourh_by_symbol_phase)
    hour_cache = _cache_hourly(hourly_by_symbol)

    recross_vals: list[float] = []
    survival_vals: list[float] = []
    recross_complete: list[bool] = []
    recross_status: list[str] = []
    observed_before: list[int] = []
    recross_before: list[bool] = []
    recross_after: list[float] = []
    recross_reason: list[str] = []
    first_hit_valid: list[bool] = []
    first_hit_reason: list[str] = []
    entry_missing: list[bool] = []

    for horizon in HORIZONS:
        output[f"gross_return_{horizon}_endpoints_only"] = np.nan
        output[f"gross_{horizon}_valid"] = False
        output[f"gross_{horizon}_reason"] = "right_censor_cutoff"
        output[f"mfe_{horizon}_valid"] = False
        output[f"mfe_{horizon}_reason"] = "right_censor_cutoff"
        output[f"net_{horizon}_valid"] = False
        output[f"net_{horizon}_reason"] = "right_censor_cutoff"

    for idx, row in output.iterrows():
        symbol = str(row["symbol"])
        phase = int(row["phase_hour"])
        side = int(row["side"])
        signal_bar_ns = utc_ns(row["ts"])
        entry_ns = utc_ns(row["entry_ts"])
        fourh = fourh_cache.get((symbol, phase))
        hourly = hour_cache.get(symbol)
        fourh_ts = fourh["ts"] if fourh is not None else np.array([], dtype=np.int64)
        hour_ts = hourly["ts"] if hourly is not None else np.array([], dtype=np.int64)

        entry_absent = fourh is None or entry_ns not in fourh["pos"]
        entry_missing.append(bool(entry_absent))

        recross = recross_survival_on_grid(
            signal_bar_ns=signal_bar_ns,
            side=side,
            fourh_ts=fourh_ts,
            close=fourh["close"] if fourh is not None else np.array([]),
            sma7=fourh["sma7"] if fourh is not None else np.array([]),
        )
        recross_vals.append(recross["ma7_recross_bars"])
        survival_vals.append(recross["same_side_survival_bars"])
        recross_complete.append(bool(recross["recross_complete"]))
        recross_status.append(str(recross["recross_status"]))
        observed_before.append(int(recross["observed_same_side_bars_before_interrupt"]))
        recross_before.append(bool(recross["recross_observed_before_interrupt"]))
        recross_after.append(recross["recross_after_gap_bars"])
        recross_reason.append(
            exclusive_reason(entry_bar_missing=entry_absent, complete=recross["recross_complete"])
            if entry_absent
            else recross["exclusive_reason"]
        )

        first_hit_1h = window_status(hour_ts, entry_ns, 4 * MAX_FUTURE_BARS, ONE_H_NS)
        first_hit_4h = window_status(fourh_ts, entry_ns, MAX_FUTURE_BARS, FOUR_H_NS)
        fh_complete = bool(first_hit_1h["complete"])
        first_hit_valid.append(fh_complete)
        first_hit_reason.append(
            exclusive_reason(
                entry_bar_missing=entry_absent,
                internal_gap=first_hit_1h["internal_gap"],
                path_1h_missing=first_hit_4h["complete"] and not first_hit_1h["complete"],
                right_censor=first_hit_1h["right_censor"]
                and not (first_hit_4h["complete"] and not first_hit_1h["complete"]),
                complete=fh_complete,
            )
        )
        if not fh_complete:
            output.at[idx, "first_hit_label"] = "incomplete_future"
            output.at[idx, "first_hit_hour"] = math.nan

        entry_price = float(row["entry_price"])
        for horizon in HORIZONS:
            gross_win = window_status(fourh_ts, entry_ns, horizon + 1, FOUR_H_NS)
            mfe_win = window_status(hour_ts, entry_ns, 4 * horizon, ONE_H_NS)
            exit_ns = entry_ns + horizon * FOUR_H_NS
            exit_pos = fourh["pos"].get(int(exit_ns)) if fourh is not None else None
            if exit_pos is not None and not entry_absent:
                exit_open = float(fourh["open"][exit_pos])
                output.at[idx, f"gross_return_{horizon}_endpoints_only"] = side * (
                    exit_open / entry_price - 1.0
                )
            if gross_win["complete"]:
                output.at[idx, f"gross_{horizon}_valid"] = True
                output.at[idx, f"gross_{horizon}_reason"] = "complete"
            else:
                output.at[idx, f"gross_return_{horizon}"] = math.nan
                output.at[idx, f"net_return_4bps_{horizon}"] = math.nan
                output.at[idx, f"net_return_8bps_{horizon}"] = math.nan
                output.at[idx, f"gross_{horizon}_valid"] = False
                output.at[idx, f"gross_{horizon}_reason"] = exclusive_reason(
                    entry_bar_missing=entry_absent,
                    internal_gap=gross_win["internal_gap"],
                    right_censor=gross_win["right_censor"],
                )
            output.at[idx, f"mfe_{horizon}_valid"] = bool(mfe_win["complete"])
            output.at[idx, f"mfe_{horizon}_reason"] = exclusive_reason(
                entry_bar_missing=entry_absent,
                internal_gap=mfe_win["internal_gap"],
                path_1h_missing=gross_win["complete"] and not mfe_win["complete"],
                right_censor=mfe_win["right_censor"]
                and not (gross_win["complete"] and not mfe_win["complete"]),
                complete=mfe_win["complete"],
            )
            if not mfe_win["complete"]:
                output.at[idx, f"mfe_{horizon}"] = math.nan
                output.at[idx, f"mae_{horizon}"] = math.nan
                output.at[idx, f"mfe_bar_{horizon}"] = math.nan
                output.at[idx, f"mae_bar_{horizon}"] = math.nan
            funding_ok = bool(output.at[idx, f"funding_complete_{horizon}"])
            net_ok = bool(gross_win["complete"] and funding_ok)
            output.at[idx, f"net_{horizon}_valid"] = net_ok
            output.at[idx, f"net_{horizon}_reason"] = exclusive_reason(
                entry_bar_missing=entry_absent,
                internal_gap=gross_win["internal_gap"],
                right_censor=gross_win["right_censor"],
                funding_missing=gross_win["complete"] and not funding_ok,
                complete=net_ok,
            )
            if not net_ok:
                output.at[idx, f"net_return_4bps_{horizon}"] = math.nan
                output.at[idx, f"net_return_8bps_{horizon}"] = math.nan

    output["ma7_recross_bars"] = recross_vals
    output["same_side_survival_bars"] = survival_vals
    output["recross_complete"] = recross_complete
    output["recross_status"] = recross_status
    output["observed_same_side_bars_before_interrupt"] = observed_before
    output["recross_observed_before_interrupt"] = recross_before
    output["recross_after_gap_bars"] = recross_after
    output["recross_reason"] = recross_reason
    output["first_hit_valid"] = first_hit_valid
    output["first_hit_reason"] = first_hit_reason
    output["entry_bar_missing"] = entry_missing
    output["survival_valid"] = recross_complete
    return output


def enrich_outcomes_gap_aware(
    events: pd.DataFrame,
    hourly_by_symbol: dict[str, pd.DataFrame],
    fourh_by_symbol_phase: dict[tuple[str, int], pd.DataFrame],
    funding_lookup: dict[str, Any],
) -> pd.DataFrame:
    labeled = enrich_outcomes(events, hourly_by_symbol, fourh_by_symbol_phase, funding_lookup)
    return apply_gap_guard(labeled, hourly_by_symbol, fourh_by_symbol_phase, funding_lookup)


def first_hit_success_rate(frame: pd.DataFrame) -> float:
    if frame.empty or "first_hit_valid" not in frame.columns:
        return math.nan
    valid = frame.loc[frame["first_hit_valid"]]
    if valid.empty:
        return math.nan
    return float(valid["first_hit_label"].eq("favorable_first").mean())


def guarded_mean(frame: pd.DataFrame, column: str, valid_col: str) -> float:
    if frame.empty or valid_col not in frame.columns or column not in frame.columns:
        return math.nan
    return weighted_mean(frame.loc[frame[valid_col], column])


def summarize_guarded_first_hit(events: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    primary = events.loc[events["phase_hour"].eq(0) & events["ma_period"].eq(PRIMARY_MA)].copy()
    for direction in ("long", "short"):
        event_side = primary.loc[primary["direction"].eq(direction)]
        control_side = controls.loc[controls["direction"].eq(direction)]
        event_valid = event_side.loc[event_side["first_hit_valid"]]
        if "first_hit_valid" in control_side.columns:
            control_valid = control_side.loc[control_side["first_hit_valid"]]
        else:
            control_valid = control_side
        rows.append(
            {
                "direction": direction,
                "candidates": int(len(event_side)),
                "valid": int(len(event_valid)),
                "interrupted": int(len(event_side) - len(event_valid)),
                "event_favorable_rate": first_hit_success_rate(event_side),
                "control_candidates": int(len(control_side)),
                "control_valid": int(len(control_valid)),
                "control_favorable_rate": first_hit_success_rate(control_side),
            }
        )
    return pd.DataFrame(rows)


def classify_windows_for_inventory(
    events: pd.DataFrame,
    fourh_by_symbol_phase: dict[tuple[str, int], pd.DataFrame],
    hourly_by_symbol: dict[str, pd.DataFrame],
    *,
    sample_kind: str,
) -> pd.DataFrame:
    """Window availability only. Does not compute returns, first-hit hits, or bootstrap."""
    if events.empty:
        return events.copy()
    out = events.copy().reset_index(drop=True)
    out["sample_kind"] = sample_kind
    fourh_cache = _cache_fourh(fourh_by_symbol_phase)
    hour_cache = _cache_hourly(hourly_by_symbol)
    reason_cols = ["first_hit_reason", "recross_reason", "entry_reason"]
    for horizon in HORIZONS:
        reason_cols.append(f"gross_{horizon}_reason")
        reason_cols.append(f"mfe_{horizon}_reason")
    grouped = list(out.groupby(["symbol", "phase_hour"], sort=False))
    assigned = {name: [""] * len(out) for name in reason_cols}
    recross_complete_arr = [False] * len(out)
    recross_after_arr = [math.nan] * len(out)
    observed_arr = [0] * len(out)

    for (symbol, phase), group in grouped:
        fourh = fourh_cache.get((str(symbol), int(phase)))
        hourly = hour_cache.get(str(symbol))
        fourh_ts = fourh["ts"] if fourh is not None else np.array([], dtype=np.int64)
        hour_ts = hourly["ts"] if hourly is not None else np.array([], dtype=np.int64)
        close = fourh["close"] if fourh is not None else np.array([])
        sma7 = fourh["sma7"] if fourh is not None else np.array([])
        pos = fourh["pos"] if fourh is not None else {}
        entry_ns = series_utc_ns(group["entry_ts"])
        signal_ns = series_utc_ns(group["ts"])
        sides = group["side"].to_numpy(dtype=int)
        index = group.index.to_numpy()

        entry_present = np.array([int(ts) in pos for ts in entry_ns], dtype=bool)
        fh_1h = batch_window_status(entry_ns, hour_ts, 4 * MAX_FUTURE_BARS, ONE_H_NS)
        fh_4h = batch_window_status(entry_ns, fourh_ts, MAX_FUTURE_BARS, FOUR_H_NS)

        for local_i, row_idx in enumerate(index):
            entry_miss = not bool(entry_present[local_i])
            assigned["entry_reason"][row_idx] = exclusive_reason(
                entry_bar_missing=entry_miss, complete=not entry_miss
            )
            assigned["first_hit_reason"][row_idx] = exclusive_reason(
                entry_bar_missing=entry_miss,
                internal_gap=bool(fh_1h["internal_gap"][local_i]),
                path_1h_missing=bool(fh_4h["complete"][local_i] and not fh_1h["complete"][local_i]),
                right_censor=bool(fh_1h["right_censor"][local_i])
                and not bool(fh_4h["complete"][local_i] and not fh_1h["complete"][local_i]),
                complete=bool(fh_1h["complete"][local_i]),
            )
            recross = recross_survival_on_grid(
                signal_bar_ns=int(signal_ns[local_i]),
                side=int(sides[local_i]),
                fourh_ts=fourh_ts,
                close=close,
                sma7=sma7,
            )
            recross_complete_arr[row_idx] = bool(recross["recross_complete"])
            recross_after_arr[row_idx] = recross["recross_after_gap_bars"]
            observed_arr[row_idx] = int(recross["observed_same_side_bars_before_interrupt"])
            assigned["recross_reason"][row_idx] = (
                exclusive_reason(entry_bar_missing=True)
                if entry_miss
                else recross["exclusive_reason"]
            )

        for horizon in HORIZONS:
            g = batch_window_status(entry_ns, fourh_ts, horizon + 1, FOUR_H_NS)
            m = batch_window_status(entry_ns, hour_ts, 4 * horizon, ONE_H_NS)
            for local_i, row_idx in enumerate(index):
                entry_miss = not bool(entry_present[local_i])
                assigned[f"gross_{horizon}_reason"][row_idx] = exclusive_reason(
                    entry_bar_missing=entry_miss,
                    internal_gap=bool(g["internal_gap"][local_i]),
                    right_censor=bool(g["right_censor"][local_i]),
                    complete=bool(g["complete"][local_i]),
                )
                assigned[f"mfe_{horizon}_reason"][row_idx] = exclusive_reason(
                    entry_bar_missing=entry_miss,
                    internal_gap=bool(m["internal_gap"][local_i]),
                    path_1h_missing=bool(g["complete"][local_i] and not m["complete"][local_i]),
                    right_censor=bool(m["right_censor"][local_i])
                    and not bool(g["complete"][local_i] and not m["complete"][local_i]),
                    complete=bool(m["complete"][local_i]),
                )

    for name, values in assigned.items():
        out[name] = values
    out["recross_complete"] = recross_complete_arr
    out["recross_after_gap_bars"] = recross_after_arr
    out["observed_same_side_bars_before_interrupt"] = observed_arr
    out["first_hit_valid"] = out["first_hit_reason"].eq("complete")
    out["survival_valid"] = out["recross_reason"].eq("complete")
    for horizon in HORIZONS:
        out[f"gross_{horizon}_valid"] = out[f"gross_{horizon}_reason"].eq("complete")
        out[f"mfe_{horizon}_valid"] = out[f"mfe_{horizon}_reason"].eq("complete")
    if "signal_ts" in out.columns:
        out["calendar_year"] = pd.to_datetime(out["signal_ts"], utc=True).dt.year.astype(int)
    elif "ts" in out.columns:
        out["calendar_year"] = pd.to_datetime(out["ts"], utc=True).dt.year.astype(int)
    return out


def inventory_metric_specs() -> list[dict[str, str]]:
    specs = [
        {"metric": "first_hit_30", "reason_col": "first_hit_reason"},
        {"metric": "ma7_recross_survival_30", "reason_col": "recross_reason"},
    ]
    for horizon in HORIZONS:
        specs.append({"metric": f"gross_return_{horizon}", "reason_col": f"gross_{horizon}_reason"})
        specs.append({"metric": f"mfe_mae_{horizon}", "reason_col": f"mfe_{horizon}_reason"})
    return specs


def reason_counts(frame: pd.DataFrame, reason_col: str) -> dict[str, int]:
    counts = {name: 0 for name in EXCLUSIVE_REASON_PRIORITY}
    if frame.empty or reason_col not in frame.columns:
        counts["candidates"] = 0
        return counts
    vc = frame[reason_col].value_counts(dropna=False)
    for name, value in vc.items():
        key = str(name)
        if key in counts:
            counts[key] = int(value)
    counts["candidates"] = int(len(frame))
    return counts


def checksum_ok(counts: dict[str, int]) -> bool:
    total = int(counts.get("candidates", 0))
    summed = sum(int(counts.get(name, 0)) for name in EXCLUSIVE_REASON_PRIORITY)
    return total == summed


def build_inventory_tables(classified: pd.DataFrame) -> dict[str, pd.DataFrame]:
    specs = inventory_metric_specs()
    metric_rows: list[dict[str, Any]] = []
    direction_rows: list[dict[str, Any]] = []
    year_rows: list[dict[str, Any]] = []
    phase_rows: list[dict[str, Any]] = []
    symbol_rows: list[dict[str, Any]] = []

    kinds = sorted(classified["sample_kind"].unique()) if "sample_kind" in classified.columns else ["events"]
    for kind in kinds:
        subset = classified.loc[classified["sample_kind"].eq(kind)] if "sample_kind" in classified.columns else classified
        for spec in specs:
            counts = reason_counts(subset, spec["reason_col"])
            metric_rows.append(
                {
                    "sample_kind": kind,
                    "metric": spec["metric"],
                    **{name: counts.get(name, 0) for name in EXCLUSIVE_REASON_PRIORITY},
                    "candidates": counts["candidates"],
                    "valid": counts.get("complete", 0),
                    "checksum_ok": checksum_ok(counts),
                    "internal_gap_rate": (
                        counts.get("internal_gap", 0) / counts["candidates"] if counts["candidates"] else math.nan
                    ),
                    "right_censor_rate": (
                        counts.get("right_censor_cutoff", 0) / counts["candidates"] if counts["candidates"] else math.nan
                    ),
                    "valid_rate": (
                        counts.get("complete", 0) / counts["candidates"] if counts["candidates"] else math.nan
                    ),
                }
            )
            for direction, group in subset.groupby("direction", sort=True):
                dcounts = reason_counts(group, spec["reason_col"])
                direction_rows.append(
                    {
                        "sample_kind": kind,
                        "metric": spec["metric"],
                        "direction": direction,
                        **{name: dcounts.get(name, 0) for name in EXCLUSIVE_REASON_PRIORITY},
                        "candidates": dcounts["candidates"],
                        "valid": dcounts.get("complete", 0),
                        "checksum_ok": checksum_ok(dcounts),
                    }
                )
            if "calendar_year" in subset.columns:
                for year, group in subset.groupby("calendar_year", sort=True):
                    ycounts = reason_counts(group, spec["reason_col"])
                    year_rows.append(
                        {
                            "sample_kind": kind,
                            "metric": spec["metric"],
                            "calendar_year": int(year),
                            "candidates": ycounts["candidates"],
                            "valid": ycounts.get("complete", 0),
                            "internal_gap": ycounts.get("internal_gap", 0),
                            "right_censor_cutoff": ycounts.get("right_censor_cutoff", 0),
                            "indicator_warmup_insufficient": ycounts.get("indicator_warmup_insufficient", 0),
                            "path_1h_missing": ycounts.get("path_1h_missing", 0),
                            "checksum_ok": checksum_ok(ycounts),
                        }
                    )
            if "phase_hour" in subset.columns:
                for phase, group in subset.groupby("phase_hour", sort=True):
                    pcounts = reason_counts(group, spec["reason_col"])
                    phase_rows.append(
                        {
                            "sample_kind": kind,
                            "metric": spec["metric"],
                            "phase_hour": int(phase),
                            "candidates": pcounts["candidates"],
                            "valid": pcounts.get("complete", 0),
                            "internal_gap": pcounts.get("internal_gap", 0),
                            "right_censor_cutoff": pcounts.get("right_censor_cutoff", 0),
                            "path_1h_missing": pcounts.get("path_1h_missing", 0),
                            "checksum_ok": checksum_ok(pcounts),
                        }
                    )
            if spec["metric"] in {"first_hit_30", "ma7_recross_survival_30", "gross_return_30"}:
                for symbol, group in subset.groupby("symbol", sort=True):
                    scounts = reason_counts(group, spec["reason_col"])
                    if scounts["candidates"] == 0:
                        continue
                    symbol_rows.append(
                        {
                            "sample_kind": kind,
                            "metric": spec["metric"],
                            "symbol": symbol,
                            "candidates": scounts["candidates"],
                            "valid": scounts.get("complete", 0),
                            "internal_gap": scounts.get("internal_gap", 0),
                            "right_censor_cutoff": scounts.get("right_censor_cutoff", 0),
                            "path_1h_missing": scounts.get("path_1h_missing", 0),
                            "affected": scounts["candidates"] - scounts.get("complete", 0),
                        }
                    )

    return {
        "by_metric": pd.DataFrame(metric_rows),
        "by_direction": pd.DataFrame(direction_rows),
        "by_year": pd.DataFrame(year_rows),
        "by_phase": pd.DataFrame(phase_rows),
        "by_symbol": pd.DataFrame(symbol_rows),
    }


def warmup_bar_counts(panel: pd.DataFrame) -> dict[str, int]:
    if panel.empty:
        return {
            "pool_bars": 0,
            "indicator_warmup_insufficient": 0,
            "atr_period": int(ATR_PERIOD),
        }
    pool = panel.loc[panel["in_trading_pool"].fillna(False)].copy()
    sma_ok = np.isfinite(pool.get("sma7", pd.Series(dtype=float)).to_numpy(dtype=float))
    atr_ok = np.isfinite(pool.get("atr_scale", pd.Series(dtype=float)).to_numpy(dtype=float))
    atr_pos = pool.get("atr_scale", pd.Series(dtype=float)).to_numpy(dtype=float) > 0
    insufficient = ~(sma_ok & atr_ok & atr_pos)
    return {
        "pool_bars": int(len(pool)),
        "indicator_warmup_insufficient": int(insufficient.sum()),
        "atr_period": int(ATR_PERIOD),
    }


def discover_internal_gaps(
    frame: pd.DataFrame,
    step: pd.Timedelta,
    *,
    symbol: str | None = None,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    view = frame.copy()
    view["ts"] = pd.to_datetime(view["ts"], utc=True)
    if symbol is not None:
        view = view.loc[view["symbol"].eq(symbol)]
    if start is not None:
        view = view.loc[view["ts"] >= pd.Timestamp(start)]
    if end is not None:
        view = view.loc[view["ts"] < pd.Timestamp(end)]
    rows: list[dict[str, Any]] = []
    group_cols = ["symbol"]
    if "phase_hour" in view.columns:
        group_cols.append("phase_hour")
    for key, group in view.groupby(group_cols, sort=True):
        ordered = group.sort_values("ts")
        ts = ordered["ts"].to_numpy()
        if len(ts) < 2:
            continue
        delta = pd.Series(ordered["ts"]).diff()
        holes = delta.gt(step)
        for loc in np.flatnonzero(holes.to_numpy()):
            prev_ts = ordered["ts"].iloc[loc - 1]
            next_ts = ordered["ts"].iloc[loc]
            missing = int((next_ts - prev_ts) / step) - 1
            rows.append(
                {
                    "symbol": ordered["symbol"].iloc[loc],
                    "phase_hour": int(ordered["phase_hour"].iloc[loc]) if "phase_hour" in ordered.columns else 0,
                    "gap_after_ts": prev_ts.isoformat(),
                    "gap_resume_ts": next_ts.isoformat(),
                    "missing_bars": missing,
                }
            )
    return pd.DataFrame(rows)
