from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from http.client import IncompleteRead
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-regime-continuation"
INVENTORY_PATH = FAMILY_DIR / "artifacts/binance_1d_ma7_rc_p0_universe_inventory.csv"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
ARCHIVE_ROOT = ROOT / "data/raw/_archives/binance/futures/um/monthly"
RAW_ROOT = ROOT / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
NORMALIZED_ROOT = (
    ROOT / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
)

VISION = "https://data.binance.vision"
FAPI = "https://fapi.binance.com"
USER_AGENT = "quant-research-lab-bin-1d-ma7-rc-p3-sync/0.1"
SOURCE_VISION = "binance_vision_kline_monthly"
SOURCE_API = "binance_futures_kline_api"
JULY_MONTH = "2026-07"
AUGUST_START = pd.Timestamp("2026-08-01T00:00:00Z")
CUTOFF = pd.Timestamp("2026-08-25T00:00:00Z")
KLINE_COLUMNS = [
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


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    symbol: str
    archive_path: str
    archive_sha256: str
    archive_bytes: int
    rows: int


class RateLimiter:
    def __init__(self, calls_per_second: float) -> None:
        self.interval = 1.0 / calls_per_second
        self.lock = threading.Lock()
        self.next_allowed = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_allowed - now)
            self.next_allowed = max(now, self.next_allowed) + self.interval
        if delay:
            time.sleep(delay)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extend the BIN-1D-MA7-RC data lake through the frozen P3 cutoff. "
            "July uses checksum-verified Binance Vision monthly 15m archives; "
            "August uses closed Binance FAPI 15m bars."
        )
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--api-workers", type=int, default=8)
    parser.add_argument("--api-calls-per-second", type=float, default=3.5)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--attempts", type=int, default=7)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--july-only", action="store_true")
    parser.add_argument("--august-only", action="store_true")
    return parser.parse_args()


def request_bytes(
    url: str,
    *,
    timeout: float,
    attempts: int,
    rate_limiter: RateLimiter | None = None,
) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            if rate_limiter is not None:
                rate_limiter.wait()
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise
            if exc.code not in {418, 429, 500, 502, 503, 504}:
                raise
            last_error = exc
        except (URLError, TimeoutError, IncompleteRead, ConnectionError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(20.0, 0.75 * 2**attempt))
    raise RuntimeError(f"request failed after {attempts} attempts: {url}") from last_error


def request_json(
    path: str,
    params: dict[str, Any] | None,
    *,
    timeout: float,
    attempts: int,
    rate_limiter: RateLimiter | None = None,
) -> Any:
    query = f"?{urlencode(params)}" if params else ""
    return json.loads(
        request_bytes(
            f"{FAPI}{path}{query}",
            timeout=timeout,
            attempts=attempts,
            rate_limiter=rate_limiter,
        )
    )


def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def canonical_symbol(archive_symbol: pd.Series) -> pd.Series:
    return archive_symbol.str.removesuffix("USDT") + "/USDT:USDT"


def parse_kline_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.shape[1] != len(KLINE_COLUMNS):
        raise RuntimeError(f"unexpected kline column count: {frame.shape[1]}")
    frame = frame.copy()
    frame.columns = KLINE_COLUMNS
    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="coerce")
    frame = frame.loc[frame["open_time"].notna()].copy()
    frame["close_time"] = pd.to_numeric(frame["close_time"], errors="coerce")
    for column in KLINE_COLUMNS[1:6] + KLINE_COLUMNS[7:11]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["ignore"] = pd.to_numeric(frame["ignore"], errors="coerce")
    frame["trade_count"] = frame["trade_count"].astype("Int64")
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    return frame.reset_index(drop=True)


def normalize(raw: pd.DataFrame, source: str) -> pd.DataFrame:
    frame = raw.copy()
    frame["ts"] = frame["open_time"]
    frame["exchange"] = "binance"
    frame["symbol"] = canonical_symbol(frame["archive_symbol"])
    frame["market_type"] = "perp"
    frame["timeframe"] = "15m"
    frame["base_asset"] = frame["archive_symbol"].str.removesuffix("USDT")
    frame["quote_asset"] = "USDT"
    frame["is_closed"] = True
    frame["source"] = source
    frame["vwap"] = frame["quote_volume"] / frame["volume"].replace(0.0, np.nan)
    frame["vwap"] = frame["vwap"].fillna(frame["close"])
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
            "taker_buy_volume",
            "taker_buy_quote_volume",
            "vwap",
            "is_closed",
            "source",
        ]
    ]


