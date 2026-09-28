from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import duckdb
import numpy as np
import pandas as pd

from strategy_lab.data.manifest import (
    inventory_fingerprint,
    parquet_inventory,
    sha256_file,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.research_inputs import load_v3_research_ohlcv
from strategy_lab.data.settings import default_settings


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/hype/15m-candle-count-reversal"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
PRICE_ROOT = ROOT / "data/derived/datasets/binance_perp_15m_history_v3"
MARK_ROOT = (
    ROOT
    / "data/normalized/mark_price_klines/exchange=binance/market_type=perp/"
    "timeframe=15m"
)
FUNDING_ROOT = ROOT / "data/derived/datasets/binance_perp_funding_v3_inputs_v2"

SUMMARY_PATH = ARTIFACT_DIR / "hype_cc_v35_maker_entry_summary_2026-09-07.json"
COMPARISON_PATH = ARTIFACT_DIR / "hype_cc_v35_maker_entry_comparison_2026-09-07.csv"
TRADES_PATH = ARTIFACT_DIR / "hype_cc_v35_maker_entry_trades_2026-09-07.csv"
SNAPSHOT_PATH = ARTIFACT_DIR / "hype_cc_v35_maker_entry_input_2026-09-07.parquet"

BINANCE_FAPI = "https://fapi.binance.com"
SYMBOL = "HYPEUSDT"
CANONICAL_SYMBOL = "HYPE/USDT:USDT"
BAR_MS = 15 * 60 * 1000
API_OVERLAP_START = pd.Timestamp("2026-07-15T00:00:00Z")
CLAIM_START = pd.Timestamp("2026-08-01T00:00:00Z")
CLAIM_START_ASIA_SHANGHAI = pd.Timestamp("2026-07-31T16:00:00Z")
FROZEN_END_OPEN = pd.Timestamp("2026-09-07T07:30:00Z")
EXPECTED_FUNDING_MANIFEST_SHA256 = (
    "398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076"
)


@dataclass(frozen=True, slots=True)
class CostModel:
    name: str
    fee_rate: float
    taker_slippage_rate: float = 0.0004
    maker_entry_slippage_rate: float = 0.0


@dataclass(frozen=True, slots=True)
class Variant:
    name: str
    entry: Literal["next_open", "maker_extreme"]
    fill_model: Literal["taker", "touch", "trade_through_1tick"]
    ma_filter: Literal["none", "ema24_672_dual", "ema24_672_short_only"] = "none"


@dataclass(slots=True)
class PendingOrder:
    direction: int
    signal_position: int
    signal_ts: pd.Timestamp
    first_fill_position: int
    expiry_position: int
    limit_price: float | None
    base_allocation: float
    stop_loss_pct: float
    take_profit_pct: float


@dataclass(slots=True)
class RunResult:
    variant: Variant
    cost_model: CostModel
    start: pd.Timestamp
    end: pd.Timestamp
    equity_curve: pd.Series
    period_returns: pd.Series
    weights: pd.Series
    trades: pd.DataFrame
    metrics: dict[str, Any]


def _canonical_json_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _request_json(path: str, params: dict[str, Any]) -> Any:
    url = f"{BINANCE_FAPI}{path}?{urllib.parse.urlencode(params)}"
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "quant-strategy-lab-hype-cc-maker-audit/1.0"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except Exception as exc:  # pragma: no cover - exercised only on network failure
            last_error = exc
            if attempt == 3:
                break
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Binance request failed for {path}: {last_error}")


def _fetch_server_time() -> tuple[int, str]:
    payload = _request_json("/fapi/v1/time", {})
    return int(payload["serverTime"]), _canonical_json_sha256(payload)


def _fetch_exchange_tick_size() -> tuple[float, str]:
    payload = _request_json("/fapi/v1/exchangeInfo", {})
    symbol = next(item for item in payload["symbols"] if item["symbol"] == SYMBOL)
    price_filter = next(
        item for item in symbol["filters"] if item["filterType"] == "PRICE_FILTER"
    )
    tick_size = float(price_filter["tickSize"])
    if not np.isfinite(tick_size) or tick_size <= 0.0:
        raise RuntimeError(f"invalid Binance tick size: {tick_size}")
    return tick_size, _canonical_json_sha256(symbol)


def _fetch_klines(
    path: str, start: pd.Timestamp, end_open: pd.Timestamp, server_time_ms: int
) -> tuple[pd.DataFrame, list[str]]:
    cursor = int(start.timestamp() * 1000)
    end_ms = int(end_open.timestamp() * 1000)
    rows: list[list[Any]] = []
    page_hashes: list[str] = []
    while cursor <= end_ms:
        payload = _request_json(
            path,
            {
                "symbol": SYMBOL,
                "interval": "15m",
                "startTime": cursor,
                "endTime": end_ms + BAR_MS - 1,
                "limit": 1500,
            },
        )
        page_hashes.append(_canonical_json_sha256(payload))
        if not payload:
            break
        rows.extend(payload)
        last_open = int(payload[-1][0])
        next_cursor = last_open + BAR_MS
        if next_cursor <= cursor:
            raise RuntimeError(f"non-advancing Binance pagination for {path}")
        cursor = next_cursor
        if len(payload) < 1500:
            break
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
    if frame.empty:
        raise RuntimeError(f"empty Binance response for {path}")
    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="raise").astype(
        "int64"
    )
    frame["close_time"] = pd.to_numeric(frame["close_time"], errors="raise").astype(
        "int64"
    )
    frame = frame.loc[
        frame["open_time"].le(end_ms) & frame["close_time"].lt(server_time_ms)
    ].copy()
    frame["ts"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    for column in ("open", "high", "low", "close", "volume", "quote_volume"):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
    frame["trade_count"] = pd.to_numeric(frame["trade_count"], errors="raise").astype(
        "int64"
    )
    frame = frame.sort_values("ts").drop_duplicates("ts", keep="last")
    return frame, page_hashes


def _fetch_funding(
    start: pd.Timestamp, end_open: pd.Timestamp
) -> tuple[pd.DataFrame, list[str]]:
    cursor = int(start.timestamp() * 1000)
    end_ms = int((end_open + pd.Timedelta(minutes=15)).timestamp() * 1000) - 1
    rows: list[dict[str, Any]] = []
    page_hashes: list[str] = []
    while cursor <= end_ms:
        payload = _request_json(
            "/fapi/v1/fundingRate",
            {"symbol": SYMBOL, "startTime": cursor, "endTime": end_ms, "limit": 1000},
        )
        page_hashes.append(_canonical_json_sha256(payload))
        if not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("non-advancing Binance funding pagination")
        cursor = next_cursor
        if len(payload) < 1000:
            break
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["ts", "funding_rate", "rate_type"]), page_hashes
    frame["ts"] = pd.to_datetime(frame["fundingTime"], unit="ms", utc=True)
    frame["funding_rate"] = pd.to_numeric(frame["fundingRate"], errors="raise")
    frame["rate_type"] = frame.get("rateType", pd.Series("Unknown", index=frame.index))
    return (
        frame.sort_values("ts").drop_duplicates(["ts", "rate_type"], keep="last"),
        page_hashes,
    )


