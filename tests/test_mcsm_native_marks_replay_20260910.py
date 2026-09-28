"""The audit overlay must not silently change rate, quantity, time or event scope."""
import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

DIRECTORY = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
sys.path.insert(0, str(DIRECTORY))
SPEC = importlib.util.spec_from_file_location("native_overlay_0910", DIRECTORY / "replay_mcsm_native_marks_20260910.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


@pytest.fixture
def frames():
    original = pd.DataFrame({"event_id": ["a", "b"], "symbol": ["AAA", "BBB"],
                             "funding_rate": [-.01, .02], "rate_type": ["Regular", "Regular"],
                             "native_mark": [None, None], "mark_center": [10., 20.],
                             "mark_low": [9., 19.], "mark_high": [11., 21.], "mark_source": ["proxy", "proxy"]})
    checked = pd.DataFrame({"original_event_id": ["a", "b"], "native_mark": [10.5, None],
                            "native_rate": [-.01, .02], "native_rate_type": ["Regular", "Regular"],
                            "mapping_status": ["MATCH_EXACT_NATIVE_KEY", "MATCH_OFFICIAL_UNIQUE_HOUR"],
                            "source_path": ["official-api.bin", "official-api.bin"],
                            "source_sha256": ["a" * 64, "a" * 64]})
    return original, checked


def test_only_valid_matched_native_marks_replace(frames):
    result, coverage = MOD.native_overlay(*frames)
    assert result.mark_center.tolist() == [10.5, 20.]
    assert result.mark_low.tolist() == [10.5, 19.]
    assert result.mark_high.tolist() == [10.5, 21.]
    assert coverage["usable_native_mark_events"] == 1


@pytest.mark.parametrize("bad", [0., -2., float("inf"), float("nan")])
def test_bad_native_mark_keeps_declared_proxy_not_zero(frames, bad):
    frames[1].loc[0, "native_mark"] = bad
    result, _ = MOD.native_overlay(*frames)
    assert result.mark_center.iloc[0] == 10.


@pytest.mark.parametrize("column,value", [("native_rate", .01), ("native_rate_type", "Special")])
def test_cannot_change_rate_or_type_under_a_mark_overlay(frames, column, value):
    frames[1].loc[0, column] = value
    with pytest.raises(ValueError, match="differs"):
        MOD.native_overlay(*frames)


def test_no_drop_or_duplicate_original_events(frames):
    with pytest.raises(ValueError, match="omitted"):
        MOD.native_overlay(frames[0], frames[1].iloc[:1])
    frames[1].loc[1, "original_event_id"] = "a"
    with pytest.raises(ValueError, match="exactly one"):
        MOD.native_overlay(*frames)


def test_unconfirmed_mapping_cannot_replace(frames):
    frames[1].loc[0, "mapping_status"] = "SOURCE_QUERY_INCOMPLETE"
    result, coverage = MOD.native_overlay(*frames)
    assert result.mark_center.iloc[0] == 10.
    assert coverage["independently_matched_source_events"] == 1


def test_known_source_conflict_blocks_even_when_mark_absent(frames):
    frames[1].loc[1, "mapping_status"] = "RATE_CONFLICT"
    with pytest.raises(ValueError, match="known source conflict"):
        MOD.native_overlay(*frames)


@pytest.mark.parametrize("column,value", [("source_path", ""), ("source_sha256", "wrong")])
def test_missing_provenance_blocks_replacement(frames, column, value):
    frames[1].loc[0, column] = value
    with pytest.raises(ValueError, match="provenance"):
        MOD.native_overlay(*frames)


def test_replacement_primary_provenance_does_not_point_to_old_proxy(frames):
    frames[0]["mark_raw_path"] = ["old-proxy.zip", "old-proxy.zip"]
    frames[0]["mark_raw_sha256"] = ["b" * 64, "b" * 64]
    result, _ = MOD.native_overlay(*frames)
    assert result.mark_raw_path.tolist() == ["official-api.bin", "old-proxy.zip"]
    assert result.mark_raw_sha256.tolist() == ["a" * 64, "b" * 64]


def test_native_mark_must_come_from_comparison_not_original_metadata(frames):
    frames[1].drop(columns="native_mark", inplace=True)
    with pytest.raises(ValueError, match="itself must supply"):
        MOD.native_overlay(*frames)


def test_wrong_symbol_is_rejected(frames):
    frames[1]["symbol"] = ["WRONG", "BBB"]
    with pytest.raises(ValueError, match="symbol differs"):
        MOD.native_overlay(*frames)


def test_native_time_must_stay_inside_actual_hold(frames):
    times = pd.to_datetime(["2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"])
    frames[0]["ts"] = times
    frames[0]["holding_start"] = times - pd.Timedelta(days=1)
    frames[0]["holding_end"] = times + pd.Timedelta(milliseconds=10)
    frames[1]["frozen_ts"] = times
    frames[1]["native_ts"] = times + pd.Timedelta(milliseconds=45)
    with pytest.raises(ValueError, match="actual holding window"):
        MOD.native_overlay(*frames)


def test_original_frozen_timestamp_metadata_does_not_hide_checked_time(frames):
    times = pd.to_datetime(["2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"])
    frames[0]["ts"] = times
    frames[0]["frozen_ts"] = times + pd.Timedelta(milliseconds=22)
    frames[1]["frozen_ts"] = times
    frames[1]["native_ts"] = times
    MOD.native_overlay(*frames)


@pytest.mark.parametrize("offset", [0.045, 3.0, -0.045])
def test_time_mapping_cannot_drift_or_cross_hour(frames, offset):
    times = pd.to_datetime(["2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"])
    frames[0]["ts"] = times
    frames[1]["frozen_ts"] = times
    frames[1]["native_ts"] = times + pd.Timedelta(seconds=offset)
    if offset == .045:
        MOD.native_overlay(*frames)
    else:
        with pytest.raises(ValueError, match="timestamp"):
            MOD.native_overlay(*frames)
