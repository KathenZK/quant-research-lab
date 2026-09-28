#!/usr/bin/env python3
"""Verify round-2 protected lake and frozen 4H evidence were not mutated."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from strategy_lab.data.manifest import sha256_file

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SNAPSHOT = (
    ROOT
    / "research/platform/data-lake-governance/artifacts"
    / "pre_round2_protected_inventory_2026-09-03.csv"
)
CHECK_PREFIXES = (
    "data/raw/",
    "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m/",
    "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h/",
    "data/derived/datasets/binance_perp_1h_from_15m_v1/",
    "data/derived/datasets/binance_perp_4h_from_15m_v1/",
    "data/derived/datasets/binance_perp_1d_from_15m_v1/",
    "data/cache/binance_perp_1d_from_15m/",
    "data/cache/binance-1d-ma7-rc-p0/",
    "data/cache/binance-1d-ma7-rc-p3/",
    "research/asset-portfolios/4h-ma7-regime-continuation/artifacts/",
    "research/asset-portfolios/4h-ma7-regime-continuation/configs/",
)


def checked(relpath: str) -> bool:
    if relpath.endswith(".cache-meta.json") or relpath.endswith("_INPUT_SNAPSHOT.json"):
        return False
    return any(relpath.startswith(prefix) for prefix in CHECK_PREFIXES)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args()
    expected: dict[str, dict[str, str]] = {}
    with args.snapshot.open("r", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if checked(row["relpath"]):
                expected[row["relpath"]] = row
    missing = []
    changed = []
    for relpath, row in expected.items():
        path = ROOT / relpath
        if not path.exists():
            missing.append(relpath)
            continue
        stat = path.stat()
        digest = sha256_file(path)
        if (
            str(int(stat.st_size)) != str(row["size"])
            or digest != row["sha256"]
        ):
            changed.append(relpath)
    if missing or changed:
        raise SystemExit(
            f"round-2 protected files changed: missing={len(missing)} changed={len(changed)}; "
            f"examples={(missing + changed)[:8]}"
        )
    print(f"ok: {len(expected)} round-2 protected files unchanged")


if __name__ == "__main__":
    main()
