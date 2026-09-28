from __future__ import annotations

from enum import StrEnum
from importlib.metadata import version
import re

import exchange_calendars as xcals
import pandas as pd


class OHLCVSessionPolicy(StrEnum):
    """Trading-session grid used to audit OHLCV continuity and closure."""

    CONTINUOUS_24_7 = "continuous_24_7"
    XNAS_REGULAR = "xnas_regular"


def timeframe_delta(value: str) -> pd.Timedelta:
    match = re.fullmatch(r"([1-9]\d*)([mhdw])", str(value).strip().lower())
    if not match:
        raise ValueError(f"unsupported timeframe: {value!r}")
    amount, unit = match.groups()
    unit_map = {"m": "min", "h": "h", "d": "D", "w": "W"}
    return pd.Timedelta(int(amount), unit=unit_map[unit])


def _as_utc(value: pd.Timestamp | str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def session_policy_metadata(
    policy: OHLCVSessionPolicy | str,
) -> dict[str, str | None]:
    resolved = OHLCVSessionPolicy(policy)
    if resolved == OHLCVSessionPolicy.CONTINUOUS_24_7:
        return {
            "policy": resolved.value,
            "calendar": None,
            "calendar_timezone": "UTC",
            "calendar_package": None,
            "calendar_package_version": None,
            "session_type": "continuous",
        }
    calendar = xcals.get_calendar("XNAS")
    return {
        "policy": resolved.value,
        "calendar": "XNAS",
        "calendar_timezone": str(calendar.tz),
        "calendar_package": "exchange-calendars",
        "calendar_package_version": version("exchange-calendars"),
        "session_type": "regular",
    }


def expected_ohlcv_session_bars(
    *,
    start: pd.Timestamp | str,
    end: pd.Timestamp | str,
    timeframe: str,
    session_policy: OHLCVSessionPolicy | str,
) -> pd.DataFrame:
    """Return the authoritative bar-open grid for a bounded session range."""

    policy = OHLCVSessionPolicy(session_policy)
    if policy != OHLCVSessionPolicy.XNAS_REGULAR:
        raise ValueError(
            "expected_ohlcv_session_bars requires a calendar-backed session policy"
        )
    start_ts = _as_utc(start)
    end_ts = _as_utc(end)
    if end_ts < start_ts:
        raise ValueError("session audit end must not precede start")

    interval = timeframe_delta(timeframe)
    if interval >= pd.Timedelta(days=1):
        raise ValueError(
            f"{policy.value} currently supports intraday OHLCV only, got {timeframe!r}"
        )

    calendar = xcals.get_calendar("XNAS")
    sessions = calendar.sessions_in_range(start_ts.date(), end_ts.date())
    columns = [
        "ts",
        "bar_close_ts",
        "session",
        "session_open",
        "session_close",
        "session_type",
        "session_calendar",
        "session_policy",
    ]
    if sessions.empty:
        return pd.DataFrame(columns=columns)

    intervals = calendar.trading_index(
        sessions[0],
        sessions[-1],
        period=interval,
        intervals=True,
        closed="left",
        force_close=True,
    )
    if not isinstance(intervals, pd.IntervalIndex):  # pragma: no cover
        raise TypeError("calendar did not return an interval index")

    bar_opens = pd.DatetimeIndex(intervals.left).tz_convert("UTC")
    bar_closes = pd.DatetimeIndex(intervals.right).tz_convert("UTC")
    session_labels = calendar.minutes_to_sessions(bar_opens)
    schedule = calendar.schedule.loc[session_labels]
    result = pd.DataFrame(
        {
            "ts": bar_opens,
            "bar_close_ts": bar_closes,
            "session": session_labels.strftime("%Y-%m-%d"),
            "session_open": pd.DatetimeIndex(schedule["open"]).tz_convert("UTC"),
            "session_close": pd.DatetimeIndex(schedule["close"]).tz_convert("UTC"),
            "session_type": "regular",
            "session_calendar": "XNAS",
            "session_policy": policy.value,
        }
    )
    return result.loc[
        result["bar_close_ts"].gt(start_ts) & result["ts"].le(end_ts)
    ].reset_index(drop=True)
