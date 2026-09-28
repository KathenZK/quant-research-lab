"""Offline root acceptance: retained-file hashes and independent accounting.

Does not rerun strategy selection or fetch markets. Each family documents and
retains its separate full-engine replay. Output stays in this diagnostic topic.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

TOPIC = Path(__file__).resolve().parents[1]
ROOT = TOPIC.parents[2]
OUT = TOPIC / "artifacts"
FAMILIES = {
    "A": ROOT / "research/asset-portfolios/1d-small-account-slow-trend",
    "B": ROOT / "research/asset-portfolios/1d-tpsa-long-account",
    "C": ROOT / "research/asset-portfolios/8h-btceth-small-account-carry",
}


def read(path):
    return json.loads(path.read_text())


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_manifest(base, path):
    data = read(path)
    entries = data["files"] if "files" in data else [
        {"path": name, "sha256": digest} for name, digest in data.items()
    ]
    errors = []
    for entry in entries:
        target = base / entry["path"]
        if not target.is_file() or sha(target) != entry["sha256"]:
            errors.append(entry["path"])
    assert not errors, {str(path): errors}
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path), "verified_files": len(entries), "mismatches": []}


def run_audit(name):
    script = TOPIC / "scripts" / name
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, str(script)], cwd=ROOT, env=env, text=True, capture_output=True)
    (OUT / f"{script.stem}.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, {name: result.stderr[-3000:]}
    return {"script": str(script.relative_to(ROOT)), "sha256": sha(script), "exit_code": result.returncode}


def comparison():
    a = read(FAMILIES["A"] / "artifacts/summary.json")
    b = read(FAMILIES["B"] / "artifacts/summary.json")
    c = read(FAMILIES["C"] / "artifacts/results/summary.json")
    rows = []
    for variant in ("trend_12m_risk10", "static_risk10", "static_equal_weight"):
        m = next(v for v in a["variant_metrics"] if v["variant"] == variant)
        rows.append(dict(line="A", family=a["family"], object=variant, initial_capital_usd=10000,
            start=a["coverage"]["start"], end=a["coverage"]["end"], final_equity_usd=m["final_equity_usd"],
            pnl_usd=m["net_profit_usd"], period_return=m["total_return"], cagr=m["cagr"],
            max_drawdown=m["max_drawdown"], sampling="daily close plus seed", evidence="conditional fees, distributions and execution"))
    m = b["primary"]
    rows.append(dict(line="B", family=b["family"], object=m["variant"], initial_capital_usd=10000,
        start=b["coverage"]["account_start"], end=b["coverage"]["account_end"],
        final_equity_usd=m["final_equity_ex_actual_funding"], pnl_usd=m["final_equity_ex_actual_funding"] - 10000,
        period_return=m["return_ex_actual_funding"], cagr=None, max_drawdown=m["max_drawdown_ex_actual_funding"],
        sampling="daily account plus terminal close", evidence="actual funding unknown, ideal open and continuous lot proxy"))
    for asset, metrics in c["assets"].items():
        m = metrics["perpetual_history_base"]
        rows.append(dict(line="C", family=c["family"], object=asset + " linear perpetual", initial_capital_usd=10000,
            start=m["start_utc"], end=m["end_utc"], final_equity_usd=m["final_equity_usd"], pnl_usd=m["net_pnl_usd_proxy"],
            period_return=m["net_return_pct"] / 100, cagr=None, max_drawdown=m["hourly_mdd_pct"] / 100,
            sampling="hourly observed", evidence=m["evidence_class"]))
        q = metrics["expiry_selected_first_valid_else_first"]
        rows.append(dict(line="C", family=c["family"], object=q["instrument"] + " conditional expiry quote", initial_capital_usd=10000,
            start="2026-09-08T13:00:42Z quote capture", end="2026-10-30; not yet realized",
            final_equity_usd=None, pnl_usd=q["conditional_flat_terminal_net_usd"],
            period_return=q["conditional_full_account_return_pct"] / 100, cagr=None, max_drawdown=None,
            sampling="single quote; no future account", evidence="terminal spot=index and USDT=USD assumptions; not realized"))
    value = {"capital_policy": "Every row is a separate USD10000 account; not additive", "historical_exposure": "REUSED_DIAGNOSTIC_NO_BLIND_OOS",
        "qualified_candidates": [], "next_priority": "A same-pool static account distribution and execution admissibility; post-result proposal", "rows": rows}
    write("comparison.json", value)
    with (OUT / "comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return value


def governance():
    path = ROOT / "scripts/governance/check_trusted_consumers.py"
    spec = importlib.util.spec_from_file_location("three_line_checker", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    errors = module.run_checks(ROOT)
    relevant = [str(p.relative_to(ROOT)) for p in [*FAMILIES.values(), TOPIC]]
    scoped = [error for error in errors if any(prefix in error for prefix in relevant)]
    assert not scoped, scoped
    # Compare old checker on the same tree to identify, not repair, inherited failures.
    old = subprocess.run(["git", "show", "HEAD:scripts/governance/check_trusted_consumers.py"], cwd=ROOT, text=True, capture_output=True, check=True)
    old_module = type(sys)("three_line_base_checker")
    sys.modules[old_module.__name__] = old_module
    exec(compile(old.stdout, str(path), "exec"), old_module.__dict__)
    old_errors = old_module.run_checks(ROOT)
    inherited = [error for error in errors if error in old_errors]
    assert len(inherited) == len(errors), {"new_global_errors": [e for e in errors if e not in old_errors]}
    result = {"scoped_errors": scoped, "global_errors": errors, "global_failure_count": len(errors),
        "all_remaining_errors_also_present_with_HEAD_checker": True, "checker_sha256": sha(path),
        "no_frozen_whitelist_changes": True, "scope_is_not_whole_repository_pass": True}
    write("governance-scan.json", result)
    return result


def links():
    errors = []
    checked = 0
    for base in [*FAMILIES.values(), TOPIC]:
        for md in base.rglob("*.md"):
            if "__pycache__" in md.parts:
                continue
            for target in re.findall(r"\]\(([^)]+)\)", md.read_text()):
                target = target.strip("<>").split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                # Optional app-local line reference is not part of the filename.
                target = re.sub(r":\d+$", "", target)
                checked += 1
                if not (md.parent / target).exists():
                    errors.append({"document": str(md.relative_to(ROOT)), "target": target})
    assert not errors, errors
    return {"local_links_checked": checked, "errors": errors}


def main():
    manifests = [verify_manifest(FAMILIES["A"], FAMILIES["A"] / "artifacts/hashes.json"),
        verify_manifest(FAMILIES["B"], FAMILIES["B"] / "artifacts/artifact_manifest.json"),
        verify_manifest(FAMILIES["C"], FAMILIES["C"] / "artifacts/input_manifest.json"),
        verify_manifest(FAMILIES["C"], FAMILIES["C"] / "artifacts/output_manifest.json")]
    context = read(OUT / "context-source-manifest.json")
    for item in context["sources"]:
        assert sha(Path(item["path"])) == item["sha256"], {"context_source_drift": item["path"]}
    scripts = ["independent_math_oracles.py", "audit_a_ledgers.py", "audit_b_ledgers.py", "audit_c_ledgers.py"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        audits = list(pool.map(run_audit, scripts))
    replays = {
        "A": read(FAMILIES["A"] / "artifacts/offline-reproduction-evidence.json"),
        "B": read(FAMILIES["B"] / "artifacts/one_click_reproduction_audit.json"),
        "C": read(FAMILIES["C"] / "artifacts/offline_replay_validation.json"),
    }
    assert replays["A"]["status"] == "PASS" and not replays["A"]["mismatches"]
    assert replays["B"]["completed"] and replays["B"]["all_compared_byte_identical"]
    assert replays["C"]["status"] == "PASS_OFFLINE_REPLAY"
    comparison()
    gov = governance()
    result = {"status": "VERIFYING_FINAL_LINKS", "strategy_approval": False,
        "completed_utc": datetime.now(timezone.utc).isoformat(), "manifests": manifests,
        "context_source_hashes_unchanged": len(context["sources"]), "independent_audits": audits,
        "retained_full_engine_replay_files": {"A": replays["A"]["exact_output_files_compared"], "B": replays["B"]["compared_files"], "C": len(replays["C"]["byte_identical_outputs"])},
        "note": "The root reruns its independent accountants; full-engine replays were separately executed and their evidence retained. No fresh market/OOS or actual fills claimed.",
        "links": None, "governance_scoped_errors": gov["scoped_errors"], "inherited_global_failures": gov["global_failure_count"],
        "qualified_candidates": [], "next_priority": "Same-pool static ETF account: issuer distribution and execution admissibility"}
    write("independent-acceptance.json", result)
    result["links"] = links()
    result["status"] = "FIRST_ROUND_RESEARCH_ACCEPTED_WITH_EXPLICIT_LIMITATIONS"
    write("independent-acceptance.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
