#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .check_promotion_surface import iter_active_promoted_handoffs
    from .schema_utils import load_json, schema_errors
except ImportError:  # Direct script execution.
    from check_promotion_surface import iter_active_promoted_handoffs
    from schema_utils import load_json, schema_errors

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "docs/research-governance/schemas/parity-report.schema.json"


def _discover_reports() -> dict[Path, list[dict]]:
    discovered: dict[Path, list[dict]] = {}
    for path in sorted((ROOT / "research").glob("**/artifacts/*parity*.json")):
        report = load_json(path)
        required_identity = {
            "schema_version",
            "strategy_id",
            "runner_kind",
            "trade_path",
            "conclusion",
        }
        if required_identity.issubset(report):
            discovered[path] = []
    return discovered


def _validate_report(
    path: Path,
    schema_path: Path,
    _references: list[dict],
) -> list[str]:
    if path.suffix.lower() != ".json":
        return [f"{path}: parity evidence must be a standardized JSON artifact"]
    if not path.is_file():
        return [f"{path}: parity artifact does not exist"]
    report = load_json(path)
    errors = [f"{path}: schema: {error}" for error in schema_errors(report, schema_path)]
    trade_path = report.get("trade_path", {})
    if report.get("conclusion") == "PASS":
        if trade_path.get("reference_trades") != trade_path.get("runtime_trades"):
            errors.append(f"{path}: PASS report trade counts differ")
    return errors


def promoted_requires_parity_reports(
    discovered_count: int,
    has_promoted: bool | None = None,
) -> list[str]:
    if has_promoted is None:
        has_promoted = bool(iter_active_promoted_handoffs())
    if has_promoted and discovered_count == 0:
        return [
            "存在 dry-run/live 的 active lab_handoff，但仓库内标准化 parity 报告数为 0"
        ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="*", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args()
    discovered = _discover_reports()
    errors: list[str] = []
    for path in args.reports:
        resolved = path if path.is_absolute() else ROOT / path
        discovered.setdefault(resolved, [])
    for path, references in sorted(discovered.items(), key=lambda item: str(item[0])):
        errors.extend(_validate_report(path, args.schema, references))
    errors.extend(promoted_requires_parity_reports(len(discovered)))
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1
    print(f"validated {len(discovered)} standardized parity reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
