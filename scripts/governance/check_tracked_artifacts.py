#!/usr/bin/env python3
"""Fail if a tracked research artifact is not on the allowlist."""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALLOWLIST = (
    ROOT / "docs" / "research-governance" / "tracked-artifacts-allowlist.txt"
)
ARTIFACT_DIR_NAME = "artifacts"


def family_of(relative_path: str) -> str:
    parts = PurePosixPath(relative_path).parts
    if ARTIFACT_DIR_NAME not in parts:
        return "."
    index = parts.index(ARTIFACT_DIR_NAME)
    parent = parts[:index]
    return "/".join(parent) if parent else "."


def parse_allowlist(text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pattern, _, comment = line.partition("#")
        pattern = pattern.strip()
        if not pattern:
            continue
        family = comment.strip() or family_of(pattern.replace("**", "").replace("*", ""))
        entries.append((pattern, family))
    return entries


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
            continue
        if pattern.startswith("**", index):
            parts.append(".*")
            index += 2
            continue
        char = pattern[index]
        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(char))
        index += 1
    return re.compile("^" + "".join(parts) + "$")


def path_matches(path: str, pattern: str) -> bool:
    if path == pattern:
        return True
    if fnmatch.fnmatch(path, pattern):
        return True
    if "**" in pattern or "*" in pattern or "?" in pattern:
        return _glob_to_regex(pattern).fullmatch(path) is not None
    if pattern.endswith("/"):
        return path.startswith(pattern)
    return False


def tracked_artifact_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", "research"],
        check=True,
        capture_output=True,
    )
    paths: list[str] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8")
        parts = PurePosixPath(relative).parts
        if ARTIFACT_DIR_NAME in parts:
            paths.append(relative)
    return paths


def evaluate(
    tracked: list[str],
    allowlist: list[tuple[str, str]],
) -> list[str]:
    patterns = [pattern for pattern, _family in allowlist]
    failures: list[str] = []
    for path in tracked:
        if any(path_matches(path, pattern) for pattern in patterns):
            continue
        failures.append(
            f"tracked artifact not on allowlist: {path} (family {family_of(path)})"
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Require every tracked research artifact to match the allowlist."
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=DEFAULT_ALLOWLIST,
        help="Allowlist file with one glob per line.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root used for git ls-files.",
    )
    args = parser.parse_args()
    allowlist_path = args.allowlist
    if not allowlist_path.is_file():
        print(f"ERROR: allowlist is missing: {allowlist_path}", file=sys.stderr)
        return 1
    entries = parse_allowlist(allowlist_path.read_text(encoding="utf-8"))
    if not entries:
        print(f"ERROR: allowlist is empty: {allowlist_path}", file=sys.stderr)
        return 1
    tracked = tracked_artifact_paths(args.root)
    failures = evaluate(tracked, entries)
    print(
        f"tracked artifacts: {len(tracked)}; allowlist globs: {len(entries)}"
    )
    if failures:
        print("\n".join(f"ERROR: {item}" for item in failures))
        return 1
    print("tracked artifacts allowlist: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
