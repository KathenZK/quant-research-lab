"""Archive a preselected frozen candidate; does not rerun/overwrite original research."""
from dataclasses import fields
import argparse
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys

from strategy_lab.research.evidence import create_bundle, local_backup, restore_backup, sha256

ROOT = Path(__file__).resolve().parents[4]
TOPIC = ROOT / "research/platform/cross-sectional-alpha-pipeline"
OUT = TOPIC / "artifacts/implementation-20260925"
FAMILY = ROOT / "research/asset-portfolios/1d-ma7-cross-atr-generalization"
OLD = FAMILY / "artifacts/v3_no_extra_warmup_20260913"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", type=int, default=1)
    args = parser.parse_args()
    if args.revision < 1:
        raise ValueError("positive package revision required")
    suffix = "" if args.revision == 1 else f"-r{args.revision}"
    pin = json.loads((FAMILY / "specs/v3-opportunity-engine-pin-20260913.json").read_text())
    source = json.loads((OLD / "inputs/catalog.json").read_text())["HYPE__seg001"]
    for path, h in json.loads((OLD / "started.json").read_text())["pins"].items():
        if sha256(ROOT / path) != h:
            raise ValueError(f"original frozen source changed: {path}")
    for key, hashkey in [("joint_path", "joint_sha256"), ("hourly_path", "hourly_sha256"), ("daily_source", "daily_sha256")]:
        if sha256(ROOT / source[key]) != source[hashkey]:
            raise ValueError(f"original frozen input changed: {key}")
    engine_path = ROOT / pin["engine_path"]
    if sha256(engine_path) != pin["engine_sha256"]:
        raise ValueError("engine changed")
    spec = importlib.util.spec_from_file_location("frozen_v6_package", engine_path)
    engine = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = engine
    spec.loader.exec_module(engine)
    reference = OLD / "accounts/HYPE__seg001/V3"
    summary = json.loads((reference / "summary.json").read_text())
    checkpoint = json.loads((OLD / "checkpoints/HYPE.json").read_text())
    old_row = next(r for r in checkpoint["summary"] if r["case_id"] == "V3" and r["run_key"] == "HYPE__seg001")
    assert all(old_row[k] == v for k, v in summary.items())
    config = {"identity": "HYPE MA7-CAR V3 no-extra-warmup 20260913", "parameters": {f.name: summary[f.name] for f in fields(engine.Config)},
              "segment_id": source["segment_id"], "input_start": source["input_start"],
              "start": summary["start"], "end": source["end"], "model_kind": "rule"}
    staging = OUT / ("packaging" + suffix)
    staging.mkdir(exist_ok=False)
    (staging / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    packages = ["numpy", "pandas", "pyarrow", "python-dateutil", "pytz", "tzdata", "six"]
    requirements = {p: importlib.metadata.version(p) for p in packages}
    (staging / "requirements.txt").write_text("".join(f"{p}=={v}\n" for p, v in requirements.items()))
    env = {"python": sys.version, "platform": platform.platform(), "packages": requirements,
           "repository_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
           "worktree_dirty": True, "source_identity": "exact bundled bytes are authoritative; commit alone is insufficient"}
    (staging / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
    entries = []
    def add(p, name, role):
        entries.append({"source": str(p), "path": name, "role": role, "sha256": sha256(p)})
    add(engine_path, "code/engine.py", "code")
    add(ROOT / "src/strategy_lab/research/accounting.py", "code/accounting.py", "code")
    add(TOPIC / "scripts/replay_candidate_bundle.py", "replay.py", "code")
    for p, name in [(FAMILY / "specs/contract-v3-no-extra-warmup-20260913.md", "no-extra-warmup.md"),
                    (FAMILY / "specs/contract-v3-opportunity-20260913.md", "opportunity.md"),
                    (TOPIC / "specs/implementation-contract-20260925.md", "implementation-contract.md")]:
        add(p, "spec/" + name, "spec")
    for key, name in [("joint_path", "input/joint_daily.parquet"), ("hourly_path", "input/hourly.parquet"),
                      ("daily_source", "reference/daily_features.parquet")]:
        add(ROOT / source[key], name, "input" if key != "daily_source" else "reference_output")
    for p in sorted(reference.iterdir()):
        if p.is_file():
            add(p, "reference/" + p.name, "reference_output")
    for p, name in [(OLD / "inputs/catalog.json", "source-catalog.json"), (OLD / "started.json", "original-started.json"),
                    (OLD / "checkpoints/HYPE.json", "original-checkpoint.json"),
                    (FAMILY / "specs/v3-opportunity-engine-pin-20260913.json", "engine-pin.json")]:
        add(p, "provenance/" + name, "provenance")
    add(staging / "config.json", "config.json", "spec")
    for name in ["environment.json", "requirements.txt"]:
        add(staging / name, name, "environment")
    bundle = OUT / ("candidate-bundle" + suffix)
    manifest = create_bundle(bundle, entries, metadata={"model_kind": "rule", "candidate": config["identity"],
        "created_at": datetime.now(timezone.utc).isoformat(), "retention_class": "normative-evidence",
        "funding": "unverified; original price-only replay", "new_strategy_trials": 0,
        "reference_output_pin_time": "2026-09-25 packaging; matching retained 2026-09-13 checkpoint, not a retroactive original hash claim"})
    backup_dir = Path.home() / ("QuantResearchBackups/20260925-ma7-car-v3" + suffix)
    backup_dir.mkdir(parents=True, exist_ok=False)
    archive = backup_dir / "candidate-evidence.zip"
    archive_sha = local_backup(bundle, archive)
    (backup_dir / "candidate-evidence.zip.sha256").write_text(archive_sha + "  candidate-evidence.zip\n")
    restored = backup_dir / "restored"
    restore_backup(archive, restored, expected_sha256=archive_sha)
    result = {"bundle": str(bundle), "files": len(manifest["files"]), "archive": str(archive),
              "archive_sha256": archive_sha, "archive_bytes": archive.stat().st_size,
              "restored": str(restored), "offsite_uploaded": False}
    (OUT / ("backup-receipt" + suffix + ".json")).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
