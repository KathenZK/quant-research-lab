#!/usr/bin/env python3
"""组合发布的只读现场验收；报告写入本家族 artifacts，不改数据/冻结消费者。"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from strategy_lab.data.funding_v2 import load_funding_v2, require_funding_v2_window
from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory, sha256_file
from strategy_lab.data.research_bundle import (
    FAMILY, local_path, read_bundle_contract, read_json, require_research_startup,
)

ROOT = Path(__file__).resolve().parents[4]
ART = ROOT / FAMILY / "artifacts/binance_research_bundle_v2_20260907"


def save(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def run(command: list[str]) -> dict:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
    return {"command": command, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ART)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if not out.is_relative_to((ROOT / FAMILY / "artifacts").resolve()):
        raise ValueError("output must stay in governance artifacts")
    if any((out / name).exists() for name in ("acceptance.json", "negative_checks.json", "protection.json", "test_summary.json", "price_startup_final.json", "bundle_integrity_final.json", "contract_final.json")):
        raise ValueError("fresh output filenames required; retain prior audit evidence")
    bundle, pin = read_bundle_contract(ROOT)
    example = ROOT / FAMILY / "specs/research-startup-price-example-v2.json"
    request = read_json(example)
    checks = {}
    for label, changes in {
        "net_without_identity": {"mode": "net_research"},
        "outside_frozen_window": {"end": "2026-09-07T00:00:00Z"},
        "legacy_bundle": {"bundle_id": "binance.v3.research_inputs.v1"},
        "wrong_bundle_hash": {"bundle_sha256": "0" * 64},
        "noncoin_as_crypto": {"symbols": [next(s for s, c in bundle["observed_asset_classes"].items() if c == "EQUITY")]},
    }.items():
        try:
            require_research_startup({**request, **changes}, project_root=ROOT)
        except (ValueError, FileNotFoundError) as exc:
            checks[label] = {"rejected": True, "reason": str(exc)}
        else:
            raise AssertionError(f"negative check unexpectedly passed: {label}")
    print("Request identity/range/asset negative checks passed", flush=True)
    funding_component = bundle["components"]["funding"]
    funding = load_funding_v2(local_path(ROOT / "data", funding_component["root"]),
                              expected_manifest_sha256=funding_component["manifest_sha256"])
    try:
        require_funding_v2_window(funding, symbol="BTC/USDT:USDT", start="2026-09-01T00:00:00Z",
                                 end="2026-09-02T00:00:00Z",
                                 identity_evidence="NEGATIVE CALENDAR PLUMBING TEST ONLY; NOT REAL IDENTITY EVIDENCE")
    except ValueError as exc:
        assert "coverage not proven" in str(exc)
        checks["real_september_calendar"] = {"rejected": True, "reason": str(exc),
                                             "scope": "lower-level calendar negative test, no claim of independently verified identity"}
    else:
        raise AssertionError("unproved September calendar unexpectedly passed")
    save(out / "negative_checks.json", checks)
    del funding
    print("Real funding calendar negative check passed", flush=True)

    previous = ROOT / FAMILY / "artifacts/data_lake_structure_cleanup_audit_20260907/published_content_check.json"
    protected = []
    for record in read_json(previous)["datasets"]:
        root = local_path(ROOT, record["root"])
        actual = inventory_fingerprint(parquet_inventory(root))
        assert actual == record["actual_parquet_fingerprint"], record["dataset_id"]
        assert sha256_file(root / "_MANIFEST.json") == record["manifest_sha256"], record["dataset_id"]
        protected.append({"dataset_id": record["dataset_id"], "manifest_sha256": record["manifest_sha256"], "fingerprint": actual})
        print(f'Protected content unchanged: {record["dataset_id"]}', flush=True)
    old = ROOT / FAMILY / "artifacts/binance_v3_research_inputs_v1_20260907/research_input_bundle.json"
    assert sha256_file(old) == bundle["previous_bundle_sha256"]
    expected_sources = {
        f"{FAMILY}/scripts/build_binance_v3_research_inputs.py": "336e307e7507216cd61d0f2bd863518e520ee556e1c957b3a1796f263827f27d",
        f"{FAMILY}/scripts/govern_binance_15m_history_v3.py": "817cab49d0114f57cf5464875ce9730bfd49a613353611ec410e81274e451301",
        f"{FAMILY}/scripts/build_binance_funding_v2.py": "bf3f636daddeae18baa00db278441c12aff0f49a07d919d68b06a2743ddb678b",
        f"{FAMILY}/specs/binance-funding-v3-inputs-v2-2026-09-07.md": "efe42c6ca54ab36e1a818b4dba32e3977a9f56267f54c89e61e760052bcbffa2",
        **bundle["frozen_readers"],
    }
    assert all(sha256_file(ROOT / p) == digest for p, digest in expected_sources.items())
    save(out / "protection.json", {"previous_audit_sha256": sha256_file(previous), "datasets": protected,
                                    "old_bundle_sha256": sha256_file(old), "frozen_sources": expected_sources,
                                    "all_unchanged": True, "scope": "10 published derived datasets plus listed frozen sources; not a new raw/normalized rescan"})

    commands = {}
    cli = [sys.executable, "scripts/governance/check_research_startup.py"]
    for label, mode in (("contract", ["--contract-only"]), ("bundle_integrity", ["--bundle-only"]),
                        ("price_startup", ["--request", str(example)])):
        commands[label] = run(cli + mode + ["--output", str(out / f"{label}_final.json")])
        assert commands[label]["exit_code"] == 0, commands[label]
        print(f"Live startup {label}: PASS", flush=True)
    commands["targeted_tests"] = run([sys.executable, "-m", "pytest", "-q",
        "tests/test_research_bundle.py", "tests/test_v3_research_inputs.py", "tests/test_funding_v2.py",
        "tests/test_binance_15m_history_v3.py", "tests/test_binance_15m_history_closeout.py",
        "tests/test_ohlcv_round3_governance.py", "tests/test_research_docs_consistency.py"])
    assert commands["targeted_tests"]["exit_code"] == 0, commands["targeted_tests"]
    commands["scanner_unit_tests"] = run([sys.executable, "-m", "pytest", "-q", "tests/test_trusted_consumers.py",
                                          "-k", "not repository_governed_consumers_pass"])
    assert commands["scanner_unit_tests"]["exit_code"] == 0, commands["scanner_unit_tests"]
    commands["lint"] = run([sys.executable, "-m", "ruff", "check", "src/strategy_lab/data/research_bundle.py",
                            "scripts/governance", "tests/test_research_bundle.py", "tests/test_trusted_consumers.py",
                            f"{FAMILY}/scripts/publish_binance_research_bundle_v2.py", str(Path(__file__))])
    assert commands["lint"]["exit_code"] == 0, commands["lint"]
    print("Targeted tests, scanner unit tests and lint: PASS", flush=True)
    commands["repository_preflight"] = run([sys.executable, "scripts/governance/preflight.py", "--governance-only"])
    spec = importlib.util.spec_from_file_location("startup_consumer_audit", ROOT / "scripts/governance/check_trusted_consumers.py")
    scanner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = scanner
    spec.loader.exec_module(scanner)
    current_errors = scanner.run_checks(ROOT)
    scanner.CATALOG_CONSUMER_MARKERS = tuple(s for s in scanner.CATALOG_CONSUMER_MARKERS if s != "require_research_startup")
    prior_errors = scanner.run_checks(ROOT)
    assert current_errors == prior_errors, "new startup marker introduced consumer regression"
    save(out / "test_summary.json", {"commands": commands, "current_consumer_errors": current_errors,
                                      "preexisting_consumer_errors_unchanged": current_errors == prior_errors})
    save(out / "acceptance.json", {"status": "BUNDLE_V2_STARTUP_DELIVERED", **pin,
                                   "startup_core_sha256": sha256_file(ROOT / "src/strategy_lab/data/research_bundle.py"),
                                   "five_component_integrity": "PASS", "real_price_startup": "PASS",
                                   "negative_cases": len(checks), "protected_published_datasets": len(protected),
                                   "targeted_tests_pass": True, "repository_preflight_exit_code": commands["repository_preflight"]["exit_code"],
                                   "consumer_errors": current_errors, "old_consumers_migrated": False,
                                   "full_pit_or_funding_calendar_proven": False, "strategy_approved": False})
    print("Bundle startup acceptance recorded; repository-wide gate status recorded separately", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
