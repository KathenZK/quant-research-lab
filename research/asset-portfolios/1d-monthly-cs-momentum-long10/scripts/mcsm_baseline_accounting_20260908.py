"""Pure, fail-closed accounting for a fixed-quantity linear USDT-perp baseline.

No market data, symbol selection, or execution-price assumptions live here. The
caller must establish tradability, timestamp ordering, actual funding marks,
contract identities, and terminal-settlement provenance before supplying them.
Reference-price execution PnL and explicit cash slippage are separate: slippage
is never also embedded in a synthetic fill price. This is an accounting engine,
not a margin/liquidation, exchange precision, or capacity simulation.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any, Mapping


class AccountingError(ValueError):
    """An event cannot be accounted for without inventing missing information."""


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise AccountingError(f"{label}: boolean is not a numeric observation")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AccountingError(f"{label}: missing or invalid numeric observation") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise AccountingError(f"{label}: expected {'positive ' if positive else ''}finite value")
    return result


def _time(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AccountingError("timestamp: invalid ISO timestamp") from exc
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AccountingError("timestamp: an explicit timezone is required")
    try:
        result = value.astimezone(timezone.utc)
        if not math.isfinite(result.timestamp()):
            raise ValueError("nonfinite timestamp")
    except (ValueError, TypeError, OverflowError) as exc:
        raise AccountingError("timestamp: invalid timestamp") from exc
    return result


def _symbol(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountingError("symbol: nonempty contract identity is required")
    return value


@dataclass
class Position:
    quantity: float
    entry_price: float
    mark_price: float
    mark_timestamp: datetime


class LinearPerpAccount:
    """Long-only perpetual account with atomic event application.

    ``rebalance`` targets positive weights summing to one (or ``{}`` for cash),
    at one-times *post-cost* equity. Same-name exposure is net-adjusted rather
    than closed and reopened. All quantities then remain fixed until another
    rebalance or verified terminal close; funding is cash, not reinvestment.

    Event order at an equal timestamp is explicitly the caller's responsibility.
    A funding event updates its own contract mark; other contract marks retain
    their observation times. ``all_marks_at_event_time`` flags whether an event
    snapshot is a simultaneous full-account valuation. Call ``mark`` with all
    held contracts to obtain one. Missing event observations raise and leave
    the complete account, duplicate guards, and event ledger unchanged.
    """

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        fee_rate: float = 0.001,
        slippage_rate: float = 0.0004,
    ) -> None:
        self.initial_cash = _number(initial_cash, "initial_cash", positive=True)
        self.fee_rate = self._rate(fee_rate, "fee_rate")
        self.slippage_rate = self._rate(slippage_rate, "slippage_rate")
        if self.fee_rate + self.slippage_rate >= 1:
            raise AccountingError("fee plus slippage must be less than one")
        self.cash = self.initial_cash
        self.realized_price_pnl = 0.0
        self.funding_pnl = 0.0
        self.fees = 0.0
        self.slippage = 0.0
        self.positions: dict[str, Position] = {}
        self.ledger: list[dict[str, Any]] = []
        self.last_timestamp: datetime | None = None
        self._funding_keys: set[tuple[datetime, str, str]] = set()

    @staticmethod
    def _rate(value: Any, label: str) -> float:
        result = _number(value, label)
        if result < 0:
            raise AccountingError(f"{label}: cannot be negative")
        return result

    @staticmethod
    def _prices(prices: Mapping[str, float], required: set[str]) -> dict[str, float]:
        if not isinstance(prices, Mapping):
            raise AccountingError("prices: a symbol-to-observation mapping is required")
        missing = required.difference(prices)
        if missing:
            raise AccountingError(f"missing prices for {sorted(missing)}")
        return {
            _symbol(symbol): _number(price, f"price[{symbol}]", positive=True)
            for symbol, price in prices.items()
        }

    def _event_time(self, value: Any) -> datetime:
        timestamp = _time(value)
        if self.last_timestamp is not None and timestamp < self.last_timestamp:
            raise AccountingError("events must be nondecreasing in timestamp")
        return timestamp

    def snapshot(self) -> dict[str, Any]:
        """Return a detached, JSON-friendly accounting snapshot, without mutation."""
        unrealized = math.fsum(
            p.quantity * (p.mark_price - p.entry_price) for p in self.positions.values()
        )
        equity = self.cash + unrealized
        price_pnl = self.realized_price_pnl + unrealized
        expected_cash = (
            self.initial_cash + self.realized_price_pnl + self.funding_pnl
            - self.fees - self.slippage
        )
        expected_equity = (
            self.initial_cash + price_pnl + self.funding_pnl - self.fees - self.slippage
        )
        return {
            "timestamp": self.last_timestamp.isoformat() if self.last_timestamp else None,
            "cash": self.cash,
            "realized_price_pnl": self.realized_price_pnl,
            "unrealized_price_pnl": unrealized,
            "price_pnl": price_pnl,
            "funding_pnl": self.funding_pnl,
            "fees": self.fees,
            "slippage": self.slippage,
            "equity": equity,
            "gross_notional": math.fsum(p.quantity * p.mark_price for p in self.positions.values()),
            "cash_identity_error": self.cash - expected_cash,
            "equity_identity_error": equity - expected_equity,
            "all_marks_at_event_time": all(
                p.mark_timestamp == self.last_timestamp for p in self.positions.values()
            ),
            "positions": {
                s: {
                    "quantity": p.quantity,
                    "entry_price": p.entry_price,
                    "mark_price": p.mark_price,
                    "mark_timestamp": p.mark_timestamp.isoformat(),
                    "unrealized_price_pnl": p.quantity * (p.mark_price - p.entry_price),
                }
                for s, p in sorted(self.positions.items())
            },
        }

    def _assert_account(self) -> dict[str, Any]:
        snap = self.snapshot()
        for field in (
            "cash", "realized_price_pnl", "unrealized_price_pnl", "price_pnl",
            "funding_pnl", "fees", "slippage", "equity", "gross_notional",
        ):
            _number(snap[field], field)
        if snap["equity"] <= 0:
            raise AccountingError("equity is nonpositive; continuation is prohibited")
        for symbol, p in self.positions.items():
            _number(p.quantity, f"quantity[{symbol}]", positive=True)
            _number(p.entry_price, f"entry_price[{symbol}]", positive=True)
            _number(p.mark_price, f"mark_price[{symbol}]", positive=True)
        tolerance = max(1e-8, abs(snap["equity"]) * 1e-11)
        if abs(snap["cash_identity_error"]) > tolerance or abs(snap["equity_identity_error"]) > tolerance:
            raise AccountingError("cash/equity attribution identity failed")
        return snap

    def _commit(self, candidate: LinearPerpAccount, timestamp: datetime,
                event: str, details: dict[str, Any], *,
                funding_key: tuple[datetime, str, str] | None = None) -> dict[str, Any]:
        before = self.snapshot()
        candidate.last_timestamp = timestamp
        after = candidate._assert_account()
        row = {
            "event_id": len(self.ledger),
            "event": event,
            **after,
            "equity_before": before["equity"],
            "event_price_pnl": after["price_pnl"] - before["price_pnl"],
            "event_funding_pnl": after["funding_pnl"] - before["funding_pnl"],
            "event_fees": after["fees"] - before["fees"],
            "event_slippage": after["slippage"] - before["slippage"],
            "equity_change": after["equity"] - before["equity"],
            "details": details,
        }
        row["event_identity_error"] = row["equity_change"] - (
            row["event_price_pnl"] + row["event_funding_pnl"]
            - row["event_fees"] - row["event_slippage"]
        )
        if abs(row["event_identity_error"]) > max(1e-8, abs(after["equity"]) * 1e-11):
            raise AccountingError("event attribution identity failed")
        # Validation is complete before touching shared history or duplicate
        # guards. Append in O(1), never recopy years of ledger or funding keys.
        detached_row = deepcopy(row)
        candidate.ledger = self.ledger
        candidate.ledger.append(detached_row)
        if funding_key is not None:
            candidate._funding_keys.add(funding_key)
        self.__dict__.update(candidate.__dict__)
        return deepcopy(row)

    def _candidate(self) -> LinearPerpAccount:
        candidate = LinearPerpAccount(self.initial_cash, self.fee_rate, self.slippage_rate)
        for field in ("cash", "realized_price_pnl", "funding_pnl", "fees", "slippage", "last_timestamp"):
            setattr(candidate, field, getattr(self, field))
        candidate.positions = deepcopy(self.positions)
        candidate._funding_keys = self._funding_keys
        return candidate

    def mark(self, timestamp: Any, prices: Mapping[str, float]) -> dict[str, Any]:
        """Mark every held contract; an omitted, zero, or nonfinite mark is fatal."""
        ts = self._event_time(timestamp)
        observed = self._prices(prices, set(self.positions))
        candidate = self._candidate()
        for symbol, p in candidate.positions.items():
            p.mark_price, p.mark_timestamp = observed[symbol], ts
        return self._commit(candidate, ts, "mark", {"prices": observed})

    def rebalance(self, timestamp: Any, targets: Mapping[str, float],
                  prices: Mapping[str, float]) -> dict[str, Any]:
        """Net trade into specified post-cost equity weights, without daily resets."""
        ts = self._event_time(timestamp)
        if not isinstance(targets, Mapping):
            raise AccountingError("targets: a symbol-to-weight mapping is required")
        weights = {
            _symbol(s): _number(w, f"weight[{s}]", positive=True) for s, w in targets.items()
        }
        if weights and not math.isclose(math.fsum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise AccountingError("nonempty target weights must sum to one")
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
        if weights and not math.isclose(after["gross_notional"], after["equity"], rel_tol=1e-11, abs_tol=1e-8):
            raise AccountingError("post-cost gross target is not one-times equity")
        return self._commit(candidate, ts, "rebalance", {
            "targets": weights, "prices": observed, "equity_before_costs": pre_equity,
            "solved_post_cost_equity": post_equity,
            "traded_notional": math.fsum(t["traded_notional"] for t in trades),
            "trades": trades,
        })

    def funding(self, timestamp: Any, symbol: str, rate: float,
                mark_price: float, *, rate_type: str = "Regular") -> dict[str, Any]:
        """Settle cash = -held quantity * actual event mark * signed rate.

        Regular and Special funding at the same timestamp are distinct events;
        neither may suppress the other. Unknown event types are not normalized.
        """
        ts = self._event_time(timestamp)
        symbol = _symbol(symbol)
        if not isinstance(rate_type, str) or rate_type not in {"Regular", "Special"}:
            raise AccountingError("funding rate_type must be exactly Regular or Special")
        actual_rate = _number(rate, f"funding_rate[{symbol}]")
        actual_mark = _number(mark_price, f"funding_mark[{symbol}]", positive=True)
        if symbol not in self.positions:
            raise AccountingError(f"funding contract is not held: {symbol}")
        key = (ts, symbol, rate_type)
        if key in self._funding_keys:
            raise AccountingError(f"duplicate funding event: {symbol} {rate_type} at {ts.isoformat()}")
        candidate = self._candidate()
        p = candidate.positions[symbol]
        p.mark_price, p.mark_timestamp = actual_mark, ts
        funding_cash = -p.quantity * actual_mark * actual_rate
        candidate.cash += funding_cash
        candidate.funding_pnl += funding_cash
        return self._commit(candidate, ts, "funding", {
            "symbol": symbol, "quantity": p.quantity, "rate": actual_rate,
            "rate_type": rate_type,
            "actual_mark_price": actual_mark, "funding_cash": funding_cash,
        }, funding_key=key)

    def terminal_close(self, timestamp: Any, symbol: str, settlement_price: float,
                       evidence_id: str, *, settlement_fee_rate: float,
                       settlement_slippage_rate: float = 0.0) -> dict[str, Any]:
        """Close at caller-verified official settlement; never invent a last price.

        The fee must be explicitly supplied because official terminal settlement
        is not an ordinary rebalance trade. ``evidence_id`` preserves the caller's
        provenance; its mere presence does not independently verify the source.
        This closes only the named contract and does not redistribute its capital.
        """
        ts = self._event_time(timestamp)
        symbol = _symbol(symbol)
        price = _number(settlement_price, "settlement_price", positive=True)
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            raise AccountingError("terminal settlement requires a nonempty evidence_id")
        if symbol not in self.positions:
            raise AccountingError(f"terminal contract is not held: {symbol}")
        fee_rate = self._rate(settlement_fee_rate, "settlement_fee_rate")
        slip_rate = self._rate(settlement_slippage_rate, "settlement_slippage_rate")
        if fee_rate + slip_rate >= 1:
            raise AccountingError("terminal costs must be less than one")
        candidate = self._candidate()
        p = candidate.positions.pop(symbol)
        realized = p.quantity * (price - p.entry_price)
        notional = p.quantity * price
        fee, slip = notional * fee_rate, notional * slip_rate
        candidate.realized_price_pnl += realized
        candidate.fees += fee
        candidate.slippage += slip
        candidate.cash += realized - fee - slip
        return self._commit(candidate, ts, "terminal_close", {
            "symbol": symbol, "quantity": p.quantity, "settlement_price": price,
            "evidence_id": evidence_id, "traded_notional": notional,
            "settlement_fee_rate": fee_rate, "settlement_slippage_rate": slip_rate,
            "realized_price_pnl": realized, "fee": fee, "slippage": slip,
        })
