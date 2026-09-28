from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import numpy as np
import pandas as pd


FAMILY_DIR = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
MEMBERSHIP_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_membership_daily.parquet"
CONFIG_PATH = (
    FAMILY_DIR
    / "configs/ndx100-1d-ma7-regime-continuation-yahoo-current-y0.json"
)
CACHE_DIR = ARTIFACT_DIR / "yahoo-current-cache" / "chart"
UNIVERSE_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_y0_current_universe.csv"
PRICE_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_y0_yahoo_prices.parquet"
AUDIT_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_y0_yahoo_price_audit.json"
MANIFEST_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_y0_yahoo_data_manifest.json"

STUDY_ID = "NDX100-1D-MA7-RC-Y0"
ENDPOINT = "https://query2.finance.yahoo.com/v8/finance/chart"
USER_AGENT = "Mozilla/5.0 quant-research-lab-ndx100-yahoo/1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Yahoo daily bars for the frozen current Nasdaq-100 snapshot."
    )
    parser.add_argument("--force", action="store_true", help="Replace raw caches.")
    parser.add_argument(
        "--limit",
        type=int,
        help="Smoke-test only: fetch the first N current securities plus QQQ.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.45,
        help="Minimum delay after each uncached request.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def epoch(date_value: str) -> int:
    return int(pd.Timestamp(date_value, tz="UTC").timestamp())


def load_config() -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if config.get("study_id") != STUDY_ID:
        raise RuntimeError("unexpected Yahoo observation config")
    if not config["universe"].get("survivorship_bias"):
        raise RuntimeError("Yahoo current-universe diagnostic must declare survivorship bias")
    if config["research_contract"].get("parameter_search") is not False:
        raise RuntimeError("parameter search must remain disabled")
    return config


def current_universe() -> pd.DataFrame:
    membership = pd.read_parquet(
        MEMBERSHIP_PATH, columns=["session_date", "ticker", "entity_key"]
    )
    terminal = pd.Timestamp(membership["session_date"].max())
    universe = (
        membership.loc[
            pd.to_datetime(membership["session_date"]).eq(terminal),
            ["ticker", "entity_key"],
        ]
        .drop_duplicates()
        .sort_values(["ticker", "entity_key"])
        .reset_index(drop=True)
    )
    universe.insert(0, "terminal_snapshot_session", terminal.date().isoformat())
    universe["universe_role"] = "current_constituent_retroactive"
    universe["survivorship_bias"] = True
    return universe


def yahoo_request(
    ticker: str,
    *,
    start: str,
    end_inclusive: str,
    force: bool,
    sleep_seconds: float,
    attempts: int = 7,
) -> tuple[dict[str, Any], bool]:
    cache_path = CACHE_DIR / f"{ticker}_{start}_{end_inclusive}_1d.json"
    if cache_path.exists() and not force:
        return json.loads(cache_path.read_text(encoding="utf-8")), True

    end_exclusive = (pd.Timestamp(end_inclusive) + pd.Timedelta(days=1)).date().isoformat()
    params = urllib.parse.urlencode(
        {
            "period1": epoch(start),
            "period2": epoch(end_exclusive),
            "interval": "1d",
            "includePrePost": "false",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        }
    )
    url = f"{ENDPOINT}/{urllib.parse.quote(ticker)}?{params}"
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read())
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            write_json(cache_path, payload)
            time.sleep(max(sleep_seconds, 0.0))
            return payload, False
        except urllib.error.HTTPError as error:
            last_error = error
            retriable = error.code == 429 or 500 <= error.code < 600
            if not retriable or attempt == attempts - 1:
                break
            retry_after = error.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else min(2 ** (attempt + 1), 60)
            time.sleep(wait)
        except urllib.error.URLError as error:
            last_error = error
            if attempt == attempts - 1:
                break
            time.sleep(min(2 ** (attempt + 1), 60))
    raise RuntimeError(f"Yahoo request failed for {ticker}: {last_error}")


def split_events(result: dict[str, Any]) -> list[dict[str, Any]]:
    events = (result.get("events") or {}).get("splits") or {}
    output: list[dict[str, Any]] = []
    for event in events.values():
        numerator = float(event.get("numerator") or 0.0)
        denominator = float(event.get("denominator") or 0.0)
        if numerator <= 0 or denominator <= 0:
            ratio_text = str(event.get("splitRatio") or "")
            if ":" in ratio_text:
                left, right = ratio_text.split(":", 1)
                numerator, denominator = float(left), float(right)
        if numerator <= 0 or denominator <= 0:
            raise RuntimeError(f"invalid Yahoo split event: {event}")
        output.append(
            {
                "timestamp": int(event["date"]),
                "ratio": numerator / denominator,
                "split_ratio": event.get("splitRatio"),
            }
        )
    return sorted(output, key=lambda item: item["timestamp"])


