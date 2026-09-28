#!/usr/bin/env python3
"""Compare current protected parquet files against the pre-governance inventory snapshot."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from strategy_lab.data.manifest import sha256_file

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SNAPSHOT = (
    ROOT
    / "research/platform/data-lake-governance/artifacts/pre_governance_parquet_inventory.csv"
)
PROTECTED_PREFIXES = (
    "data/raw/",
    "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m/",
    "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h/",
    "data/cache/binance_perp_1d_from_15m/",
    "data/cache/binance-1d-ma7-rc-p0/",
    "data/cache/binance-1d-ma7-rc-p3/",
    "research/asset-portfolios/4h-ma7-regime-continuation/artifacts/",
)


def is_protected(relpath: str) -> bool:
    if relpath.endswith(".cache-meta.json"):
        return False
    return any(relpath.startswith(prefix) for prefix in PROTECTED_PREFIXES) and relpath.endswith(
        (".parquet", ".sha256", ".json", ".csv", ".md")
    )


def current_row(path: Path) -> dict[str, str | int]:
    stat = path.stat()
    return {
        "relpath": path.relative_to(ROOT).as_posix(),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": sha256_file(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args()
    if not args.snapshot.exists():
        raise FileNotFoundError(f"missing snapshot {args.snapshot}")
    expected: dict[str, dict[str, str]] = {}
    with args.snapshot.open("r", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            relpath = row["relpath"]
            if is_protected(relpath):
                expected[relpath] = row
    missing = []
    changed = []
    for relpath, row in expected.items():
        path = ROOT / relpath
        if not path.exists():
            missing.append(relpath)
            continue
        actual = current_row(path)
        if (
            str(actual["size"]) != str(row["size"])
            or str(actual["mtime_ns"]) != str(row["mtime_ns"])
            or actual["sha256"] != row["sha256"]
        ):
            changed.append(
                {
                    "relpath": relpath,
                    "expected_sha256": row["sha256"],
                    "actual_sha256": actual["sha256"],
                    "expected_mtime_ns": row["mtime_ns"],
                    "actual_mtime_ns": actual["mtime_ns"],
                }
            )
    if missing or changed:
        raise SystemExit(
            f"protected files changed: missing={len(missing)} changed={len(changed)}; "
            f"examples={ (missing + [item['relpath'] for item in changed])[:8] }"
        )
    print(f"ok: {len(expected)} protected files unchanged")


if __name__ == "__main__":
    main()
