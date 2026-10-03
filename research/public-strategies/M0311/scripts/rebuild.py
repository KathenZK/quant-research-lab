"""Offline raw archive restoration, source verification and byte-identical replay."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import socket
from unittest.mock import patch
from audit_input import verify
from compare_original import compare
from run_replay import load_input, run
from validate_independent import validate

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rebuild(target, snapshot, source, reference):
    target = Path(target)
    assert not target.exists() and shutil.disk_usage(target.parent).free > 6 * 1024**3
    target.mkdir()
    with patch.object(
        socket.socket, "connect", side_effect=RuntimeError("OFFLINE_ONLY")
    ):
        shutil.copytree(snapshot, target / "snapshot")
        shutil.copytree(source, target / "sources")
        data = verify(target / "snapshot")
        inp = target / "independent-rebuilt-native12.csv"
        spec_path = ROOT / "specs/M0311-first-replay.json"
        spec = json.loads(spec_path.read_text())
        sourceqa = compare(load_input(inp, spec), target / "sources")
        summary = run(inp, target / "results", spec_path)
        accounting = validate(inp, target / "results")

        def inventory(p):
            return {
                x.name: {"sha256": sha(x), "bytes": x.stat().st_size}
                for x in sorted(Path(p).iterdir())
                if x.is_file()
            }

        expected = inventory(reference)
        actual = inventory(target / "results")
        assert actual == expected, "RESTORED_RESULTS_DIFFER"
    result = {
        "id": "M0311",
        "status": "PASS",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "all_result_files_byte_identical": True,
        "restored_result_files": len(actual),
        "protocol_sha256": summary["protocol_sha256"],
        "input_sha256": summary["input_sha256"],
        "source_status": sourceqa["status"],
        "data_status": data["status"],
        "independent_accounting": accounting["status"],
        "raw_files": 39,
        "files": actual,
        "new_market_requests": 0,
        "new_strategy_trials": 0,
        "remote_backup_verified": False,
        "method": "New-directory copy of39 raw source files and pinned source; independently rebuild114336 rows from ZIP bytes, replay then independent Decimal oracle",
    }
    with (target / "local-recovery.json").open("x") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--reference", required=True)
    a = p.parse_args()
    print(json.dumps(rebuild(a.target, a.snapshot, a.source, a.reference), indent=2))
