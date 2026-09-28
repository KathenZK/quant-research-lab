from copy import deepcopy

import pytest

from strategy_lab.research.accounting import LinearAccount, bracket_exit, digest
from strategy_lab.research.portfolio import Score, combine_targets, delta_orders, rank_targets

TS = "2026-09-01T00:00:00Z"


def fill(id, q, price, fee=.001, symbol="A", marks=None, ts=TS):
    return dict(id=id, ts=ts, kind="fill", symbol=symbol, quantity=q, price=price,
                fee_rate=fee, marks=marks or {symbol: price})


def funding(id, rate, price=100, settlement_type="regular", ts=TS):
    return dict(id=id, ts=ts, kind="funding", symbol="A", rate=rate,
                settlement_type=settlement_type, marks={"A": price})


def test_short_one_hundred_to_fifty_is_fifty_not_one_hundred_percent():
    a = LinearAccount(1000)
    a.apply(fill("sell", -10, 100, 0))
    a.apply(fill("buy", 10, 50, 0))
    assert a.cash == 1500 and a.realized == 500


def test_partial_fills_weighted_basis_partial_close_and_reversal():
    a = LinearAccount(1000)
    a.apply(fill("f1", 2, 100))
    a.apply(fill("f2", 3, 110))
    assert a.positions["A"] == {"quantity": 5, "entry": 106}
    a.apply(fill("close", -2, 120))
    assert a.realized == 28
    assert a.positions["A"] == {"quantity": 3, "entry": 106}
    a.apply(fill("flip", -5, 90))
    assert a.realized == -20
    assert a.positions["A"] == {"quantity": -2, "entry": 90}
    assert a.fees == pytest.approx(1.22)
    assert a.cash == pytest.approx(978.78)
    a.apply(dict(id="mtm", kind="mark", ts=TS, marks={"A": 80}))
    assert a.equity == pytest.approx(998.78)


def test_funding_sign_order_and_distinct_settlement_types():
    a = LinearAccount(1000)
    a.apply(funding("before", .01))  # before entry: no position, zero cashflow
    a.apply(fill("short", -2, 100, 0))
    a.apply(funding("special", .02, settlement_type="special"))
    assert a.cash == 1004
    old = a.snapshot()
    with pytest.raises(ValueError, match="duplicate funding"):
        a.apply(funding("duplicate", .01))
    assert a.snapshot() == old
    a.apply(funding("later", -.01, ts="2026-09-01T08:00:00Z"))
    assert a.cash == 1002


def test_long_pays_positive_funding():
    a = LinearAccount(1000)
    a.apply(fill("buy", 2, 100, 0))
    a.apply(funding("fee", .01))
    assert a.funding == -2 and a.cash == 998


@pytest.mark.parametrize("bad", [fill("x", 11, 100), fill("x", 1, 100, -1),
                                  fill("x", float("nan"), 100), fill("x", 1, 0),
                                  fill("x", 1, 100, ts="2026-09-01")])
def test_invalid_event_is_atomic(bad):
    a = LinearAccount(1000)
    before = a.snapshot()
    with pytest.raises(ValueError):
        a.apply(bad)
    assert a.snapshot() == before


def test_duplicate_out_of_order_and_missing_marks_rejected():
    a = LinearAccount(1000)
    a.apply(fill("buy", 2, 100))
    for e in [fill("buy", 2, 100), fill("old", 1, 100, ts="2026-08-31T00:00:00Z"),
              fill("missing", 1, 100, symbol="B")]:
        before = a.snapshot()
        with pytest.raises(ValueError):
            a.apply(e)
        assert a.snapshot() == before


def test_gap_loss_does_not_block_risk_reduction():
    a = LinearAccount(1000, 2)
    a.apply(fill("short", -15, 100, 0))
    a.apply(dict(id="gap", kind="mark", ts=TS, marks={"A": 200}))
    assert a.equity == -500 and a.state()["margin_breached"]
    a.apply(fill("close", 15, 200, 0))
    assert a.cash == -500 and not a.positions


def test_no_second_slippage_deduction_and_restart():
    a = LinearAccount(1000)
    a.apply(fill("buy", 2, 101, .001, marks={"A": 100}))
    assert a.equity == pytest.approx(997.798)
    recovered = LinearAccount.restore(a.snapshot())
    for account in [a, recovered]:
        account.apply(fill("sell", -2, 109, .001))
    assert a.state() == recovered.state()
    assert a.cash == pytest.approx(1015.58)
    corrupt = deepcopy(a.snapshot())
    corrupt["payload"]["state"]["cash"] += 100
    corrupt["sha256"] = digest(corrupt["payload"])
    with pytest.raises(ValueError, match="economic replay"):
        LinearAccount.restore(corrupt)


