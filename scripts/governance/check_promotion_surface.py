#!/usr/bin/env python3
"""检查 dry-run/live 的 active lab_handoff 是否携带完整 runner 证据。"""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .schema_utils import load_json, schema_errors
    from .validate_live_specs import (
        ROOT,
        iter_live_spec_paths,
        read_frontmatter,
    )
except ImportError:  # Direct script execution.
    from schema_utils import load_json, schema_errors
    from validate_live_specs import ROOT, iter_live_spec_paths, read_frontmatter


PROMOTED_STATUSES = frozenset({"dry-run", "live"})
PARITY_SCHEMA = ROOT / "docs/research-governance/schemas/parity-report.schema.json"
STALE_TRACKING_DAYS = 45
_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def family_dir_for_live_spec(path: Path) -> Path:
    current = path.parent
    while current != current.parent:
        if current.name == "live-specs":
            return current.parent
        current = current.parent
    raise ValueError(f"{path}: 找不到 live-specs 祖先目录")


def iter_active_promoted_handoffs(
    research_root: Path | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    promoted: list[tuple[Path, dict[str, Any]]] = []
    for path in iter_live_spec_paths(research_root):
        frontmatter, parse_error = read_frontmatter(path)
        if parse_error:
            continue
        if frontmatter.get("spec_role") != "lab_handoff":
            continue
        if frontmatter.get("spec_status") != "active":
            continue
        if frontmatter.get("main_status") not in PROMOTED_STATUSES:
            continue
        promoted.append((path, frontmatter))
    return promoted


def tracking_report_paths(family_dir: Path) -> list[Path]:
    tracking = family_dir / "runner-tracking"
    if not tracking.is_dir():
        return []
    return sorted(
        path
        for path in tracking.rglob("*")
        if path.is_file() and path.name.lower() != "readme.md"
    )


def _dates_from_text(text: str) -> list[date]:
    found: list[date] = []
    for match in _DATE_RE.findall(text):
        try:
            found.append(date.fromisoformat(match))
        except ValueError:
            continue
    return found


def latest_tracking_date(family_dir: Path) -> date | None:
    reports = [
        path
        for path in tracking_report_paths(family_dir)
        if path.suffix.lower() == ".md"
    ]
    dates: list[date] = []
    for path in reports:
        dates.extend(_dates_from_text(path.name))
    if dates:
        return max(dates)
    for path in reports:
        sample = path.read_text(encoding="utf-8")[:4000]
        dates.extend(_dates_from_text(sample))
    if dates:
        return max(dates)
    mtimes: list[date] = []
    for path in reports:
        mtimes.append(
            datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date()
        )
    return max(mtimes) if mtimes else None


def iter_family_parity_candidates(family_dir: Path) -> list[Path]:
    artifacts = family_dir / "artifacts"
    if not artifacts.is_dir():
        return []
    return sorted(
        path
        for path in artifacts.rglob("*parity*.json")
        if path.is_file()
    )


def family_has_valid_parity_evidence(family_dir: Path) -> bool:
    for path in iter_family_parity_candidates(family_dir):
        try:
            report = load_json(path)
        except (OSError, ValueError):
            continue
        if schema_errors(report, PARITY_SCHEMA):
            continue
        if report.get("conclusion") == "MISSING_EVIDENCE":
            continue
        return True
    return False


def check_promotion_surface(
    research_root: Path | None = None,
    today: date | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    as_of = today or date.today()
    for path, frontmatter in iter_active_promoted_handoffs(research_root):
        family_id = str(frontmatter.get("family_id") or path.parent.name)
        strategy_id = str(
            frontmatter.get("strategy_id")
            or ",".join(
                str(item.get("strategy_id", ""))
                for item in frontmatter.get("implementations", [])
                if isinstance(item, dict)
            )
            or path.stem
        )
        label = f"{family_id} ({strategy_id})"
        family_dir = family_dir_for_live_spec(path)
        reports = tracking_report_paths(family_dir)
        if not reports:
            errors.append(
                f"{label}: 家族目录缺少非空 runner-tracking/（{family_dir / 'runner-tracking'}）"
            )
        else:
            latest = latest_tracking_date(family_dir)
            if latest is not None and (as_of - latest).days > STALE_TRACKING_DAYS:
                warnings.append(
                    f"{label}: 最新 runner-tracking 报告日期 {latest.isoformat()} "
                    f"距今 {(as_of - latest).days} 天（阈值 {STALE_TRACKING_DAYS} 天）"
                )
        if not family_has_valid_parity_evidence(family_dir):
            errors.append(
                f"{label}: 家族 artifacts/ 缺少符合 parity-report.schema.json "
                "且 conclusion ≠ MISSING_EVIDENCE 的报告"
            )
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="用于陈旧报告计算的日期，默认今天",
    )
    args = parser.parse_args()
    errors, warnings = check_promotion_surface(today=args.as_of)
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1
    promoted = iter_active_promoted_handoffs()
    if not promoted:
        print("没有 dry-run/live 的 active lab_handoff；promotion surface 跳过硬证据检查")
        return 0
    print(
        f"checked {len(promoted)} dry-run/live active lab_handoff promotion surfaces"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
