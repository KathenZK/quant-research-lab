"""Offline-only closeout after the source API began returning repeated HTTP 403."""
from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

SCRIPT = Path(__file__).with_name("audit_mcsm_all_funding_sources_20260910.py")
SPEC = importlib.util.spec_from_file_location("mcsm_source_audit", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def main():
    audit.verify_frozen_inputs()
    plan = json.loads((audit.OUT / "plan.json").read_text())
    receipts = [json.loads(path.read_text()) for path in sorted((audit.OUT / "receipts").glob("*.json"))]
    denied = [row for row in receipts if row.get("http_status") == 403]
    if not denied:
        raise ValueError("This offline closeout is only for the retained HTTP 403 stop")
    halt_path = audit.OUT / "network-halt.json"
    if not halt_path.exists():
        audit.save_new(halt_path, {
            "status": "NETWORK_STOPPED_AFTER_REPEATED_HTTP_403_NO_RETRY_NO_ALTERNATE_ROUTE",
            "saved_at": audit.stamp(), "plan_sha256": audit.sha(audit.OUT / "plan.json"),
            "original_source_script_sha256": audit.sha(SCRIPT), "closeout_script_sha256": audit.sha(Path(__file__)),
            "halt_cause": "Repeated official fapi.binance.com awselb 403 Forbidden; process terminated, no request retry",
            "retained_http_receipts": len(receipts), "http_status_counts": dict(Counter(str(row["http_status"]) for row in receipts)),
            "first_http_403_requested_at": min(row["requested_at"] for row in denied),
            "last_retained_request_at": max(row["requested_at"] for row in receipts),
            "raw_bytes_retained": sum(row.get("raw_bytes", 0) for row in receipts),
            "inflight_requests_at_termination_may_have_no_response_receipt": True,
            "network_must_not_be_resumed_in_this_run": True,
            "offline_reuse_only": "Only four previously frozen exact-URL and SHA-verified large-funding audit API responses",
        })
    reuse = audit.reuse_inventory()
    fetcher = audit.Fetcher(audit.OUT, reuse)
    fetcher.stop.set()  # Any accidental new request is rejected before network access.
    offline_reused = []
    for job in plan["jobs"]:
        path = audit.OUT / "windows" / f"{job['window_id']:03d}.json"
        if path.exists() or job["url"] not in reuse:
            continue
        item = audit.collect_window(job, fetcher)
        if item.get("error") or not item["query_complete_not_calendar_proven"]:
            raise ValueError(f"Exact prior request reuse failed: {item}")
        audit.save_new(path, item)
        offline_reused.append(job["window_id"])
    if fetcher.requests != 0:
        raise AssertionError("Offline closeout must never request the network")
    offline_path = audit.OUT / "offline-reuse-closeout.json"
    if not offline_path.exists():
        audit.save_new(offline_path, {"window_ids": offline_reused, "new_requests": 0,
                                      "network_halt_sha256": audit.sha(halt_path)})
    sys.argv = [str(SCRIPT), "--compare-only"]
    audit.main()


if __name__ == "__main__":
    main()
