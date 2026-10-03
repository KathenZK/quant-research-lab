#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prefix and future-price perturbation checks; no extra strategy configurations."""

import argparse
import json
from pathlib import Path
import numpy as np
from run_replay import features, load_input, replay

ROOT = Path(__file__).resolve().parents[1]


def check(input_path):
    spec = json.loads((ROOT / "specs/M0293-first-replay.json").read_text())
    data = load_input(input_path, spec)
    full = features(data)
    results = []
    for cut in [601, 611, 624, 1500, 3000]:
        prefix = features(data.iloc[:cut].copy())
        changed = data.copy()
        changed.loc[cut:, ["open", "high", "low", "close"]] *= 3
        perturbed = features(changed)
        for column in ["entry_signal", "exit_signal"] + [
            c for c in full if c in ("ema8", "ema21", "sma48h50")
        ]:
            assert np.array_equal(
                prefix[column], full.iloc[:cut][column], equal_nan=True
            )
            assert np.array_equal(
                perturbed.iloc[:cut][column], full.iloc[:cut][column], equal_nan=True
            )
        cutoff = int(data.iloc[cut - 1].close_time) + 1
        for case in spec["cases"]:
            a = replay(full, spec, case, cutoff)
            b = replay(prefix, spec, case, cutoff)
            c = replay(perturbed, spec, case, cutoff)
            for index in (0, 1, 2):
                assert a[index].equals(b[index]) and a[index].equals(c[index])
        results.append(
            {
                "prefix_rows": cut,
                "future_price_multiplier": 3,
                "five_case_events_and_nav_unchanged": True,
            }
        )
    return {"id": "M0293", "status": "PASS", "cuts": results, "new_strategy_trials": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = check(args.input)
    with Path(args.output).open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))
