"""来源分钟数据与估算边界的最小非策略测试。"""
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("mcsm_est_funding", ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/build_mcsm_baseline_estimated_funding_20260909.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def blob(row=None):
    return json.dumps([row or [60000, "100", "102", "99", "101", "0", 119999, "0", 60, "0", "0", "0"]]).encode()


def test_official_minute_values_preserved():
    result = MODULE.parse_mark_rows(blob(), False)
    assert tuple(result.iloc[0][["mark_open", "mark_low", "mark_high"]]) == (100, 99, 102)


@pytest.mark.parametrize("value", [None, "", "0", "-1", "nan", "inf"])
def test_missing_native_mark_never_zero_or_finite_proxy(value):
    assert not MODULE.valid_mark(value)


def test_out_of_grid_minute_rejected():
    with pytest.raises(AssertionError):
        MODULE.parse_mark_rows(blob([60001, "100", "102", "99", "101", "0", 120000, "0", 60, "0", "0", "0"]), False)


def test_invalid_ohlc_rejected():
    with pytest.raises(AssertionError):
        MODULE.parse_mark_rows(blob([60000, "100", "98", "99", "101", "0", 119999, "0", 60, "0", "0", "0"]), False)


def test_empty_source_not_zero_funding():
    with pytest.raises(ValueError, match="empty official mark response"):
        MODULE.parse_mark_rows(b"[]", False)


def test_corrected_real_projection_roundtrips_every_utc_minute():
    base = ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-long10/artifacts/baseline-estimate-20260909/funding"
    path = base / "observed-held-events-v2.parquet"
    if not path.exists():
        pytest.skip("research evidence not distributed in this checkout")
    events = pd.read_parquet(path)
    assert pd.to_datetime(events.minute_ms, unit="ms", utc=True).eq(events.ts.dt.floor("min")).all()
    assert not events.duplicated(["symbol", "ts", "rate_type"]).any()
    assert ((events.ts > events.holding_start) & (events.ts <= events.holding_end)).all()
    unspecified = events.source_rate_type.eq("Unspecified")
    assert events.loc[unspecified, "rate_type_assumption"].eq("ESTIMATE_ASSUMES_REGULAR_UNSPECIFIED_SOURCE").all()
    assert events.loc[unspecified, "rate_type"].eq("Regular").all()