def parse_chart(ticker: str, payload: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise RuntimeError(f"Yahoo chart error for {ticker}: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        return pd.DataFrame(), {"ticker": ticker, "no_result": True}
    result = results[0]
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []
    if not timestamps or not quotes:
        return pd.DataFrame(), {"ticker": ticker, "no_result": True}
    quote = quotes[0]
    size = len(timestamps)
    for field in ("open", "high", "low", "close", "volume"):
        if len(quote.get(field) or []) != size:
            raise RuntimeError(f"Yahoo {ticker} length mismatch for {field}")
    adjclose_sets = indicators.get("adjclose") or []
    adjclose = adjclose_sets[0].get("adjclose") if adjclose_sets else [None] * size
    if len(adjclose) != size:
        adjclose = [None] * size

    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "ticker": ticker,
            "raw_open": quote["open"],
            "raw_high": quote["high"],
            "raw_low": quote["low"],
            "raw_close": quote["close"],
            "raw_volume": quote["volume"],
            "yahoo_adj_close": adjclose,
        }
    )
    exchange_tz = (result.get("meta") or {}).get("exchangeTimezoneName")
    if not exchange_tz:
        exchange_tz = "America/New_York"
    frame["session_date"] = (
        pd.to_datetime(frame["timestamp"], unit="s", utc=True)
        .dt.tz_convert(exchange_tz)
        .dt.tz_localize(None)
        .dt.normalize()
    )

    splits = split_events(result)
    split_factor = np.ones(len(frame), dtype=float)
    timestamp_array = frame["timestamp"].to_numpy(dtype=np.int64)
    for event in splits:
        split_factor[timestamp_array < event["timestamp"]] *= event["ratio"]
    frame["split_factor"] = split_factor
    for field in ("open", "high", "low", "close"):
        frame[field] = frame[f"raw_{field}"] / frame["split_factor"]
    frame["volume"] = frame["raw_volume"] * frame["split_factor"]
    null_core = frame[["open", "high", "low", "close", "volume"]].isna().any(axis=1)
    usable = frame.loc[~null_core].copy()
    diagnostics = {
        "ticker": ticker,
        "exchange_timezone": exchange_tz,
        "raw_rows": int(len(frame)),
        "null_core_rows_dropped": int(null_core.sum()),
        "usable_rows": int(len(usable)),
        "first_session": None if usable.empty else usable["session_date"].min(),
        "last_session": None if usable.empty else usable["session_date"].max(),
        "split_event_count": len(splits),
        "dividend_event_count": len((result.get("events") or {}).get("dividends") or {}),
        "meta_symbol": (result.get("meta") or {}).get("symbol"),
        "exchange_name": (result.get("meta") or {}).get("fullExchangeName"),
    }
    return usable, diagnostics


