"""Independent synthetic acceptance for the 76-month estimated-account adapter.

Only generated prices/events are used. Passing these examples verifies account
arithmetic and failure handling, not historical funding completeness or fills.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


SCRIPTS = (Path(__file__).resolve().parents[1]
           / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts")
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "mcsm_baseline_estimate_independent_audit", SCRIPTS / "run_mcsm_baseline_estimate_20260909.py")
assert SPEC is not None and SPEC.loader is not None
EST = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EST
SPEC.loader.exec_module(EST)
NAMES = list("ABCDEFGHIJ")
INITIAL = 100_000.0
COST = 0.0014
POST_ENTRY = INITIAL / (1 + COST)


def synthetic_inputs():
    months = pd.date_range("2020-03-01", "2026-06-01", freq="MS", tz="UTC")
    holdings = pd.DataFrame([
        {"month": month, "entry_ts": month + pd.Timedelta(minutes=15),
         "exit_ts": month + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15),
         "symbol": symbol, "weight": 0.1}
        for month in months for symbol in NAMES
    ])
    boundaries = pd.date_range("2020-03-01", "2026-07-01", freq="MS", tz="UTC")
    execution = pd.DataFrame([
        {"ts": boundary + pd.Timedelta(minutes=15), "symbol": symbol, "price": 10.0}
        for boundary in boundaries for symbol in NAMES
    ])
    daily = pd.DataFrame([
        {"ts": day, "symbol": symbol, "close": 10.0, "eligible": True}
        for day in pd.date_range("2020-03-01", "2026-06-30", freq="D", tz="UTC")
        for symbol in NAMES
    ])
    funding = pd.DataFrame(columns=[
        "ts", "symbol", "rate_type", "funding_rate", "mark_center", "mark_low", "mark_high", "mark_source"
    ])
    return holdings, execution, daily, funding, []


@pytest.fixture(scope="module")
def inputs():
    return synthetic_inputs()


@pytest.fixture(scope="module")
def flat_result(inputs):
    return EST.run_scenario(*inputs, "price_only")


def mutated_inputs(inputs):
    return [frame.copy(deep=True) if isinstance(frame, pd.DataFrame) else deepcopy(frame) for frame in inputs]


def assert_full_account_identity(result):
    m = result["metrics"]
    assert m["final_equity"] == pytest.approx(
        INITIAL + m["price_pnl_usdt"] + m["funding_pnl_usdt"]
        - m["fees_usdt"] - m["slippage_usdt"], abs=1e-7)
    assert np.prod(1 + result["monthly"].account_return) == pytest.approx(m["final_equity"] / INITIAL, abs=1e-11)
    assert np.prod([1 + y["return"] for y in m["yearly"]]) == pytest.approx(m["final_equity"] / INITIAL, abs=1e-11)
    assert len(result["monthly"]) == 76
    assert result["monthly"].month.tolist() == pd.date_range("2020-03-01", "2026-06-01", freq="MS", tz="UTC").tolist()
    assert m["full_account_closed"]
    assert not m["margin_liquidation_simulated"]
    assert not m["calendar_verified"]
    assert not m["pit_verified"]


def test_76_flat_months_only_charge_actual_initial_and_final_net_trades(flat_result):
    result = flat_result
    m = result["metrics"]
    assert m["final_equity"] == pytest.approx(POST_ENTRY * (1 - COST), abs=1e-7)
    assert m["fees_usdt"] == pytest.approx(2 * POST_ENTRY * 0.001, abs=1e-7)
    assert m["slippage_usdt"] == pytest.approx(2 * POST_ENTRY * 0.0004, abs=1e-7)
    assert m["price_pnl_usdt"] == pytest.approx(0, abs=1e-7)
    assert m["funding_pnl_usdt"] == 0
    middle = result["trades"].loc[result["trades"].ts.gt(EST.START) & result["trades"].ts.lt(EST.END)]
    assert middle.traded_notional.sum() == pytest.approx(0, abs=1e-7)
    assert result["monthly"].account_return.iloc[0] == pytest.approx(1 / (1 + COST) - 1)
    assert result["monthly"].account_return.iloc[-1] == pytest.approx(-COST)
    assert m["max_drawdown_daily_and_rebalance"] == pytest.approx(m["total_return"], abs=1e-11)
    assert result["nav"].ts.iloc[0] == EST.START
    assert result["nav"].ts.iloc[-1] == EST.END
    assert_full_account_identity(result)


def test_monthly_basket_is_fixed_units_and_marks_do_not_rebalance(inputs):
    data = mutated_inputs(inputs)
    daily = data[2]
    for day, a, b in (("2020-03-02", 20, 5), ("2020-03-03", 40, 2.5)):
        daily.loc[daily.ts.eq(pd.Timestamp(day, tz="UTC")) & daily.symbol.eq("A"), "close"] = a
        daily.loc[daily.ts.eq(pd.Timestamp(day, tz="UTC")) & daily.symbol.eq("B"), "close"] = b
    result = EST.run_scenario(*data, "price_only")
    row = result["daily"].set_index("ts").loc[pd.Timestamp("2020-03-04", tz="UTC")]
    assert row.equity == pytest.approx(POST_ENTRY * (0.8 + 0.1 * 4 + 0.1 * 0.25), abs=1e-7)
    assert row.price_pnl == pytest.approx(POST_ENTRY * 0.225, abs=1e-7)
    assert not result["trades"].ts.between(EST.START, pd.Timestamp("2020-04-01", tz="UTC"), inclusive="neither").any()
    # With no intervening cash flow, 1x fixed units retain equity == gross.
    open_nav = result["nav"].loc[result["nav"].ts.lt(EST.END)]
    np.testing.assert_allclose(open_nav.gross_notional, open_nav.equity, rtol=0, atol=1e-7)
    assert_full_account_identity(result)


def test_one_month_doubling_survives_continuous_month_and_year_attribution(inputs):
    data = mutated_inputs(inputs)
    data[1].loc[data[1].ts.ge(pd.Timestamp("2020-04-01", tz="UTC")), "price"] = 20.0
    data[2].loc[data[2].ts.ge(pd.Timestamp("2020-03-31", tz="UTC")), "close"] = 20.0
    result = EST.run_scenario(*data, "price_only")
    assert result["metrics"]["final_equity"] == pytest.approx(2 * POST_ENTRY * (1 - COST), abs=1e-7)
    assert result["monthly"].account_return.iloc[0] == pytest.approx(2 / (1 + COST) - 1)
    assert_full_account_identity(result)


def make_funding(ts, rate, *, kind="Regular", symbol="A", mark=10.0):
    return {"ts": pd.Timestamp(ts), "symbol": symbol, "rate_type": kind,
            "funding_rate": rate, "mark_center": mark, "mark_low": mark, "mark_high": mark,
            "mark_source": "SYNTHETIC_ACTUAL_EVENT_MARK"}


@pytest.mark.parametrize("rate", [-0.01, 0.01])
def test_funding_is_cash_actual_notional_and_each_account_reinvests_only_at_next_month(inputs, rate):
    data = mutated_inputs(inputs)
    data[3] = pd.DataFrame([
        make_funding("2020-03-15T08:00:00Z", rate, mark=20),
        make_funding("2020-03-16T08:00:00Z", rate, mark=10),
    ])
    result = EST.run_scenario(*data, "estimated_center")
    q = POST_ENTRY * .1 / 10
    funding_cash = -q * (20 + 10) * rate
    # Fixed quantity means the second event is not enlarged by the first fee/income.
    np.testing.assert_allclose(result["funding"].quantity, q, rtol=0, atol=1e-10)
    assert result["metrics"]["funding_pnl_usdt"] == pytest.approx(funding_cash, abs=1e-7)
    after_next_rebalance = POST_ENTRY + funding_cash / (1 + COST if funding_cash > 0 else 1 - COST)
    assert result["metrics"]["final_equity"] == pytest.approx(after_next_rebalance * (1 - COST), abs=1e-7)
    after_two_events = result["nav"].set_index("ts").loc[pd.Timestamp("2020-03-17", tz="UTC")]
    assert after_two_events.equity == pytest.approx(POST_ENTRY + funding_cash, abs=1e-7)
    if rate > 0:
        assert after_two_events.gross_to_equity > 1
        assert result["metrics"]["max_gross_to_equity_sampled"] > 1
    else:
        assert after_two_events.gross_to_equity < 1
    assert_full_account_identity(result)


def test_regular_and_special_same_native_timestamp_both_survive_adapter(inputs):
    data = mutated_inputs(inputs)
    ts = "2020-03-01T08:00:00Z"
    data[3] = pd.DataFrame([make_funding(ts, .001), make_funding(ts, -.002, kind="Special")])
    result = EST.run_scenario(*data, "estimated_center")
    assert result["metrics"]["funding_events_booked"] == 2
    assert set(result["funding"].rate_type) == {"Regular", "Special"}
    assert result["metrics"]["funding_pnl_usdt"] == pytest.approx(POST_ENTRY * .1 * .001)
    assert_full_account_identity(result)


@pytest.mark.parametrize("scenario,income_mark,expense_mark", [
    ("estimated_center", 10.0, 10.0),
    ("estimated_adverse", 8.0, 12.0),
    ("estimated_favorable", 12.0, 8.0),
])
def test_each_funding_scenario_rebalances_its_own_capital(inputs, scenario, income_mark, expense_mark):
    data = mutated_inputs(inputs)
    events = [make_funding("2020-03-15T08:00:00Z", -.01),
              make_funding("2020-06-15T08:00:00Z", .01)]
    for event in events:
        event.update(mark_low=8.0, mark_high=12.0, mark_source="SYNTHETIC_MARK_MINUTE_PROXY")
    data[3] = pd.DataFrame(events)
    result = EST.run_scenario(*data, scenario)
    initial_q = POST_ENTRY / 100
    first_cash = initial_q * income_mark * .01
    after_income_rebalance = POST_ENTRY + first_cash / (1 + COST)
    second_q = after_income_rebalance / 100
    second_cash = -second_q * expense_mark * .01
    after_expense_rebalance = after_income_rebalance + second_cash / (1 - COST)
    assert result["funding"].quantity.iloc[0] == pytest.approx(initial_q)
    assert result["funding"].quantity.iloc[1] == pytest.approx(second_q)
    assert result["funding"].estimate_mark.tolist() == [income_mark, expense_mark]
    assert result["metrics"]["final_equity"] == pytest.approx(after_expense_rebalance * (1 - COST), abs=1e-7)
    assert_full_account_identity(result)


@pytest.mark.parametrize("rate,adverse,favorable", [(0.01, 12, 8), (-0.01, 8, 12), (0, 12, 8)])
def test_long_funding_mark_scenarios_reverse_with_rate_sign(rate, adverse, favorable):
    row = {"mark_center": 10, "mark_low": 8, "mark_high": 12, "funding_rate": rate}
    assert EST.choose_funding_mark(row, "estimated_center") == 10
    assert EST.choose_funding_mark(row, "estimated_adverse") == adverse
    assert EST.choose_funding_mark(row, "estimated_favorable") == favorable


def test_terminal_realization_keeps_cash_until_next_rebalance_and_charges_explicit_fee(inputs):
    data = mutated_inputs(inputs)
    terminal_ts = pd.Timestamp("2020-03-15T10:00:00Z")
    later = data[0].month.ge(pd.Timestamp("2020-04-01", tz="UTC")) & data[0].symbol.eq("A")
    data[0].loc[later, "symbol"] = "K"
    first_a = data[0].month.eq(pd.Timestamp("2020-03-01", tz="UTC")) & data[0].symbol.eq("A")
    data[0].loc[first_a, "exit_ts"] = terminal_ts
    data[1] = pd.concat([data[1], data[1].loc[data[1].symbol.eq("A")].assign(symbol="K")], ignore_index=True)
    data[2] = pd.concat([data[2], data[2].loc[data[2].symbol.eq("A")].assign(symbol="K")], ignore_index=True)
    data[4] = [{"symbol": "A", "ts": terminal_ts, "center": 8, "low": 7, "high": 9,
                "source_path": "synthetic-index-minute", "source_sha256": "synthetic-source-identifier",
                "source_quality": "SYNTHETIC_TERMINAL_CONDITIONAL_RANGE"}]
    result = EST.run_scenario(*data, "price_only")
    q = POST_ENTRY / 100
    terminal = result["terminals"].iloc[0]
    assert terminal.quantity == pytest.approx(q)
    assert terminal.realized_price_pnl == pytest.approx(-q * 2)
    assert terminal.fee == pytest.approx(q * 8 * .001)
    assert terminal.slippage == 0
    next_day = result["nav"].set_index("ts").loc[pd.Timestamp("2020-03-16", tz="UTC")]
    pre = POST_ENTRY - q * 2 - q * 8 * .001
    assert next_day.equity == pytest.approx(pre, abs=1e-7)
    assert next_day.gross_notional == pytest.approx(POST_ENTRY * .9, abs=1e-7)
    assert next_day.gross_to_equity < 1
    # Nine incumbent names shrink slightly; the new K position consumes freed cash.
    next_target = (pre - .9 * COST * POST_ENTRY) / (1 - .8 * COST)
    assert result["metrics"]["final_equity"] == pytest.approx(next_target * (1 - COST), abs=1e-7)
    assert_full_account_identity(result)


def test_utc_year_boundary_uses_previous_day_close_not_jan_first_trade(inputs):
    data = mutated_inputs(inputs)
    data[1].loc[data[1].ts.ge(pd.Timestamp("2021-01-01", tz="UTC")), "price"] = 20
    data[1].loc[data[1].ts.ge(pd.Timestamp("2022-01-01", tz="UTC")), "price"] = 40
    data[2].loc[data[2].ts.ge(pd.Timestamp("2020-12-31", tz="UTC")), "close"] = 20
    data[2].loc[data[2].ts.ge(pd.Timestamp("2021-12-31", tz="UTC")), "close"] = 40
    result = EST.run_scenario(*data, "price_only")
    years = {row["year"]: row for row in result["metrics"]["yearly"]}
    assert years[2020]["return"] == pytest.approx(2 / (1 + COST) - 1)
    assert years[2021]["return"] == pytest.approx(1)
    assert years[2022]["return"] == pytest.approx(0, abs=1e-12)
    assert years[2026]["return"] == pytest.approx(-COST)
    assert years[2020]["partial_year"] and years[2026]["partial_year"]
    assert_full_account_identity(result)


def test_compact_ledger_preserves_all_numeric_account_results(inputs, flat_result, monkeypatch):
    monkeypatch.setattr(EST, "compact_row", deepcopy)
    uncompressed = EST.run_scenario(*inputs, "price_only")
    assert uncompressed["metrics"] == flat_result["metrics"]
    for table in ("nav", "daily", "monthly", "trades"):
        columns = flat_result[table].columns
        pd.testing.assert_frame_equal(uncompressed[table][columns], flat_result[table])


def test_month_contract_rejects_arbitrary_exit_even_when_after_entry(inputs):
    holdings = inputs[0].copy()
    holdings.loc[0, "exit_ts"] = pd.Timestamp("2020-05-01T00:15:00Z")
    with pytest.raises(ValueError, match="exit|interval|terminal"):
        EST.validate_holdings(holdings)


@pytest.mark.parametrize("bad", [False, None, np.nan, "False", "True", 1])
def test_missing_or_nonboolean_eligibility_never_means_valid(inputs, bad):
    data = mutated_inputs(inputs)
    data[2]["eligible"] = data[2].eligible.astype(object)
    data[2].loc[0, "eligible"] = bad
    with pytest.raises((ValueError, EST.AccountingError), match="eligible|eligibility"):
        EST.run_scenario(*data, "price_only")


def test_missing_daily_price_and_execution_do_not_skip_months(inputs):
    data = mutated_inputs(inputs)
    data[2] = data[2].drop(index=0)
    with pytest.raises(EST.AccountingError, match="missing daily mark"):
        EST.run_scenario(*data, "price_only")
    data = mutated_inputs(inputs)
    data[1] = data[1].drop(index=0)
    with pytest.raises(EST.AccountingError, match="missing prices"):
        EST.run_scenario(*data, "price_only")


def test_funding_duplicate_and_unheld_events_are_not_discarded(inputs):
    data = mutated_inputs(inputs)
    event = make_funding("2020-03-01T08:00:00Z", .001)
    data[3] = pd.DataFrame([event, event])
    with pytest.raises(ValueError, match="duplicate native funding identity"):
        EST.run_scenario(*data, "estimated_center")
    data[3] = pd.DataFrame([make_funding("2020-03-01T08:00:00Z", .001, symbol="NOT_HELD")])
    with pytest.raises(EST.AccountingError, match="outside actual position"):
        EST.run_scenario(*data, "estimated_center")


def test_unknown_scenario_does_not_silently_produce_an_account(inputs):
    with pytest.raises(ValueError, match="scenario"):
        EST.run_scenario(*inputs, "invented_scenario")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.0, -1.0])
def test_invalid_funding_proxy_does_not_become_zero_funding(bad):
    with pytest.raises(ValueError):
        EST.choose_funding_mark({"mark_center": bad, "mark_low": 1, "mark_high": 2,
                                 "funding_rate": .001}, "estimated_center")
