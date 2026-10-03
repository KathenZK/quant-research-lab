#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Restore M0293 in a new directory and require all result bytes to match."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from audit_input import audit
from compare_original import compare
from fetch_sources import fetch
from run_replay import load_input, run
from validate_independent import validate

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rebuild(target, reference_results, snapshot, source_snapshot):
    target = Path(target)
    if target.exists():
        raise ValueError("TARGET_EXISTS_REFUSED")
    assert shutil.disk_usage(target.parent).free > 5 * 1024**3 + 100 * 1024**2
    target.mkdir()
    sources = target / "sources"
    shutil.copytree(source_snapshot, sources)
    manifest = json.loads((ROOT / "specs/source-manifest.json").read_text())
    assert all((sources / item["filename"]).is_file() for item in manifest["files"]), (
        "OFFLINE_SOURCE_MISSING"
    )
    fetch(sources)  # all pinned files already exist; no network request
    new_input = target / "input"
    shutil.copytree(snapshot, new_input)
    data_audit = audit(
        new_input,
        ROOT.parent
        / "M0256/artifacts/20261003-first-replay/4h-input-manifest-light.json",
    )
    inp = new_input / "BTCUSDT-4h-202212-202412-native12.csv"
    spec_path = ROOT / "specs/M0293-first-replay.json"
    spec = json.loads(spec_path.read_text())
    source_audit = compare(load_input(inp, spec), sources)
    output = target / "results"
    summary = run(inp, output, spec_path)
    independent = validate(inp, output)
    reference_results = Path(reference_results)
    if (reference_results / "result-manifest.json").exists():
        # Public lightweight record contains hashes for private full outputs.
        reference = json.loads(
            (reference_results / "result-manifest.json").read_text()
        )["files"]
    else:
        reference = {
            p.name: {"sha256": sha(p), "bytes": p.stat().st_size}
            for p in reference_results.iterdir()
            if p.is_file()
        }
    actual = {
        p.name: {"sha256": sha(p), "bytes": p.stat().st_size}
        for p in output.iterdir()
        if p.is_file()
    }
    assert actual == reference, "RESULT_BYTE_MISMATCH"
    receipt = {
        "id": "M0293",
        "status": "PASS",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "new_directory": str(target),
        "restored_result_files": len(actual),
        "all_result_files_byte_identical": True,
        "source_restore": source_audit["status"],
        "data_restore": data_audit["status"],
        "independent_accounting": independent["status"],
        "protocol_sha256": summary["protocol_sha256"],
        "input_sha256": summary["input_sha256"],
        "new_strategy_trials": 0,
        "data_mode": "offline new-directory copy plus75 raw hashes/checksums/CRC/rowQA and raw-to-canonical rebuild;0newmarketrequests",
        "files": actual,
    }
    (target / "local-recovery.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--reference-results", required=True)
    parser.add_argument("--input-snapshot", required=True)
    parser.add_argument("--source-snapshot", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            rebuild(
                args.target,
                args.reference_results,
                args.input_snapshot,
                args.source_snapshot,
            ),
            indent=2,
        )
    )
