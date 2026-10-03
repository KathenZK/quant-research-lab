#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Restore pinned public software into an explicit private directory."""

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fetch(target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for item in json.loads((ROOT / "specs/source-manifest.json").read_text())["files"]:
        path = target / item["filename"]
        if path.exists():
            data = path.read_bytes()
        else:
            with urllib.request.urlopen(item["url"], timeout=30) as response:
                data = response.read(2_000_001)
        assert len(data) == item["bytes"]
        assert hashlib.sha256(data).hexdigest() == item["sha256"]
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(data)
    return {"status": "PASS", "files": len(list(target.glob("*")))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    print(json.dumps(fetch(parser.parse_args().target)))
