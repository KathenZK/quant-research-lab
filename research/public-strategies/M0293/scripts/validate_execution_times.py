#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Audit signal/execution times against known March24 suspension; no new trials."""

import argparse
import collections
import csv
from datetime import datetime
import json
from pathlib import Path


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def audit(result_dir):
    result_dir = Path(result_dir)
    checks = {}
    for name in ["base", "fee0", "fee20", "delay2", "buyhold"]:
        with (result_dir / f"{name}-trades.csv").open() as stream:
            trades = list(csv.DictReader(stream))
        near = [row for row in trades if row["bar_open_utc"].startswith("2023-03-24")]
        for row in trades:
            earliest, latest = (
                dt(row["execution_earliest_utc"]),
                dt(row["execution_latest_utc"]),
            )
            assert earliest <= latest
            assert not (
                earliest < dt("2023-03-24T14:00:00Z")
                and latest >= dt("2023-03-24T11:27:00Z")
            )
            if row["signal_close_utc"]:
                assert dt(row["signal_close_utc"]) < earliest
        checks[name] = {
            "fills": len(trades),
            "march24_fills": len(near),
            "no_timestamp_bounds_overlap_known_halt": True,
            "all_signal_closes_before_execution_lower_bound": True,
        }
        with (result_dir / f"{name}-daily-nav.csv").open() as stream:
            daily = list(csv.DictReader(stream))
        previous = 100000
        years = {}
        for year in ["2023", "2024"]:
            end = float(
                [row for row in daily if row["date"].startswith(year)][-1]["equity"]
            )
            years[year] = end / previous - 1
            previous = end
        checks[name]["descriptive_calendar_returns"] = years
        checks[name]["sell_reasons"] = dict(
            collections.Counter(
                row["reason"] for row in trades if row["side"] == "SELL"
            )
        )
    return {"id": "M0293", "status": "PASS", "checks": checks, "new_strategy_trials": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with Path(args.output).open("x") as stream:
        json.dump(audit(args.results), stream, indent=2)
        stream.write("\n")
