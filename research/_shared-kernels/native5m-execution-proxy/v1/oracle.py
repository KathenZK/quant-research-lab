#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decimal event replay and metric recomputation, independent of port engine.
Signals are separately checked against the original class by compare_original.py.
"""

import csv
from datetime import datetime
from decimal import Decimal, getcontext
import hashlib
import json
import math
from pathlib import Path
import statistics

getcontext().prec = 40
D = Decimal
ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    with Path(path).open() as stream:
        return list(csv.DictReader(stream))


def close(actual, expected):
    if actual is None or expected is None:
        assert actual is expected
        return
    observed, reference = D(str(actual)), D(str(expected))
    assert observed.is_finite() and reference.is_finite(), (actual, expected)
    if reference == 0:
        assert observed == 0, (actual, expected)
    else:
        assert abs(observed - reference) <= abs(reference) * D("1e-9"), (
            actual,
            expected,
        )


def validate(input_path, result_path, spec_path):
    result_path = Path(result_path)
    spec_path = Path(spec_path)
    spec = json.loads(spec_path.read_text())
    assert D(str(spec["execution"]["initial_cash"])) == D("100000")
    assert D(str(spec["execution"]["slippage_bps"])) == D("2")
    assert D(str(spec["execution"]["cash_budget_fraction"])) == D("0.95")
    assert (
        hashlib.sha256(Path(input_path).read_bytes()).hexdigest()
        == spec["input"]["sha256"]
    )
    summary = json.loads((result_path / "summary.json").read_text())
    assert (
        summary["protocol_sha256"] == hashlib.sha256(spec_path.read_bytes()).hexdigest()
    )
    bars, signals = rows(input_path), rows(result_path / "signals.csv")
    assert len(bars) == len(signals) == spec["input"]["expected_rows"]

    def as_time(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    first = int(
        (
            as_time(spec["evaluation"]["start"]) - as_time(spec["input"]["start"])
        ).total_seconds()
        // 300
    )
    stop = int(
        (
            as_time(spec["evaluation"]["end_exclusive"])
            - as_time(spec["input"]["start"])
        ).total_seconds()
        // 300
    )
    results = {}
    for case in spec["cases"]:
        name = case["name"]
        events = rows(result_path / f"{name}-trades.csv")
        nav = rows(result_path / f"{name}-nav.csv")
        daily = rows(result_path / f"{name}-daily-nav.csv")
        assert len(nav) == stop - first and len(daily) == (stop - first) // 288
        cash, quantity, cost, entry, entry_time = D(100000), D(0), D(0), D(0), 0
        fee, slip, frac = D(case["fee_bps"]) / 10000, D(2) / 10000, D("0.95")
        event_index, total_fees, roundtrips = 0, D(0), []
        equities, daily_eq, holds = [D(100000)], [D(100000)], 0
        for index in range(first, stop):
            bar = bars[index]
            opened = int(bar["open_time"])
            effective = (
                spec["execution"]["open_execution_overrides"]
                .get(str(opened), {})
                .get("effective_open_ms", opened)
            )
            op, hi, lo, cl = (D(bar[k]) for k in ("open", "high", "low", "close"))
            prior = index - case["delay_bars"]
            ent = prior >= first and int(signals[prior]["entry_signal"]) == 1
            ext = prior >= first and int(signals[prior]["exit_signal"]) == 1
            hold = case.get("buy_hold", False)
            if hold:
                ent, ext = index == first, False
            exited = False

            def fill(side, reference, reason):
                nonlocal \
                    cash, \
                    quantity, \
                    cost, \
                    entry, \
                    entry_time, \
                    event_index, \
                    total_fees, \
                    exited
                assert event_index < len(events), f"MISSING_EVENT {name} {index}"
                actual = events[event_index]
                assert (
                    int(actual["bar_index"]) == index
                    and actual["side"] == side
                    and actual["reason"] == reason
                )
                price = reference * (1 + slip if side == "BUY" else 1 - slip)
                if side == "BUY":
                    assert quantity == 0
                    budget = frac * cash
                    quantity = budget / (price * (1 + fee))
                    size = quantity
                    notional = quantity * price
                    charge = notional * fee
                    cash -= notional + charge
                    cost, entry, entry_time = notional + charge, price, effective
                else:
                    assert quantity > 0
                    size = quantity
                    notional = size * price
                    charge = notional * fee
                    cash += notional - charge
                    quantity = D(0)
                    roundtrips.append((notional - charge) / cost - 1)
                    exited = True
                total_fees += charge
                for field, value in [
                    ("reference_price", reference),
                    ("fill_price", price),
                    ("quantity", size),
                    ("fee", charge),
                    ("cash_after", cash),
                    ("quantity_after", quantity),
                ]:
                    close(actual[field], value)
                if reason in ("entry_signal", "exit_signal"):
                    assert int(actual["signal_bar_index"]) == prior
                    assert int(bars[prior]["close_time"]) < effective
                event_index += 1

            signal_profit_ok = (
                (
                    not spec["execution"].get("exit_profit_only", False)
                    or op * (1 - fee) / (entry * (1 + fee)) - 1
                    > D(str(spec["execution"].get("exit_profit_offset", 0)))
                )
                if quantity
                else False
            )
            if quantity and ext and not ent and signal_profit_ok:
                fill("SELL", op, "exit_signal")
            if not quantity and ent and not ext and not exited:
                fill("BUY", op, "buy_hold" if hold else "entry_signal")
            if quantity and not hold:
                elapsed = (effective - entry_time) // 60000
                key = max(
                    int(k) for k in spec["risk"]["minimal_roi"] if int(k) <= elapsed
                )
                roi = D(str(spec["risk"]["minimal_roi"][str(key)]))
                target = entry * (1 + fee) * (1 + roi) / (1 - fee)
                floor = entry * (1 + D(str(spec["risk"]["stoploss"])))
                if op <= floor:
                    fill("SELL", op, "stoploss")
                elif op > target:
                    fill("SELL", op, "roi")
                elif lo <= floor:
                    fill("SELL", floor, "stoploss")
                elif hi > target:
                    fill("SELL", target, "roi")
            equity = cash + quantity * cl
            actual_nav = nav[index - first]
            for field, value in [
                ("cash", cash),
                ("quantity", quantity),
                ("equity", equity),
                ("nav", equity / 100000),
            ]:
                close(actual_nav[field], value)
            equities.append(equity)
            holds += int(quantity > 0)
            if (index - first + 1) % 288 == 0:
                daily_eq.append(equity)
                close(daily[(index - first) // 288]["equity"], equity)
        assert event_index == len(events), f"EXTRA_EVENTS {name}"
        m = summary["results"][name]["metrics"]
        returns = [float(b / a - 1) for a, b in zip(daily_eq, daily_eq[1:])]
        peak = equities[0]
        mdd = D(0)
        for equity in equities:
            peak = max(peak, equity)
            mdd = max(mdd, 1 - equity / peak)
        for field, value in [
            ("total_return", equities[-1] / 100000 - 1),
            ("max_drawdown", mdd),
            (
                "sharpe",
                statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(365)
                if len(returns) > 1 and statistics.stdev(returns) > 0
                else None,
            ),
            ("final_equity", equities[-1]),
            ("fees_paid", total_fees),
            ("position_bar_fraction", holds / (stop - first)),
            ("final_cash", cash),
            ("final_quantity", quantity),
        ]:
            close(m[field], value)
        assert m["trades"] == len(events) and m["round_trips"] == len(roundtrips)
        results[name] = {
            "event_rows": len(events),
            "nav_rows": len(nav),
            "daily_rows": len(daily),
            "cash_quantity_equity_and_decisions": "PASS",
            "metrics": "PASS",
        }
    return {
        "id": spec["record_id"],
        "status": "PASS",
        "method": "Independent Decimal event decisions, cash/quantity/equity identities and stdlib metric recomputation; original-source signal equality separately verified",
        "absolute_tolerance": 0,
        "relative_tolerance": 1e-9,
        "expected_zero": "exact; Decimal comparison without float underflow",
        "event_fields_checked": [
            "bar_index",
            "side",
            "reason",
            "reference_price",
            "fill_price",
            "quantity",
            "fee",
            "cash_after",
            "quantity_after",
            "signal_bar_index when signal-driven",
        ],
        "event_fields_not_independently_checked": [
            "phase",
            "effective_execution_time",
            "notional",
            "signal_available_at",
        ],
        "cases": results,
        "protocol_sha256": summary["protocol_sha256"],
        "input_sha256": summary["input_sha256"],
    }
