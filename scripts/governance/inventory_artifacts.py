#!/usr/bin/env python3
"""Inventory repository artifact files without reading artifact contents."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "quant-strategy-lab-artifact-inventory"
MIB = 1024 * 1024
FILE_REVIEW_BYTES = 10 * MIB
FILE_EXTERNALIZE_BYTES = 50 * MIB
FILE_GIT_PROHIBITED_BYTES = 100 * MIB
FAMILY_REVIEW_BYTES = 100 * MIB
FAMILY_EXTERNALIZE_BYTES = 500 * MIB

SKIP_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
}
SCRATCH_MARKERS = {"cache", "local", "local-only", "scratch", "temp", "tmp"}
DATASET_SUFFIXES = {
    ".arrow",
    ".db",
    ".duckdb",
    ".feather",
    ".parquet",
    ".sqlite",
}
REGENERABLE_SUFFIXES = {
    ".arrow",
    ".csv",
    ".feather",
    ".joblib",
    ".json",
    ".jsonl",
    ".npy",
    ".npz",
    ".parquet",
    ".pickle",
    ".pkl",
}
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")
ARTIFACT_PATH_RE = re.compile(
    r"(?P<path>(?:(?:\.\.?|[A-Za-z0-9_.-]+)/)*"
    r"artifacts/[A-Za-z0-9_./%+@=-]+)"
)


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _artifact_root(relative_path: Path) -> Path:
    artifact_index = relative_path.parts.index("artifacts")
    return Path(*relative_path.parts[: artifact_index + 1])


def _family_path(relative_path: Path) -> str:
    artifact_root = _artifact_root(relative_path)
    parent = artifact_root.parent
    return parent.as_posix() if parent.parts else "."


def _git_visible_relative_paths(root: Path) -> set[str] | None:
    """Return git-tracked plus untracked-not-ignored paths, or None if not a repo."""
    if not (root / ".git").exists():
        return None

    def _ls(extra: list[str]) -> set[str] | None:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", *extra],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return {
            item
            for item in proc.stdout.decode("utf-8", "replace").split("\0")
            if item
        }

    tracked = _ls([])
    others = _ls(["--others", "--exclude-standard"])
    if tracked is None or others is None:
        return None
    return tracked | others


def iter_artifact_files(root: Path) -> list[Path]:
    """Return files below directories named artifacts, using metadata only."""
    visible = _git_visible_relative_paths(root)
    if visible is not None:
        files: list[Path] = []
        for rel in sorted(visible):
            relative = Path(rel)
            if "artifacts" not in relative.parts:
                continue
            path = root / relative
            if path.is_file() and not path.is_symlink():
                files.append(path)
        return files

    files = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in SKIP_DIR_NAMES
            and not (Path(current) / name).is_symlink()
        )
        current_path = Path(current)
        current_relative = current_path.relative_to(root)
        if "artifacts" not in current_relative.parts:
            continue
        files.extend(
            current_path / name
            for name in sorted(file_names)
            if not (current_path / name).is_symlink()
        )
    return files


def iter_reference_markdown(root: Path) -> list[Path]:
    """Return Markdown sources, excluding artifact trees and tool caches."""
    markdown: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in SKIP_DIR_NAMES
            and name != "artifacts"
            and not (Path(current) / name).is_symlink()
        )
        current_path = Path(current)
        markdown.extend(
            current_path / name for name in sorted(file_names) if name.endswith(".md")
        )
    return markdown


def _resolve_reference(target: str, source: Path, root: Path) -> str | None:
    target = unquote(target.strip("<>`'\""))
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    path_text = parsed.path.rstrip(".,;:")
    if not path_text:
        return None
    candidate = Path(path_text)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(root).as_posix()
        except ValueError:
            return None
    if candidate.parts and candidate.parts[0] in {
        "archive",
        "docs",
        "research",
        "scripts",
        "tests",
    }:
        resolved = (root / candidate).resolve()
    else:
        resolved = (source.parent / candidate).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return None


def collect_markdown_references(
    root: Path, artifact_paths: set[str]
) -> dict[str, list[str]]:
    """Map exact artifact file paths to Markdown files that reference them."""
    references: dict[str, set[str]] = defaultdict(set)
    for markdown_path in iter_reference_markdown(root):
        text = markdown_path.read_text(encoding="utf-8", errors="replace")
        targets = [match.group(1) for match in MARKDOWN_LINK_RE.finditer(text)]
        targets.extend(match.group("path") for match in ARTIFACT_PATH_RE.finditer(text))
        source_relative = _relative(markdown_path, root)
        for target in targets:
            resolved = _resolve_reference(target, markdown_path, root)
            if resolved in artifact_paths:
                references[resolved].add(source_relative)
    return {path: sorted(sources) for path, sources in references.items()}


def file_budget_tier(size_bytes: int) -> str:
    if size_bytes > FILE_GIT_PROHIBITED_BYTES:
        return "D-prohibited-new-git"
    if size_bytes > FILE_EXTERNALIZE_BYTES:
        return "C-externalize"
    if size_bytes > FILE_REVIEW_BYTES:
        return "B-review"
    return "A-normal"


def family_budget_tier(size_bytes: int) -> str:
    if size_bytes > FAMILY_EXTERNALIZE_BYTES:
        return "C-externalize"
    if size_bytes > FAMILY_REVIEW_BYTES:
        return "B-review"
    return "A-normal"


def retention_class(path: str, size_bytes: int, referenced: bool) -> str:
    parts = {part.lower() for part in Path(path).parts}
    suffix = Path(path).suffix.lower()
    if parts & SCRATCH_MARKERS:
        return "scratch"
    if referenced:
        return "normative-evidence"
    if suffix in DATASET_SUFFIXES:
        return "local-dataset"
    if size_bytes > FILE_REVIEW_BYTES and suffix in REGENERABLE_SUFFIXES:
        return "regenerable-large"
    return "retained-unclassified"


def build_inventory(root: Path, generated_at: str | None = None) -> dict[str, object]:
    root = root.resolve()
    artifact_files = iter_artifact_files(root)
    artifact_paths = {_relative(path, root) for path in artifact_files}
    references = collect_markdown_references(root, artifact_paths)

    file_rows: list[dict[str, object]] = []
    family_files: dict[str, list[dict[str, object]]] = defaultdict(list)
    artifact_roots: set[str] = set()
    for path in artifact_files:
        relative_path = Path(_relative(path, root))
        relative = relative_path.as_posix()
        size_bytes = path.stat().st_size
        referenced_by = references.get(relative, [])
        row = {
            "path": relative,
            "family_path": _family_path(relative_path),
            "artifact_root": _artifact_root(relative_path).as_posix(),
            "size_bytes": size_bytes,
            "referenced": bool(referenced_by),
            "referenced_by": referenced_by,
            "budget_tier": file_budget_tier(size_bytes),
            "retention_class": retention_class(
                relative, size_bytes, bool(referenced_by)
            ),
        }
        file_rows.append(row)
        family_files[str(row["family_path"])].append(row)
        artifact_roots.add(str(row["artifact_root"]))

    file_rows.sort(key=lambda row: str(row["path"]))
    family_rows: list[dict[str, object]] = []
    for family_path, rows in sorted(family_files.items()):
        total_bytes = sum(int(row["size_bytes"]) for row in rows)
        referenced_count = sum(bool(row["referenced"]) for row in rows)
        max_row = max(rows, key=lambda row: int(row["size_bytes"]))
        family_rows.append(
            {
                "family_path": family_path,
                "artifact_roots": sorted(
                    {str(row["artifact_root"]) for row in rows}
                ),
                "file_count": len(rows),
                "total_bytes": total_bytes,
                "max_file": {
                    "path": max_row["path"],
                    "size_bytes": max_row["size_bytes"],
                },
                "referenced_file_count": referenced_count,
                "reference_coverage_pct": round(
                    referenced_count * 100 / len(rows), 2
                ),
                "budget_tier": family_budget_tier(total_bytes),
            }
        )

    total_bytes = sum(int(row["size_bytes"]) for row in file_rows)
    referenced_count = sum(bool(row["referenced"]) for row in file_rows)
    for row in file_rows:
        # Family summaries retain this derivable grouping; omit repeated values from
        # the 40k+ row machine detail to keep the generated inventory compact.
        del row["family_path"]
        del row["artifact_root"]
        if not row["referenced_by"]:
            del row["referenced_by"]
        if row["budget_tier"] == "A-normal":
            del row["budget_tier"]
        if row["retention_class"] == "retained-unclassified":
            del row["retention_class"]
    generated = generated_at or dt.datetime.now(dt.timezone.utc).isoformat(
        timespec="seconds"
    )
    return {
        "schema_version": "1.0",
        "generated_at": generated,
        "root": ".",
        "scope": {
            "artifact_directory_name": "artifacts",
            "artifact_content_read": False,
            "markdown_reference_sources_exclude_artifacts": True,
            "symlinks_followed": False,
            "skipped_directory_names": sorted(SKIP_DIR_NAMES),
        },
        "file_defaults": {
            "referenced_by": [],
            "budget_tier": "A-normal",
            "retention_class": "retained-unclassified",
        },
        "budget_policy": {
            "file_review_bytes": FILE_REVIEW_BYTES,
            "file_externalize_bytes": FILE_EXTERNALIZE_BYTES,
            "file_git_prohibited_bytes": FILE_GIT_PROHIBITED_BYTES,
            "family_review_bytes": FAMILY_REVIEW_BYTES,
            "family_externalize_bytes": FAMILY_EXTERNALIZE_BYTES,
        },
        "summary": {
            "artifact_root_count": len(artifact_roots),
            "family_count": len(family_rows),
            "file_count": len(file_rows),
            "total_bytes": total_bytes,
            "referenced_file_count": referenced_count,
            "reference_coverage_pct": round(
                referenced_count * 100 / len(file_rows), 2
            )
            if file_rows
            else 0.0,
        },
        "families": family_rows,
        "files": file_rows,
    }


def _human_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < MIB:
        return f"{value / 1024:.1f} KiB"
    if value < 1024 * MIB:
        return f"{value / MIB:.1f} MiB"
    return f"{value / (1024 * MIB):.2f} GiB"


def render_markdown(inventory: dict[str, object], json_name: str) -> str:
    summary = inventory["summary"]
    assert isinstance(summary, dict)
    families = inventory["families"]
    assert isinstance(families, list)
    lines = [
        "# Artifacts 全仓清单",
        "",
        f"- 生成时间（UTC）：`{inventory['generated_at']}`",
        "- 口径：只读取路径、文件元数据与 artifacts 目录外 Markdown 的引用目标；"
        "不读取 artifacts 文件内容，不跟随符号链接。",
        f"- artifacts 根目录：{summary['artifact_root_count']} 个；"
        f"家族/主题：{summary['family_count']} 个；文件：{summary['file_count']} 个。",
        f"- 总大小：{_human_bytes(int(summary['total_bytes']))}；"
        f"被 Markdown 精确引用：{summary['referenced_file_count']} 个"
        f"（{summary['reference_coverage_pct']}%）。",
        f"- 逐文件机器明细见 [`{json_name}`]({json_name})；本页不展开逐文件列表。",
        "",
        "## 家族/主题汇总",
        "",
        "| 家族/主题路径 | 文件数 | 总大小 | 最大文件 | 引用覆盖率 | 预算级别 |",
        "| --- | ---: | ---: | --- | ---: | --- |",
    ]
    for family in families:
        assert isinstance(family, dict)
        maximum = family["max_file"]
        assert isinstance(maximum, dict)
        lines.append(
            f"| `{family['family_path']}` | {family['file_count']} | "
            f"{_human_bytes(int(family['total_bytes']))} | "
            f"`{maximum['path']}` "
            f"({_human_bytes(int(maximum['size_bytes']))}) | "
            f"{family['referenced_file_count']}/{family['file_count']} "
            f"({family['reference_coverage_pct']}%) | `{family['budget_tier']}` |"
        )
    lines.extend(
        [
            "",
            "## 解释限制",
            "",
            "- “被引用”仅表示 artifacts 目录外 Markdown 对具体文件的精确链接或路径引用；"
            "目录级链接、代码中的读取、动态拼接路径不计入。",
            "- 保留类别是基于路径、后缀、大小与引用状态的治理提示，不是删除授权。",
            "- 本清单不证明产物正确、可复现或仍被运行时代码使用。",
            "",
        ]
    )
    return "\n".join(lines)


def write_inventory(
    inventory: dict[str, object], json_output: Path, markdown_output: Path
) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(inventory, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    markdown_output.write_text(
        render_markdown(inventory, json_output.name),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory artifact paths, sizes, counts, and Markdown references."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "artifact-inventory.json",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / "artifact-inventory.md",
    )
    args = parser.parse_args()
    inventory = build_inventory(args.root)
    write_inventory(inventory, args.json_output, args.markdown_output)
    summary = inventory["summary"]
    assert isinstance(summary, dict)
    print(
        f"Inventoried {summary['file_count']} files across "
        f"{summary['family_count']} families: {_human_bytes(int(summary['total_bytes']))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
