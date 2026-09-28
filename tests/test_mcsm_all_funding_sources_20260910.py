"""Source comparison must retain conflicts and preserve native event identities."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_all_funding_sources_20260910.py"
SPEC = importlib.util.spec_from_file_location("all_funding_recheck", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
TS = pd.Timestamp("2026-01-02T00:00:00Z")
MS = TS.as_unit("ns").value // 1_000_000
JOB = {"holding_month": "2026-01", "symbol": "BTC/USDT:USDT", "api_symbol": "BTCUSDT",
       "holding_start_ms": MS - 3600_000, "holding_end_ms": MS + 3600_000,
       "start_ms": MS - 3600_000, "end_ms": MS + 3600_000}


def frozen(ts=TS, rate=-0.01, source_type="Unspecified", model_type="Regular", event_id="event-1"):
    return {"ts": ts, "funding_rate": rate, "source_rate_type": source_type,
            "rate_type": model_type, "event_id": event_id}


def native(ms=MS, rate="-0.01", rate_type="Regular", mark="123.45"):
    row = {"symbol": "BTCUSDT", "fundingTime": ms, "fundingRate": rate, "markPrice": mark,
           "source_path": "raw/source.json", "source_sha256": "abcd"}
    if rate_type is not None:
        row["rateType"] = rate_type
    return row


def compare(fs=None, ns=None, complete=True):
    return audit.compare_window(JOB, pd.DataFrame(fs or [frozen()]), ns if ns is not None else [native()], complete)


def test_utc_milliseconds_are_unit_safe_and_timezone_required():
    assert audit.utc_ms(TS.as_unit("us")) == MS
    with pytest.raises(ValueError, match="Naive"):
        audit.utc_ms("2026-01-02")
    with pytest.raises(ValueError, match="roundtrip"):
        audit.utc_ms(TS + pd.Timedelta(nanoseconds=1))


def test_exact_match_retains_original_id_and_source_type():
    rows, boundary = compare()
    assert boundary == 0
    assert rows[0]["mapping_status"] == "MATCH_EXACT_NATIVE_KEY"
    assert rows[0]["original_event_id"] == "event-1"
    assert rows[0]["frozen_rate_type"] == "Unspecified"
    assert rows[0]["model_rate_type"] == "Regular"
    assert rows[0]["native_mark"] == 123.45


def test_unique_full_official_hour_can_map_subtwo_second_offset():
    rows, _ = compare(ns=[native(ms=MS + 17)])
    assert rows[0]["mapping_status"] == "MATCH_OFFICIAL_UNIQUE_HOUR"
    assert rows[0]["timestamp_delta_ms"] == 17
    assert rows[0]["native_ts"] != rows[0]["frozen_ts"]


def test_two_second_or_larger_offset_is_conflict_not_match():
    rows, _ = compare(ns=[native(ms=MS + 2000)])
    assert rows[0]["mapping_status"] == "TIME_CONFLICT"


def test_rate_rescaling_would_be_reported_not_normalized():
    rows, _ = compare(ns=[native(rate="-1")])
    assert rows[0]["mapping_status"] == "RATE_CONFLICT"
    assert rows[0]["native_rate"] == -1


def test_source_type_conflict_is_not_merged():
    rows, _ = compare(fs=[frozen(source_type="Regular")], ns=[native(rate_type="Special")])
    assert rows[0]["mapping_status"] == "TYPE_CONFLICT"


def test_regular_and_special_same_timestamp_remain_two_events():
    fs = [frozen(source_type="Regular", event_id="regular"),
          frozen(source_type="Special", model_type="Special", event_id="special")]
    ns = [native(rate_type="Regular"), native(rate_type="Special")]
    rows, _ = compare(fs=fs, ns=ns)
    assert len(rows) == 2
    assert {row["mapping_status"] for row in rows} == {"MATCH_EXACT_NATIVE_KEY"}
    assert {row["native_rate_type"] for row in rows} == {"Regular", "Special"}


def test_two_native_events_with_unknown_frozen_type_are_ambiguous():
    rows, _ = compare(ns=[native(rate_type="Regular"), native(rate_type="Special")])
    assert rows[0]["mapping_status"] == "AMBIGUOUS_OFFICIAL_HOUR"
    assert sum(row["mapping_status"] == "EXTRA_API_EVENT" for row in rows) == 2


def test_same_hour_nearby_events_not_arbitrarily_deduplicated():
    rows, _ = compare(ns=[native(ms=MS + 1), native(ms=MS + 5)])
    assert rows[0]["mapping_status"] == "AMBIGUOUS_OFFICIAL_HOUR"
    assert len(rows) == 3


def test_missing_and_extra_events_survive_outer_comparison():
    rows, _ = compare(ns=[native(ms=MS + 3600_000)])
    assert {row["mapping_status"] for row in rows} == {"MISSING_FROM_API", "EXTRA_API_EVENT"}


def test_empty_source_is_missing_not_zero_funding():
    rows, _ = compare(ns=[])
    assert rows[0]["mapping_status"] == "MISSING_FROM_API"
    assert rows[0]["native_rate"] is None


def test_incomplete_source_is_not_absence_proof():
    rows, _ = compare(ns=[], complete=False)
    assert rows[0]["mapping_status"] == "SOURCE_QUERY_INCOMPLETE"


@pytest.mark.parametrize("mark", [None, "", "0", "nan", "-12"])
def test_empty_invalid_mark_stays_missing(mark):
    rows, _ = compare(ns=[native(mark=mark)])
    assert rows[0]["native_mark"] is None


def test_funding_exactly_at_entry_is_not_paid_by_new_position():
    rows, boundary = compare(ns=[native(ms=JOB["holding_start_ms"]), native()])
    assert boundary == 1
    assert len(rows) == 1


def test_missing_api_rate_type_remains_explicit():
    rows, _ = compare(ns=[native(rate_type=None)])
    assert rows[0]["mapping_status"] == "API_TYPE_UNSPECIFIED"
    assert rows[0]["native_rate_type"] == "Unspecified"


def test_parse_checks_original_raw_hash_and_symbol(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    path = tmp_path / "raw.json"
    path.write_text(json.dumps([native()]))
    receipt = {"http_status": 200, "raw_path": "raw.json", "raw_sha256": audit.sha(path)}
    assert len(audit.parse_response(receipt, JOB)) == 1
    receipt["raw_sha256"] = "bad"
    with pytest.raises(ValueError, match="checksum"):
        audit.parse_response(receipt, JOB)


def test_parse_rejects_outside_request_window(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    path = tmp_path / "raw.json"
    path.write_text(json.dumps([native(ms=JOB["end_ms"] + 1)]))
    receipt = {"http_status": 200, "raw_path": "raw.json", "raw_sha256": audit.sha(path)}
    with pytest.raises(ValueError, match="outside"):
        audit.parse_response(receipt, JOB)


def test_access_denied_run_cannot_request_again(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    (tmp_path / "network-halt.json").write_text("{}")
    fetcher = audit.Fetcher(tmp_path, {})
    job = {**JOB, "window_id": 0, "url": "https://fapi.binance.com/fapi/v1/fundingRate?test"}
    with pytest.raises(RuntimeError, match="permanently closed"):
        fetcher.fetch(job, 0)
    assert fetcher.requests == 0


def test_http403_immediately_sets_global_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "ROOT", tmp_path)

    def denied(*args, **kwargs):
        raise audit.HTTPError("https://fapi.binance.com", 403, "Forbidden", {}, None)

    monkeypatch.setattr(audit, "urlopen", denied)
    fetcher = audit.Fetcher(tmp_path, {})
    job = {**JOB, "window_id": 0, "url": "https://fapi.binance.com/fapi/v1/fundingRate?test"}
    receipt = fetcher.fetch(job, 0)
    assert receipt["http_status"] == 403
    assert fetcher.stop.is_set()
    assert fetcher.requests == 1
