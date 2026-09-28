"""Read only the frozen existing-native receipt list; no network or lake scan."""
from __future__ import annotations

from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-long10"
BASE = FAMILY / "artifacts/baseline-estimate-20260909"
SOURCE_LIST = BASE / "funding-identity-corrected/existing-native-source-receipts-v2.json"
OUT = FAMILY / "artifacts/funding-recheck-20260910/marks"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def valid_mark(value):
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (ValueError, TypeError):
        return False


def checked(path, expected):
    if sha(path) != expected:
        raise ValueError(f"raw hash mismatch: {path}")


def compatible_type(source, model_source):
    return model_source not in {"Regular", "Special"} or source == model_source


def same_rate(left, right):
    return abs(float(left) - float(right)) <= 1e-12


def pick_match(event, exact, hours):
    timestamp = int(event.ts.timestamp() * 1000)
    exact_hits = [r for r in exact.get((event.symbol, timestamp), [])
                  if same_rate(r["native_rate"], event.funding_rate)
                  and compatible_type(r["native_rate_type"], event.source_rate_type)]
    if len(exact_hits) > 1:
        return None, "AMBIGUOUS_EXACT_TIME"
    if len(exact_hits) == 1:
        return exact_hits[0], "UNIQUE_EXACT_NATIVE_MS_RATE_TYPE"
    hour_hits = [r for r in hours.get((event.symbol, timestamp // 3600000), [])
                 if same_rate(r["native_rate"], event.funding_rate)
                 and compatible_type(r["native_rate_type"], event.source_rate_type)
                 and abs(r["native_ms"] - timestamp) <= 2000
                 and r["complete_request_hour"]]
    if len(hour_hits) > 1:
        return None, "AMBIGUOUS_COMPLETE_HOUR"
    if len(hour_hits) == 1:
        return hour_hits[0], "UNIQUE_COMPLETE_REQUEST_HOUR_RATE_TYPE_WITHIN_2S"
    return None, "NO_RETAINED_MATCH"


def run():
    summary_path = OUT / "native-retained-summary.json"
    if summary_path.exists():
        raise FileExistsError(summary_path)
    started = json.loads((BASE / "accounts/started.json").read_text())
    event_path = ROOT / started["paths"]["funding"]
    checked(event_path, started["sha256"]["funding"])
    events = pd.read_parquet(event_path)
    source_list_hash = sha(SOURCE_LIST)
    source_list = json.loads(SOURCE_LIST.read_text())
    all_rows = defaultdict(list)
    source_audit = []
    for receipt in source_list:
        path = ROOT / receipt["path"]
        checked(path, receipt["sha256"])
        body = path.read_bytes()
        zipped = path.suffix == ".gz"
        if zipped:
            body = gzip.decompress(body)
        raw_hash = hashlib.sha256(body).hexdigest()
        if raw_hash != receipt.get("raw_sha256", receipt["sha256"]):
            raise ValueError("decoded raw hash mismatch")
        metadata_path = path.with_suffix(".meta.json") if zipped else Path(str(path).replace("-raw-response.bin", "-receipt.json"))
        metadata = json.loads(metadata_path.read_text())
        parsed_url = urlparse(metadata["url"])
        if parsed_url.hostname != "fapi.binance.com" or parsed_url.path != "/fapi/v1/fundingRate":
            raise ValueError("not an official USD-M funding-rate API receipt")
        query = parse_qs(parsed_url.query)
        code = query.get("symbol", [None])[0]
        begin, end, limit = int(query["startTime"][0]), int(query["endTime"][0]), int(query["limit"][0])
        rows = json.loads(body)
        if not isinstance(rows, list):
            raise ValueError("funding raw is not a list")
        keys = set()
        metadata_hash = sha(metadata_path)
        for row in rows:
            timestamp = int(row["fundingTime"])
            native_type = row.get("rateType", "UNSPECIFIED_API")
            if (code is not None and row["symbol"] != code) or not begin <= timestamp <= end:
                raise ValueError("native record outside receipt request")
            key = (row["symbol"].removesuffix("USDT") + "/USDT:USDT", timestamp, native_type)
            if key in keys:
                raise ValueError("duplicate raw funding record")
            keys.add(key)
            hour = timestamp // 3600000 * 3600000
            all_rows[key].append({"symbol": key[0], "native_ms": timestamp,
                                  "native_rate": float(row["fundingRate"]), "native_rate_type": native_type,
                                  "native_mark": float(row["markPrice"]) if valid_mark(row.get("markPrice")) else None,
                                  "mark_field_present": "markPrice" in row,
                                  "source_path": receipt["path"], "source_file_sha256": receipt["sha256"],
                                  "source_raw_sha256": raw_hash, "source_metadata_path": str(metadata_path.relative_to(ROOT)),
                                  "source_metadata_sha256": metadata_hash,
                                  "complete_request_hour": len(rows) < limit and begin <= hour and end >= hour + 3599999,
                                  "source_url": metadata["url"]})
        source_audit.append({"path": receipt["path"], "sha256": receipt["sha256"], "raw_sha256": raw_hash,
                             "metadata_path": str(metadata_path.relative_to(ROOT)), "metadata_sha256": metadata_hash,
                             "rows": len(rows), "positive_native_marks": sum(valid_mark(r.get("markPrice")) for r in rows),
                             "list_under_limit": len(rows) < limit, "start_ms": begin, "end_ms": end, "symbol": code or "ALL_SYMBOLS_REQUEST"})
    exact, hours = defaultdict(list), defaultdict(list)
    conflicts = []
    for key, copies in all_rows.items():
        rates = {r["native_rate"] for r in copies}
        marks = {r["native_mark"] for r in copies if r["native_mark"] is not None}
        if len(rates) > 1 or len(marks) > 1:
            conflicts.append({"key": str(key), "rates": str(sorted(rates)), "marks": str(sorted(marks))})
            continue
        chosen = sorted(copies, key=lambda r: (r["native_mark"] is not None, r["complete_request_hour"]), reverse=True)[0].copy()
        chosen["complete_request_hour"] = any(r["complete_request_hour"] for r in copies)
        chosen["source_copies"] = len(copies)
        chosen["matching_source_references_json"] = json.dumps([{k: v for k, v in r.items() if k.startswith("source_")} for r in copies], ensure_ascii=False)
        exact[(key[0], key[1])].append(chosen)
        hours[(key[0], key[1] // 3600000)].append(chosen)
    mappings, unmatched, ambiguous = [], [], []
    for event in events.itertuples():
        hit, status = pick_match(event, exact, hours)
        if hit is None:
            item = {"event_id": event.event_id, "symbol": event.symbol, "ts": event.ts, "status": status}
            (ambiguous if status.startswith("AMBIGUOUS") else unmatched).append(item)
            continue
        native_ts = pd.Timestamp(hit["native_ms"], unit="ms", tz="UTC")
        if not event.holding_start < native_ts <= event.holding_end:
            raise ValueError("matched native time outside actual holding")
        mappings.append({"event_id": event.event_id, "original_event_id": event.event_id, "holding_window_id": event.holding_window_id,
                         "symbol": event.symbol, "original_ts": event.ts, "original_rate": event.funding_rate,
                         "original_source_rate_type": event.source_rate_type, "original_model_rate_type": event.rate_type,
                         "original_mark": event.mark_center, "original_mark_source": event.mark_source,
                         "native_ts": native_ts, "match_status": status,
                         "has_positive_native_mark": hit["native_mark"] is not None,
                         **{k: v for k, v in hit.items() if k != "symbol"}})
    matches = pd.DataFrame(mappings)
    positive = matches[matches.has_positive_native_mark].copy()
    positive["native_over_original_mark"] = positive.native_mark / positive.original_mark
    cash_path = BASE / "accounts/estimated_center/funding.parquet"
    account = json.loads((BASE / "accounts/summary.json").read_text())
    checked(cash_path, account["output_sha256"]["estimated_center/funding.parquet"])
    cash = pd.read_parquet(cash_path)
    positive = positive.merge(cash[["symbol", "ts", "rate_type", "quantity", "funding_cash"]],
                              left_on=["symbol", "original_ts", "original_model_rate_type"], right_on=["symbol", "ts", "rate_type"], validate="one_to_one")
    positive["native_cash_same_original_quantity"] = -positive.quantity * positive.native_mark * positive.native_rate
    positive["native_cash_minus_original"] = positive.native_cash_same_original_quantity - positive.funding_cash
    new = positive.original_mark_source.ne("HASH_VERIFIED_NATIVE_FUNDING_API_MARK")
    summary = {"status": "RETAINED_NATIVE_SOURCE_MAPPING_NOT_CALENDAR_PROOF", "script_sha256": sha(Path(__file__)),
               "source_list_path": str(SOURCE_LIST.relative_to(ROOT)), "source_list_sha256": source_list_hash,
               "event_path": str(event_path.relative_to(ROOT)), "event_sha256": sha(event_path),
               "receipt_files": len(source_list), "all_raw_rows": sum(r["rows"] for r in source_audit),
               "unique_raw_event_keys": len(all_rows), "raw_conflicts": len(conflicts), "ambiguous_matches": len(ambiguous),
               "original_events": len(events), "matched_events": len(matches), "no_retained_match_events": len(unmatched),
               "matched_native_mark_missing": int((~matches.has_positive_native_mark).sum()),
               "positive_native_mark_events": len(positive), "new_positive_native_mark_events": int(new.sum()),
               "positive_native_mark_original_abs_cash_share": float(positive.funding_cash.abs().sum() / cash.funding_cash.abs().sum()),
               "same_quantity_native_minus_original_cash": float(positive.native_cash_minus_original.sum()),
               "max_abs_native_over_original_minus_one": float((positive.native_over_original_mark - 1).abs().max()),
               "positive_native_counts_by_symbol": positive.symbol.value_counts().to_dict(),
               "match_status_counts": matches.match_status.value_counts().to_dict(),
               "mu_positive_native_events": int(positive.symbol.eq("MU/USDT:USDT").sum()),
               "no_network": True, "no_lake_directory_scan": True,
               "full_calendar_or_live_net_return_certified": False}
    outputs = {"native-retained-mappings.parquet": matches,
               "native-retained-positive-marks.parquet": positive,
               "native-retained-source-audit.csv": pd.DataFrame(source_audit),
               "native-retained-conflicts.csv": pd.DataFrame(conflicts),
               "native-retained-ambiguous.csv": pd.DataFrame(ambiguous)}
    for name, frame in outputs.items():
        path = OUT / name
        if path.exists():
            raise FileExistsError(path)
        if path.suffix == ".parquet":
            frame.to_parquet(path, index=False)
        else:
            frame.to_csv(path, index=False)
    if sha(SOURCE_LIST) != source_list_hash:
        raise ValueError("source list changed while auditing")
    summary["output_sha256"] = {name: sha(OUT / name) for name in outputs}
    with summary_path.open("x") as stream:
        json.dump(summary, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return summary


if __name__ == "__main__":
    run()
