from __future__ import annotations

import argparse
from datetime import datetime, timezone
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


ROOT = Path(__file__).resolve().parents[3]
FAMILY_DIR = ROOT / "research/mu"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"

SYMBOL = "MUUSDT"
DISPLAY_SYMBOL = "MU/USDT:USDT"
SYMBOL_FILE = "symbol=mu_usdt_usdt.parquet"
TIMEFRAME = "15m"
INTERVAL_MS = 15 * 60 * 1000
BASE_URL = "https://fapi.binance.com"
USER_AGENT = "quant-research-lab-mu-15m/0.1"

RAW_OHLCV_ROOT = (
    ROOT / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
)
NORMALIZED_OHLCV_ROOT = (
    ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
)
RAW_FUNDING_ROOT = (
    ROOT / "data/raw/funding_rates/exchange=binance/market_type=perp"
)
NORMALIZED_FUNDING_ROOT = (
    ROOT / "data/normalized/funding_rates/exchange=binance/market_type=perp"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh and audit all closed Binance MUUSDT TRADIFI perpetual 15m "
            "candles and funding history."
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
    url = f"{BASE_URL}{path}{query}"
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(min(8.0, 0.75 * 2**attempt))
    raise RuntimeError(f"Binance request failed after {attempts} attempts: {url}") from last_error


def fetch_contract(timeout: float) -> dict[str, Any]:
    payload = request_json("/fapi/v1/exchangeInfo", timeout=timeout)
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Binance exchangeInfo payload")
    matches = [row for row in payload.get("symbols", []) if row.get("symbol") == SYMBOL]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {SYMBOL} exchangeInfo row, got {len(matches)}")
    row = matches[0]
    filters = {item["filterType"]: item for item in row.get("filters", [])}
    return {
        "symbol": SYMBOL,
        "status": row.get("status"),
        "contract_type": row.get("contractType"),
        "onboard_date_ms": int(row["onboardDate"]),
        "onboard_date": pd.to_datetime(
            row["onboardDate"], unit="ms", utc=True
        ).isoformat(),
        "underlying_type": row.get("underlyingType"),
        "underlying_sub_type": row.get("underlyingSubType"),
        "margin_asset": row.get("marginAsset"),
        "order_types": row.get("orderTypes"),
        "trigger_protect": row.get("triggerProtect"),
        "price_filter": filters.get("PRICE_FILTER"),
        "lot_size": filters.get("LOT_SIZE"),
        "market_lot_size": filters.get("MARKET_LOT_SIZE"),
        "min_notional": filters.get("MIN_NOTIONAL"),
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
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1][0]) + INTERVAL_MS
        if next_cursor <= cursor:
            raise RuntimeError("MUUSDT kline pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1500:
            break
        time.sleep(0.05)
    if not rows:
        raise RuntimeError("Binance returned no MUUSDT 15m klines")

    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
        "ignore",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "taker_buy_quote_volume",
    ]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    cutoff = pd.to_datetime(cutoff_ms, unit="ms", utc=True)
    onboard = pd.to_datetime(start_ms, unit="ms", utc=True)
    frame["source"] = "binance_futures_kline_api"
    frame["is_closed"] = frame["close_time"] < cutoff
    return (
        frame.loc[(frame["open_time"] >= onboard) & frame["is_closed"]]
        .drop_duplicates("open_time", keep="last")
        .sort_values("open_time")
        .reset_index(drop=True)
    )


