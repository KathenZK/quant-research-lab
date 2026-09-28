from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
from http.client import IncompleteRead
import json
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from strategy_lab.data import DataLakeLayout, DatasetKind, MarketType, audit_ohlcv_frame
from strategy_lab.data.fs import atomic_write_path
from strategy_lab.data.normalize import normalize_dataset
from strategy_lab.data.settings import load_settings


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/btc/1d-ma7-rsi6-lightgbm-trend"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"

API_ROOT = "https://fapi.binance.com"
USER_AGENT = "quant-research-lab-btc-1h-stop-path/0.1"
SOURCE = "binance_futures_kline_api_direct"
SYMBOL = "BTCUSDT"
DISPLAY_SYMBOL = "BTC/USDT:USDT"
TIMEFRAME = "1h"
INTERVAL_MS = 60 * 60 * 1000
FEATURE_DIR = ROOT / "data/features/btcusdt_1h_stop_path_v1"
FEATURE_PATH = FEATURE_DIR / "btcusdt_perp_1h.parquet"
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
            "Download and audit complete Binance BTCUSDT perpetual 1h candles "
            "for daily-strategy stop-path resolution."
        )
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--no-write", action="store_true")
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
        except (
            URLError,
            TimeoutError,
            IncompleteRead,
            ConnectionError,
            json.JSONDecodeError,
        ) as exc:
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
    }


def server_time_ms(timeout: float) -> int:
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
        next_cursor = int(payload[-1][0]) + INTERVAL_MS
        if next_cursor <= cursor:
            raise RuntimeError("BTCUSDT 1h kline pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1500:
            break
        time.sleep(0.05)
    if not rows:
        raise RuntimeError("Binance returned no BTCUSDT 1h klines")

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
    for column in (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ):
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
        .sort_values("open_time_ms")
        .drop_duplicates("open_time_ms", keep="last")
        .reset_index(drop=True)[RAW_COLUMNS]
    )


def normalize_klines(
    raw: pd.DataFrame,
    *,
    generated_at: str,
) -> pd.DataFrame:
    duration_ms = raw["close_time_ms"] - raw["open_time_ms"] + 1
    aligned = (
        raw["open_time"].dt.minute.eq(0)
        & raw["open_time"].dt.second.eq(0)
        & raw["open_time"].dt.microsecond.eq(0)
        & duration_ms.eq(INTERVAL_MS)
    )
    accepted = raw.loc[aligned].copy()
    if len(accepted) != len(raw):
        raise RuntimeError(
            f"BTCUSDT 1h input contains {len(raw) - len(accepted)} non-complete bars"
        )
    volume_positive = accepted["volume"].gt(0.0)
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    provenance = json.dumps(
        {
            "mode": "explicit_opt_in",
            "fields": {
                "vwap": {
                    "formula_version": "binance-kline-vwap-v1",
                    "formula": "quote_volume / volume",
                    "source_columns": ["quote_volume", "volume", "close"],
                    "generated_at_utc": generated_at,
                    "script_sha256": script_hash,
                }
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )
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
            "vwap": np.where(
                volume_positive,
                accepted["quote_volume"] / accepted["volume"],
                accepted["close"],
            ),
            "is_closed": accepted["is_closed"].astype(bool),
            "source": SOURCE,
            "derivation_provenance": provenance,
            "quality_flags": np.where(
                volume_positive,
                "derived_vwap_quote_volume_over_volume",
                "derived_vwap_close_fill_zero_volume",
            ),
        }
    )
    return normalize_dataset(DatasetKind.OHLCV, normalized)


def frame_sha256(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    timestamps = (
        pd.to_datetime(frame["ts"], utc=True)
        .to_numpy(dtype="datetime64[ns]")
        .astype("int64")
    )
    digest.update(np.ascontiguousarray(timestamps, dtype="int64").tobytes())
    for column in (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "vwap",
    ):
        values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype="float64")
        digest.update(np.ascontiguousarray(values, dtype="float64").tobytes())
    counts = pd.to_numeric(frame["trade_count"], errors="raise").to_numpy(dtype="int64")
    digest.update(np.ascontiguousarray(counts, dtype="int64").tobytes())
    return digest.hexdigest()


def audit_data(
    raw: pd.DataFrame,
    normalized: pd.DataFrame,
) -> dict[str, Any]:
    report = audit_ohlcv_frame(normalized, expected_timeframe=TIMEFRAME)
    merged = raw.merge(
        normalized,
        left_on="open_time",
        right_on="ts",
        how="outer",
        suffixes=("_raw", "_normalized"),
        indicator=True,
    )
    both = merged["_merge"].eq("both")
    mismatches: dict[str, int] = {}
    for column in (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
    ):
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
        or int(merged["_merge"].ne("both").sum()) > 0
        or any(mismatches.values())
    )
    result = {
        "normalized_audit": report.to_dict(),
        "raw_rows": int(len(raw)),
        "normalized_rows": int(len(normalized)),
        "raw_normalized_join": {
            str(key): int(value)
            for key, value in merged["_merge"].value_counts().sort_index().items()
        },
        "field_mismatches": mismatches,
        "normalized_sha256": frame_sha256(normalized),
        "blocker_count": int(bool(blockers)),
    }
    if blockers:
        raise RuntimeError(f"BTCUSDT 1h data-quality blockers found: {result}")
    return result


def write_raw_partitions(
    raw: pd.DataFrame,
    layout: DataLakeLayout,
) -> dict[str, Any]:
    paths: list[Path] = []
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
        paths.append(
            atomic_write_path(
                path,
                lambda temp_path, part=day.reset_index(drop=True): part.to_parquet(
                    temp_path, index=False
                ),
            )
        )
    return {
        "partitions_written": len(paths),
        "first_path": str(paths[0].relative_to(ROOT)),
        "last_path": str(paths[-1].relative_to(ROOT)),
    }


def main() -> None:
    args = parse_args()
    generated_at = datetime.now(UTC).isoformat()
    contract = fetch_contract(args.timeout)
    if contract["status"] != "TRADING" or contract["contract_type"] != "PERPETUAL":
        raise RuntimeError(f"Unexpected BTCUSDT contract state: {contract}")
    cutoff_ms = server_time_ms(args.timeout)
    raw = fetch_klines(
        start_ms=int(contract["onboard_date_ms"]),
        cutoff_ms=cutoff_ms,
        timeout=args.timeout,
    )
    normalized = normalize_klines(raw, generated_at=generated_at)
    quality = audit_data(raw, normalized)
    summary: dict[str, Any] = {
        "generated_at_utc": generated_at,
        "binance_server_time": pd.to_datetime(
            cutoff_ms, unit="ms", utc=True
        ).isoformat(),
        "contract": contract,
        "symbol": SYMBOL,
        "display_symbol": DISPLAY_SYMBOL,
        "timeframe": TIMEFRAME,
        "source": SOURCE,
        "quality": quality,
        "write_enabled": not args.no_write,
    }
    if not args.no_write:
        layout = DataLakeLayout.from_settings(load_settings(None))
        layout.ensure_directories()
        summary["raw_write"] = write_raw_partitions(raw, layout)
        FEATURE_DIR.mkdir(parents=True, exist_ok=True)
        atomic_write_path(
            FEATURE_PATH,
            lambda temp_path: normalized.to_parquet(temp_path, index=False),
        )
        summary["feature_path"] = str(FEATURE_PATH.relative_to(ROOT))
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        artifact = (
            ARTIFACT_DIR
            / f"btcusdt_perp_1h_stop_path_quality_{datetime.now(UTC).date().isoformat()}.json"
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
