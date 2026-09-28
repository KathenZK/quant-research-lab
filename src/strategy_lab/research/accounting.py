"""Small independent economic oracle for offline linear USDT contract tests.

Not an exchange simulator: no maintenance tiers, liquidation, queue or precision model.
Fills carry their actual execution price; slippage is never separately charged.
Every event supplies contemporaneous marks for all open positions. Event order at
the same timestamp is explicit (not inferred from OHLC or a funding calendar).
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math


def utc(value: str) -> str:
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return t.astimezone(timezone.utc).isoformat()


def number(value, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("finite number required")
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError("invalid number sign")
    return float(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


class LinearAccount:
    """Signed quantity/basis ledger, atomic events, and replay-verified snapshots."""

    def __init__(self, initial_cash: float, max_gross_leverage: float = 1.0):
        self.initial_cash = number(initial_cash, positive=True)
        self.max_gross_leverage = number(max_gross_leverage, positive=True)
        self.cash = self.initial_cash
        self.realized = self.fees = self.funding = 0.0
        self.positions = {}  # symbol -> {quantity, entry}
        self.events = []
        self.marks = {}
        self._ids = set()
        self._funding_keys = set()

    @property
    def equity(self):
        return self.cash + sum(p["quantity"] * (self.marks[s] - p["entry"])
                               for s, p in self.positions.items())

    @property
    def gross(self):
        return sum(abs(p["quantity"]) * self.marks[s] for s, p in self.positions.items())

    def apply(self, event: dict) -> dict:
        candidate = deepcopy(self)
        candidate._apply(deepcopy(event))
        self.__dict__.update(candidate.__dict__)
        return self.state()

    def _apply(self, event):
        kind = event.get("kind")
        fields = {"id", "ts", "kind", "marks"}
        fields |= {"symbol", "quantity", "price", "fee_rate"} if kind == "fill" else set()
        fields |= {"symbol", "rate", "settlement_type"} if kind == "funding" else set()
        if kind not in {"fill", "funding", "mark"} or set(event) != fields:
            raise ValueError("invalid event schema")
        if not isinstance(event["id"], str) or not event["id"] or event["id"] in self._ids:
            raise ValueError("missing/duplicate event id")
        event["ts"] = utc(event["ts"])
        if self.events and event["ts"] < self.events[-1]["ts"]:
            raise ValueError("events must be chronological")
        marks = event["marks"]
        if not isinstance(marks, dict) or any(not isinstance(s, str) or not s for s in marks):
            raise ValueError("invalid marks")
        self.marks = {s: number(p, positive=True) for s, p in marks.items()}
        if not self.positions.keys() <= self.marks.keys():
            raise ValueError("every open position needs a current mark")
        before_gross = self.gross
        if kind != "mark":
            s = event["symbol"]
            if not isinstance(s, str) or not s or s not in self.marks:
                raise ValueError("symbol requires a current mark")
        if kind == "fill":
            q = number(event["quantity"])
            price = number(event["price"], positive=True)
            rate = number(event["fee_rate"], nonnegative=True)
            if q == 0 or rate >= 1:
                raise ValueError("nonzero fill and fee rate below one required")
            old = self.positions.get(s, {"quantity": 0.0, "entry": price})
            oq, entry = old["quantity"], old["entry"]
            close = min(abs(oq), abs(q)) if oq * q < 0 else 0.0
            realized = close * (1 if oq > 0 else -1) * (price - entry)
            nq = oq + q
            if oq * q >= 0:
                basis = (abs(oq) * entry + abs(q) * price) / (abs(oq) + abs(q))
            else:
                basis = price if oq * nq < 0 else entry
            if nq == 0:
                self.positions.pop(s, None)
            else:
                self.positions[s] = {"quantity": nq, "entry": basis}
            fee = abs(q) * price * rate
            self.cash += realized - fee
            self.realized += realized
            self.fees += fee
            # Permit risk-reducing closes even after a loss; reject any newly
            # opened/increased leg when total initial margin is unaffordable.
            opens_risk = oq * q >= 0 or abs(q) > abs(oq)
            if opens_risk and (self.equity <= 0 or
                               self.gross > self.equity * self.max_gross_leverage + 1e-9):
                raise ValueError("insufficient initial margin")
        elif kind == "funding":
            rate = number(event["rate"])
            if event["settlement_type"] not in {"regular", "special"}:
                raise ValueError("explicit settlement type required")
            key = (event["ts"], s, event["settlement_type"])
            if key in self._funding_keys:
                raise ValueError("duplicate funding settlement")
            self._funding_keys.add(key)
            amount = -self.positions.get(s, {"quantity": 0})["quantity"] * self.marks[s] * rate
            self.cash += amount
            self.funding += amount
        self._ids.add(event["id"])
        self.events.append(event)
        if not math.isclose(self.cash, self.initial_cash + self.realized + self.funding - self.fees,
                            rel_tol=1e-12, abs_tol=1e-8):
            raise ValueError("cash identity failed")
        if not all(math.isfinite(v) for v in (self.cash, self.equity, self.gross, before_gross)):
            raise ValueError("nonfinite account")

    def state(self):
        return {"cash": self.cash, "realized": self.realized, "fees": self.fees,
                "funding": self.funding, "equity": self.equity, "gross": self.gross,
                "initial_margin": self.gross / self.max_gross_leverage,
                "margin_breached": self.equity < self.gross / self.max_gross_leverage,
                "positions": deepcopy(self.positions), "marks": dict(self.marks)}

    def snapshot(self):
        payload = {"schema": 1, "initial_cash": self.initial_cash,
                   "max_gross_leverage": self.max_gross_leverage,
                   "events": deepcopy(self.events), "state": self.state()}
        return {"payload": payload, "sha256": digest(payload)}

    @classmethod
    def restore(cls, snapshot):
        p = snapshot["payload"]
        if snapshot["sha256"] != digest(p) or p["schema"] != 1:
            raise ValueError("snapshot integrity failed")
        account = cls(p["initial_cash"], p["max_gross_leverage"])
        for event in p["events"]:
            account.apply(event)
        if account.state() != p["state"]:
            raise ValueError("snapshot economic replay failed")
        return account


def bracket_exit(*, side: int, open: float, high: float, low: float, close: float,
                 stop: float, take_profit: float) -> tuple[str, float] | None:
    """Synthetic conservative OHLC reference, not a change to any frozen strategy.

    Stop gap fills at open. If both levels touch and open is between levels,
    choose stop first. A take-profit limit receives no optimistic price improvement.
    """
    o, h, lo, c, s, tp = [number(v, positive=True) for v in (open, high, low, close, stop, take_profit)]
    if side not in {-1, 1} or not lo <= min(o, c) <= max(o, c) <= h or side * (tp - s) <= 0:
        raise ValueError("invalid OHLC/bracket")
    if side * (o - s) <= 0:
        return "stop_gap", o
    if side * (o - tp) >= 0:
        return "take_profit", tp
    if lo <= s <= h:
        return "stop", s
    if lo <= tp <= h:
        return "take_profit", tp
    return None
