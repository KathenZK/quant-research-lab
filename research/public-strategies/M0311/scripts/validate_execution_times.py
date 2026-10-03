"""Native5m trade time bounds and explicit signal delay validation."""

import argparse
import collections
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def audit(root):
    checks = {}
    for case in ["base", "fee0", "fee20", "delay2", "buyhold"]:
        with (Path(root) / f"{case}-trades.csv").open() as f:
            trades = list(csv.DictReader(f))
        for t in trades:
            op = dt(t["bar_open_utc"])
            lo = dt(t["execution_earliest_utc"])
            hi = dt(t["execution_latest_utc"])
            assert op == lo <= hi < op + timedelta(minutes=5)
            assert t["execution_time_basis"] == "native_5m_open_proxy"
            if t["signal_close_utc"]:
                signal = dt(t["signal_close_utc"])
                assert signal < lo
                assert (lo - signal).total_seconds() == (
                    300 if case == "delay2" else 0
                ) + 0.001
            if t["phase"] in ["open", "open_gap"]:
                assert lo == hi == dt(t["execution_time_utc"])
            else:
                assert not t["execution_time_utc"]
        checks[case] = {
            "fills": len(trades),
            "time_bounds_and_delay": "PASS",
            "sell_reasons": dict(
                collections.Counter(t["reason"] for t in trades if t["side"] == "SELL")
            ),
        }
    return {
        "id": "M0311",
        "status": "PASS",
        "checks": checks,
        "intrabar_exact_time_claim": False,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--results", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    with Path(a.output).open("x") as f:
        json.dump(audit(a.results), f, indent=2)
        f.write("\n")