def normalize_klines(raw: pd.DataFrame, generated_at: str) -> pd.DataFrame:
    frame = raw.rename(columns={"open_time": "ts"}).copy()
    frame["exchange"] = "binance"
    frame["symbol"] = DISPLAY_SYMBOL
    frame["market_type"] = "perp"
    frame["timeframe"] = TIMEFRAME
    frame["base_asset"] = "MU"
    frame["quote_asset"] = "USDT"
    frame["vwap"] = np.where(
        frame["volume"] > 0,
        frame["quote_volume"] / frame["volume"],
        frame["close"],
    )
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    provenance = {
        "mode": "explicit_opt_in",
        "fields": {
            "vwap": {
                "formula_version": "binance-kline-vwap-v1",
                "formula": "quote_volume / volume",
                "source_columns": ["quote_volume", "volume", "close"],
                "source_dataset": "Binance FAPI /fapi/v1/klines MUUSDT 15m",
                "generated_at_utc": generated_at,
                "null_policy": "no nulls allowed",
                "fill_policy": "when volume == 0, use close",
                "script_sha256": script_hash,
            }
        },
    }
    frame["derivation_provenance"] = json.dumps(
        provenance, ensure_ascii=False, sort_keys=True
    )
    frame["quality_flags"] = np.where(
        frame["volume"].eq(0),
        "derived_vwap_close_fill_zero_volume",
        "derived_vwap_quote_volume_over_volume",
    )
    return frame[
        [
            "ts",
            "exchange",
            "symbol",
            "market_type",
            "timeframe",
            "base_asset",
            "quote_asset",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "trade_count",
            "vwap",
            "is_closed",
            "source",
            "derivation_provenance",
            "quality_flags",
        ]
    ].reset_index(drop=True)


