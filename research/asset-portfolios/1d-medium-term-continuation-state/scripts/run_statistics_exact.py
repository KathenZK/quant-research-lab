"""固定原P1 panel与修复合同，执行可恢复的完整比率bootstrap；不改原运行。"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-run", default="p1-research")
    parser.add_argument("--original-run", default="p1-statistics")
    parser.add_argument("--run-id", default="p1-statistics-exact-r1")
    parser.add_argument("--parity-only", action="store_true")
    parser.add_argument("--batch-reps", type=int, default=256)
    parser.add_argument("--checkpoint-reps", type=int, default=4096)
    args = parser.parse_args()
    if args.parity_only and args.run_id == "p1-statistics-exact-r1":
        args.run_id = "p1-statistics-exact-parity-r1"
    for name in (args.panel_run, args.original_run, args.run_id):
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("invalid own-family run directory")
    if args.run_id in (args.panel_run, args.original_run):
        raise ValueError("output must not replace input or original failed inference")
    spec = importlib.util.spec_from_file_location("mtcs_statistics_exact_runner", FAMILY / "scripts/statistics_exact.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    inp = FAMILY / "artifacts" / args.panel_run
    metadata_path = inp / "panel-manifest.json"
    metadata = json.loads(metadata_path.read_text())
    path = inp / "panel.pkl.gz"
    if module.file_sha(path) != metadata["sha256"]:
        raise ValueError("frozen P1 panel bytes changed")
    for relative, digest in metadata["pins"].items():
        pinned = (FAMILY / relative).resolve()
        if not pinned.is_relative_to(FAMILY) or module.file_sha(pinned) != digest:
            raise ValueError(f"original panel computation identity changed: {relative}")
    names = ("specs/research-contract.md", "specs/statistics-contract.md",
             "specs/statistics-exact-computation-repair.md", "scripts/statistics.py",
             "scripts/run_statistics.py", "scripts/statistics_exact.py", "scripts/run_statistics_exact.py",
             "scripts/test_statistics_exact.py")
    pins = {name: module.file_sha(FAMILY / name) for name in names}
    pins[str(metadata_path.relative_to(FAMILY))] = module.file_sha(metadata_path)
    pins[str(path.relative_to(FAMILY))] = metadata["sha256"]
    panel = pd.read_pickle(path, compression="gzip")
    if not isinstance(panel, pd.DataFrame) or len(panel) != metadata["rows"]:
        raise ValueError("panel type or row count changed")
    output = FAMILY / "artifacts" / args.run_id
    if args.parity_only:
        report = module.validate_parity(panel, output, seed=20260908,
                                        batch_reps=args.batch_reps, external_pins=pins)
    else:
        report = module.analyze(panel, output, bootstrap_reps=1_000_000, seed=20260908,
                                batch_reps=args.batch_reps, checkpoint_reps=args.checkpoint_reps,
                                external_pins=pins, baseline_dir=FAMILY / "artifacts" / args.original_run)
    changed = [name for name, digest in pins.items() if module.file_sha(FAMILY / name) != digest]
    if changed:
        raise ValueError(f"frozen files changed during execution: {changed}")
    receipt_path = output / "execution-receipt.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt["pins"] != pins or receipt["report_sha256"] != module.file_sha(output / "report.json"):
            raise ValueError("existing execution receipt differs")
    else:
        module._json(receipt_path, {"utc": datetime.now(timezone.utc).isoformat(), "pins": pins,
                                    "panel_sha256": metadata["sha256"], "history_only": True,
                                    "mode": "PARITY_ONLY" if args.parity_only else "FULL_EXACT_BOOTSTRAP",
                                    "report_sha256": module.file_sha(output / "report.json")})
    print(json.dumps({"status": report["status"], "mode": report.get("mode", "FULL_EXACT_BOOTSTRAP"),
                      "all_reliable": report.get("all_reliable"),
                      "candidate": report.get("selected_historical_candidate"),
                      "output": str(output)}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