def _load_local_trade() -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest_path = PRICE_ROOT / "_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_fingerprint = inventory_fingerprint(parquet_inventory(PRICE_ROOT))
    manifest_fingerprint = manifest["parquet_inventory_fingerprint"]
    frame = load_v3_research_ohlcv(
        layout=DataLakeLayout.from_settings(default_settings()),
        timeframe="15m",
        symbol=CANONICAL_SYMBOL,
        start="2025-05-30T10:30:00Z",
        end=manifest["cutoff_exclusive_utc"],
        identity_policy="observed_diagnostic",
    )
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    verified_identity = frame.attrs["verified_identity"]
    dataset_audit = frame.attrs["ohlcv_audit"]
    quality = _audit_ohlcv(frame, "local_history_v3")
    quality.update(
        {
            "dataset_id": manifest["dataset_id"],
            "manifest_sha256": sha256_file(manifest_path),
            "manifest_inventory_fingerprint": manifest_fingerprint,
            "actual_inventory_fingerprint": actual_fingerprint,
            "manifest_inventory_match": actual_fingerprint == manifest_fingerprint,
            "catalog_trusted_read": True,
            "catalog_fingerprint_mode": verified_identity["fingerprint_mode"],
            "catalog_row_quality": dataset_audit["row_quality"],
            "catalog_research_window_fitness": dataset_audit[
                "research_window_fitness"
            ],
            "identity_policy": frame.attrs["identity_policy"],
            "tradability_proven": frame.attrs["tradability_proven"],
        }
    )
    return frame, quality


def _load_local_mark() -> tuple[pd.DataFrame, dict[str, Any]]:
    files = sorted(MARK_ROOT.glob("date=*/symbol=hype_usdt_usdt.parquet"))
    if not files:
        raise RuntimeError(f"no local mark-price files under {MARK_ROOT}")
    frame = pd.concat(
        [pd.read_parquet(path, columns=["ts", "high", "low"]) for path in files],
        ignore_index=True,
    )
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame = frame.sort_values("ts").drop_duplicates("ts", keep="last")
    expected = pd.date_range(frame.ts.iloc[0], frame.ts.iloc[-1], freq="15min")
    return frame, {
        "files": len(files),
        "rows": len(frame),
        "start": frame.ts.iloc[0].isoformat(),
        "end": frame.ts.iloc[-1].isoformat(),
        "missing_bars": len(expected.difference(pd.DatetimeIndex(frame.ts))),
        "null_high_low": int(frame[["high", "low"]].isna().any(axis=1).sum()),
    }


def _audit_ohlcv(
    frame: pd.DataFrame, label: str, *, require_positive_volume: bool = True
) -> dict[str, Any]:
    if frame.empty:
        raise RuntimeError(f"{label} is empty")
    frame = frame.sort_values("ts")
    index = pd.DatetimeIndex(pd.to_datetime(frame["ts"], utc=True))
    expected = pd.date_range(index[0], index[-1], freq="15min")
    numeric = frame[["open", "high", "low", "close", "volume"]].astype(float)
    ohlc_legal = (
        numeric["high"].ge(numeric[["open", "close", "low"]].max(axis=1))
        & numeric["low"].le(numeric[["open", "close", "high"]].min(axis=1))
        & numeric[["open", "high", "low", "close"]].gt(0.0).all(axis=1)
    )
    quality = {
        "label": label,
        "rows": int(len(frame)),
        "start": index[0].isoformat(),
        "end": index[-1].isoformat(),
        "duplicates": int(index.duplicated().sum()),
        "missing_bars": int(len(expected.difference(index))),
        "nonfinite_ohlcv": int((~np.isfinite(numeric.to_numpy())).any(axis=1).sum()),
        "ohlc_violations": int((~ohlc_legal).sum()),
        "zero_volume": int(numeric["volume"].le(0.0).sum()),
    }
    blockers = sum(
        int(quality[key])
        for key in (
            "duplicates",
            "missing_bars",
            "nonfinite_ohlcv",
            "ohlc_violations",
        )
    )
    if require_positive_volume:
        blockers += int(quality["zero_volume"])
    if blockers:
        raise RuntimeError(f"{label} OHLCV quality failure: {quality}")
    return quality


