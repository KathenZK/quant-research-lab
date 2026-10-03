"""Independent Decimal ledger + fsum indicators; does not import replay engine."""

import csv
from decimal import Decimal as D
import json
import math
from pathlib import Path
import sys


def verify(inputs, results):
    rows = list(csv.DictReader(inputs.open()))
    closes = [float(r["close"]) for r in rows]
    from datetime import datetime, timezone

    dates = [
        datetime.fromtimestamp(int(r["open_time"]) / 1000, timezone.utc)
        .date()
        .isoformat()
        for r in rows
    ]
    fast = [
        None if i < 10 else math.fsum(closes[i - 10 : i + 1]) / 11
        for i in range(len(rows))
    ]
    slow = [
        None if i < 19 else math.fsum(closes[i - 19 : i + 1]) / 20
        for i in range(len(rows))
    ]
    report = {}
    for name, fee, lag, benchmark in [
        ("base", "0.0008", 1, False),
        ("fee0", "0", 1, False),
        ("fee20", "0.002", 1, False),
        ("lag2", "0.0008", 2, False),
        ("buyhold", "0.0008", 1, True),
    ]:
        cash = D(100000)
        qty = D(0)
        peak = cash
        halt = False
        pending = {}
        expected = []
        fills = []
        for i, row in enumerate(rows):
            if dates[i] < "2023-01-01":
                continue
            order = pending.pop(i, 0)
            if benchmark and not expected:
                order = 1
            if order == 1 and qty == 0:
                price = D(row["open"]) * D("1.0002")
                amount = cash * D(".95")
                qty = amount / price
                charge = amount * D(fee)
                cash -= amount + charge
                fills.append((dates[i], "BUY", float(qty), float(charge)))
            elif order == -1 and qty > 0:
                price = D(row["open"]) * D(".9998")
                charge = qty * price * D(fee)
                cash += qty * price - charge
                fills.append((dates[i], "SELL", float(qty), float(charge)))
                qty = D(0)
            total = cash + qty * D(row["close"])
            peak = max(peak, total)
            if not benchmark and D(1) - total / peak >= D(".15"):
                halt = True
            if not benchmark and not halt and i >= 21:
                up = fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]
                down = fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]
                if (up or down) and i + lag < len(rows):
                    pending[i + lag] = 1 if up else -1
            expected.append((dates[i], float(total), float(cash), float(qty), halt))
        actual = list(csv.DictReader((results / f"{name}-nav.csv").open()))
        actual_fills = list(csv.DictReader((results / f"{name}-trades.csv").open()))
        assert len(actual) == len(expected) == 731
        errors = []
        for a, e in zip(actual, expected, strict=True):
            assert a["date"] == e[0] and (a["halted"] == "True") == e[4]
            for field, value in zip(
                ["equity", "cash", "quantity"], e[1:4], strict=True
            ):
                assert math.isclose(
                    float(a[field]), value, rel_tol=1e-10, abs_tol=1e-6
                ), (name, field, a, e)
            errors.append(abs(float(a["equity"]) - e[1]))
        assert len(actual_fills) == len(fills)
        for a, e in zip(actual_fills, fills, strict=True):
            assert (a["date"], a["side"]) == e[:2]
            assert math.isclose(float(a["quantity"]), e[2], rel_tol=1e-10)
            assert math.isclose(float(a["fee"]), e[3], rel_tol=1e-10, abs_tol=1e-8)
            if not benchmark:
                assert a["signal_date"] < a["date"]
        report[name] = dict(
            status="PASS",
            nav_rows=len(actual),
            fills=len(fills),
            max_equity_difference=max(errors),
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    verify(Path(sys.argv[1]), Path(sys.argv[2]))
