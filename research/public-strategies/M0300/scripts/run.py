"""Pinned shared kernel entrypoint; forwards user-supplied local file paths."""

from pathlib import Path
import hashlib
import json
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    s = json.loads((ROOT / "specs/protocol.json").read_text())
    kernel = ROOT.parents[1] / "_shared-kernels/native5m-execution-proxy/v1"
    for name, digest in s["kernel"]["files"].items():
        assert hashlib.sha256((kernel / name).read_bytes()).hexdigest() == digest, name
    sys.path.insert(0, str(kernel))
    sys.argv += ["--idroot", str(ROOT)]
    runpy.run_path(str(kernel / "workflow.py"), run_name="__main__")
