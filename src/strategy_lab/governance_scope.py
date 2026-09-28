"""Separate executable research sources from retained evidence snapshots."""

from pathlib import Path


def is_research_artifact(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    return len(parts) > 2 and parts[0] == "research" and "artifacts" in parts[1:-1]


def research_sources(root: Path):
    for path in (root / "research").rglob("*.py"):
        if not is_research_artifact(path, root):
            yield path
