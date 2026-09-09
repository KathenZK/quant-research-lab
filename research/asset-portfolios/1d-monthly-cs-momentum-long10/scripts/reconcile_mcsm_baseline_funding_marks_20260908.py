"""只核对已冻结探针与官方月档；不抓取、不更改湖、不宣称净收益。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-long10"
OUT = FAMILY / "artifacts/baseline-verification-20260908/funding-evidence"
ARCHIVES = FAMILY / "artifacts/funding-source-20260908/source-evidence"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_new(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.write("\n")


def reconcile_one(symbol, index):
    prefix = f"{index:02d}-{symbol}USDT-2026-06-01"
    receipt_path = OUT / f"{prefix}-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    raw = ROOT / receipt["raw_path"]
    assert sha(raw) == receipt["raw_sha256"]
    api = pd.DataFrame(json.loads(raw.read_bytes()))
    assert api.symbol.eq(symbol + "USDT").all()
    api = api.rename(columns={"fundingTime": "calc_time", "fundingRate": "api_rate", "markPrice": "settlement_mark_price"})
    api.api_rate = pd.to_numeric(api.api_rate)
    api.settlement_mark_price = pd.to_numeric(api.settlement_mark_price)
    zip_path = ARCHIVES / f"{symbol}USDT-fundingRate-2026-06.zip"
    checksum = zip_path.with_suffix(".zip.CHECKSUM")
    assert sha(zip_path) == checksum.read_text().split()[0]
    with zipfile.ZipFile(zip_path) as container:
        assert container.testzip() is None
        assert len(container.namelist()) == 1
        with container.open(container.namelist()[0]) as stream:
            archive = pd.read_csv(stream)
    archive = archive.rename(columns={"last_funding_rate": "archive_rate"})
    merged = api.merge(archive, on="calc_time", how="outer", validate="one_to_one", indicator=True)
    merged["rate_error"] = merged.api_rate - merged.archive_rate
    assert merged._merge.eq("both").all()
    assert merged.rate_error.abs().le(1e-12).all()
    assert merged.settlement_mark_price.gt(0).all()
    merged["ts_utc"] = pd.to_datetime(merged.calc_time, unit="ms", utc=True)
    merged["event_cash_per_unit_long"] = -merged.settlement_mark_price * merged.api_rate
    merged["api_raw_sha256"] = sha(raw)
    merged["archive_zip_sha256"] = sha(zip_path)
    assert not (OUT / f"{symbol}-native-mark-archive-parity.csv").exists()
    merged.to_csv(OUT / f"{symbol}-native-mark-archive-parity.csv", index=False)
    # Monthly archive intervals are independent fields, but same-frequency adjacent
    # links do not prove transitions or window edges under the published v2 contract.
    ordered = merged.sort_values("calc_time")
    frequency = ordered.funding_interval_hours
    delta = ordered.calc_time.diff() / 3_600_000
    same = frequency.eq(frequency.shift())
    matched = same & delta.sub(frequency).abs().le(2 / 3600)
    return {"symbol": symbol + "USDT", "api_events": len(api), "archive_events": len(archive),
            "exact_timestamp_one_to_one": True, "maximum_rate_abs_error": float(merged.rate_error.abs().max()),
            "native_positive_mark_events": int(merged.settlement_mark_price.gt(0).sum()),
            "source_types": sorted(merged.rateType.unique()),
            "interval_counts": {str(k): int(v) for k, v in frequency.value_counts().items()},
            "frequency_changes": int(frequency.ne(frequency.shift()).sum() - 1),
            "same_frequency_adjacent_links_proven": int(matched.sum()),
            "window_calendar_proven": False,
            "whole_month_event_cash_usdt_for_one_token_long_not_strategy_return": float(merged.event_cash_per_unit_long.sum()),
            "api_receipt_sha256": sha(receipt_path), "archive_zip_sha256": sha(zip_path),
            "archive_checksum_sha256": sha(checksum)}


def normalized_inventory():
    roots = [ROOT / "data/normalized/funding_rates/exchange=binance/market_type=perp",
             ROOT / "data/normalized/funding/exchange=binance/market_type=perp"]
    output = []
    connection = duckdb.connect()
    try:
        for root in roots:
            files = sorted(root.rglob("*.parquet"))
            if not files:
                continue
            relation = connection.read_parquet([str(p) for p in files], hive_partitioning=False, union_by_name=True)
            relation.create_view("audit_inventory", replace=True)
            columns = set(relation.columns)
            if "mark_price" in columns:
                result = connection.sql("SELECT count(*) AS rows, count(mark_price) AS non_null_mark_rows, count(*) FILTER (WHERE isfinite(mark_price) AND mark_price > 0) AS finite_positive_mark_rows FROM audit_inventory").df().iloc[0].to_dict()
            elif "markPrice" in columns:
                result = connection.sql("SELECT count(*) AS rows, count(markPrice) AS non_null_mark_rows, count(*) FILTER (WHERE isfinite(try_cast(markPrice AS DOUBLE)) AND try_cast(markPrice AS DOUBLE)>0) AS finite_positive_mark_rows FROM audit_inventory").df().iloc[0].to_dict()
            else:
                result = {"rows": int(connection.sql("SELECT count(*) FROM audit_inventory").fetchone()[0]), "mark_field_absent": True}
            output.append({"root": str(root.relative_to(ROOT)), "files": len(files), "columns": sorted(columns),
                           "inventory_files_sha256": hashlib.sha256("\n".join(str(p.relative_to(ROOT)) for p in files).encode()).hexdigest(),
                           "purpose": "READ_ONLY_SOURCE_FIELD_AVAILABILITY_NOT_TRUSTED_RESEARCH_INPUT",
                           "result": {k: int(v) if not isinstance(v, bool) else v for k, v in result.items()}})
    finally:
        connection.close()
    return output


def tests():
    path = Path(__file__).with_name("probe_mcsm_baseline_funding_marks_20260908.py")
    spec = importlib.util.spec_from_file_location("probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for value in [None, "", "nan", "inf", "0", "-1"]:
        assert not module.valid_mark({"markPrice": value})
    assert module.valid_mark({"markPrice": "0.01"})
    assert module.ms("2020-03-01") == 1583020800000
    assert module.row_summary([])["finite_positive_mark_rows"] == 0
    return 9


def main():
    result = {"status": "FUNDING_MARK_SOURCE_PARTIALLY_RECOVERABLE_NOT_NET_VERIFIED",
              "reconciliation_script_sha256": sha(Path(__file__)), "assertion_checks": tests(),
              "official_documentation_url": "https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data",
              "june_anomaly_reconciliation": [reconcile_one(symbol, index) for index, symbol in enumerate(["HOME", "LAB", "H"], 1)],
              "normalized_source_inventory": normalized_inventory(),
              "scope_note": "API native mark values are independent evidence supplements, not registered dataset modifications or full historical coverage proof."}
    save_new(OUT / "native-mark-reconciliation-summary.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
