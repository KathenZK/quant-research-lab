"""Synthetic causality, missing-price and cash-timing checks."""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("drawdown0911", SCRIPTS / "research_mcsm_drawdown_20260911.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def frame(symbol, returns):
    n = len(returns)
    return pd.DataFrame({"ts": pd.date_range("2021-01-01", periods=n, tz="UTC"), "symbol": symbol,
                         "close": 100 * np.cumprod(1 + np.array(returns)), "eligible": True,
                         "research_segment_id": "first", "quote_volume": 2e7})


def test_beta_has_no_current_day_label():
    x = np.sin(np.arange(100)) * .01
    a, b, c = frame("BTC/USDT:USDT", x), frame("ETH/USDT:USDT", x), frame("C/USDT:USDT", 2*x)
    data = pd.concat([a, b, c])
    _, base, _ = mod.market_features(data, {s: "COIN" for s in data.symbol.unique()})
    modified = data.copy()
    cutoff = pd.Timestamp("2021-03-12", tz="UTC")
    modified.loc[modified.symbol.eq("C/USDT:USDT") & modified.ts.ge(cutoff), "close"] *= 5
    _, changed, _ = mod.market_features(modified, {s: "COIN" for s in data.symbol.unique()})
    before = base.loc[base.symbol.eq("C/USDT:USDT") & base.ts.le(cutoff), "beta_asof_previous_closed_day"].to_numpy()
    after = changed.loc[changed.symbol.eq("C/USDT:USDT") & changed.ts.le(cutoff), "beta_asof_previous_closed_day"].to_numpy()
    np.testing.assert_allclose(before, after, equal_nan=True)
    assert base.loc[base.symbol.eq("C/USDT:USDT") & base.ts.eq(cutoff), "beta_asof_previous_closed_day"].iloc[0] == pytest.approx(2.)


def test_broad_missing_label_invalidates_whole_day_not_membership():
    x = np.sin(np.arange(70)) * .01
    data = pd.concat([frame(s, x) for s in ["BTC/USDT:USDT", "ETH/USDT:USDT", "C/USDT:USDT", "D/USDT:USDT", "E/USDT:USDT"]])
    date = pd.Timestamp("2021-02-20", tz="UTC")
    data.loc[data.symbol.eq("C/USDT:USDT") & data.ts.eq(date), "eligible"] = False
    market, _, pool = mod.market_features(data, {s: "COIN" for s in data.symbol.unique()})
    assert market.loc[date, "pool_count"] == 5
    assert market.loc[date, "valid_count"] == 4
    assert np.isnan(market.loc[date, "broad_return"])
    assert pool.loc[pool.symbol.eq("C/USDT:USDT") & pool.ts.eq(date), "prior_pool_eligible"].iloc[0]


def test_beta_resets_at_segment_boundary():
    x = np.sin(np.arange(100)) * .01
    data = pd.concat([frame(s, x) for s in ["BTC/USDT:USDT", "ETH/USDT:USDT", "C/USDT:USDT"]])
    cutoff = pd.Timestamp("2021-03-01", tz="UTC")
    data.loc[data.symbol.eq("C/USDT:USDT") & data.ts.ge(cutoff), "research_segment_id"] = "second"
    _, features, _ = mod.market_features(data, {s: "COIN" for s in data.symbol.unique()})
    assert features.loc[features.symbol.eq("C/USDT:USDT") & features.ts.ge(cutoff), "beta_asof_previous_closed_day"].isna().all()


def test_absent_entire_bar_does_not_remove_prior_selected_coin():
    x = np.sin(np.arange(70)) * .01
    names = ["BTC/USDT:USDT", "ETH/USDT:USDT", "C/USDT:USDT", "D/USDT:USDT", "E/USDT:USDT"]
    data = pd.concat([frame(s, x) for s in names])
    date = pd.Timestamp("2021-02-20", tz="UTC")
    data = data.loc[~(data.symbol.eq("C/USDT:USDT") & data.ts.eq(date))]
    market, _, pool = mod.market_features(data, {s: "COIN" for s in names})
    assert market.loc[date, "pool_count"] == 5
    assert market.loc[date, "valid_count"] == 4
    assert np.isnan(market.loc[date, "broad_return"])
    selected_missing = pool.loc[pool.symbol.eq("C/USDT:USDT") & pool.ts.eq(date)]
    assert len(selected_missing) == 1 and selected_missing.prior_pool_eligible.iloc[0]


def test_arrow_backed_input_supported_without_changing_values():
    x = np.sin(np.arange(70)) * .01
    data = pd.concat([frame(s, x) for s in ["BTC/USDT:USDT", "ETH/USDT:USDT", "C/USDT:USDT"]])
    classes = {s: "COIN" for s in data.symbol.unique()}
    expected, _, _ = mod.market_features(data, classes)
    actual, _, _ = mod.market_features(data.convert_dtypes(dtype_backend="pyarrow"), classes)
    np.testing.assert_allclose(expected.market_factor.to_numpy(float), actual.market_factor.to_numpy(float), equal_nan=True)


def test_month_cost_assigns_next_month_new_token_separately():
    march = pd.Timestamp("2021-03-01T00:00Z")
    april = pd.Timestamp("2021-04-01T00:00Z")
    legs = pd.DataFrame({"month": [march], "symbol": ["A"], "price_pnl": [100.], "funding_pnl": [5.],
                         "direct_exit_fees": [1.], "direct_exit_slippage": [.4], "early_exit": [True],
                         "net_before_separate_month_boundary_costs": [103.6]})
    trades = pd.DataFrame({"ts": [march+mod.MIN15, april+mod.MIN15], "symbol": ["A", "B"],
                           "old_quantity": [0., 0.], "new_quantity": [1., 1.], "fee": [2., 3.], "slippage": [.8, 1.2]})
    end = 100000 + 100 + 5 - 1 - .4 - 2 - 3 - .8 - 1.2
    monthly = pd.DataFrame({"month": [march], "account_start_equity": [100000.], "account_end_equity": [end], "account_return": [end/100000 - 1]})
    result, costs = mod.monthly_details(legs, trades, monthly)
    assert result.reconciliation_error.abs().max() < 1e-8
    assert not costs.loc[costs.symbol.eq("B"), "held_in_attributed_month"].iloc[0]
    assert costs.attributed_month.eq(march).all()


def test_daily_attribution_excludes_partial_entry_exit_days():
    legs = pd.DataFrame({"month": [pd.Timestamp("2021-03-01T00:00Z")], "symbol": ["A"],
                         "entry_ts": [pd.Timestamp("2021-03-01T00:15Z")],
                         "actual_exit_ts": [pd.Timestamp("2021-03-05T00:15Z")], "initial_quantity": [1.]})
    dates = pd.date_range("2021-03-01", "2021-03-06", tz="UTC")
    features = pd.DataFrame({"symbol": "A", "ts": dates, "daily_return": .1, "previous_close": 100.,
                             "beta_asof_previous_closed_day": 2., "market_factor": .03, "beta_prior_observations": 50})
    actual = mod.daily_attribution(legs, features)
    assert actual.start_ts.min() == pd.Timestamp("2021-03-02T00:00Z")
    assert actual.end_ts.max() == pd.Timestamp("2021-03-05T00:00Z")
    assert len(actual) == 3
    assert actual.market_related_price_pnl.eq(6.).all()


def test_market_window_does_not_splice_missing_day():
    dates = pd.date_range("2021-03-01", periods=4, tz="UTC")
    market = pd.DataFrame({"btc_return": .1, "eth_return": .1, "market_factor": .1,
                           "broad_return": [.1, np.nan, .1, .1], "pool_count": 10}, index=dates)
    result = mod.market_window(market, dates[0], dates[-1] + mod.DAY)
    assert result["btc_return"] == pytest.approx(1.1**4-1)
    assert result["broad_return"] is None
    assert result["broad_return_valid_days"] == 3


def test_drawdown_keeps_same_time_post_cost_trough():
    nav = pd.DataFrame({"ts": pd.to_datetime(["2021-01-01", "2021-01-02", "2021-01-02", "2021-01-03"], utc=True),
                        "event_id": [1, 2, 3, 4], "equity": [200000., 100000., 99000., 201000.]})
    _, result = mod.drawdown_episode(nav)
    assert result["trough_index"] == 2
    assert result["max_drawdown"] == pytest.approx(-.505)
    assert result["recovered_by_end"]
