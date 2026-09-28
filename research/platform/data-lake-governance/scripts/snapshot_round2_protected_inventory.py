#!/usr/bin/env python3
"""Snapshot round-2 protected lake and frozen research evidence. Does not overwrite round-1 inventory."""

from __future__ import annotations

import csv
from pathlib import Path

from strategy_lab.data.manifest import sha256_file

ROOT = Path(__file__).resolve().parents[4]
OUT = (
    ROOT
    / "research/platform/data-lake-governance/artifacts"
    / "pre_round2_protected_inventory_2026-09-03.csv"
)
PREFIXES = (
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
    "research/platform/data-lake-governance/artifacts/",
)
SUFFIXES = (".parquet", ".json", ".sha256", ".csv", ".md")
SKIP_NAMES = {"pre_round2_protected_inventory_2026-09-03.csv"}


def is_protected(relpath: str) -> bool:
    name = Path(relpath).name
    if name in SKIP_NAMES or name.endswith(".cache-meta.json"):
        return False
    return any(relpath.startswith(prefix) for prefix in PREFIXES) and relpath.endswith(SUFFIXES)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str | int]] = []
    for prefix in PREFIXES:
        root = ROOT / prefix
        if not root.exists():
            continue
        paths = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
        for path in paths:
            relpath = path.relative_to(ROOT).as_posix()
            if not is_protected(relpath):
                continue
            stat = path.stat()
            rows.append(
                {
                    "relpath": relpath,
                    "size": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                    "sha256": sha256_file(path),
                }
            )
            if len(rows) % 5000 == 0:
                print(f"hashed {len(rows)} files", flush=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["relpath", "size", "mtime_ns", "sha256"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
