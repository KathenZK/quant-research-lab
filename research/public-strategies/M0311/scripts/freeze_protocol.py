"""C0 exclusive creation before historical performance. No overwriting."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, obj):
    with Path(p).open("x") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def freeze():
    now = datetime.now(timezone.utc).isoformat()
    s = json.loads((ROOT / "specs/protocol-template.json").read_text())
    s["frozen_at_utc"] = now
    s["code_hashes"] = {
        str(p.relative_to(ROOT)): sha(p)
        for p in sorted((ROOT / "scripts").glob("*.py"))
    }
    s["supporting_evidence_hashes"] = {
        str(p.relative_to(ROOT)): sha(p)
        for p in sorted((ROOT / "specs").iterdir())
        if p.is_file()
    }
    target = ROOT / "specs/M0311-first-replay.json"
    write(target, s)
    write(
        ROOT / "specs/exposure.json",
        {
            "id": s["run_id"] + "-exposure",
            "kind": "exposure",
            "family": s["family"],
            "window_start": s["evaluation"]["start"],
            "window_end": s["evaluation"]["end_exclusive"],
            "evidence_class": "historical_replay",
            "trial_count": 4,
            "control_configurations": 1,
            "historical_total_search_count": "UNKNOWN",
            "oos_claim": False,
            "selection_reason": s["exposure"]["selection"],
            "recorded_at_utc": now,
            "artifacts": {"specs/M0311-first-replay.json": sha(target)},
        },
    )
    result = {
        "id": "M0311",
        "state": "FROZEN_NOT_EXECUTED",
        "frozen_at_utc": now,
        "protocol_sha256": sha(target),
        "input_sha256": s["input"]["sha256"],
        "fidelity_class": "ADAPTED",
        "execution_class": "ADAPTED_EXECUTION_PROXY",
        "strategy_ids": 1,
        "strategy_configurations": 4,
        "controls": 1,
        "strict_replication": False,
        "market_requests": 0,
        "remote_backup_verified": False,
    }
    write(ROOT / "artifacts/20261003-first-replay/freeze-receipt.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(freeze(), indent=2))
