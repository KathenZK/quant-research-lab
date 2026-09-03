from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from strategy_lab.data.sessions import timeframe_delta

GapPolicy = Literal["reject", "contiguous_segments", "report_only"]
LoadPurpose = Literal["research", "governance_audit", "unspecified"]


def require_aware_utc(value: pd.Timestamp | str, *, field: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware UTC, got naive {timestamp!r}")
    return timestamp.tz_convert("UTC")


def bar_close(ts: pd.Timestamp, timeframe: str) -> pd.Timestamp:
    return ts + timeframe_delta(timeframe)


def closed_bar_cutoff_sql(timeframe: str, ts_column: str = "ts") -> str:
    seconds = int(timeframe_delta(timeframe).total_seconds())
    return f"(({ts_column} + INTERVAL '{seconds} seconds') <= ?)"


def closed_bar_end_filter(timeframe: str | None, cutoff: pd.Timestamp) -> tuple[str, pd.Timestamp]:
    if not timeframe:
        return "ts < ?", cutoff
    return closed_bar_cutoff_sql(timeframe), cutoff


def output_bar_closes_by_cutoff(ts: pd.Timestamp, timeframe: str, cutoff: pd.Timestamp) -> bool:
    return bar_close(ts, timeframe) <= cutoff


def assert_request_window_covered(
    *,
    dataset_id: str,
    timeframe: str,
    requested_start: pd.Timestamp | None,
    requested_end: pd.Timestamp | None,
    available_start: pd.Timestamp | None,
    available_end: pd.Timestamp | None,
    allow_incomplete_request_window: bool,
) -> dict[str, Any]:
    payload = {
        "dataset_id": dataset_id,
        "requested_start": None if requested_start is None else requested_start.isoformat(),
        "requested_end": None if requested_end is None else requested_end.isoformat(),
        "available_start": None if available_start is None else available_start.isoformat(),
        "available_end": None if available_end is None else available_end.isoformat(),
        "available_last_bar_close": None
        if available_end is None
        else bar_close(available_end, timeframe).isoformat(),
    }
    if allow_incomplete_request_window:
        payload["window_status"] = "EXPLICIT_DIAGNOSTIC_TRUNCATION_ALLOWED"
        return payload
    failures: list[str] = []
    if requested_start is not None and available_start is not None and requested_start < available_start:
        failures.append(
            f"requested start {requested_start.isoformat()} is before available start {available_start.isoformat()}"
        )
    if requested_end is not None and available_end is not None:
        last_close = bar_close(available_end, timeframe)
        if requested_end > last_close:
            failures.append(
                f"requested cutoff {requested_end.isoformat()} is after last available bar close {last_close.isoformat()}"
            )
    if failures:
        payload["window_status"] = "REQUEST_WINDOW_EXCEEDS_AVAILABLE"
        payload["delta"] = failures
        raise ValueError(
            f"dataset {dataset_id} REQUEST_WINDOW_EXCEEDS_AVAILABLE: {failures}; "
            f"requested_end={payload['requested_end']} available_last_bar_close="
            f"{payload['available_last_bar_close']} delta={failures}; "
            "pass allow_incomplete_request_window=True with EXPLICIT_DIAGNOSTIC to opt in"
        )
    payload["window_status"] = "COVERED"
    return payload


@dataclass(frozen=True, slots=True)
class GapInterval:
    symbol: str
    prev_ts: pd.Timestamp
    next_ts: pd.Timestamp
    missing_bars: int
    aligned: bool
    listing_evidence: str = "unknown"


def gap_intervals_from_timestamps(
    symbol: str,
    timestamps: pd.Series,
    timeframe: str,
) -> list[GapInterval]:
    seconds = int(timeframe_delta(timeframe).total_seconds())
    ordered = pd.to_datetime(pd.Series(timestamps), utc=True).sort_values().reset_index(drop=True)
    gaps: list[GapInterval] = []
    for prev, nxt in zip(ordered.iloc[:-1], ordered.iloc[1:]):
        delta = int((nxt - prev).total_seconds())
        if delta <= seconds:
            continue
        missing = (delta // seconds) - 1
        aligned = delta % seconds == 0
        gaps.append(
            GapInterval(
                symbol=symbol,
                prev_ts=prev,
                next_ts=nxt,
                missing_bars=int(missing),
                aligned=bool(aligned),
                listing_evidence="unknown",
            )
        )
    return gaps


def contiguous_segments(
    timestamps: pd.Series,
    timeframe: str,
) -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    seconds = int(timeframe_delta(timeframe).total_seconds())
    ordered = pd.to_datetime(pd.Series(timestamps), utc=True).sort_values().reset_index(drop=True)
    if ordered.empty:
        return []
    segments: list[tuple[pd.Timestamp, pd.Timestamp, int]] = []
    start = ordered.iloc[0]
    prev = start
    count = 1
    for ts in ordered.iloc[1:]:
        delta = int((ts - prev).total_seconds())
        if delta == seconds:
            prev = ts
            count += 1
            continue
        segments.append((start, prev, count))
        start = ts
        prev = ts
        count = 1
    segments.append((start, prev, count))
    return segments


def lookback_crosses_gap(
    timestamps: pd.Series,
    *,
    timeframe: str,
    lookback: int,
) -> bool:
    ordered = pd.to_datetime(pd.Series(timestamps), utc=True).sort_values().reset_index(drop=True)
    if len(ordered) < lookback:
        return True
    seconds = int(timeframe_delta(timeframe).total_seconds())
    window = ordered.iloc[-lookback:]
    expected = seconds * (lookback - 1)
    span = int((window.iloc[-1] - window.iloc[0]).total_seconds())
    return span != expected


def holding_window_has_gap(
    timestamps: pd.Series,
    *,
    timeframe: str,
    start: pd.Timestamp,
    horizon_bars: int,
) -> bool:
    seconds = int(timeframe_delta(timeframe).total_seconds())
    ordered = pd.to_datetime(pd.Series(timestamps), utc=True).sort_values()
    end = start + pd.Timedelta(seconds=seconds * horizon_bars)
    window = ordered[(ordered >= start) & (ordered <= end)]
    expected = horizon_bars + 1
    return len(window) != expected
