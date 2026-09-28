from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Sequence

import exchange_calendars as xcals
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/us-indexes/1d-nasdaq100-ma7-regime-continuation"
CONFIG_PATH = FAMILY_DIR / "configs/ndx100-1d-ma7-regime-continuation-p0.json"
MEMBERSHIP_PATH = (
    FAMILY_DIR / "artifacts/ndx100_1d_ma7_rc_p0_membership_daily.parquet"
)
INTERVAL_PATH = (
    FAMILY_DIR / "artifacts/ndx100_1d_ma7_rc_p0_membership_intervals.csv"
)
MEMBERSHIP_AUDIT_PATH = (
    FAMILY_DIR / "artifacts/ndx100_1d_ma7_rc_p0_membership_audit.json"
)
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
CACHE_DIR = ARTIFACT_DIR / "massive-cache"
EXPECTED_CONFIG_SHA256 = (
    "971706072f6faffe6ecbd3739a8b466b71568cce870d68c1ecb66ba216902af5"
)

STUDY_ID = "NDX100-1D-MA7-RC-P0"
FETCH_START = "2008-01-01"
HORIZONS = (1, 3, 5, 10, 20, 40)
MA_PERIODS = (5, 7, 10)
RETURN_METRICS = ("raw_return", "atr_return")
REGIME_VARIABLES = {
    "normalized_slope": "slope_q",
    "er20": "er_q",
    "rv_percentile": "rv_q",
}
RELIABLE_MIN_EVENTS = 100
RELIABLE_MIN_SECURITIES = 10
RELIABLE_MIN_DATES = 30
TEMPORAL_SPLIT = pd.Timestamp("2020-01-01")
USER_AGENT = "quant-research-lab-ndx100-ma7-regime/1.0"

BLOCKER_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_data_access_blocker.json"
ACCESS_AUDIT_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_massive_access_audit.json"
IDENTIFIER_MAP_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_identifier_map.csv"
IDENTIFIER_AUDIT_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_identifier_audit.json"
PRICE_AUDIT_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_price_audit.json"
EVENT_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_events.parquet"
EDGE_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_regime_edges.json"
SINGLE_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_single_variable_stats.csv"
THREE_WAY_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_three_way_stats.csv"
ROBUSTNESS_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_robustness_stats.csv"
GAP_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_gap_diagnostic.csv"
MONOTONICITY_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_monotonicity.csv"
SURFACE_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_surface_diagnostics.csv"
UNCONDITIONAL_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_unconditional_stats.csv"
SUMMARY_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_summary.json"
CROSS_STATUS_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_cross_market_status.json"

