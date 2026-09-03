#!/usr/bin/env python3
"""Run the repository's local governance and data-contract gates."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def _run(label: str, command: list[str]) -> bool:
    print(f"\n==> {label}", flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        print(f"FAILED: {label} (exit {result.returncode})")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run evidence, docs, data-contract, and lint gates."
    )
    parser.add_argument(
        "--governance-only",
        action="store_true",
        help="Skip data-layer tests and repository lint.",
    )
    args = parser.parse_args()

    python = sys.executable
    steps = [
        (
            "standardized parity reports",
            [python, "scripts/governance/check_parity_report.py"],
        ),
        (
            "Lab live specs",
            [python, "scripts/governance/validate_live_specs.py"],
        ),
        (
            "promotion surface",
            [python, "scripts/governance/check_promotion_surface.py"],
        ),
        (
            "live artifact budget",
            [python, "scripts/governance/check_artifact_inventory.py"],
        ),
        (
            "tracked artifacts allowlist",
            [python, "scripts/governance/check_tracked_artifacts.py"],
        ),
        (
            "trusted research consumers",
            [python, "scripts/governance/check_trusted_consumers.py"],
        ),
        (
            "research document consistency",
            [
                python,
                "-m",
                "pytest",
                "-q",
                "tests/test_research_docs_consistency.py",
                "tests/test_governance_live_specs.py",
                "tests/test_render_runner_tracking.py",
            ],
        ),
    ]
    if not args.governance_only:
        steps.extend(
            [
                (
                    "data-layer contracts",
                    [python, "-m", "pytest", "-q", "tests/test_data_layer.py"],
                ),
                (
                    "ohlcv governance contracts",
                    [
                        python,
                        "-m",
                        "pytest",
                        "-q",
                        "tests/test_ohlcv_dataset_governance.py",
                        "tests/test_ohlcv_round2_governance.py",
                        "tests/test_ohlcv_round3_governance.py",
                        "tests/test_binance_4h_ma7_regime_continuation_p0r_data.py",
                        "tests/test_trusted_consumers.py",
                    ],
                ),
                (
                    "Python lint",
                    [
                        python,
                        "-m",
                        "ruff",
                        "check",
                        "src",
                        "tests",
                        "scripts/governance",
                    ],
                ),
            ]
        )

    failures = [label for label, command in steps if not _run(label, command)]
    if failures:
        print("\nPreflight failed: " + ", ".join(failures))
        return 1
    print("\nPreflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
