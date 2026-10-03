#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent light-manifest/recapture comparison; never promotes input trust."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT.parent / "M0256/scripts/rebuild_official_bars.py"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(target, expected):
    target = Path(target)
    reference = json.loads(Path(expected).read_text())
    manifest = json.loads((target / "manifest.json").read_text())
    for key in (
        "timeframe",
        "schema",
        "start_utc",
        "end_exclusive_utc",
        "builder_sha256",
        "identity",
    ):
        assert reference[key] == manifest[key], key
    assert sha(BUILDER) == reference["builder_sha256"]
    module_spec = importlib.util.spec_from_file_location("archive_builder", BUILDER)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    rows = []
    assert len(reference["archives"]) == len(manifest["archives"]) == 25
    for old, new in zip(reference["archives"], manifest["archives"], strict=True):
        assert old["month"] == new["month"]
        for kind in ("zip", "checksum", "csv"):
            path = target / new[kind]["path"]
            assert path.stat().st_size == old[kind]["bytes"] == new[kind]["bytes"]
            assert sha(path) == old[kind]["sha256"] == new[kind]["sha256"]
        zipped = target / new["zip"]["path"]
        data, _ = module.verify_archive(
            zipped.read_bytes(),
            (target / new["checksum"]["path"]).read_bytes(),
            zipped.name,
        )
        assert data == (target / new["csv"]["path"]).read_bytes()
        raw_rows, _ = module.audit_csv(data, "4h", new["month"])
        rows.extend((row, zipped.name) for row in raw_rows)
    canonical = module.serialize(rows, "4h")
    inp = target / manifest["canonical_csv"]["path"]
    assert canonical == inp.read_bytes()
    for key in ("bytes", "rows", "sha256"):
        assert manifest["canonical_csv"][key] == reference["canonical_csv"][key]
    assert sha(inp) == reference["canonical_csv"]["sha256"]
    return {
        "status": "PASS",
        "id": "M0286",
        "archives": 25,
        "rows": len(rows),
        "archive_files_verified": 75,
        "canonical_sha256": sha(inp),
        "reference_manifest_sha256": sha(expected),
        "capture_manifest_sha256": sha(target / "manifest.json"),
        "official_checksums_crc_grid_ohlcv": "PASS",
        "raw_to_canonical": "BYTE_IDENTICAL",
        "data_quality_status": "DIAGNOSTIC_ONLY",
        "trusted": False,
        "strict_finality": "NOT_ESTABLISHED",
        "pit": "NOT_ESTABLISHED",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = audit(args.target, args.expected)
    with Path(args.output).open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))
