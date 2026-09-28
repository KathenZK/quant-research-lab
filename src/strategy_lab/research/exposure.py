"""Append-only, hash-chained research exposure and observation records.

File locks serialize local writers; hashes detect edits, not a malicious rewrite
of the whole file. Keep ledger checkpoints in independently retained bundles.
Backfills remain backfills and are never labelled prospective observations.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import fcntl
import json
import os
from pathlib import Path

from .accounting import digest, utc


def read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        return _read(f.read())


def _read(text):
    if text and not text.endswith("\n"):
        raise ValueError("truncated ledger tail")
    records, previous, ids = [], "0" * 64, set()
    for line in text.splitlines():
        record = json.loads(line)
        payload = {k: v for k, v in record.items() if k != "sha256"}
        if (record["sequence"] != len(records) + 1 or record["previous_sha256"] != previous
                or record["sha256"] != digest(payload) or record["data"]["id"] in ids):
            raise ValueError("ledger chain invalid")
        previous = record["sha256"]
        ids.add(record["data"]["id"])
        records.append(record)
    return records


def _validate(data):
    if not isinstance(data.get("id"), str) or not data["id"] or not data.get("family"):
        raise ValueError("record identity required")
    if data.get("kind") == "exposure":
        for field in ("window_start", "window_end", "evidence_class", "selection_reason", "artifacts", "trial_count"):
            if field not in data:
                raise ValueError(f"missing {field}")
        if utc(data["window_start"]) >= utc(data["window_end"]):
            raise ValueError("invalid exposed window")
        if data["evidence_class"] not in {"historical_replay", "development", "synthetic_test", "prospective"}:
            raise ValueError("explicit evidence class required")
        count = data["trial_count"]
        if count is not None and (type(count) is not int or count < 1):
            raise ValueError("trial count must be positive or unknown")
        if count is None and not data.get("trial_count_unknown_reason"):
            raise ValueError("explain unknown trial count")
        if data["evidence_class"] == "prospective":
            raise ValueError("prospective status requires observation records, not exposure relabelling")
    elif data.get("kind") == "observation":
        for field in ("decision_at", "completed_at", "deadline_at", "config_sha256", "code_sha256",
                      "status", "reason", "input_available_at", "execution_link", "account_link"):
            if field not in data:
                raise ValueError(f"missing {field}")
        decision, completed, deadline = (utc(data[k]) for k in ("decision_at", "completed_at", "deadline_at"))
        if completed < decision or deadline < decision:
            raise ValueError("invalid observation times")
        if data["status"] not in {"completed", "missed", "backfill_diagnostic"}:
            raise ValueError("explicit observation status required")
        if data["status"] != "completed" and not data["reason"]:
            raise ValueError("missing/backfill observations require reason")
        if data["input_available_at"] is not None and utc(data["input_available_at"]) > decision:
            raise ValueError("future input at decision")
        if data["status"] == "completed" and data["input_available_at"] is None:
            raise ValueError("completed observation requires input availability")
    else:
        raise ValueError("unsupported record kind")
    artifacts = data.get("artifacts", {})
    hashes = list(artifacts.values()) + [data[k] for k in ("config_sha256", "code_sha256") if k in data]
    if not artifacts and data["kind"] == "exposure":
        raise ValueError("exposure evidence references required")
    if any(not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h) for h in hashes):
        raise ValueError("invalid evidence SHA256")


def append_record(path: Path, data: dict) -> dict:
    _validate(data)
    now = datetime.now(timezone.utc).isoformat()
    data = json.loads(json.dumps(data, allow_nan=False))
    if data["kind"] == "observation":
        if utc(data["completed_at"]) > now:
            raise ValueError("completion cannot be in the future")
        # Late writing cannot retroactively become timely forward evidence.
        data["late"] = now > utc(data["deadline_at"]) or utc(data["completed_at"]) > utc(data["deadline_at"])
        data["prospective_credit"] = data["status"] == "completed" and not data["late"]
    def build(records):
        if data["kind"] == "observation" and any(
            r["data"]["kind"] == "observation" and r["data"]["family"] == data["family"]
            and utc(r["data"]["decision_at"]) == utc(data["decision_at"]) for r in records
        ):
            raise ValueError("duplicate observation node; append correction as new exposure")
        return data

    return append_locked(path, build)


def append_locked(path: Path, build, *, idempotent: bool = False) -> dict:
    """Shared local journal transaction; caller validates event semantics under lock.

    Used by exposure records and TrialRegistry. This is local POSIX locking, not
    a distributed database or external timestamp service. A damaged tail fails
    closed; it is never silently discarded.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        records = _read(f.read())
        data = json.loads(json.dumps(build(records), allow_nan=False))
        for record in records:
            if record["data"]["id"] == data["id"]:
                if idempotent and record["data"] == data:
                    return record
                raise ValueError("duplicate record id with conflicting or non-idempotent data")
        now = datetime.now(timezone.utc).isoformat()
        payload = {"sequence": len(records) + 1, "registered_at": now,
                   "previous_sha256": records[-1]["sha256"] if records else "0" * 64, "data": data}
        record = {**payload, "sha256": digest(payload)}
        f.write(json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return record


def overlaps(records: list[dict], *, start: str, end: str) -> list[dict]:
    a, b = utc(start), utc(end)
    if a >= b:
        raise ValueError("invalid query window")
    return [r for r in records if r["data"]["kind"] == "exposure"
            and utc(r["data"]["window_start"]) < b and utc(r["data"]["window_end"]) > a]


def observation_coverage(records: list[dict], *, family: str, start: str, end: str,
                         as_of: str, cadence_hours: int) -> dict:
    """Count expected elapsed decision nodes, including nodes absent from logs.

    Cadence and window must come from the frozen observation contract; choosing
    a convenient schedule after seeing gaps does not establish forward evidence.
    """
    if type(cadence_hours) is not int or cadence_hours < 1:
        raise ValueError("positive integer cadence required")
    a, b, now = [datetime.fromisoformat(utc(t)) for t in (start, end, as_of)]
    if a >= b:
        raise ValueError("invalid observation range")
    nodes = {utc(r["data"]["decision_at"]): r["data"] for r in records
             if r["data"]["kind"] == "observation" and r["data"]["family"] == family}
    result = []
    t = a
    while t < b and t <= now:
        data = nodes.get(t.isoformat())
        result.append({"decision_at": t.isoformat(), "status": data["status"] if data else "missing_record",
                       "timely_credit": bool(data and data.get("prospective_credit")),
                       "execution_linked": bool(data and data.get("execution_link")),
                       "account_linked": bool(data and data.get("account_link"))})
        t += timedelta(hours=cadence_hours)
    return {"expected_elapsed_nodes": len(result), "missing_records": sum(r["status"] == "missing_record" for r in result),
            "timely_nodes": sum(r["timely_credit"] for r in result),
            "fully_linked_timely_nodes": sum(r["timely_credit"] and r["execution_linked"] and r["account_linked"] for r in result),
            "nodes": result, "exchange_reconciled": False}
