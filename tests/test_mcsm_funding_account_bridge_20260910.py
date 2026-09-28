"""Small synthetic independent interval-account tests; no historical IO."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

SCRIPTS = (Path(__file__).resolve().parents[1]
           / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts")
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("mcsm_interval_bridge", SCRIPTS / "audit_mcsm_funding_account_bridge_20260910.py")
assert SPEC is not None and SPEC.loader is not None
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)
COST = .0014
OPEN = 100_000 / (1 + COST)


def inputs(months=1):
    dates = pd.date_range("2020-03-01", periods=months + 1, freq="MS", tz="UTC")
    names = list("ABCDEFGHIJ")
    h = pd.DataFrame([{"month": day, "entry_ts": day + pd.Timedelta(minutes=15),
                       "exit_ts": dates[i + 1] + pd.Timedelta(minutes=15), "symbol": symbol,
                       "weight": .1, "entry_price": 100., "exit_price": 100., "terminal": False}
                      for i, day in enumerate(dates[:-1]) for symbol in names])
    x = pd.DataFrame([{"ts": day + pd.Timedelta(minutes=15), "symbol": symbol, "price": 100.}
                      for day in dates for symbol in names])
    d = pd.DataFrame([{"ts": day, "symbol": symbol, "close": 100., "eligible": True}
                      for day in pd.date_range(dates[0], dates[-1] - pd.Timedelta(days=1)) for symbol in names])
    f = pd.DataFrame([{"ts": dates[0] + pd.Timedelta(days=10), "symbol": "A", "rate_type": "Regular",
                       "funding_rate": -.02, "mark_center": 100., "mark_low": 90., "mark_high": 110.}])
    return h, x, d.set_index(["ts", "symbol"]), f


def run(h, x, d, f, terminals=None, scenario="estimated_center"):
    return A.reconstruct(h, x, d, f, A.prepare_windows(h, f), terminals or {}, scenario)


def test_signed_cash_decimal_percentage_not_times_100():
    assert A.funding_cash(10., 100., -.02) == 20.
    assert A.funding_cash(10., 100., .02) == -20.
    assert A.funding_cash(10., 100., 0.) == 0.


def test_independent_bisection_exact_entry_exit_and_net_only():
    assert A.solve_post_cost(100_000, {}, {"A": 1.}) == pytest.approx(OPEN)
    assert A.solve_post_cost(100_000, {"A": 100_000}, {"A": 1.}) == pytest.approx(100_000)
    assert A.solve_post_cost(100_000, {"A": 100_000}, {}) == pytest.approx(99_860)


@pytest.mark.parametrize("scenario,mark", [("estimated_center", 100.), ("estimated_adverse", 90.), ("estimated_favorable", 110.)])
def test_single_interval_closed_form_and_daily_cash_timing(scenario, mark):
    h, x, d, f = inputs()
    result = run(h, x, d, f, scenario=scenario)
    quantity = OPEN / 10 / 100
    income = quantity * mark * .02
    assert result["final_equity"] == pytest.approx(OPEN * (1 - COST) + income)
    assert result["cash"] == pytest.approx([income])
    same_time = result["nav"].loc[result["nav"].ts.eq(f.ts.iloc[0]), "equity"].iloc[0]
    next_day = result["nav"].loc[result["nav"].ts.eq(f.ts.iloc[0] + pd.Timedelta(days=1)), "equity"].iloc[0]
    assert same_time == pytest.approx(OPEN)
    assert next_day == pytest.approx(OPEN + income)
    assert result["nav"].price_pnl.eq(0).all()


def test_same_name_overlap_only_increase_is_traded_and_new_month_compounds():
    h, x, d, f = inputs(2)
    f = pd.concat([f, f.assign(ts=pd.Timestamp("2020-04-11", tz="UTC"))], ignore_index=True)
    result = run(h, x, d, f)
    first_income = OPEN * .1 * .02
    april_capital = OPEN + first_income / (1 + COST)
    april_trades = result["trades"].loc[result["trades"].ts.eq(pd.Timestamp("2020-04-01T00:15Z"))]
    assert april_trades.traded_notional.sum() == pytest.approx(april_capital - OPEN)
    assert result["quantities"] == pytest.approx([OPEN / 1000, april_capital / 1000])
    assert result["final_equity"] == pytest.approx(april_capital * (1 - COST + .002))
    assert np.prod(1 + result["monthly"].account_return) == pytest.approx(result["final_equity"] / 100_000)


def test_same_instant_regular_special_both_count_without_duplicate_merging():
    h, x, d, f = inputs()
    f = pd.concat([f, f.assign(rate_type="Special", funding_rate=.01)], ignore_index=True)
    result = run(h, x, d, f)
    assert result["cash"].sum() == pytest.approx(OPEN * .001)
    assert result["quantities"][0] == result["quantities"][1]
    with pytest.raises(ValueError, match="duplicate"):
        A.prepare_windows(h, pd.concat([f, f.iloc[[0]]]))


@pytest.mark.parametrize("boundary,allowed", [("entry", False), ("exit", True), ("after", False)])
def test_exact_holding_window_endpoints(boundary, allowed):
    h, x, d, f = inputs()
    f.loc[0, "ts"] = {"entry": h.entry_ts.iloc[0], "exit": h.exit_ts.iloc[0],
                       "after": h.exit_ts.iloc[0] + pd.Timedelta(milliseconds=1)}[boundary]
    if allowed:
        assert sum(len(v) for v in A.prepare_windows(h, f).values()) == 1
    else:
        with pytest.raises(ValueError, match="outside actual"):
            A.prepare_windows(h, f)


def test_terminal_cash_not_reinvested_and_price_telescopes():
    h, x, d, f = inputs()
    terminal = pd.Timestamp("2020-03-15T09:00Z")
    h.loc[h.symbol.eq("A"), ["terminal", "exit_ts", "exit_price"]] = [True, terminal, 110.]
    values = {("A", terminal): {s: 110. for s in A.SCENARIOS}}
    result = run(h, x, d, f, values)
    q = OPEN / 1000
    assert result["nav"].price_pnl.iloc[-1] == pytest.approx(q * 10)
    assert result["final_equity"] == pytest.approx(OPEN + q * 10 + OPEN * .002 - q * 110 * .001 - OPEN * .9 * COST)
    assert "A" not in result["trades"].loc[result["trades"].ts.eq(h.exit_ts.max()), "symbol"].tolist()
    f.loc[0, "ts"] = terminal + pd.Timedelta(milliseconds=1)
    with pytest.raises(ValueError, match="outside actual"):
        A.prepare_windows(h, f)


def test_price_only_never_books_funding_and_invalid_mark_not_zero_filled():
    h, x, d, f = inputs()
    result = run(h, x, d, f, scenario="price_only")
    assert result["cash"].sum() == 0
    assert result["final_equity"] == pytest.approx(OPEN * (1 - COST))
    f.loc[0, "mark_center"] = np.nan
    with pytest.raises(ValueError, match="invalid funding"):
        run(h, x, d, f)
