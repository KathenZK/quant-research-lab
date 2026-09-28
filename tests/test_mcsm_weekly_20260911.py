"""Literal timing and account tests for the precommitted weekly comparison."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
sys.path.insert(0, str(SCRIPTS))
import research_mcsm_weekly_20260911 as weekly  # noqa: E402


def daily_frame(symbol="X/USDT:USDT", days=70):
    return pd.DataFrame({"symbol": symbol, "ts": pd.date_range("2020-01-01", periods=days, tz="UTC"),
                         "eligible": True, "close": np.arange(days, dtype=float) + 100,
                         "quote_volume": 20_000_000., "research_segment_id": "x#1"})


def test_complete_31_day_window_and_cutoff():
    f = weekly.feature_table(daily_frame())
    assert not f.valid31.iloc[29]
    assert f.valid31.iloc[30]
    assert f.decision_ts.iloc[30] == pd.Timestamp("2020-02-01", tz="UTC")
    assert f.return_28.iloc[30] == pytest.approx(130 / 102 - 1)


def test_arrow_input_segment_boundaries_supported():
    original = daily_frame().convert_dtypes(dtype_backend="pyarrow")
    got = weekly.feature_table(original)
    assert got.valid31.iloc[30]


@pytest.mark.parametrize("fault", ["gap", "invalid", "segment"])
def test_feature_does_not_bridge_missing_or_identity(fault):
    f = daily_frame()
    if fault == "gap":
        f = f.drop(10)
    elif fault == "invalid":
        f.loc[10, "eligible"] = False
    else:
        f.loc[10:20, "research_segment_id"] = "x#2"
    got = weekly.feature_table(f)
    assert not got.loc[got.decision_ts.eq(pd.Timestamp("2020-02-01", tz="UTC")), "valid31"].iloc[0]


def test_weekly_initial_stub_and_monday_schedule():
    dates = weekly.decision_dates("W28")
    assert dates[0] == pd.Timestamp("2020-04-01", tz="UTC")
    assert dates[1] == pd.Timestamp("2020-04-06", tz="UTC")
    assert all(x.dayofweek == 0 for x in dates[1:])
    assert dates[-1] == pd.Timestamp("2026-06-29", tz="UTC")


def test_preentry_filter_uses_only_prior_activity_then_rank():
    ts = pd.Timestamp("2020-04-01", tz="UTC")
    ranked = pd.DataFrame({"strategy": "W28", "decision_ts": ts,
                           "symbol": [f"S{i}/USDT:USDT" for i in range(12)], "rank": range(1, 13)})
    endpoints = pd.DataFrame({"ts": ts, "symbol": ranked.symbol,
                              "eligible": [False] + [True] * 11, "research_window_valid": True,
                              "open": np.arange(12.) + 1})
    selected, _ = weekly.qualify_ranked(ranked, endpoints)
    endpoints["open"] *= 1000
    again, _ = weekly.qualify_ranked(ranked, endpoints)
    assert selected.symbol.tolist() == ranked.symbol.iloc[1:11].tolist()
    pd.testing.assert_frame_equal(selected, again)


def test_insufficient_active_does_not_form_smaller_basket():
    ts = pd.Timestamp("2020-04-01", tz="UTC")
    ranked = pd.DataFrame({"strategy": "W7", "decision_ts": ts,
                           "symbol": [f"S{i}/USDT:USDT" for i in range(10)], "rank": range(1, 11)})
    endpoints = pd.DataFrame({"ts": ts, "symbol": ranked.symbol,
                              "eligible": [False] + [True] * 9, "research_window_valid": True})
    with pytest.raises(ValueError, match="INSUFFICIENT_ACTIVE"):
        weekly.qualify_ranked(ranked, endpoints)


def test_monthly_pnl_is_marked_not_realized_trade_month():
    ts = pd.Timestamp("2020-04-01T00:15:00Z")
    end = pd.Timestamp("2020-06-01T00:15:00Z")
    h = pd.DataFrame({"symbol": ["X"], "entry_ts": [ts], "exit_ts": [end]})
    nav = pd.DataFrame({"ts": [pd.Timestamp("2020-05-01T00:00:00Z"), end], "equity": [120_000., 110_000.]})
    result = weekly.monthly_summary(nav, h, ts, end)
    assert result.pnl_usdt.tolist() == [20_000., -10_000.]
    assert result.held_symbols_during_month.tolist() == ["X", "X"]


def test_known_terminal_clips_holding_without_refill():
    entry = pd.Timestamp("2025-03-01T00:15:00Z")
    terminal = pd.Timestamp("2025-03-17T09:00:00Z")
    h = pd.DataFrame({"symbol": ["BNX/USDT:USDT"], "entry_ts": [entry],
                      "scheduled_exit_ts": [pd.Timestamp("2025-04-01T00:15:00Z")]})
    got = weekly.apply_known_terminals(h, [{"symbol": "BNX/USDT:USDT", "ts": terminal}])
    assert got.exit_ts.iloc[0] == terminal
    assert got.terminal.iloc[0]


def test_price_adapter_constant_market_charges_actual_net_turnover():
    start = pd.Timestamp("2020-04-01T00:15:00Z")
    end = pd.Timestamp("2020-05-01T00:15:00Z")
    rebal = pd.Timestamp("2020-04-06T00:15:00Z")
    h = pd.DataFrame({"symbol": ["X", "X"], "entry_ts": [start, rebal],
                      "exit_ts": [rebal, end], "weight": [1., 1.]})
    daily = pd.DataFrame({"symbol": "X", "ts": pd.date_range("2020-04-01", "2020-04-30", tz="UTC"),
                          "eligible": True, "close": 100.})
    quotes = pd.DataFrame([{"symbol": "X", "ts": ts + pd.Timedelta(minutes=d), "open": 100.,
                            "eligible": True, "research_window_valid": True}
                           for ts in [start, rebal, end] for d in (0, -15)])
    result = weekly.replay_price(h, quotes, daily, [], [start, rebal, end], .0004, start, end)
    expected = 100_000 / 1.0014 * .9986
    assert result["metrics"]["final_equity"] == pytest.approx(expected)
    mid = result["trades"].loc[result["trades"].ts.eq(rebal)]
    assert mid.traded_notional.sum() == pytest.approx(0.)


def test_missing_exit_is_failure_not_zero_or_skipped_period():
    start = pd.Timestamp("2020-04-01T00:15:00Z")
    end = pd.Timestamp("2020-05-01T00:15:00Z")
    h = pd.DataFrame({"symbol": ["X"], "entry_ts": [start], "exit_ts": [end], "weight": [1.]})
    daily = pd.DataFrame({"symbol": "X", "ts": pd.date_range("2020-04-01", "2020-04-30", tz="UTC"),
                          "eligible": True, "close": 100.})
    quotes = pd.DataFrame([{"symbol": "X", "ts": start + pd.Timedelta(minutes=d), "open": 100.,
                            "eligible": True, "research_window_valid": True} for d in (0, -15)])
    with pytest.raises(ValueError, match="EXECUTION_OPEN_MISSING"):
        weekly.replay_price(h, quotes, daily, [], [start, end], .0004, start, end)


def test_missing_nomination_week_cannot_be_labelled_complete():
    rows = []
    for strategy in ("B0", "M28", "W28", "W7"):
        dates = weekly.decision_dates("M28" if strategy == "B0" else strategy)
        if strategy == "W7":
            dates = dates[1:]
        rows += [{"strategy": strategy, "entry_ts": d + weekly.MIN15, "symbol": f"S{i}", "weight": .1}
                 for d in dates for i in range(10)]
    with pytest.raises(ValueError, match="^INCOMPLETE_DECISION_SCHEDULE W7"):
        weekly.validate_nominations(pd.DataFrame(rows))


def test_native_coverage_uses_rechecked_source_not_stale_legacy_column():
    native = pd.DataFrame({"event_id": ["old", "new", "proxy"], "native_mark": [2., np.nan, np.nan],
                           "mark_source": ["RECHECKED_OFFICIAL_NATIVE_SETTLEMENT_MARK",
                                           "RECHECKED_OFFICIAL_NATIVE_SETTLEMENT_MARK", "VISION_MARK_1M_MONTH"],
                           "mark_center": [2., 3., 4.]})
    events = pd.DataFrame({"event_id": ["old", "new", "proxy", "snapshot", "missing"],
                           "mark_price": [np.nan, np.nan, np.nan, 5., np.nan]})
    flags, count = weekly.funding_availability_flags(events, native)
    assert count == 2
    assert flags.native_settlement_mark_available.tolist() == [True, True, False, True, False]
    assert flags.old_monthly_estimate_available.tolist() == [True, True, True, False, False]
