"""Explicit, self-contained research bundles with fail-closed local restoration.

This is integrity/provenance checking, not a cryptographic signature or offsite
backup. A write-capable user can still delete files; callers must keep independent
copies. No frozen research file is silently overwritten.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_path(root: Path, name: str) -> Path:
    p = PurePosixPath(name)
    if not name or "\\" in name or p.is_absolute() or ".." in p.parts or str(p) != name:
        raise ValueError("unsafe/noncanonical relative path")
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("path escapes bundle")
    return path


def create_bundle(destination: Path, entries: list[dict], *, metadata: dict) -> dict:
    """entry = source absolute path, destination relative path, role, expected SHA."""
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    roles = {e["role"] for e in entries}
    required = {"code", "spec", "input", "reference_output", "environment"}
    if metadata.get("model_kind") == "trained":
        required |= {"model", "preprocessor", "feature_order"}
    if metadata.get("model_kind") not in {"rule", "trained"} or not required <= roles:
        raise ValueError("missing mandatory evidence roles/model kind")
    checked = []
    names = set()
    for e in entries:
        source = Path(e["source"])
        target = safe_path(destination, e["path"])
        if e["path"] == "manifest.json" or e["path"] in names or not source.is_file():
            raise ValueError("invalid/duplicate bundle entry")
        names.add(e["path"])
        actual = sha256(source)
        if actual != e["sha256"]:
            raise ValueError(f"source SHA mismatch: {source}")
        checked.append((e, source, target, actual))
    destination.mkdir(parents=True, exist_ok=False)
    files = []
    for e, source, target, actual in checked:
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        if sha256(target) != actual:
            raise ValueError("copy changed content")
        files.append({"path": e["path"], "role": e["role"], "sha256": actual,
                      "bytes": target.stat().st_size, "original_source": str(source)})
    manifest = {"schema": 1, "metadata": metadata, "files": files,
                "preservation": "research evidence; not disposable cache"}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    verify_bundle(destination)
    return manifest


def verify_bundle(root: Path) -> dict:
    root = Path(root)
    m = json.loads((root / "manifest.json").read_text())
    if m["schema"] != 1:
        raise ValueError("unknown manifest schema")
    expected = {"manifest.json"}
    for e in m["files"]:
        p = safe_path(root, e["path"])
        if e["path"] in expected or not p.is_file():
            raise ValueError("duplicate/missing file")
        expected.add(e["path"])
        if p.stat().st_size != e["bytes"] or sha256(p) != e["sha256"]:
            raise ValueError(f"bundle content changed: {e['path']}")
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    if actual != expected or any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("untracked/symlink evidence")
    return m


def local_backup(root: Path, archive: Path) -> str:
    verify_bundle(root)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                z.write(p, str(p.relative_to(root)))
    return sha256(archive)


def restore_backup(archive: Path, destination: Path, *, expected_sha256: str) -> dict:
    if sha256(archive) != expected_sha256:
        raise ValueError("archive SHA mismatch")
    if destination.exists():
        raise FileExistsError(destination)
    with zipfile.ZipFile(archive) as z:
        names = set()
        for i in z.infolist():
            safe_path(destination, i.filename)
            mode = i.external_attr >> 16
            if i.is_dir() or stat.S_ISLNK(mode) or i.filename in names:
                raise ValueError("duplicate/directory/symlink archive member")
            names.add(i.filename)
        if "manifest.json" not in names:
            raise ValueError("manifest missing")
        destination.mkdir(parents=True, exist_ok=False)
        for i in z.infolist():
            target = safe_path(destination, i.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
    return verify_bundle(destination)
