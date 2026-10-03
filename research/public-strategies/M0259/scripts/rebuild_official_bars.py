#!/usr/bin/env python3
"""Bounded, immutable Binance Vision spot archive capture, audit and rebuild.

This is a raw, diagnostic snapshot, not LAB_OHLCV_V1 or trusted lake ingestion.
No credentials, repo imports, installs, strategy execution, or raw-data upload.
Use only after the operator has reviewed the applicable dataset terms.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

VERSION = "binance-vision-spot-btcusdt-native12-v1"
UTC = timezone.utc
MIN_FREE = 5 * 1024**3
MAX_DOWNLOAD_BYTES = 2 * 1024**2
MAX_CSV_BYTES = 8 * 1024**2
BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT"
TERMS_URL = "https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md"
TERMS_SHA256 = "dcf358e9d18f598a7a635fac80f6e643fa24a0e111a4d39bda47f1e246b31eb1"
README_URL = "https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/README.md"
FIELD_DOC_URL = "https://github.com/binance/binance-spot-api-docs/blob/828ca74b809cfedbd5602df328b5f706368d483b/rest-api.md#klinecandlestick-data"
NATIVE = ["open_time", "open", "high", "low", "close", "volume", "close_time",
          "quote_volume", "trade_count", "taker_buy_base_volume",
          "taker_buy_quote_volume", "ignore"]
ADDED = ["ts", "exchange", "market_type", "timeframe", "symbol", "native_symbol",
         "source", "bar_close_ts", "source_archive"]
START = datetime(2022, 12, 1, tzinfo=UTC)
END = datetime(2025, 1, 1, tzinfo=UTC)
INTERVALS = {"1h": 3600000, "4h": 14400000}


class CaptureError(Exception):
    pass


def now():
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise CaptureError(message)


def ms(dt):
    return int(dt.timestamp() * 1000)


def iso_ms(timestamp):
    seconds, milli = divmod(timestamp, 1000)
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S") + f".{milli:03d}Z"


def months():
    return ["2022-12"] + [f"{y}-{m:02d}" for y in (2023, 2024) for m in range(1, 13)]


def assert_disk(parent, allocation=MAX_CSV_BYTES):
    free = shutil.disk_usage(parent).free
    require(free - allocation > MIN_FREE, f"DISK_RESERVE: {free} free bytes; must retain > {MIN_FREE}")
    return free


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert_disk(path.parent, len(data))
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path, obj):
    write_new(path, (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CaptureError(f"REDIRECT_REFUSED: {req.full_url} -> {newurl}, HTTP {code}")


def fetch(url, target):
    # Exact pinned public source. No alternate hosts, proxy changes or retries.
    require(url.startswith(BASE + "/"), f"SOURCE_REJECTED: {url}")
    require(urllib.parse.urlparse(url).netloc == "data.binance.vision", f"SOURCE_REJECTED: {url}")
    started = now()
    req = urllib.request.Request(url, headers={"User-Agent": "offline-research-archive-audit/1.0"})
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=60) as response:
            require(response.status == 200, f"UNAVAILABLE: HTTP {response.status} {url}")
            body = response.read(MAX_DOWNLOAD_BYTES + 1)
            require(len(body) <= MAX_DOWNLOAD_BYTES, f"DOWNLOAD_CAP_EXCEEDED: {url}")
            headers = dict(response.headers.items())
            final_url = response.url
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CaptureError(f"UNAVAILABLE: GET {url}: {type(exc).__name__}: {exc}") from exc
    ended = now()
    declared = headers.get("Content-Length")
    require(declared is None or int(declared) == len(body), f"TRUNCATED: {url}")
    write_new(target, body)
    receipt = {"path": str(target.name), "url": url, "final_url": final_url,
               "method": "GET", "status": 200, "bytes": len(body), "sha256": digest(body),
               "fetch_started_at_utc": started, "fetch_completed_at_utc": ended,
               "http_headers": headers}
    write_json(target.with_name(target.name + ".http.json"), receipt)
    time.sleep(0.15)
    return body, receipt


def integer(text, name):
    require(re.fullmatch(r"[0-9]+", text) is not None, f"SCHEMA: invalid {name}: {text!r}")
    return int(text)


def number(text, name):
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise CaptureError(f"SCHEMA: invalid {name}: {text!r}") from exc
    require(value.is_finite(), f"SCHEMA: nonfinite {name}")
    return value


def audit_csv(data, timeframe, month):
    require(timeframe in INTERVALS, "UNSUPPORTED_TIMEFRAME")
    year, mon = map(int, month.split("-"))
    month_start = datetime(year, mon, 1, tzinfo=UTC)
    days = calendar.monthrange(year, mon)[1]
    duration = INTERVALS[timeframe]
    expected = days * 86400000 // duration
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"), newline="")))
    require(len(rows) == expected, f"COVERAGE: {timeframe} {month}: {len(rows)} != {expected}")
    opens, zero_volumes, zero_trades, ignored_values = set(), [], [], set()
    max_quote_rounding_error = Decimal("0")
    for index, row in enumerate(rows):
        context = f"{timeframe}/{month}/row={index + 1}"
        require(len(row) == 12, f"SCHEMA: {context}: {len(row)} fields")
        require(all(x != "" and x == x.strip() for x in row), f"SCHEMA: blank/whitespace {context}")
        opened = integer(row[0], "open_time")
        closed = integer(row[6], "close_time")
        require(opened not in opens, f"DUPLICATE: {context}: {opened}")
        opens.add(opened)
        require(opened == ms(month_start) + index * duration, f"GRID_ORDER_GAP: {context}: {opened}")
        require(closed == opened + duration - 1, f"CLOSE_TIME: {context}: {closed}")
        op, hi, lo, cl, vol = [number(row[i], NATIVE[i]) for i in (1, 2, 3, 4, 5)]
        quote, tb, tq = [number(row[i], NATIVE[i]) for i in (7, 9, 10)]
        trades = integer(row[8], "trade_count")
        require(0 < lo <= op <= hi and lo <= cl <= hi, f"OHLC: {context}")
        require(vol >= 0 and quote >= 0 and 0 <= tb <= vol and 0 <= tq <= quote, f"VOLUME_RANGE: {context}")
        # Source decimals are retained byte-for-field. One quoted precision unit is
        # allowed for source-side rounded quote totals; never alter source values.
        quote_unit = Decimal(1).scaleb(quote.as_tuple().exponent)
        taker_unit = Decimal(1).scaleb(tq.as_tuple().exponent)
        require(lo * vol - quote_unit <= quote <= hi * vol + quote_unit, f"QUOTE_VOLUME_BOUNDS: {context}")
        require(lo * tb - taker_unit <= tq <= hi * tb + taker_unit, f"TAKER_QUOTE_BOUNDS: {context}")
        max_quote_rounding_error = max(max_quote_rounding_error, lo * vol - quote, quote - hi * vol)
        require((vol == 0) == (trades == 0), f"VOLUME_TRADE_CONSISTENCY: {context}")
        if vol == 0:
            zero_volumes.append(opened)
        if trades == 0:
            zero_trades.append(opened)
        ignored_values.add(row[11])
    return rows, {"month": month, "rows": len(rows), "expected_rows": expected,
                  "duplicates": 0, "out_of_order": 0, "missing_grid_bars": 0,
                  "ohlc_errors": 0, "volume_errors": 0, "close_time_errors": 0,
                  "first_open_utc": iso_ms(int(rows[0][0])),
                  "last_close_utc": iso_ms(int(rows[-1][6])),
                  "zero_volume_open_times_ms": zero_volumes,
                  "zero_trade_open_times_ms": zero_trades,
                  "ignore_distinct_values": sorted(ignored_values),
                  "quote_rounding_excess_max": str(max_quote_rounding_error)}


def verify_archive(zip_bytes, checksum_bytes, filename):
    text = checksum_bytes.decode("ascii")
    match = re.fullmatch(r"([a-fA-F0-9]{64})[ \t]+\*?([^\r\n]+)\r?\n?", text)
    require(match is not None, f"CHECKSUM_FORMAT: {filename}")
    require(match[2] == filename, f"CHECKSUM_FILENAME: {filename}: {match[2]}")
    require(digest(zip_bytes) == match[1].lower(), f"MISMATCH: official ZIP checksum {filename}")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        entries = archive.infolist()
        expected_csv = filename.removesuffix(".zip") + ".csv"
        require(len(entries) == 1 and entries[0].filename == expected_csv, f"ZIP_MEMBERS: {filename}")
        entry = entries[0]
        require(not entry.is_dir() and not (entry.flag_bits & 1), f"ZIP_ENCRYPTED_OR_DIRECTORY: {filename}")
        require(entry.file_size <= MAX_CSV_BYTES, f"ZIP_EXPANSION_CAP: {filename}")
        require(archive.testzip() is None, f"ZIP_CRC: {filename}")
        body = archive.read(entry)
        require(len(body) == entry.file_size, f"ZIP_SIZE: {filename}")
    return body, {"official_sha256": match[1].lower(), "crc32": f"{entry.CRC:08x}",
                  "archive_member": entry.filename, "uncompressed_bytes": len(body),
                  "sha256": digest(body), "zip_internal_timestamp": list(entry.date_time)}


def serialize(rows, timeframe):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(NATIVE + ADDED)
    for row, source_archive in rows:
        writer.writerow(row + [iso_ms(int(row[0])), "binance", "spot", timeframe,
                               "BTC/USDT", "BTCUSDT", "binance_vision",
                               iso_ms(int(row[6])), source_archive])
    return output.getvalue().encode("utf-8")


def compare_expected(actual, expected):
    keys = ("protocol", "timeframe", "start_utc", "end_exclusive_utc", "builder_sha256", "schema")
    for key in keys:
        require(actual[key] == expected[key], f"MISMATCH: manifest {key}")
    for kind in ("zip", "checksum", "csv"):
        old = {x["month"]: (x[kind]["sha256"], x[kind]["bytes"]) for x in expected["archives"]}
        new = {x["month"]: (x[kind]["sha256"], x[kind]["bytes"]) for x in actual["archives"]}
        require(new == old, f"MISMATCH: {kind} archive inventory")
    for key in ("sha256", "bytes", "rows"):
        require(actual["canonical_csv"][key] == expected["canonical_csv"][key], f"MISMATCH: canonical_csv {key}")


def capture(args):
    require(args.terms_reviewed, "TERMS_NOT_REVIEWED: operator review/authorization required; no request sent")
    target = Path(args.target).resolve()
    stage = target.with_name(target.name + ".partial")
    require(not target.exists(), f"TARGET_EXISTS_REFUSED: {target}")
    require(not stage.exists(), f"STAGING_EXISTS_REFUSED: {stage}")
    expected = None
    if args.expected_manifest:
        expected = json.loads(Path(args.expected_manifest).read_text())
        require(expected["timeframe"] == args.timeframe, "MISMATCH: expected timeframe")
    target.parent.mkdir(parents=True, exist_ok=True)
    disk_before = assert_disk(target.parent, 64 * 1024**2)
    stage.mkdir()
    started = now()
    try:
        all_rows, archives, audits = [], [], []
        for month in months():
            filename = f"BTCUSDT-{args.timeframe}-{month}.zip"
            url = f"{BASE}/{args.timeframe}/{filename}"
            folder = stage / "archives" / month
            folder.mkdir(parents=True)
            checksum, cmeta = fetch(url + ".CHECKSUM", folder / (filename + ".CHECKSUM"))
            zipped, zmeta = fetch(url, folder / filename)
            raw_csv, xmeta = verify_archive(zipped, checksum, filename)
            csv_path = folder / xmeta["archive_member"]
            write_new(csv_path, raw_csv)
            xmeta.update({"path": str(csv_path.relative_to(stage)), "bytes": len(raw_csv),
                          "extracted_at_utc": now(), "source_fetched_at_utc": zmeta["fetch_completed_at_utc"]})
            zmeta["path"] = str((folder / filename).relative_to(stage))
            cmeta["path"] = str((folder / (filename + ".CHECKSUM")).relative_to(stage))
            rows, audit = audit_csv(raw_csv, args.timeframe, month)
            all_rows.extend((row, filename) for row in rows)
            archives.append({"month": month, "zip": zmeta, "checksum": cmeta, "csv": xmeta})
            audits.append(audit)
            print(f"VERIFIED_ARCHIVE {args.timeframe} {month} rows={len(rows)}", flush=True)
        interval = INTERVALS[args.timeframe]
        expected_rows = (ms(END) - ms(START)) // interval
        require(len(all_rows) == expected_rows, "COVERAGE: total rows")
        require(all(int(row[0]) == ms(START) + i * interval for i, (row, _) in enumerate(all_rows)), "GRID: cross-month")
        canonical = serialize(all_rows, args.timeframe)
        canonical_name = f"BTCUSDT-{args.timeframe}-202212-202412-native12.csv"
        write_new(stage / canonical_name, canonical)
        builder = Path(__file__).read_bytes()
        zero_count = sum(len(a["zero_volume_open_times_ms"]) for a in audits)
        manifest = {
            "protocol": VERSION, "timeframe": args.timeframe,
            "dataset_id": f"binance.spot.BTCUSDT.{args.timeframe}.vision_monthly.202212_202412.diagnostic.v1",
            "layer": "raw", "registered_status": "UNACCEPTED", "scope": "EXPLICIT_DIAGNOSTIC",
            "profile": "NATIVE12_CANONICAL_DIAGNOSTIC_V1", "quality_status": "DIAGNOSTIC_ONLY",
            "trusted": False, "is_closed_authoritative": False,
            "start_utc": "2022-12-01T00:00:00Z", "end_exclusive_utc": "2025-01-01T00:00:00Z",
            "cutoff_exclusive_utc": "2025-01-01T00:00:00Z", "timestamp_unit": "milliseconds",
            "calendar_policy": "continuous_24_7", "timezone": "UTC",
            "identity": {"exchange": "binance", "market_type": "spot", "symbol": "BTC/USDT", "native_symbol": "BTCUSDT", "source": "binance_vision"},
            "schema": NATIVE + ADDED, "builder_sha256": digest(builder),
            "capture_started_at_utc": started, "capture_completed_at_utc": now(),
            "canonical_csv": {"path": canonical_name, "bytes": len(canonical), "sha256": digest(canonical), "rows": len(all_rows), "generated_at_utc": now()},
            "archives": archives, "monthly_audits": audits,
            "row_quality": "PASS" if zero_count == 0 else "PASS_WITH_NATIVE_ZERO_VOLUME",
            "zero_volume_rows": zero_count, "reject_gap_policy_eligible": zero_count == 0,
            "integrity": {"official_checksums": "PASS", "zip_crc": "PASS", "utc_open_close_grid": "PASS", "all_native_fields_preserved": "PASS", "sorting_dedup_fill_performed": False},
            "closure_evidence": {"monthly_archive_full_calendar_grid": "PASS", "native_close_times_end_at_interval_minus_1ms": "PASS", "official_archive_schedule": README_URL, "native_final_flag": "ABSENT", "newer_current_bucket": "NOT_CHECKED", "stable_full_recapture": "NOT_CHECKED_IN_THIS_CAPTURE", "strict_core_finality": "NOT_ESTABLISHED"},
            "licensing": {"status": "REVIEW_REQUIRED_FOR_EACH_USE", "terms_url": TERMS_URL, "terms_sha256": TERMS_SHA256, "dataset_license": "CC-BY-NC-SA-4.0 plus Binance Vision Dataset Terms", "operator_review_flag": True, "commercial_or_live_use_authorized": False, "raw_redistribution_performed": False},
            "field_documentation": [README_URL, FIELD_DOC_URL],
            "limitations": ["Not registered/trusted lake ingestion; explicit bounded handoff diagnostic capture only.", "No native is_closed flag; do not invent it from timestamp or archive location.", "Archived records can be revised; current checksum agreement is not historical point-in-time evidence.", "BTCUSDT was predeclared for this diagnostic; no author-selected or survivorship-free universe claim.", "No historical instrument/tradability/PIT attestation or original release-time snapshots.", "No VWAP is fabricated. All original native field strings retained.", "No original trades/order book; intrabar path and executable liquidity are unknown.", "License restrictions also cover derivative charts/models and noncommercial ShareAlike redistribution."],
            "disk_free_bytes_before": disk_before, "disk_free_bytes_after": assert_disk(stage),
            "rebuild_status": "CAPTURED_NOT_INDEPENDENTLY_REBUILT",
        }
        if expected is not None:
            compare_expected(manifest, expected)
            manifest["rebuild_status"] = "VERIFIED_SAME_INPUT_AND_CANONICAL_HASHES"
            manifest["rebuild_against_manifest_sha256"] = digest(Path(args.expected_manifest).read_bytes())
        write_json(stage / "manifest.json", manifest)
        require(not target.exists(), f"TARGET_EXISTS_REFUSED: {target}")
        stage.rename(target)
        print(json.dumps({"status": manifest["rebuild_status"], "target": str(target), "canonical_csv": manifest["canonical_csv"], "manifest_sha256": digest((target / "manifest.json").read_bytes())}, indent=2), flush=True)
    except Exception as exc:
        receipt = {"status": "MISMATCH" if "MISMATCH" in str(exc) else "FAILED", "error_type": type(exc).__name__, "error": str(exc), "at_utc": now(), "target_not_published": str(target), "retained_partial_evidence": str(stage)}
        failure = stage / "failure.json"
        if not failure.exists():
            write_json(failure, receipt)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeframe", choices=sorted(INTERVALS), required=True)
    parser.add_argument("--target", required=True, help="New nonexistent immutable snapshot directory")
    parser.add_argument("--expected-manifest", help="Frozen prior manifest for genuine public-source rebuild")
    parser.add_argument("--terms-reviewed", action="store_true", help="Operator confirms applicable terms reviewed; does not grant legal approval or bypass any required user authorization")
    args = parser.parse_args()
    try:
        capture(args)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
