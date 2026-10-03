"""Compare a rebuilt result directory to the immutable published result hashes."""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

from run_replay import FAMILY, dump, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuilt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((FAMILY / "artifacts/20261003-first-replay/result-manifest.json").read_text())
    expected = manifest["private_full_results"]
    assert len(expected) == 10
    assert {p.name for p in args.rebuilt.iterdir()} == {x["path"] for x in expected}
    for item in expected:
        path = args.rebuilt / item["path"]
        if sha(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise ValueError(f"Rebuild mismatch: {item['path']}")
    dump(args.out, {"status": "PASS", "verified_at_utc": datetime.now(UTC).isoformat(),
                    "files_exact_hash_and_size": 10, "original_run_id": manifest["origin_run_id"],
                    "strict_replication": False})
    print("PASS all 10 rebuilt result files match frozen hashes and sizes")


if __name__ == "__main__":
    main()
