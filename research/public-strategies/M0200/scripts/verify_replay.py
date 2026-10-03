"""Independent Decimal signal/account ledger. Engine imported only for causality test."""

import argparse
import csv
from decimal import Decimal as D
import importlib.util
import json
import math
from pathlib import Path
from datetime import datetime, timezone


def verify(inputs, results):
    rows = list(csv.DictReader(Path(inputs).open()))
    closes = [D(r["close"]) for r in rows]
    dates = [
        datetime.fromtimestamp(int(r["open_time"]) / 1000, timezone.utc)
        .date()
        .isoformat()
        for r in rows
    ]
    gains = [max(b - a, D(0)) for a, b in zip(closes, closes[1:])]
    losses = [max(a - b, D(0)) for a, b in zip(closes, closes[1:])]
    gain, loss = sum(gains[:2]) / 2, sum(losses[:2]) / 2
    rsis = {}
    for i in range(2, len(rows)):
        if i > 2:
            gain, loss = (gain + gains[i - 1]) / 2, (loss + losses[i - 1]) / 2
        rsis[i] = (
            D(50)
            if gain == loss == 0
            else D(100)
            if loss == 0
            else 100 - 100 / (1 + gain / loss)
        )
    summary = json.loads((results / "summary.json").read_text())
    checks = {}
    for name, fee, delay, hold in [
        ("base", D(".0008"), 1, False),
        ("fee0", D(0), 1, False),
        ("fee20", D(".002"), 1, False),
        ("lag2", D(".0008"), 2, False),
        ("buyhold", D(".0008"), 1, True),
    ]:
        cash, qty = D(100000), D(0)
        pending = {}
        nav = []
        fills = []
        for i, r in enumerate(rows):
            if not "2023-08-01" <= dates[i] <= "2024-12-31":
                continue
            order = pending.pop(i, None)
            if hold and not nav:
                order = "BUY"
            if order:
                price = D(r["open"]) * (D("1.0002") if order == "BUY" else D(".9998"))
                amount = cash * D(".95") if order == "BUY" else qty * price
                size = amount / price if order == "BUY" else qty
                charge = amount * fee
                cash = (
                    cash - amount - charge if order == "BUY" else cash + amount - charge
                )
                qty = qty + size if order == "BUY" else D(0)
                fills.append((dates[i], order, size, price, charge))
            nav.append((cash, qty, cash + qty * closes[i]))
            if not hold and not pending:
                ma5 = sum(closes[i - 4 : i + 1]) / 5
                ma200 = sum(closes[i - 199 : i + 1]) / 200
                if qty == 0 and closes[i] > ma200 and closes[i] < ma5 and rsis[i] < 10:
                    pending[i + delay] = "BUY"
                elif qty > 0 and closes[i] > ma5:
                    pending[i + delay] = "SELL"
        actual = list(csv.DictReader((results / f"{name}-nav.csv").open()))
        tx = list(csv.DictReader((results / f"{name}-trades.csv").open()))
        assert len(actual) == len(nav) == 519 and len(tx) == len(fills)
        for a, e in zip(actual, nav):
            for key, n in zip(["cash", "quantity", "equity"], e):
                assert math.isclose(
                    float(a[key]), float(n), rel_tol=1e-10, abs_tol=1e-7
                )
        for a, e in zip(tx, fills):
            assert (a["date"], a["side"]) == e[:2]
            for key, n in zip(["quantity", "price", "fee"], e[2:]):
                assert math.isclose(
                    float(a[key]), float(n), rel_tol=1e-10, abs_tol=1e-7
                )
        values = [100000] + [float(n[2]) for n in nav]
        rets = [b / a - 1 for a, b in zip(values, values[1:])]
        mean = math.fsum(rets) / len(rets)
        variance = math.fsum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        peak = values[0]
        dd = 0
        for v in values:
            peak = max(peak, v)
            dd = max(dd, 1 - v / peak)
        expected = {
            "return_pct": (values[-1] / 100000 - 1) * 100,
            "max_drawdown_pct": dd * 100,
            "sharpe_daily_365": mean / math.sqrt(variance) * math.sqrt(365),
            "cagr_pct": ((values[-1] / 100000) ** (365 / len(nav)) - 1) * 100,
        }
        for k, v in expected.items():
            assert math.isclose(summary[name][k], v, rel_tol=1e-9, abs_tol=1e-8)
        checks[name] = {
            "daily_rows": len(nav),
            "fills": len(fills),
            "independent_decimal_accounting": True,
            "independent_metrics": True,
        }
    import pandas as pd

    spec = importlib.util.spec_from_file_location(
        "engine", Path(__file__).with_name("run_replay.py")
    )
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    df = pd.read_csv(inputs)
    mutated = df.copy()
    cut = 500
    for col in ["open", "high", "low", "close"]:
        mutated.loc[cut:, col] *= 1.7
    for name, fee, lag, bm in engine.CONFIGS:
        before, bt = engine.run(df, fee, lag, bm)
        after, at = engine.run(mutated, fee, lag, bm)
        bound = dates[cut]
        pd.testing.assert_frame_equal(
            before[before.date < bound], after[after.date < bound]
        )
        pd.testing.assert_frame_equal(bt[bt.date < bound], at[at.date < bound])
    return {
        "status": "PASS",
        "configurations": checks,
        "future_perturbation_pass": True,
        "independent_source_verification": False,
        "strict_reproductions": 0,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--results", required=True)
    a = p.parse_args()
    result = verify(a.input, Path(a.results))
    dest = Path(a.results) / "verification.json"
    with dest.open("x") as f:
        f.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
