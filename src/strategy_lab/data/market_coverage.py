"""Complete requested-window coverage, preserving input order and multiplicity."""

from importlib.metadata import version
import pandas as pd


class MarketCoverageValidator:
    def validate(
        self, timestamps, *, requested_start, requested_end, frequency, calendar
    ):
        start, end = pd.Timestamp(requested_start), pd.Timestamp(requested_end)
        ts = pd.DatetimeIndex(timestamps)
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("Ordered timezone-aware requested boundaries required")
        start, end = start.tz_convert("UTC"), end.tz_convert("UTC")
        base = dict(
            requested_start=start.isoformat(),
            requested_end=end.isoformat(),
            actual_start=ts.min().isoformat()
            if len(ts) and not ts.isna().all()
            else None,
            actual_end=ts.max().isoformat()
            if len(ts) and not ts.isna().all()
            else None,
            expected_count=None,
            actual_count=len(ts),
            gap_count=None,
            duplicate_count=int(ts.duplicated().sum()),
            unexpected_count=0,
            ordered=ts.is_monotonic_increasing,
            calendar=calendar,
            calendar_version="UNKNOWN",
            coverage_status="UNKNOWN",
            coverage_reason="Unsupported calendar/frequency",
        )
        if ts.isna().any() or (len(ts) and ts.tz is None):
            return {
                **base,
                "coverage_status": "INVALID",
                "coverage_reason": "Invalid or timezone-naive bar timestamp",
            }
        if calendar == "CRYPTO_24_7":
            try:
                step = pd.Timedelta(frequency)
            except ValueError:
                return base
            if (
                step <= pd.Timedelta(0)
                or start.value % step.value
                or end.value % step.value
            ):
                return {
                    **base,
                    "coverage_status": "INVALID",
                    "coverage_reason": "Unaligned requested boundaries",
                }
            expected = pd.date_range(start, end, freq=step, inclusive="left")
            base["calendar_version"] = "crypto-utc-grid-v1"
        elif frequency == "1d":
            import exchange_calendars as xcals

            try:
                cal = xcals.get_calendar(calendar, start=start.date(), end=end.date())
                expected = pd.DatetimeIndex(
                    cal.sessions_in_range(
                        start.date(), (end - pd.Timedelta(nanoseconds=1)).date()
                    )
                )
                expected = (
                    expected.tz_localize("UTC")
                    if expected.tz is None
                    else expected.tz_convert("UTC")
                )
                expected = expected[(expected >= start) & (expected < end)]
                base["calendar_version"] = "exchange-calendars-" + version(
                    "exchange-calendars"
                )
            except (ValueError, KeyError):
                return base
        else:
            return base
        observed = ts.tz_convert("UTC") if len(ts) else pd.DatetimeIndex([], tz="UTC")
        missing, extra = expected.difference(observed), observed.difference(expected)
        base.update(
            expected_count=len(expected),
            gap_count=len(missing),
            unexpected_count=len(extra),
        )
        if base["duplicate_count"] or not base["ordered"] or len(extra):
            return {
                **base,
                "coverage_status": "INVALID",
                "coverage_reason": "Duplicate, unordered or unexpected bars",
            }
        if len(missing):
            return {
                **base,
                "coverage_status": "PARTIAL",
                "coverage_reason": "Missing requested bars, including boundary and interior checks",
            }
        if not len(expected):
            return {
                **base,
                "coverage_status": "UNKNOWN",
                "coverage_reason": "Requested window has no expected sessions",
            }
        return {
            **base,
            "coverage_status": "VERIFIED",
            "coverage_reason": "Exact ordered unique match to every requested calendar bar",
        }
