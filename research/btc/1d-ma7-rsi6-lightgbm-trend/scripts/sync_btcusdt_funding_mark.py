from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import time
from typing import Any
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from strategy_lab.data import DataLakeLayout, DatasetKind, DuckDBWarehouse, MarketType
from strategy_lab.data.fs import atomic_write_path
from strategy_lab.data.settings import load_settings


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/btc/1d-ma7-rsi6-lightgbm-trend"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"

API_ROOT = "https://fapi.binance.com"
USER_AGENT = "quant-research-lab-btc-funding-mark/0.1"
SYMBOL = "BTCUSDT"
DISPLAY_SYMBOL = "BTC/USDT:USDT"
INTERVAL = "8h"
INTERVAL_MS = 8 * 60 * 60 * 1000
MARK_SOURCE = "binance_mark_price"
FEATURE_DIR = ROOT / "data/features/btcusdt_funding_mark_v1"
FEATURE_PATH = FEATURE_DIR / "btcusdt_perp_funding_mark.parquet"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build an audited BTCUSDT funding-event dataset with official "
            "Binance mark-price fallback."
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


def server_time_ms(timeout: float) -> int:
    payload = request_json("/fapi/v1/time", timeout=timeout)
    if not isinstance(payload, dict) or "serverTime" not in payload:
        raise RuntimeError(f"Unexpected Binance server time payload: {payload!r}")
    return int(payload["serverTime"])


def load_funding() -> pd.DataFrame:
    layout = DataLakeLayout.from_settings(load_settings(None))
    frame = DuckDBWarehouse(layout).load_dataset(
        layer="normalized",
        kind=DatasetKind.FUNDING_RATES,
        exchange="binance",
        market_type=MarketType.PERP,
        symbol=DISPLAY_SYMBOL,
    )
    if frame.empty:
        raise RuntimeError("Canonical BTCUSDT funding history is empty")
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame["funding_rate"] = pd.to_numeric(frame["funding_rate"], errors="raise")
    frame["mark_price"] = pd.to_numeric(frame["mark_price"], errors="coerce")
    frame = (
        frame.sort_values("ts").drop_duplicates("ts", keep=False).reset_index(drop=True)
    )
    if frame["ts"].duplicated().any():
        raise RuntimeError(
            "Canonical BTCUSDT funding history contains duplicate timestamps"
        )
    return frame


