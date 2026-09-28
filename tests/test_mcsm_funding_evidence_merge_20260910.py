"""Typed API evidence may fill uncovered rows but must never hide source conflicts."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/merge_mcsm_funding_source_evidence_20260910.py"
SPEC = importlib.util.spec_from_file_location("mcsm_merge_test", SCRIPT)
merge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(merge)
TS = pd.Timestamp("2026-01-01T08:00:00Z")


def fixtures():
    old = {"original_event_id": "event", "symbol": "BTC/USDT:USDT", "frozen_ts": TS,
           "frozen_rate": -0.01, "model_rate_type": "Regular", "mapping_status": "SOURCE_QUERY_INCOMPLETE",
           "native_ts": pd.NaT, "native_rate": float("nan"), "native_rate_type": None,
           "native_mark": float("nan"), "source_path": None, "source_sha256": None,
           "timestamp_delta_ms": float("nan"), "source_retrieval_kind": "UNQUERIED_OR_REFUSED"}
    frame = pd.DataFrame([old]).set_index("original_event_id", drop=False)
    frame["native_ts"] = pd.to_datetime(frame.native_ts, utc=True)
    row = {"original_event_id": "event", "symbol": "BTC/USDT:USDT", "native_ts": TS,
           "native_rate": -0.01, "native_rate_type": "Regular", "native_mark": 100,
           "source_path": "saved.bin", "source_sha256": "abc"}
    return frame, row


def test_exact_api_replaces_only_uncovered_evidence():
    frame, row = fixtures()
    merge.merge_candidate(frame, row, "RETAINED_API")
    assert frame.loc["event", "mapping_status"] == "MATCH_EXACT_NATIVE_KEY"
    assert frame.loc["event", "native_mark"] == 100
    assert len(frame) == 1


def test_archive_unspecified_type_cannot_be_promoted_to_api_match():
    frame, row = fixtures()
    row["native_rate_type"] = "Unspecified"
    with pytest.raises(ValueError, match="type differs"):
        merge.merge_candidate(frame, row, "ARCHIVE")


def test_rate_conflict_is_never_hidden():
    frame, row = fixtures()
    row["native_rate"] = 0.01
    with pytest.raises(ValueError, match="identity/rate conflict"):
        merge.merge_candidate(frame, row, "API")


def test_original_conflict_status_cannot_be_replaced():
    frame, row = fixtures()
    frame.loc["event", "mapping_status"] = "EXTRA_API_EVENT"
    with pytest.raises(ValueError, match="hide an existing"):
        merge.merge_candidate(frame, row, "API")


def test_independent_native_mark_conflict_fails():
    frame, row = fixtures()
    merge.merge_candidate(frame, row, "API1")
    row["native_mark"] = 101
    with pytest.raises(ValueError, match="disagree on native mark"):
        merge.merge_candidate(frame, row, "API2")


def test_same_native_evidence_does_not_duplicate_event():
    frame, row = fixtures()
    merge.merge_candidate(frame, row, "API1")
    merge.merge_candidate(frame, row, "API2")
    assert len(frame) == 1
    assert frame.loc["event", "source_retrieval_kind"] == "API1"
