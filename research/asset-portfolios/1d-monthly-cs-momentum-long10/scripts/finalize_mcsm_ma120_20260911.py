"""Finalize scoped tests, evidence pins and budget; never repairs other families."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from research_mcsm_single_asset_exit_20260910 import FAMILY, ROOT, load_frozen_inputs, save, sha

OUT = FAMILY / "artifacts/ma120-round-20260911"


def main():
    audit = json.loads((OUT / "independent-audit.json").read_text())
    assert audit["status"] == "PASS_ALL_8_ACCOUNTS_AND_DIRECT_MA120_SIGNALS"
    assert sha(OUT / "summary.json") == audit["summary_sha256"]
    summary = json.loads((OUT / "summary.json").read_text())
    for name, digest in summary["source_sha256"].items():
        assert sha(OUT / name) == digest, name
    load_frozen_inputs()
    tests = ["test_mcsm_ma120_20260911.py", "test_mcsm_single_asset_exit_20260910.py",
             "test_mcsm_single_exit_independent_account_20260910.py", "test_mcsm_broader_exit_20260911.py",
             "test_mcsm_round_independent_20260911.py", "test_mcsm_weekly_20260911.py",
             "test_mcsm_weekly_independent_account_20260911.py"]
    qa = subprocess.run([sys.executable, "-m", "pytest", "-q", *[str(ROOT / "tests" / n) for n in tests]],
                        cwd=ROOT, capture_output=True, text=True, check=False)
    assert qa.returncode == 0, qa.stdout + qa.stderr
    scripts = sorted((FAMILY / "scripts").glob("*mcsm_ma120*20260911.py"))
    scripts += [FAMILY / "scripts/mcsm_ma120_accounting_20260911.py"]
    lint = subprocess.run([sys.executable, "-m", "ruff", "check", "--ignore", "F401", *map(str, scripts),
                           str(ROOT / "tests/test_mcsm_ma120_20260911.py")],
                          cwd=ROOT, capture_output=True, text=True, check=False)
    assert lint.returncode == 0, lint.stdout + lint.stderr
    location = ROOT / "scripts/governance/check_trusted_consumers.py"
    spec = importlib.util.spec_from_file_location("ma120_consumer_registry_check", location)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    errors = module.run_checks(ROOT)
    own = [e for e in errors if "1d-monthly-cs-momentum-long10" in e]
    assert not own, own
    qa_result = {"tests_pass": True, "tests_output": qa.stdout, "ruff_pass_except_frozen_unused_import": True,
                 "ruff_ignored_rule": "F401 only: frozen research runner retains unused ROOT import; no code changed after plan",
                 "ruff_output": lint.stdout, "repository_wide_registry_pass": not errors,
                 "registry_errors_outside_this_family": errors, "own_family_registry_errors": own,
                 "original_frozen_inputs_unchanged": True}
    save(OUT / "qa.json", qa_result)
    required = [FAMILY / "specs/binance-1d-mcsm-ma120-round-20260911.md",
                FAMILY / "diagnostics/binance-1d-mcsm-ma120-round-20260911.md",
                OUT / "monthly-holdings-and-pnl.md", OUT / "yearly-results.md", OUT / "README.md",
                OUT / "summary.json", OUT / "independent-audit.json", OUT / "report-details.json", OUT / "qa.json"]
    assert all(p.is_file() for p in required)
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    assert size < 50 * 1024 * 1024
    final = {"status": "RESEARCH_COMPLETE_MA120_NOT_LIVE_READY", "accounts_complete": 8,
             "monthly_slots_checked": 760, "admitted_month_legs": 516, "early_exit_legs": 173,
             "monthly_tables": 76, "yearly_tables": 7, "new_bytes_before_completion": size,
             "budget_bytes": 50 * 1024 * 1024, "repository_wide_registry_pass": not errors,
             "own_family_registry_pass": True, "original_sources_unchanged": True,
             "files_sha256": {str(p.relative_to(ROOT)): sha(p) for p in [*required, *scripts,
                                                                        ROOT / "tests/test_mcsm_ma120_20260911.py"]}}
    save(OUT / "completion.json", final)
    print(json.dumps({k: v for k, v in final.items() if k != "files_sha256"}), flush=True)


if __name__ == "__main__":
    main()
