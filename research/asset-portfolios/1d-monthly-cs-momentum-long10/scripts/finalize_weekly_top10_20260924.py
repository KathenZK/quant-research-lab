"""Scoped completion gate, immutable evidence chain, tables, tests and budget."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys

import pandas as pd

from complete_weekly_top10_20260924 import FAMILY, OUT, PRIOR, ROOT, validate_prior
from research_mcsm_weekly_20260911 import pin, save, sha


def main():
    validate_prior()
    audit = json.loads((OUT / "independent-audit.json").read_text())
    assert len(audit["results"]) == 8
    assert all(r["status"] == "PASS_INDEPENDENT_CASH_AND_REPORTING" for r in audit["results"])
    pin(OUT / "summary.json", audit["summary_sha256"])
    pin(FAMILY / "scripts/audit_weekly_top10_20260924.py", audit["audit_script_sha256"])
    summary = json.loads((OUT / "summary.json").read_text())
    for name, digest in summary["files_sha256"].items():
        pin(OUT / name, digest)
    plan = json.loads((OUT / "plan.json").read_text())
    pin(FAMILY / "scripts/complete_weekly_top10_20260924.py", plan["script_sha256"])
    for name, digest in plan["retained_endpoint_hashes"].items():
        pin(ROOT / name, digest)
    details = json.loads((OUT / "report-details.json").read_text())
    pin(OUT / "independent-audit.json", details["audit_sha256"])
    pin(FAMILY / "scripts/report_weekly_top10_20260924.py", details["report_script_sha256"])
    for name, digest in details["delivery_sha256"].items():
        pin(FAMILY / name, digest)
    weekly = (OUT / "weekly-holdings-and-pnl.md").read_text()
    rows = re.findall(r"^\| \d{4}-\d{2}-\d{2} \|.*$", weekly, re.M)
    assert len(rows) == 318
    periods = pd.read_parquet(OUT / "W7-center-4bp/periods.parquet")
    for line, r in zip(rows, periods.to_dict("records"), strict=True):
        assert f"| {r['return']:+.2%} | {r['pnl_usdt']:+,.2f} | {r['end_equity']:,.2f} |" in line
        assert r["selected_symbols"].replace("/USDT:USDT", "") in line
    monthly = (OUT / "monthly-holdings-and-pnl.md").read_text()
    assert len(re.findall(r"^\| \d{4}-\d{2} \|", monthly, re.M)) == 146  # 73 accounts and 73 holdings
    years = (OUT / "yearly-results.md").read_text()
    assert len(re.findall(r"^\| 20\d{2}", years, re.M)) == 7
    docs = [FAMILY / "specs/binance-1d-mcsm-weekly-top10-20260924.md",
            FAMILY / "specs/binance-1d-mcsm-weekly-top10-terminal-amendment-20260924.md",
            FAMILY / "diagnostics/binance-1d-mcsm-weekly-top10-20260924.md", PRIOR / "README.md",
            OUT / "weekly-holdings-and-pnl.md", OUT / "monthly-holdings-and-pnl.md", OUT / "yearly-results.md"]
    pending = {(OUT / "qa.json").resolve(), (OUT / "completion.json").resolve()}
    for doc in docs:
        for target in re.findall(r"\]\(([^)]+)\)", doc.read_text()):
            if target.startswith(("https://", "http://", "#")):
                continue
            path = (doc.parent / target.split("#")[0]).resolve()
            assert path.exists() or path in pending, (doc, target)
    tests = ["test_weekly_top10_20260924.py", "test_mcsm_weekly_20260911.py",
             "test_mcsm_weekly_independent_account_20260911.py", "test_mcsm_baseline_accounting_20260908.py",
             "test_mcsm_baseline_estimate_20260909.py"]
    qa = subprocess.run([sys.executable, "-m", "pytest", "-q", *[str(ROOT / "tests" / n) for n in tests]],
                        cwd=ROOT, capture_output=True, text=True, check=False)
    assert qa.returncode == 0, qa.stdout + qa.stderr
    scripts = [FAMILY / "scripts" / (n + "_20260924.py") for n in [
        "collect_weekly_terminals", "research_weekly_top10", "complete_weekly_top10",
        "audit_weekly_top10", "report_weekly_top10", "finalize_weekly_top10"]]
    lint = subprocess.run([sys.executable, "-m", "ruff", "check", *map(str, scripts),
                           str(ROOT / "tests/test_weekly_top10_20260924.py")],
                          cwd=ROOT, capture_output=True, text=True, check=False)
    assert lint.returncode == 0, lint.stdout + lint.stderr
    registry = ROOT / "scripts/governance/check_trusted_consumers.py"
    spec = importlib.util.spec_from_file_location("weekly_20260924_registry", registry)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    errors = module.run_checks(ROOT)
    own = [e for e in errors if "1d-monthly-cs-momentum-long10" in e]
    assert not own, own
    size = sum(p.stat().st_size for p in PRIOR.rglob("*") if p.is_file())
    assert size < 30 * 1024 * 1024
    save(OUT / "qa.json", {"tests_pass": True, "tests_output": qa.stdout, "ruff_pass": True,
                           "ruff_output": lint.stdout, "report_links_pass": True, "all_weekly_table_values_checked": True,
                           "own_family_registry_errors": own, "repository_wide_registry_pass": not errors,
                           "registry_errors_outside_this_family": errors, "registry_sha256": sha(registry),
                           "all_first_attempt_evidence_unchanged": True, "prior_frozen_sources_unchanged": True})
    required = [*docs, *scripts, OUT / "qa.json", OUT / "plan.json", OUT / "summary.json",
                OUT / "independent-audit.json", OUT / "report-details.json", ROOT / "tests/test_weekly_top10_20260924.py",
                FAMILY / "README.md", FAMILY / "binance-1d-mcsm-l10-core-ledger.md", FAMILY / "decision-log.md",
                FAMILY / "scripts/README.md", FAMILY / "artifacts/README.md"]
    final = {"status": "RESEARCH_COMPLETE_WEEKLY_TOP10_NOT_LIVE_READY", "accounts_complete": 8,
             "weekly_decisions": 318, "weekly_legs": 3180, "monthly_records_per_account": 73,
             "years_per_account": 7, "funding_included": False, "exact_terminal_prices_verified": False,
             "own_family_registry_pass": True, "repository_wide_registry_pass": not errors,
             "new_bytes_before_completion": size, "budget_bytes": 30 * 1024 * 1024,
             "files_sha256": {str(p.relative_to(ROOT)): sha(p) for p in required}}
    save(OUT / "completion.json", final)
    print(qa.stdout, flush=True)
    print(json.dumps({k: v for k, v in final.items() if k != "files_sha256"}), flush=True)


if __name__ == "__main__":
    main()
