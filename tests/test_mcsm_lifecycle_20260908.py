"""Synthetic-only independent audit of the Sep08 Top10 lifecycle diagnostic.

No market files, historical outcomes, or research startup calls are loaded here.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
    / "research_binance_1d_mcsm_lifecycle_20260908.py"
)
SPEC = importlib.util.spec_from_file_location("mcsm_lifecycle_20260908_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
LIFE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LIFE
SPEC.loader.exec_module(LIFE)


def panels(month="2020-08-01", count=12):
    """Distinct formation ranks, then flat independent fixed-quantity baskets."""
    month = pd.Timestamp(month, tz="UTC")
    signal_end = month - pd.Timedelta(days=1)
    start = month - pd.DateOffset(months=1) - pd.Timedelta(days=1)
    end = month + pd.offsets.MonthBegin(1) + pd.Timedelta(days=1)
    dates = pd.date_range(start, end, freq="D")
    symbols = [f"C{i:02d}/USDT:USDT" for i in range(count)]
    day = np.minimum((dates - start).days, (signal_end - start).days)
    values = np.exp(np.outer(day, np.arange(1, count + 1) / 1000.0)) * 100.0
    price = pd.DataFrame(values, index=dates, columns=symbols)
    segments = pd.DataFrame({s: f"{s}#1" for s in symbols}, index=dates)
    result = {
        "open": price.copy(), "close": price.copy(),
        "adv30": pd.DataFrame(20_000_000.0, index=dates, columns=symbols),
        "research_segment_id": segments,
    }
    for frame in result.values():
        frame.columns.name = "symbol"
    return result


def one_month(monkeypatch, month="2020-08-01"):
    month = pd.Timestamp(month, tz="UTC")
    monkeypatch.setattr(LIFE, "START", month)
    monkeypatch.setattr(LIFE, "LAST", month)
    return month


def test_natural_state_boundaries_and_missingness():
    assert LIFE.state_name(0.5, 0.0) == "market_weak__leader_weak"
    assert LIFE.state_name(0.500001, 0.0) == "market_strong__leader_weak"
    assert LIFE.state_name(0.5, 0.000001) == "market_weak__leader_strong"
    assert LIFE.state_name(np.nan, 0.0) == "unavailable"
    assert LIFE.state_name(1.0, np.nan) == "unavailable"


def test_fixed_units_and_exit_notional_cost():
    p = panels(count=2)
    names = p["open"].columns.tolist()
    entry = pd.Timestamp("2020-08-02", tz="UTC")
    end = pd.Timestamp("2020-08-04", tz="UTC")
    for key in ("open", "close"):
        p[key].loc[entry:end, names] = [[10.0, 10.0], [20.0, 5.0], [40.0, 2.5]]
    basket = LIFE.basket_paths(p, names, pd.Timestamp("2020-07-31", tz="UTC"), entry, end)
    np.testing.assert_allclose(basket["q"].to_numpy(), [0.05, 0.05])
    np.testing.assert_allclose(basket["open"].loc[entry:end], [1.0, 1.25, 2.125])
    assert LIFE.path_return(basket["open"], entry, end) == pytest.approx(1.125)
    assert LIFE.after_cost(2.125) == pytest.approx(1.125 - LIFE.COST * 3.125)
    # Daily target-weight compounding would return 0.5625, not 1.125.
    assert not np.isclose(1.125, 1.25 * 1.25 - 1.0)


def test_path_rejects_internal_gap_even_with_valid_endpoints():
    dates = pd.date_range("2020-08-01", periods=4, tz="UTC")
    path = pd.Series([1.0, np.nan, 1.2, 1.3], index=dates)
    assert np.isnan(LIFE.path_return(path, dates[0], dates[-1]))
    assert np.isnan(LIFE.path_return(path.drop(dates[1]), dates[0], dates[-1]))
    assert np.isnan(LIFE.path_return(pd.Series([1, 0, 2, 3], index=dates), dates[0], dates[-1]))


def test_segment_break_does_not_reconnect_prices_after_reappearance():
    p = panels(count=2)
    names = p["open"].columns.tolist()
    signal_end = pd.Timestamp("2020-07-31", tz="UTC")
    entry = pd.Timestamp("2020-08-02", tz="UTC")
    gap = pd.Timestamp("2020-08-12", tz="UTC")
    end = pd.Timestamp("2020-09-02", tz="UTC")
    p["research_segment_id"].loc[gap:, names[0]] = f"{names[0]}#2"
    basket = LIFE.basket_paths(p, names, signal_end, entry, end)
    assert basket["q"] is not None
    assert basket["open"].loc[:gap - pd.Timedelta(days=1)].notna().all()
    assert basket["open"].loc[gap:].isna().all()
    assert np.isnan(LIFE.path_return(basket["open"], entry, end))


def test_no_future_survivor_reselection_of_top_or_market(monkeypatch):
    month = one_month(monkeypatch)
    p = panels()
    original_pool = LIFE.select_month(p, month)
    non_top = original_pool.symbol.iloc[-1]
    gap = pd.Timestamp("2020-08-12", tz="UTC")
    p["research_segment_id"].loc[gap:, non_top] = f"{non_top}#2"
    new_pool = LIFE.select_month(p, month)
    pd.testing.assert_frame_equal(new_pool, original_pool)
    monthly, daily, _, holdings, blockers = LIFE.calculate(p)
    assert monthly.iloc[0].market_count == 12
    assert monthly.iloc[0].baseline_valid
    assert not monthly.iloc[0].market_baseline_valid
    assert np.isnan(monthly.iloc[0].market_gross)
    assert non_top in holdings.symbol.tolist()
    assert (blockers.role == "market").any()
    after_gap = daily.loc[daily.decision.gt(gap)]
    assert not after_gap.empty
    assert after_gap.state.eq("unavailable").all()


def test_missing_top_entry_never_promotes_rank_eleven(monkeypatch):
    month = one_month(monkeypatch)
    p = panels()
    pool = LIFE.select_month(p, month)
    selected = pool.symbol.iloc[:10].tolist()
    entry = month + pd.Timedelta(days=1)
    p["open"].loc[entry, selected[0]] = np.nan
    monthly, _, _, holdings, _ = LIFE.calculate(p)
    row = monthly.iloc[0]
    assert row.symbols.split("|") == selected
    assert not row.top_entry_valid
    assert not row.baseline_valid
    assert not holdings.loc[holdings.symbol.eq(pool.symbol.iloc[10]), "is_top10"].any()


def test_first_trigger_is_once_and_execution_is_next_day(monkeypatch):
    month = one_month(monkeypatch)
    monthly, daily, landmarks, _, _ = LIFE.calculate(panels())
    row = monthly.iloc[0]
    entry = month + pd.Timedelta(days=1)
    assert row.first_trigger == entry + pd.Timedelta(days=7)
    assert row.trigger_exit == entry + pd.Timedelta(days=8)
    assert row.trigger_exit == row.first_trigger + pd.Timedelta(days=1)
    assert row.trigger_prior_peak == pytest.approx(0.0)
    assert not row.established_before_trigger
    assert row.delta_price_cost == pytest.approx(0.0)
    assert daily.iloc[0].decision == row.first_trigger
    assert landmarks.age_days.tolist() == [7, 14, 21]
    assert (landmarks.fill == landmarks.decision + pd.Timedelta(days=1)).all()
    assert (landmarks.label_end == landmarks.fill + pd.Timedelta(days=7)).all()


def test_same_timing_market_control_does_not_call_shared_beta_alpha(monkeypatch):
    month = one_month(monkeypatch)
    p = panels()
    jump = pd.Timestamp("2020-08-20", tz="UTC")
    for key in ("open", "close"):
        p[key].loc[jump:] *= 1.5
    monthly, _, _, _, _ = LIFE.calculate(p)
    row = monthly.iloc[0]
    assert row.first_trigger == month + pd.Timedelta(days=8)
    assert row.delta_price_cost == pytest.approx(-0.5 * (1 - LIFE.COST))
    assert row.market_delta_price_cost == pytest.approx(row.delta_price_cost)
    assert row.delta_excess_price_cost == pytest.approx(0.0, abs=1e-12)
    assert row.missed_upside == pytest.approx(-row.delta_price_cost)
    assert row.avoided_loss == 0.0


def test_unknown_state_does_not_fabricate_an_exit(monkeypatch):
    month = one_month(monkeypatch)
    p = panels()
    non_top = LIFE.select_month(p, month).symbol.iloc[-1]
    p["research_segment_id"].loc[month + pd.Timedelta(days=2):, non_top] = f"{non_top}#2"
    monthly, daily, _, _, _ = LIFE.calculate(p)
    row = monthly.iloc[0]
    assert row.first_trigger is None
    assert daily.state.eq("unavailable").all()
    assert row.unknown_state_days == len(daily)
    assert row.candidate_price_cost == pytest.approx(row.baseline_price_cost)
    assert row.delta_price_cost == pytest.approx(0.0)


def test_known_state_does_not_read_decision_day_or_future():
    p = panels()
    month = pd.Timestamp("2020-08-01", tz="UTC")
    pool = LIFE.select_month(p, month)
    names = pool.symbol.tolist()
    decision = pd.Timestamp("2020-08-09", tz="UTC")
    signal_end = month - pd.Timedelta(days=1)
    entry = month + pd.Timedelta(days=1)
    end = pd.Timestamp("2020-09-02", tz="UTC")

    def state():
        top = LIFE.basket_paths(p, names[:10], signal_end, entry, end)
        market = LIFE.basket_paths(p, names, signal_end, entry, end)
        return LIFE.known_state(top, market, decision)

    before = state()
    p["close"].loc[decision:, names[0]] *= 100.0
    p["open"].loc[decision:, names[0]] *= 0.01
    np.testing.assert_allclose(before, state())


def test_landmark_cannot_extend_beyond_month_end(monkeypatch):
    month = one_month(monkeypatch, "2021-02-01")
    _, _, landmarks, _, _ = LIFE.calculate(panels(str(month.date())))
    late = landmarks.loc[landmarks.age_days.eq(21)].iloc[0]
    assert not late.within_holding_month
    assert not late.valid
    assert np.isnan(late.future_top7)
    assert np.isnan(late.future_market7)


def test_block_bootstrap_is_deterministic_and_retains_missing_months(monkeypatch):
    monkeypatch.setattr(LIFE, "START", pd.Timestamp("2020-01-01", tz="UTC"))
    monkeypatch.setattr(LIFE, "LAST", pd.Timestamp("2020-06-01", tz="UTC"))
    dates = pd.date_range(LIFE.START, LIFE.LAST, freq="MS")
    values = pd.Series([0.1, np.nan, np.nan, 0.3, np.nan, -0.2], index=dates)
    first = LIFE.block_ci(values, draws=100)
    assert first == LIFE.block_ci(values, draws=100)
    assert first["months"] == 3
    assert first["mean"] == pytest.approx(0.2 / 3)
    empty = LIFE.block_ci(pd.Series(np.nan, index=dates), draws=100)
    assert empty["mean"] is None and empty["p05"] is None and empty["p95"] is None


def test_make_panels_rejects_duplicate_keys_and_noncausal_mask():
    frame = pd.DataFrame({
        "ts": pd.date_range("2020-01-01", periods=2, tz="UTC"),
        "symbol": ["A/USDT:USDT"] * 2, "open": [1.0, 1.0], "close": [1.0, 1.0],
        "quote_volume": [20_000_000.0] * 2, "research_segment_id": ["A#1"] * 2,
        "eligible": [True, True], "research_window_valid": [True, True],
    })
    with pytest.raises(ValueError, match="duplicate"):
        LIFE.make_panels(pd.concat([frame, frame.iloc[:1]], ignore_index=True))
    frame.loc[1, "research_window_valid"] = False
    with pytest.raises(ValueError, match="mask mismatch"):
        LIFE.make_panels(frame)
