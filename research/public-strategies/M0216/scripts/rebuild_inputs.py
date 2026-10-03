"""Restore a private exact input from official archives; never publish prices."""

import argparse
import hashlib
import json
from pathlib import Path

import fetch_inputs

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--staging-dir", type=Path, required=True)
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / "artifacts/20261003-first-replay"
    if (target / "input.csv").exists():
        raise FileExistsError("Refusing to overwrite retained input.csv")
    expected = json.loads((target / "input-manifest.json").read_text())["input_sha256"]
    fetch_inputs.RAW = args.raw_dir
    fetch_inputs.OUT = args.staging_dir
    fetch_inputs.fetch()
    payload = (args.staging_dir / "input.csv").read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError(
            "Official archive revision differs from frozen input; do not run as exact recovery"
        )
    with (target / "input.csv").open("xb") as handle:
        handle.write(payload)
    print("Exact private input restored and hash-verified:", expected)
