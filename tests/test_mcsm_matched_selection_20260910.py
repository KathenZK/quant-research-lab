"""Synthetic tests; no historical future returns are inspected here."""
import importlib.util
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PATH = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/research_mcsm_matched_selection_20260910.py"
SPEC = importlib.util.spec_from_file_location("mcsm_matched", PATH)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def daily():
    n = 70
    return pd.DataFrame({
        "symbol": "AAA", "ts": pd.date_range("2020-01-01", periods=n, tz="UTC"),
        "close": 100 * np.cumprod(1 + np.sin(np.arange(n)) / 100),
        "research_segment_id": 1, "research_window_valid": True,
    })


def test_volatility_needs_31_valid_prices():
    x = daily()
    out = M.prior_volatility(x)
    assert out.vol30.iloc[:30].isna().all()
    assert np.isclose(out.vol30.iloc[30], x.close.pct_change().iloc[1:31].std(ddof=1))


def test_volatility_does_not_cross_segment():
    x = daily()
    x.loc[35:, "research_segment_id"] = 2
    out = M.prior_volatility(x)
    assert out.vol30.iloc[35:65].isna().all()
    assert np.isfinite(out.vol30.iloc[65])


def test_invalid_day_and_gap_not_joined():
    x = daily()
    x.loc[33, "research_window_valid"] = False
    out = M.prior_volatility(x)
    assert out.vol30.iloc[33:64].isna().all()
    y = daily().drop(index=33)
    out = M.prior_volatility(y)
    assert out.vol30.loc[34:63].isna().all()


def test_feature_is_future_blind():
    x = daily()
    out = M.prior_volatility(x)
    x.loc[40:, "close"] *= 1000
    changed = M.prior_volatility(x)
    pd.testing.assert_frame_equal(out.iloc[:40], changed.iloc[:40])


def pool():
    return pd.DataFrame({"symbol": ["A", "B", "C", "D", "E"],
                         "adv30": [10., 20., 11., 19., 100.],
                         "vol30": [.1, .2, .11, .19, 1.]})


def test_matching_unique_and_future_columns_ignored():
    p = pool()
    out = M.optimal_pairs(p, ["A", "B"])
    assert out.control_symbol.iloc[0] == "C"
    assert out.control_symbol.iloc[1] in ("D", "E")  # Equal percentile distance.
    assert out.control_symbol.nunique() == 2
    p["future_return"] = [1000, -1, -1, 1000, 9000]
    pd.testing.assert_frame_equal(out, M.optimal_pairs(p, ["A", "B"]))


def test_matching_order_independent():
    a = M.optimal_pairs(pool(), ["A", "B"])
    b = M.optimal_pairs(pool().iloc[::-1], ["B", "A"])
    pd.testing.assert_frame_equal(a, b)


def test_missing_input_and_too_few_controls_rejected():
    p = pool()
    p.loc[0, "vol30"] = np.nan
    with pytest.raises(ValueError, match="Missing"):
        M.optimal_pairs(p, ["A", "B"])
    with pytest.raises(ValueError, match="Insufficient"):
        M.optimal_pairs(pool().iloc[:3], ["A", "B"])


def test_duplicate_symbol_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        M.optimal_pairs(pd.concat([pool(), pool().iloc[:1]]), ["A"])


def test_asset_class_cannot_cross_and_whole_pool_zscore():
    p = pool()
    p["asset_class"] = ["STOCK", "COIN", "COIN", "COIN", "STOCK"]
    out = M.optimal_pairs(p, ["A", "B"])
    assert out.loc[out.top_symbol.eq("A"), "control_symbol"].iloc[0] == "E"
    expected = (np.log(p.adv30.iloc[0]) - np.log(p.adv30).mean()) / np.log(p.adv30).std(ddof=0)
    assert np.isclose(out.loc[out.top_symbol.eq("A"), "top_adv30_z"].iloc[0], expected)


def test_lexicographic_tie_is_symbol_order():
    rows, cols = M.lexicographic_assignment(np.ones((3, 5)))
    assert rows.tolist() == [0, 1, 2]
    assert cols.tolist() == [0, 1, 2]


def test_assignment_matches_exhaustive_small_problem():
    matrix = np.array([[3., 1., 2., 8.], [1., 6., 4., 2.], [4., 3., 2., 1.]])
    rows, cols = M.lexicographic_assignment(matrix)
    exhaustive = min((sum(matrix[i, j] for i, j in enumerate(p)), p)
                     for p in itertools.permutations(range(4), 3))
    assert float(matrix[rows, cols].sum()) == exhaustive[0]
    assert tuple(cols) == exhaustive[1]


def test_cost_postcost_sizing():
    cost = .0014
    q = 1 / (1 + cost) / 100
    independent_final = 1 - q * 100 * cost + q * (200 - 100) - q * 200 * cost
    assert np.isclose(M.net_roundtrip_return(100, 200), independent_final - 1)


def test_label_does_not_use_future_execution_bar_activity():
    month = pd.Timestamp("2020-01-01", tz="UTC")
    times = [month, month + pd.Timedelta(minutes=15), month + pd.offsets.MonthBegin(1),
             month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15)]
    endpoints = pd.DataFrame({"symbol": "A", "ts": times, "open": [1, 1, 2, 2],
                              "research_window_valid": [True, False, True, False]}).set_index(["symbol", "ts"])
    assert M.leg_label("A", month, endpoints, [])["status"] == "LABEL_AVAILABLE"
    endpoints.loc[("A", month), "research_window_valid"] = False
    assert M.leg_label("A", month, endpoints, [])["status"] == "LABEL_UNAVAILABLE"


def test_bootstrap_keeps_calendar_missing_and_reproducible():
    values = np.array([.1, np.nan, -.1, .2, np.nan, .4])
    a, b = M.bootstrap_calendar(values), M.bootstrap_calendar(values)
    assert a == b
    assert a["retained_missing_calendar_slots"]
