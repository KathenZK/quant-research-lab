"""Synthetic checks for the independent funded-replica audit, no historical IO."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest


SCRIPTS = (Path(__file__).resolve().parents[1]
           / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts")
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("funded_independent_audit_test", SCRIPTS / "audit_mcsm_funded_replica_20260909.py")
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)
START = pd.Timestamp("2020-03-01T00:15:00Z")
END = pd.Timestamp("2020-06-01T00:15:00Z")
C = .0014
S = 100_000 / (1 + C)


def inputs():
    names = list("ABCDEFGHIJ")
    times = pd.date_range(START, END, freq="MS")
    h = pd.DataFrame([{"entry_ts": ts, "symbol": symbol, "weight": .1}
                      for ts in times[:-1] for symbol in names])
    x = pd.DataFrame([{"ts": ts, "symbol": symbol, "price": 10.0}
                      for ts in times for symbol in names])
    d = pd.DataFrame([{"ts": day, "symbol": symbol, "eligible": True, "close": 10.0}
                      for day in pd.date_range("2020-03-01", "2020-05-31", tz="UTC") for symbol in names])
    f = pd.DataFrame([
        {"ts": pd.Timestamp("2020-03-15T08:00:00Z"), "symbol": "A", "rate_type": "Regular",
         "source_type": "Regular", "funding_rate": -.01, "mark_center": 10, "mark_low": 8, "mark_high": 12},
        {"ts": pd.Timestamp("2020-04-15T08:00:00Z"), "symbol": "A", "rate_type": "Regular",
         "source_type": "Regular", "funding_rate": .01, "mark_center": 10, "mark_low": 8, "mark_high": 12},
    ])
    return h, x, d.set_index(["ts", "symbol"]), f


@pytest.mark.parametrize("scenario,income_mark,expense_mark", [
    ("estimated_center", 10, 10), ("estimated_adverse", 8, 12), ("estimated_favorable", 12, 8)
])
def test_closed_form_cash_chain_and_own_scenario_quantity(scenario, income_mark, expense_mark):
    h, x, d, f = inputs()
    result = AUDIT.reconstruct(h, x, d, f, [], scenario, START, END)
    first_q = S / 100
    first_cash = first_q * income_mark * .01
    april_capital = S + first_cash / (1 + C)
    second_q = april_capital / 100
    second_cash = -second_q * expense_mark * .01
    may_capital = april_capital + second_cash / (1 - C)
    assert result["final"]["equity"] == pytest.approx(may_capital * (1 - C), abs=1e-8)
    assert result["funding"].quantity.tolist() == pytest.approx([first_q, second_q])
    assert result["funding"].funding_cash.tolist() == pytest.approx([first_cash, second_cash])
    assert result["final"]["funding_pnl"] == pytest.approx(first_cash + second_cash)
    final = result["final"]
    assert final["equity"] == pytest.approx(100_000 + final["price_pnl"] + final["funding_pnl"] - final["fees"] - final["slippage"], abs=1e-8)
    assert (1 + result["monthly"].account_return).prod() == pytest.approx(final["equity"] / 100_000)


def test_same_timestamp_regular_special_are_distinct_and_not_reinvested():
    h, x, d, f = inputs()
    extra = f.iloc[[0]].copy()
    extra["rate_type"] = "Special"
    extra["source_type"] = "Special"
    extra["funding_rate"] = .005
    f = pd.concat([f, extra], ignore_index=True)
    result = AUDIT.reconstruct(h, x, d, f, [], "estimated_center", START, END)
    first_pair = result["funding"].iloc[:2]
    assert first_pair.rate_type.tolist() == ["Regular", "Special"]
    assert first_pair.quantity.tolist() == pytest.approx([S / 100, S / 100])
    assert first_pair.funding_cash.tolist() == pytest.approx([S * .001, -S * .0005])


def test_unknown_native_type_and_duplicate_are_not_merged():
    h, x, d, f = inputs()
    with pytest.raises(ValueError, match="duplicate funding event identity"):
        AUDIT.reconstruct(h, x, d, pd.concat([f, f.iloc[[0]]]), [], "estimated_center", START, END)
    f.loc[0, "rate_type"] = "Unknown"
    with pytest.raises(ValueError, match="unknown rate type"):
        AUDIT.reconstruct(h, x, d, f, [], "estimated_center", START, END)


def test_terminal_reserve_is_not_redistributed_and_funding_after_close_is_rejected():
    h, x, d, f = inputs()
    ts = pd.Timestamp("2020-03-10T10:00:00Z")
    terminal = {"ts": ts, "symbol": "A", "center": 8, "low": 7, "high": 9}
    with pytest.raises(ValueError, match="unheld funding contract"):
        AUDIT.reconstruct(h, x, d, f, [terminal], "estimated_center", START, END)
    f = f.iloc[0:0]
    h = h.copy()
    h.loc[h.entry_ts.gt(START) & h.symbol.eq("A"), "symbol"] = "K"
    x = pd.concat([x, x.loc[x.symbol.eq("A")].assign(symbol="K")], ignore_index=True)
    d = d.reset_index()
    d = pd.concat([d, d.loc[d.symbol.eq("A")].assign(symbol="K")], ignore_index=True).set_index(["ts", "symbol"])
    result = AUDIT.reconstruct(h, x, d, f, [terminal], "estimated_adverse", START, END)
    row = result["nav"].set_index("ts").loc[pd.Timestamp("2020-03-11", tz="UTC")]
    assert row.gross_notional == pytest.approx(S * .9)
    assert row.replica_reserve_cash == pytest.approx(S / 100 * 7 * .999)
    assert result["terminals"].settlement_price.tolist() == [7]


@pytest.mark.parametrize("field,value", [("mark_center", None), ("mark_low", float("nan")),
                                         ("funding_rate", float("inf")), ("mark_high", 0)])
def test_invalid_cash_source_fails_closed(field, value):
    row = {"funding_rate": .01, "mark_center": 10, "mark_low": 9, "mark_high": 11}
    row[field] = value
    with pytest.raises((ValueError, TypeError)):
        AUDIT.mark_for_event(row, "estimated_center")
