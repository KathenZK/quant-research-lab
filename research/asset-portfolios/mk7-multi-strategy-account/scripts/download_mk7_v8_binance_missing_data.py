"""Download Binance-only missing inputs for external mk7-v8 reproduction.

Writes under data/cache/mk7_v8_binance/. The recent-data REST endpoint for
topLongShortPositionRatio is limited to ~30 days, so full-history top_lsr_pos
comes from Binance Vision USD-M daily metrics archives.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import time
import zipfile
from http.client import IncompleteRead
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
CACHE = ROOT / "data/cache/mk7_v8_binance"
AGG_DIR = CACHE / "aggTrades" / "HYPEUSDT"
FEATURE_DIR = CACHE / "features"
PREMIUM_DIR = CACHE / "premium"
LSR_DIR = CACHE / "top_lsr"
KLINES_DIR = CACHE / "klines"
LOG_DIR = CACHE / "logs"

FAPI = "https://fapi.binance.com"
VISION = "https://data.binance.vision"
UA = "quant-research-lab-mk7-v8-data/0.1"

MID_LO = 2_000.0
MID_HI = 20_000.0
WINDOW_START = pd.Timestamp("2025-05-30T00:00:00Z")
WINDOW_END = pd.Timestamp("2026-07-02T03:00:00Z")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--since", default=str(WINDOW_START))
    p.add_argument("--until", default=str(WINDOW_END))
    p.add_argument("--skip-aggtrades", action="store_true")
    p.add_argument("--only-aggtrades", action="store_true")
    p.add_argument("--only-top-lsr", action="store_true")
    p.add_argument("--timeout", type=float, default=60.0)
    return p.parse_args()


def request_bytes(url: str, *, timeout: float, attempts: int = 8) -> bytes:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return resp.read()
        except HTTPError as exc:
            last = exc
            if exc.code == 404:
                raise
            time.sleep(min(12.0, 0.75 * 2**attempt))
        except (URLError, TimeoutError, IncompleteRead, ConnectionError) as exc:
            last = exc
            time.sleep(min(12.0, 0.75 * 2**attempt))
    raise RuntimeError(f"request failed: {url}") from last


def request_json(url: str, *, timeout: float) -> Any:
    return json.loads(request_bytes(url, timeout=timeout).decode("utf-8"))


def ms(ts: pd.Timestamp) -> int:
    return int(pd.Timestamp(ts).tz_convert("UTC").timestamp() * 1000)


def fetch_paginated_klines(
    path: str,
    *,
    symbol: str,
    interval: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    timeout: float,
) -> pd.DataFrame:
    rows: list[list[Any]] = []
    cursor = ms(start)
    end_ms = ms(end)
    while cursor < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": cursor,
            "endTime": end_ms,
            "limit": 1500,
        }
        url = f"{FAPI}{path}?{urlencode(params)}"
        batch = request_json(url, timeout=timeout)
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        nxt = int(batch[-1][0]) + 1
        if nxt <= cursor:
            break
        cursor = nxt
        if len(batch) < 1500:
            break
        time.sleep(0.05)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(
        rows,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trade_count",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ],
    )
    frame["ts"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    for col in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_base",
        "taker_buy_quote",
    ]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.loc[frame["ts"] < end].copy()
    return (
        frame.drop_duplicates("ts", keep="last")
        .sort_values("ts")
        .reset_index(drop=True)
    )


def download_premium(since: pd.Timestamp, until: pd.Timestamp, timeout: float) -> Path:
    frame = fetch_paginated_klines(
        "/fapi/v1/premiumIndexKlines",
        symbol="HYPEUSDT",
        interval="15m",
        start=since,
        end=until,
        timeout=timeout,
    )
    out = PREMIUM_DIR / "hype_usdt_premium_index_15m.parquet"
    frame.to_parquet(out, index=False)
    return out


def download_klines_with_taker(
    symbol: str,
    interval: str,
    since: pd.Timestamp,
    until: pd.Timestamp,
    timeout: float,
) -> Path:
    frame = fetch_paginated_klines(
        "/fapi/v1/klines",
        symbol=symbol,
        interval=interval,
        start=since,
        end=until,
        timeout=timeout,
    )
    out = KLINES_DIR / f"{symbol.lower()}_{interval}_with_taker.parquet"
    frame.to_parquet(out, index=False)
    return out


def metric_daterange(since: pd.Timestamp, until: pd.Timestamp) -> list[pd.Timestamp]:
    start = pd.Timestamp(since).tz_convert("UTC").normalize()
    last = (pd.Timestamp(until).tz_convert("UTC") - pd.Timedelta(nanoseconds=1)).normalize()
    days: list[pd.Timestamp] = []
    cur = start
    while cur <= last:
        days.append(cur)
        cur += pd.Timedelta(days=1)
    return days


def download_top_lsr(
    since: pd.Timestamp, until: pd.Timestamp, timeout: float
) -> tuple[Path, dict[str, Any]]:
    """Download 5m top-trader position ratio from Binance Vision daily metrics."""
    frames: list[pd.DataFrame] = []
    missing: list[str] = []
    days = metric_daterange(since, until)
    for i, day in enumerate(days, start=1):
        stamp = day.strftime("%Y-%m-%d")
        url = (
            f"{VISION}/data/futures/um/daily/metrics/HYPEUSDT/"
            f"HYPEUSDT-metrics-{stamp}.zip"
        )
        try:
            payload = request_bytes(url, timeout=timeout)
        except HTTPError as exc:
            if exc.code != 404:
                raise
            missing.append(stamp)
            continue
        with zipfile.ZipFile(BytesIO(payload)) as zf:
            bad = zf.testzip()
            if bad is not None:
                raise RuntimeError(f"corrupt metrics zip member {bad} on {stamp}")
            names = [name for name in zf.namelist() if name.endswith(".csv")]
            if len(names) != 1:
                raise RuntimeError(f"unexpected metrics archive members on {stamp}: {names}")
            with zf.open(names[0]) as handle:
                daily = pd.read_csv(handle)
        required = {
            "create_time",
            "symbol",
            "count_toptrader_long_short_ratio",
            "sum_toptrader_long_short_ratio",
        }
        absent = required - set(daily.columns)
        if absent:
            raise RuntimeError(f"metrics columns missing on {stamp}: {sorted(absent)}")
        frames.append(daily)
        if i % 50 == 0 or i == len(days):
            print(
                f"  top_lsr progress {i}/{len(days)} "
                f"downloaded={len(frames)} missing={len(missing)}"
            )
        time.sleep(0.02)
    if missing:
        raise RuntimeError(f"missing Binance Vision metrics days: {missing[:10]}")
    if not frames:
        raise RuntimeError("Binance Vision metrics returned no rows")
    frame = pd.concat(frames, ignore_index=True)
    frame["ts"] = pd.to_datetime(frame["create_time"], utc=True)
    numeric = [
        "sum_open_interest",
        "sum_open_interest_value",
        "count_toptrader_long_short_ratio",
        "sum_toptrader_long_short_ratio",
        "count_long_short_ratio",
        "sum_taker_long_short_vol_ratio",
    ]
    for col in numeric:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["top_lsr_pos"] = frame["sum_toptrader_long_short_ratio"]
    frame["source_create_time"] = frame["ts"]
    floored = frame["ts"].dt.floor("5min")
    offgrid_source_timestamps = int(frame["ts"].ne(floored).sum())
    # Vision create_time occasionally carries 1-45 seconds of collector lag.
    # The metric itself is a 5m observation; normalize it to its period timestamp,
    # matching the REST endpoint's exact 5m timestamp convention.
    frame["ts"] = floored
    frame = (
        frame.loc[(frame["ts"] >= since) & (frame["ts"] < until)]
        .drop_duplicates("ts", keep="last")
        .sort_values("ts")
        .reset_index(drop=True)
    )
    null_top_lsr_rows = int(frame["top_lsr_pos"].isna().sum())
    frame = frame.dropna(subset=["top_lsr_pos"]).reset_index(drop=True)
    if frame.empty:
        raise RuntimeError("top_lsr_pos archive is empty after dropping null points")
    out = LSR_DIR / "hype_usdt_top_lsr_pos_5m.parquet"
    frame.to_parquet(out, index=False)
    expected = pd.date_range(frame["ts"].iloc[0], frame["ts"].iloc[-1], freq="5min")
    missing_ts = expected.difference(pd.DatetimeIndex(frame["ts"]))
    meta = {
        "source": "binance_vision_usdm_daily_metrics",
        "source_column": "sum_toptrader_long_short_ratio",
        "mapped_column": "top_lsr_pos",
        "rows": int(len(frame)),
        "first_ts": str(frame["ts"].iloc[0]),
        "last_ts": str(frame["ts"].iloc[-1]),
        "days_expected": len(days),
        "days_downloaded": len(frames),
        "days_missing": missing,
        "offgrid_source_timestamps_normalized": offgrid_source_timestamps,
        "null_top_lsr_rows_dropped": null_top_lsr_rows,
        "five_minute_gaps": int(len(missing_ts)),
        "note": (
            "sum_toptrader_long_short_ratio is the archived top-trader "
            "position-size long/short ratio; count_toptrader_long_short_ratio "
            "is the account-count ratio and is not used by mk7-v8."
        ),
    }
    (LSR_DIR / "hype_usdt_top_lsr_pos_5m.meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return out, meta


def daterange(since: pd.Timestamp, until: pd.Timestamp) -> list[pd.Timestamp]:
    start = pd.Timestamp(since).tz_convert("UTC").normalize()
    end = pd.Timestamp(until).tz_convert("UTC").normalize()
    days = []
    cur = start
    while cur < end:
        days.append(cur)
        cur += pd.Timedelta(days=1)
    return days


def download_aggtrade_day(day: pd.Timestamp, timeout: float) -> Path | None:
    stamp = day.strftime("%Y-%m-%d")
    out = AGG_DIR / f"HYPEUSDT-aggTrades-{stamp}.zip"
    if out.exists() and out.stat().st_size > 0:
        try:
            with zipfile.ZipFile(out) as zf:
                if zf.testzip() is None:
                    return out
        except zipfile.BadZipFile:
            out.unlink(missing_ok=True)
    url = (
        f"{VISION}/data/futures/um/daily/aggTrades/HYPEUSDT/"
        f"HYPEUSDT-aggTrades-{stamp}.zip"
    )
    try:
        payload = request_bytes(url, timeout=timeout)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    tmp = out.with_suffix(".zip.partial")
    tmp.write_bytes(payload)
    with zipfile.ZipFile(tmp) as zf:
        bad = zf.testzip()
        if bad is not None:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"corrupt zip member {bad} in {stamp}")
    tmp.replace(out)
    return out


def aggregate_aggtrades_to_15m(timeout: float) -> Path:
    """Build single-venue Binance mid/big CVD and net/total taker flow on 15m bars."""
    zips = sorted(AGG_DIR.glob("HYPEUSDT-aggTrades-*.zip"))
    if not zips:
        raise RuntimeError("no aggTrade zips downloaded")
    chunks: list[pd.DataFrame] = []
    for path in zips:
        with zipfile.ZipFile(path) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as handle:
                raw = pd.read_csv(handle)
        # Vision schema: agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker
        cols = {c.lower(): c for c in raw.columns}
        price = pd.to_numeric(raw[cols.get("price", "price")], errors="coerce")
        qty = pd.to_numeric(raw[cols.get("quantity", "quantity")], errors="coerce")
        ts = pd.to_datetime(
            raw[cols.get("transact_time", "transact_time")], unit="ms", utc=True
        )
        maker = raw[cols.get("is_buyer_maker", "is_buyer_maker")].astype(str).str.lower().isin(
            {"true", "1"}
        )
        quote = price * qty
        # is_buyer_maker True => sell aggressor; False => buy aggressor
        buy_quote = np.where(~maker, quote, 0.0)
        sell_quote = np.where(maker, quote, 0.0)
        mid_mask = (quote >= MID_LO) & (quote < MID_HI)
        big_mask = quote >= MID_HI
        part = pd.DataFrame(
            {
                "ts": ts,
                "buy_quote": buy_quote,
                "sell_quote": sell_quote,
                "mid_buy": np.where(mid_mask, buy_quote, 0.0),
                "mid_sell": np.where(mid_mask, sell_quote, 0.0),
                "big_buy": np.where(big_mask, buy_quote, 0.0),
                "big_sell": np.where(big_mask, sell_quote, 0.0),
            }
        )
        part = part.dropna(subset=["ts"]).set_index("ts").sort_index()
        bar = part.resample("15min", label="left", closed="left").sum(min_count=1)
        chunks.append(bar)
    frame = pd.concat(chunks).groupby(level=0).sum(min_count=1).sort_index()
    frame["net_flow"] = frame["buy_quote"] - frame["sell_quote"]
    frame["total_flow"] = frame["buy_quote"] + frame["sell_quote"]
    frame["mid_imb"] = (frame["mid_buy"] - frame["mid_sell"]) / (
        frame["mid_buy"] + frame["mid_sell"]
    ).replace(0.0, np.nan)
    frame["big_imb"] = (frame["big_buy"] - frame["big_sell"]) / (
        frame["big_buy"] + frame["big_sell"]
    ).replace(0.0, np.nan)
    frame["cvd_all"] = frame["net_flow"].cumsum()
    frame["cvd_mid"] = (frame["mid_buy"] - frame["mid_sell"]).cumsum()
    frame["cvd_big"] = (frame["big_buy"] - frame["big_sell"]).cumsum()
    out = FEATURE_DIR / "hype_usdt_15m_cvd_flow_single_venue.parquet"
    frame.reset_index().rename(columns={"index": "ts"}).to_parquet(out, index=False)
    return out


def human_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f}{unit}"
        value /= 1024
    return f"{n}B"


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def main() -> None:
    args = parse_args()
    since = pd.Timestamp(args.since)
    until = pd.Timestamp(args.until)
    if since.tzinfo is None:
        since = since.tz_localize("UTC")
    if until.tzinfo is None:
        until = until.tz_localize("UTC")
    for path in (AGG_DIR, FEATURE_DIR, PREMIUM_DIR, LSR_DIR, KLINES_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "exchange": "binance",
        "market_type": "perp",
        "venue_assumption": "single_binance_usdm",
        "window": {"since": str(since), "until": str(until)},
        "estimates": {
            "aggTrades_zip_total": "~1.8-2.2GB compressed (~5MB/day * ~400 days)",
            "aggTrades_csv_uncompressed": "~8-12GB",
            "15m_cvd_flow_features": "~5-20MB parquet",
            "premium_15m": "~2-5MB",
            "top_lsr_5m": "~5-15MB (Binance Vision daily metrics)",
            "hype_1m_with_taker": "~40-80MB",
            "btc_15m_with_taker": "~3-8MB",
        },
        "outputs": {},
        "blockers": [],
    }

    if not args.only_aggtrades and not args.only_top_lsr:
        print("downloading premiumIndexKlines 15m...")
        path = download_premium(since, until, args.timeout)
        summary["outputs"]["premium_15m"] = {
            "path": str(path.relative_to(ROOT)),
            "rows": int(len(pd.read_parquet(path))),
            "bytes": path.stat().st_size,
        }
    if not args.only_aggtrades:
        print("downloading top trader position ratio 5m (Binance Vision daily metrics)...")
        path, meta = download_top_lsr(since, until, args.timeout)
        summary["outputs"]["top_lsr_5m"] = {
            "path": str(path.relative_to(ROOT)),
            "rows": meta["rows"],
            "bytes": path.stat().st_size,
            "meta": meta,
        }
    if not args.only_aggtrades and not args.only_top_lsr:
        print("downloading HYPE 1m klines with taker_buy...")
        path = download_klines_with_taker("HYPEUSDT", "1m", since, until, args.timeout)
        summary["outputs"]["hype_1m_taker"] = {
            "path": str(path.relative_to(ROOT)),
            "rows": int(len(pd.read_parquet(path))),
            "bytes": path.stat().st_size,
        }
        print("downloading HYPE 15m klines with taker_buy...")
        path = download_klines_with_taker("HYPEUSDT", "15m", since, until, args.timeout)
        summary["outputs"]["hype_15m_taker"] = {
            "path": str(path.relative_to(ROOT)),
            "rows": int(len(pd.read_parquet(path))),
            "bytes": path.stat().st_size,
        }
        print("downloading BTC 15m klines with taker_buy...")
        path = download_klines_with_taker("BTCUSDT", "15m", since, until, args.timeout)
        summary["outputs"]["btc_15m_taker"] = {
            "path": str(path.relative_to(ROOT)),
            "rows": int(len(pd.read_parquet(path))),
            "bytes": path.stat().st_size,
        }

    if not args.skip_aggtrades and not args.only_top_lsr:
        days = daterange(since, until)
        print(f"downloading HYPE aggTrades daily zips: {len(days)} days...")
        ok = 0
        missing: list[str] = []
        for i, day in enumerate(days, start=1):
            path = download_aggtrade_day(day, args.timeout)
            stamp = day.strftime("%Y-%m-%d")
            if path is None:
                missing.append(stamp)
                print(f"  missing {stamp}")
            else:
                ok += 1
            if i % 20 == 0 or i == len(days):
                print(
                    f"  progress {i}/{len(days)} ok={ok} bytes={human_bytes(dir_size(AGG_DIR))}"
                )
            time.sleep(0.05)
        summary["outputs"]["aggTrades_zips"] = {
            "dir": str(AGG_DIR.relative_to(ROOT)),
            "days_ok": ok,
            "days_missing": missing,
            "bytes": dir_size(AGG_DIR),
        }
        print("aggregating 15m CVD/flow features from aggTrades...")
        path = aggregate_aggtrades_to_15m(args.timeout)
        summary["outputs"]["cvd_flow_15m"] = {
            "path": str(path.relative_to(ROOT)),
            "rows": int(len(pd.read_parquet(path))),
            "bytes": path.stat().st_size,
            "formula_note": (
                "single Binance USDM venue; mid=2k-20k quote, big>=20k; "
                "imb=(buy-sell)/(buy+sell); flow uses all-size taker quote."
            ),
        }

    summary["cache_bytes_total"] = dir_size(CACHE)
    summary["cache_bytes_human"] = human_bytes(dir_size(CACHE))
    out = LOG_DIR / "download_summary.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
