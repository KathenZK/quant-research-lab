"""Independent stdlib event notional, phase and native5m timestamp audit; no engine import."""

import argparse
import csv
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path

D = Decimal
ROOT = Path(__file__).resolve().parents[1]


def close(actual, expected):
    a, b = D(str(actual)), D(str(expected))
    assert a.is_finite() and b.is_finite()
    assert a == 0 if b == 0 else abs(a - b) <= abs(b) * D("1e-9"), (a, b)


def ms(value):
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def rows(path):
    with Path(path).open() as f:
        return list(csv.DictReader(f))


def audit(inputpath, resultpath):
    s = json.loads((ROOT / "specs/protocol.json").read_text())
    bars = rows(inputpath)
    result = {}
    assert (
        not s["execution"]["open_execution_overrides"]
        and not s["execution"]["intrabar_execution_latest_overrides"]
    )
    for case in s["cases"]:
        events = rows(Path(resultpath) / (case["name"] + "-trades.csv"))
        entry = None
        opened = None
        fee = D(case["fee_bps"]) / 10000
        for k, t in enumerate(events, 1):
            i = int(t["bar_index"])
            bar = bars[i]
            op = int(bar["open_time"])
            end = int(bar["close_time"])
            raw = D(bar["open"])
            reference = D(t["reference_price"])
            assert int(t["trade_id"]) == k and ms(t["bar_open_utc"]) == op
            close(t["notional"], D(t["quantity"]) * D(t["fill_price"]))
            close(t["fee"], D(t["notional"]) * fee)
            if t["reason"] in ["entry_signal", "exit_signal"]:
                assert t["phase"] == "open"
                close(reference, raw)
                prior = i - case["delay_bars"]
                assert int(t["signal_bar_index"]) == prior and ms(
                    t["signal_close_utc"]
                ) == int(bars[prior]["close_time"])
                assert (
                    op - int(bars[prior]["close_time"])
                    == (case["delay_bars"] - 1) * 300000 + 1
                )
            else:
                assert entry is not None and t["side"] == "SELL"
                elapsed = (op - opened) // 60000
                key = max(int(x) for x in s["risk"]["minimal_roi"] if int(x) <= elapsed)
                stop = entry * (1 + D(str(s["risk"]["stoploss"])))
                target = (
                    entry
                    * (1 + fee)
                    * (1 + D(str(s["risk"]["minimal_roi"][str(key)])))
                    / (1 - fee)
                )
                expected = (
                    "open_gap" if raw <= stop or raw > target else "intrabar_unknown"
                )
                assert t["phase"] == expected
                close(
                    reference,
                    raw
                    if expected == "open_gap"
                    else (stop if t["reason"] == "stoploss" else target),
                )
                assert t["reason"] in ["stoploss", "roi"]
                assert not t["signal_bar_index"] and not t["signal_close_utc"]
            assert t["execution_time_basis"] == "native_5m_open_proxy"
            assert ms(t["execution_earliest_utc"]) == op
            if t["phase"] in ["open", "open_gap"]:
                assert (
                    ms(t["execution_latest_utc"]) == op
                    and ms(t["execution_time_utc"]) == op
                )
            else:
                assert (
                    not t["execution_time_utc"] and ms(t["execution_latest_utc"]) == end
                )
            if t["side"] == "BUY":
                assert entry is None
                entry = D(t["fill_price"])
                opened = op
            else:
                entry = None
                opened = None
        result[case["name"]] = {
            "events": len(events),
            "notional_fees_phase_and_time": "PASS",
        }
    return {
        "id": s["record_id"],
        "status": "PASS",
        "method": "Independent stdlib/Decimal event field audit, separate from shared account and oracle; exact phase/time plus nonzero-relative1e-9 notional",
        "intrabar_exact_time_claim": False,
        "cases": result,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--results", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    with Path(a.output).open("x") as f:
        json.dump(audit(a.input, a.results), f, indent=2)
        f.write("\n")
