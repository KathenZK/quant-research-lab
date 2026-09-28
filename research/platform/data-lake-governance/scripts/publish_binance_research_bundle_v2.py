#!/usr/bin/env python3
"""发布已验收价格/费率的组合清单；不修改任何数据集、旧清单或读取器。"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pandas as pd

from strategy_lab.data.manifest import sha256_file
from strategy_lab.data.research_bundle import (
    BUNDLE_ID, BUNDLE_PATH, COMPONENT_IDS, COMPONENT_ROOTS, CURRENT_PATH, FAMILY,
    READER_PATHS, local_path, read_bundle_contract, read_json, verify_bundle_files,
)
from strategy_lab.data.research_inputs import STEP, V3_CUTOFF

ROOT = Path(__file__).resolve().parents[4]
EXPECTED_MANIFESTS = {
    "15m": "e90fe921e03bccf78dea0b29675470a3661baa5cd38af8dadc2202bb0e475e8f",
    "1h": "20b1b84ca85fe158a9f05bd729c125d54877013c72fd7bf081683858b434ef7d",
    "4h": "c2bbccedaf062c0581938dd8526517c59f02aabb455e2f61c2f34e86ca8047ab",
    "1d": "f52f9c5094d37bb0064861b45f283e15f97d935929a175cecc2ebc4e2f278e19",
    "funding": "398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076",
}
EXPECTED_READERS = {
    "src/strategy_lab/data/research_inputs.py": "a4ca482c0e09e28ce164045f795458dd5451759814df38ce26b1157446ae9ce1",
    "src/strategy_lab/data/funding_v2.py": "61f5c3c400ce2089a7df533d549b90d02fc3a6f927d03f7744e44fe185535910",
}
EXPECTED_INVENTORY = "977777b6f386e02ee89006caddf617ef34e71b35e628d649a2a745adbd3c0668"


def write_immutable(path: Path, value: dict) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError(f"refusing to overwrite published file: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(content)


def build_bundle(project_root: Path, data_root: Path) -> dict:
    old = project_root / FAMILY / "artifacts/binance_v3_research_inputs_v1_20260907"
    inventory = old / "identity_inventory.csv"
    if sha256_file(inventory) != EXPECTED_INVENTORY:
        raise ValueError("old identity inventory changed")
    with inventory.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    classes = {r["symbol"]: r["snapshot_underlying_type"] or "UNKNOWN" for r in rows}
    if len(rows) != 874 or len(classes) != 874:
        raise ValueError("unexpected observed symbol inventory")
    readers = {p: sha256_file(local_path(project_root, p)) for p in sorted(READER_PATHS)}
    if readers != EXPECTED_READERS:
        raise ValueError("published readers changed")
    components = {}
    for role, relative in COMPONENT_ROOTS.items():
        manifest = local_path(data_root, relative) / "_MANIFEST.json"
        digest = sha256_file(manifest)
        if digest != EXPECTED_MANIFESTS[role]:
            raise ValueError(f"{role}: not the accepted frozen manifest")
        m = read_json(manifest)
        c = {key: m[key] for key in ("dataset_id", "rows", "start_utc", "end_utc", "parquet_inventory_fingerprint")}
        if c["dataset_id"] != COMPONENT_IDS[role]:
            raise ValueError("wrong component identity")
        c.update(root=relative, manifest_sha256=digest, symbols=m.get("symbol_count", m.get("symbols")))
        if role in STEP:
            c["last_bar_close_utc"] = (pd.Timestamp(m["end_utc"]) + STEP[role]).isoformat()
        if role in ("1h", "4h", "1d"):
            c.update(input_dataset_id=m["input_dataset_id"], input_manifest_sha256=m["input_manifest_sha256"])
        components[role] = c
    return {"schema_version": 1, "bundle_id": BUNDLE_ID, "release_date": "2026-09-07",
            "cutoff_utc": V3_CUTOFF.isoformat(), "components": components,
            "frozen_readers": readers, "observed_asset_classes": classes,
            "identity_inventory_source_sha256": EXPECTED_INVENTORY,
            "previous_bundle_sha256": sha256_file(old / "research_input_bundle.json"),
            "pit_universe_proven": False, "full_historical_funding_calendar_verified": False,
            "known_limits": ["observed classification is not historical identity or PIT universe",
                             "zero-trade bars and unresolved gaps break research windows",
                             "funding is PARTIAL_COVERAGE; API-only tails do not prove a settlement calendar",
                             "input verification does not approve costs, execution, OOS or a strategy",
                             "old consumers and immutable inputs are not migrated"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--publish", action="store_true", help="显式发布；缺省只读检查")
    args = parser.parse_args()
    bundle = build_bundle(args.project_root, args.data_root or args.project_root / "data")
    verified = verify_bundle_files(bundle, data_root=args.data_root or args.project_root / "data")
    if args.publish:
        target = local_path(args.project_root, BUNDLE_PATH)
        write_immutable(target, bundle)
        pin = {"bundle_id": BUNDLE_ID, "bundle_path": BUNDLE_PATH, "bundle_sha256": sha256_file(target)}
        read_bundle_contract(args.project_root, pin=pin)
        write_immutable(local_path(args.project_root, CURRENT_PATH), pin)
    print(json.dumps({"published": args.publish, "bundle_id": BUNDLE_ID, "verified_components": verified}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