def main() -> int:
    args = parse_args()
    config = load_config()
    universe = current_universe()
    if args.limit is not None:
        if args.limit <= 0:
            raise SystemExit("--limit must be positive")
        universe = universe.head(args.limit).copy()
    UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    universe.to_csv(UNIVERSE_PATH, index=False)

    start = config["data"]["fetch_start_inclusive"]
    end = config["data"]["study_end_inclusive"]
    tickers = sorted(set(universe["ticker"].astype(str)) | {"QQQ"})
    frames: list[pd.DataFrame] = []
    per_ticker: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    cached_requests = 0
    downloaded_requests = 0
    for ticker in tickers:
        try:
            payload, from_cache = yahoo_request(
                ticker,
                start=start,
                end_inclusive=end,
                force=args.force,
                sleep_seconds=args.sleep_seconds,
            )
            cached_requests += int(from_cache)
            downloaded_requests += int(not from_cache)
            frame, diagnostic = parse_chart(ticker, payload)
            diagnostic["from_cache"] = from_cache
            per_ticker.append(diagnostic)
            if not frame.empty:
                frames.append(frame)
        except Exception as error:  # preserve the rest of the audit surface
            failures.append({"ticker": ticker, "error": str(error)})

    if not frames:
        raise RuntimeError("Yahoo returned no usable price frames")
    prices = pd.concat(frames, ignore_index=True).sort_values(
        ["ticker", "session_date"]
    )
    duplicate_rows = prices.duplicated(["ticker", "session_date"], keep=False)
    invalid_ohlcv = (
        prices[["open", "high", "low", "close", "volume"]].isna().any(axis=1)
        | prices[["open", "high", "low", "close"]].le(0).any(axis=1)
        | prices["volume"].lt(0)
        | prices["high"].lt(prices[["open", "close", "low"]].max(axis=1))
        | prices["low"].gt(prices[["open", "close", "high"]].min(axis=1))
    )
    calendar = xcals.get_calendar("XNAS")
    sessions = pd.DatetimeIndex(
        calendar.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
    ).tz_localize(None)
    out_of_session = ~prices["session_date"].isin(sessions)
    internal_missing: dict[str, list[str]] = {}
    for ticker, group in prices.groupby("ticker", sort=True):
        observed = pd.DatetimeIndex(group["session_date"].unique())
        expected = sessions[(sessions >= observed.min()) & (sessions <= observed.max())]
        missing = expected.difference(observed)
        internal_missing[ticker] = missing.strftime("%Y-%m-%d").tolist()
    for diagnostic in per_ticker:
        missing = internal_missing.get(str(diagnostic["ticker"]), [])
        diagnostic["internal_missing_session_count"] = len(missing)
        diagnostic["first_internal_missing_sessions"] = missing[:10]
    prices.to_parquet(PRICE_PATH, index=False)

    diagnostics = pd.DataFrame(per_ticker)
    universe_tickers = set(universe["ticker"].astype(str))
    usable_tickers = set(prices["ticker"].astype(str))
    no_usable_universe = sorted(universe_tickers - usable_tickers)
    study_start = pd.Timestamp(config["data"]["study_start_inclusive"])
    insufficient_warmup = sorted(
        diagnostics.loc[
            diagnostics["ticker"].isin(universe_tickers)
            & pd.to_datetime(diagnostics["first_session"]).gt(study_start),
            "ticker",
        ].astype(str)
    )
    audit = {
        "study_id": STUDY_ID,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "status": "FETCH_COMPLETE_WITH_LIMITATIONS" if failures or no_usable_universe else "FETCH_COMPLETE",
        "source": "yahoo_finance_chart_query2",
        "credential_required": False,
        "current_snapshot_session": universe["terminal_snapshot_session"].iloc[0],
        "survivorship_bias": True,
        "universe_security_count": int(len(universe)),
        "requested_ticker_count_including_qqq": len(tickers),
        "usable_ticker_count_including_qqq": int(prices["ticker"].nunique()),
        "rows": int(len(prices)),
        "first_session": prices["session_date"].min(),
        "last_session": prices["session_date"].max(),
        "cached_requests": cached_requests,
        "downloaded_requests": downloaded_requests,
        "request_failures": failures,
        "current_universe_without_usable_data": no_usable_universe,
        "current_universe_starting_after_study_start": insufficient_warmup,
        "duplicate_ticker_session_rows": int(duplicate_rows.sum()),
        "invalid_ohlcv_rows": int(invalid_ohlcv.sum()),
        "out_of_xnas_session_rows": int(out_of_session.sum()),
        "tickers_with_internal_missing_sessions": sorted(
            ticker for ticker, missing in internal_missing.items() if missing
        ),
        "internal_missing_session_count": int(
            sum(len(missing) for missing in internal_missing.values())
        ),
        "price_adjustment": "split-only from Yahoo split events; yahoo_adj_close retained only for diagnostics",
        "dividends_in_primary_prices": False,
        "per_ticker": per_ticker,
        "blockers_for_full_current_universe_study": [
            item
            for item, blocked in (
                ("Yahoo request failures", bool(failures)),
                ("current constituent without usable Yahoo daily data", bool(no_usable_universe)),
                ("duplicate ticker/session rows", bool(duplicate_rows.any())),
                ("invalid adjusted OHLCV rows", bool(invalid_ohlcv.any())),
                ("daily rows outside XNAS calendar", bool(out_of_session.any())),
            )
            if blocked
        ],
    }
    write_json(AUDIT_PATH, audit)
    manifest = {
        "study_id": STUDY_ID,
        "generated_at_utc": audit["generated_at_utc"],
        "files": {
            str(CONFIG_PATH.relative_to(FAMILY_DIR)): sha256_file(CONFIG_PATH),
            str(UNIVERSE_PATH.relative_to(FAMILY_DIR)): sha256_file(UNIVERSE_PATH),
            str(PRICE_PATH.relative_to(FAMILY_DIR)): sha256_file(PRICE_PATH),
            str(AUDIT_PATH.relative_to(FAMILY_DIR)): sha256_file(AUDIT_PATH),
        },
        "raw_cache_file_count": len(list(CACHE_DIR.glob("*.json"))),
        "raw_cache_sha256": {
            path.name: sha256_file(path) for path in sorted(CACHE_DIR.glob("*.json"))
        },
    }
    write_json(MANIFEST_PATH, manifest)
    print(json.dumps({key: audit[key] for key in audit if key != "per_ticker"}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
