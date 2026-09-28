"""No candidate rule calls: closed-day ranks, union, later exits and audit pins."""
import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("mcsm_round_audit", SCRIPTS / "audit_mcsm_round_20260911.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def fixture():
    month = pd.Timestamp("2024-01-01T00:00Z")
    first = pd.Timestamp("2024-01-15T00:15Z")
    later = first + pd.Timedelta(days=4)
    holdings = pd.DataFrame([{"month": month, "symbol": str(i), "exit_ts": month + pd.offsets.MonthBegin(1)} for i in range(10)])
    original = pd.DataFrame([{"month": month, "symbol": "9", "exit_ts": first},
                             {"month": month, "symbol": "8", "exit_ts": later}])
    signal_day = first.floor("D") - pd.Timedelta(days=1)
    rows = []
    for i in range(10):
        rows += [{"symbol": str(i), "ts": signal_day - pd.Timedelta(days=7), "close": 100.},
                 {"symbol": str(i), "ts": signal_day, "close": 100. + i}]
    return month, first, later, holdings, original, pd.DataFrame(rows)


def test_x5_is_union_not_quota_and_keeps_later_exit():
    month, first, later, h, original, daily = fixture()
    plan = audit.independent_plan(h, original, daily, "x5")
    assert len(plan) == 7
    assert {s for (m, s), t in plan.items() if t == first} == {"0", "1", "2", "3", "4", "9"}
    assert plan[(month, "8")] == later


def test_x10_leaves_no_later_exit():
    _, first, _, h, original, daily = fixture()
    plan = audit.independent_plan(h, original, daily, "x10")
    assert len(plan) == 10 and set(plan.values()) == {first}


def test_future_close_not_used():
    _, first, _, h, original, daily = fixture()
    expected = audit.independent_plan(h, original, daily, "x5")
    future = pd.DataFrame([{"symbol": str(i), "ts": first.floor("D"), "close": 1e10 / (i + 1)} for i in range(10)])
    assert audit.independent_plan(h, original, pd.concat([daily, future]), "x5") == expected


def test_missing_exact_past_day_fails():
    _, _, _, h, original, daily = fixture()
    with pytest.raises(KeyError):
        audit.independent_plan(h, original, daily.iloc[1:], "x5")


def test_empty_original_no_exits():
    _, _, _, h, original, daily = fixture()
    assert audit.independent_plan(h, original.iloc[:0], daily, "x10") == {}


def test_hash_mismatch_fails(tmp_path):
    # pytest owns this isolated text fixture, never research evidence.
    p = tmp_path / "input"
    p.write_text("unchanged")
    audit.verify_hashes({"input": audit.sha(p)}, tmp_path)
    with pytest.raises(ValueError, match="changed evidence"):
        audit.verify_hashes({"input": "0" * 64}, tmp_path)