def fetch_funding(
    *,
    start_ms: int,
    cutoff_ms: int,
    timeout: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    cursor = start_ms
    while cursor <= cutoff_ms:
        payload = request_json(
            "/fapi/v1/fundingRate",
            params={
                "symbol": SYMBOL,
                "startTime": cursor,
                "endTime": cutoff_ms,
                "limit": 1000,
            },
            timeout=timeout,
        )
        if not isinstance(payload, list) or not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("MUUSDT funding pagination stopped advancing")
        cursor = next_cursor
        if len(payload) < 1000:
            break
        time.sleep(0.05)
    if not rows:
        raise RuntimeError("Binance returned no MUUSDT funding history")

    raw = pd.DataFrame(rows)
    raw["funding_time"] = pd.to_datetime(raw["fundingTime"], unit="ms", utc=True)
    raw["funding_rate"] = pd.to_numeric(raw["fundingRate"], errors="coerce")
    raw["mark_price"] = pd.to_numeric(raw["markPrice"], errors="coerce")
    raw["source"] = "binance_futures_funding_rate_api"
    raw = (
        raw.drop_duplicates("funding_time", keep="last")
        .sort_values("funding_time")
        .reset_index(drop=True)
    )

    normalized = pd.DataFrame(
        {
            "ts": raw["funding_time"],
            "exchange": "binance",
            "symbol": DISPLAY_SYMBOL,
            "market_type": "perp",
            "base_asset": "MU",
            "quote_asset": "USDT",
            "funding_rate": raw["funding_rate"],
            "mark_price": raw["mark_price"],
            "source": raw["source"],
        }
    )
    return raw, normalized


def audit_ohlcv(raw: pd.DataFrame, normalized: pd.DataFrame) -> dict[str, Any]:
    expected = pd.date_range(
        normalized["ts"].iloc[0],
        normalized["ts"].iloc[-1],
        freq="15min",
    )
    missing = expected.difference(pd.DatetimeIndex(normalized["ts"]))
    critical = [
        "ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "vwap",
        "source",
        "is_closed",
        "derivation_provenance",
    ]
    nulls = {column: int(normalized[column].isna().sum()) for column in critical}
    violations = {
        "high_lt_open_close": int(
            (normalized["high"] < normalized[["open", "close"]].max(axis=1)).sum()
        ),
        "low_gt_open_close": int(
            (normalized["low"] > normalized[["open", "close"]].min(axis=1)).sum()
        ),
        "high_lt_low": int((normalized["high"] < normalized["low"]).sum()),
        "nonpositive_ohlc": int(
            ((normalized[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum()
        ),
        "negative_volume": int((normalized["volume"] < 0).sum()),
        "negative_quote_volume": int((normalized["quote_volume"] < 0).sum()),
        "negative_trade_count": int((normalized["trade_count"] < 0).sum()),
        "vwap_outside_high_low": int(
            (
                (normalized["volume"] > 0)
                & (
                    (normalized["vwap"] < normalized["low"] * 0.999999)
                    | (normalized["vwap"] > normalized["high"] * 1.000001)
                )
            ).sum()
        ),
        "not_closed": int((~normalized["is_closed"]).sum()),
    }
    raw_sorted = raw.sort_values("open_time").reset_index(drop=True)
    mismatch: dict[str, int] = {}
    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
    ]:
        tolerance = 0.0 if column == "trade_count" else 1e-12
        mismatch[column] = int(
            (
                ~np.isclose(
                    raw_sorted[column].to_numpy(dtype="float64"),
                    normalized[column].to_numpy(dtype="float64"),
                    rtol=0.0,
                    atol=tolerance,
                )
            ).sum()
        )
    blocker_count = (
        int(raw.duplicated("open_time").sum())
        + int(normalized.duplicated("ts").sum())
        + len(missing)
        + sum(nulls.values())
        + sum(violations.values())
        + sum(mismatch.values())
    )
    result = {
        "rows": int(len(normalized)),
        "first_ts": normalized["ts"].iloc[0].isoformat(),
        "last_ts": normalized["ts"].iloc[-1].isoformat(),
        "expected_rows_between_endpoints": int(len(expected)),
        "missing_bars": int(len(missing)),
        "first_missing": missing[0].isoformat() if len(missing) else None,
        "duplicate_raw": int(raw.duplicated("open_time").sum()),
        "duplicate_normalized": int(normalized.duplicated("ts").sum()),
        "critical_nulls": nulls,
        "ohlcv_violations": violations,
        "raw_normalized_mismatch": mismatch,
        "zero_volume_bars": int(normalized["volume"].eq(0).sum()),
        "source_values": {
            str(key): int(value)
            for key, value in normalized["source"].value_counts().items()
        },
        "closed_values": {
            str(key): int(value)
            for key, value in normalized["is_closed"].value_counts().items()
        },
        "blocker_count": int(blocker_count),
    }
    if blocker_count:
        raise RuntimeError(f"MUUSDT OHLCV data-quality blockers found: {result}")
    return result


def audit_funding(
    raw: pd.DataFrame,
    normalized: pd.DataFrame,
) -> dict[str, Any]:
    gaps = normalized["ts"].diff().dropna()
    mismatch = int(
        (
            ~np.isclose(
                raw["funding_rate"].to_numpy(dtype="float64"),
                normalized["funding_rate"].to_numpy(dtype="float64"),
                rtol=0.0,
                atol=0.0,
            )
        ).sum()
    )
    blockers = (
        int(raw.duplicated("funding_time").sum())
        + int(normalized.duplicated("ts").sum())
        + int(normalized[["ts", "funding_rate", "source"]].isna().sum().sum())
        + mismatch
    )
    result = {
        "rows": int(len(normalized)),
        "first_ts": normalized["ts"].iloc[0].isoformat(),
        "last_ts": normalized["ts"].iloc[-1].isoformat(),
        "duplicate_raw": int(raw.duplicated("funding_time").sum()),
        "duplicate_normalized": int(normalized.duplicated("ts").sum()),
        "critical_nulls": {
            column: int(normalized[column].isna().sum())
            for column in ["ts", "funding_rate", "source"]
        },
        "raw_normalized_rate_mismatch": mismatch,
        "max_gap_hours": (
            float(gaps.max().total_seconds() / 3600.0) if len(gaps) else None
        ),
        "funding_interval_hours": (
            sorted(float(value) for value in (gaps.dt.total_seconds() / 3600).unique())
            if len(gaps)
            else []
        ),
        "zero_rate_rows": int(normalized["funding_rate"].eq(0).sum()),
        "sum_rate": float(normalized["funding_rate"].sum()),
        "blocker_count": int(blockers),
    }
    if blockers:
        raise RuntimeError(f"MUUSDT funding data-quality blockers found: {result}")
    return result


def write_daily(
    frame: pd.DataFrame,
    *,
    root: Path,
    ts_column: str,
) -> int:
    work = frame.copy()
    work["partition_date"] = pd.to_datetime(work[ts_column], utc=True).dt.date
    count = 0
    for partition_date, group in work.groupby("partition_date", sort=True):
        path = root / f"date={partition_date}" / SYMBOL_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        group.drop(columns="partition_date").to_parquet(path, index=False)
        count += 1
    return count


def audit_normalized_consumer_view() -> dict[str, Any]:
    files = sorted(NORMALIZED_OHLCV_ROOT.rglob(SYMBOL_FILE))
    if not files:
        raise RuntimeError("No normalized MUUSDT partitions found after write")
    frames: list[pd.DataFrame] = []
    partition_mismatch_rows = 0
    for path in files:
        frame = pd.read_parquet(
            path,
            columns=[
                "ts",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "quote_volume",
                "trade_count",
                "vwap",
                "is_closed",
                "source",
            ],
        )
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        expected_partition = path.parent.name.removeprefix("date=")
        partition_mismatch_rows += int(
            frame["ts"].dt.date.astype(str).ne(expected_partition).sum()
        )
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    duplicate_rows = int(combined.duplicated("ts", keep=False).sum())
    combined = combined.sort_values("ts").reset_index(drop=True)
    expected = pd.date_range(
        combined["ts"].iloc[0], combined["ts"].iloc[-1], freq="15min"
    )
    missing = expected.difference(pd.DatetimeIndex(combined["ts"]))
    blocker_count = partition_mismatch_rows + duplicate_rows + len(missing)
    result = {
        "files": len(files),
        "rows": int(len(combined)),
        "first_ts": combined["ts"].iloc[0].isoformat(),
        "last_ts": combined["ts"].iloc[-1].isoformat(),
        "partition_mismatch_rows": partition_mismatch_rows,
        "duplicate_rows": duplicate_rows,
        "missing_bars": int(len(missing)),
        "blocker_count": int(blocker_count),
    }
    if blocker_count:
        raise RuntimeError(f"MUUSDT normalized consumer-view blockers found: {result}")
    return result


def main() -> None:
    args = parse_args()
    generated_at = datetime.now(timezone.utc).isoformat()
    contract = fetch_contract(args.timeout)
    if contract["status"] != "TRADING":
        raise RuntimeError(f"MUUSDT contract is not trading: {contract}")
    if contract["contract_type"] != "TRADIFI_PERPETUAL":
        raise RuntimeError(f"Unexpected MUUSDT contract type: {contract}")
    if contract["underlying_type"] != "EQUITY":
        raise RuntimeError(f"Unexpected MUUSDT underlying type: {contract}")
    cutoff_ms = server_time_ms(args.timeout)
    raw_ohlcv = fetch_klines(
        start_ms=int(contract["onboard_date_ms"]),
        cutoff_ms=cutoff_ms,
        timeout=args.timeout,
    )
    normalized_ohlcv = normalize_klines(raw_ohlcv, generated_at)
    raw_funding, normalized_funding = fetch_funding(
        start_ms=int(contract["onboard_date_ms"]),
        cutoff_ms=cutoff_ms,
        timeout=args.timeout,
    )
    ohlcv_quality = audit_ohlcv(raw_ohlcv, normalized_ohlcv)
    funding_quality = audit_funding(raw_funding, normalized_funding)

    summary = {
        "generated_at_utc": generated_at,
        "binance_server_time": pd.to_datetime(
            cutoff_ms, unit="ms", utc=True
        ).isoformat(),
        "market": "Binance USD-M Futures TRADIFI_PERPETUAL",
        "symbol": SYMBOL,
        "display_symbol": DISPLAY_SYMBOL,
        "timeframe": TIMEFRAME,
        "contract": contract,
        "ohlcv_quality": ohlcv_quality,
        "funding_quality": funding_quality,
        "write_enabled": not args.no_write,
    }
    if not args.no_write:
        partitions = {
            "raw_ohlcv": write_daily(
                raw_ohlcv, root=RAW_OHLCV_ROOT, ts_column="open_time"
            ),
            "normalized_ohlcv": write_daily(
                normalized_ohlcv, root=NORMALIZED_OHLCV_ROOT, ts_column="ts"
            ),
            "raw_funding": write_daily(
                raw_funding, root=RAW_FUNDING_ROOT, ts_column="funding_time"
            ),
            "normalized_funding": write_daily(
                normalized_funding, root=NORMALIZED_FUNDING_ROOT, ts_column="ts"
            ),
        }
        summary["partitions"] = partitions
        summary["normalized_consumer_view"] = audit_normalized_consumer_view()
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        output = ARTIFACT_DIR / "mu_binance_15m_data_quality_latest.json"
        output.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary["artifact"] = str(output.relative_to(ROOT))

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