def _compare_overlap(
    local: pd.DataFrame, official: pd.DataFrame, columns: tuple[str, ...]
) -> dict[str, Any]:
    overlap_start = max(local.ts.min(), official.ts.min())
    overlap_end = min(local.ts.max(), official.ts.max())
    left = local.loc[local.ts.between(overlap_start, overlap_end), ["ts", *columns]]
    right = official.loc[
        official.ts.between(overlap_start, overlap_end), ["ts", *columns]
    ]
    joined = left.merge(
        right, on="ts", how="outer", suffixes=("_local", "_official"), indicator=True
    )
    mismatches: dict[str, int] = {
        "missing_local": int(joined["_merge"].eq("right_only").sum()),
        "missing_official": int(joined["_merge"].eq("left_only").sum()),
    }
    common = joined.loc[joined["_merge"].eq("both")]
    for column in columns:
        mismatches[column] = int(
            (~np.isclose(
                common[f"{column}_local"].astype(float),
                common[f"{column}_official"].astype(float),
                rtol=0.0,
                atol=1e-10,
            )).sum()
        )
    return {
        "start": overlap_start.isoformat(),
        "end": overlap_end.isoformat(),
        "rows": int(len(common)),
        "mismatches": mismatches,
    }


def _load_and_compare_funding(
    official: pd.DataFrame,
) -> tuple[pd.Series, dict[str, Any]]:
    manifest_path = FUNDING_ROOT / "_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_manifest_sha = sha256_file(manifest_path)
    actual_inventory = inventory_fingerprint(parquet_inventory(FUNDING_ROOT))
    event_files = [str(path) for path in sorted((FUNDING_ROOT / "events").rglob("*.parquet"))]
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    try:
        local = connection.execute(
            """
            SELECT ts, funding_rate, rate_type, event_unambiguous, event_id
            FROM read_parquet(?) WHERE symbol = ? ORDER BY ts
            """,
            [event_files, CANONICAL_SYMBOL],
        ).df()
    finally:
        connection.close()
    local["ts"] = pd.to_datetime(local["ts"], utc=True)
    segments = pd.read_parquet(FUNDING_ROOT / "coverage/segments.parquet")
    segments["start"] = pd.to_datetime(segments["start"], utc=True)
    segments["end"] = pd.to_datetime(segments["end"], utc=True)
    hype_segments = segments.loc[segments.symbol.eq(CANONICAL_SYMBOL)].copy()
    overlap_start = max(local.ts.min(), official.ts.min())
    overlap_end = min(local.ts.max(), official.ts.max())
    local_overlap = local.loc[local.ts.between(overlap_start, overlap_end)].copy()
    official_overlap = official.loc[official.ts.between(overlap_start, overlap_end)].copy()
    joined = local_overlap.merge(
        official_overlap[["ts", "funding_rate", "rate_type"]],
        on="ts",
        how="outer",
        suffixes=("_local", "_official"),
        indicator=True,
    )
    both = joined.loc[joined["_merge"].eq("both")]
    compare = {
        "overlap_start": overlap_start.isoformat(),
        "overlap_end": overlap_end.isoformat(),
        "local_rows": int(len(local_overlap)),
        "official_rows": int(len(official_overlap)),
        "missing_local": int(joined["_merge"].eq("right_only").sum()),
        "missing_official": int(joined["_merge"].eq("left_only").sum()),
        "rate_mismatches": int(
            (~np.isclose(
                both["funding_rate_local"].astype(float),
                both["funding_rate_official"].astype(float),
                rtol=0.0,
                atol=1e-12,
            )).sum()
        ),
        "type_mismatches": int(
            both["rate_type_local"].astype(str).ne(both["rate_type_official"].astype(str)).sum()
        ),
    }
    funding_by_bar = (
        official.assign(bar_ts=official.ts.dt.floor("15min"))
        .groupby("bar_ts", sort=True)["funding_rate"]
        .sum()
    )
    quality = {
        "dataset_id": manifest["dataset_id"],
        "manifest_sha256": actual_manifest_sha,
        "expected_manifest_sha256": EXPECTED_FUNDING_MANIFEST_SHA256,
        "manifest_identity_match": actual_manifest_sha
        == EXPECTED_FUNDING_MANIFEST_SHA256,
        "manifest_inventory_fingerprint": manifest["parquet_inventory_fingerprint"],
        "actual_inventory_fingerprint": actual_inventory,
        "inventory_match": actual_inventory
        == manifest["parquet_inventory_fingerprint"],
        "status": manifest["status"],
        "full_historical_funding_calendar_verified": manifest[
            "full_historical_funding_calendar_verified"
        ],
        "local_hype_rows": int(len(local)),
        "local_ambiguous_rows": int((~local.event_unambiguous).sum()),
        "verified_segments": [
            {
                "segment_id": row.segment_id,
                "start": row.start.isoformat(),
                "end": row.end.isoformat(),
                "expected_events": int(row.expected_events),
            }
            for row in hype_segments.itertuples()
        ],
        "official_comparison": compare,
        "full_claim_window_net_status": "OBSERVED_ONLY_NOT_VERIFIED",
    }
    return funding_by_bar, quality


