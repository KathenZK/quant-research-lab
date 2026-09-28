import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

PATH = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts/audit_mcsm_retained_native_marks_20260910.py"
SPEC = importlib.util.spec_from_file_location("retained_native_mark_audit", PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
MS = 1583049600000


def event(kind="Unspecified"):
    return SimpleNamespace(ts=pd.Timestamp(MS, unit="ms", tz="UTC"), symbol="MU/USDT:USDT", funding_rate=-.02, source_rate_type=kind)


def native(delta=0, kind="Regular", complete=True, rate=-.02):
    return {"native_ms": MS + delta, "native_rate": rate, "native_rate_type": kind, "native_mark": 1000, "complete_request_hour": complete}


def test_exact_native_time_is_preferred():
    exact = {("MU/USDT:USDT", MS): [native()]}
    hours = {("MU/USDT:USDT", MS // 3600000): [native(1)]}
    match, status = AUDIT.pick_match(event(), exact, hours)
    assert match["native_ms"] == MS
    assert status == "UNIQUE_EXACT_NATIVE_MS_RATE_TYPE"


def test_hour_match_requires_complete_response_and_two_seconds():
    key = ("MU/USDT:USDT", MS // 3600000)
    match, status = AUDIT.pick_match(event(), {}, {key: [native(2)]})
    assert match is not None
    assert "COMPLETE_REQUEST_HOUR" in status
    assert AUDIT.pick_match(event(), {}, {key: [native(2, complete=False)]})[0] is None
    assert AUDIT.pick_match(event(), {}, {key: [native(2001)]})[0] is None


def test_same_time_special_regular_must_not_merge():
    exact = {("MU/USDT:USDT", MS): [native(kind="Regular"), native(kind="Special")]}
    assert AUDIT.pick_match(event(), exact, {}) == (None, "AMBIGUOUS_EXACT_TIME")
    assert AUDIT.pick_match(event("Special"), exact, {})[0]["native_rate_type"] == "Special"


def test_same_hour_multiple_candidates_is_ambiguous():
    hours = {("MU/USDT:USDT", MS // 3600000): [native(1), native(2)]}
    assert AUDIT.pick_match(event(), {}, hours) == (None, "AMBIGUOUS_COMPLETE_HOUR")


def test_rate_mismatch_not_matched():
    assert AUDIT.pick_match(event(), {("MU/USDT:USDT", MS): [native(rate=.02)]}, {})[0] is None


def test_missing_and_nonpositive_mark_not_positive():
    assert not AUDIT.valid_mark(None)
    assert not AUDIT.valid_mark("")
    assert not AUDIT.valid_mark("0")
    assert not AUDIT.valid_mark("nan")
    assert AUDIT.valid_mark("0.25162")
