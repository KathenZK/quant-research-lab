#!/usr/bin/env python3
"""Ingest the pinned Stooq GC.F snapshot as raw-unaccepted futures data."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/gold/1d-multi-speed-tsmom"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
RAW_ROOT = (
    ROOT
    / "data/raw/ohlcv/exchange=comex/market_type=futures/timeframe=1d"
    / "source=github_stooq_commodities_snapshot"
)

PINNED_COMMIT = "e4be293bde6a79cdf0d353bade1691d9717948d1"
DOWNLOAD_URL = (
    "https://raw.githubusercontent.com/raja-grewal/stooq-commodities/"
    f"{PINNED_COMMIT}/market_data/stooq_major.csv"
)
SOURCE_DATASET_ID = f"github:raja-grewal/stooq-commodities:{PINNED_COMMIT}:stooq_major.csv"
EXPECTED_CSV_SHA256 = (
    "17b7923a7792aa179afdedcdac8bd7482c0dc8f61bbbbc49f41ccfd3e201648c"
)
SOURCE = "github_stooq_commodities_snapshot"
EXCHANGE = "comex"
MARKET_TYPE = "futures"
SYMBOL = "GC.F"
SYMBOL_FILE = "symbol=gc_f.parquet"
TIMEFRAME = "1d"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-date", default=datetime.now(UTC).date().isoformat())
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    return parser.parse_args()


def digest_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def fetch_bytes(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            request = Request(
                url,
                headers={"User-Agent": "quant-research-lab-research/1.0"},
            )
            with urlopen(request, timeout=60) as response:
                content = response.read()
            if content:
                return content
        except Exception as exc:  # pragma: no cover - network retry
            last_error = exc
        time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"download failed after retries: {last_error}")


def parse_snapshot(csv_bytes: bytes) -> tuple[pd.DataFrame, dict[str, Any]]:
    csv_hash = digest_bytes(csv_bytes)
    if csv_hash != EXPECTED_CSV_SHA256:
        raise RuntimeError(
            "pinned CSV drift: "
            f"expected {EXPECTED_CSV_SHA256}, got {csv_hash}"
        )
    source = pd.read_csv(BytesIO(csv_bytes), header=[0, 1], index_col=0)
    required = [(field, SYMBOL) for field in ("Open", "High", "Low", "Close", "Volume", "OpenInt")]
    missing = [str(item) for item in required if item not in source.columns]
    if missing:
        raise RuntimeError(f"source CSV missing columns: {missing}")

    frame = pd.DataFrame(
        {
            "open": pd.to_numeric(source[("Open", SYMBOL)], errors="coerce"),
            "high": pd.to_numeric(source[("High", SYMBOL)], errors="coerce"),
            "low": pd.to_numeric(source[("Low", SYMBOL)], errors="coerce"),
            "close": pd.to_numeric(source[("Close", SYMBOL)], errors="coerce"),
            "volume": pd.to_numeric(source[("Volume", SYMBOL)], errors="coerce"),
            "open_interest": pd.to_numeric(source[("OpenInt", SYMBOL)], errors="coerce"),
        }
    )
    frame.index.name = "session_date"
    frame = frame.reset_index()
    frame["session_date"] = frame["session_date"].astype("string")
    frame["ts"] = pd.to_datetime(
        frame["session_date"], format="%Y-%m-%d", utc=True, errors="raise"
    )
    provider_rows = int(len(frame))
    empty_price_mask = frame[["open", "high", "low", "close"]].isna().all(axis=1)
    empty_price_sessions = frame.loc[empty_price_mask, "session_date"].tolist()
    frame = frame.loc[~empty_price_mask].sort_values("ts").reset_index(drop=True)

    price_columns = ["open", "high", "low", "close"]
    price_nulls = {column: int(frame[column].isna().sum()) for column in price_columns}
    invalid_ohlc = int(
        (
            frame[price_columns].le(0.0).any(axis=1)
            | frame["high"].lt(frame[["open", "close", "low"]].max(axis=1))
            | frame["low"].gt(frame[["open", "close", "high"]].min(axis=1))
        ).sum()
    )
    duplicates = int(frame["ts"].duplicated().sum())
    monotonic = bool(frame["ts"].is_monotonic_increasing)
    mechanical_price_blockers = sum(price_nulls.values()) + invalid_ohlc + duplicates + int(not monotonic)
    if mechanical_price_blockers:
        raise RuntimeError(
            "price-series audit failed: "
            f"price_nulls={price_nulls}, invalid_ohlc={invalid_ohlc}, "
            f"duplicates={duplicates}, monotonic={monotonic}"
        )

    frame["exchange"] = EXCHANGE
    frame["symbol"] = SYMBOL
    frame["market_type"] = MARKET_TYPE
    frame["timeframe"] = TIMEFRAME
    frame["source"] = SOURCE
    frame["source_dataset_id"] = SOURCE_DATASET_ID
    frame["continuous_contract_identity"] = "Stooq GC.F Gold - COMEX continuous series"
    frame["roll_adjustment"] = "provider_method_unverified"
    frame["price_semantics"] = "provider_daily_ohlc_unverified_settlement_vs_trade"
    frame["ts_semantics"] = "provider_session_date_at_00:00_utc_placeholder"
    frame["quality_status"] = "raw_unaccepted"

    daily_return = frame["close"].pct_change()
    gaps = frame["ts"].diff().dt.days.dropna()
    audit = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "download_url": DOWNLOAD_URL,
        "source_dataset_id": SOURCE_DATASET_ID,
        "repository_license": "MIT",
        "underlying_stooq_redistribution_terms": "not independently verified",
        "pinned_commit": PINNED_COMMIT,
        "csv_sha256": csv_hash,
        "provider_rows": provider_rows,
        "all_null_price_rows_dropped": int(empty_price_mask.sum()),
        "all_null_price_sessions": empty_price_sessions,
        "rows": int(len(frame)),
        "first_session": str(frame["session_date"].iloc[0]),
        "last_session": str(frame["session_date"].iloc[-1]),
        "duplicate_ts": duplicates,
        "price_nulls": price_nulls,
        "volume_null_rows": int(frame["volume"].isna().sum()),
        "open_interest_null_rows": int(frame["open_interest"].isna().sum()),
        "invalid_ohlc_rows": invalid_ohlc,
        "timestamps_monotonic": monotonic,
        "max_calendar_gap_days": int(gaps.max()) if len(gaps) else 0,
        "zero_volume_rows": int(frame["volume"].eq(0.0).sum()),
        "daily_abs_return_over_10pct_rows": int(daily_return.abs().gt(0.10).sum()),
        "max_abs_daily_return": float(daily_return.abs().max()),
        "mechanical_price_blockers": mechanical_price_blockers,
        "quality_status": "raw_unaccepted",
        "accepted_for_strategy_evidence": False,
        "rejected_alternative": {
            "source_dataset_id": "kaggle:hamzasamiullah/gold-price-historical-data-2000-2026:v2",
            "inner_csv_sha256": "4508410f7ac20324ab2e6e00aec0c20fce6a44d1cc6b732dab862feb81907c1c",
            "rows": 6383,
            "invalid_ohlc_rows": 441,
            "decision": "REJECTED_AS_PRIMARY_NO_SILENT_REPAIR",
        },
        "acceptance_blockers": [
            "continuous contract roll mapping and price adjustment method are unavailable",
            "COMEX exchange-calendar continuity audit is not implemented",
            "daily bar close/settlement semantics are not provider-verifiable",
            "is_closed, trade_count and vwap provenance are unavailable",
            "seven retained price rows have missing volume",
            "snapshot ends in 2021 and is stale relative to the current date",
            "underlying Stooq data redistribution terms were not independently verified",
        ],
    }
    return frame, audit


def partition_path(session_date: str) -> Path:
    return RAW_ROOT / f"date={session_date}" / SYMBOL_FILE


def atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.stem}-",
        suffix=".parquet.tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        frame.to_parquet(temporary, index=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_partitions(frame: pd.DataFrame, *, force: bool) -> dict[str, Any]:
    written = 0
    verified_existing = 0
    for _, row in frame.iterrows():
        session_date = str(row["session_date"])
        path = partition_path(session_date)
        expected = pd.DataFrame([row.to_dict()])
        if path.exists() and not force:
            actual = pd.read_parquet(path)
            if len(actual) != 1 or str(actual.iloc[0]["session_date"]) != session_date:
                raise RuntimeError(f"existing raw partition mismatch: {path}")
            verified_existing += 1
            continue
        atomic_write_parquet(expected, path)
        written += 1
    return {
        "raw_root": RAW_ROOT.relative_to(ROOT).as_posix(),
        "partitions_total": int(len(frame)),
        "partitions_written": written,
        "partitions_verified_existing": verified_existing,
        "first_partition": partition_path(str(frame["session_date"].iloc[0])).relative_to(ROOT).as_posix(),
        "last_partition": partition_path(str(frame["session_date"].iloc[-1])).relative_to(ROOT).as_posix(),
    }


def atomic_write_json(path: Path, payload: dict[str, Any], *, force: bool) -> None:
    if path.exists() and not force:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("csv_sha256") == payload.get("csv_sha256"):
            return
        raise RuntimeError(f"artifact exists with different source; use --force: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode() + b"\n"
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.stem}-",
        suffix=".json.tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    csv_bytes = fetch_bytes(DOWNLOAD_URL)
    source_frame, audit = parse_snapshot(csv_bytes)
    existing = sorted(RAW_ROOT.glob(f"date=*/{SYMBOL_FILE}"))
    if existing and not args.refresh:
        frame = pd.concat([pd.read_parquet(path) for path in existing], ignore_index=True)
        frame = frame.sort_values("ts").reset_index(drop=True)
        if len(frame) != len(source_frame):
            raise RuntimeError(
                f"existing raw row count {len(frame)} != pinned source {len(source_frame)}"
            )
    else:
        frame = source_frame
    if args.audit_only:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return
    write_result = write_partitions(frame, force=args.force)
    payload = {**audit, **write_result}
    output = ARTIFACT_DIR / f"gold-1d-ms-tsmom-baseline-{args.run_date}-data-audit.json"
    atomic_write_json(output, payload, force=args.force)
    print(
        json.dumps(
            {
                "artifact": output.relative_to(ROOT).as_posix(),
                "rows": payload["rows"],
                "partitions_written": payload["partitions_written"],
                "quality_status": payload["quality_status"],
                "accepted_for_strategy_evidence": payload["accepted_for_strategy_evidence"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
