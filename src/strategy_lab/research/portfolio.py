"""Offline score -> budgeted net targets -> actual-position delta orders."""
from __future__ import annotations

from dataclasses import dataclass
from .accounting import number, utc


@dataclass(frozen=True)
class Score:
    symbol: str
    value: float
    available_at: str


def rank_targets(scores: list[Score], *, decision_at: str, slots: int,
                 gross_budget: float = 1.0) -> dict[str, float]:
    """Fixed-capacity equal-weight long baseline; unused slots remain cash.

    Universe admission and feature availability evidence belong to the caller's
    frozen input contract; this adapter rejects future scores but cannot prove
    that a historical publication timestamp supplied by a caller is genuine.
    """
    decision = utc(decision_at)
    budget = number(gross_budget, nonnegative=True)
    if type(slots) is not int or slots <= 0 or budget > 1:
        raise ValueError("positive slots and unlevered budget required")
    seen = set()
    for s in scores:
        if not isinstance(s.symbol, str) or not s.symbol or s.symbol in seen:
            raise ValueError("missing/duplicate symbol")
        seen.add(s.symbol)
        number(s.value)
        if utc(s.available_at) > decision:
            raise ValueError("score not known at decision")
    return {s.symbol: budget / slots for s in sorted(scores, key=lambda x: (-x.value, x.symbol))[:slots]}


def combine_targets(strategies: dict[str, dict[str, float]], budgets: dict[str, float]) -> dict[str, float]:
    if strategies.keys() != budgets.keys():
        raise ValueError("each strategy needs a capital budget")
    if sum(number(b, nonnegative=True) for b in budgets.values()) > 1 + 1e-12:
        raise ValueError("capital budgets exceed one")
    net = {}
    for name, target in strategies.items():
        if any(not isinstance(s, str) or not s for s in target):
            raise ValueError("invalid target symbol")
        if sum(abs(number(w)) for w in target.values()) > 1 + 1e-12:
            raise ValueError("strategy gross target exceeds its budget")
        for s, w in target.items():
            net[s] = net.get(s, 0.0) + budgets[name] * w
    return {s: w for s, w in net.items() if w != 0}


def delta_orders(*, targets: dict[str, float], quantities: dict[str, float],
                 marks: dict[str, float], equity: float, fee_rate: float,
                 max_gross: float = 1.0) -> dict:
    """Solve post-fee target equity and charge only actual net turnover.

    Assumes all proposed fills at these marks. Replan after partial fills or price
    changes. No funding estimate, slippage forecast, tick/lot or capacity model.
    """
    e = number(equity, positive=True)
    fee = number(fee_rate, nonnegative=True)
    cap = number(max_gross, positive=True)
    if fee >= 1 or fee * cap >= 1:
        raise ValueError("fee/gross combination not contractive")
    names = sorted(targets.keys() | quantities.keys())
    if any(not isinstance(s, str) or not s for s in names):
        raise ValueError("invalid symbol")
    prices = {s: number(marks[s], positive=True) for s in names}
    w = {s: number(targets.get(s, 0)) for s in names}
    current = {s: number(quantities.get(s, 0)) * prices[s] for s in names}
    if sum(abs(v) for v in w.values()) > cap + 1e-12:
        raise ValueError("target gross cap exceeded")
    def cost(after):
        return fee * sum(abs(w[s] * after - current[s]) for s in names)
    if cost(0) >= e:
        raise ValueError("equity cannot finance rebalance fees")
    lo, hi = 0.0, e
    for _ in range(100):
        mid = (lo + hi) / 2
        if mid + cost(mid) > e:
            hi = mid
        else:
            lo = mid
    after = (lo + hi) / 2
    deltas = {s: (w[s] * after - current[s]) / prices[s] for s in names}
    reductions, increases = [], []
    for s, delta in deltas.items():
        old = current[s] / prices[s]
        reduction = (-1 if delta < 0 else 1) * min(abs(delta), abs(old)) if old * delta < 0 else 0.0
        for amount, phase, bucket in [(reduction, "reduce", reductions),
                                      (delta - reduction, "increase", increases)]:
            if abs(amount * prices[s]) > 1e-10:
                bucket.append({"symbol": s, "quantity": amount, "phase": phase})
    return {"post_fee_equity": after, "estimated_fee": cost(after),
            "orders": {s: q for s, q in deltas.items() if abs(q * prices[s]) > 1e-10},
            "execution_sequence": reductions + increases,
            "execution_assumption": "all fills at supplied contemporaneous marks"}