def fetch_mark_klines(
    *,
    start_ms: int,
    cutoff_ms: int,
    timeout: float,
) -> pd.DataFrame:
    rows: list[list[Any]] = []
    cursor = start_ms
    while cursor < cutoff_ms:
        payload = request_json(
            "/fapi/v1/markPriceKlines",
            params={
                "symbol": SYMBOL,
                "interval": INTERVAL,
                "startTime": cursor,
                "endTime": cutoff_ms,
                "limit": 1500,
            },
            timeout=timeout,
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected Binance mark-price payload: {payload!r}")
        if not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1][0]) + INTERVAL_MS
        if next_cursor <= cursor:
            raise RuntimeError("BTCUSDT mark-price pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1500:
            break
        time.sleep(0.05)
    if not rows:
        raise RuntimeError("Binance returned no BTCUSDT mark-price klines")

    columns = [
        "open_time_ms",
        "open",
        "high",
        "low",
        "close",
        "ignore_volume",
        "close_time_ms",
        "ignore_quote_volume",
        "observation_count",
        "ignore_taker_base",
        "ignore_taker_quote",
        "ignore",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    frame["ts"] = pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True)
    frame["close_ts"] = pd.to_datetime(frame["close_time_ms"], unit="ms", utc=True)
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame["observation_count"] = pd.to_numeric(
        frame["observation_count"], errors="raise"
    ).astype("int64")
    frame["exchange"] = "binance"
    frame["market_type"] = "perp"
    frame["symbol"] = DISPLAY_SYMBOL
    frame["timeframe"] = INTERVAL
    frame["source"] = MARK_SOURCE
    frame["is_closed"] = frame["close_time_ms"].lt(cutoff_ms)
    return (
        frame.loc[frame["is_closed"]]
        .sort_values("ts")
        .drop_duplicates("ts", keep="last")
        .reset_index(drop=True)
    )


def audit_mark_klines(frame: pd.DataFrame) -> dict[str, Any]:
    timestamps = pd.DatetimeIndex(frame["ts"])
    expected = pd.date_range(timestamps.min(), timestamps.max(), freq=INTERVAL)
    missing = expected.difference(timestamps)
    invalid_ohlc = frame["high"].lt(
        frame[["open", "close", "low"]].max(axis=1)
    ) | frame["low"].gt(frame[["open", "close", "high"]].min(axis=1))
    blockers = (
        int(timestamps.duplicated().sum())
        + int(len(missing))
        + int(invalid_ohlc.sum())
        + int(frame[["open", "high", "low", "close"]].isna().sum().sum())
        + int((~frame["is_closed"]).sum())
    )
    result = {
        "rows": int(len(frame)),
        "start": timestamps.min().isoformat(),
        "end": timestamps.max().isoformat(),
        "expected_rows": int(len(expected)),
        "missing_bars": int(len(missing)),
        "duplicate_rows": int(timestamps.duplicated().sum()),
        "invalid_ohlc": int(invalid_ohlc.sum()),
        "not_closed": int((~frame["is_closed"]).sum()),
        "blocker_count": blockers,
    }
    if blockers:
        raise RuntimeError(f"BTCUSDT mark-price quality blockers found: {result}")
    return result


def build_resolved_funding(
    funding: pd.DataFrame,
    mark: pd.DataFrame,
    *,
    generated_at: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    funding_work = funding.copy()
    funding_work["funding_nominal_ts"] = funding_work["ts"].dt.floor(INTERVAL)
    funding_lag_seconds = (
        funding_work["ts"] - funding_work["funding_nominal_ts"]
    ).dt.total_seconds()
    invalid_lag = funding_lag_seconds.lt(0.0) | funding_lag_seconds.gt(1.0)
    if invalid_lag.any():
        raise RuntimeError(
            "BTCUSDT funding timestamps exceed the frozen one-second alignment "
            f"tolerance: {funding_work.loc[invalid_lag, 'ts'].head(10).tolist()}"
        )
    mark_open = mark[["ts", "open"]].rename(
        columns={
            "ts": "funding_nominal_ts",
            "open": "mark_kline_open",
        }
    )
    merged = funding_work.merge(
        mark_open,
        on="funding_nominal_ts",
        how="left",
        validate="one_to_one",
    )
    endpoint_mark = merged["mark_price"]
    fallback_mark = merged["mark_kline_open"]
    merged["resolved_mark_price"] = endpoint_mark.fillna(fallback_mark)
    merged["mark_price_source"] = np.where(
        endpoint_mark.notna(),
        "binance_funding_history_mark_price",
        np.where(
            fallback_mark.notna(),
            "binance_mark_price_kline_8h_open",
            "unresolved",
        ),
    )
    overlap = merged.loc[endpoint_mark.notna() & fallback_mark.notna()].copy()
    overlap_diff_bps = (
        overlap["mark_kline_open"] / overlap["mark_price"] - 1.0
    ).abs() * 10_000.0
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    merged["derivation_provenance"] = json.dumps(
        {
            "formula_version": "btcusdt-funding-mark-v1",
            "generated_at_utc": generated_at,
            "script_sha256": script_hash,
            "funding_source": sorted(
                str(value) for value in funding["source"].dropna().unique()
            ),
            "fallback_source": "Binance FAPI /fapi/v1/markPriceKlines 8h open",
            "join_key": (
                "funding timestamp floored to the nominal 8h bucket after "
                "verifying settlement lag is within one second"
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    output = merged[
        [
            "ts",
            "funding_nominal_ts",
            "exchange",
            "symbol",
            "market_type",
            "base_asset",
            "quote_asset",
            "funding_rate",
            "resolved_mark_price",
            "mark_price_source",
            "source",
            "derivation_provenance",
        ]
    ].rename(columns={"resolved_mark_price": "mark_price"})
    output = output.loc[output["mark_price"].notna()].reset_index(drop=True)
    quality = {
        "funding_rows": int(len(funding)),
        "funding_start": funding["ts"].min().isoformat(),
        "funding_end": funding["ts"].max().isoformat(),
        "funding_timestamp_lag_seconds": {
            "median": float(funding_lag_seconds.median()),
            "p95": float(funding_lag_seconds.quantile(0.95)),
            "max": float(funding_lag_seconds.max()),
        },
        "endpoint_mark_rows": int(endpoint_mark.notna().sum()),
        "fallback_mark_rows": int((endpoint_mark.isna() & fallback_mark.notna()).sum()),
        "unresolved_rows_excluded": int(
            (endpoint_mark.isna() & fallback_mark.isna()).sum()
        ),
        "resolved_rows": int(len(output)),
        "resolved_start": output["ts"].min().isoformat(),
        "resolved_end": output["ts"].max().isoformat(),
        "overlap_comparison_rows": int(len(overlap)),
        "overlap_mark_abs_diff_bps": {
            "median": float(overlap_diff_bps.median()) if len(overlap) else None,
            "p95": float(overlap_diff_bps.quantile(0.95)) if len(overlap) else None,
            "max": float(overlap_diff_bps.max()) if len(overlap) else None,
        },
        "critical_nulls": {
            column: int(output[column].isna().sum())
            for column in (
                "ts",
                "funding_nominal_ts",
                "funding_rate",
                "mark_price",
                "mark_price_source",
            )
        },
        "duplicate_ts": int(output["ts"].duplicated().sum()),
    }
    blockers = (
        sum(quality["critical_nulls"].values())
        + quality["duplicate_ts"]
        + int((output["mark_price"] <= 0.0).sum())
    )
    quality["blocker_count"] = int(blockers)
    if blockers:
        raise RuntimeError(
            f"Resolved BTCUSDT funding quality blockers found: {quality}"
        )
    return output, quality


def write_mark_raw(frame: pd.DataFrame, layout: DataLakeLayout) -> dict[str, Any]:
    paths: list[Path] = []
    for partition_date, day in frame.groupby(frame["ts"].dt.date, sort=True):
        path = layout.dataset_path(
            layer="raw",
            kind=DatasetKind.BASIS,
            exchange="binance",
            market_type=MarketType.PERP,
            symbol=DISPLAY_SYMBOL,
            timeframe=INTERVAL,
            source=MARK_SOURCE,
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
    cutoff_ms = server_time_ms(args.timeout)
    funding = load_funding()
    mark = fetch_mark_klines(
        start_ms=int(funding["ts"].min().timestamp() * 1000),
        cutoff_ms=cutoff_ms,
        timeout=args.timeout,
    )
    mark_quality = audit_mark_klines(mark)
    resolved, resolved_quality = build_resolved_funding(
        funding,
        mark,
        generated_at=generated_at,
    )
    summary: dict[str, Any] = {
        "generated_at_utc": generated_at,
        "binance_server_time": pd.to_datetime(
            cutoff_ms, unit="ms", utc=True
        ).isoformat(),
        "symbol": SYMBOL,
        "display_symbol": DISPLAY_SYMBOL,
        "mark_interval": INTERVAL,
        "mark_source": MARK_SOURCE,
        "mark_quality": mark_quality,
        "resolved_funding_quality": resolved_quality,
        "write_enabled": not args.no_write,
    }
    if not args.no_write:
        layout = DataLakeLayout.from_settings(load_settings(None))
        layout.ensure_directories()
        summary["raw_mark_write"] = write_mark_raw(mark, layout)
        FEATURE_DIR.mkdir(parents=True, exist_ok=True)
        atomic_write_path(
            FEATURE_PATH,
            lambda temp_path: resolved.to_parquet(temp_path, index=False),
        )
        summary["feature_path"] = str(FEATURE_PATH.relative_to(ROOT))
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        artifact = (
            ARTIFACT_DIR
            / f"btcusdt_funding_mark_quality_{datetime.now(UTC).date().isoformat()}.json"
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
