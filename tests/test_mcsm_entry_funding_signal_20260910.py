"""Causal feature boundaries, explicit unknowns, unit cash and calendar blocks."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

DIRECTORY = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
SPEC = importlib.util.spec_from_file_location("entryfund0910", DIRECTORY / "research_mcsm_entry_funding_signal_20260910.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def events(times, rates, types=None):
    n = len(times)
    return pd.DataFrame({"symbol": ["AAA"] * n, "ts": pd.to_datetime(times, utc=True),
                         "event_id": [f"event-{i}" for i in range(n)], "funding_rate": rates,
                         "rate_type": types or ["Regular"] * n, "event_unambiguous": [True] * n,
                         "mark_center": [100.] * n})


def test_month_open_and_post_entry_cannot_leak_into_signal():
    source = events(["2025-12-28T23:59:59Z", "2025-12-29T00:00:00Z", "2025-12-31T23:59:59Z",
                     "2026-01-01T00:00:00Z", "2026-01-01T00:15:00Z"], [.8, .01, -.03, 100., 100.])
    result = MOD.pre_entry_feature(source, pd.Timestamp("2026-01-01T00:00:00Z"))
    assert result["pre_observed_events"] == 2
    assert result["pre72_rate_sum"] == pytest.approx(-.02)
    assert result["pre72_sign"] == result["latest_sign"] == "NEGATIVE"


def test_empty_pre_events_are_unknown_not_zero():
    source = events([], [])
    result = MOD.pre_entry_feature(source, pd.Timestamp("2026-01-01T00:00:00Z"))
    assert result["pre72_rate_sum"] is None
    assert result["pre72_sign"] == result["latest_sign"] == "UNKNOWN"


def test_special_not_mixed_with_regular_unspecified_is_labeled():
    source = events(["2025-12-31T12:00:00Z", "2025-12-31T16:00:00Z"], [-100., .01],
                    ["Special", "Unspecified"])
    result = MOD.pre_entry_feature(source, pd.Timestamp("2026-01-01T00:00:00Z"))
    assert result["pre72_rate_sum"] == .01
    assert result["pre_special_events"] == result["pre_unspecified_events"] == 1
    assert result["pre_observation_status"] == "OBSERVED_ONLY"


def test_ambiguous_pre_events_make_feature_unknown():
    source = events(["2025-12-31T16:00:00Z"], [-.01])
    source.loc[0, "event_unambiguous"] = False
    assert MOD.pre_entry_feature(source, pd.Timestamp("2026-01-01T00:00:00Z"))["pre72_sign"] == "UNKNOWN"


@pytest.mark.parametrize("time", ["2026-01-01", "2026-01-02T00:00:00Z", "2026-01-01T00:15:00Z"])
def test_signal_timestamp_must_be_utc_month_boundary(time):
    with pytest.raises(ValueError):
        MOD.pre_entry_feature(events([], []), pd.Timestamp(time))


def holding(terminal=False):
    return {"entry_price": 100., "exit_price": 200., "symbol": "AAA", "terminal": terminal,
            "entry_ts": pd.Timestamp("2026-01-01T00:15:00Z"),
            "exit_ts": pd.Timestamp("2026-02-01T00:15:00Z")}


def test_long_unit_funding_cash_and_cost_do_not_reinvest():
    source = events(["2026-01-02T08:00:00Z", "2026-01-20T08:00:00Z"], [.01, -.02])
    source["mark_center"] = [100., 300.]
    result = MOD.unit_forward_return(holding(), source)
    assert result["price_return"] == 1
    assert result["funding_return_estimate"] == pytest.approx(.05)
    assert result["funding_received_per_initial_notional"] == .06
    assert result["funding_paid_per_initial_notional"] == .01
    assert result["standalone_cost_total_return_estimate"] == pytest.approx(1.05 - .0042)
    assert result["receipts_at_mark_ge_2x_entry"] == .06


def test_terminal_exit_has_no_market_slippage_like_original_account():
    source = events(["2026-01-02T08:00:00Z"], [.01])
    result = MOD.unit_forward_return(holding(True), source)
    assert result["standalone_roundtrip_cost"] == pytest.approx(.0034)


@pytest.mark.parametrize("time", ["2026-01-01T00:15:00Z", "2026-02-01T00:15:00.001Z"])
def test_forward_cash_must_be_strictly_after_entry_and_no_later_than_exit(time):
    with pytest.raises(ValueError, match="bounds"):
        MOD.unit_forward_return(holding(), events([time], [-.01]))


def test_no_future_observations_cannot_be_zero_cash():
    with pytest.raises(ValueError, match="UNKNOWN"):
        MOD.unit_forward_return(holding(), events([], []))


def test_calendar_checks_exact_expected_inventory_not_observed_intervals():
    source = events(["2025-12-31T16:00:00Z"], [-.01])
    start, end = pd.Timestamp("2025-12-29T00:00:00Z"), pd.Timestamp("2025-12-31T23:59:59Z")
    segments = pd.DataFrame({"symbol": ["AAA"], "start": [start], "end": [end], "segment_id": ["a"]})
    expected = source.copy()
    expected["segment_id"] = "a"
    snapshot = SimpleNamespace(segments=segments, expected=expected)
    assert MOD.calendar_check(snapshot, "AAA", start, end, source)[0]
    snapshot.expected = expected.iloc[:0]
    assert not MOD.calendar_check(snapshot, "AAA", start, end, source)[0]


def sample_legs():
    rows = []
    for month in pd.date_range("2026-01-01", "2026-06-01", freq="MS", tz="UTC"):
        for sign in (["NEGATIVE"] if month.month == 3 else ["NEGATIVE", "POSITIVE"]):
            value = month.month / 10 if sign == "NEGATIVE" else 0.
            rows.append({"month": month, "pre72_sign": sign, "price_return": value,
                         "funding_return_estimate": value, "gross_total_return_estimate": value,
                         "standalone_cost_total_return_estimate": value})
    return pd.DataFrame(rows)


def test_paired_comparison_retains_unpaired_calendar_month_as_gap():
    paired = MOD.paired_months(sample_legs(), "pre72_sign")
    assert len(paired) == 6
    assert paired.loc[2, "month"].month == 3
    assert np.isnan(paired.loc[2, "price_return_negative_minus_nonnegative"])


def test_three_month_bootstrap_is_reproducible_and_has_valid_denominator():
    paired = MOD.paired_months(sample_legs(), "pre72_sign")
    a, b = MOD.paired_summary(paired), MOD.paired_summary(paired)
    assert a == b
    assert a["paired_months"] == 5
    assert a["calendar_months"] == 6
    assert a["price_return_negative_minus_nonnegative"]["mean"] == pytest.approx(.36)


def test_equal_month_and_equal_leg_averages_are_distinct():
    legs = sample_legs()
    result = MOD.group_metrics(legs)
    assert result["price_return_mean"] != result["price_return_equal_month_mean"]