def archive_paths(symbol: str) -> tuple[Path, str]:
    filename = f"{symbol}-15m-{JULY_MONTH}.zip"
    local = ARCHIVE_ROOT.joinpath(
        "klines",
        f"symbol={symbol.lower()}",
        "timeframe=15m",
        "year=2026",
        filename,
    )
    remote = (
        f"{VISION}/data/futures/um/monthly/klines/"
        f"{quote(symbol, safe='')}/15m/{quote(filename, safe='-._')}"
    )
    return local, remote


def checksum_value(text: str) -> str:
    value = text.strip().split()[0].lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise RuntimeError(f"invalid checksum sidecar: {text!r}")
    return value


def fetch_july_archive(
    symbol: str, *, timeout: float, attempts: int
) -> tuple[pd.DataFrame, ArchiveResult] | None:
    local, remote = archive_paths(symbol)
    try:
        sidecar = request_bytes(
            f"{remote}.CHECKSUM", timeout=timeout, attempts=attempts
        )
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    expected = checksum_value(sidecar.decode("utf-8"))
    local.parent.mkdir(parents=True, exist_ok=True)
    payload = local.read_bytes() if local.exists() else b""
    actual = hashlib.sha256(payload).hexdigest() if payload else ""
    if actual != expected:
        payload = request_bytes(remote, timeout=timeout, attempts=attempts)
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            raise RuntimeError(f"archive checksum mismatch: {symbol}")
        temporary = local.with_suffix(f"{local.suffix}.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, local)
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"corrupt archive member: {symbol} {bad_member}")
        members = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(members) != 1:
            raise RuntimeError(f"unexpected archive members: {symbol} {members}")
        with archive.open(members[0]) as handle:
            frame = pd.read_csv(handle, header=None, low_memory=False)
    frame = parse_kline_rows(frame)
    frame["archive_symbol"] = symbol
    return frame, ArchiveResult(
        symbol=symbol,
        archive_path=str(local.relative_to(ROOT)),
        archive_sha256=actual,
        archive_bytes=len(payload),
        rows=len(frame),
    )


def exchange_symbols(*, timeout: float, attempts: int) -> list[str]:
    payload = request_json(
        "/fapi/v1/exchangeInfo", None, timeout=timeout, attempts=attempts
    )
    symbols = []
    for item in payload["symbols"]:
        contract_type = str(item.get("contractType", ""))
        if (
            item.get("quoteAsset") == "USDT"
            and item.get("status") == "TRADING"
            and contract_type.endswith("PERPETUAL")
        ):
            symbols.append(str(item["symbol"]))
    return sorted(set(symbols))


def july_candidate_symbols(active: list[str]) -> list[str]:
    inventory = pd.read_csv(INVENTORY_PATH)
    historical = (
        inventory["base_asset"].astype(str).str.upper().add("USDT").tolist()
    )
    return sorted(set(historical) | set(active))


def sync_july(
    candidates: list[str], *, workers: int, timeout: float, attempts: int, force: bool
) -> dict[str, Any]:
    raw_path = RAW_ROOT / "source=binance_vision_monthly/month=2026-07/part-0000.parquet"
    normalized_path = (
        NORMALIZED_ROOT
        / "source=binance_vision_monthly/month=2026-07/part-0000.parquet"
    )
    marker_path = normalized_path.with_suffix(".complete.json")
    if raw_path.exists() and normalized_path.exists() and marker_path.exists() and not force:
        return json.loads(marker_path.read_text(encoding="utf-8")) | {
            "status": "existing"
        }

    frames: list[pd.DataFrame] = []
    results: list[ArchiveResult] = []
    failures: list[dict[str, str]] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                fetch_july_archive, symbol, timeout=timeout, attempts=attempts
            ): symbol
            for symbol in candidates
        }
        for future in as_completed(futures):
            symbol = futures[future]
            completed += 1
            try:
                value = future.result()
            except Exception as exc:  # noqa: BLE001
                failures.append({"symbol": symbol, "error": repr(exc)})
                continue
            if value is not None:
                frame, result = value
                frames.append(frame)
                results.append(result)
            if completed % 50 == 0:
                print(
                    f"july progress={completed}/{len(candidates)} archives={len(results)} "
                    f"failures={len(failures)}",
                    flush=True,
                )
    if failures:
        raise RuntimeError(f"July archive failures: {failures[:10]}")
    if not frames:
        raise RuntimeError("no July archives were found")
    raw = pd.concat(frames, ignore_index=True, sort=False)
    normalized = normalize(raw, SOURCE_VISION)
    normalized = normalized.loc[
        normalized["ts"].ge(pd.Timestamp("2026-07-01T00:00:00Z"))
        & normalized["ts"].lt(AUGUST_START)
    ].copy()
    if normalized.duplicated(["ts", "symbol"]).any():
        raise RuntimeError("July normalized rows contain duplicate keys")
    critical = normalized[
        ["ts", "symbol", "open", "high", "low", "close", "volume", "is_closed"]
    ].isna().any(axis=1)
    invalid = (
        normalized[["open", "high", "low", "close"]].le(0).any(axis=1)
        | normalized["volume"].lt(0)
        | normalized["high"].lt(normalized[["open", "close", "low"]].max(axis=1))
        | normalized["low"].gt(normalized[["open", "close", "high"]].min(axis=1))
    )
    if critical.any() or invalid.any():
        raise RuntimeError(
            f"July quality blockers: critical={int(critical.sum())} invalid={int(invalid.sum())}"
        )
    retained = normalized[["ts", "symbol"]].copy()
    raw["ts"] = raw["open_time"]
    raw["symbol"] = canonical_symbol(raw["archive_symbol"])
    raw = raw.merge(retained.assign(_retain=True), on=["ts", "symbol"], how="inner")
    raw = raw.drop(columns="_retain")
    atomic_parquet(raw.sort_values(["ts", "symbol"]), raw_path)
    atomic_parquet(normalized.sort_values(["ts", "symbol"]), normalized_path)
    manifest = {
        "phase": "july_vision",
        "status": "written",
        "candidate_symbols": len(candidates),
        "archive_symbols": len(results),
        "missing_archive_symbols": len(candidates) - len(results),
        "rows": len(normalized),
        "start_ts": normalized["ts"].min(),
        "end_ts": normalized["ts"].max(),
        "raw_path": str(raw_path.relative_to(ROOT)),
        "normalized_path": str(normalized_path.relative_to(ROOT)),
        "archives": [asdict(item) for item in sorted(results, key=lambda item: item.symbol)],
    }
    atomic_json(manifest, marker_path)
    return manifest


