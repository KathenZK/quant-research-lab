"""原基线资金费结算标记价格有界来源探针；不写湖，不计算净值。"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-long10"
OUT = FAMILY / "artifacts/baseline-verification-20260908/funding-evidence"
RAW = ROOT / "data/raw/funding_rates/exchange=binance/market_type=perp/source=binance_futures_funding_rate_api"
DOC = "https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data"
PROBES = [
    ("HOMEUSDT", "2026-06-01", "2026-07-01"),
    ("LABUSDT", "2026-06-01", "2026-07-01"),
    ("HUSDT", "2026-06-01", "2026-07-01"),
    ("BTCUSDT", "2020-03-01", "2020-04-01"),
    ("BTCUSDT", "2026-06-01", "2026-07-01"),
    ("BTCUSDT", "2026-09-01", "2026-09-05"),
]


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def dump_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def ms(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


def valid_mark(row):
    try:
        number = float(row.get("markPrice"))
        return math.isfinite(number) and number > 0
    except (TypeError, ValueError):
        return False


def row_summary(rows):
    if not isinstance(rows, list):
        return {"response_is_list": False}
    marks = [r for r in rows if valid_mark(r)]
    return {"response_is_list": True, "rows": len(rows), "finite_positive_mark_rows": len(marks),
            "rows_with_mark_key": sum("markPrice" in r for r in rows),
            "first_ms": min((r["fundingTime"] for r in rows), default=None),
            "last_ms": max((r["fundingTime"] for r in rows), default=None),
            "first_mark_ms": min((r["fundingTime"] for r in marks), default=None),
            "last_mark_ms": max((r["fundingTime"] for r in marks), default=None)}


def inspect_local():
    files = []
    by_run = Counter()
    marked_by_run = Counter()
    symbols = set()
    exact = {f"{s}:{a}:{b}": {"observed_rows": 0, "marked_rows": 0, "matching_paths": []}
             for s, a, b in PROBES}
    for path in sorted(RAW.rglob("*.json.gz")):
        raw = path.read_bytes()
        content = gzip.decompress(raw)
        rows = json.loads(content)
        summary = row_summary(rows)
        meta_path = path.with_suffix(".meta.json")
        receipt = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        hash_match = receipt.get("sha256") == digest(raw)
        if receipt and not hash_match:
            raise ValueError(f"Existing receipt hash mismatch: {path}")
        files.append({"path": str(path.relative_to(ROOT)), "sha256": digest(raw),
                      "raw_sha256": digest(content), "receipt_hash_verified": hash_match, **summary})
        run = path.parent.name
        by_run[run] += summary.get("rows", 0)
        marked_by_run[run] += summary.get("finite_positive_mark_rows", 0)
        if isinstance(rows, list):
            symbols.update(r["symbol"] for r in rows if valid_mark(r))
            for s, a, b in PROBES:
                hits = [r for r in rows if r.get("symbol") == s and ms(a) <= r["fundingTime"] < ms(b)]
                if hits:
                    item = exact[f"{s}:{a}:{b}"]
                    item["observed_rows"] += len(hits)
                    item["marked_rows"] += sum(valid_mark(r) for r in hits)
                    item["matching_paths"].append(str(path.relative_to(ROOT)))
    result = {"status": "RAW_SOURCE_INVENTORY_NOT_NET_VERIFIED", "root": str(RAW.relative_to(ROOT)),
              "inspected_at": stamp(), "files": files, "rows_by_run_including_query_overlap": dict(by_run),
              "marked_rows_by_run_including_query_overlap": dict(marked_by_run),
              "marked_symbols": sorted(symbols), "probe_window_local_matches_including_overlap": exact}
    dump_new(OUT / "local-native-api-inventory.json", result)
    return {"files": len(files), "rows": sum(by_run.values()), "marked_rows": sum(marked_by_run.values()),
            "marked_symbols": len(symbols), "probe_windows": exact}


def probe():
    plan = {"purpose": "FUNDING_SETTLEMENT_MARK_AVAILABILITY_ONLY", "frozen_at": stamp(),
            "script_sha256": digest(Path(__file__).read_bytes()), "official_documentation_url": DOC,
            "probes": [{"symbol": s, "start_utc": a, "end_exclusive_utc": b,
                        "start_ms": ms(a), "end_inclusive_ms": ms(b) - 1, "limit": 1000} for s, a, b in PROBES],
            "maximum_requests": len(PROBES), "single_worker": True, "minimum_interval_seconds": 2,
            "stop_on_any_http_error": True, "no_retry_no_alternate_host": True,
            "trade_price_or_mark_kline_substitution": False,
            "api_event_list_is_not_independent_historical_calendar_proof": True}
    dump_new(OUT / "probe-plan.json", plan)
    results = []
    for index, job in enumerate(plan["probes"]):
        if index:
            time.sleep(2)
        params = {"symbol": job["symbol"], "startTime": job["start_ms"],
                  "endTime": job["end_inclusive_ms"], "limit": 1000}
        url = "https://fapi.binance.com/fapi/v1/fundingRate?" + urlencode(params)
        before = stamp()
        headers, status, error = {}, None, None
        blob = b""
        try:
            with urlopen(Request(url, headers={"User-Agent": "strategy-lab-baseline-funding-probe"}), timeout=25) as response:
                status, headers, blob = response.status, dict(response.headers), response.read()
        except HTTPError as failure:
            status, headers, blob = failure.code, dict(failure.headers), failure.read()
            error = str(failure)
        except (URLError, TimeoutError, OSError) as failure:
            error = str(failure)
        name = f"{index + 1:02d}-{job['symbol']}-{job['start_utc']}"
        path = OUT / f"{name}-raw-response.bin"
        with path.open("xb") as stream:
            stream.write(blob)
        result = {**job, "url": url, "requested_at": before, "finished_at": stamp(),
                  "http_status": status, "headers": headers, "error": error,
                  "raw_path": str(path.relative_to(ROOT)), "raw_sha256": digest(blob),
                  "raw_bytes": len(blob), "calendar_verified": False, "net_pnl_verified": False}
        if status == 200:
            try:
                rows = json.loads(blob)
                result.update(row_summary(rows))
                if not isinstance(rows, list):
                    raise ValueError("Non-list response")
                if any(r["symbol"] != job["symbol"] or not job["start_ms"] <= r["fundingTime"] <= job["end_inclusive_ms"] for r in rows):
                    raise ValueError("Returned events outside requested range/symbol")
                if [r["fundingTime"] for r in rows] != sorted(r["fundingTime"] for r in rows):
                    raise ValueError("Event order invalid")
                result["list_not_limit_truncated"] = len(rows) < 1000
                result["availability"] = ("MARK_VALUES_RETURNED" if result["finite_positive_mark_rows"] else
                                         "EVENTS_WITHOUT_USABLE_MARK" if rows else "EMPTY_NOT_ABSENCE_PROOF")
            except (ValueError, KeyError, TypeError) as failure:
                result["error"] = str(failure)
        results.append(result)
        dump_new(OUT / f"{name}-receipt.json", result)
        print(json.dumps({k: result.get(k) for k in ["symbol", "start_utc", "http_status", "rows", "finite_positive_mark_rows", "availability", "error"]}), flush=True)
        if error or result.get("error"):
            break
    dump_new(OUT / "probe-summary.json", {"status": "SOURCE_PROBE_ONLY_NOT_NET_VERIFIED", "completed_at": stamp(),
               "requests_planned": len(PROBES), "requests_attempted": len(results), "results": results})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args()
    if not args.probe_only:
        print(json.dumps(inspect_local(), ensure_ascii=False), flush=True)
    if not args.local_only:
        probe()


if __name__ == "__main__":
    main()
