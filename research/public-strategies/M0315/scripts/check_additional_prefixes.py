"""Supplementary feature causality across2024; existing configs, no optimization."""

import argparse
import json
from pathlib import Path
import numpy as np
from run_replay import load_input, features

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    spec = json.loads((ROOT / "specs/M0315-first-replay.json").read_text())
    d = load_input(a.input, spec)
    full = features(d)
    cuts = [10000, 20000, 50000, 90000, 114335]
    for cut in cuts:
        pref = features(d.iloc[:cut].copy())
        mod = d.copy()
        mod.loc[cut:, ["open", "high", "low", "close"]] *= 3
        changed = features(mod)
        for c in ["ma12", "ma26", "umacd", "entry_signal", "exit_signal"]:
            assert np.array_equal(pref[c], full.iloc[:cut][c], equal_nan=True)
            assert np.array_equal(
                changed.iloc[:cut][c], full.iloc[:cut][c], equal_nan=True
            )
    with Path(a.output).open("x") as f:
        json.dump(
            {
                "id": "M0315",
                "status": "PASS",
                "cuts": cuts,
                "method": "exact prefix and futureOHLCx3 feature/signal array equality",
                "new_strategy_trials": 0,
                "reason": "Frozen account-prefix probes only cover early2024; supplemental feature probes span remaining year",
            },
            f,
            indent=2,
        )
        f.write("\n")
