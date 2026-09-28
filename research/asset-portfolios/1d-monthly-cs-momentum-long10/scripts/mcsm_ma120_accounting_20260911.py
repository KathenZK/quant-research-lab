"""Scoped partial-cash extension of frozen 20260908 accounting; original unchanged.

Only the weight-sum constraint and gross reconciliation differ in rebalance.
Baseline full-weight equivalence and an independent cash replay are mandatory.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from mcsm_baseline_accounting_20260908 import (
    AccountingError, LinearPerpAccount, Position, _number, _symbol,
)


class PartialCashAccount(LinearPerpAccount):
    def rebalance(self, timestamp: Any, targets: Mapping[str, float],
                  prices: Mapping[str, float]) -> dict[str, Any]:
        """Net trade into specified post-cost equity weights, without daily resets."""
        ts = self._event_time(timestamp)
        if not isinstance(targets, Mapping):
            raise AccountingError("targets: a symbol-to-weight mapping is required")
        weights = {
            _symbol(s): _number(w, f"weight[{s}]", positive=True) for s, w in targets.items()
        }
        if math.fsum(weights.values()) > 1.0 + 1e-12:
            raise AccountingError("target weights cannot exceed one")
        union = set(self.positions) | set(weights)
        observed = self._prices(prices, union)
        candidate = self._candidate()
        for symbol, p in candidate.positions.items():
            p.mark_price, p.mark_timestamp = observed[symbol], ts
        pre_equity = candidate._assert_account()["equity"]
        old_notional = {s: self.positions[s].quantity * observed[s] if s in self.positions else 0.0
                        for s in union}
        cost_rate = self.fee_rate + self.slippage_rate

        def turnover(equity: float) -> float:
            return math.fsum(abs(weights.get(s, 0.0) * equity - old_notional[s]) for s in union)

        if cost_rate * turnover(0.0) >= pre_equity:
            raise AccountingError("equity cannot cover the target rebalance costs")
        low, high = 0.0, pre_equity
        for _ in range(120):
            midpoint = (low + high) / 2.0
            if midpoint + cost_rate * turnover(midpoint) > pre_equity:
                high = midpoint
            else:
                low = midpoint
        post_equity = (low + high) / 2.0
        trades: list[dict[str, Any]] = []
        realized = fee = slip = 0.0
        for symbol in sorted(union):
            price = observed[symbol]
            old = candidate.positions.get(symbol)
            old_q = old.quantity if old else 0.0
            new_q = weights.get(symbol, 0.0) * post_equity / price
            delta_q = new_q - old_q
            notional = abs(delta_q) * price
            closed_q = max(0.0, old_q - new_q)
            trade_realized = closed_q * (price - old.entry_price) if old else 0.0
            if new_q > 0:
                if old is None:
                    basis = price
                elif delta_q > 0:
                    basis = (old_q * old.entry_price + delta_q * price) / new_q
                else:
                    basis = old.entry_price
                candidate.positions[symbol] = Position(new_q, basis, price, ts)
            else:
                candidate.positions.pop(symbol, None)
            trade_fee, trade_slip = notional * self.fee_rate, notional * self.slippage_rate
            realized += trade_realized
            fee += trade_fee
            slip += trade_slip
            trades.append({
                "symbol": symbol, "old_quantity": old_q, "new_quantity": new_q,
                "delta_quantity": delta_q, "reference_price": price,
                "traded_notional": notional, "closed_quantity": closed_q,
                "realized_price_pnl": trade_realized, "fee": trade_fee, "slippage": trade_slip,
            })
        candidate.realized_price_pnl += realized
        candidate.fees += fee
        candidate.slippage += slip
        candidate.cash += realized - fee - slip
        after = candidate._assert_account()
        if not math.isclose(after["equity"], post_equity, rel_tol=1e-11, abs_tol=1e-8):
            raise AccountingError("post-cost target equity reconciliation failed")
        if weights and not math.isclose(after["gross_notional"], after["equity"] * math.fsum(weights.values()), rel_tol=1e-11, abs_tol=1e-8):
            raise AccountingError("post-cost gross target differs from prescribed partial exposure")
        return self._commit(candidate, ts, "rebalance", {
            "targets": weights, "prices": observed, "equity_before_costs": pre_equity,
            "solved_post_cost_equity": post_equity,
            "traded_notional": math.fsum(t["traded_notional"] for t in trades),
            "trades": trades,
        })

