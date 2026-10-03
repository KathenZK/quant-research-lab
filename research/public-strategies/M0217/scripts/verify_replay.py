"""Independent Decimal accounting and causality checks; no production imports."""
import argparse
import csv
from decimal import Decimal, getcontext
import hashlib
import importlib.util
import json
from pathlib import Path

getcontext().prec = 40
FAMILY = Path(__file__).resolve().parents[1]
D = Decimal


def read_csv(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def verify(input_path, results):
    assert hashlib.sha256(input_path.read_bytes()).hexdigest() == "48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5"
    raw = read_csv(input_path)
    errors = []
    checked = 0
    max_error = 0.0

    def near(actual, expected):
        nonlocal checked, max_error
        error = abs(float(actual) - float(expected))
        max_error = max(max_error, error)
        assert error <= 1e-7 + abs(float(expected)) * 1e-11, (actual, expected)
        checked += 1

    for name, fee in (("base", D(".0008")), ("fee0", D("0")), ("fee20", D(".002")), ("buy_hold", D(".0008"))):
        nav = read_csv(results / f"{name}-nav.csv")
        trades = read_csv(results / f"{name}-trades.csv")
        wealth = D(100000)
        peak = wealth
        cash = wealth
        qty = D(0)
        j = 0
        assert len(nav) == 731
        for n, row in enumerate(raw[31:]):
            previous = raw[30 + n]
            level = D(previous["close"]) + D(".8") * (D(previous["high"]) - D(previous["low"]))
            triggered = n == 0 if name == "buy_hold" else D(row["high"]) >= level
            if triggered:
                price = (D(row["open"]) if name == "buy_hold" else max(D(row["open"]), level)) * D("1.0002")
                notional = wealth * D(".95")
                qty = notional / price
                charge = notional * fee
                cash = wealth - notional - charge
                t = trades[j]
                assert t["side"] == "BUY" and t["date"] == nav[n]["date"]
                for key, expected in (("quantity", qty), ("price", price), ("fee", charge), ("cash_after", cash), ("position_after", qty)):
                    near(t[key], expected)
                j += 1
                if name != "buy_hold":
                    sell = D(row["close"]) * D(".9998")
                    proceeds = qty * sell
                    charge = proceeds * fee
                    # Independent multiplicative daily return identity.
                    wealth *= D(".05") - D(".95") * fee + D(".95") * sell / price * (1 - fee)
                    t = trades[j]
                    assert t["side"] == "SELL" and t["date"] == nav[n]["date"]
                    for key, expected in (("quantity", qty), ("price", sell), ("fee", charge), ("cash_after", wealth), ("position_after", 0)):
                        near(t[key], expected)
                    j += 1
                    qty = D(0)
                    cash = wealth
            if name == "buy_hold":
                wealth = cash + qty * D(row["close"])
            peak = max(peak, wealth)
            for key, expected in (("equity", wealth), ("cash", cash), ("quantity", qty), ("drawdown", wealth / peak - 1)):
                near(nav[n][key], expected)
            assert (nav[n]["triggered"] == "True") == triggered
        assert j == len(trades)
        assert not errors

    module_spec = importlib.util.spec_from_file_location("m0217_replay", FAMILY / "scripts/run_replay.py")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    config = json.loads((FAMILY / "specs/M0217-first-replay.json").read_text())
    rows = module.load(input_path)
    baseline, bt = module.run(rows, config)
    changed = [dict(r) for r in rows]
    for row in changed:
        if row["date"] >= "2024-07-01":
            for field in ("open", "high", "low", "close"):
                row[field] *= 1.7
    mutated, mt = module.run(changed, config)
    assert [r for r in baseline if r["date"] < "2024-07-01"] == [r for r in mutated if r["date"] < "2024-07-01"]
    assert [r for r in bt if r["date"] < "2024-07-01"] == [r for r in mt if r["date"] < "2024-07-01"]
    # Exact threshold, no-trigger, and gap-through cases isolate execution semantics.
    previous = dict(date="2022-12-31", open=100., high=110., low=90., close=100.)
    current = dict(date="2023-01-01", open=100., high=116., low=99., close=112.)
    _, fills = module.run([previous, current], config)
    assert len(fills) == 2 and fills[0]["price"] == 116 * 1.0002
    current["high"] = 115.99
    _, fills = module.run([previous, current], config)
    assert not fills
    current.update(open=120., high=125., low=119., close=121.)
    _, fills = module.run([previous, current], config)
    assert fills[0]["price"] == 120 * 1.0002
    return dict(status="PASS", independent_method="Decimal 40-digit multiplicative returns and separate cash ledger", configurations=4, daily_rows=2924, numeric_comparisons=checked, max_absolute_difference=max_error, future_perturbation="PASS: prices from 2024-07-01 multiplied by 1.7; all earlier NAV/trades identical", execution_edge_cases=3, original_rule_fidelity="HYPOTHESIS", strict_reproduction=False)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = verify(a.input, a.results)
    with a.output.open("x") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(json.dumps(result))
