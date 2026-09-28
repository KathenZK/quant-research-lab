from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from strategy_lab.data import (
    DataLakeLayout,
    DatasetKind,
    DuckDBWarehouse,
    MarketType,
    audit_ohlcv_frame,
)
from strategy_lab.data.fs import atomic_write_path
from strategy_lab.data.normalize import normalize_dataset
from strategy_lab.data.settings import load_settings
from strategy_lab.data.store import write_dataframe


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/btc/1d-ma7-rsi6-lightgbm-trend"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"

API_ROOT = "https://fapi.binance.com"
USER_AGENT = "quant-research-lab-btc-1d-ma7-rsi6-lgbm/0.1"
SOURCE = "binance_futures_kline_api_direct"
SYMBOL = "BTCUSDT"
DISPLAY_SYMBOL = "BTC/USDT:USDT"
TIMEFRAME = "1d"
DAY_MS = 86_400_000
RAW_COLUMNS = [
    "open_time_ms",
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time_ms",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
    "exchange",
    "symbol",
    "market_type",
    "timeframe",
    "is_closed",
    "source",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download, normalize, and audit all closed Binance USD-M BTCUSDT "
            "perpetual daily candles."
        )
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Fetch and audit without writing the data lake or artifact.",
    )
    return parser.parse_args()


def request_json(
    path: str,
    *,
    params: dict[str, object] | None = None,
    timeout: float,
    attempts: int = 6,
) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    url = f"{API_ROOT}{path}{query}"
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {418, 429, 500, 502, 503, 504}:
                raise
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(12.0, 0.75 * 2**attempt))
    raise RuntimeError(
        f"Binance request failed after {attempts} attempts: {url}"
    ) from last_error


def fetch_contract(timeout: float) -> dict[str, Any]:
    payload = request_json("/fapi/v1/exchangeInfo", timeout=timeout)
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Binance exchangeInfo payload")
    matches = [row for row in payload.get("symbols", []) if row.get("symbol") == SYMBOL]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one {SYMBOL} exchangeInfo row, got {len(matches)}"
        )
    row = matches[0]
    return {
        "symbol": SYMBOL,
        "status": row.get("status"),
        "contract_type": row.get("contractType"),
        "onboard_date_ms": int(row["onboardDate"]),
        "onboard_date": pd.to_datetime(
            row["onboardDate"], unit="ms", utc=True
        ).isoformat(),
        "base_asset": row.get("baseAsset"),
        "quote_asset": row.get("quoteAsset"),
        "margin_asset": row.get("marginAsset"),
        "underlying_type": row.get("underlyingType"),
    }


def fetch_server_time_ms(timeout: float) -> int:
    payload = request_json("/fapi/v1/time", timeout=timeout)
    if not isinstance(payload, dict) or "serverTime" not in payload:
        raise RuntimeError(f"Unexpected Binance server time payload: {payload!r}")
    return int(payload["serverTime"])


