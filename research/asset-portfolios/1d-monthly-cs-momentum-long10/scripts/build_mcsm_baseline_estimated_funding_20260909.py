"""明确 explore/untrusted 的观察资金费事件与分钟 mark 估算输入，不发布净值。"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
import zipfile

import numpy as np
import pandas as pd

from strategy_lab.data.funding_v2 import load_funding_v2
from strategy_lab.data.research_bundle import read_bundle_contract

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-long10"
OUT = FAMILY / "artifacts/baseline-estimate-20260909/funding"
PLAN = OUT / "plan-v2.json"
OBSERVED = OUT / "observed-held-events-v2.parquet"
JOBS = OUT / "jobs-v2"
OLD = FAMILY / "artifacts/baseline-verification-20260908/funding-evidence"
RAW_API = ROOT / "data/raw/funding_rates/exchange=binance/market_type=perp/source=binance_futures_funding_rate_api"
PIN = {"bundle_id": "binance.v3.research_inputs.v2",
       "bundle_path": "research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json",
       "bundle_sha256": "d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008"}
FUNDING_SHA = "398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076"
LOCK = threading.Lock()
STOP = threading.Event()
NEXT_REQUEST = 0.0
SOURCE_CACHE = {}
SOURCE_CACHE_ROOT = None


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False, default=str)
        stream.write("\n")


def valid_mark(value):
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False


def frozen_frame(path, frame):
    if path.exists():
        raise FileExistsError(path)
    frame.to_parquet(path, index=False)


def load_existing_native():
    """只查明确两个来源目录，逐原文校验hash，不扫描全湖。"""
    records, receipts = [], []
    for path in sorted(RAW_API.rglob("*.json.gz")):
        meta_path = path.with_suffix(".meta.json")
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        assert sha(path) == meta["sha256"], path
        blob = gzip.decompress(path.read_bytes())
        rows = json.loads(blob)
        receipts.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path), "raw_sha256": hashlib.sha256(blob).hexdigest()})
        for row in rows:
            if valid_mark(row.get("markPrice")):
                records.append({"symbol": row["symbol"].removesuffix("USDT") + "/USDT:USDT",
                                "native_ms": row["fundingTime"], "native_rate": float(row["fundingRate"]),
                                "native_type": row.get("rateType", "UNSPECIFIED_API"), "native_mark": float(row["markPrice"]),
                                "mark_raw_sha256": hashlib.sha256(blob).hexdigest(), "mark_raw_path": str(path.relative_to(ROOT)),
                                "allow_hour_adjudication": False})
    for meta_path in sorted(OLD.glob("*-receipt.json")):
        meta = json.loads(meta_path.read_text())
        if meta.get("http_status") != 200 or meta.get("error"):
            continue
        path = ROOT / meta["raw_path"]
        assert sha(path) == meta["raw_sha256"], path
        rows = json.loads(path.read_bytes())
        if not isinstance(rows, list):
            continue
        receipts.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path)})
        for row in rows:
            if valid_mark(row.get("markPrice")):
                records.append({"symbol": row["symbol"].removesuffix("USDT") + "/USDT:USDT",
                                "native_ms": row["fundingTime"], "native_rate": float(row["fundingRate"]),
                                "native_type": row.get("rateType", "UNSPECIFIED_API"), "native_mark": float(row["markPrice"]),
                                "mark_raw_sha256": sha(path), "mark_raw_path": str(path.relative_to(ROOT)),
                                "allow_hour_adjudication": bool(meta.get("list_not_limit_truncated"))})
    native = pd.DataFrame(records)
    if len(native):
        identities = ["symbol", "native_ms", "native_type"]
        disagreements = native.groupby(identities).agg(marks=("native_mark", "nunique"), rates=("native_rate", "nunique"))
        assert disagreements.marks.le(1).all() and disagreements.rates.le(1).all(), "native source conflict"
        native = native.sort_values("allow_hour_adjudication", ascending=False).drop_duplicates(identities)
    return native, receipts


def prepare(windows_path):
    OUT.mkdir(parents=True, exist_ok=True)
    if PLAN.exists():
        raise FileExistsError("plan already frozen")
    windows = pd.read_parquet(windows_path) if windows_path.suffix == ".parquet" else pd.read_csv(windows_path)
    windows = windows.rename(columns={"entry_ts": "start", "exit_ts": "end"})
    required = {"symbol", "start", "end"}
    if not required <= set(windows):
        raise ValueError(f"holding windows need columns {required}")
    windows["start"] = pd.to_datetime(windows.start, utc=True)
    windows["end"] = pd.to_datetime(windows.end, utc=True)
    assert (windows.end > windows.start).all()
    assert windows.start.min() >= pd.Timestamp("2020-03-01T00:15:00Z")
    assert windows.end.max() <= pd.Timestamp("2026-07-01T00:15:00Z")
    bundle, selected = read_bundle_contract(ROOT, pin=PIN)
    funding_component = bundle["components"]["funding"]
    assert funding_component["manifest_sha256"] == FUNDING_SHA
    data = load_funding_v2(ROOT / "data" / funding_component["root"], expected_manifest_sha256=FUNDING_SHA)
    native, native_receipts = load_existing_native()
    selected_events, coverage = [], []
    event_groups = {s: g for s, g in data.events.groupby("symbol", sort=False)}
    for n, row in windows.iterrows():
        events = event_groups.get(row.symbol, data.events.iloc[:0])
        events = events[(events.ts > row.start) & (events.ts <= row.end)].copy()
        events["holding_window_id"] = n
        events["holding_start"] = row.start
        events["holding_end"] = row.end
        selected_events.append(events)
        segments = data.segments
        proof = segments[(segments.symbol == row.symbol) & (segments.start <= row.start) & (segments.end >= row.end)]
        coverage.append({"holding_window_id": n, "symbol": row.symbol, "start": row.start, "end": row.end,
                         "observed_events": len(events), "empty_is_proven_zero": False,
                         "covered_by_single_frozen_calendar_segment": len(proof) == 1,
                         "first_observed_event": events.ts.min(), "last_observed_event": events.ts.max(),
                         "calendar_status": "PARTIAL_EVIDENCE_ONLY_NOT_NET_INPUT_VERIFIED", "identity_verified": False})
    events = pd.concat(selected_events, ignore_index=True)
    assert not events.event_id.duplicated().any(), "overlapping holding windows double-count funding"
    events["frozen_ts"] = events.ts
    events["frozen_rate_type"] = events.rate_type
    events["native_mark"] = np.nan
    events["mark_raw_sha256"] = ""
    events["mark_raw_path"] = ""
    events["native_mark_status"] = "MISSING_NATIVE_MARK"
    events["ts_adjudication"] = "FROZEN_EVENT_KEY"
    exact = {(r.symbol, int(r.native_ms), r.native_type): r for r in native.itertuples()}
    exact_untyped = {}
    for r in native.itertuples():
        exact_untyped.setdefault((r.symbol, int(r.native_ms)), []).append(r)
    by_hour = {}
    for r in native.itertuples():
        if r.allow_hour_adjudication:
            by_hour.setdefault((r.symbol, int(r.native_ms) // 3_600_000), []).append(r)
    mappings = []
    for i, r in events.iterrows():
        timestamp = int(r.ts.timestamp() * 1000)
        hit = exact.get((r.symbol, timestamp, r.rate_type))
        if hit is None and r.rate_type not in ["Regular", "Special"]:
            typed = [x for x in exact_untyped.get((r.symbol, timestamp), []) if abs(x.native_rate - r.funding_rate) <= 1e-12]
            if len(typed) == 1:
                hit = typed[0]
                events.at[i, "ts_adjudication"] = "EXACT_NATIVE_TIME_UNIQUE_RATE_AND_TYPE"
        if hit is None:
            # Exact native time with an archive-unspecified type is permitted only
            # with a unique complete-hour authoritative response.
            candidates = by_hour.get((r.symbol, timestamp // 3_600_000), [])
            candidates = [x for x in candidates if abs(x.native_rate - r.funding_rate) <= 1e-12 and abs(x.native_ms - timestamp) <= 2000
                          and (r.rate_type not in ["Regular", "Special"] or x.native_type == r.rate_type)]
            if len(candidates) == 1:
                hit = candidates[0]
                events.at[i, "ts_adjudication"] = "COMPLETE_HOUR_AUTHORITY_UNIQUE_RATE_MATCH"
        if hit is not None:
            assert abs(hit.native_rate - r.funding_rate) <= 1e-12
            events.at[i, "native_mark"] = hit.native_mark
            events.at[i, "mark_raw_sha256"] = hit.mark_raw_sha256
            events.at[i, "mark_raw_path"] = hit.mark_raw_path
            events.at[i, "native_mark_status"] = "HASH_VERIFIED_NATIVE_FUNDING_API_MARK"
            events.at[i, "ts"] = pd.Timestamp(hit.native_ms, unit="ms", tz="UTC")
            events.at[i, "rate_type"] = hit.native_type
            mappings.append({"event_id": r.event_id, "old_ts": r.ts, "native_ts": events.at[i, "ts"], "raw_sha256": hit.mark_raw_sha256})
    assert ((events.ts > events.holding_start) & (events.ts <= events.holding_end)).all(), "native timestamp moved outside actual holding window"
    events["source_rate_type"] = events.rate_type
    unknown_type = ~events.source_rate_type.isin(["Regular", "Special"])
    events["rate_type_assumption"] = np.where(unknown_type, "ESTIMATE_ASSUMES_REGULAR_UNSPECIFIED_SOURCE", "NATIVE_OR_ADJUDICATED_TYPE")
    events.loc[unknown_type, "rate_type"] = "Regular"
    assert not events.duplicated(["symbol", "ts", "rate_type"]).any(), "model type mapping collides with distinct economic events"
    event_ns = events.ts.dt.as_unit("ns").astype("int64")
    events["minute_ms"] = (event_ns // 1_000_000 // 60000 * 60000).astype("int64")
    recovered_minute = pd.to_datetime(events.minute_ms, unit="ms", utc=True)
    assert recovered_minute.eq(events.ts.dt.floor("min")).all(), "minute key does not reconstruct original UTC minute"
    assert ((events.ts - recovered_minute).dt.total_seconds().ge(0) & (events.ts - recovered_minute).dt.total_seconds().lt(60)).all()
    assert recovered_minute.dt.year.ge(2020).all()
    events["calendar_month"] = events.ts.dt.strftime("%Y-%m")
    missing = events[events.native_mark.isna()]
    jobs = []
    for (symbol, month), group in missing.groupby(["symbol", "calendar_month"], sort=True):
        first, last = int(group.minute_ms.min()), int(group.minute_ms.max())
        code = symbol.split("/")[0] + "USDT"
        small = (last - first) // 60000 + 1 <= 1500
        job_id = f"{code}-{month}"
        if small:
            source = "FAPI_MARK_1M_WINDOW"
            url = "https://fapi.binance.com/fapi/v1/markPriceKlines?" + urlencode({"symbol": code, "interval": "1m", "startTime": first, "endTime": last + 59999, "limit": 1500})
            checksum_url = None
        else:
            source = "VISION_MARK_1M_MONTH"
            url = f"https://data.binance.vision/data/futures/um/monthly/markPriceKlines/{code}/1m/{code}-1m-{month}.zip"
            checksum_url = url + ".CHECKSUM"
        jobs.append({"job_id": job_id, "symbol": symbol, "month": month, "events": len(group),
                     "source": source, "url": url, "checksum_url": checksum_url,
                     "first_minute_ms": first, "last_minute_ms": last})
    frozen_frame(OBSERVED, events)
    pd.DataFrame(coverage).to_csv(OUT / "holding-window-coverage-v2.csv", index=False)
    pd.DataFrame(mappings).to_csv(OUT / "native-mark-mappings-v2.csv", index=False)
    save_new(OUT / "existing-native-source-receipts-v2.json", native_receipts)
    plan = {"status": "EXPLORE_UNTRUSTED_ESTIMATED_FUNDING_INPUTS", "created_at": utc(),
            "script_sha256": sha(Path(__file__)), "holdings_path": str(windows_path.relative_to(ROOT)),
            "holdings_sha256": sha(windows_path), "bundle_pin": PIN, "funding_manifest_sha256": FUNDING_SHA,
            "funding_event_source_component": funding_component, "holding_windows": len(windows), "observed_events": len(events),
            "native_mark_events": int(events.native_mark.notna().sum()), "minute_proxy_required_events": len(missing),
            "source_rate_type_counts": events.source_rate_type.value_counts().to_dict(),
            "regular_type_assumed_for_unspecified_events": int(unknown_type.sum()),
            "empty_holding_windows": [r["holding_window_id"] for r in coverage if r["observed_events"] == 0],
            "observed_event_projection_sha256": sha(OBSERVED), "jobs": jobs,
            "replaces_invalid_plan": str((OUT / "plan.json").relative_to(ROOT)) if (OUT / "plan.json").exists() else None,
            "invalid_plan_reason": "pandas datetime64[us] initially divided as ns; no strategy performance computed; source prefetch unaffected" if (OUT / "plan.json").exists() else None,
            "timestamp_unit_checked": "EXPLICIT_NS_THEN_MS_AND_UTC_MINUTE_ROUNDTRIP",
            "parent_source_plan_path": str((SOURCE_CACHE_ROOT / "plan-v2.json").relative_to(ROOT)) if SOURCE_CACHE_ROOT else None,
            "parent_source_plan_sha256": sha(SOURCE_CACHE_ROOT / "plan-v2.json") if SOURCE_CACHE_ROOT else None,
            "source_cache_reuse_requires_exact_url_and_raw_hash": bool(SOURCE_CACHE_ROOT),
            "maximum_concurrency": 4, "global_request_spacing_seconds": .5, "no_retry": True,
            "rate_limit_stop_statuses": [403, 418, 429], "exact_calendar_proven": False,
            "proxy_center": "OFFICIAL_MARK_1M_EVENT_MINUTE_OPEN", "proxy_bounds": "EVENT_MINUTE_LOW_HIGH_CONDITIONAL_NOT_CONFIDENCE_INTERVAL",
            "no_missing_event_fill": True, "no_trade_price_fallback": True,
            "note": "Observed event cash estimate only; no complete funding calendar, PIT or native settlement mark certification."}
    save_new(PLAN, plan)
    print(json.dumps({k: v for k, v in plan.items() if k not in ["jobs", "funding_event_source_component"]}, default=str), flush=True)


def request_saved(url, stem):
    global NEXT_REQUEST
    raw_path = OUT / "raw" / f"{stem}.bin"
    meta_path = OUT / "raw" / f"{stem}.receipt.json"
    if meta_path.exists() and json.loads(meta_path.read_text())["url"] != url:
        # Preserve the invalid earlier source query; never reuse it for a corrected URL.
        stem += "-correct-ms-v2"
        raw_path = OUT / "raw" / f"{stem}.bin"
        meta_path = OUT / "raw" / f"{stem}.receipt.json"
    if meta_path.exists():
        receipt = json.loads(meta_path.read_text())
        assert receipt["url"] == url and sha(raw_path) == receipt["raw_sha256"]
        return raw_path.read_bytes(), receipt
    if raw_path.exists():
        raise ValueError("orphan raw evidence requires explicit review")
    if url in SOURCE_CACHE:
        cache_path, receipt = SOURCE_CACHE[url]
        assert sha(cache_path) == receipt["raw_sha256"]
        return cache_path.read_bytes(), {**receipt, "reused_hash_verified_source_cache": True}
    if STOP.is_set():
        raise RuntimeError("request scheduler stopped")
    with LOCK:
        if STOP.is_set():
            raise RuntimeError("request scheduler stopped")
        time.sleep(max(0, NEXT_REQUEST - time.monotonic()))
        NEXT_REQUEST = time.monotonic() + .5
    request_url = quote(url, safe=":/?&=%")
    receipt = {"url": url, "request_url_utf8_encoded": request_url, "requested_at": utc(), "http_status": None, "error": None}
    blob = b""
    try:
        with urlopen(Request(request_url, headers={"User-Agent": "strategy-lab-explore-funding-mark/1"}), timeout=40) as response:
            receipt.update(http_status=response.status, headers=dict(response.headers))
            blob = response.read()
    except HTTPError as error:
        receipt.update(http_status=error.code, headers=dict(error.headers), error=str(error))
        blob = error.read()
        if error.code in [403, 418, 429]:
            STOP.set()
    except (URLError, TimeoutError, OSError) as error:
        receipt["error"] = str(error)
        STOP.set()
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("xb") as stream:
        stream.write(blob)
    receipt.update(finished_at=utc(), raw_path=str(raw_path.relative_to(ROOT)), raw_sha256=sha(raw_path), bytes=len(blob))
    save_new(meta_path, receipt)
    return blob, receipt


def parse_mark_rows(blob, zipped):
    if zipped:
        with zipfile.ZipFile(io.BytesIO(blob)) as container:
            assert container.testzip() is None
            names = container.namelist()
            assert len(names) == 1
            content = container.read(names[0])
        first_cell = content.split(b",", 1)[0]
        frame = pd.read_csv(io.BytesIO(content), header=None, skiprows=0 if first_cell.isdigit() else 1)
    else:
        frame = pd.DataFrame(json.loads(blob))
    if frame.empty:
        raise ValueError("empty official mark response")
    if len(frame.columns) != 12:
        raise ValueError("wrong official mark column count")
    frame.columns = ["minute_ms", "mark_open", "mark_high", "mark_low", "mark_close", "ignored_volume", "close_ms", "ignored_quote", "observations", "ignored_taker1", "ignored_taker2", "ignore"]
    numeric = ["minute_ms", "mark_open", "mark_high", "mark_low", "mark_close", "close_ms"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric)
    assert frame.minute_ms.is_monotonic_increasing and not frame.minute_ms.duplicated().any()
    assert frame.minute_ms.mod(60000).eq(0).all()
    assert frame.close_ms.eq(frame.minute_ms + 59999).all()
    marks = frame[["mark_open", "mark_high", "mark_low", "mark_close"]]
    assert np.isfinite(marks.to_numpy()).all() and marks.gt(0).all().all()
    assert frame.mark_low.le(frame.mark_open).all() and frame.mark_low.le(frame.mark_close).all()
    assert frame.mark_high.ge(frame.mark_open).all() and frame.mark_high.ge(frame.mark_close).all()
    return frame


def effective_receipt_path(job_id):
    resumed = JOBS / f"resumed-{job_id}.json"
    return resumed if resumed.exists() else JOBS / f"{job_id}.json"


def fetch_job(job, needed):
    receipt_path = effective_receipt_path(job["job_id"])
    projection_path = OUT / "marks" / f"{job['job_id']}.parquet"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("error") == "RuntimeError: request scheduler stopped" or receipt.get("error", "").startswith("UnicodeEncodeError:"):
            # No provider failure is retried: this queued job never passed the
            # scheduler. Preserve the cancellation receipt and save a new one.
            receipt_path = JOBS / f"resumed-{job['job_id']}.json"
        else:
            if receipt.get("projection_sha256"):
                assert sha(projection_path) == receipt["projection_sha256"]
            return receipt
    try:
        payload, receipt = request_saved(job["url"], job["job_id"])
        result = {"job": job, "source_receipt": receipt, "status": "MISSING_OR_FAILED_SOURCE"}
        if receipt["http_status"] != 200:
            save_new(receipt_path, result)
            return result
        if job["checksum_url"]:
            checksum, checksum_receipt = request_saved(job["checksum_url"], job["job_id"] + "-CHECKSUM")
            result["checksum_receipt"] = checksum_receipt
            if checksum_receipt["http_status"] != 200:
                save_new(receipt_path, result)
                return result
            assert checksum.decode().split()[0] == hashlib.sha256(payload).hexdigest(), "official CHECKSUM mismatch"
        bars = parse_mark_rows(payload, bool(job["checksum_url"]))
        start, end = pd.Timestamp(job["month"] + "-01", tz="UTC"), pd.Timestamp(job["month"] + "-01", tz="UTC") + pd.offsets.MonthBegin(1)
        assert bars.minute_ms.between(int(start.timestamp() * 1000), int(end.timestamp() * 1000) - 1).all()
        selected = bars[bars.minute_ms.isin(needed)].copy()
        selected["symbol"] = job["symbol"]
        selected["mark_raw_sha256"] = receipt["raw_sha256"]
        selected["mark_raw_path"] = receipt["raw_path"]
        selected["mark_source"] = job["source"]
        projection_path.parent.mkdir(parents=True, exist_ok=True)
        frozen_frame(projection_path, selected)
        result.update(status="MINUTE_MARK_PROXY_AVAILABLE", total_source_bars=len(bars), required_minutes=len(needed),
                      returned_required_minutes=len(selected), missing_required_minutes=sorted(set(needed) - set(selected.minute_ms)),
                      source_internal_minute_gaps=int(bars.minute_ms.diff().dropna().ne(60000).sum()),
                      projection_path=str(projection_path.relative_to(ROOT)), projection_sha256=sha(projection_path))
        save_new(receipt_path, result)
        return result
    except Exception as error:
        source_empty = isinstance(error, ValueError) and str(error) == "empty official mark response"
        if not source_empty:
            STOP.set()
        result = {"job": job, "status": "EMPTY_MARK_SOURCE_REQUIRES_BOUNDED_REPAIR" if source_empty else "EXCEPTION_STOP",
                  "error": f"{type(error).__name__}: {error}", "at": utc()}
        if not receipt_path.exists():
            save_new(receipt_path, result)
        return result


def fetch(max_jobs):
    plan = json.loads(PLAN.read_text())
    assert sha(OBSERVED) == plan["observed_event_projection_sha256"]
    events = pd.read_parquet(OBSERVED)
    jobs = plan["jobs"][:max_jobs] if max_jobs else plan["jobs"]
    needed = {(s, m): g.minute_ms.unique().tolist() for (s, m), g in events[events.native_mark.isna()].groupby(["symbol", "calendar_month"])}
    completed = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_job, job, needed[(job["symbol"], job["month"])]): job for job in jobs}
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            if completed % 20 == 0 or result["status"] != "MINUTE_MARK_PROXY_AVAILABLE" or completed == len(jobs):
                print(f"mark jobs {completed}/{len(jobs)} {result['job']['job_id']} {result['status']}", flush=True)
            if STOP.is_set():
                for pending in futures:
                    pending.cancel()
                break
    print(json.dumps({"completed_jobs": completed, "selected_jobs": len(jobs), "stopped": STOP.is_set()}), flush=True)


def assemble():
    plan = json.loads(PLAN.read_text())
    assert sha(OBSERVED) == plan["observed_event_projection_sha256"]
    events = pd.read_parquet(OBSERVED)
    frames, incomplete = [], []
    for job in plan["jobs"]:
        path = effective_receipt_path(job["job_id"])
        if not path.exists():
            incomplete.append({"job": job["job_id"], "status": "NOT_ATTEMPTED"})
            continue
        result = json.loads(path.read_text())
        if result.get("projection_sha256"):
            projection = ROOT / result["projection_path"]
            assert sha(projection) == result["projection_sha256"]
            frames.append(pd.read_parquet(projection))
        if result.get("missing_required_minutes") or result["status"] != "MINUTE_MARK_PROXY_AVAILABLE":
            incomplete.append({"job": job["job_id"], "status": result["status"], "missing_minutes": result.get("missing_required_minutes")})
    repair_plan_path = OUT / "repair-plan.json"
    source_fallback_path = OUT / "source-fallback-plan.json"
    for supplementary_path in [source_fallback_path, repair_plan_path]:
        if not supplementary_path.exists():
            continue
        repair_plan = json.loads(supplementary_path.read_text())
        assert repair_plan["parent_plan_sha256"] == sha(PLAN)
        for job in repair_plan["jobs"]:
            repair_receipt = effective_receipt_path(job["job_id"])
            if repair_receipt.exists():
                repaired = json.loads(repair_receipt.read_text())
                if repaired.get("projection_sha256"):
                    projection = ROOT / repaired["projection_path"]
                    assert sha(projection) == repaired["projection_sha256"]
                    frames.append(pd.read_parquet(projection))
    marks = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["symbol", "minute_ms", "mark_open", "mark_high", "mark_low", "mark_raw_sha256", "mark_raw_path", "mark_source"])
    assert not marks.duplicated(["symbol", "minute_ms"]).any()
    selected = marks[["symbol", "minute_ms", "mark_open", "mark_high", "mark_low", "mark_raw_sha256", "mark_raw_path", "mark_source"]]
    result = events.merge(selected, on=["symbol", "minute_ms"], how="left", validate="many_to_one", suffixes=("_native", "_minute"))
    native = result.native_mark.notna()
    result["mark_center"] = result.native_mark.where(native, result.mark_open)
    result["mark_low"] = result.native_mark.where(native, result.mark_low)
    result["mark_high"] = result.native_mark.where(native, result.mark_high)
    result["mark_source"] = result.mark_source.where(~native, "HASH_VERIFIED_NATIVE_FUNDING_API_MARK")
    result["mark_quality"] = np.where(native, "NATIVE_MARK_SOURCE_VERIFIED_CALENDAR_NOT_PROVEN", np.where(result.mark_center.notna(), "EXPLORE_UNTRUSTED_MARK_1M_PROXY", "MISSING_MARK_NOT_ZERO"))
    result["mark_raw_sha256"] = result.mark_raw_sha256_native.where(native, result.mark_raw_sha256_minute)
    result["mark_raw_path"] = result.mark_raw_path_native.where(native, result.mark_raw_path_minute)
    result["calendar_proven_for_strategy"] = False
    result["net_return_verified"] = False
    result = result.sort_values(["ts", "symbol", "rate_type"]).reset_index(drop=True)
    assert result.mark_low.le(result.mark_center).fillna(False).equals(result.mark_center.notna())
    assert result.mark_center.le(result.mark_high).fillna(False).equals(result.mark_center.notna())
    frozen_frame(OUT / "estimated-funding-events.parquet", result)
    result.to_csv(OUT / "estimated-funding-events.csv", index=False)
    summary = {"status": "EXPLORE_UNTRUSTED_OBSERVED_FUNDING_CASH_INPUTS", "generated_at": utc(),
               "plan_path": str(PLAN.relative_to(ROOT)), "plan_sha256": sha(PLAN), "events": len(result), "native_mark_events": int(native.sum()),
               "minute_proxy_events": int((~native & result.mark_center.notna()).sum()), "missing_mark_events": int(result.mark_center.isna().sum()),
               "all_observed_event_marks_usable": bool(result.mark_center.notna().all()),
               "original_jobs_with_source_gaps_or_failures": incomplete,
               "jobs_incomplete": result.loc[result.mark_center.isna(), ["symbol", "ts", "calendar_month"]].to_dict("records"),
               "events_sha256": sha(OUT / "estimated-funding-events.parquet"), "calendar_complete_proven": False,
               "unknown_or_missing_events_not_filled": True, "source_timestamp_and_type_fields_preserved": True,
               "native_time_changes_require_authority_mapping": True,
               "modeled_regular_for_unspecified_count": plan["regular_type_assumed_for_unspecified_events"],
               "conditional_bounds_not_confidence_interval": True, "pit_or_live_ready": False}
    calendar_path = OUT / "calendar-observed-audit.json"
    if calendar_path.exists():
        calendar = json.loads(calendar_path.read_text())
        assert calendar["plan_sha256"] == sha(PLAN)
        summary["calendar_audit_path"] = str(calendar_path.relative_to(ROOT))
        summary["calendar_audit_sha256"] = sha(calendar_path)
        summary["known_missing_expected_events_within_frozen_proven_segments"] = calendar["known_missing_expected_events_within_frozen_proven_segments"]
        summary["observed_events_outside_partial_proven_calendar"] = calendar["observed_events_outside_partial_proven_calendar"]
        summary["empty_holding_windows"] = calendar["empty_holding_windows"]
    if repair_plan_path.exists():
        summary["repair_plan_path"] = str(repair_plan_path.relative_to(ROOT))
        summary["repair_plan_sha256"] = sha(repair_plan_path)
    if source_fallback_path.exists():
        summary["source_fallback_plan_path"] = str(source_fallback_path.relative_to(ROOT))
        summary["source_fallback_plan_sha256"] = sha(source_fallback_path)
    summary["assembly_script_sha256"] = sha(Path(__file__))
    save_new(OUT / "summary.json", summary)
    print(json.dumps(summary, default=str), flush=True)


def repair():
    """只对本批已完成月档中的实际缺分钟另取有界1m官方API日窗口。"""
    plan = json.loads(PLAN.read_text())
    missing = []
    for job in plan["jobs"]:
        receipt_path = effective_receipt_path(job["job_id"])
        if not receipt_path.exists():
            raise ValueError("Finish or explicitly adjudicate main source batch before freezing repairs")
        receipt = json.loads(receipt_path.read_text())
        if receipt["status"] != "MINUTE_MARK_PROXY_AVAILABLE":
            fallback_plan_path = OUT / "source-fallback-plan.json"
            if not fallback_plan_path.exists():
                raise ValueError(f"Source failure needs its frozen monthly fallback first: {job['job_id']}")
            alternatives = [j for j in json.loads(fallback_plan_path.read_text())["jobs"] if j.get("parent_job") == job["job_id"]]
            if not alternatives:
                raise ValueError(f"No frozen source alternative for {job['job_id']}")
            fallback_missing = []
            for alternative in alternatives:
                alternate_receipt = effective_receipt_path(alternative["job_id"])
                if not alternate_receipt.exists():
                    raise ValueError(f"Source alternative unattempted: {alternative['job_id']}")
                receipt = json.loads(alternate_receipt.read_text())
                if receipt["status"] != "MINUTE_MARK_PROXY_AVAILABLE":
                    raise ValueError(f"Both source variants failed; needs review: {alternative['job_id']}")
                fallback_missing.extend(receipt.get("missing_required_minutes", []))
            receipt = {"missing_required_minutes": fallback_missing}
        for timestamp in receipt.get("missing_required_minutes", []):
            missing.append({"symbol": job["symbol"], "minute_ms": timestamp,
                            "date": pd.Timestamp(timestamp, unit="ms", tz="UTC").strftime("%Y-%m-%d"),
                            "parent_job": job["job_id"]})
    jobs, needed = [], {}
    for (symbol, date), group in pd.DataFrame(missing, columns=["symbol", "date", "minute_ms", "parent_job"]).groupby(["symbol", "date"], sort=True):
        code = symbol.split("/")[0] + "USDT"
        first, last = int(group.minute_ms.min()), int(group.minute_ms.max())
        job_id = f"repair-{code}-{date}"
        assert (last - first) // 60000 < 1440
        url = "https://fapi.binance.com/fapi/v1/markPriceKlines?" + urlencode({"symbol": code, "interval": "1m", "startTime": first, "endTime": last + 59999, "limit": 1500})
        jobs.append({"job_id": job_id, "symbol": symbol, "month": date[:7], "events": len(group),
                     "source": "FAPI_MARK_1M_REPAIR_WINDOW", "url": url, "checksum_url": None,
                     "first_minute_ms": first, "last_minute_ms": last, "required_minutes": sorted(group.minute_ms.tolist())})
        needed[job_id] = sorted(group.minute_ms.tolist())
    path = OUT / "repair-plan.json"
    if path.exists():
        prior = json.loads(path.read_text())
        assert prior["parent_plan_sha256"] == sha(PLAN) and prior["jobs"] == jobs
    else:
        save_new(path, {"status": "MINUTE_SOURCE_GAP_REPAIR_NOT_CALENDAR_REPAIR", "created_at": utc(),
                       "parent_plan_sha256": sha(PLAN), "script_sha256": sha(Path(__file__)),
                       "jobs": jobs, "missing_minutes": len(missing), "no_zero_fill": True,
                       "source_selected_before_strategy_returns": True, "maximum_concurrency": 4,
                       "global_request_spacing_seconds": .5, "no_retry": True})
    print(f"frozen minute repairs jobs={len(jobs)} missing_minutes={len(missing)}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_job, job, needed[job["job_id"]]): job for job in jobs}
        count = 0
        for future in as_completed(futures):
            response = future.result()
            count += 1
            if count % 10 == 0 or response["status"] != "MINUTE_MARK_PROXY_AVAILABLE" or count == len(jobs):
                print(f"minute repairs {count}/{len(jobs)} {response['job']['job_id']} {response['status']}", flush=True)
            if STOP.is_set():
                for pending in futures:
                    pending.cancel()
                break


def source_fallback():
    """官方小窗口空源只补同月官方1m档；不重试失败endpoint或更换主机绕过封禁。"""
    plan = json.loads(PLAN.read_text())
    events = pd.read_parquet(OBSERVED)
    jobs, needed = [], {}
    for job in plan["jobs"]:
        path = effective_receipt_path(job["job_id"])
        if not path.exists():
            raise ValueError("Wait for main source attempts before freezing fallback scope")
        result = json.loads(path.read_text())
        if result["status"] == "MINUTE_MARK_PROXY_AVAILABLE":
            continue
        source_empty = "empty official mark response" in result.get("error", "")
        http400 = result.get("source_receipt", {}).get("http_status") == 400
        code = job["symbol"].split("/")[0] + "USDT"
        relevant = events.loc[events.symbol.eq(job["symbol"]) & events.calendar_month.eq(job["month"]) & events.native_mark.isna(), ["minute_ms"]].drop_duplicates()
        if job["source"] == "FAPI_MARK_1M_WINDOW" and (source_empty or http400):
            url = f"https://data.binance.vision/data/futures/um/monthly/markPriceKlines/{code}/1m/{code}-1m-{job['month']}.zip"
            fallback = {**job, "job_id": "fallback-" + job["job_id"], "parent_job": job["job_id"], "source": "VISION_MARK_1M_FALLBACK_MONTH", "url": url, "checksum_url": url + ".CHECKSUM"}
            jobs.append(fallback)
            needed[fallback["job_id"]] = relevant.minute_ms.tolist()
        elif job["source"] == "VISION_MARK_1M_MONTH" and result.get("source_receipt", {}).get("http_status") == 404:
            relevant["day"] = pd.to_datetime(relevant.minute_ms, unit="ms", utc=True).dt.strftime("%Y-%m-%d")
            for day, group in relevant.groupby("day"):
                first, last = int(group.minute_ms.min()), int(group.minute_ms.max())
                assert (last - first) // 60000 < 1440
                url = "https://fapi.binance.com/fapi/v1/markPriceKlines?" + urlencode({"symbol": code, "interval": "1m", "startTime": first, "endTime": last + 59999, "limit": 1500})
                fallback = {**job, "job_id": f"fallback-day-{code}-{day}", "parent_job": job["job_id"], "source": "FAPI_MARK_1M_FALLBACK_DAY", "url": url, "checksum_url": None,
                            "events": len(group), "first_minute_ms": first, "last_minute_ms": last}
                jobs.append(fallback)
                needed[fallback["job_id"]] = group.minute_ms.tolist()
        else:
            raise ValueError(f"Unexpected source failure is not authorized fallback: {job['job_id']}")
    path = OUT / "source-fallback-plan.json"
    if path.exists():
        prior = json.loads(path.read_text())
        assert prior["parent_plan_sha256"] == sha(PLAN) and prior["jobs"] == jobs
    else:
        save_new(path, {"status": "OFFICIAL_1M_ONLY_BOUNDED_SOURCE_ALTERNATIVES", "created_at": utc(),
                       "parent_plan_sha256": sha(PLAN), "jobs": jobs, "no_strategy_selection_changes": True,
                       "same_minute_proxy_definition": True, "no_retry_failed_endpoint": True})
    print(f"frozen source fallbacks {len(jobs)}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_job, job, needed[job["job_id"]]): job for job in jobs}
        for future in as_completed(futures):
            result = future.result()
            print(f"source fallback {result['job']['job_id']} {result['status']}", flush=True)
            if STOP.is_set():
                for pending in futures:
                    pending.cancel()
                break


def probe():
    """最早实际成员的整月官方1m月档可用性；原文可被正式job复用。"""
    job_id = "BTCUSDT-2020-03"
    url = "https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2020-03.zip"
    save_new(OUT / "source-probe-plan.json", {"created_at": utc(), "purpose": "SOURCE_SCHEMA_AVAILABILITY_ONLY", "symbol": "BTC/USDT:USDT",
             "month": "2020-03", "url": url, "checksum_url": url + ".CHECKSUM", "max_requests": 2,
             "script_sha256": sha(Path(__file__)), "no_retry": True, "funding_mark_exact": False})
    payload, receipt = request_saved(url, job_id)
    checksum, checksum_receipt = request_saved(url + ".CHECKSUM", job_id + "-CHECKSUM")
    result = {"source_receipt": receipt, "checksum_receipt": checksum_receipt, "status": "SOURCE_UNAVAILABLE"}
    if receipt["http_status"] == 200 and checksum_receipt["http_status"] == 200:
        assert checksum.decode().split()[0] == hashlib.sha256(payload).hexdigest()
        bars = parse_mark_rows(payload, True)
        target = int(pd.Timestamp("2020-03-01T08:00:00Z").timestamp() * 1000)
        result.update(status="OFFICIAL_1M_MARK_SOURCE_AVAILABLE", rows=len(bars), raw_bytes=len(payload),
                      first_held_event_minute=bars[bars.minute_ms.eq(target)].to_dict("records"),
                      full_month_grid=bool(len(bars) == 31 * 1440 and bars.minute_ms.diff().dropna().eq(60000).all()))
    save_new(OUT / "source-probe-qa.json", result)
    print(json.dumps(result, default=str), flush=True)


def prefetch(max_jobs):
    """仅按已冻结原始成员预取原文，最终按新holding计划消费。"""
    source = FAMILY / "artifacts/binance-1d-mcsm-long10-diagnostic-2026-08-18-holdings.csv"
    old = pd.read_csv(source)
    old = old[old.variant.eq("adv10m_top10_long_only") & old.status.eq("traded")].sort_values("rebalance")
    jobs = []
    for row in old.itertuples():
        for symbol in row.longs.split(","):
            code, month = symbol + "USDT", row.rebalance[:7]
            url = f"https://data.binance.vision/data/futures/um/monthly/markPriceKlines/{code}/1m/{code}-1m-{month}.zip"
            jobs.append({"job_id": f"{code}-{month}", "url": url, "month": month, "symbol": symbol})
    jobs = jobs[:max_jobs or 100]
    plan_path = OUT / "source-prefetch-plan.json"
    if plan_path.exists():
        prior = json.loads(plan_path.read_text())
        assert prior["source_sha256"] == sha(source) and prior["jobs"] == jobs
    else:
        save_new(plan_path, {"status": "RAW_SOURCE_PREFETCH_ONLY_NOT_FINAL_HOLDINGS", "created_at": utc(),
                            "source_path": str(source.relative_to(ROOT)), "source_sha256": sha(source),
                            "script_sha256": sha(Path(__file__)), "jobs": jobs,
                            "selection": "FIRST_FROZEN_ORIGINAL_MONTHS_NOT_PNL_SELECTED", "final_consumer_must_use_final_holdings": True})
    def one(job):
        dest = OUT / "prefetch-qa" / f"{job['job_id']}.json"
        if dest.exists():
            return json.loads(dest.read_text())
        try:
            blob, receipt = request_saved(job["url"], job["job_id"])
            check, check_receipt = request_saved(job["url"] + ".CHECKSUM", job["job_id"] + "-CHECKSUM")
            result = {"job": job, "source_receipt": receipt, "checksum_receipt": check_receipt, "status": "SOURCE_FAILED"}
            if receipt["http_status"] == 200 and check_receipt["http_status"] == 200:
                assert check.decode().split()[0] == hashlib.sha256(blob).hexdigest()
                frame = parse_mark_rows(blob, True)
                result.update(status="RAW_MINUTE_MARK_AVAILABLE", rows=len(frame), bytes=len(blob))
            save_new(dest, result)
            return result
        except Exception as error:
            STOP.set()
            return {"job": job, "status": "EXCEPTION_STOP", "error": str(error)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(one, job): job for job in jobs}
        count = 0
        for future in as_completed(futures):
            result = future.result()
            count += 1
            if count % 10 == 0 or result["status"] != "RAW_MINUTE_MARK_AVAILABLE":
                print(f"prefetch {count}/{len(jobs)} {result['job']['job_id']} {result['status']}", flush=True)
            if STOP.is_set():
                for pending in futures:
                    pending.cancel()
                break


def main():
    global OUT, PLAN, OBSERVED, JOBS, SOURCE_CACHE, SOURCE_CACHE_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["probe", "prefetch", "prepare", "fetch", "source-fallback", "repair", "assemble"], required=True)
    parser.add_argument("--windows", type=Path)
    parser.add_argument("--max-jobs", type=int)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--source-cache-root", type=Path)
    args = parser.parse_args()
    if args.out:
        OUT = args.out.resolve()
        assert OUT.is_relative_to(FAMILY / "artifacts/baseline-estimate-20260909"), "output must remain in this exploratory family run"
        PLAN, OBSERVED, JOBS = OUT / "plan-v2.json", OUT / "observed-held-events-v2.parquet", OUT / "jobs-v2"
    if args.source_cache_root:
        cache_root = args.source_cache_root.resolve()
        SOURCE_CACHE_ROOT = cache_root
        assert cache_root.is_relative_to(FAMILY / "artifacts/baseline-estimate-20260909")
        for meta_path in sorted((cache_root / "raw").glob("*.receipt.json")):
            receipt = json.loads(meta_path.read_text())
            path = ROOT / receipt["raw_path"]
            assert path.is_relative_to(cache_root)
            if receipt["url"] in SOURCE_CACHE:
                assert SOURCE_CACHE[receipt["url"]][1]["raw_sha256"] == receipt["raw_sha256"], "source cache conflict"
            SOURCE_CACHE[receipt["url"]] = (path, receipt)
    if args.phase == "probe":
        probe()
    elif args.phase == "prefetch":
        prefetch(args.max_jobs)
    elif args.phase == "prepare":
        if args.windows is None:
            raise ValueError("--windows is required")
        prepare(args.windows.resolve())
    elif args.phase == "fetch":
        fetch(args.max_jobs)
    elif args.phase == "repair":
        repair()
    elif args.phase == "source-fallback":
        source_fallback()
    else:
        assemble()


if __name__ == "__main__":
    main()
