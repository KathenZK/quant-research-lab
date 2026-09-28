#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import yaml

try:
    from .schema_utils import schema_errors
except ImportError:  # Direct script execution.
    from schema_utils import schema_errors


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = (
    ROOT / "docs/research-governance/schemas/lab-live-spec-frontmatter.schema.json"
)
DEFAULT_RUNNER_ROOT = Path("/Users/ZK/OpenCode/quant-runner")
ALLOWED_ROLES = frozenset(
    {
        "lab_handoff",
        "external_reproduction",
        "ensemble_component",
        "live_feasibility",
    }
)
SUPPORTING_SCHEMAS = {
    "external_reproduction": ROOT
    / "docs/research-governance/schemas/live-spec-external-reproduction-frontmatter.schema.json",
    "ensemble_component": ROOT
    / "docs/research-governance/schemas/live-spec-ensemble-component-frontmatter.schema.json",
    "live_feasibility": ROOT
    / "docs/research-governance/schemas/live-spec-live-feasibility-frontmatter.schema.json",
}


def read_frontmatter(path: Path) -> tuple[dict[str, Any], str | None]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "missing YAML front matter"
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, "unterminated YAML front matter"
    data = yaml.safe_load("\n".join(lines[1:end]))
    if not isinstance(data, dict):
        return {}, "front matter must be a mapping"
    return data, None


def implementation_pairs(frontmatter: dict[str, Any]) -> set[tuple[str, str]]:
    if "implementations" in frontmatter:
        return {
            (item.get("strategy_id", ""), item.get("runner_kind", ""))
            for item in frontmatter.get("implementations", [])
            if isinstance(item, dict)
        }
    return {(frontmatter.get("strategy_id", ""), frontmatter.get("runner_kind", ""))}


def iter_live_spec_paths(research_root: Path | None = None) -> list[Path]:
    root = research_root or (ROOT / "research")
    return sorted(
        path
        for path in root.glob("**/live-specs/**/*.md")
        if path.name.lower() != "readme.md"
    )


def peer_spec_paths(frontmatter: dict[str, Any]) -> list[str]:
    if "implementations" in frontmatter:
        values: list[str] = []
        for item in frontmatter.get("implementations", []):
            if isinstance(item, dict) and item.get("peer_spec"):
                values.append(str(item["peer_spec"]))
        return values
    value = frontmatter.get("peer_spec")
    return [str(value)] if value else []


def resolve_runner_root(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return explicit if explicit.is_dir() else None
    env = os.environ.get("QUANT_RUNNER_ROOT")
    candidate = Path(env) if env else DEFAULT_RUNNER_ROOT
    return candidate if candidate.is_dir() else None


def _normalize_posix(value: str) -> str:
    return Path(value).as_posix().lstrip("./")


def _cross_repo_errors(
    path: Path,
    frontmatter: dict[str, Any],
    runner_root: Path,
    lab_root: Path,
) -> list[str]:
    errors: list[str] = []
    expected = path.relative_to(lab_root).as_posix()
    peers = peer_spec_paths(frontmatter)
    if not peers:
        errors.append(f"{path}: active lab_handoff missing peer_spec")
        return errors
    for peer in peers:
        peer_path = runner_root / peer
        if not peer_path.is_file():
            errors.append(
                f"{path}: peer_spec 文件不存在: {peer_path}"
            )
            continue
        peer_fm, parse_error = read_frontmatter(peer_path)
        if parse_error:
            errors.append(f"{path}: runner peer_spec {peer}: {parse_error}")
            continue
        reverse = _normalize_posix(str(peer_fm.get("peer_spec") or ""))
        if reverse != expected:
            errors.append(
                f"{path}: peer_spec 未反向指向本文件: runner 为 {reverse!r}，期望 {expected!r}"
            )
    return errors


def validate(
    schema_path: Path = DEFAULT_SCHEMA,
    research_root: Path | None = None,
    runner_root: Path | None = None,
    skip_cross_repo: bool = False,
    paths: list[Path] | None = None,
) -> list[str]:
    errors, _skips = validate_detailed(
        schema_path=schema_path,
        research_root=research_root,
        runner_root=runner_root,
        skip_cross_repo=skip_cross_repo,
        paths=paths,
    )
    return errors


def validate_detailed(
    schema_path: Path = DEFAULT_SCHEMA,
    research_root: Path | None = None,
    runner_root: Path | None = None,
    skip_cross_repo: bool = False,
    paths: list[Path] | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    skips: list[str] = []
    active_pairs: dict[tuple[str, str], Path] = {}
    declared_specs = 0
    lab_root = ROOT if research_root is None else research_root.parent
    spec_paths = paths if paths is not None else iter_live_spec_paths(research_root)
    resolved_runner: Path | None = None
    run_cross_repo = False
    if not skip_cross_repo:
        resolved_runner = resolve_runner_root(runner_root)
        if resolved_runner is None:
            skips.append(
                "quant-runner 仓库不存在，peer_spec 跨仓校验未执行"
            )
        else:
            run_cross_repo = True

    for path in spec_paths:
        if path.name.lower() == "readme.md":
            continue
        frontmatter, parse_error = read_frontmatter(path)
        if parse_error:
            errors.append(f"{path}: {parse_error}")
            continue
        role = frontmatter.get("spec_role")
        if role not in ALLOWED_ROLES:
            errors.append(
                f"{path}: spec_role {role!r} 不在 {sorted(ALLOWED_ROLES)}"
            )
            continue
        if role == "lab_handoff":
            if frontmatter.get("spec_status") == "superseded":
                continue
            declared_specs += 1
            errors.extend(
                f"{path}: schema: {error}"
                for error in schema_errors(frontmatter, schema_path)
            )
            pairs = implementation_pairs(frontmatter)
            implementations = frontmatter.get("implementations", pairs)
            if len(pairs) != len(implementations):
                errors.append(
                    f"{path}: duplicate strategy_id/runner_kind implementation mapping"
                )
            if frontmatter.get("spec_status") == "active":
                for pair in pairs:
                    previous = active_pairs.get(pair)
                    if previous and previous != path:
                        errors.append(
                            f"{path}: active mapping {pair} duplicates {previous}"
                        )
                    active_pairs[pair] = path
                if run_cross_repo and resolved_runner is not None:
                    errors.extend(
                        _cross_repo_errors(
                            path, frontmatter, resolved_runner, lab_root
                        )
                    )
            continue
        supporting_schema = SUPPORTING_SCHEMAS[role]
        errors.extend(
            f"{path}: schema: {error}"
            for error in schema_errors(frontmatter, supporting_schema)
        )
    if paths is None and declared_specs == 0:
        errors.append("no Lab handoff specs declared with spec_role=lab_handoff")
    return errors, skips


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--skip-cross-repo",
        action="store_true",
        help="跳过 quant-runner peer_spec 跨仓校验",
    )
    args = parser.parse_args()
    selected = None
    if args.paths:
        selected = [
            path if path.is_absolute() else ROOT / path for path in args.paths
        ]
    errors, skips = validate_detailed(
        schema_path=args.schema,
        skip_cross_repo=args.skip_cross_repo,
        paths=selected,
    )
    for note in skips:
        print(f"SKIPPED: {note}")
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors))
        return 1
    print("validated live-spec files under research/**/live-specs/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