def fetch_api_symbol(
    symbol: str,
    *,
    timeout: float,
    attempts: int,
    rate_limiter: RateLimiter,
) -> pd.DataFrame:
    start_ms = int(AUGUST_START.timestamp() * 1000)
    end_ms = int(CUTOFF.timestamp() * 1000) - 1
    rows: list[list[Any]] = []
    cursor = start_ms
    while cursor <= end_ms:
        payload = request_json(
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": "15m",
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1500,
            },
            timeout=timeout,
            attempts=attempts,
            rate_limiter=rate_limiter,
        )
        if not payload:
            break
        rows.extend(payload)
        next_cursor = int(payload[-1][0]) + 15 * 60 * 1000
        if next_cursor <= cursor:
            raise RuntimeError(f"non-advancing API cursor for {symbol}")
        cursor = next_cursor
        if len(payload) < 1500:
            break
    if not rows:
        return pd.DataFrame(columns=[*KLINE_COLUMNS, "archive_symbol"])
    frame = parse_kline_rows(pd.DataFrame(rows))
    frame["archive_symbol"] = symbol
    frame = frame.loc[
        frame["open_time"].ge(AUGUST_START)
        & frame["open_time"].lt(CUTOFF)
        & frame["close_time"].lt(CUTOFF)
    ].copy()
    return frame.drop_duplicates("open_time", keep="last").reset_index(drop=True)


def existing_api_keys() -> pd.DataFrame:
    paths = sorted(NORMALIZED_ROOT.glob("date=2026-08-*/*.parquet"))
    frames: list[pd.DataFrame] = []
    for path in paths:
        try:
            frame = pd.read_parquet(path, columns=["ts", "symbol", "source"])
        except Exception:
            continue
        frame = frame.loc[frame["source"].eq(SOURCE_API), ["ts", "symbol"]]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["ts", "symbol"])
    result = pd.concat(frames, ignore_index=True)
    result["ts"] = pd.to_datetime(result["ts"], utc=True)
    return result.drop_duplicates(["ts", "symbol"])


