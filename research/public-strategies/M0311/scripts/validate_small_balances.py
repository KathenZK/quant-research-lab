"""Supplemental low-balance precision audit; frozen outputs unchanged, no new trials."""

import argparse
import json
import math
from pathlib import Path
import validate_independent as oracle


def close(actual, expected):
    assert math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-18), (
        actual,
        expected,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--results", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    oracle.close = close
    result = oracle.validate(a.input, a.results)
    result.update(
        absolute_tolerance=1e-18,
        relative_tolerance=1e-9,
        reason="Near-zero fee20 balances make inherited2e-7 absolute tolerance too loose; tighten absolute floor and verify relative agreement",
        new_strategy_trials=0,
    )
    with Path(a.output).open("x") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
