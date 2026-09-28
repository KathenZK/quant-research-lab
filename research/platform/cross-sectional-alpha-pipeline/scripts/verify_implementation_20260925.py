"""Scoped final acceptance; retain broader governance failures separately."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from strategy_lab.research.evidence import sha256, verify_bundle
from strategy_lab.research.exposure import read_ledger

ROOT = Path(__file__).resolve().parents[4]
TOPIC = ROOT / "research/platform/cross-sectional-alpha-pipeline"
OUT = TOPIC / "artifacts/implementation-20260925"


def main():
    tests = ["test_research_account_portfolio.py", "test_research_evidence_exposure.py", "test_relative_strength_boundaries.py",
             "test_factors.py", "test_linear_contract_returns.py", "test_mcsm_baseline_accounting_20260908.py",
             "test_mcsm_funding_account_bridge_20260910.py", "test_ma7_car_v3_opportunity.py"]
    command = [sys.executable, "-m", "pytest", "-q", *["tests/" + p for p in tests],
               "--junitxml=" + str(OUT / "acceptance-tests.xml")]
    run = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    (OUT / "acceptance-tests.txt").write_text(run.stdout + run.stderr)
    lint_paths = ["src/strategy_lab/research", "src/strategy_lab/data/factors/cross_sectional.py",
                  "research/platform/cross-sectional-alpha-pipeline/scripts",
                  "tests/test_research_account_portfolio.py", "tests/test_research_evidence_exposure.py",
                  "tests/test_relative_strength_boundaries.py"]
    lint = subprocess.run([sys.executable, "-m", "ruff", "check", *lint_paths], cwd=ROOT, text=True, capture_output=True)
    (OUT / "acceptance-lint.txt").write_text(lint.stdout + lint.stderr)
    checker = ROOT / "scripts/governance/check_trusted_consumers.py"
    spec = importlib.util.spec_from_file_location("implementation_trusted_check", checker)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    errors = module.run_checks(ROOT)
    own_errors = [e for e in errors if "research/platform/cross-sectional-alpha-pipeline/" in e]
    (OUT / "repository-governance.json").write_text(json.dumps({"errors": errors, "own_errors": own_errors}, indent=2) + "\n")
    package = verify_bundle(OUT / "candidate-bundle-r3")
    receipt = json.loads((OUT / "backup-receipt-r3.json").read_text())
    verify_bundle(Path(receipt["restored"]))
    assert sha256(Path(receipt["archive"])) == receipt["archive_sha256"]
    pin = json.loads((ROOT / "research/asset-portfolios/1d-ma7-cross-atr-generalization/specs/v3-opportunity-engine-pin-20260913.json").read_text())
    assert sha256(ROOT / pin["engine_path"]) == pin["engine_sha256"]
    restore = json.loads((OUT / "candidate-restore-result.json").read_text())
    offline = json.loads((OUT / "offline-restore-result.json").read_text())
    assert restore["ending_equity"] == offline["ending_equity"] and offline["trades"] == 18
    for entry in json.loads((ROOT / "research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json").read_text())["frozen_readers"].items():
        assert sha256(ROOT / entry[0]) == entry[1]
    ledger = read_ledger(TOPIC / "artifacts/research-exposure-ledger.jsonl")
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "test_returncode": run.returncode,
              "test_command": command, "lint_returncode": lint.returncode,
              "repository_governance_errors": len(errors), "own_governance_errors": own_errors,
              "candidate_files_verified": len(package["files"]), "local_backup_verified": True,
              "independent_restore_verified": True, "offline_restore_verified": True,
              "frozen_kernel_unchanged": True, "frozen_data_readers_unchanged": True,
              "exposure_records": len(ledger), "exposure_chain_verified": True,
              "status": "SCOPED_IMPLEMENTATION_PASS" if run.returncode == lint.returncode == 0 and not own_errors else "SCOPED_IMPLEMENTATION_FAILED",
              "repository_wide_pass": not errors, "strategy_approved": False, "prospective_started": False,
              "offsite_uploaded": False, "production_touched": False}
    (OUT / "acceptance.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "test_command"}, indent=2))
    if result["status"] != "SCOPED_IMPLEMENTATION_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