def fetch_klines(
    *,
    start_ms: int,
    cutoff_ms: int,
    timeout: float,
) -> pd.DataFrame:
    rows: list[list[Any]] = []
    cursor = start_ms
    while cursor < cutoff_ms:
        payload = request_json(
            "/fapi/v1/klines",
            params={
                "symbol": SYMBOL,
                "interval": TIMEFRAME,
                "startTime": cursor,
                "endTime": cutoff_ms,
                "limit": 1500,
            },
            timeout=timeout,
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected Binance kline payload: {payload!r}")
        if not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1][0]) + DAY_MS
        if next_cursor <= cursor:
            raise RuntimeError("BTCUSDT daily kline pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1500:
            break
        time.sleep(0.05)
    if not rows:
        raise RuntimeError("Binance returned no BTCUSDT daily klines")

    columns = [
        "open_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time_ms",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
        "ignore",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    frame["open_time"] = pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time_ms"], unit="ms", utc=True)
    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame["trade_count"] = frame["trade_count"].astype("int64")
    frame["exchange"] = "binance"
    frame["symbol"] = DISPLAY_SYMBOL
    frame["market_type"] = "perp"
    frame["timeframe"] = TIMEFRAME
    frame["is_closed"] = frame["close_time_ms"].lt(cutoff_ms)
    frame["source"] = SOURCE
    return (
        frame.loc[frame["is_closed"]]
        .drop_duplicates("open_time_ms", keep="last")
        .sort_values("open_time_ms")
        .reset_index(drop=True)[RAW_COLUMNS]
    )


def normalize_complete_utc_days(
    raw: pd.DataFrame,
    *,
    generated_at: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    duration_ms = raw["close_time_ms"] - raw["open_time_ms"] + 1
    utc_aligned = (
        raw["open_time"].dt.hour.eq(0)
        & raw["open_time"].dt.minute.eq(0)
        & raw["open_time"].dt.second.eq(0)
        & raw["open_time"].dt.microsecond.eq(0)
    )
    full_duration = duration_ms.eq(DAY_MS)
    accepted = raw.loc[utc_aligned & full_duration].copy()
    if accepted.empty:
        raise RuntimeError(
            "No complete UTC daily BTCUSDT candles remained after filtering"
        )

    volume_positive = accepted["volume"].gt(0)
    vwap = np.where(
        volume_positive,
        accepted["quote_volume"] / accepted["volume"],
        accepted["close"],
    )
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    provenance = {
        "mode": "explicit_opt_in",
        "fields": {
            "vwap": {
                "formula_version": "binance-kline-vwap-v1",
                "formula": "quote_volume / volume",
                "source_columns": ["quote_volume", "volume", "close"],
                "source_dataset": "Binance FAPI /fapi/v1/klines BTCUSDT 1d",
                "generated_at_utc": generated_at,
                "null_policy": "no nulls allowed",
                "fill_policy": "when volume == 0, use close",
                "script_sha256": script_hash,
            }
        },
    }
    normalized = pd.DataFrame(
        {
            "ts": accepted["open_time"],
            "exchange": "binance",
            "symbol": DISPLAY_SYMBOL,
            "market_type": "perp",
            "timeframe": TIMEFRAME,
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "open": accepted["open"],
            "high": accepted["high"],
            "low": accepted["low"],
            "close": accepted["close"],
            "volume": accepted["volume"],
            "quote_volume": accepted["quote_volume"],
            "trade_count": accepted["trade_count"],
            "vwap": vwap,
            "is_closed": accepted["is_closed"].astype(bool),
            "source": SOURCE,
            "derivation_provenance": json.dumps(
                provenance, ensure_ascii=False, sort_keys=True
            ),
            "quality_flags": np.where(
                volume_positive,
                "derived_vwap_quote_volume_over_volume",
                "derived_vwap_close_fill_zero_volume",
            ),
        }
    )
    normalized = normalize_dataset(DatasetKind.OHLCV, normalized)
    exclusions = {
        "closed_rows_downloaded": int(len(raw)),
        "excluded_non_utc_aligned": int((~utc_aligned).sum()),
        "excluded_non_full_duration": int((~full_duration).sum()),
        "accepted_complete_utc_days": int(len(normalized)),
    }
    return normalized, exclusions


def frame_sha256(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    timestamps = (
        pd.to_datetime(frame["ts"], utc=True)
        .to_numpy(dtype="datetime64[ns]")
        .astype("int64")
    )
    digest.update(np.ascontiguousarray(timestamps, dtype="int64").tobytes())
    float_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "vwap",
    ]
    for column in float_columns:
        values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype="float64")
        digest.update(np.ascontiguousarray(values, dtype="float64").tobytes())
    trade_count = pd.to_numeric(frame["trade_count"], errors="raise").to_numpy(
        dtype="int64"
    )
    digest.update(np.ascontiguousarray(trade_count, dtype="int64").tobytes())
    is_closed = frame["is_closed"].astype(bool).to_numpy(dtype="uint8")
    digest.update(np.ascontiguousarray(is_closed, dtype="uint8").tobytes())
    digest.update("\0".join(frame["source"].astype(str)).encode("utf-8"))
    return digest.hexdigest()


def audit_data(
    raw: pd.DataFrame,
    normalized: pd.DataFrame,
    exclusions: dict[str, Any],
) -> dict[str, Any]:
    report = audit_ohlcv_frame(normalized, expected_timeframe=TIMEFRAME)
    accepted_raw = raw.loc[raw["open_time"].isin(normalized["ts"])].copy()
    merged = accepted_raw.merge(
        normalized,
        left_on="open_time",
        right_on="ts",
        how="outer",
        suffixes=("_raw", "_normalized"),
        indicator=True,
    )
    compare_fields = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
    ]
    mismatches: dict[str, int] = {}
    both = merged["_merge"].eq("both")
    for column in compare_fields:
        mismatches[column] = int(
            (
                ~np.isclose(
                    merged.loc[both, f"{column}_raw"].to_numpy(dtype="float64"),
                    merged.loc[both, f"{column}_normalized"].to_numpy(dtype="float64"),
                    rtol=0.0,
                    atol=0.0,
                )
            ).sum()
        )
    blockers = (
        (not report.trusted)
        or int(merged["_merge"].eq("left_only").sum()) > 0
        or int(merged["_merge"].eq("right_only").sum()) > 0
        or any(mismatches.values())
    )
    result = {
        "normalized_audit": report.to_dict(),
        "raw_closed_rows": int(len(raw)),
        "accepted_raw_rows": int(len(accepted_raw)),
        "raw_normalized_join": {
            str(key): int(value)
            for key, value in merged["_merge"].value_counts().sort_index().items()
        },
        "raw_normalized_field_mismatches": mismatches,
        "exclusions": exclusions,
        "normalized_sha256": frame_sha256(normalized),
        "blocker_count": int(bool(blockers)),
    }
    if blockers:
        raise RuntimeError(f"BTCUSDT daily data-quality blockers found: {result}")
    return result


def validation_split(normalized: pd.DataFrame) -> dict[str, Any]:
    first_ts = pd.Timestamp(normalized["ts"].iloc[0])
    last_ts = pd.Timestamp(normalized["ts"].iloc[-1])
    validation_end_exclusive = last_ts + pd.Timedelta(days=1)
    validation_start = validation_end_exclusive - pd.DateOffset(years=1)
    train = normalized.loc[normalized["ts"].lt(validation_start)]
    validation = normalized.loc[normalized["ts"].ge(validation_start)]
    if train.empty or validation.empty:
        raise RuntimeError(
            "Full history is too short for a one-calendar-year validation holdout"
        )
    return {
        "policy": "latest_complete_calendar_year_of_bars",
        "frozen": True,
        "selection_allowed": False,
        "dataset_start": first_ts.isoformat(),
        "dataset_end_inclusive": last_ts.isoformat(),
        "development_start": pd.Timestamp(train["ts"].iloc[0]).isoformat(),
        "development_end_inclusive": pd.Timestamp(train["ts"].iloc[-1]).isoformat(),
        "development_rows": int(len(train)),
        "validation_start": pd.Timestamp(validation["ts"].iloc[0]).isoformat(),
        "validation_end_inclusive": pd.Timestamp(validation["ts"].iloc[-1]).isoformat(),
        "validation_rows": int(len(validation)),
    }


def write_partitions(
    raw: pd.DataFrame,
    normalized: pd.DataFrame,
    *,
    layout: DataLakeLayout,
) -> dict[str, Any]:
    raw_paths: list[Path] = []
    for partition_date, day in raw.groupby(raw["open_time"].dt.date, sort=True):
        path = layout.dataset_path(
            layer="raw",
            kind=DatasetKind.OHLCV,
            exchange="binance",
            market_type=MarketType.PERP,
            symbol=DISPLAY_SYMBOL,
            timeframe=TIMEFRAME,
            source=SOURCE,
            partition_date=partition_date,
        )
        written = atomic_write_path(
            path,
            lambda temp_path, frame=day.reset_index(drop=True): frame.to_parquet(
                temp_path, index=False
            ),
        )
        raw_paths.append(written)

    normalized_paths: list[Path] = []
    for partition_date, day in normalized.groupby(normalized["ts"].dt.date, sort=True):
        normalized_paths.append(
            write_dataframe(
                day.reset_index(drop=True),
                layout=layout,
                layer="normalized",
                kind=DatasetKind.OHLCV,
                exchange="binance",
                market_type=MarketType.PERP,
                symbol=DISPLAY_SYMBOL,
                timeframe=TIMEFRAME,
                partition_date=partition_date,
            )
        )
    return {
        "raw_partitions_written": len(raw_paths),
        "normalized_partitions_written": len(normalized_paths),
        "first_raw_path": str(raw_paths[0].relative_to(ROOT)),
        "last_raw_path": str(raw_paths[-1].relative_to(ROOT)),
        "first_normalized_path": str(normalized_paths[0].relative_to(ROOT)),
        "last_normalized_path": str(normalized_paths[-1].relative_to(ROOT)),
    }


def verify_consumer_view(
    normalized: pd.DataFrame,
    *,
    layout: DataLakeLayout,
) -> dict[str, Any]:
    loaded = DuckDBWarehouse(layout).load_trusted_ohlcv(
        exchange="binance",
        market_type=MarketType.PERP,
        symbol=DISPLAY_SYMBOL,
        timeframe=TIMEFRAME,
        source=SOURCE,
    )
    expected_hash = frame_sha256(normalized)
    actual_hash = frame_sha256(loaded)
    result = {
        "rows": int(len(loaded)),
        "first_ts": pd.Timestamp(loaded["ts"].iloc[0]).isoformat(),
        "last_ts": pd.Timestamp(loaded["ts"].iloc[-1]).isoformat(),
        "expected_sha256": expected_hash,
        "actual_sha256": actual_hash,
        "exact_hash_match": expected_hash == actual_hash,
        "audit": loaded.attrs["ohlcv_audit"],
        "source_counts": loaded.attrs["source_counts"],
    }
    if len(loaded) != len(normalized) or expected_hash != actual_hash:
        raise RuntimeError(
            f"Written BTCUSDT consumer view does not match fetch: {result}"
        )
    return result


def main() -> None:
    args = parse_args()
    generated_at = datetime.now(UTC).isoformat()
    contract = fetch_contract(args.timeout)
    if contract["status"] != "TRADING":
        raise RuntimeError(f"BTCUSDT contract is not trading: {contract}")
    if contract["contract_type"] != "PERPETUAL":
        raise RuntimeError(f"Unexpected BTCUSDT contract type: {contract}")
    cutoff_ms = fetch_server_time_ms(args.timeout)
    raw = fetch_klines(
        start_ms=int(contract["onboard_date_ms"]),
        cutoff_ms=cutoff_ms,
        timeout=args.timeout,
    )
    normalized, exclusions = normalize_complete_utc_days(
        raw,
        generated_at=generated_at,
    )
    quality = audit_data(raw, normalized, exclusions)
    split = validation_split(normalized)
    summary: dict[str, Any] = {
        "generated_at_utc": generated_at,
        "binance_server_time": pd.to_datetime(
            cutoff_ms, unit="ms", utc=True
        ).isoformat(),
        "market": "Binance USD-M Futures PERPETUAL",
        "symbol": SYMBOL,
        "display_symbol": DISPLAY_SYMBOL,
        "timeframe": TIMEFRAME,
        "source": SOURCE,
        "contract": contract,
        "quality": quality,
        "split": split,
        "write_enabled": not args.no_write,
    }
    if not args.no_write:
        layout = DataLakeLayout.from_settings(load_settings(None))
        layout.ensure_directories()
        summary["partitions"] = write_partitions(
            raw,
            normalized,
            layout=layout,
        )
        summary["consumer_view"] = verify_consumer_view(
            normalized,
            layout=layout,
        )
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        artifact = (
            ARTIFACT_DIR
            / f"btcusdt_perp_1d_data_quality_{datetime.now(UTC).date().isoformat()}.json"
        )
        summary["artifact"] = str(artifact.relative_to(ROOT))
        atomic_write_path(
            artifact,
            lambda temp_path: temp_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            ),
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
