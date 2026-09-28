"""冻结首月首持仓日的原生资金费标记价补证；最多九请求，不改旧探针。"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
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
BASE = FAMILY / "artifacts/baseline-verification-20260908"
OUT = BASE / "funding-evidence/first-held-day"
HOLDINGS = BASE / "plan/required-holding-windows.csv"
SYMBOLS = ["LINK", "ETH", "XRP", "TRX", "ADA", "LTC", "EOS", "BCH", "ETC"]
START, END = "2020-03-01T00:15:00+00:00", "2020-03-02T00:15:00+00:00"


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def ms(text):
    return int(datetime.fromisoformat(text).timestamp() * 1000)


def save(path, value):
    path.parent.mkdir(exist_ok=True, parents=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def valid_mark(row):
    try:
        mark = float(row.get("markPrice"))
        return math.isfinite(mark) and mark > 0
    except (TypeError, ValueError):
        return False


def first_event(rows, symbol, actual, source_path, source_sha):
    rows = [r for r in rows if r["symbol"] == symbol + "USDT" and ms(START) < r["fundingTime"] <= ms(END)]
    rows.sort(key=lambda r: r["fundingTime"])
    row = rows[0] if rows else None
    return {"symbol": symbol + "/USDT:USDT", "actual_first_month_observed_candidate": actual,
            "returned_held_day_events": len(rows), "valid_mark_events": sum(valid_mark(r) for r in rows),
            "first_held_event": row, "first_held_event_mark_valid": bool(row and valid_mark(row)),
            "raw_path": str(source_path.relative_to(ROOT)), "raw_sha256": source_sha,
            "first_held_event_utc": datetime.fromtimestamp(row["fundingTime"] / 1000, timezone.utc).isoformat() if row else None,
            "calendar_verified": False, "net_pnl_verified": False}


def main():
    with HOLDINGS.open() as stream:
        first_month = [r for r in csv.DictReader(stream) if r["start"] == "2020-03-01 00:15:00+00:00"]
    actual = {r["symbol"].split("/")[0] for r in first_month}
    assert "BTC" in actual
    assert actual <= set(SYMBOLS) | {"BTC"}
    plan = {"frozen_at": now(), "script_sha256": sha(Path(__file__).read_bytes()),
            "holdings_path": str(HOLDINGS.relative_to(ROOT)), "holdings_sha256": sha(HOLDINGS.read_bytes()),
            "purpose": "FIRST_ACTUAL_HOLDING_FUNDING_MARK_AVAILABILITY_ONLY", "first_month_symbols": sorted(actual),
            "queries": [{"symbol": s + "USDT", "actual_first_month_candidate": s in actual,
                         "startTime": ms(START) + 1, "endTime": ms(END), "limit": 1000} for s in SYMBOLS],
            "window_semantics": "(2020-03-01 00:15 UTC,2020-03-02 00:15 UTC]", "maximum_requests": 9,
            "minimum_request_spacing_seconds": 2, "single_worker": True, "stop_on_any_http_error": True,
            "retries": 0, "alternate_hosts": False, "mark_kline_substitution": False,
            "extra_control_not_in_observed_first_month": sorted(set(SYMBOLS) - actual)}
    save(OUT / "plan.json", plan)
    old_receipt = json.loads((BASE / "funding-evidence/04-BTCUSDT-2020-03-01-receipt.json").read_text())
    old_raw = ROOT / old_receipt["raw_path"]
    assert sha(old_raw.read_bytes()) == old_receipt["raw_sha256"]
    results = [first_event(json.loads(old_raw.read_bytes()), "BTC", True, old_raw, old_receipt["raw_sha256"])]
    save(OUT / "BTC-first-held-event-existing-source.json", results[0])
    receipts = []
    for idx, query in enumerate(plan["queries"], 1):
        if idx > 1:
            time.sleep(2)
        url = "https://fapi.binance.com/fapi/v1/fundingRate?" + urlencode({k: query[k] for k in ["symbol", "startTime", "endTime", "limit"]})
        receipt = {"query": query, "url": url, "requested_at": now(), "http_status": None, "error": None}
        blob = b""
        try:
            with urlopen(Request(url, headers={"User-Agent": "strategy-lab-baseline-first-held-event"}), timeout=25) as response:
                receipt.update(http_status=response.status, headers=dict(response.headers))
                blob = response.read()
        except HTTPError as failure:
            receipt.update(http_status=failure.code, headers=dict(failure.headers), error=str(failure))
            blob = failure.read()
        except (URLError, TimeoutError, OSError) as failure:
            receipt["error"] = str(failure)
        path = OUT / f"{idx:02d}-{query['symbol']}-raw-response.bin"
        with path.open("xb") as stream:
            stream.write(blob)
        receipt.update(finished_at=now(), raw_path=str(path.relative_to(ROOT)), raw_sha256=sha(blob), raw_bytes=len(blob))
        if receipt["http_status"] == 200:
            try:
                rows = json.loads(blob)
                assert isinstance(rows, list) and len(rows) < 1000
                assert all(r["symbol"] == query["symbol"] and query["startTime"] <= r["fundingTime"] <= query["endTime"] for r in rows)
                result = first_event(rows, SYMBOLS[idx - 1], query["actual_first_month_candidate"], path, sha(blob))
                receipt["result"] = result
                results.append(result)
            except (AssertionError, ValueError, KeyError, TypeError) as failure:
                receipt["error"] = f"Invalid raw response: {failure}"
        save(OUT / f"{idx:02d}-{query['symbol']}-receipt.json", receipt)
        receipts.append(receipt)
        print(json.dumps(receipt.get("result", {"query": query, "error": receipt["error"]}), ensure_ascii=False), flush=True)
        if receipt["error"]:
            break
    summary = {"status": "ACTUAL_FIRST_HELD_FUNDING_MARK_MISSING" if any(r["actual_first_month_observed_candidate"] and not r["first_held_event_mark_valid"] for r in results) else "SOURCE_DIAGNOSTIC_ONLY",
               "completed_at": now(), "requests_attempted": len(receipts), "first_month_candidate_count": len(actual),
               "first_month_candidates_queried_including_btc_reuse": sum(r["actual_first_month_observed_candidate"] for r in results),
               "actual_candidates_first_mark_missing": [r["symbol"] for r in results if r["actual_first_month_observed_candidate"] and not r["first_held_event_mark_valid"]],
               "results": results, "net_pnl_verified": False, "holdings_plan_sha256": plan["holdings_sha256"]}
    save(OUT / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
