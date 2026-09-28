"""Independently query every frozen holding window; no account or lake mutation."""
from __future__ import annotations

import argparse
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-long10"
BASE = FAMILY / "artifacts/baseline-estimate-20260909"
OUT = FAMILY / "artifacts/funding-recheck-20260910/sources"
SPEC = FAMILY / "specs/binance-1d-mcsm-funding-recheck-20260910.md"
LIMIT = 1000
MAX_REQUESTS = 800
MAX_BYTES = 90 * 1024 * 1024


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def save_new(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def utc_ms(value):
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise ValueError("Naive timestamp prohibited")
    ts = ts.tz_convert("UTC")
    result = ts.as_unit("ns").value // 1_000_000
    if pd.Timestamp(result, unit="ms", tz="UTC") != ts:
        raise ValueError("Timestamp milliseconds roundtrip failed")
    if not 2020 <= ts.year <= 2026:
        raise ValueError("Timestamp outside frozen research years")
    return int(result)


def positive_mark(value):
    if value is None or value == "":
        return None
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        return None
    return result


def api_type(row):
    value = row.get("rateType")
    return str(value) if value not in (None, "") else "Unspecified"


def verify_frozen_inputs():
    started_path, summary_path = BASE / "accounts/started.json", BASE / "accounts/summary.json"
    started, summary = json.loads(started_path.read_text()), json.loads(summary_path.read_text())
    checks = {}
    for name, expected in started["sha256"].items():
        path = Path(started["paths"][name])
        if not path.is_absolute():
            path = ROOT / path
        actual = sha(path)
        if actual != expected or summary["input_sha256"][name] != expected:
            raise ValueError(f"Frozen input changed: {name}")
        checks[str(path.relative_to(ROOT))] = actual
    for name, expected in summary["output_sha256"].items():
        path = BASE / "accounts" / name
        actual = sha(path)
        if actual != expected:
            raise ValueError(f"Frozen account output changed: {name}")
        checks[str(path.relative_to(ROOT))] = actual
    kernel = FAMILY / "scripts/mcsm_baseline_accounting_20260908.py"
    if sha(kernel) != started["kernel_sha256"]:
        raise ValueError("Frozen kernel changed")
    checks[str(kernel.relative_to(ROOT))] = sha(kernel)
    checks[str(started_path.relative_to(ROOT))] = sha(started_path)
    checks[str(summary_path.relative_to(ROOT))] = sha(summary_path)
    return started, checks


def build_jobs(holdings):
    jobs = []
    for index, row in enumerate(holdings.sort_values(["entry_ts", "symbol"]).itertuples()):
        start, end = utc_ms(row.entry_ts), utc_ms(row.exit_ts)
        if start >= end:
            raise ValueError("Empty holding window")
        code = row.symbol.split("/")[0] + "USDT"
        params = {"symbol": code, "startTime": start, "endTime": end, "limit": LIMIT}
        jobs.append({"window_id": index, "holding_month": row.month.strftime("%Y-%m"),
                     "symbol": row.symbol, "api_symbol": code, "holding_start_ms": start,
                     "holding_end_ms": end, "start_ms": start, "end_ms": end,
                     "url": "https://fapi.binance.com/fapi/v1/fundingRate?" + urlencode(params)})
    if len(jobs) != 760 or len({(j["symbol"], j["start_ms"]) for j in jobs}) != 760:
        raise ValueError("Expected exactly 760 unique frozen holding windows")
    return jobs


def reuse_inventory():
    result = {}
    # Explicitly bounded previous audit directory, never scan the data root.
    raw_dir = BASE / "large-funding-cash-source-audit/raw"
    for path in sorted(raw_dir.glob("*-funding-api.receipt.json")):
        receipt = json.loads(path.read_text())
        source = ROOT / receipt["raw_path"]
        if sha(source) != receipt["raw_sha256"]:
            raise ValueError(f"Previous source hash mismatch: {source}")
        if receipt["http_status"] == 200 and not receipt.get("error"):
            result[receipt["url"]] = {**receipt, "reused_receipt_path": str(path.relative_to(ROOT)),
                                     "reused_receipt_sha256": sha(path)}
    return result


class Fetcher:
    def __init__(self, out, reused):
        self.out = out
        self.reused = reused
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.next_time = 0.0
        self.requests = 0
        self.bytes = 0
        self.request_times = deque()

    def fetch(self, job, page):
        name = f"{job['window_id']:03d}-{job['api_symbol']}-{job['holding_month']}-p{page}"
        receipt_path = self.out / "receipts" / f"{name}.json"
        if receipt_path.exists():
            existing = json.loads(receipt_path.read_text())
            if existing["url"] != job["url"] or sha(ROOT / existing["raw_path"]) != existing["raw_sha256"]:
                raise ValueError("Existing saved request receipt is not an exact hash-verified match")
            return existing
        if job["url"] in self.reused:
            receipt = {**self.reused[job["url"]], "reused_exact_request": True, "page": page}
            save_new(receipt_path, receipt)
            return receipt
        if (self.out / "network-halt.json").exists():
            raise RuntimeError("This run was access-denied and permanently closed to new network requests")
        with self.lock:
            if self.stop.is_set() or self.requests >= MAX_REQUESTS or self.bytes >= MAX_BYTES:
                raise RuntimeError("Global request stop or predeclared budget reached")
            wait = self.next_time - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            now = time.monotonic()
            while self.request_times and self.request_times[0] <= now - 300:
                self.request_times.popleft()
            if len(self.request_times) >= 490:
                time.sleep(max(0, self.request_times[0] + 300.1 - now))
            if self.stop.is_set():
                raise RuntimeError("Global stop before request")
            self.request_times.append(time.monotonic())
            self.next_time = time.monotonic() + 0.75
            self.requests += 1
        status, headers, body, error = None, {}, b"", None
        requested = stamp()
        try:
            with urlopen(Request(job["url"], headers={"User-Agent": "strategy-lab-all-held-funding-source-audit"}), timeout=25) as response:
                status, headers, body = response.status, dict(response.headers), response.read()
        except HTTPError as failure:
            status, headers, body, error = failure.code, dict(failure.headers), failure.read(), str(failure)
        except (URLError, TimeoutError, OSError) as failure:
            error = str(failure)
        if status in (403, 418, 429):
            self.stop.set()
        raw_path = self.out / "raw" / f"{name}.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_path.open("xb") as stream:
            stream.write(body)
        with self.lock:
            self.bytes += len(body)
            if self.bytes >= MAX_BYTES:
                self.stop.set()
        receipt = {"url": job["url"], "request_start_ms": job["start_ms"], "request_end_ms": job["end_ms"],
                   "requested_at": requested, "finished_at": stamp(), "http_status": status,
                   "headers": headers, "error": error, "page": page,
                   "raw_path": str(raw_path.relative_to(ROOT)), "raw_sha256": sha(raw_path),
                   "raw_bytes": len(body), "reused_exact_request": False}
        save_new(receipt_path, receipt)
        return receipt


def parse_response(receipt, job):
    if receipt["http_status"] != 200 or receipt.get("error"):
        raise ValueError(f"HTTP source failed: {receipt['http_status']}: {receipt.get('error')}")
    path = ROOT / receipt["raw_path"]
    if sha(path) != receipt["raw_sha256"]:
        raise ValueError("Raw checksum mismatch")
    rows = json.loads(path.read_bytes())
    if not isinstance(rows, list) or len(rows) > LIMIT:
        raise ValueError("Non-list response or provider limit violated")
    times = []
    for row in rows:
        timestamp = row["fundingTime"]
        if not isinstance(timestamp, int) or row["symbol"] != job["api_symbol"]:
            raise ValueError("Source identity or timestamp type mismatch")
        if not job["start_ms"] <= timestamp <= job["end_ms"]:
            raise ValueError("Source event outside requested range")
        if utc_ms(pd.Timestamp(timestamp, unit="ms", tz="UTC")) != timestamp:
            raise ValueError("Native timestamp roundtrip failed")
        if not math.isfinite(float(row["fundingRate"])):
            raise ValueError("Nonfinite source rate")
        times.append(timestamp)
    if times != sorted(times):
        raise ValueError("Source events out of order")
    return rows


def collect_window(job, fetcher):
    result = {"window_id": job["window_id"], "holding_month": job["holding_month"], "symbol": job["symbol"],
              "pages": [], "rows": [], "query_complete_not_calendar_proven": False}
    current = dict(job)
    try:
        for page in range(3):
            receipt = fetcher.fetch(current, page)
            rows = parse_response(receipt, current)
            result["pages"].append({"source_path": receipt["raw_path"], "source_sha256": receipt["raw_sha256"],
                                    "row_count": len(rows), "reused_exact_request": receipt["reused_exact_request"],
                                    "url": receipt["url"], "http_status": receipt["http_status"]})
            for row in rows:
                result["rows"].append({**row, "source_path": receipt["raw_path"], "source_sha256": receipt["raw_sha256"]})
            if len(rows) < LIMIT:
                result["query_complete_not_calendar_proven"] = True
                break
            # Pagination continuation is frozen before issuing it. Never truncate a full page.
            next_ms = max(row["fundingTime"] for row in rows) + 1
            if next_ms > job["end_ms"]:
                raise ValueError("Full page reaches terminal timestamp: cannot exclude same-ms truncation")
            current["start_ms"] = next_ms
            current["url"] = "https://fapi.binance.com/fapi/v1/fundingRate?" + urlencode({
                "symbol": job["api_symbol"], "startTime": next_ms, "endTime": job["end_ms"], "limit": LIMIT})
            page_plan = fetcher.out / "pagination-plans" / f"{job['window_id']:03d}-p{page + 1}.json"
            if not page_plan.exists():
                save_new(page_plan, {**current, "frozen_at": stamp(), "previous_page_sha256": receipt["raw_sha256"]})
        if not result["query_complete_not_calendar_proven"]:
            raise ValueError("Pagination cap reached without terminal short page")
    except (ValueError, KeyError, TypeError, RuntimeError) as failure:
        result["error"] = str(failure)
    return result


def compare_window(job, frozen, native, query_complete=True):
    """Outer comparison, with no same-hour inference when the official hour is ambiguous."""
    frozen_rows = frozen.to_dict("records")
    # The API request starts inclusive; an event exactly at entry is reported but not held.
    nonheld_boundary = [r for r in native if r["fundingTime"] == job["holding_start_ms"]]
    native_rows = [r for r in native if job["holding_start_ms"] < r["fundingTime"] <= job["holding_end_ms"]]
    f_hour = Counter(utc_ms(r["ts"]) // 3_600_000 for r in frozen_rows)
    n_hour = Counter(r["fundingTime"] // 3_600_000 for r in native_rows)
    used = set()
    result = []
    for fr in frozen_rows:
        frozen_ms = utc_ms(fr["ts"])
        original_type = str(fr.get("source_rate_type", fr["rate_type"]))
        base = {"holding_month": job["holding_month"], "symbol": job["symbol"],
                "frozen_ts": pd.Timestamp(frozen_ms, unit="ms", tz="UTC"),
                "frozen_rate": float(fr["funding_rate"]), "frozen_rate_type": original_type,
                "model_rate_type": str(fr["rate_type"]), "original_event_id": fr.get("event_id"),
                "native_ts": pd.NaT, "native_rate": None, "native_rate_type": None,
                "native_mark": None, "source_path": None, "source_sha256": None,
                "timestamp_delta_ms": None, "mapping_status": "MISSING_FROM_API" if query_complete else "SOURCE_QUERY_INCOMPLETE"}
        same_hour = [(idx, nr) for idx, nr in enumerate(native_rows)
                     if idx not in used and nr["fundingTime"] // 3_600_000 == frozen_ms // 3_600_000]
        exact = [(idx, nr) for idx, nr in same_hour if nr["fundingTime"] == frozen_ms and
                 (original_type == "Unspecified" or api_type(nr) == original_type)]
        chosen = exact[0] if len(exact) == 1 else None
        method = "MATCH_EXACT_NATIVE_KEY"
        if chosen is None and f_hour[frozen_ms // 3_600_000] == n_hour[frozen_ms // 3_600_000] == 1:
            chosen = same_hour[0] if len(same_hour) == 1 else None
            method = "MATCH_OFFICIAL_UNIQUE_HOUR"
        if chosen is not None:
            idx, nr = chosen
            used.add(idx)
            delta = int(nr["fundingTime"] - frozen_ms)
            native_rate = float(nr["fundingRate"])
            status = method
            if abs(delta) >= 2000:
                status = "TIME_CONFLICT"
            elif abs(native_rate - base["frozen_rate"]) > 1e-12:
                status = "RATE_CONFLICT"
            elif original_type != "Unspecified" and api_type(nr) != original_type:
                status = "TYPE_CONFLICT"
            elif api_type(nr) == "Unspecified":
                status = "API_TYPE_UNSPECIFIED"
            base.update({"native_ts": pd.Timestamp(nr["fundingTime"], unit="ms", tz="UTC"),
                         "native_rate": native_rate, "native_rate_type": api_type(nr),
                         "native_mark": positive_mark(nr.get("markPrice")),
                         "source_path": nr["source_path"], "source_sha256": nr["source_sha256"],
                         "timestamp_delta_ms": delta, "mapping_status": status})
        elif same_hour:
            base["mapping_status"] = "AMBIGUOUS_OFFICIAL_HOUR"
        result.append(base)
    for idx, nr in enumerate(native_rows):
        if idx not in used:
            result.append({"holding_month": job["holding_month"], "symbol": job["symbol"],
                           "frozen_ts": pd.NaT, "frozen_rate": None, "frozen_rate_type": None,
                           "model_rate_type": None, "original_event_id": None,
                           "native_ts": pd.Timestamp(nr["fundingTime"], unit="ms", tz="UTC"),
                           "native_rate": float(nr["fundingRate"]), "native_rate_type": api_type(nr),
                           "native_mark": positive_mark(nr.get("markPrice")), "source_path": nr["source_path"],
                           "source_sha256": nr["source_sha256"], "timestamp_delta_ms": None,
                           "mapping_status": "EXTRA_API_EVENT"})
    return result, len(nonheld_boundary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--compare-only", action="store_true")
    parser.add_argument("--offline", action="store_true", help="Read saved sources only; this is the default")
    parser.add_argument("--fetch-explicitly-authorized", action="store_true", help="Requires new user authorization; refused for an access-denied run")
    args = parser.parse_args()
    started, checks = verify_frozen_inputs()
    holdings = pd.read_parquet(ROOT / started["paths"]["holdings"])
    frozen = pd.read_parquet(ROOT / started["paths"]["funding"])
    if len(frozen) != 97421:
        raise ValueError("Frozen funding event count changed")
    jobs = build_jobs(holdings)
    reused = reuse_inventory()
    plan_path = OUT / "plan.json"
    if not plan_path.exists():
        save_new(plan_path, {"status": "FROZEN_ALL_HOLDING_SOURCE_RECHECK_NOT_RESEARCH_STARTUP_APPROVAL",
                             "frozen_at": stamp(), "jobs": jobs, "verified_original_files": checks,
                             "script_sha256": sha(Path(__file__)), "spec_sha256": sha(SPEC),
                             "maximum_requests": MAX_REQUESTS, "maximum_workers": 4,
                             "minimum_request_start_interval_seconds": 0.75,
                             "maximum_requests_per_rolling_300_seconds": 490,
                             "maximum_new_raw_bytes": MAX_BYTES, "expected_frozen_events": 97421,
                             "exact_request_reuse_count": sum(j["url"] in reused for j in jobs),
                             "historical_calendar_not_proven_by_api": True})
    plan = json.loads(plan_path.read_text())
    if plan["jobs"] != jobs or plan["verified_original_files"] != checks:
        raise ValueError("Run request or original inputs differ from predeclared plan")
    if args.prepare_only:
        print(json.dumps({"jobs": len(jobs), "reuse": plan["exact_request_reuse_count"], "plan_sha256": sha(plan_path)}), flush=True)
        return
    if args.fetch_explicitly_authorized and (OUT / "network-halt.json").exists():
        raise RuntimeError("Refuse resuming this access-denied run; no retry or alternate route")
    offline = not args.fetch_explicitly_authorized or args.offline or args.compare_only
    if offline and (OUT / "summary.json").exists():
        existing = json.loads((OUT / "summary.json").read_text())
        for name, expected in existing["output_sha256"].items():
            if sha(OUT / name) != expected:
                raise ValueError("Saved source comparison changed")
        print(json.dumps({"status": existing["status"], "saved_summary_sha256": sha(OUT / "summary.json"),
                          "network_requests": 0, "read_only_replay": True}), flush=True)
        return
    fetcher = Fetcher(OUT, reused)
    collected = {}
    if offline:
        collected = {int(path.stem): json.loads(path.read_text()) for path in (OUT / "windows").glob("*.json")}
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(collect_window, job, fetcher): job for job in jobs}
            for future in as_completed(futures):
                job, item = futures[future], future.result()
                collected[job["window_id"]] = item
                window_path = OUT / "windows" / f"{job['window_id']:03d}.json"
                if not window_path.exists():
                    save_new(window_path, item)
                if len(collected) % 40 == 0 or item.get("error"):
                    print(json.dumps({"completed": len(collected), "of": len(jobs), "new_requests": fetcher.requests,
                                      "new_raw_bytes": fetcher.bytes, "latest_error": item.get("error")}), flush=True)
    comparisons, windows = [], []
    for job in jobs:
        item = collected.get(job["window_id"], {"rows": [], "pages": [], "error": "WINDOW_NOT_REQUESTED", "query_complete_not_calendar_proven": False})
        frame = frozen[frozen.symbol.eq(job["symbol"]) & frozen.holding_start.eq(pd.Timestamp(job["holding_start_ms"], unit="ms", tz="UTC"))]
        checked, boundary = compare_window(job, frame, item["rows"], item["query_complete_not_calendar_proven"])
        comparisons.extend(checked)
        count = dict(Counter(row["mapping_status"] for row in checked))
        windows.append({"window_id": job["window_id"], "holding_month": job["holding_month"], "symbol": job["symbol"],
                        "frozen_events": len(frame), "native_rows": len(item["rows"]), "boundary_not_held_events": boundary,
                        "query_complete_not_calendar_proven": item["query_complete_not_calendar_proven"],
                        "pages": len(item["pages"]), "source_error": item.get("error"), "mapping_counts": count})
    combined = pd.DataFrame(comparisons)
    for column in ["frozen_ts", "native_ts"]:
        combined[column] = pd.to_datetime(combined[column], utc=True)
    output = OUT / "native-event-comparison.parquet"
    if output.exists():
        raise FileExistsError("Never overwrite the first comparison result")
    combined.to_parquet(output, index=False)
    matched = combined.mapping_status.str.startswith("MATCH_")
    missing = combined.mapping_status.eq("MISSING_FROM_API")
    extra = combined.mapping_status.eq("EXTRA_API_EVENT")
    issues = combined[~matched]
    issues_path = OUT / "event-differences.parquet"
    issues.to_parquet(issues_path, index=False)
    save_new(OUT / "window-summary.json", windows)
    final_checks = verify_frozen_inputs()[1]
    if final_checks != checks:
        raise ValueError("Frozen input or account mutated during source audit")
    summary = {"status": "ALL_FROZEN_EVENTS_MATCH_OFFICIAL_API_NOT_CALENDAR_CERTIFIED" if len(issues) == 0 else "SOURCE_DIFFERENCES_OR_INCOMPLETE_QUERY_REQUIRE_REVIEW",
               "completed_at": stamp(), "plan_sha256": sha(plan_path), "script_sha256": sha(Path(__file__)),
               "original_inputs_and_outputs_unchanged": True, "windows": len(jobs), "frozen_events": len(frozen),
               "query_complete_windows": sum(x["query_complete_not_calendar_proven"] for x in windows),
               "matched_events": int(matched.sum()), "missing_from_api": int(missing.sum()), "extra_api_events": int(extra.sum()),
               "comparison_rows": len(combined), "issue_rows": len(issues),
               "mapping_counts": combined.mapping_status.value_counts().to_dict(),
               "frozen_source_rate_type_counts": frozen.source_rate_type.value_counts().to_dict(),
               "native_rate_type_counts": combined.native_rate_type.dropna().value_counts().to_dict(),
               "native_mark_available_matched_events": int((matched & combined.native_mark.notna()).sum()),
               "matched_native_timestamp_max_abs_delta_ms": float(combined.loc[matched, "timestamp_delta_ms"].abs().max()) if matched.any() else None,
               "matched_rate_max_abs_diff": float((combined.loc[matched, "frozen_rate"] - combined.loc[matched, "native_rate"]).abs().max()) if matched.any() else None,
               "new_http_requests_this_invocation": fetcher.requests, "new_raw_bytes_this_invocation": fetcher.bytes,
               "reused_exact_prior_request_windows": plan["exact_request_reuse_count"],
               "source_error_windows": [x for x in windows if x["source_error"]],
               "empty_api_response_windows": [x for x in windows if x["native_rows"] == 0],
               "paginated_windows": [x for x in windows if x["pages"] > 1],
               "comparison_key_explanation": "original_event_id is the unchanged source funding event_id; frozen_ts is actual account ts; frozen_rate_type retains source_rate_type (mostly Unspecified), model_rate_type is actual account Regular/Special",
               "calendar_complete_proven": False, "native_marks_missing_are_not_zero": True,
               "output_sha256": {"native-event-comparison.parquet": sha(output), "event-differences.parquet": sha(issues_path),
                                  "window-summary.json": sha(OUT / "window-summary.json")}}
    save_new(OUT / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