@pytest.mark.parametrize("side,o,h,lo,c,stop,tp,expected", [
    (1, 80, 95, 75, 90, 90, 110, ("stop_gap", 80)),
    (-1, 120, 125, 105, 110, 110, 90, ("stop_gap", 120)),
    (1, 100, 115, 85, 101, 90, 110, ("stop", 90)),
    (-1, 100, 115, 85, 101, 110, 90, ("stop", 110)),
    (1, 120, 125, 115, 121, 90, 110, ("take_profit", 110)),
    (1, 100, 105, 95, 101, 90, 110, None),
])
def test_bracket_reference(side, o, h, lo, c, stop, tp, expected):
    assert bracket_exit(side=side, open=o, high=h, low=lo, close=c, stop=stop, take_profit=tp) == expected


def test_known_at_fixed_slots_and_ties():
    scores = [Score("B", 1, TS), Score("A", 1, TS)]
    assert rank_targets(scores, decision_at=TS, slots=4) == {"A": .25, "B": .25}
    with pytest.raises(ValueError, match="not known"):
        rank_targets([Score("A", 1, "2026-09-02T00:00:00Z")], decision_at=TS, slots=1)
    with pytest.raises(ValueError):
        rank_targets(scores + scores, decision_at=TS, slots=1)


def test_opposing_strategies_net_before_account_and_unchanged_no_churn():
    assert combine_targets({"long": {"A": 1}, "short": {"A": -1}},
                           {"long": .5, "short": .5}) == {}
    plan = delta_orders(targets={"A": .5}, quantities={"A": 5}, marks={"A": 100},
                        equity=1000, fee_rate=.001)
    assert plan["orders"] == {} and plan["estimated_fee"] == 0


def test_post_cost_budget_and_partial_fill_residual():
    plan = delta_orders(targets={"A": 1}, quantities={}, marks={"A": 100},
                        equity=1000, fee_rate=.001)
    assert plan["post_fee_equity"] == pytest.approx(1000/1.001)
    a = LinearAccount(1000)
    a.apply(fill("half", plan["orders"]["A"] / 2, 100))
    rest = delta_orders(targets={"A": 1}, quantities={"A": a.positions["A"]["quantity"]},
                        marks={"A": 100}, equity=a.equity, fee_rate=.001)
    assert rest["orders"]["A"] == pytest.approx(plan["orders"]["A"] / 2)
    a.apply(fill("rest", rest["orders"]["A"], 100))
    assert a.equity == pytest.approx(a.gross)


def test_signed_targets_and_single_net_cash_account():
    target = combine_targets({"trend": {"A": 1}, "hedge": {"A": -.5, "B": .5}},
                             {"trend": .6, "hedge": .4})
    assert target == pytest.approx({"A": .4, "B": .2})
    a = LinearAccount(1000)
    plan = delta_orders(targets=target, quantities={}, marks={"A": 100, "B": 50},
                        equity=a.equity, fee_rate=.001)
    for s, q in plan["orders"].items():
        a.apply(fill(s, q, {"A": 100, "B": 50}[s], symbol=s, marks={"A": 100, "B": 50}))
    assert a.equity == pytest.approx(plan["post_fee_equity"])
    assert a.gross == pytest.approx(.6 * a.equity)
    with pytest.raises(ValueError, match="budgets"):
        combine_targets({"a": {}, "b": {}}, {"a": .7, "b": .7})


def test_rebalance_releases_margin_before_opening_next_asset():
    a = LinearAccount(1000)
    a.apply(fill("old", 10, 100, 0, symbol="B"))
    plan = delta_orders(targets={"A": 1}, quantities={"B": 10}, marks={"A": 100, "B": 100},
                        equity=a.equity, fee_rate=.001)
    assert [x["symbol"] for x in plan["execution_sequence"]] == ["B", "A"]
    for i, order in enumerate(plan["execution_sequence"]):
        a.apply(fill(str(i), order["quantity"], 100, symbol=order["symbol"], marks={"A": 100, "B": 100}))
    assert a.equity == pytest.approx(plan["post_fee_equity"])
    assert set(a.positions) == {"A"}
