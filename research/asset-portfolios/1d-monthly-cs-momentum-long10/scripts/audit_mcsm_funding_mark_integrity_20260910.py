"""Independently parse retained official mark sources; never fetch or change inputs.

This is a scoped historical reproduction audit, not a trusted market-data loader.
Every consumed frozen account input is content-checked and every used mark raw
body is independently hashed and parsed. Minute proxies remain estimates.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
import zipfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-long10"
BASE = FAMILY / "artifacts/baseline-estimate-20260909"
DEFAULT_OUT = FAMILY / "artifacts/funding-recheck-20260910/marks"
DAILY = FAMILY / "artifacts/lifecycle-inputs-20260908/daily-returned-frames.parquet"
DAILY_SHA = "3565255edeafcdc5dd3083191b820d2302f993e4ac89679bd812e43601e7049a"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(path, expected):
    actual = sha(path)
    if actual != expected:
        raise ValueError(f"content mismatch: {path}")
    return actual


def equivalent(left, right):
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)


def parse_minute_source(body, zipped, needed, symbol, month):
    """stdlib CSV/JSON parser independent of the original pandas reader.

    Inspect every raw timestamp, but materialize only minutes actually used by
    this account. This does not create a second copy of the monthly sources.
    """
    archive = None
    if zipped:
        archive = zipfile.ZipFile(io.BytesIO(body))
        names = archive.namelist()
        expected = f"{symbol.split('/')[0]}USDT-1m-{month}.csv"
        if names != [expected]:
            raise ValueError(f"unexpected archive member: {names}")
        rows = csv.reader(io.TextIOWrapper(archive.open(names[0]), encoding="utf-8-sig"))
    else:
        rows = iter(json.loads(body))
    needed = set(map(int, needed))
    selected, prior, total, gaps = {}, None, 0, 0
    for row in rows:
        if row and str(row[0]) in {"open_time", "openTime"}:
            if total or prior is not None:
                raise ValueError("header inside raw data")
            continue
        if len(row) != 12:
            raise ValueError("raw mark record must have twelve fields")
        timestamp = int(row[0])
        if timestamp % 60000 or int(row[6]) != timestamp + 59999:
            raise ValueError("not an exact UTC millisecond minute")
        if timestamp < 1577836800000 or timestamp > 1893456000000:
            raise ValueError("raw timestamp is not 2020-2029 milliseconds")
        if prior is not None:
            if timestamp <= prior:
                raise ValueError("raw minute timestamp duplicate or out of order")
            gaps += timestamp - prior != 60000
        prior = timestamp
        total += 1
        if timestamp not in needed:
            continue
        opened, high, low, closed = map(float, row[1:5])
        if not all(math.isfinite(v) and v > 0 for v in [opened, high, low, closed]):
            raise ValueError("nonpositive/nonfinite used mark")
        if not low <= min(opened, closed) <= max(opened, closed) <= high:
            raise ValueError("invalid used mark OHLC")
        selected[timestamp] = (opened, high, low, closed)
    if archive is not None:
        archive.close()
    if needed != set(selected):
        raise ValueError(f"used minutes absent in raw: {sorted(needed - set(selected))[:10]}")
    return selected, {"raw_rows": total, "raw_internal_gaps": int(gaps), "used_minutes": len(selected)}


def validate_source_url(url, symbol, month, zipped):
    parsed = urlparse(url)
    code = symbol.split("/")[0] + "USDT"
    if zipped:
        expected = f"/data/futures/um/monthly/markPriceKlines/{code}/1m/{code}-1m-{month}.zip"
        if parsed.hostname != "data.binance.vision" or unquote(parsed.path) != expected:
            raise ValueError("mark ZIP is not the expected USD-M mark symbol/month")
    else:
        query = parse_qs(parsed.query)
        if parsed.hostname != "fapi.binance.com" or parsed.path != "/fapi/v1/markPriceKlines":
            raise ValueError("not an official USD-M mark API URL")
        if query.get("symbol") != [code] or query.get("interval") != ["1m"]:
            raise ValueError("mark API symbol or interval mismatch")


def collect_job_sources(fund_dir):
    sources = {}
    # Exactly the source directories pinned by this frozen estimate, not a lake scan.
    for directory in [BASE / "funding/jobs-v2", fund_dir / "jobs-v2"]:
        for path in sorted(directory.glob("*.json")):
            receipt = json.loads(path.read_text())
            source = receipt.get("source_receipt")
            if source and source.get("http_status") == 200:
                key = (source["raw_path"], source["raw_sha256"])
                sources.setdefault(key, []).append((path, receipt))
    return sources


def native_match(rows, event):
    timestamp = int(pd.Timestamp(event.ts).timestamp() * 1000)
    code = event.symbol.split("/")[0] + "USDT"
    hits = [r for r in rows if r.get("symbol") == code
            and int(r["fundingTime"]) == timestamp
            and equivalent(r["fundingRate"], event.funding_rate)
            and r.get("rateType", "UNSPECIFIED_API") == event.source_rate_type]
    if len(hits) != 1:
        raise ValueError(f"native settlement mark does not map uniquely: {code} {timestamp}")
    return float(hits[0]["markPrice"])


def run(output):
    if output.exists():
        raise FileExistsError(output)
    started_path = BASE / "accounts/started.json"
    started = json.loads(started_path.read_text())
    input_pins = {}
    for key in ["holdings", "funding", "funding_summary", "funding_plan"]:
        path = ROOT / started["paths"][key]
        input_pins[key] = {"path": str(path.relative_to(ROOT)), "sha256": checked(path, started["sha256"][key])}
    fund_path = ROOT / started["paths"]["funding"]
    events = pd.read_parquet(fund_path)
    windows = pd.read_parquet(ROOT / started["paths"]["holdings"]).reset_index(names="holding_window_id")
    if len(events) != 97421 or len(windows) != 760:
        raise ValueError("not the original fixed account scope")
    if events.duplicated(["symbol", "ts", "rate_type"]).any():
        raise ValueError("duplicate economic event")
    expected_ms = events.ts.map(lambda t: int(t.timestamp() * 1000) // 60000 * 60000)
    if not expected_ms.eq(events.minute_ms).all():
        raise ValueError("event UTC minute extraction mismatch")
    jobs = collect_job_sources(fund_path.parent)
    sources, errors = [], []
    for n, ((raw_path, expected_hash), group) in enumerate(events.groupby(["mark_raw_path", "mark_raw_sha256"], sort=True), 1):
        path = ROOT / raw_path
        checked(path, expected_hash)
        body = path.read_bytes()
        row = {"path": raw_path, "sha256": expected_hash, "events": len(group), "bytes": len(body)}
        if group.mark_source.eq("HASH_VERIFIED_NATIVE_FUNDING_API_MARK").all():
            raw = json.loads(body)
            for event in group.itertuples():
                mark = native_match(raw, event)
                if not all(equivalent(mark, value) for value in [event.mark_center, event.mark_low, event.mark_high]):
                    errors.append({"event_id": event.event_id, "field": "native_mark"})
            row.update(kind="native_funding_mark", raw_rows=len(raw))
        else:
            if group.symbol.nunique() != 1 or group.calendar_month.nunique() != 1:
                raise ValueError("minute raw file mixed symbols or months")
            symbol, month = group.symbol.iloc[0], group.calendar_month.iloc[0]
            candidates = jobs.get((raw_path, expected_hash), [])
            if not candidates:
                raise ValueError(f"missing source receipt: {raw_path}")
            receipt_path, receipt = candidates[-1]
            zipped = body.startswith(b"PK")
            validate_source_url(receipt["source_receipt"]["url"], symbol, month, zipped)
            row.update(receipt_path=str(receipt_path.relative_to(ROOT)), receipt_sha256=sha(receipt_path),
                       symbol=symbol, month=month, kind="official_mark_minute")
            if zipped:
                check = receipt["checksum_receipt"]
                checked(ROOT / check["raw_path"], check["raw_sha256"])
                if (ROOT / check["raw_path"]).read_text().split()[0] != expected_hash:
                    raise ValueError("Binance official checksum disagrees with raw body")
                row.update(official_checksum_verified=True)
            parsed, counts = parse_minute_source(body, zipped, group.minute_ms, symbol, month)
            row.update(counts)
            for event in group.itertuples():
                opened, high, low, closed = parsed[int(event.minute_ms)]
                for field, actual, expected in [("center", event.mark_center, opened), ("high", event.mark_high, high), ("low", event.mark_low, low)]:
                    if not equivalent(actual, expected):
                        errors.append({"event_id": event.event_id, "field": field, "actual": actual, "expected": expected})
        sources.append(row)
        if n % 100 == 0:
            print(f"independently parsed used raw sources: {n}", flush=True)
    checked(DAILY, DAILY_SHA)
    daily = pd.read_parquet(DAILY, columns=["ts", "symbol", "open", "high", "low", "close", "eligible"])
    cash_path = BASE / "accounts/estimated_center/funding.parquet"
    # Root account summary is authoritative for the output hash, not a self-hash.
    account_summary = json.loads((BASE / "accounts/summary.json").read_text())
    account_pins = account_summary["output_sha256"]
    checked(cash_path, account_pins["estimated_center/funding.parquet"])
    cash = pd.read_parquet(cash_path)
    all_rows = events.merge(cash[["symbol", "ts", "rate_type", "quantity", "funding_cash"]],
                            on=["symbol", "ts", "rate_type"], validate="one_to_one")
    all_rows = all_rows.merge(windows[["holding_window_id", "month", "entry_price"]],
                             on="holding_window_id", validate="many_to_one")
    all_rows["day"] = all_rows.ts.dt.floor("D")
    all_rows = all_rows.merge(daily.rename(columns={"ts": "day"}), on=["symbol", "day"], how="left", validate="many_to_one")
    if all_rows.low.isna().any():
        raise ValueError("missing frozen trade-day comparison")
    all_rows["mark_over_entry"] = all_rows.mark_center / all_rows.entry_price
    all_rows["mark_over_day_low"] = all_rows.mark_center / all_rows.low
    all_rows["mark_over_day_high"] = all_rows.mark_center / all_rows.high
    all_rows["quantity_times_mark"] = all_rows.quantity * all_rows.mark_center
    all_rows["quantity_times_entry"] = all_rows.quantity * all_rows.entry_price
    all_rows["outside_daily_envelope_2x"] = all_rows.mark_over_day_low.lt(.5) | all_rows.mark_over_day_high.gt(2)
    selected_cols = ["holding_window_id", "month", "symbol", "ts", "funding_rate", "source_rate_type", "mark_center", "quantity", "funding_cash", "quantity_times_mark", "quantity_times_entry", "mark_over_entry", "mark_over_day_low", "mark_over_day_high", "mark_source"]
    window_stats = all_rows.groupby(["holding_window_id", "month", "symbol"]).agg(
        events=("ts", "size"), funding_cash=("funding_cash", "sum"),
        native_events=("native_mark", "count"), mark_over_entry_min=("mark_over_entry", "min"),
        mark_over_entry_max=("mark_over_entry", "max"), mark_over_day_low_min=("mark_over_day_low", "min"),
        mark_over_day_high_max=("mark_over_day_high", "max"),
        maximum_mark_notional=("quantity_times_mark", "max"), entry_notional=("quantity_times_entry", "first"))
    top7 = window_stats.nlargest(7, "funding_cash")
    thousand = all_rows[all_rows.symbol.str.match(r"^\d+")]
    mu = all_rows[all_rows.symbol.eq("MU/USDT:USDT")]
    native = all_rows.mark_source.eq("HASH_VERIFIED_NATIVE_FUNDING_API_MARK")
    summary = {"status": "PASS_RAW_MARK_PARSING_NOT_REALIZED_NET_RETURN_CERTIFICATION" if not errors else "RAW_MARK_MISMATCH",
               "input_pins": input_pins, "started_sha256": sha(started_path), "script_sha256": sha(Path(__file__)),
               "daily_comparison_path": str(DAILY.relative_to(ROOT)), "daily_comparison_sha256": DAILY_SHA,
               "events": len(events), "unique_used_raw_files": len(sources), "source_field_mismatches": len(errors),
               "raw_bytes_read_once_per_unique_source": sum(s["bytes"] for s in sources),
               "raw_minute_rows_scanned": sum(s["raw_rows"] for s in sources if s["kind"] == "official_mark_minute"),
               "official_zip_checksums_verified": sum(s.get("official_checksum_verified", False) for s in sources),
               "source_counts": events.mark_source.value_counts().to_dict(),
               "native_mark_events": int(native.sum()), "native_mark_abs_cash_share": float(all_rows.loc[native, "funding_cash"].abs().sum() / all_rows.funding_cash.abs().sum()),
               "minute_proxy_events": int((~native).sum()), "mark_daily_price_envelope_2x_outliers": int(all_rows.outside_daily_envelope_2x.sum()),
               "daily_trade_envelope_comparison_is_not_exact_trade_or_mark_basis": True,
               "mark_over_day_low_min": float(all_rows.mark_over_day_low.min()), "mark_over_day_high_max": float(all_rows.mark_over_day_high.max()),
               "numeric_prefix_symbols": sorted(thousand.symbol.unique().tolist()), "numeric_prefix_events": len(thousand),
               "numeric_prefix_mark_daily_envelope_2x_outliers": int(thousand.outside_daily_envelope_2x.sum()),
               "mu_events": len(mu), "mu_source_rate_types": mu.source_rate_type.value_counts().to_dict(),
               "mu_modeled_rate_types": mu.rate_type.value_counts().to_dict(), "mu_funding_cash": float(mu.funding_cash.sum()),
               "frozen_snapshot_native_mark_count": int(events.mark_price.notna().sum()),
               "full_historical_identity_proven": False, "funding_calendar_complete_proven": False,
               "historical_liquidation_margin_capacity_and_actual_execution_proven": False,
               "scope": "All used original marks source-hashed and independently parsed; no missing event or native mark inferred as zero."}
    output.mkdir(parents=True)
    files = {"raw-source-audit.csv": pd.DataFrame(sources), "mark-field-mismatches.csv": pd.DataFrame(errors),
             "asset-month-mark-cash.csv": window_stats.reset_index(), "top7-asset-month-marks.csv": top7.reset_index(),
             "top7-largest-events.csv": all_rows[all_rows.holding_window_id.isin(top7.index.get_level_values(0))].nlargest(21, "funding_cash")[selected_cols],
             "daily-envelope-2x-outliers.csv": all_rows[all_rows.outside_daily_envelope_2x][selected_cols],
             "numeric-prefix-units.csv": window_stats.reset_index().loc[lambda x: x.symbol.isin(thousand.symbol.unique())],
             "mu-events.csv": mu[selected_cols]}
    for name, frame in files.items():
        frame.to_csv(output / name, index=False)
    summary["output_sha256"] = {name: sha(output / name) for name in files}
    with (output / "summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    run(parser.parse_args().output)
