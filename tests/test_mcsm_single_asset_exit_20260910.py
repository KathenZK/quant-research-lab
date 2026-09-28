"""Causal timing, missing-feature handling, and nonredistributing exit checks."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

DIRECTORY = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
sys.path.insert(0, str(DIRECTORY))
SPEC = importlib.util.spec_from_file_location("mcsm_single_exit_0910", DIRECTORY / "research_mcsm_single_asset_exit_20260910.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def fixture_frames():
    month = pd.Timestamp("2020-03-01", tz="UTC")
    dates = pd.date_range(month - pd.Timedelta(days=30), month + pd.Timedelta(days=15), tz="UTC")
    frames = []
    for index in range(10):
        close = np.full(len(dates), 100.)
        if index == 0:
            close[dates >= month] = np.linspace(90, 50, (dates >= month).sum())
        frames.append(pd.DataFrame({"symbol": f"S{index}", "ts": dates, "close": close,
                                    "eligible": True, "research_segment_id": 1}))
    holdings = pd.DataFrame({"month": month, "symbol": [f"S{i}" for i in range(10)],
                             "entry_ts": month + pd.Timedelta(minutes=15),
                             "exit_ts": month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15), "weight": .1})
    return holdings, pd.concat(frames, ignore_index=True)


def test_previous_20_low_excludes_current_close():
    holdings, daily = fixture_frames()
    feature = MOD.daily_features(daily, set(holdings.symbol))
    row = feature.loc[("S0", pd.Timestamp("2020-03-01", tz="UTC"))]
    assert row.previous_20_low == 100.
    assert row.close == 90.


def test_arrow_backed_returned_frame_uses_same_features():
    holdings, daily = fixture_frames()
    ordinary = MOD.daily_features(daily, set(holdings.symbol))
    arrow = MOD.daily_features(daily.convert_dtypes(dtype_backend="pyarrow"), set(holdings.symbol))
    assert np.allclose(ordinary.previous_20_low.astype(float), arrow.previous_20_low.astype(float), equal_nan=True)


def test_exit_after_two_closed_held_days_next_0015():
    holdings, daily = fixture_frames()
    signals, exits = MOD.make_exit_signals(holdings, MOD.daily_features(daily, set(holdings.symbol)))
    assert len(exits) == 1
    assert exits.iloc[0].exit_ts == pd.Timestamp("2020-03-03T00:15:00Z")
    assert exits.iloc[0].decision_ts == pd.Timestamp("2020-03-03T00:00:00Z")
    assert signals.loc[signals.triggered, "confirmation_days"].tolist() == [2]


def test_unknown_peer_resets_two_day_confirmation():
    holdings, daily = fixture_frames()
    feature = MOD.daily_features(daily, set(holdings.symbol))
    feature.loc[("S9", pd.Timestamp("2020-03-02", tz="UTC")), "return_7d"] = np.nan
    signals, exits = MOD.make_exit_signals(holdings, feature)
    assert exits.iloc[0].exit_ts == pd.Timestamp("2020-03-05T00:15:00Z")
    unknown = signals.loc[signals.symbol.eq("S0") & signals.day.eq(pd.Timestamp("2020-03-02", tz="UTC"))].iloc[0]
    assert unknown.feature_status == "UNKNOWN_RESET_CONFIRMATION"
    assert unknown.confirmation_days == 0


@pytest.mark.parametrize("failure", ["missing", "ineligible", "segment"])
def test_no_feature_across_daily_gap_or_boundary(failure):
    holdings, daily = fixture_frames()
    mask = daily.symbol.eq("S0") & daily.ts.eq(pd.Timestamp("2020-02-25", tz="UTC"))
    if failure == "missing":
        daily = daily.loc[~mask]
    elif failure == "ineligible":
        daily.loc[mask, "eligible"] = False
    else:
        daily.loc[daily.symbol.eq("S0") & daily.ts.ge(pd.Timestamp("2020-02-25", tz="UTC")), "research_segment_id"] = 2
    feature = MOD.daily_features(daily, set(holdings.symbol))
    row = feature.loc[("S0", pd.Timestamp("2020-03-01", tz="UTC"))]
    assert not row.valid_21
    assert np.isnan(row.previous_20_low)


def test_ordinary_exit_has_cost_and_leaves_other_quantity_unchanged():
    account = MOD.LinearPerpAccount(100000)
    ts = pd.Timestamp("2020-03-01T00:15Z")
    account.rebalance(ts, {"A": .5, "B": .5}, {"A": 100., "B": 200.})
    before = account.positions["B"].quantity
    row = MOD.voluntary_close(account, ts + MOD.DAY, "A", 90., "test verified execution")
    assert "A" not in account.positions
    assert account.positions["B"].quantity == before
    assert row["details"]["fee"] == pytest.approx(row["details"]["traded_notional"] * .001)
    assert row["details"]["slippage"] == pytest.approx(row["details"]["traded_notional"] * .0004)


def test_funding_at_exit_included_after_exit_excluded():
    holdings, _ = fixture_frames()
    exit_ts = pd.Timestamp("2020-03-03T00:15Z")
    exits = pd.DataFrame({"month": [holdings.month.iloc[0]], "symbol": ["S0"], "exit_ts": [exit_ts]})
    funding = pd.DataFrame({"symbol": "S0", "ts": [exit_ts, exit_ts + pd.Timedelta(milliseconds=1)], "rate_type": "Regular"})
    booked, excluded = MOD.clip_funding(holdings, funding, exits)
    assert len(booked) == len(excluded) == 1
    assert booked.ts.iloc[0] == exit_ts


def test_unassigned_funding_is_error_not_silent_zero():
    holdings, _ = fixture_frames()
    funding = pd.DataFrame({"symbol": ["NOT_HELD"], "ts": [pd.Timestamp("2020-03-02", tz="UTC")], "rate_type": ["Regular"]})
    with pytest.raises(ValueError, match="exactly once"):
        MOD.clip_funding(holdings, funding, pd.DataFrame())


def test_execution_uses_only_prior_activity_not_current_bar_future_volume(tmp_path, monkeypatch):
    timestamp = pd.Timestamp("2020-03-03T00:15Z")
    request = {"symbols": ["S0"]}
    plan = {"label": "sample", "request": request,
            "required": [{"symbol": "S0", "exit_ts": timestamp, "ordinary_exit_required": True}]}
    MOD.save(tmp_path / "execution-requests/sample.json", request)
    frame = pd.DataFrame({"ts": [timestamp - pd.Timedelta(minutes=15), timestamp],
                           "eligible": [True, False], "research_window_valid": [True, False],
                           "open": [100., 90.]})
    fake = SimpleNamespace(prices={"S0": frame}, report={"status": "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"})
    monkeypatch.setattr(MOD, "ROOT", tmp_path)
    monkeypatch.setattr(MOD, "require_research_startup", lambda *args, **kwargs: fake)
    prices, _ = MOD.load_exit_execution([plan], tmp_path)
    assert prices.price.tolist() == [90.]
    assert prices.current_bar_future_activity_not_used.tolist() == [True]


def test_execution_rejects_missing_prior_active_bar(tmp_path, monkeypatch):
    timestamp = pd.Timestamp("2020-03-03T00:15Z")
    request = {"symbols": ["S0"]}
    plan = {"label": "sample", "request": request,
            "required": [{"symbol": "S0", "exit_ts": timestamp, "ordinary_exit_required": True}]}
    MOD.save(tmp_path / "execution-requests/sample.json", request)
    frame = pd.DataFrame({"ts": [timestamp], "eligible": [True], "research_window_valid": [True], "open": [90.]})
    fake = SimpleNamespace(prices={"S0": frame}, report={"status": "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"})
    monkeypatch.setattr(MOD, "ROOT", tmp_path)
    monkeypatch.setattr(MOD, "require_research_startup", lambda *args, **kwargs: fake)
    with pytest.raises(ValueError, match="prior closed active"):
        MOD.load_exit_execution([plan], tmp_path)


def test_future_prices_cannot_change_past_exit_plan():
    holdings, daily = fixture_frames()
    _, first = MOD.make_exit_signals(holdings, MOD.daily_features(daily, set(holdings.symbol)))
    daily.loc[daily.ts.gt(pd.Timestamp("2020-03-02", tz="UTC")), "close"] = 100000.
    _, second = MOD.make_exit_signals(holdings, MOD.daily_features(daily, set(holdings.symbol)))
    pd.testing.assert_frame_equal(first, second)


def test_all_nine_peers_required_no_changing_denominator():
    holdings, daily = fixture_frames()
    daily = daily.loc[~daily.symbol.eq("S9")]
    signals, exits = MOD.make_exit_signals(holdings, MOD.daily_features(daily, set(holdings.symbol)))
    assert exits.empty
    assert signals.loc[signals.symbol.eq("S0"), "peer_valid_count"].max() == 8


def test_signal_confirmation_cannot_use_pre_entry_day():
    holdings, daily = fixture_frames()
    daily.loc[daily.symbol.eq("S0") & daily.ts.eq(pd.Timestamp("2020-02-29", tz="UTC")), "close"] = 95.
    _, exits = MOD.make_exit_signals(holdings, MOD.daily_features(daily, set(holdings.symbol)))
    assert exits.exit_ts.min() == pd.Timestamp("2020-03-03T00:15Z")


def test_month_end_rule_is_not_replaced_with_double_exit():
    holdings, daily = fixture_frames()
    base = daily.loc[daily.ts.lt(pd.Timestamp("2020-03-01", tz="UTC"))].copy()
    future = []
    for symbol in holdings.symbol:
        dates = pd.date_range("2020-03-01", "2020-03-31", tz="UTC")
        close = np.full(len(dates), 100.)
        if symbol == "S0":
            close[-2:] = [90., 80.]
        future.append(pd.DataFrame({"symbol": symbol, "ts": dates, "close": close, "eligible": True, "research_segment_id": 1}))
    daily = pd.concat([base, *future], ignore_index=True)
    _, exits = MOD.make_exit_signals(holdings, MOD.daily_features(daily, set(holdings.symbol)))
    assert exits.empty


def synthetic_full_account():
    months = pd.date_range("2020-03-01", "2026-06-01", freq="MS", tz="UTC")
    names = [f"S{i}" for i in range(10)]
    holdings = pd.DataFrame([{"month": month, "symbol": symbol, "entry_ts": month + pd.Timedelta(minutes=15),
                              "exit_ts": month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15), "weight": .1}
                             for month in months for symbol in names])
    executions = pd.DataFrame([{"ts": ts, "symbol": symbol, "price": 100.}
                              for ts in pd.date_range(MOD.START, MOD.END, freq="MS", tz="UTC") for symbol in names])
    daily = pd.DataFrame([{"ts": ts, "symbol": symbol, "close": 100., "eligible": True}
                           for ts in pd.date_range("2020-03-01", "2026-06-30", tz="UTC") for symbol in names])
    funding = pd.DataFrame({"symbol": pd.Series([], dtype="str"), "ts": pd.Series([], dtype="datetime64[ns, UTC]"),
                           "rate_type": pd.Series([], dtype="str")})
    exits = pd.DataFrame(columns=["month", "symbol", "exit_ts", "original_exit_ts"])
    prices = pd.DataFrame({"symbol": pd.Series([], dtype="str"), "ts": pd.Series([], dtype="datetime64[ns, UTC]"), "price": []})
    return holdings, executions, daily, funding, exits, prices


def test_disabled_adapter_reproduces_original_account_engine():
    from run_mcsm_baseline_estimate_20260909 import run_scenario
    holdings, executions, daily, funding, exits, prices = synthetic_full_account()
    original = run_scenario(holdings, executions, daily, funding, [], "price_only")
    new = MOD.replay_exit(holdings, executions, daily, funding, [], exits, prices, "price_only")
    for key in ("final_equity", "price_pnl_usdt", "fees_usdt", "slippage_usdt", "max_drawdown_daily_and_rebalance"):
        assert original["metrics"][key] == pytest.approx(new["metrics"][key], abs=1e-8)


def test_extra_common_marks_do_not_create_price_pnl():
    holdings, executions, daily, funding, exits, prices = synthetic_full_account()
    original = MOD.replay_exit(holdings, executions, daily, funding, [], exits, prices, "price_only")
    prices = pd.DataFrame({"symbol": [f"S{i}" for i in range(10)], "ts": pd.Timestamp("2020-03-03T00:15Z"), "price": 50.})
    marked = MOD.replay_exit(holdings, executions, daily, funding, [], exits, prices, "price_only")
    assert marked["metrics"]["final_equity"] == pytest.approx(original["metrics"]["final_equity"], abs=1e-8)
    assert marked["metrics"]["price_pnl_usdt"] == pytest.approx(0.)
    assert marked["metrics"]["max_drawdown_daily_and_rebalance"] < original["metrics"]["max_drawdown_daily_and_rebalance"]