def sync_august(
    active: list[str],
    *,
    workers: int,
    calls_per_second: float,
    timeout: float,
    attempts: int,
    force: bool,
) -> dict[str, Any]:
    raw_path = RAW_ROOT / "source=binance_futures_kline_api_p3/month=2026-08/part-0000.parquet"
    normalized_path = (
        NORMALIZED_ROOT
        / "source=binance_futures_kline_api_p3/month=2026-08/part-0000.parquet"
    )
    marker_path = normalized_path.with_suffix(".complete.json")
    if raw_path.exists() and normalized_path.exists() and marker_path.exists() and not force:
        return json.loads(marker_path.read_text(encoding="utf-8")) | {
            "status": "existing"
        }
    rate_limiter = RateLimiter(calls_per_second)
    frames: list[pd.DataFrame] = []
    failures: list[dict[str, str]] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                fetch_api_symbol,
                symbol,
                timeout=timeout,
                attempts=attempts,
                rate_limiter=rate_limiter,
            ): symbol
            for symbol in active
        }
        for future in as_completed(futures):
            symbol = futures[future]
            completed += 1
            try:
                frame = future.result()
            except Exception as exc:  # noqa: BLE001
                failures.append({"symbol": symbol, "error": repr(exc)})
                continue
            if not frame.empty:
                frames.append(frame)
            if completed % 25 == 0:
                print(
                    f"august progress={completed}/{len(active)} frames={len(frames)} "
                    f"failures={len(failures)}",
                    flush=True,
                )
    if failures:
        raise RuntimeError(f"August API failures: {failures[:10]}")
    raw = pd.concat(frames, ignore_index=True, sort=False)
    normalized = normalize(raw, SOURCE_API)
    legacy = existing_api_keys()
    legacy_overlap = 0
    if not legacy.empty:
        marked = normalized.merge(
            legacy.assign(_legacy=True), on=["ts", "symbol"], how="left"
        )
        legacy_overlap = int(marked["_legacy"].notna().sum())
        normalized = marked.loc[marked["_legacy"].isna()].drop(columns="_legacy")
    if normalized.duplicated(["ts", "symbol"]).any():
        raise RuntimeError("August normalized rows contain duplicate keys")
    critical = normalized[
        ["ts", "symbol", "open", "high", "low", "close", "volume", "is_closed"]
    ].isna().any(axis=1)
    invalid = (
        normalized[["open", "high", "low", "close"]].le(0).any(axis=1)
        | normalized["volume"].lt(0)
        | normalized["high"].lt(normalized[["open", "close", "low"]].max(axis=1))
        | normalized["low"].gt(normalized[["open", "close", "high"]].min(axis=1))
    )
    if critical.any() or invalid.any():
        raise RuntimeError(
            f"August quality blockers: critical={int(critical.sum())} invalid={int(invalid.sum())}"
        )
    retained = normalized[["ts", "symbol"]]
    raw["ts"] = raw["open_time"]
    raw["symbol"] = canonical_symbol(raw["archive_symbol"])
    raw = raw.merge(retained.assign(_retain=True), on=["ts", "symbol"], how="inner")
    raw = raw.drop(columns="_retain")
    atomic_parquet(raw.sort_values(["ts", "symbol"]), raw_path)
    atomic_parquet(normalized.sort_values(["ts", "symbol"]), normalized_path)
    manifest = {
        "phase": "august_api",
        "status": "written",
        "active_symbols": len(active),
        "symbols_with_rows": int(raw["archive_symbol"].nunique()),
        "rows_fetched": sum(len(frame) for frame in frames),
        "legacy_api_overlap_excluded": legacy_overlap,
        "rows_written": len(normalized),
        "start_ts": normalized["ts"].min(),
        "end_ts": normalized["ts"].max(),
        "raw_path": str(raw_path.relative_to(ROOT)),
        "normalized_path": str(normalized_path.relative_to(ROOT)),
    }
    atomic_json(manifest, marker_path)
    return manifest


def main() -> None:
    args = parse_args()
    if args.july_only and args.august_only:
        raise ValueError("--july-only and --august-only are mutually exclusive")
    active = exchange_symbols(timeout=args.timeout, attempts=args.attempts)
    candidates = july_candidate_symbols(active)
    print(
        f"active_usdt_perpetuals={len(active)} july_candidates={len(candidates)} "
        f"cutoff={CUTOFF.isoformat()}",
        flush=True,
    )
    manifest: dict[str, Any] = {
        "study_id": "BIN-1D-MA7-RC-P3",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "cutoff_exclusive_utc": CUTOFF.isoformat(),
    }
    if not args.august_only:
        manifest["july"] = sync_july(
            candidates,
            workers=args.workers,
            timeout=args.timeout,
            attempts=args.attempts,
            force=args.force,
        )
        print(
            f"july status={manifest['july']['status']} "
            f"symbols={manifest['july'].get('archive_symbols')} "
            f"rows={manifest['july'].get('rows')}",
            flush=True,
        )
    if not args.july_only:
        manifest["august"] = sync_august(
            active,
            workers=args.api_workers,
            calls_per_second=args.api_calls_per_second,
            timeout=args.timeout,
            attempts=args.attempts,
            force=args.force,
        )
        print(
            f"august status={manifest['august']['status']} "
            f"symbols={manifest['august'].get('symbols_with_rows')} "
            f"rows={manifest['august'].get('rows_written')}",
            flush=True,
        )
    output = ARTIFACT_DIR / "binance_1d_ma7_rc_p3_data_sync_manifest.json"
    atomic_json(manifest, output)
    print(f"manifest -> {output.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
