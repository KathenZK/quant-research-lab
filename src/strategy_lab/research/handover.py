"""Read-only ZIP handover preflight. This never certifies research or restoration.

Expected bytes and hashes must come from an independently retained manifest.
Source archives and previous reports are never overwritten or extracted here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import zipfile

from strategy_lab.research.evidence import safe_path, sha256

RESERVE = 5 * 1024**3


def inspect_archives(input_dir: Path, expected: list[dict], *, max_expanded_bytes=2 * 1024**3) -> dict:
    """Check pinned archives, CRCs, member paths and conflicts without extraction.

    PASS only means archive transport/integrity passed. Internal manifest and
    corpus semantics, licenses, market QA and remote recovery remain unverified.
    """
    input_dir = Path(input_dir)
    if not input_dir.is_dir() or input_dir.is_symlink():
        raise ValueError("Input directory must be an existing non-symlink directory")
    if not expected or max_expanded_bytes <= 0:
        raise ValueError("Nonempty expectations and a positive expansion bound required")
    archive_names = set()
    for item in expected:
        name = item["name"]
        safe_path(input_dir, name)
        if "/" in name or name in archive_names:
            raise ValueError("Archive names must be unique basenames")
        if type(item["bytes"]) is not int or item["bytes"] <= 0:
            raise ValueError("Expected byte length must be a positive integer")
        if not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
            raise ValueError("Expected SHA256 required")
        archive_names.add(name)

    free = shutil.disk_usage(input_dir).free
    report = dict(schema="research-handover-preflight/v1",
                  checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  free_bytes=free, reserve_bytes=RESERVE, archives=[], members=[],
                  status="BLOCKED", internal_manifest="NOT_VERIFIED",
                  corpus_acceptance="NOT_VERIFIED", offsite_restore="NOT_VERIFIED",
                  research_ids_completed=0, research_runs_started=0)
    if free < RESERVE:
        report["reason"] = "DISK_RESERVE"
        return report
    seen = set()
    expanded = 0
    for item in expected:
        path = input_dir / item["name"]
        result = dict(item, status="BLOCKED")
        report["archives"].append(result)
        if path.is_symlink() or not path.is_file():
            result["reason"] = "MISSING_OR_NONREGULAR_INPUT"
            continue
        result["actual_bytes"] = path.stat().st_size
        result["actual_sha256"] = sha256(path)
        if result["actual_bytes"] != item["bytes"] or result["actual_sha256"] != item["sha256"]:
            result["reason"] = "BYTE_OR_HASH_MISMATCH"
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                local_names = set()
                for member in archive.infolist():
                    name = member.filename.rstrip("/") if member.is_dir() else member.filename
                    safe_path(input_dir, name)
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not
                            (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
                        raise ValueError("Nonregular ZIP member")
                    if member.filename in local_names or member.flag_bits & 1:
                        raise ValueError("Duplicate or encrypted ZIP member")
                    local_names.add(member.filename)
                    if member.is_dir():
                        continue
                    if name in seen:
                        raise ValueError("Duplicate file across ZIP parts")
                    seen.add(name)
                    expanded += member.file_size
                    if expanded > max_expanded_bytes or free - expanded < RESERVE:
                        raise ValueError("Expansion bound or disk reserve exceeded")
                    digest = hashlib.sha256()
                    actual_size = 0
                    with archive.open(member) as source:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            actual_size += len(chunk)
                            if actual_size > member.file_size:
                                raise ValueError("Expanded size mismatch")
                            digest.update(chunk)
                    if actual_size != member.file_size:
                        raise ValueError("Expanded size mismatch")
                    report["members"].append(dict(archive=item["name"], path=name,
                                                  bytes=actual_size, sha256=digest.hexdigest()))
                if sha256(path) != item["sha256"]:
                    raise ValueError("Archive changed during inspection")
            result["status"] = "PASS"
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
            result["reason"] = str(exc)
    files = {m["path"] for m in report["members"]}
    conflict = any(any(str(p) in files for p in Path(name).parents if str(p) != ".") for name in files)
    report["status"] = "PASS" if not conflict and all(a["status"] == "PASS" for a in report["archives"]) else "BLOCKED"
    if conflict:
        report["reason"] = "FILE_DIRECTORY_CONFLICT"
    report["expanded_bytes"] = expanded
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True, help="JSON list of name, bytes, sha256")
    parser.add_argument("--report", type=Path, required=True, help="New private JSON report; never overwritten")
    args = parser.parse_args()
    if args.report.exists() or args.report.is_symlink():
        raise FileExistsError(args.report)
    report = inspect_archives(args.input_dir, json.loads(args.expected.read_text()))
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({k: report[k] for k in ["status", "research_ids_completed", "research_runs_started"]}))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