def load_input_frame() -> tuple[pd.DataFrame, float, dict[str, Any]]:
    server_time_ms, server_time_sha = _fetch_server_time()
    server_time = pd.to_datetime(server_time_ms, unit="ms", utc=True)
    latest_available_open = server_time.floor("15min") - pd.Timedelta(minutes=15)
    if latest_available_open < FROZEN_END_OPEN:
        raise RuntimeError(
            f"Binance server has not closed frozen end bar {FROZEN_END_OPEN.isoformat()}"
        )
    last_closed_open = FROZEN_END_OPEN
    tick_size, exchange_info_sha = _fetch_exchange_tick_size()

    local_trade, local_trade_quality = _load_local_trade()
    local_mark, local_mark_quality = _load_local_mark()
    official_trade, trade_page_hashes = _fetch_klines(
        "/fapi/v1/klines", API_OVERLAP_START, last_closed_open, server_time_ms
    )
    official_mark, mark_page_hashes = _fetch_klines(
        "/fapi/v1/markPriceKlines",
        API_OVERLAP_START,
        last_closed_open,
        server_time_ms,
    )
    official_trade_quality = _audit_ohlcv(official_trade, "official_rest_trade")
    official_mark_quality = _audit_ohlcv(
        official_mark, "official_rest_mark", require_positive_volume=False
    )
    trade_overlap = _compare_overlap(
        local_trade, official_trade, ("open", "high", "low", "close", "volume")
    )
    mark_overlap = _compare_overlap(local_mark, official_mark, ("high", "low"))

    official_funding, funding_page_hashes = _fetch_funding(
        local_trade.ts.min(), last_closed_open
    )
    funding_by_bar, funding_quality = _load_and_compare_funding(official_funding)

    trade = pd.concat(
        [
            local_trade.loc[local_trade.ts.lt(API_OVERLAP_START)],
            official_trade.assign(
                symbol=CANONICAL_SYMBOL,
                timeframe="15m",
                is_closed=True,
                source="binance_futures_rest_live_snapshot",
            ),
        ],
        ignore_index=True,
        sort=False,
    )
    trade = trade.sort_values("ts").drop_duplicates("ts", keep="last")
    mark = pd.concat(
        [
            local_mark.loc[local_mark.ts.lt(API_OVERLAP_START)],
            official_mark[["ts", "high", "low"]],
        ],
        ignore_index=True,
    )
    mark = mark.sort_values("ts").drop_duplicates("ts", keep="last")
    frame = trade[["ts", "open", "high", "low", "close", "volume"]].merge(
        mark.rename(columns={"high": "mark_high", "low": "mark_low"}),
        on="ts",
        how="left",
        validate="one_to_one",
    )
    frame["funding_rate"] = funding_by_bar.reindex(frame.ts).fillna(0.0).to_numpy()
    frame = frame.loc[frame.ts.le(last_closed_open)].sort_values("ts")
    combined_quality = _audit_ohlcv(frame, "combined_research_frame")
    combined_quality["missing_mark_bars"] = int(
        frame[["mark_high", "mark_low"]].isna().any(axis=1).sum()
    )
    if combined_quality["missing_mark_bars"]:
        raise RuntimeError(f"combined frame has missing mark bars: {combined_quality}")
    if not frame.ts.iloc[-1] == last_closed_open:
        raise RuntimeError(
            f"official tail does not reach last closed bar {last_closed_open.isoformat()}"
        )
    frame = frame.set_index("ts")
    data_quality = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "binance_server_time": server_time.isoformat(),
        "latest_available_bar_open_at_fetch": latest_available_open.isoformat(),
        "last_closed_bar_open": last_closed_open.isoformat(),
        "server_time_receipt_sha256": server_time_sha,
        "exchange_symbol_receipt_sha256": exchange_info_sha,
        "tick_size": tick_size,
        "local_trade": local_trade_quality,
        "local_mark": local_mark_quality,
        "official_trade": official_trade_quality,
        "official_mark": official_mark_quality,
        "trade_overlap": trade_overlap,
        "mark_overlap": mark_overlap,
        "funding": funding_quality,
        "combined": combined_quality,
        "api_receipts": {
            "trade_page_sha256": trade_page_hashes,
            "mark_page_sha256": mark_page_hashes,
            "funding_page_sha256": funding_page_hashes,
        },
    }
    return frame, tick_size, data_quality


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    bullish = out.close.gt(out.open).astype(float)
    bearish = out.close.lt(out.open).astype(float)
    bullish_count = bullish.rolling(10, min_periods=10).sum()
    bearish_count = bearish.rolling(10, min_periods=10).sum()
    out["signal"] = 0
    out.loc[bullish_count.ge(8), "signal"] = -1
    out.loc[bearish_count.ge(8), "signal"] = 1
    previous_close = out.close.shift(1)
    true_range = pd.concat(
        [
            out.high - out.low,
            (out.high - previous_close).abs(),
            (out.low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr_pct_672"] = true_range.rolling(672, min_periods=672).mean() / out.close
    out["trend_return_96"] = out.close.pct_change(96, fill_method=None)
    out["limit_low_10"] = out.low.rolling(10, min_periods=10).min()
    out["limit_high_10"] = out.high.rolling(10, min_periods=10).max()
    out["ema24"] = out.close.ewm(span=24, adjust=False, min_periods=24).mean()
    out["ema672"] = out.close.ewm(span=672, adjust=False, min_periods=672).mean()
    return out


def _signal_allowed(
    frame: pd.DataFrame, position: int, direction: int, ma_filter: str
) -> tuple[bool, str | None]:
    if position <= 0 or int(frame.signal.iloc[position - 1]) == direction:
        return False, "not_signal_start"
    start = max(0, position - 8)
    if frame.signal.iloc[start:position].eq(-direction).any():
        return False, "opposite_gap"
    trend = float(frame.trend_return_96.iloc[position])
    if not np.isfinite(trend):
        return False, "trend_unavailable"
    if direction < 0 and trend > 0.05:
        return False, "original_trend_filter"
    if direction > 0 and trend < -0.05:
        return False, "original_trend_filter"
    fast = float(frame.ema24.iloc[position])
    slow = float(frame.ema672.iloc[position])
    if ma_filter == "ema24_672_dual":
        if not np.isfinite(fast) or not np.isfinite(slow):
            return False, "ma_filter"
        if (direction > 0 and fast <= slow) or (direction < 0 and fast >= slow):
            return False, "ma_filter"
    elif ma_filter == "ema24_672_short_only" and direction < 0:
        if not np.isfinite(fast) or not np.isfinite(slow) or fast >= slow:
            return False, "ma_filter"
    return True, None


def _pending_from_signal(
    frame: pd.DataFrame, position: int, direction: int, variant: Variant
) -> PendingOrder | None:
    atr_pct = float(frame.atr_pct_672.iloc[position])
    if not np.isfinite(atr_pct) or atr_pct <= 0.0:
        return None
    base_allocation = min(3.0, 3.0 * 0.006 / atr_pct)
    stop_loss_pct = float(np.clip(atr_pct * 5.0, 0.025, 0.035))
    take_profit_pct = float(np.clip(atr_pct * 5.5, 0.020, 0.035))
    if variant.entry == "next_open":
        limit_price = None
        expiry = position + 1
    else:
        limit_price = float(
            frame.limit_low_10.iloc[position]
            if direction > 0
            else frame.limit_high_10.iloc[position]
        )
        expiry = position + 16
    return PendingOrder(
        direction=direction,
        signal_position=position,
        signal_ts=pd.Timestamp(frame.index[position]),
        first_fill_position=position + 1,
        expiry_position=expiry,
        limit_price=limit_price,
        base_allocation=base_allocation,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
    )


def _maker_filled(
    order: PendingOrder,
    high: float,
    low: float,
    fill_model: str,
    tick_size: float,
) -> bool:
    if order.limit_price is None:
        return True
    threshold = 0.0 if fill_model == "touch" else tick_size
    if order.direction > 0:
        return low <= order.limit_price - threshold
    return high >= order.limit_price + threshold


def _protective_exit(
    direction: int,
    entry_price: float,
    mark_high: float,
    mark_low: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> tuple[float | None, str | None]:
    if direction > 0:
        stop = entry_price * (1.0 - stop_loss_pct)
        take = entry_price * (1.0 + take_profit_pct)
        if mark_low <= stop:
            return stop, "stop"
        if mark_high >= take:
            return take, "take"
    else:
        stop = entry_price * (1.0 + stop_loss_pct)
        take = entry_price * (1.0 - take_profit_pct)
        if mark_high >= stop:
            return stop, "stop"
        if mark_low <= take:
            return take, "take"
    return None, None


def _early_exit_reason(
    frame: pd.DataFrame, entry_position: int, position: int, direction: int
) -> str | None:
    bars_held = position - entry_position + 1
    if bars_held == 3:
        window = frame.iloc[entry_position : position + 1]
        opposite = (
            int(window.close.lt(window.open).sum())
            if direction > 0
            else int(window.close.gt(window.open).sum())
        )
        if opposite == 3:
            return "early_main"
    if bars_held == 12:
        window = frame.iloc[entry_position : position + 1]
        if direction > 0:
            opposite = int(window.close.lt(window.open).sum())
            favorable = int(window.close.gt(window.open).sum())
        else:
            opposite = int(window.close.gt(window.open).sum())
            favorable = int(window.close.lt(window.open).sum())
        if opposite >= 9:
            return "early_counter_opposite"
        if favorable >= 9:
            return "early_counter_favorable"
    return None


def run_backtest(
    frame: pd.DataFrame,
    *,
    variant: Variant,
    costs: CostModel,
    tick_size: float,
    trade_start: pd.Timestamp,
    trade_end: pd.Timestamp,
) -> RunResult:
    if trade_start not in frame.index or trade_end not in frame.index:
        raise ValueError("trade bounds must be exact bar opens in the input frame")
    start_position = int(frame.index.get_loc(trade_start))
    end_position = int(frame.index.get_loc(trade_end))
    if start_position >= end_position:
        raise ValueError("trade window must contain at least two bars")

    equity = 1.0
    direction = 0
    pending: PendingOrder | None = None
    entry_position: int | None = None
    entry_ts: pd.Timestamp | None = None
    entry_price = math.nan
    entry_equity = math.nan
    previous_price = float(frame.close.iloc[start_position])
    allocation = 0.0
    base_allocation = 0.0
    risk_at_entry = 1.0
    stop_loss_pct = 0.0
    take_profit_pct = 0.0
    signal_ts: pd.Timestamp | None = None
    order_limit: float | None = None
    risk_multiplier = 1.0
    cooldown_remaining = 0

    equity_values: list[float] = []
    period_returns: list[float] = []
    weights: list[float] = []
    trades: list[dict[str, Any]] = []
    counters: dict[str, int] = {
        "signals": 0,
        "entries": 0,
        "exits": 0,
        "expired_orders": 0,
        "blocked_original_trend": 0,
        "blocked_ma": 0,
        "long_entries": 0,
        "short_entries": 0,
        "stop": 0,
        "take": 0,
        "early_main": 0,
        "early_counter_opposite": 0,
        "early_counter_favorable": 0,
        "terminal_mark": 0,
    }
    trading_costs = 0.0
    funding_pnl = 0.0
    fill_delays: list[int] = []

    def close_trade(
        position: int, exit_price: float, reason: str, bar_return: float
    ) -> float:
        nonlocal equity, direction, entry_position, entry_ts, entry_price
        nonlocal entry_equity, previous_price, allocation, base_allocation
        nonlocal risk_at_entry, stop_loss_pct, take_profit_pct, signal_ts
        nonlocal order_limit, risk_multiplier, cooldown_remaining, trading_costs
        pnl = direction * allocation * (exit_price / previous_price - 1.0)
        exit_cost = allocation * (costs.fee_rate + costs.taker_slippage_rate)
        equity *= 1.0 + pnl - exit_cost
        bar_return += pnl - exit_cost
        trading_costs += exit_cost
        counters["exits"] += 1
        counters[reason] += 1
        if reason == "stop":
            risk_multiplier = max(0.0625, risk_multiplier * 0.5)
        elif reason == "take":
            risk_multiplier = 1.0
        trades.append(
            {
                "variant": variant.name,
                "cost_model": costs.name,
                "signal_ts": signal_ts,
                "entry_ts": entry_ts,
                "exit_ts": pd.Timestamp(frame.index[position]),
                "direction": direction,
                "order_limit": order_limit,
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "fill_delay_bars": (
                    None
                    if signal_ts is None or entry_ts is None
                    else int((entry_ts - signal_ts) / pd.Timedelta(minutes=15))
                ),
                "allocation": allocation,
                "base_allocation": base_allocation,
                "risk_multiplier_at_entry": risk_at_entry,
                "stop_loss_pct": stop_loss_pct,
                "take_profit_pct": take_profit_pct,
                "entry_equity": float(entry_equity),
                "exit_equity": float(equity),
                "trade_return": float(equity / entry_equity - 1.0),
                "exit_reason": reason,
                "same_bar_exit": position == entry_position,
            }
        )
        direction = 0
        entry_position = None
        entry_ts = None
        entry_price = math.nan
        entry_equity = math.nan
        allocation = 0.0
        base_allocation = 0.0
        risk_at_entry = 1.0
        stop_loss_pct = 0.0
        take_profit_pct = 0.0
        signal_ts = None
        order_limit = None
        previous_price = float(frame.close.iloc[position])
        if reason != "terminal_mark":
            cooldown_remaining = max(cooldown_remaining, 8)
        return bar_return

    for position in range(start_position, end_position + 1):
        ts = pd.Timestamp(frame.index[position])
        close_price = float(frame.close.iloc[position])
        bar_return = 0.0
        exited_this_bar = False
        cooldown_at_start = cooldown_remaining

        if direction == 0 and pending is not None and position >= pending.first_fill_position:
            if position <= pending.expiry_position and _maker_filled(
                pending,
                high=float(frame.high.iloc[position]),
                low=float(frame.low.iloc[position]),
                fill_model=variant.fill_model,
                tick_size=tick_size,
            ):
                direction = pending.direction
                entry_position = position
                entry_ts = ts
                entry_price = (
                    float(frame.open.iloc[position])
                    if pending.limit_price is None
                    else float(pending.limit_price)
                )
                previous_price = entry_price
                entry_equity = equity
                base_allocation = pending.base_allocation
                allocation = base_allocation * risk_multiplier
                risk_at_entry = risk_multiplier
                stop_loss_pct = pending.stop_loss_pct
                take_profit_pct = pending.take_profit_pct
                signal_ts = pending.signal_ts
                order_limit = pending.limit_price
                entry_cost_rate = costs.fee_rate + (
                    costs.taker_slippage_rate
                    if pending.limit_price is None
                    else costs.maker_entry_slippage_rate
                )
                entry_cost = allocation * entry_cost_rate
                equity *= 1.0 - entry_cost
                bar_return -= entry_cost
                trading_costs += entry_cost
                counters["entries"] += 1
                counters["long_entries" if direction > 0 else "short_entries"] += 1
                fill_delays.append(position - pending.signal_position)
                pending = None
            elif position >= pending.expiry_position:
                counters["expired_orders"] += 1
                pending = None

        if direction != 0 and entry_position is not None:
            exit_price, exit_reason = _protective_exit(
                direction,
                float(entry_price),
                float(frame.mark_high.iloc[position]),
                float(frame.mark_low.iloc[position]),
                stop_loss_pct,
                take_profit_pct,
            )
            if exit_price is None:
                exit_reason = _early_exit_reason(frame, entry_position, position, direction)
                if exit_reason is not None:
                    exit_price = close_price
            if exit_price is None:
                pnl = direction * allocation * (close_price / previous_price - 1.0)
                equity *= 1.0 + pnl
                bar_return += pnl
                previous_price = close_price
            else:
                bar_return = close_trade(
                    position, float(exit_price), str(exit_reason), bar_return
                )
                exited_this_bar = True
        elif position > start_position:
            previous_price = close_price

        if direction != 0:
            funding = -direction * allocation * float(frame.funding_rate.iloc[position])
            equity *= 1.0 + funding
            bar_return += funding
            funding_pnl += funding

        if (
            position < end_position
            and direction == 0
            and pending is None
            and cooldown_remaining == 0
            and not exited_this_bar
        ):
            desired = int(frame.signal.iloc[position])
            if desired != 0:
                counters["signals"] += 1
                allowed, reason = _signal_allowed(frame, position, desired, variant.ma_filter)
                if allowed:
                    pending = _pending_from_signal(frame, position, desired, variant)
                elif reason == "original_trend_filter":
                    counters["blocked_original_trend"] += 1
                elif reason == "ma_filter":
                    counters["blocked_ma"] += 1

        if position == end_position and direction != 0:
            bar_return = close_trade(position, close_price, "terminal_mark", bar_return)
            exited_this_bar = True
        if position == end_position and pending is not None:
            counters["expired_orders"] += 1
            pending = None

        equity_values.append(equity)
        period_returns.append(bar_return)
        weights.append(direction * allocation)
        if cooldown_at_start > 0:
            cooldown_remaining -= 1

    index = frame.index[start_position : end_position + 1]
    equity_curve = pd.Series(equity_values, index=index, name="equity")
    period_return_series = pd.Series(period_returns, index=index, name="period_return")
    weight_series = pd.Series(weights, index=index, name="weight")
    drawdown = equity_curve / equity_curve.cummax() - 1.0
    standard_deviation = float(period_return_series.std(ddof=0))
    sharpe = (
        float(period_return_series.mean() / standard_deviation * math.sqrt(365 * 24 * 4))
        if standard_deviation > 0.0
        else 0.0
    )
    trade_frame = pd.DataFrame(trades)
    wins = (
        int(trade_frame.loc[trade_frame.exit_reason.ne("terminal_mark"), "trade_return"].gt(0).sum())
        if not trade_frame.empty
        else 0
    )
    natural_trades = (
        int(trade_frame.exit_reason.ne("terminal_mark").sum())
        if not trade_frame.empty
        else 0
    )
    metrics = {
        **counters,
        "return_pct": round((equity - 1.0) * 100.0, 6),
        "ending_equity": float(equity),
        "max_drawdown_pct": round(float(drawdown.min()) * 100.0, 6),
        "sharpe": round(sharpe, 6),
        "win_rate_pct": round(wins / natural_trades * 100.0, 6)
        if natural_trades
        else None,
        "avg_abs_allocation": float(weight_series.abs().mean()),
        "max_abs_allocation": float(weight_series.abs().max()),
        "trading_costs_fraction_sum": float(trading_costs),
        "funding_pnl_fraction_sum": float(funding_pnl),
        "maker_fill_rate_pct": (
            round(counters["entries"] / max(1, counters["entries"] + counters["expired_orders"]) * 100.0, 6)
            if variant.entry == "maker_extreme"
            else None
        ),
        "median_fill_delay_bars": float(np.median(fill_delays)) if fill_delays else None,
        "max_fill_delay_bars": max(fill_delays) if fill_delays else None,
        "entered_and_exited_same_bar": int(
            trade_frame.same_bar_exit.sum() if not trade_frame.empty else 0
        ),
        "funding_treatment": "official_observed_events; full-window calendar not verified",
    }
    return RunResult(
        variant=variant,
        cost_model=costs,
        start=trade_start,
        end=trade_end,
        equity_curve=equity_curve,
        period_returns=period_return_series,
        weights=weight_series,
        trades=trade_frame,
        metrics=metrics,
    )


def _window_starts(end: pd.Timestamp, earliest: pd.Timestamp) -> dict[str, pd.Timestamp]:
    candidates = {
        "1d": end - pd.Timedelta(days=1),
        "7d": end - pd.Timedelta(days=7),
        "1m": end - pd.Timedelta(days=30),
        "3m": end - pd.Timedelta(days=90),
        "6m": end - pd.Timedelta(days=180),
        "1y": end - pd.Timedelta(days=365),
    }
    return {name: max(start.ceil("15min"), earliest) for name, start in candidates.items()}


def _comparison_row(label: str, result: RunResult) -> dict[str, Any]:
    return {
        "window": label,
        "start": result.start.isoformat(),
        "end": result.end.isoformat(),
        "variant": result.variant.name,
        "entry": result.variant.entry,
        "fill_model": result.variant.fill_model,
        "ma_filter": result.variant.ma_filter,
        "cost_model": result.cost_model.name,
        **result.metrics,
    }


def _slice_existing_run(
    result: RunResult, start: pd.Timestamp, label: str
) -> dict[str, Any]:
    equity = result.equity_curve.loc[result.equity_curve.index >= start]
    normalized = equity / float(equity.iloc[0])
    drawdown = normalized / normalized.cummax() - 1.0
    return {
        "window": label,
        "start": equity.index[0].isoformat(),
        "end": equity.index[-1].isoformat(),
        "variant": result.variant.name,
        "cost_model": result.cost_model.name,
        "return_pct": round(float(normalized.iloc[-1] - 1.0) * 100.0, 6),
        "max_drawdown_pct": round(float(drawdown.min()) * 100.0, 6),
        "state_initialization": "continuous_from_listing_then_normalized",
    }


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    frame, tick_size, data_quality = load_input_frame()
    featured = build_features(frame)
    end = pd.Timestamp(featured.index[-1])
    if CLAIM_START < featured.index[0] or CLAIM_START >= end:
        raise RuntimeError("claim window is outside available HYPE data")

    primary_cost = CostModel("v35_explicit", fee_rate=0.00045)
    conservative_cost = CostModel("binance_repo_default", fee_rate=0.001)
    variants = [
        Variant("B0_next_open_taker", "next_open", "taker"),
        Variant(
            "B1_ema24_672_dual_next_open",
            "next_open",
            "taker",
            "ema24_672_dual",
        ),
        Variant(
            "B1_ema24_672_short_only_next_open",
            "next_open",
            "taker",
            "ema24_672_short_only",
        ),
        Variant("M0_extreme_touch", "maker_extreme", "touch"),
        Variant("M0_extreme_trade_through_1tick", "maker_extreme", "trade_through_1tick"),
        Variant(
            "M1_ema24_672_dual_trade_through",
            "maker_extreme",
            "trade_through_1tick",
            "ema24_672_dual",
        ),
        Variant(
            "M1_ema24_672_short_only_trade_through",
            "maker_extreme",
            "trade_through_1tick",
            "ema24_672_short_only",
        ),
    ]

    results: list[tuple[str, RunResult]] = []
    for variant in variants:
        results.append(
            (
                "since_2026-08-01_fresh_state",
                run_backtest(
                    featured,
                    variant=variant,
                    costs=primary_cost,
                    tick_size=tick_size,
                    trade_start=CLAIM_START,
                    trade_end=end,
                ),
            )
        )
    for variant in variants:
        results.append(
            (
                "since_2026-08-01_asia_shanghai_fresh_state",
                run_backtest(
                    featured,
                    variant=variant,
                    costs=primary_cost,
                    tick_size=tick_size,
                    trade_start=CLAIM_START_ASIA_SHANGHAI,
                    trade_end=end,
                ),
            )
        )

    frictionless = featured.copy()
    frictionless["funding_rate"] = 0.0
    frictionless_cost = CostModel(
        "frictionless_no_funding", fee_rate=0.0, taker_slippage_rate=0.0
    )
    for variant in variants:
        results.append(
            (
                "since_2026-08-01_frictionless_no_funding_sensitivity",
                run_backtest(
                    frictionless,
                    variant=variant,
                    costs=frictionless_cost,
                    tick_size=tick_size,
                    trade_start=CLAIM_START,
                    trade_end=end,
                ),
            )
        )
    for variant in variants:
        results.append(
            (
                "since_2026-08-01_fresh_state",
                run_backtest(
                    featured,
                    variant=variant,
                    costs=conservative_cost,
                    tick_size=tick_size,
                    trade_start=CLAIM_START,
                    trade_end=end,
                ),
            )
        )

    slice_starts = _window_starts(end, featured.index[0])
    for label, start in slice_starts.items():
        for variant in variants:
            results.append(
                (
                    f"recent_{label}_fresh_state",
                    run_backtest(
                        featured,
                        variant=variant,
                        costs=primary_cost,
                        tick_size=tick_size,
                        trade_start=start,
                        trade_end=end,
                    ),
                )
            )

    full_runs = [
        run_backtest(
            featured,
            variant=variant,
            costs=primary_cost,
            tick_size=tick_size,
            trade_start=featured.index[0],
            trade_end=end,
        )
        for variant in variants
    ]
    continuous_rows = [
        _slice_existing_run(run, CLAIM_START, "since_2026-08-01_continuous_state")
        for run in full_runs
    ]

    comparison_rows = [
        _comparison_row(label, result) for label, result in results
    ] + continuous_rows
    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(COMPARISON_PATH, index=False)
    primary_trades = []
    for label, result in results:
        if label != "since_2026-08-01_fresh_state" or result.trades.empty:
            continue
        trades = result.trades.copy()
        trades.insert(0, "window", label)
        primary_trades.append(trades)
    pd.concat(primary_trades, ignore_index=True).to_csv(TRADES_PATH, index=False)

    snapshot = featured.reset_index()
    snapshot.to_parquet(SNAPSHOT_PATH, index=False)
    snapshot_sha = sha256_file(SNAPSHOT_PATH)

    primary = comparison.loc[
        comparison.window.eq("since_2026-08-01_fresh_state")
        & comparison.cost_model.eq(primary_cost.name)
    ].set_index("variant")
    baseline_return = float(primary.loc["B0_next_open_taker", "return_pct"])
    touch_return = float(primary.loc["M0_extreme_touch", "return_pct"])
    strict_return = float(
        primary.loc["M0_extreme_trade_through_1tick", "return_pct"]
    )
    dual_next_open_return = float(
        primary.loc["B1_ema24_672_dual_next_open", "return_pct"]
    )
    dual_maker_return = float(
        primary.loc["M1_ema24_672_dual_trade_through", "return_pct"]
    )
    short_only_next_open_return = float(
        primary.loc["B1_ema24_672_short_only_next_open", "return_pct"]
    )
    short_only_maker_return = float(
        primary.loc["M1_ema24_672_short_only_trade_through", "return_pct"]
    )
    numeric_300_reproduced = touch_return >= 300.0 and strict_return >= 300.0
    maker_improves = touch_return > baseline_return and strict_return > baseline_return
    blockers = [
        "FULL_CLAIM_WINDOW_FUNDING_CALENDAR_NOT_VERIFIED",
        "MA_SPEC_FROM_SCREENSHOT_MISSING",
        "MAKER_QUEUE_AND_PARTIAL_FILL_UNOBSERVED_IN_OHLC",
    ]
    primary_frame = primary.reset_index().astype(object)
    primary_records = primary_frame.where(pd.notna(primary_frame), None).to_dict(
        "records"
    )
    timezone_frame = comparison.loc[
        comparison.window.eq("since_2026-08-01_asia_shanghai_fresh_state")
        & comparison.cost_model.eq(primary_cost.name)
    ].astype(object)
    timezone_records = timezone_frame.where(pd.notna(timezone_frame), None).to_dict(
        "records"
    )
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "family": "HYPE-Candle-Count-Reversal",
        "strategy_baseline": "HYPE-CC-V35",
        "research_role": "diagnostic_only_not_a_new_version",
        "claim": {
            "window_start": CLAIM_START.isoformat(),
            "window_end": end.isoformat(),
            "claimed_return_pct": 300.0,
            "numeric_300_reproduced_under_both_maker_fill_models": numeric_300_reproduced,
            "maker_improves_over_next_open_under_both_fill_models": maker_improves,
            "baseline_return_pct": baseline_return,
            "maker_touch_return_pct": touch_return,
            "maker_trade_through_return_pct": strict_return,
        },
        "ema_factorial": {
            "dual_next_open_return_pct": dual_next_open_return,
            "dual_maker_return_pct": dual_maker_return,
            "dual_maker_minus_next_open_percentage_points": round(
                dual_maker_return - dual_next_open_return, 6
            ),
            "short_only_next_open_return_pct": short_only_next_open_return,
            "short_only_maker_return_pct": short_only_maker_return,
            "short_only_maker_minus_next_open_percentage_points": round(
                short_only_maker_return - short_only_next_open_return, 6
            ),
        },
        "formal_conclusion": "DATA_OR_REPRODUCTION_FAILURE",
        "formal_blockers": blockers,
        "data_quality": data_quality,
        "contracts": {
            "signal_and_risk": "HYPE-CC-V35 frozen rules",
            "maker_limit": "long=min(low,last10); short=max(high,last10)",
            "order_lifetime_bars": 16,
            "touch_model": "full fill on touch; optimistic queue assumption",
            "strict_model": "full fill only after one-tick trade-through; still no queue/partial-fill proof",
            "ma_sensitivity": "EMA24/672 dual and short-only; not exact colleague reproduction",
            "primary_cost": asdict(primary_cost),
            "conservative_cost": asdict(conservative_cost),
            "frictionless_sensitivity": asdict(frictionless_cost),
            "funding": "official observed events applied; complete calendar not verified for full claim window",
        },
        "artifact_identity": {
            "input_snapshot": str(SNAPSHOT_PATH.relative_to(ROOT)),
            "input_snapshot_sha256": snapshot_sha,
            "input_snapshot_start": snapshot.ts.iloc[0].isoformat(),
            "input_snapshot_end": snapshot.ts.iloc[-1].isoformat(),
            "input_snapshot_rows": int(len(snapshot)),
            "comparison_csv": str(COMPARISON_PATH.relative_to(ROOT)),
            "trades_csv": str(TRADES_PATH.relative_to(ROOT)),
        },
        "primary_rows": primary_records,
        "asia_shanghai_start_sensitivity_rows": timezone_records,
        "continuous_state_rows": continuous_rows,
    }
    SUMMARY_PATH.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
            default=str,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    print(f"Wrote {SUMMARY_PATH}")
    print(f"Wrote {COMPARISON_PATH}")
    print(f"Wrote {TRADES_PATH}")
    print(f"Wrote {SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
