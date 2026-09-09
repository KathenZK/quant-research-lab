"""Independent synthetic examples: no lake reads or historical return claims."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import random
import sys

import pytest


SCRIPT = (Path(__file__).resolve().parents[1]
          / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
          / "mcsm_baseline_accounting_20260908.py")
SPEC = importlib.util.spec_from_file_location("mcsm_baseline_accounting_20260908", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
ENGINE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ENGINE
SPEC.loader.exec_module(ENGINE)
Account, AccountingError = ENGINE.LinearPerpAccount, ENGINE.AccountingError
T0, T1, T2, T3 = [f"2020-01-0{day}T00:00:00Z" for day in range(1, 5)]


def assert_identities(account):
    snap = account.snapshot()
    assert snap["cash"] == pytest.approx(
        account.initial_cash + snap["realized_price_pnl"] + snap["funding_pnl"]
        - snap["fees"] - snap["slippage"], abs=1e-8)
    assert snap["equity"] == pytest.approx(snap["cash"] + snap["unrealized_price_pnl"], abs=1e-8)
    assert snap["equity"] == pytest.approx(
        account.initial_cash + snap["price_pnl"] + snap["funding_pnl"]
        - snap["fees"] - snap["slippage"], abs=1e-8)
    for row in account.ledger:
        assert row["event_identity_error"] == pytest.approx(0, abs=1e-8)


def assert_rejected_atomically(account, operation):
    before, ledger = account.snapshot(), deepcopy(account.ledger)
    with pytest.raises(AccountingError):
        operation()
    assert account.snapshot() == before
    assert account.ledger == ledger


def test_initial_post_cost_target_solves_implicit_equation():
    account = Account()
    row = account.rebalance(T0, {"A": 0.5, "B": 0.5}, {"A": 100, "B": 20})
    expected = 100_000 / 1.0014
    assert row["equity"] == pytest.approx(expected)
    assert row["cash"] == pytest.approx(expected)  # Perp notional is not a cash purchase.
    assert row["gross_notional"] == pytest.approx(expected)
    assert account.positions["A"].quantity == pytest.approx(expected / 200)
    assert account.positions["B"].quantity == pytest.approx(expected / 40)
    assert row["fees"] == pytest.approx(expected * 0.001)
    assert row["slippage"] == pytest.approx(expected * 0.0004)
    assert row["price_pnl"] == 0
    assert_identities(account)


def test_fixed_quantity_diverging_prices_are_not_daily_equal_weight():
    account = Account(100, fee_rate=0, slippage_rate=0)
    account.rebalance(T0, {"A": 0.5, "B": 0.5}, {"A": 10, "B": 10})
    quantities = {s: p.quantity for s, p in account.positions.items()}
    account.mark(T1, {"A": 20, "B": 5})
    account.mark(T2, {"A": 40, "B": 2.5})
    assert quantities == {s: p.quantity for s, p in account.positions.items()}
    assert account.snapshot()["equity"] == pytest.approx(212.5)
    assert account.snapshot()["equity"] != pytest.approx(100 * 1.25 ** 2)
    assert len(account.ledger) == 3
    assert_identities(account)


def test_same_name_unchanged_price_rebalance_has_no_roundtrip_charge():
    account = Account()
    account.rebalance(T0, {"A": 1}, {"A": 100})
    before = account.snapshot()
    row = account.rebalance(T1, {"A": 1}, {"A": 100})
    assert row["details"]["traded_notional"] == pytest.approx(0, abs=1e-8)
    assert row["fees"] == pytest.approx(before["fees"], abs=1e-8)
    assert row["slippage"] == pytest.approx(before["slippage"], abs=1e-8)
    assert_identities(account)


def test_net_adjustment_and_partial_realization_use_original_basis():
    account = Account(1000, fee_rate=0, slippage_rate=0)
    account.rebalance(T0, {"A": 0.5, "B": 0.5}, {"A": 10, "B": 10})
    row = account.rebalance(T1, {"A": 0.5, "B": 0.5}, {"A": 20, "B": 10})
    # Equity 1500 => A 37.5 units (sell 12.5), B 75 units (buy 25).
    assert account.positions["A"].quantity == pytest.approx(37.5)
    assert account.positions["A"].entry_price == 10
    assert account.positions["B"].quantity == pytest.approx(75)
    assert row["realized_price_pnl"] == pytest.approx(125)
    assert row["unrealized_price_pnl"] == pytest.approx(375)
    assert row["details"]["traded_notional"] == pytest.approx(500)
    assert_identities(account)


def test_added_units_have_weighted_average_reference_basis():
    account = Account(1000, fee_rate=0, slippage_rate=0)
    account.rebalance(T0, {"A": 0.5, "B": 0.5}, {"A": 10, "B": 10})
    account.rebalance(T1, {"A": 1}, {"A": 20, "B": 10})
    assert account.positions["A"].quantity == pytest.approx(75)
    assert account.positions["A"].entry_price == pytest.approx((50 * 10 + 25 * 20) / 75)
    row = account.rebalance(T2, {}, {"A": 30})
    assert not account.positions
    assert row["realized_price_pnl"] == pytest.approx(1250)
    assert row["equity"] == pytest.approx(2250)
    assert row["unrealized_price_pnl"] == 0
    assert_identities(account)


def test_funding_uses_actual_event_notional_and_does_not_reinvest():
    account = Account(1000, fee_rate=0, slippage_rate=0)
    account.rebalance(T0, {"A": 1}, {"A": 10})
    row = account.funding(T1, "A", -0.01, 20)
    assert row["event_funding_pnl"] == pytest.approx(20)
    assert row["event_price_pnl"] == pytest.approx(1000)
    assert row["equity"] == pytest.approx(2020)
    assert account.positions["A"].quantity == 100
    row = account.funding(T2, "A", 0.01, 5)
    assert row["event_funding_pnl"] == pytest.approx(-5)
    assert account.positions["A"].quantity == 100
    assert row["funding_pnl"] == pytest.approx(15)
    assert row["equity"] == pytest.approx(515)
    # Funding cash joins the equity target only at an actual rebalance.
    account.rebalance(T3, {"A": 1}, {"A": 5})
    assert account.positions["A"].quantity == pytest.approx(103)
    assert_identities(account)


def test_duplicate_funding_and_out_of_order_rejected_atomically():
    account = Account()
    account.rebalance(T0, {"A": 1}, {"A": 10})
    account.funding(T1, "A", 0.001, 10)
    assert_rejected_atomically(account, lambda: account.funding(T1, "A", 0.001, 10))
    assert_rejected_atomically(account, lambda: account.mark(T0, {"A": 10}))


def test_regular_and_special_same_timestamp_are_distinct_funding_events():
    account = Account(1000, fee_rate=0, slippage_rate=0)
    account.rebalance(T0, {"A": 1}, {"A": 10})
    regular = account.funding(T1, "A", 0.001, 10)
    special = account.funding(T1, "A", -0.002, 10, rate_type="Special")
    assert regular["details"]["rate_type"] == "Regular"
    assert special["details"]["rate_type"] == "Special"
    assert regular["event_funding_pnl"] == pytest.approx(-1)
    assert special["event_funding_pnl"] == pytest.approx(2)
    assert account.snapshot()["funding_pnl"] == pytest.approx(1)
    assert account.snapshot()["equity"] == pytest.approx(1001)
    for rate_type in ("Regular", "Special"):
        assert_rejected_atomically(account, lambda: account.funding(
            T1, "A", 0.001, 10, rate_type=rate_type))
    assert_identities(account)


@pytest.mark.parametrize("bad_type", [None, "", "regular", "SPECIAL", "Other", True, []])
def test_unknown_funding_type_is_rejected_without_reserving_event(bad_type):
    account = Account(1000, fee_rate=0, slippage_rate=0)
    account.rebalance(T0, {"A": 1}, {"A": 10})
    assert_rejected_atomically(account, lambda: account.funding(
        T1, "A", 0.001, 10, rate_type=bad_type))
    assert account.funding(T1, "A", 0.001, 10)["details"]["rate_type"] == "Regular"


def test_partial_event_mark_is_explicit_and_full_mark_requires_all_positions():
    account = Account()
    account.rebalance(T0, {"A": 0.5, "B": 0.5}, {"A": 10, "B": 10})
    row = account.funding(T1, "A", 0, 11)
    assert not row["all_marks_at_event_time"]
    assert row["positions"]["B"]["mark_timestamp"].startswith("2020-01-01")
    assert_rejected_atomically(account, lambda: account.mark(T1, {"A": 11}))
    assert account.mark(T1, {"A": 11, "B": 12})["all_marks_at_event_time"]


def test_terminal_settlement_realizes_verified_price_without_redistribution():
    account = Account(1000, fee_rate=0, slippage_rate=0)
    account.rebalance(T0, {"A": 0.5, "B": 0.5}, {"A": 10, "B": 10})
    row = account.terminal_close(T1, "A", 8, "synthetic-official-record", settlement_fee_rate=0.001)
    assert row["realized_price_pnl"] == pytest.approx(-100)
    assert row["fees"] == pytest.approx(0.4)
    assert row["slippage"] == 0
    assert row["equity"] == pytest.approx(899.6)
    assert "A" not in account.positions
    assert account.positions["B"].quantity == 50
    assert row["details"]["evidence_id"] == "synthetic-official-record"
    assert_identities(account)


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -1.0, 0.0, True])
def test_invalid_mark_rejected_without_state_change(bad):
    account = Account()
    account.rebalance(T0, {"A": 1}, {"A": 10})
    assert_rejected_atomically(account, lambda: account.mark(T1, {"A": bad}))
    assert_rejected_atomically(account, lambda: account.funding(T1, "A", 0.001, bad))
    assert_rejected_atomically(account, lambda: account.terminal_close(
        T1, "A", bad, "record", settlement_fee_rate=0))


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), True])
def test_missing_funding_is_not_zero_and_does_not_poison_duplicate_guard(bad):
    account = Account()
    account.rebalance(T0, {"A": 1}, {"A": 10})
    assert_rejected_atomically(account, lambda: account.funding(T1, "A", bad, 10))
    account.funding(T1, "A", 0.001, 10)
    assert len(account.ledger) == 2


def test_nonpositive_equity_stops_even_when_caused_by_funding():
    account = Account(1000, fee_rate=0, slippage_rate=0)
    account.rebalance(T0, {"A": 1}, {"A": 10})
    assert_rejected_atomically(account, lambda: account.funding(T1, "A", 1, 10))
    assert_rejected_atomically(account, lambda: account.funding(T1, "A", 2, 10))
    account.funding(T1, "A", 0.9, 10)
    assert_rejected_atomically(account, lambda: account.mark(T2, {"A": 1}))


def test_failed_insolvent_funding_does_not_reserve_event_key():
    account = Account(1000, fee_rate=0, slippage_rate=0)
    account.rebalance(T0, {"A": 1}, {"A": 10})
    assert_rejected_atomically(account, lambda: account.funding(T1, "A", 1, 10))
    assert account.funding(T1, "A", 0, 10)["event_funding_pnl"] == 0


def test_positive_equity_that_cannot_cover_rebalance_costs_stops():
    account = Account(1000, fee_rate=0.01, slippage_rate=0)
    account.rebalance(T0, {"A": 1}, {"A": 10})
    account.funding(T1, "A", 0.995, 10)
    assert account.snapshot()["equity"] > 0
    assert_rejected_atomically(account, lambda: account.rebalance(T2, {}, {"A": 10}))


def test_invalid_targets_and_terminal_evidence_are_not_silently_repaired():
    account = Account()
    for targets in ({"A": 0.5}, {"A": -1}, {"A": 0}, {"A": float("nan")}):
        assert_rejected_atomically(account, lambda: account.rebalance(T0, targets, {"A": 10}))
    account.rebalance(T0, {"A": 1}, {"A": 10})
    assert_rejected_atomically(account, lambda: account.rebalance(T1, {"B": 1}, {"B": 20}))
    assert_rejected_atomically(account, lambda: account.terminal_close(
        T1, "A", 10, "", settlement_fee_rate=0))
    assert_rejected_atomically(account, lambda: account.funding(T1, "B", 0, 10))


def test_naive_or_missing_timestamps_are_prohibited():
    account = Account()
    for timestamp in (None, "2020-01-01", "bad"):
        assert_rejected_atomically(account, lambda: account.rebalance(timestamp, {"A": 1}, {"A": 10}))


def test_reference_slippage_is_not_double_counted_in_entry_or_exit_basis():
    account = Account(1000, fee_rate=0.01, slippage_rate=0.02)
    account.rebalance(T0, {"A": 1}, {"A": 10})
    quantity = 1000 / 1.03 / 10
    assert account.positions["A"].entry_price == 10
    row = account.rebalance(T1, {}, {"A": 12})
    assert row["price_pnl"] == pytest.approx(quantity * 2)
    assert row["fees"] == pytest.approx(quantity * 22 * 0.01)
    assert row["slippage"] == pytest.approx(quantity * 22 * 0.02)
    assert row["equity"] == pytest.approx(1000 + quantity * 2 - quantity * 22 * 0.03)
    assert_identities(account)


def test_randomized_turnover_solver_matches_independent_equation_and_cash_identity():
    rng = random.Random(86420)
    account = Account()
    prices = {"A": 10.0, "B": 20.0, "C": 50.0}
    for day in range(1, 29):
        timestamp = f"2020-01-{day:02d}T00:00:00Z"
        prices = {s: p * rng.uniform(0.95, 1.08) for s, p in prices.items()}
        old_q = {s: p.quantity for s, p in account.positions.items()}
        pre_equity = account.cash + sum(
            p.quantity * (prices[s] - p.entry_price) for s, p in account.positions.items())
        symbols = list(prices)[:rng.randint(1, 3)]
        raw = [rng.uniform(1, 5) for _ in symbols]
        weights = {s: w / sum(raw) for s, w in zip(symbols, raw)}
        row = account.rebalance(timestamp, weights, prices)
        post = row["equity"]
        independent_turnover = sum(
            abs(weights.get(s, 0) * post - old_q.get(s, 0) * prices[s]) for s in prices)
        assert post == pytest.approx(pre_equity - 0.0014 * independent_turnover, abs=1e-8)
        assert row["details"]["traded_notional"] == pytest.approx(independent_turnover, abs=1e-8)
        assert row["gross_notional"] == pytest.approx(post, abs=1e-8)
        for s in symbols:
            account.funding(timestamp, s, rng.uniform(-0.001, 0.001), prices[s])
        assert_identities(account)


def test_returned_snapshots_and_event_rows_are_detached():
    account = Account()
    row = account.rebalance(T0, {"A": 1}, {"A": 10})
    row["positions"]["A"]["quantity"] = -1
    snap = account.snapshot()
    snap["positions"]["A"]["quantity"] = -2
    assert account.positions["A"].quantity > 0
    assert account.ledger[0]["positions"]["A"]["quantity"] > 0
