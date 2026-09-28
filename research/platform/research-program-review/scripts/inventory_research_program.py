"""Snapshot research-document inventory; never reads or changes market data."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TOPIC = Path(__file__).resolve().parents[1]
OUTPUT = TOPIC / "artifacts" / "research-inventory-2026-09-08.json"


def snapshot(path: Path) -> dict:
    raw = path.read_bytes()
    lines = raw.decode("utf-8").splitlines()
    evidence = [
        {"line": i, "text": line}
        for i, line in enumerate(lines, 1)
        if re.search(r"当前.*状态|研究状态|唯一结论|主状态|^[- ]*状态[：:]", line)
    ]
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "line_count": len(lines),
        "status_text_candidates_not_adjudications": evidence[:8],
    }


def main() -> None:
    ledgers = sorted((ROOT / "research").rglob("*core-ledger.md"))
    rows = []
    for ledger in ledgers:
        row = snapshot(ledger)
        row["asset_directory"] = ledger.relative_to(ROOT).parts[1]
        readme = ledger.parent / "README.md"
        row["family_readme"] = snapshot(readme) if readme.exists() else None
        rows.append(row)
    external_scripts = [p for p in (ROOT / "research").rglob("*.py") if not p.is_relative_to(TOPIC)]
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "All research/**/*core-ledger.md and their same-directory README. Metadata inventory is not full strategy reproduction or current runtime verification.",
        "counts": {
            "core_ledgers": len(ledgers),
            "by_asset_directory": dict(sorted(Counter(r["asset_directory"] for r in rows).items())),
            "ledger_directories_containing_ma7": sum("ma7" in str(p.parent.relative_to(ROOT)) for p in ledgers),
            "research_python_excluding_this_audit": len(external_scripts),
            "shared_src_python": len(list((ROOT / "src/strategy_lab").rglob("*.py"))),
            "top_level_test_files": len(list((ROOT / "tests").glob("test_*.py"))),
            "archive_research_markdown": len(list((ROOT / "archive/research").rglob("*.md"))),
        },
        "interpretation_limit": "Counts are files/directories, not independent hypotheses, independent trials, invested effort, or profitable strategy counts. Status snippets can refer to historical versions.",
        "ledgers": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
