"""Joint daily/hourly research eligibility must never bridge bad execution bars."""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

_PATH = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts/prepare_inputs.py"
_SPEC = importlib.util.spec_from_file_location("ma7_gen_prepare_inputs", _PATH)
module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(module)


def frames(days=70):
    times = pd.date_range("2025-01-01", periods=24 * days, freq="h", tz="UTC")
    h = pd.DataFrame({"ts": times, "symbol": "TEST/USDT:USDT", "open": 10.0,
                      "high": 11.0, "low": 9.0, "close": 10.2, "volume": 1.0,
                      "quote_volume": 10.0, "trade_count": 1,
                      "eligible": True, "research_segment_id": "TEST#1",
                      "research_window_valid": True})
    d = h.set_index("ts").resample("D").agg({"symbol": "first", "open": "first", "high": "max",
        "low": "min", "close": "last", "volume": "sum", "quote_volume": "sum",
        "trade_count": "sum", "eligible": "all", "research_segment_id": "first",
        "research_window_valid": "all"}).reset_index()
    return d, h


def test_one_bad_hour_invalidates_day_and_restarts_full_warmup():
    d, h = frames()
    h.loc[35 * 24 + 12, "eligible"] = False
    joint, audit = module.joint_daily_projection(d, h, 29)
    assert audit["daily_valid_but_hourly_incomplete_days"] == 1
    assert audit["joint_segments"] == 2
    assert joint.loc[35, "eligible"]
    assert not joint.loc[35, "joint_eligible"]
    assert not joint.loc[36:63, "research_window_valid"].any()
    assert joint.loc[64, "research_window_valid"]
    assert joint.loc[34, "joint_segment_id"] != joint.loc[36, "joint_segment_id"]


def test_missing_hour_breaks_joint_day_without_filling_or_joining():
    d, h = frames()
    h = h.drop(index=35 * 24 + 12).reset_index(drop=True)
    joint, audit = module.joint_daily_projection(d, h, 29)
    assert audit["joint_segments"] == 2
    assert joint.loc[35, "hour_rows"] == 23
    assert not joint.loc[35, "joint_eligible"]


def test_aggregation_conflict_fails_closed():
    d, h = frames()
    d.loc[12, "high"] = 12.0
    with pytest.raises(ValueError, match="aggregation mismatch: high"):
        module.joint_daily_projection(d, h, 29)


def test_full_input_preserves_433_trade_day_window():
    d, h = frames(462)
    joint, audit = module.joint_daily_projection(d, h, 29)
    window = {"window_id": "main", "input_start": d.ts.iloc[0].isoformat(),
              "trade_start": d.ts.iloc[29].isoformat(),
              "end": (d.ts.iloc[-1] + pd.Timedelta(days=1)).isoformat()}
    segments = module.segment_rows(joint, window, 29)
    assert audit["joint_complete_feature_windows"] == 434
    assert len(segments) == 1
    assert segments[0]["trading_days"] == 433
    assert segments[0]["full_window_contiguous"]
    assert not segments[0]["boundary_end_due_to_data"]
