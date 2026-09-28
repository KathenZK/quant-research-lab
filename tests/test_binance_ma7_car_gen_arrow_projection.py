"""Arrow-backed real-world schema must keep invalid-hour segment boundaries."""
from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts"))
from prepare_inputs_v4 import joint_daily_projection  # noqa: E402


@pytest.mark.parametrize("price", [10.0, 0.000001])
def test_arrow_boolean_segments_reset_and_warm_from_full_observed_days(price):
    h = pd.DataFrame({"ts": pd.date_range("2025-01-01", periods=70*24, freq="h", tz="UTC"),
        "symbol": "TEST/USDT:USDT", "open": price, "high": price*1.1, "low": price*.9,
        "close": price, "volume": 1.0, "quote_volume": price, "trade_count": 1,
        "eligible": True, "research_segment_id": "TEST#1", "research_window_valid": True})
    d = h.set_index("ts").resample("D").agg({"symbol": "first", "open": "first", "high": "max",
        "low": "min", "close": "last", "volume": "sum", "quote_volume": "sum",
        "trade_count": "sum", "eligible": "all", "research_segment_id": "first",
        "research_window_valid": "all"}).reset_index()
    h.loc[35*24+12, "eligible"] = False
    d, h = d.convert_dtypes(dtype_backend="pyarrow"), h.convert_dtypes(dtype_backend="pyarrow")
    joint, audit = joint_daily_projection(d, h, 29)
    assert audit["joint_segments"] == 2
    assert int(joint.joint_eligible.sum()) == 69
    assert not joint.loc[35:63, "research_window_valid"].any()
    assert joint.loc[64:, "research_window_valid"].all()
    assert joint.loc[34, "joint_segment_id"] != joint.loc[36, "joint_segment_id"]
