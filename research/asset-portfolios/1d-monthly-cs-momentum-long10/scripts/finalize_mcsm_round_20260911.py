"""Final bounded QA, export checks and immutable completion receipt for this round."""
from __future__ import annotations

import hashlib
import gzip
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY.parents[2]
ROUND = FAMILY / "artifacts/drawdown-frequency-round-20260911"
DELIVERY = ROOT / "outputs/mcsm-20260911-drawdown-frequency"
REPORT = FAMILY / "diagnostics/binance-1d-mcsm-drawdown-frequency-round-20260911.md"
XLSX = DELIVERY / "Top10_月度持仓盈亏与年度比较_20260911.xlsx"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def run(args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
    return {"args": args, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def workbook_xml_check():
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    errors, formulas, sheets, tables = [], 0, [], []
    with zipfile.ZipFile(XLSX) as archive:
        for name in archive.namelist():
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name):
                doc = ET.fromstring(archive.read(name))
                for cell in doc.findall(".//s:c", ns):
                    if cell.attrib.get("t") == "e":
                        errors.append({"sheet": name, "cell": cell.attrib.get("r"), "value": cell.findtext("s:v", namespaces=ns)})
                    if cell.find("s:f", ns) is not None:
                        formulas += 1
                rows = doc.findall(".//s:sheetData/s:row", ns)
                if any(row.attrib.get("hidden") == "1" for row in rows):
                    raise ValueError("export unexpectedly hides data rows")
                dimension = doc.find("s:dimension", ns)
                sheets.append({"file": name, "rows": len(rows), "dimension": dimension.attrib.get("ref") if dimension is not None else None})
            if re.fullmatch(r"xl/tables/table\d+\.xml", name):
                doc = ET.fromstring(archive.read(name))
                if doc.find("s:autoFilter", ns) is None:
                    raise ValueError("filterable table lost filter")
                tables.append({"name": doc.attrib.get("name"), "ref": doc.attrib["ref"]})
    if errors or len(sheets) != 7 or len(tables) != 7 or formulas < 1000:
        raise ValueError(f"workbook XML failed: errors={errors}, sheets={len(sheets)}, tables={len(tables)}, formulas={formulas}")
    return {"status": "PASS_EXPORTED_XML_FORMULAS_FILTERS_NO_HIDDEN_ROWS", "formula_count": formulas,
            "error_cells": errors, "sheets": sheets, "tables": tables, "xlsx_sha256": sha(XLSX)}


def main():
    if (ROUND / "completion.json").exists():
        raise FileExistsError(ROUND / "completion.json")
    old = json.loads((FAMILY / "artifacts/mechanism-round-20260910/completion.json").read_text())
    for relative, expected in old["files_sha256"].items():
        if sha(ROOT / relative) != expected:
            raise ValueError(f"frozen previous-round file changed: {relative}")
    contract = FAMILY / "specs/binance-1d-mcsm-drawdown-frequency-round-20260911.md"
    if sha(contract) != "aa38d87cf3cb374d4f587faf3660586950986bfa2a25813e851d65c28862d2d4":
        raise ValueError("contract changed")
    text = REPORT.read_text()
    if "本节尚未发布" in text or "周频分支仍在" in text:
        raise ValueError("report still contains an unfinished research statement")
    paths = subprocess.run(["rg", "--files", "tests"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    tests = sorted(p for p in paths if Path(p).name.startswith("test_mcsm") and p.endswith(".py"))
    test_run = run([str(ROOT / ".venv/bin/python"), "-m", "pytest", *tests, "-q"])
    scripts = sorted(FAMILY.joinpath("scripts").glob("*20260911.py"))
    lint = run([str(ROOT / ".venv/bin/ruff"), "check", *[str(p.relative_to(ROOT)) for p in scripts],
                *[t for t in tests if "20260911" in t]])
    registry = run([str(ROOT / ".venv/bin/python"), "scripts/governance/check_trusted_consumers.py"])
    own_errors = [line for line in registry["stdout"].splitlines() if line.startswith("ERROR:") and "1d-monthly-cs-momentum-long10" in line]
    xml = workbook_xml_check()
    workbook_qa = json.loads((DELIVERY / "workbook-qa.json").read_text())
    if not workbook_qa["sensitivityCheckRestored"] or not workbook_qa["renderedEverySheet"]:
        raise ValueError("workbook final verification incomplete")
    visual = json.loads((DELIVERY / "workbook-visual-review.json").read_text())
    if visual["status"] != "PASS_ALL_SEVEN_SHEETS_VISUALLY_INSPECTED" or len(visual["previews_sha256"]) != 7:
        raise ValueError("workbook visual review incomplete")
    for relative, expected in visual["previews_sha256"].items():
        if sha(DELIVERY / relative) != expected:
            raise ValueError("preview changed after visual review")
    log = json.loads((DELIVERY / "workbook-log-archive.json").read_text())
    log_hash, log_bytes = hashlib.sha256(), 0
    with gzip.open(DELIVERY / log["archive_path"], "rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            log_hash.update(chunk)
            log_bytes += len(chunk)
    if log_hash.hexdigest() != log["uncompressed_sha256"] or log_bytes != log["uncompressed_bytes"]:
        raise ValueError("compressed workbook inspection log failed lossless verification")
    missing_links = []
    for doc in [REPORT, FAMILY / "README.md", FAMILY / "binance-1d-mcsm-l10-core-ledger.md",
                FAMILY / "decision-log.md", FAMILY / "scripts/README.md", FAMILY / "artifacts/README.md", ROUND / "README.md"]:
        for match in re.finditer(r"\]\(([^)]+)\)", doc.read_text()):
            target = match.group(1).split("#")[0]
            if not target or "://" in target:
                continue
            resolved = (doc.parent / target).resolve()
            if resolved in {ROUND / "qa.json", ROUND / "completion.json"}:
                continue  # These two declared receipts are created by this successful run.
            if not resolved.exists():
                missing_links.append({"doc": str(doc.relative_to(ROOT)), "target": target})
    size = sum(p.stat().st_size for p in ROUND.rglob("*") if p.is_file())
    size += sum(p.stat().st_size for p in DELIVERY.rglob("*") if p.is_file())
    qa = {"tests": test_run, "lint": lint, "trusted_consumer": registry, "own_family_registry_errors": own_errors,
          "workbook_xml": xml, "missing_links": missing_links, "new_bytes": size,
          "budget_bytes": 100*1024**2, "old_frozen_files_verified": len(old["files_sha256"])}
    save(ROUND / "qa.json", qa)
    if test_run["exit_code"] or lint["exit_code"] or own_errors or missing_links or size > 100*1024**2:
        raise ValueError("round final QA failed; see preserved qa.json")
    weekly = json.loads((ROUND / "independent-audit/weekly-summary.json").read_text())
    checked = [contract, REPORT, XLSX, DELIVERY / "workbook-qa.json", DELIVERY / "workbook-visual-review.json",
               DELIVERY / "workbook-log-archive.json", DELIVERY / log["archive_path"],
               FAMILY / "scripts/build_mcsm_round_workbook_20260911.mjs", ROUND / "qa.json", ROUND / "README.md",
               ROUND / "broader-exit/summary.json", ROUND / "drawdown/summary.json",
               ROUND / "drawdown/independent-detail-audit.json", ROUND / "weekly/summary.json",
               ROUND / "weekly/postrun-integrity.json", ROUND / "weekly/future-input-gaps.json",
               ROUND / "independent-audit/breadth-summary.json", ROUND / "independent-audit/drawdown-summary.json",
               ROUND / "independent-audit/weekly-summary.json", ROUND / "independent-audit/bzrx-missing-endpoint-cause.md",
               ROUND / "independent-audit/keep-missing-endpoint-cause.md",
               ROUND / "delivery/workbook-data.json", *scripts]
    result = {"status": "RESEARCH_AND_DELIVERY_COMPLETE_NOT_LIVE_READY", "contract_sha256": sha(contract),
              "new_breadth_accounts": 8, "drawdown_original_accounts": 4, "weekly_prescribed_accounts": 8,
              "weekly_complete_price_accounts": sum(r["status"].startswith("INDEPENDENT_PRICE_ACCOUNT") for r in weekly["results"]),
              "weekly_confirmed_missing_input_accounts": sum(r["status"].startswith("CONFIRMED_FIRST_MISSING") for r in weekly["results"]),
              "workbook_counts": workbook_qa["counts"], "new_bytes_before_completion": size,
              "repository_wide_registry_passed": registry["exit_code"] == 0, "own_family_registry_passed": not own_errors,
              "files_sha256": {str(p.relative_to(ROOT)): sha(p) for p in checked}}
    save(ROUND / "completion.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