BINANCE_ARTIFACT_DIR = (
    ROOT / "research/asset-portfolios/1d-ma7-regime-continuation/artifacts"
)
BINANCE_SINGLE_PATH = (
    BINANCE_ARTIFACT_DIR / "binance_1d_ma7_rc_p0_single_variable_stats.csv"
)
BINANCE_THREE_WAY_PATH = (
    BINANCE_ARTIFACT_DIR / "binance_1d_ma7_rc_p0_three_way_stats.csv"
)
BINANCE_EVENT_PATH = BINANCE_ARTIFACT_DIR / "binance_1d_ma7_rc_p0_events.parquet"
CROSS_SINGLE_LONG_PATH = (
    ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_cross_market_single_variable_long.csv"
)
CROSS_SINGLE_WIDE_PATH = (
    ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_cross_market_single_variable_wide.csv"
)
CROSS_THREE_WAY_LONG_PATH = (
    ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_cross_market_three_way_long.csv"
)
CROSS_THREE_WAY_WIDE_PATH = (
    ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_cross_market_three_way_wide.csv"
)
CROSS_SINGLE_COMMON_PATH = (
    ARTIFACT_DIR
    / "ndx100_1d_ma7_rc_p0_cross_market_common_window_single_variable_wide.csv"
)
CROSS_THREE_WAY_COMMON_PATH = (
    ARTIFACT_DIR
    / "ndx100_1d_ma7_rc_p0_cross_market_common_window_three_way_wide.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the frozen NDX100-1D-MA7-RC-P0 event study."
    )
    parser.add_argument(
        "--check-access",
        action="store_true",
        help="Check Massive credentials and reference-data entitlement only.",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch and cache frozen Massive reference and adjusted daily data.",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Fetch missing inputs and calculate the frozen historical study.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace task-local caches and generated P0 artifacts.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_config() -> dict[str, Any]:
    actual = sha256_file(CONFIG_PATH)
    if actual != EXPECTED_CONFIG_SHA256:
        raise RuntimeError(
            f"frozen config hash mismatch: {actual} != {EXPECTED_CONFIG_SHA256}"
        )
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if config.get("study_id") != STUDY_ID:
        raise RuntimeError("unexpected study_id in frozen config")
    if config["binning"].get("threshold_search") is not False:
        raise RuntimeError("threshold search must remain disabled")
    return config


def utc_now() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def credential() -> tuple[str | None, str | None]:
    for name in ("MASSIVE_API_KEY", "POLYGON_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value, name
    return None, None


def write_credential_blocker(config: dict[str, Any]) -> None:
    membership_audit = (
        json.loads(MEMBERSHIP_AUDIT_PATH.read_text(encoding="utf-8"))
        if MEMBERSHIP_AUDIT_PATH.exists()
        else None
    )
    write_json(
        BLOCKER_PATH,
        {
            "study_id": STUDY_ID,
            "generated_at_utc": utc_now(),
            "status": "BLOCKED_DATA_ACCESS",
            "blocking_stage": "Massive credential discovery",
            "credentials_checked": config["data"][
                "credential_environment_variables_in_priority_order"
            ],
            "credential_values_logged": False,
            "blocker": (
                "Neither MASSIVE_API_KEY nor the legacy POLYGON_API_KEY is present "
                "in the process environment. Massive prices, point-in-time ticker "
                "details, ticker events, statistical results, and cross-market "
                "comparisons were not fabricated."
            ),
            "substitute_provider_used": False,
            "membership_reconstruction_available": MEMBERSHIP_PATH.exists(),
            "membership_audit": membership_audit,
            "resume_command": (
                ".venv/bin/python research/us-indexes/"
                "1d-nasdaq100-ma7-regime-continuation/scripts/"
                "research_ndx100_1d_ma7_regime_continuation.py --run"
            ),
        },
    )
    write_json(
        CROSS_STATUS_PATH,
        {
            "study_id": STUDY_ID,
            "generated_at_utc": utc_now(),
            "status": "BLOCKED_COMPARISON_INPUT",
            "stock_input_status": "BLOCKED_DATA_ACCESS",
            "binance_single_variable_available": BINANCE_SINGLE_PATH.exists(),
            "binance_three_way_available": BINANCE_THREE_WAY_PATH.exists(),
            "fabricated_rows": 0,
            "blocker": (
                "Nasdaq-100 event-study outputs do not exist because Massive data "
                "access is blocked. Binance outputs cannot substitute for the stock side."
            ),
        },
    )


class MassiveClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def get_json(
        self,
        path_or_url: str,
        params: dict[str, Any] | None = None,
        *,
        attempts: int = 6,
    ) -> dict[str, Any]:
        if path_or_url.startswith("http"):
            url = path_or_url
        else:
            url = self.base_url + "/" + path_or_url.lstrip("/")
        query = dict(params or {})
        query["apiKey"] = self.api_key
        separator = "&" if "?" in url else "?"
        request_url = url + separator + urllib.parse.urlencode(query)
        safe_url = url + separator + urllib.parse.urlencode(
            {key: value for key, value in query.items() if key != "apiKey"}
        )
        for attempt in range(attempts):
            request = urllib.request.Request(
                request_url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    payload = json.loads(response.read())
                payload["_request_url_without_api_key"] = safe_url
                return payload
            except urllib.error.HTTPError as error:
                retriable = error.code == 429 or 500 <= error.code < 600
                if not retriable or attempt == attempts - 1:
                    body = error.read().decode("utf-8", errors="replace")[:800]
                    raise RuntimeError(
                        f"Massive HTTP {error.code} for {safe_url}: {body}"
                    ) from error
                retry_after = error.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else min(2**attempt, 30)
                time.sleep(wait)
            except urllib.error.URLError as error:
                if attempt == attempts - 1:
                    raise RuntimeError(f"Massive request failed for {safe_url}") from error
                time.sleep(min(2**attempt, 30))
        raise AssertionError("unreachable")


def check_massive_access(
    client: MassiveClient, config: dict[str, Any], credential_name: str
) -> dict[str, Any]:
    date = config["data"]["study_end_session_inclusive"]
    historical_anchor = "2010-01-04"
    checks: list[dict[str, Any]] = []
    details_figi: str | None = None
    endpoints = (
        (
            "ticker_details",
            "/v3/reference/tickers/AAPL",
            {"date": date},
        ),
        (
            "daily_aggregates",
            f"/v2/aggs/ticker/AAPL/range/1/day/{date}/{date}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        ),
        (
            "historical_daily_aggregates",
            f"/v2/aggs/ticker/AAPL/range/1/day/{historical_anchor}/{historical_anchor}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        ),
    )
    for name, path, params in endpoints:
        try:
            payload = client.get_json(path, params)
            if name == "ticker_details":
                details_figi = (payload.get("results") or {}).get("composite_figi")
            result_count = payload.get(
                "resultsCount", 1 if payload.get("results") else 0
            )
            endpoint_ok = payload.get("status") in {"OK", "DELAYED"}
            if name == "historical_daily_aggregates":
                endpoint_ok = endpoint_ok and result_count >= 1
            checks.append(
                {
                    "name": name,
                    "ok": endpoint_ok,
                    "status": payload.get("status"),
                    "request_id": payload.get("request_id"),
                    "result_count": result_count,
                    "required_historical_anchor": (
                        historical_anchor
                        if name == "historical_daily_aggregates"
                        else None
                    ),
                    "error": (
                        "required 2010 daily history is unavailable under this entitlement"
                        if name == "historical_daily_aggregates" and result_count < 1
                        else payload.get("error")
                    ),
                }
            )
        except RuntimeError as error:
            checks.append({"name": name, "ok": False, "error": str(error)})
    if details_figi is None:
        checks.append(
            {
                "name": "ticker_events",
                "ok": False,
                "error": "AAPL point-in-time details did not return composite_figi",
            }
        )
    else:
        try:
            payload = client.get_json(
                f"/vX/reference/tickers/{urllib.parse.quote(details_figi)}/events"
            )
            checks.append(
                {
                    "name": "ticker_events",
                    "ok": payload.get("status") in {"OK", "DELAYED"},
                    "status": payload.get("status"),
                    "request_id": payload.get("request_id"),
                    "error": payload.get("error"),
                }
            )
        except RuntimeError as error:
            checks.append({"name": "ticker_events", "ok": False, "error": str(error)})
    result = {
        "study_id": STUDY_ID,
        "generated_at_utc": utc_now(),
        "credential_environment_variable": credential_name,
        "credential_value_logged": False,
        "checks": checks,
        "all_required_checks_pass": all(item["ok"] for item in checks),
    }
    write_json(ACCESS_AUDIT_PATH, result)
    return result


def write_entitlement_blocker(
    config: dict[str, Any], access: dict[str, Any]
) -> None:
    write_json(
        BLOCKER_PATH,
        {
            "study_id": STUDY_ID,
            "generated_at_utc": utc_now(),
            "status": "BLOCKED_DATA_ACCESS",
            "blocking_stage": "Massive historical entitlement",
            "credential_present": True,
            "credential_value_logged": False,
            "access_audit": str(ACCESS_AUDIT_PATH.relative_to(FAMILY_DIR)),
            "blocker": (
                "Massive credentials authenticate and current/reference endpoints are "
                "available, but the required 2010 daily aggregate anchor is unavailable. "
                "The observed account entitlement only returned the recent two-year window."
            ),
            "required_study_start": config["data"]["study_start_session"],
            "substitute_provider_used_for_p0": False,
            "separate_yahoo_current_observation": "NDX100-1D-MA7-RC-Y0",
            "access_checks": access["checks"],
        },
    )
    write_json(
        CROSS_STATUS_PATH,
        {
            "study_id": STUDY_ID,
            "generated_at_utc": utc_now(),
            "status": "BLOCKED_COMPARISON_INPUT",
            "stock_input_status": "BLOCKED_MASSIVE_HISTORY_ENTITLEMENT",
            "fabricated_rows": 0,
            "separate_yahoo_current_observation": "NDX100-1D-MA7-RC-Y0",
        },
    )


def cache_path(category: str, identity: str) -> Path:
    safe = identity.replace("/", "_").replace(":", "_").replace("?", "_")
    return CACHE_DIR / category / f"{safe}.json"


def cached_request(
    client: MassiveClient,
    *,
    category: str,
    identity: str,
    path: str,
    params: dict[str, Any],
    force: bool,
) -> dict[str, Any]:
    destination = cache_path(category, identity)
    if destination.exists() and not force:
        return json.loads(destination.read_text(encoding="utf-8"))
    payload = client.get_json(path, params)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_json(destination, payload)
    return payload


def fetch_reference_data(
    client: MassiveClient,
    intervals: pd.DataFrame,
    *,
    force: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in intervals.itertuples(index=False):
        for boundary, date in (
            ("start", item.start_session),
            ("end", item.end_session_inclusive),
        ):
            identity = f"{item.ticker}_{date}_{boundary}"
            payload = cached_request(
                client,
                category="ticker-details",
                identity=identity,
                path=f"/v3/reference/tickers/{urllib.parse.quote(item.ticker)}",
                params={"date": date},
                force=force,
            )
            result = payload.get("results") or {}
            rows.append(
                {
                    "ticker": item.ticker,
                    "entity_key": item.entity_key,
                    "interval_start": item.start_session,
                    "interval_end": item.end_session_inclusive,
                    "boundary": boundary,
                    "as_of_date": date,
                    "provider_status": payload.get("status"),
                    "provider_ticker": result.get("ticker"),
                    "name": result.get("name"),
                    "active": result.get("active"),
                    "market": result.get("market"),
                    "primary_exchange": result.get("primary_exchange"),
                    "type": result.get("type"),
                    "currency_name": result.get("currency_name"),
                    "composite_figi": result.get("composite_figi"),
                    "share_class_figi": result.get("share_class_figi"),
                    "cik": result.get("cik"),
                    "request_id": payload.get("request_id"),
                }
            )
    details = pd.DataFrame(rows)
    details.to_csv(IDENTIFIER_MAP_PATH, index=False)

    absent = details.loc[
        details["provider_ticker"].isna()
        | details["composite_figi"].isna()
        | details["share_class_figi"].isna()
    ]
    ticker_event_rows: list[dict[str, Any]] = []
    event_request_failures: list[dict[str, str]] = []
    for figi in sorted(details["composite_figi"].dropna().astype(str).unique()):
        try:
            payload = cached_request(
                client,
                category="ticker-events",
                identity=figi,
                path=f"/vX/reference/tickers/{urllib.parse.quote(figi)}/events",
                params={},
                force=force,
            )
        except RuntimeError as error:
            event_request_failures.append({"composite_figi": figi, "error": str(error)})
            continue
        if payload.get("status") not in {"OK", "DELAYED"}:
            event_request_failures.append(
                {
                    "composite_figi": figi,
                    "error": f"provider status={payload.get('status')}: {payload.get('error')}",
                }
            )
            continue
        result = payload.get("results") or {}
        for event in result.get("events") or []:
            change = event.get("ticker_change") or {}
            ticker_event_rows.append(
                {
                    "composite_figi": figi,
                    "event_date": event.get("date"),
                    "event_type": event.get("type"),
                    "event_ticker": change.get("ticker"),
                    "event_payload": json.dumps(event, sort_keys=True),
                }
            )
    ticker_events = pd.DataFrame(
        ticker_event_rows,
        columns=[
            "composite_figi",
            "event_date",
            "event_type",
            "event_ticker",
            "event_payload",
        ],
    )
    ticker_events.to_csv(
        ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_ticker_events.csv", index=False
    )
    reused = details.groupby("ticker")["entity_key"].nunique()
    reused_tickers = reused.index[reused.gt(1)].tolist()
    reuse_checks: list[dict[str, Any]] = []
    for ticker in reused_tickers:
        sample = details.loc[details["ticker"].eq(ticker)]
        by_entity = sample.groupby("entity_key")["share_class_figi"].agg(
            lambda values: sorted(set(values.dropna().astype(str)))
        )
        sets = [tuple(value) for value in by_entity]
        reuse_checks.append(
            {
                "ticker": ticker,
                "entity_count": int(len(by_entity)),
                "share_class_figis_by_entity": by_entity.to_dict(),
                "distinct_entity_figi_sets": len(set(sets)) == len(sets),
            }
        )
    rename_checks: list[dict[str, Any]] = []
    interval_tickers = intervals.groupby("entity_key")["ticker"].agg(
        lambda values: sorted(set(values.astype(str)))
    )
    for entity_key, expected_tickers in interval_tickers.items():
        if len(expected_tickers) < 2:
            continue
        figis = set(
            details.loc[
                details["entity_key"].eq(entity_key), "composite_figi"
            ].dropna().astype(str)
        )
        observed = set(
            ticker_events.loc[
                ticker_events["composite_figi"].isin(figis), "event_ticker"
            ].dropna().astype(str)
        )
        observed.update(
            details.loc[
                details["entity_key"].eq(entity_key), "provider_ticker"
            ].dropna().astype(str)
        )
        rename_checks.append(
            {
                "entity_key": entity_key,
                "expected_tickers": expected_tickers,
                "observed_detail_or_event_tickers": sorted(observed),
                "all_expected_tickers_observed": set(expected_tickers).issubset(observed),
            }
        )
    audit = {
        "study_id": STUDY_ID,
        "generated_at_utc": utc_now(),
        "detail_requests": int(len(details)),
        "membership_intervals": int(len(intervals)),
        "missing_ticker_or_figi_rows": int(len(absent)),
        "ticker_event_requests": int(details["composite_figi"].nunique()),
        "ticker_event_request_failures": event_request_failures,
        "ticker_event_rows": int(len(ticker_events)),
        "same_ticker_multiple_entity_checks": reuse_checks,
        "all_same_ticker_generations_distinct": all(
            item["distinct_entity_figi_sets"] for item in reuse_checks
        ),
        "rename_lineage_checks": rename_checks,
        "all_rename_lineages_observed": all(
            item["all_expected_tickers_observed"] for item in rename_checks
        ),
        "blockers": [],
    }
    if len(absent):
        audit["blockers"].append("missing point-in-time ticker details or FIGI")
    if not audit["all_same_ticker_generations_distinct"]:
        audit["blockers"].append("same-symbol entity generation not resolved by FIGI")
    if event_request_failures:
        audit["blockers"].append("Massive ticker-events requests failed")
    if not audit["all_rename_lineages_observed"]:
        audit["blockers"].append("renamed ticker lineage not confirmed by details/events")
    write_json(IDENTIFIER_AUDIT_PATH, audit)
    if audit["blockers"]:
        raise RuntimeError(f"identifier audit blockers: {audit['blockers']}")
    return details, audit


def fetch_daily_bars(
    client: MassiveClient,
    tickers: Iterable[str],
    *,
    end_date: str,
    force: bool,
) -> None:
    for ticker in sorted(set(tickers) | {"QQQ"}):
        cached_request(
            client,
            category="daily-aggregates",
            identity=f"{ticker}_{FETCH_START}_{end_date}_adjusted",
            path=(
                f"/v2/aggs/ticker/{urllib.parse.quote(ticker)}/range/1/day/"
                f"{FETCH_START}/{end_date}"
            ),
            params={"adjusted": "true", "sort": "asc", "limit": 50000},
            force=force,
        )


def _raw_bars_for_ticker(ticker: str, end_date: str) -> pd.DataFrame:
    path = cache_path(
        "daily-aggregates", f"{ticker}_{FETCH_START}_{end_date}_adjusted"
    )
    if not path.exists():
        raise RuntimeError(f"missing Massive aggregate cache for {ticker}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") not in {"OK", "DELAYED"}:
        raise RuntimeError(f"Massive aggregate status for {ticker}: {payload.get('status')}")
    results = payload.get("results") or []
    if not results:
        return pd.DataFrame(
            columns=["session_date", "ticker", "open", "high", "low", "close", "volume"]
        )
    frame = pd.DataFrame(results).rename(
        columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
    )
    timestamps = pd.to_datetime(frame["t"], unit="ms", utc=True)
    frame["session_date"] = timestamps.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    frame["ticker"] = ticker
    return frame[["session_date", "ticker", "open", "high", "low", "close", "volume"]]


def assign_entity_keys(bars: pd.DataFrame, intervals: pd.DataFrame) -> pd.DataFrame:
    outputs: list[pd.DataFrame] = []
    for ticker, group in bars.groupby("ticker", sort=False):
        if ticker == "QQQ":
            mapped = group.copy()
            mapped["entity_key"] = "QQQ"
            outputs.append(mapped)
            continue
        mapping = intervals.loc[intervals["ticker"].eq(ticker)].sort_values(
            "start_session"
        )
        if mapping.empty:
            raise RuntimeError(f"no membership lineage for ticker {ticker}")
        entities = mapping["entity_key"].drop_duplicates().tolist()
        mapped = group.copy()
        if len(entities) == 1:
            mapped["entity_key"] = entities[0]
        else:
            mapped["entity_key"] = None
            boundaries = (
                mapping.groupby("entity_key", sort=False)["start_session"].min().sort_values()
            )
            ordered = list(boundaries.items())
            for index, (entity, start) in enumerate(ordered):
                lower = pd.Timestamp.min if index == 0 else pd.Timestamp(start)
                upper = (
                    pd.Timestamp(ordered[index + 1][1])
                    if index + 1 < len(ordered)
                    else pd.Timestamp.max
                )
                mask = mapped["session_date"].ge(lower) & mapped["session_date"].lt(upper)
                mapped.loc[mask, "entity_key"] = entity
        outputs.append(mapped)
    result = pd.concat(outputs, ignore_index=True)
    if result["entity_key"].isna().any():
        raise RuntimeError("unresolved ticker/date entity mapping")
    return result


def load_and_audit_prices(
    intervals: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    end_date = config["data"]["study_end_session_inclusive"]
    raw = pd.concat(
        [
            _raw_bars_for_ticker(ticker, end_date)
            for ticker in sorted(set(intervals["ticker"]) | {"QQQ"})
        ],
        ignore_index=True,
    )
    mapped = assign_entity_keys(raw, intervals)
    calendar = xcals.get_calendar("XNAS")
    valid_sessions = pd.DatetimeIndex(
        calendar.sessions_in_range(pd.Timestamp(FETCH_START), pd.Timestamp(end_date))
    ).tz_localize(None)
    invalid_ohlc = (
        mapped[["open", "high", "low", "close"]].isna().any(axis=1)
        | mapped["open"].le(0)
        | mapped["high"].le(0)
        | mapped["low"].le(0)
        | mapped["close"].le(0)
        | mapped["volume"].isna()
        | mapped["volume"].lt(0)
        | mapped["high"].lt(mapped[["open", "close", "low"]].max(axis=1))
        | mapped["low"].gt(mapped[["open", "close", "high"]].min(axis=1))
    )
    duplicate_ticker_date = mapped.duplicated(["ticker", "session_date"], keep=False)
    duplicate_entity_date = mapped.duplicated(["entity_key", "session_date"], keep=False)
    out_of_session = ~mapped["session_date"].isin(valid_sessions)
    blockers: list[str] = []
    if invalid_ohlc.any():
        blockers.append("invalid or null OHLCV rows")
    if duplicate_ticker_date.any():
        blockers.append("duplicate ticker/session rows")
    if duplicate_entity_date.any():
        blockers.append("overlapping ticker lineage creates duplicate entity/session rows")
    if out_of_session.any():
        blockers.append("daily aggregate dates outside XNAS sessions")
    audit = {
        "study_id": STUDY_ID,
        "generated_at_utc": utc_now(),
        "source": "polygon_api",
        "provider_label": "Massive (formerly Polygon)",
        "adjusted_for_splits": True,
        "dividends_and_delisting_returns_included": False,
        "rows": int(len(mapped)),
        "tickers": int(mapped["ticker"].nunique()),
        "entities": int(mapped["entity_key"].nunique()),
        "first_session": mapped["session_date"].min(),
        "last_session": mapped["session_date"].max(),
        "invalid_ohlcv_rows": int(invalid_ohlc.sum()),
        "duplicate_ticker_session_rows": int(duplicate_ticker_date.sum()),
        "duplicate_entity_session_rows": int(duplicate_entity_date.sum()),
        "out_of_xnas_session_rows": int(out_of_session.sum()),
        "blockers": blockers,
    }
    write_json(PRICE_AUDIT_PATH, audit)
    if blockers:
        raise RuntimeError(f"price audit blockers: {blockers}")
    qqq = mapped.loc[mapped["entity_key"].eq("QQQ")].copy()
    equities = mapped.loc[~mapped["entity_key"].eq("QQQ")].copy()
    return equities, qqq, audit


def rolling_percentile_current(
    values: Sequence[float] | np.ndarray, window: int
) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    output = np.full(len(array), np.nan, dtype=float)
    if len(array) < window:
        return output
    windows = np.lib.stride_tricks.sliding_window_view(array, window)
    valid = np.isfinite(windows).all(axis=1)
    current = windows[:, -1]
    ranks = np.full(len(windows), np.nan, dtype=float)
    ranks[valid] = (windows[valid] <= current[valid, None]).mean(axis=1)
    output[window - 1 :] = ranks
    return output


def _feature_block(group: pd.DataFrame) -> pd.DataFrame:
    block = group.copy()
    close = block["close"].astype(float)
    high = block["high"].astype(float)
    low = block["low"].astype(float)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    block["atr14"] = true_range.rolling(14, min_periods=14).mean()
    block["sma30"] = close.rolling(30, min_periods=30).mean()
    block["normalized_slope"] = (
        block["sma30"] - block["sma30"].shift(1)
    ) / block["atr14"]
    absolute_path = close.diff().abs().rolling(20, min_periods=20).sum()
    block["er20"] = (close - close.shift(20)).abs() / absolute_path.replace(0, np.nan)
    log_return = np.log(close).diff()
    block["rv20"] = log_return.rolling(20, min_periods=20).std(ddof=1) * math.sqrt(252.0)
    block["rv_percentile"] = rolling_percentile_current(block["rv20"], 252)
    block["adv30_median"] = (
        (close * block["volume"].astype(float)).rolling(30, min_periods=30).median()
    )
    block["gap"] = (block["open"].astype(float) - previous_close) / previous_close
    block["sma200"] = close.rolling(200, min_periods=200).mean()
    block["return_30d"] = close / close.shift(30) - 1.0
    for period in MA_PERIODS:
        block[f"sma{period}"] = close.rolling(period, min_periods=period).mean()
    for horizon in HORIZONS:
        block[f"future_close_{horizon}"] = close.shift(-horizon)
    return block


def prepare_feature_panel(
    bars: pd.DataFrame,
    membership: pd.DataFrame,
    qqq: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    calendar = xcals.get_calendar("XNAS")
    sessions = pd.DatetimeIndex(
        calendar.sessions_in_range(
            pd.Timestamp(FETCH_START),
            pd.Timestamp(config["data"]["study_end_session_inclusive"]),
        )
    ).tz_localize(None)
    ordinal = pd.Series(np.arange(len(sessions)), index=sessions)
    panel = bars.sort_values(["entity_key", "session_date", "ticker"]).reset_index(drop=True)
    panel["session_ordinal"] = panel["session_date"].map(ordinal)
    previous = panel.groupby("entity_key", sort=False)["session_ordinal"].shift(1)
    panel["new_block"] = previous.isna() | panel["session_ordinal"].sub(previous).ne(1)
    panel["block_id"] = panel.groupby("entity_key", sort=False)["new_block"].cumsum().astype(int)
    featured = [
        _feature_block(group)
        for _, group in panel.groupby(["entity_key", "block_id"], sort=False)
    ]
    panel = pd.concat(featured, ignore_index=True)

    membership = membership.copy()
    membership["session_date"] = pd.to_datetime(membership["session_date"])
    membership["membership_interval_start"] = pd.to_datetime(
        membership["membership_interval_start"]
    )
    membership_ordinal = membership["session_date"].map(ordinal)
    start_ordinal = membership["membership_interval_start"].map(ordinal)
    membership["membership_tenure_sessions"] = membership_ordinal - start_ordinal
    member_columns = [
        "session_date",
        "ticker",
        "entity_key",
        "membership_interval_start",
        "membership_tenure_sessions",
    ]
    panel = panel.merge(
        membership[member_columns],
        on=["session_date", "ticker", "entity_key"],
        how="left",
        validate="one_to_one",
        indicator="membership_merge",
    )
    panel["is_member"] = panel["membership_merge"].eq("both")
    study_start = pd.Timestamp(config["data"]["study_start_session"])
    study_end = pd.Timestamp(config["data"]["study_end_session_inclusive"])
    finite_regime = np.isfinite(
        panel[["normalized_slope", "er20", "rv_percentile", "atr14"]].to_numpy()
    ).all(axis=1)
    panel["eligible_regime"] = (
        panel["is_member"]
        & panel["session_date"].between(study_start, study_end)
        & finite_regime
    )

    qqq = qqq.sort_values("session_date").copy()
    qqq["session_ordinal"] = qqq["session_date"].map(ordinal)
    previous_qqq = qqq["session_ordinal"].shift(1)
    qqq["block_id"] = (previous_qqq.isna() | qqq["session_ordinal"].sub(previous_qqq).ne(1)).cumsum()
    qqq = pd.concat(
        [_feature_block(group) for _, group in qqq.groupby("block_id", sort=False)],
        ignore_index=True,
    )
    qqq["market_phase"] = np.select(
        [
            qqq["close"].gt(qqq["sma200"]) & qqq["return_30d"].gt(0),
            qqq["close"].lt(qqq["sma200"]) & qqq["return_30d"].lt(0),
        ],
        ["bull", "bear"],
        default="transition",
    )
    panel = panel.merge(
        qqq[["session_date", "market_phase"]],
        on="session_date",
        how="left",
        validate="many_to_one",
    )
    eligible = panel.loc[panel["eligible_regime"]]
    panel.loc[eligible.index, "liquidity_rank"] = eligible.groupby("session_date")[
        "adv30_median"
    ].rank(method="first", ascending=False)
    panel["liquidity_segment"] = np.select(
        [panel["liquidity_rank"].le(20), panel["liquidity_rank"].gt(20)],
        ["top20", "other"],
        default="unavailable",
    )
    panel["membership_tenure_segment"] = np.select(
        [
            panel["membership_tenure_sessions"].lt(252),
            panel["membership_tenure_sessions"].ge(252),
        ],
        ["recent_member", "seasoned_member"],
        default="unavailable",
    )
    panel["calendar_year"] = panel["session_date"].dt.year.astype(int)
    return panel


def quantile_edges(values: pd.Series, bins: int = 5) -> list[float]:
    clean = values[np.isfinite(values.to_numpy(dtype=float))].to_numpy(dtype=float)
    if not len(clean):
        raise RuntimeError("cannot calculate quantiles from an empty series")
    edges = np.quantile(clean, np.linspace(0.0, 1.0, bins + 1), method="linear")
    if np.any(np.diff(edges) <= 0):
        raise RuntimeError(f"non-unique quintile edges: {edges.tolist()}")
    return [float(value) for value in edges]


def assign_quintile(values: pd.Series, edges: Sequence[float]) -> pd.Series:
    internal = np.asarray(edges[1:-1], dtype=float)
    array = values.to_numpy(dtype=float)
    output = np.full(len(array), np.nan)
    valid = np.isfinite(array)
    output[valid] = np.searchsorted(internal, array[valid], side="left") + 1
    return pd.Series(output, index=values.index, dtype="Int64")


def freeze_regime_bins(panel: pd.DataFrame) -> dict[str, list[float]]:
    eligible = panel.loc[panel["eligible_regime"]]
    edges = {
        "normalized_slope": quantile_edges(eligible["normalized_slope"]),
        "er20": quantile_edges(eligible["er20"]),
        "rv_percentile": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
    }
    panel["slope_q"] = assign_quintile(panel["normalized_slope"], edges["normalized_slope"])
    panel["er_q"] = assign_quintile(panel["er20"], edges["er20"])
    panel["rv_q"] = assign_quintile(panel["rv_percentile"], edges["rv_percentile"])
    return edges


def build_events(panel: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    identity = [
        "ticker",
        "entity_key",
        "session_date",
        "block_id",
        "close",
        "atr14",
        "normalized_slope",
        "er20",
        "rv20",
        "rv_percentile",
        "slope_q",
        "er_q",
        "rv_q",
        "gap",
        "adv30_median",
        "liquidity_rank",
        "liquidity_segment",
        "membership_tenure_sessions",
        "membership_tenure_segment",
        "market_phase",
        "calendar_year",
    ]
    grouped = panel.groupby(["entity_key", "block_id"], sort=False)
    for period in MA_PERIODS:
        previous_close = grouped["close"].shift(1)
        previous_ma = grouped[f"sma{period}"].shift(1)
        directions = (
            (
                "long",
                previous_close.le(previous_ma) & panel["close"].gt(panel[f"sma{period}"]),
                1.0,
            ),
            (
                "short",
                previous_close.ge(previous_ma) & panel["close"].lt(panel[f"sma{period}"]),
                -1.0,
            ),
        )
        for direction, trigger, sign in directions:
            mask = trigger & panel["eligible_regime"]
            events = panel.loc[mask, identity].copy()
            events["ma_period"] = period
            events["direction"] = direction
            events["trigger_ma"] = panel.loc[mask, f"sma{period}"].to_numpy()
            for horizon in HORIZONS:
                future = panel.loc[mask, f"future_close_{horizon}"].to_numpy(dtype=float)
                entry = events["close"].to_numpy(dtype=float)
                atr = events["atr14"].to_numpy(dtype=float)
                events[f"raw_return_{horizon}"] = sign * (future / entry - 1.0)
                events[f"atr_return_{horizon}"] = sign * (future - entry) / atr
            events["event_id"] = (
                "MA"
                + str(period)
                + "|"
                + direction
                + "|"
                + events["entity_key"].astype(str)
                + "|"
                + events["session_date"].dt.strftime("%Y-%m-%d")
            )
            frames.append(events)
    result = pd.concat(frames, ignore_index=True)
    if result["event_id"].duplicated().any():
        raise RuntimeError("duplicate event identifiers")
    return result.sort_values(["ma_period", "session_date", "entity_key"]).reset_index(drop=True)


def _cluster_variance(residual: np.ndarray, labels: pd.Series) -> tuple[float, int]:
    codes, uniques = pd.factorize(labels, sort=False)
    groups = len(uniques)
    if groups < 2:
        return math.nan, groups
    sums = np.bincount(codes, weights=residual)
    variance = (groups / (groups - 1.0)) * float(np.dot(sums, sums)) / len(residual) ** 2
    return variance, groups


def infer_mean(
    values: pd.Series, securities: pd.Series, dates: pd.Series
) -> dict[str, Any]:
    array = values.to_numpy(dtype=float)
    valid = np.isfinite(array)
    array = array[valid]
    security_values = securities.loc[valid]
    date_values = dates.loc[valid]
    count = len(array)
    if count == 0:
        return {
            "sample_count": 0,
            "security_count": 0,
            "event_date_count": 0,
            "mean": math.nan,
            "median": math.nan,
            "win_rate": math.nan,
            "cluster_se": math.nan,
            "t_stat": math.nan,
            "ci95_low": math.nan,
            "ci95_high": math.nan,
            "p_value": math.nan,
            "cluster_variance_fallback": False,
        }
    mean = float(np.mean(array))
    residual = array - mean
    security_variance, security_count = _cluster_variance(residual, security_values)
    date_variance, date_count = _cluster_variance(residual, date_values)
    fallback = False
    if count < 2 or not np.isfinite(security_variance) or not np.isfinite(date_variance):
        standard_error = math.nan
    else:
        observation_variance = count / (count - 1.0) * float(np.dot(residual, residual)) / count**2
        combined = security_variance + date_variance - observation_variance
        fallback = combined <= 0
        if fallback:
            combined = max(security_variance, date_variance)
        standard_error = math.sqrt(max(combined, 0.0))
    if np.isfinite(standard_error) and standard_error > 0:
        t_stat = mean / standard_error
        p_value = math.erfc(abs(t_stat) / math.sqrt(2.0))
        ci_low = mean - 1.959963984540054 * standard_error
        ci_high = mean + 1.959963984540054 * standard_error
    else:
        t_stat = p_value = ci_low = ci_high = math.nan
    return {
        "sample_count": int(count),
        "security_count": int(security_count),
        "event_date_count": int(date_count),
        "mean": mean,
        "median": float(np.median(array)),
        "win_rate": float(np.mean(array > 0)),
        "cluster_se": standard_error,
        "t_stat": t_stat,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "p_value": p_value,
        "cluster_variance_fallback": bool(fallback),
    }


def summarize_groups(events: pd.DataFrame, groups: Sequence[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        for metric in RETURN_METRICS:
            value_column = f"{metric}_{horizon}"
            valid = events.loc[np.isfinite(events[value_column])]
            for keys, group in valid.groupby(list(groups), dropna=False, sort=True):
                values = keys if isinstance(keys, tuple) else (keys,)
                identity = dict(zip(groups, values, strict=True))
                rows.append(
                    {
                        **identity,
                        "horizon_days": horizon,
                        "return_metric": metric,
                        **infer_mean(
                            group[value_column], group["entity_key"], group["session_date"]
                        ),
                    }
                )
    return pd.DataFrame(rows)


def benjamini_hochberg(values: pd.Series) -> pd.Series:
    array = values.to_numpy(dtype=float)
    output = np.full(len(array), np.nan)
    positions = np.flatnonzero(np.isfinite(array))
    if not len(positions):
        return pd.Series(output, index=values.index)
    order = positions[np.argsort(array[positions])]
    adjusted = array[order] * len(order) / np.arange(1, len(order) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    output[order] = np.minimum(adjusted, 1.0)
    return pd.Series(output, index=values.index)


def build_single_variable_stats(events: pd.DataFrame) -> pd.DataFrame:
    primary = events.loc[events["ma_period"].eq(7)]
    outputs: list[pd.DataFrame] = []
    for variable, column in REGIME_VARIABLES.items():
        stats = summarize_groups(primary, ["direction", column]).rename(
            columns={column: "quintile"}
        )
        stats["variable"] = variable
        outputs.append(stats)
    return pd.concat(outputs, ignore_index=True).sort_values(
        ["direction", "variable", "horizon_days", "return_metric", "quintile"]
    ).reset_index(drop=True)


def build_three_way_stats(events: pd.DataFrame) -> pd.DataFrame:
    primary = events.loc[events["ma_period"].eq(7)]
    result = summarize_groups(primary, ["direction", "slope_q", "er_q", "rv_q"])
    result["reliable_cell"] = (
        result["sample_count"].ge(RELIABLE_MIN_EVENTS)
        & result["security_count"].ge(RELIABLE_MIN_SECURITIES)
        & result["event_date_count"].ge(RELIABLE_MIN_DATES)
    )
    result["q_value_bh"] = result.groupby(
        ["direction", "horizon_days", "return_metric"], group_keys=False
    )["p_value"].transform(benjamini_hochberg)
    return result.sort_values(
        ["direction", "horizon_days", "return_metric", "slope_q", "er_q", "rv_q"]
    ).reset_index(drop=True)


def _slice_variable_stats(
    events: pd.DataFrame, *, slice_type: str, slice_column: str
) -> pd.DataFrame:
    outputs: list[pd.DataFrame] = []
    for variable, column in REGIME_VARIABLES.items():
        stats = summarize_groups(events, ["direction", slice_column, column]).rename(
            columns={slice_column: "slice_value", column: "quintile"}
        )
        stats["slice_type"] = slice_type
        stats["variable"] = variable
        outputs.append(stats)
    return pd.concat(outputs, ignore_index=True)


def build_robustness_stats(events: pd.DataFrame) -> pd.DataFrame:
    primary = events.loc[events["ma_period"].eq(7)]
    outputs = [
        _slice_variable_stats(primary, slice_type="calendar_year", slice_column="calendar_year"),
        _slice_variable_stats(
            primary.loc[primary["market_phase"].notna()],
            slice_type="qqq_market_phase",
            slice_column="market_phase",
        ),
        _slice_variable_stats(
            primary.loc[primary["liquidity_segment"].isin(["top20", "other"])],
            slice_type="liquidity_segment",
            slice_column="liquidity_segment",
        ),
        _slice_variable_stats(
            primary.loc[
                primary["membership_tenure_segment"].isin(
                    ["recent_member", "seasoned_member"]
                )
            ],
            slice_type="membership_tenure_segment",
            slice_column="membership_tenure_segment",
        ),
        _slice_variable_stats(
            events, slice_type="ma_neighborhood", slice_column="ma_period"
        ),
    ]
    return pd.concat(outputs, ignore_index=True).sort_values(
        ["slice_type", "slice_value", "direction", "variable", "horizon_days", "return_metric", "quintile"]
    ).reset_index(drop=True)


def build_gap_diagnostic(events: pd.DataFrame) -> pd.DataFrame:
    primary = events.loc[events["ma_period"].eq(7)]
    outputs: list[pd.DataFrame] = []
    for label, threshold in (
        ("all_events", None),
        ("abs_gap_lt_1pct", 0.01),
        ("abs_gap_lt_2pct", 0.02),
        ("abs_gap_lt_3pct", 0.03),
    ):
        sample = primary if threshold is None else primary.loc[primary["gap"].abs().lt(threshold)]
        for variable, column in REGIME_VARIABLES.items():
            stats = summarize_groups(sample, ["direction", column]).rename(
                columns={column: "quintile"}
            )
            stats["gap_slice"] = label
            stats["absolute_gap_threshold"] = threshold
            stats["variable"] = variable
            outputs.append(stats)
    return pd.concat(outputs, ignore_index=True).sort_values(
        ["gap_slice", "direction", "variable", "horizon_days", "return_metric", "quintile"]
    ).reset_index(drop=True)


def _spearman(left: Sequence[float], right: Sequence[float]) -> float:
    left_series = pd.Series(left, dtype=float)
    right_series = pd.Series(right, dtype=float)
    valid = left_series.notna() & right_series.notna()
    if valid.sum() < 3:
        return math.nan
    left_rank = left_series.loc[valid].rank().to_numpy()
    right_rank = right_series.loc[valid].rank().to_numpy()
    if np.std(left_rank) == 0 or np.std(right_rank) == 0:
        return math.nan
    return float(np.corrcoef(left_rank, right_rank)[0, 1])


def build_monotonicity_stats(single: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    keys = ["direction", "variable", "horizon_days", "return_metric"]
    for values, group in single.groupby(keys, sort=True):
        direction, variable, horizon, metric = values
        ordered = group.sort_values("quintile")
        if set(ordered["quintile"].astype(int)) != {1, 2, 3, 4, 5}:
            continue
        aligned = (
            ordered.sort_values("quintile", ascending=False)
            if variable == "normalized_slope" and direction == "short"
            else ordered
        )
        means = aligned["mean"].to_numpy(dtype=float)
        rows.append(
            {
                "direction": direction,
                "variable": variable,
                "horizon_days": horizon,
                "return_metric": metric,
                "aligned_spearman": _spearman(range(1, 6), means),
                "adjacent_consistency": float(np.mean(np.diff(means) >= 0)),
                "aligned_extreme_spread": float(means[-1] - means[0]),
                "min_quintile_events": int(ordered["sample_count"].min()),
            }
        )
    return pd.DataFrame(rows).sort_values(keys).reset_index(drop=True)


def _surface_mean(
    events: pd.DataFrame,
    *,
    ma_period: int,
    date_start: pd.Timestamp | None = None,
    date_end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    sample = events.loc[events["ma_period"].eq(ma_period)]
    if date_start is not None:
        sample = sample.loc[sample["session_date"].ge(date_start)]
    if date_end is not None:
        sample = sample.loc[sample["session_date"].lt(date_end)]
    rows: list[pd.DataFrame] = []
    keys = ["direction", "slope_q", "er_q", "rv_q"]
    for horizon in HORIZONS:
        for metric in RETURN_METRICS:
            column = f"{metric}_{horizon}"
            summary = (
                sample.loc[np.isfinite(sample[column])]
                .groupby(keys, observed=True)[column]
                .agg(sample_count="count", mean="mean")
                .reset_index()
            )
            summary["horizon_days"] = horizon
            summary["return_metric"] = metric
            rows.append(summary)
    return pd.concat(rows, ignore_index=True)


def _surface_correlation(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    direction: str,
    horizon: int,
    metric: str,
    minimum_count: int,
) -> tuple[float, int]:
    keys = ["slope_q", "er_q", "rv_q"]
    def filtered(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.loc[
            frame["direction"].eq(direction)
            & frame["horizon_days"].eq(horizon)
            & frame["return_metric"].eq(metric)
            & frame["sample_count"].ge(minimum_count),
            keys + ["mean"],
        ]

    merged = filtered(left).rename(columns={"mean": "left_mean"}).merge(
        filtered(right).rename(columns={"mean": "right_mean"}), on=keys
    )
    return _spearman(merged["left_mean"], merged["right_mean"]), int(len(merged))


def build_surface_diagnostics(
    events: pd.DataFrame, three_way: pd.DataFrame
) -> pd.DataFrame:
    pre = _surface_mean(events, ma_period=7, date_end=TEMPORAL_SPLIT)
    post = _surface_mean(events, ma_period=7, date_start=TEMPORAL_SPLIT)
    surfaces = {period: _surface_mean(events, ma_period=period) for period in MA_PERIODS}
    rows: list[dict[str, Any]] = []
    for direction in ("long", "short"):
        for horizon in HORIZONS:
            for metric in RETURN_METRICS:
                full = three_way.loc[
                    three_way["direction"].eq(direction)
                    & three_way["horizon_days"].eq(horizon)
                    & three_way["return_metric"].eq(metric)
                ]
                reliable = full.loc[full["reliable_cell"]]
                values = {
                    (int(row.slope_q), int(row.er_q), int(row.rv_q)): float(row.mean)
                    for row in reliable.itertuples()
                }
                neighbors: list[float] = []
                for cell, value in values.items():
                    for axis in range(3):
                        neighbor = list(cell)
                        neighbor[axis] += 1
                        key = tuple(neighbor)
                        if key in values:
                            neighbors.append(abs(value - values[key]))
                std = float(np.std(list(values.values()), ddof=1)) if len(values) > 1 else math.nan
                roughness = float(np.mean(neighbors)) if neighbors else math.nan
                temporal_corr, temporal_cells = _surface_correlation(
                    pre,
                    post,
                    direction=direction,
                    horizon=horizon,
                    metric=metric,
                    minimum_count=50,
                )
                ma5_corr, ma5_cells = _surface_correlation(
                    surfaces[5],
                    surfaces[7],
                    direction=direction,
                    horizon=horizon,
                    metric=metric,
                    minimum_count=100,
                )
                ma10_corr, ma10_cells = _surface_correlation(
                    surfaces[10],
                    surfaces[7],
                    direction=direction,
                    horizon=horizon,
                    metric=metric,
                    minimum_count=100,
                )
                rows.append(
                    {
                        "direction": direction,
                        "horizon_days": horizon,
                        "return_metric": metric,
                        "populated_cells": int(len(full)),
                        "reliable_cells": int(len(reliable)),
                        "reliable_cell_fraction": len(reliable) / 125.0,
                        "fdr_significant_reliable_cells": int(
                            (reliable["q_value_bh"] <= 0.05).sum()
                        ),
                        "neighbor_pairs": int(len(neighbors)),
                        "neighbor_absolute_roughness": roughness,
                        "normalized_neighbor_roughness": roughness / std if np.isfinite(std) and std > 0 else math.nan,
                        "pre2020_post2020_spearman": temporal_corr,
                        "pre2020_post2020_common_cells": temporal_cells,
                        "ma5_ma7_spearman": ma5_corr,
                        "ma5_ma7_common_cells": ma5_cells,
                        "ma10_ma7_spearman": ma10_corr,
                        "ma10_ma7_common_cells": ma10_cells,
                    }
                )
    return pd.DataFrame(rows)


def _market_frame(frame: pd.DataFrame, market: str) -> pd.DataFrame:
    output = frame.copy()
    output.insert(0, "market", market)
    if "symbol_count" in output and "security_count" not in output:
        output = output.rename(columns={"symbol_count": "security_count"})
    return output


def _wide_cross_market(
    combined: pd.DataFrame, keys: Sequence[str]
) -> pd.DataFrame:
    measures = [
        column
        for column in ("mean", "median", "win_rate", "sample_count", "t_stat", "ci95_low", "ci95_high")
        if column in combined
    ]
    pivot = combined.pivot(index=list(keys), columns=["market", "direction"], values=measures)
    pivot.columns = [
        f"{str(market).lower()}_{str(direction).lower()}_{measure}"
        for measure, market, direction in pivot.columns
    ]
    return pivot.reset_index()


def build_cross_market_artifacts(
    stock_single: pd.DataFrame,
    stock_three_way: pd.DataFrame,
    stock_events: pd.DataFrame,
) -> dict[str, Any]:
    missing = [
        str(path)
        for path in (BINANCE_SINGLE_PATH, BINANCE_THREE_WAY_PATH, BINANCE_EVENT_PATH)
        if not path.exists()
    ]
    if missing:
        status = {
            "study_id": STUDY_ID,
            "generated_at_utc": utc_now(),
            "status": "BLOCKED_COMPARISON_INPUT",
            "missing_binance_artifacts": missing,
            "fabricated_rows": 0,
        }
        write_json(CROSS_STATUS_PATH, status)
        return status
    crypto_single = pd.read_csv(BINANCE_SINGLE_PATH)
    crypto_three = pd.read_csv(BINANCE_THREE_WAY_PATH)
    single = pd.concat(
        [_market_frame(crypto_single, "Crypto"), _market_frame(stock_single, "Nasdaq100")],
        ignore_index=True,
        sort=False,
    )
    three = pd.concat(
        [_market_frame(crypto_three, "Crypto"), _market_frame(stock_three_way, "Nasdaq100")],
        ignore_index=True,
        sort=False,
    )
    single.to_csv(CROSS_SINGLE_LONG_PATH, index=False)
    three.to_csv(CROSS_THREE_WAY_LONG_PATH, index=False)
    _wide_cross_market(
        single,
        ["variable", "quintile", "horizon_days", "return_metric"],
    ).to_csv(CROSS_SINGLE_WIDE_PATH, index=False)
    _wide_cross_market(
        three,
        ["slope_q", "er_q", "rv_q", "horizon_days", "return_metric"],
    ).to_csv(CROSS_THREE_WAY_WIDE_PATH, index=False)

    binance_dates = pd.read_parquet(BINANCE_EVENT_PATH, columns=["event_date"])[
        "event_date"
    ]
    common_start = pd.Timestamp(binance_dates.min()).tz_localize(None).normalize()
    common_end = pd.Timestamp(binance_dates.max()).tz_localize(None).normalize()
    stock_common_events = stock_events.loc[
        stock_events["session_date"].between(common_start, common_end)
    ]
    stock_common_single = build_single_variable_stats(stock_common_events)
    stock_common_three = build_three_way_stats(stock_common_events)
    common_single = pd.concat(
        [
            _market_frame(crypto_single, "Crypto"),
            _market_frame(stock_common_single, "Nasdaq100"),
        ],
        ignore_index=True,
        sort=False,
    )
    common_three = pd.concat(
        [
            _market_frame(crypto_three, "Crypto"),
            _market_frame(stock_common_three, "Nasdaq100"),
        ],
        ignore_index=True,
        sort=False,
    )
    _wide_cross_market(
        common_single,
        ["variable", "quintile", "horizon_days", "return_metric"],
    ).to_csv(CROSS_SINGLE_COMMON_PATH, index=False)
    _wide_cross_market(
        common_three,
        ["slope_q", "er_q", "rv_q", "horizon_days", "return_metric"],
    ).to_csv(CROSS_THREE_WAY_COMMON_PATH, index=False)
    status = {
        "study_id": STUDY_ID,
        "generated_at_utc": utc_now(),
        "status": "COMPARISON_WRITTEN",
        "single_variable_rows": int(len(single)),
        "three_way_rows": int(len(three)),
        "common_event_date_window": {
            "start": common_start,
            "end": common_end,
            "stock_regime_edges_refit": False,
        },
        "outputs": [
            str(CROSS_SINGLE_LONG_PATH.relative_to(FAMILY_DIR)),
            str(CROSS_SINGLE_WIDE_PATH.relative_to(FAMILY_DIR)),
            str(CROSS_THREE_WAY_LONG_PATH.relative_to(FAMILY_DIR)),
            str(CROSS_THREE_WAY_WIDE_PATH.relative_to(FAMILY_DIR)),
            str(CROSS_SINGLE_COMMON_PATH.relative_to(FAMILY_DIR)),
            str(CROSS_THREE_WAY_COMMON_PATH.relative_to(FAMILY_DIR)),
        ],
    }
    write_json(CROSS_STATUS_PATH, status)
    return status


def artifact_hashes(paths: Iterable[Path]) -> dict[str, str]:
    return {
        str(path.relative_to(FAMILY_DIR)): sha256_file(path)
        for path in paths
        if path.exists()
    }


def run_study(
    client: MassiveClient,
    config: dict[str, Any],
    *,
    force: bool,
) -> dict[str, Any]:
    if SUMMARY_PATH.exists() and not force:
        raise RuntimeError("P0 summary exists; pass --force to reproduce it")
    membership = pd.read_parquet(MEMBERSHIP_PATH)
    intervals = pd.read_csv(INTERVAL_PATH)
    for column in ("start_session", "end_session_inclusive"):
        intervals[column] = pd.to_datetime(intervals[column])
    fetch_reference_data(client, intervals, force=force)
    end_date = config["data"]["study_end_session_inclusive"]
    fetch_daily_bars(client, intervals["ticker"], end_date=end_date, force=force)
    bars, qqq, price_audit = load_and_audit_prices(intervals, config)
    panel = prepare_feature_panel(bars, membership, qqq, config)
    edges = freeze_regime_bins(panel)
    write_json(
        EDGE_PATH,
        {
            "study_id": STUDY_ID,
            "generated_at_utc": utc_now(),
            "selection_uses_outcomes": False,
            "eligible_member_sessions": int(panel["eligible_regime"].sum()),
            "edges": edges,
        },
    )
    events = build_events(panel)
    events.to_parquet(EVENT_PATH, index=False)
    single = build_single_variable_stats(events)
    three = build_three_way_stats(events)
    robustness = build_robustness_stats(events)
    gap = build_gap_diagnostic(events)
    monotonicity = build_monotonicity_stats(single)
    surface = build_surface_diagnostics(events, three)
    unconditional = summarize_groups(
        events.loc[events["ma_period"].eq(7)], ["direction"]
    )
    outputs = (
        (SINGLE_PATH, single),
        (THREE_WAY_PATH, three),
        (ROBUSTNESS_PATH, robustness),
        (GAP_PATH, gap),
        (MONOTONICITY_PATH, monotonicity),
        (SURFACE_PATH, surface),
        (UNCONDITIONAL_PATH, unconditional),
    )
    for path, frame in outputs:
        frame.to_csv(path, index=False)
    cross_status = build_cross_market_artifacts(single, three, events)
    output_paths = [path for path, _ in outputs] + [EVENT_PATH, EDGE_PATH, CROSS_STATUS_PATH]
    summary = {
        "study_id": STUDY_ID,
        "generated_at_utc": utc_now(),
        "status": "DIAGNOSTIC_COMPLETE_NOT_PROMOTED",
        "config_sha256": EXPECTED_CONFIG_SHA256,
        "membership_audit_sha256": sha256_file(MEMBERSHIP_AUDIT_PATH),
        "price_audit": price_audit,
        "member_feature_sessions": int(panel["eligible_regime"].sum()),
        "event_rows_all_ma_periods": int(len(events)),
        "ma7_event_rows": int(events["ma_period"].eq(7).sum()),
        "ma7_long_events": int(
            (events["ma_period"].eq(7) & events["direction"].eq("long")).sum()
        ),
        "ma7_short_events": int(
            (events["ma_period"].eq(7) & events["direction"].eq("short")).sum()
        ),
        "cross_market_status": cross_status,
        "decision_boundary": "diagnostic only; not promoted; not live-ready",
        "artifact_sha256": artifact_hashes(output_paths),
    }
    write_json(SUMMARY_PATH, summary)
    if BLOCKER_PATH.exists():
        BLOCKER_PATH.unlink()
    return summary


def main() -> int:
    args = parse_args()
    if not (args.check_access or args.fetch or args.run):
        raise SystemExit("choose --check-access, --fetch, or --run")
    config = read_config()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    key, credential_name = credential()
    if key is None or credential_name is None:
        write_credential_blocker(config)
        print(BLOCKER_PATH)
        return 2
    client = MassiveClient(key, config["data"]["api_base_url"])
    access = check_massive_access(client, config, credential_name)
    if not access["all_required_checks_pass"]:
        write_entitlement_blocker(config, access)
        if args.check_access and not (args.fetch or args.run):
            print(json.dumps(access, ensure_ascii=False))
            return 3
        raise RuntimeError("Massive access audit failed; see entitlement blocker")
    if args.check_access and not (args.fetch or args.run):
        print(json.dumps(access, ensure_ascii=False))
        return 0
    intervals = pd.read_csv(INTERVAL_PATH)
    for column in ("start_session", "end_session_inclusive"):
        intervals[column] = pd.to_datetime(intervals[column])
    if args.fetch and not args.run:
        fetch_reference_data(client, intervals, force=args.force)
        fetch_daily_bars(
            client,
            intervals["ticker"],
            end_date=config["data"]["study_end_session_inclusive"],
            force=args.force,
        )
        print(CACHE_DIR)
        return 0
    summary = run_study(client, config, force=args.force)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
