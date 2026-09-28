import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

PATH = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
sys.path.insert(0, str(PATH))
SPEC = importlib.util.spec_from_file_location("independent_exit_account", PATH / "audit_mcsm_single_exit_account_20260910.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_same_name_rebalance_does_not_charge_full_roundtrip():
    assert MOD.post_cost(100., {"A": 100.}, {"A": 1.}, .0014) == 100.


def test_cannot_certify_empty_or_duplicate_account_set():
    with pytest.raises(ValueError, match="eight"):
        MOD.check_complete_results([])
    rows = [{"scenario": s, "strategy": p, "slippage_rate": c} for s in ("price_only", "estimated_center")
            for p in ("baseline", "single_exit") for c in (.0004, .0008)]
    MOD.check_complete_results(rows)
    rows[-1] = rows[0]
    with pytest.raises(ValueError, match="eight"):
        MOD.check_complete_results(rows)


def test_missing_valuation_day_and_nonfinite_nav_rejected():
    start, end = pd.Timestamp("2020-03-01T00:15Z"), pd.Timestamp("2026-07-01T00:15Z")
    dates = sorted(set(pd.date_range(start, end, freq="MS")) | set(pd.date_range(start.floor("D") + pd.Timedelta(days=1), end.floor("D"))))
    nav = pd.DataFrame({"ts": dates, "equity": 100.})
    extra = pd.Series(dtype=float, index=pd.MultiIndex.from_tuples([], names=["ts", "symbol"]))
    MOD.check_complete_nav(nav, extra)
    with pytest.raises(ValueError, match="valuation clock"):
        MOD.check_complete_nav(nav.iloc[1:], extra)
    nav.loc[10, "equity"] = float("nan")
    with pytest.raises(ValueError, match="invalid NAV"):
        MOD.check_complete_nav(nav, extra)


@pytest.mark.parametrize("early", [False, True])
@pytest.mark.parametrize("funded", [False, True])
def test_endpoint_cash_and_daily_funding_for_early_or_natural_exit(early, funded):
    month = pd.Timestamp("2025-01-01T00:00Z")
    entry, end = month + pd.Timedelta(minutes=15), pd.Timestamp("2025-02-01T00:15Z")
    exit_time = pd.Timestamp("2025-01-16T00:15Z")
    day = pd.Timestamp("2025-02-01T00:00Z")
    h = pd.DataFrame([dict(month=month, symbol="A", weight=1., entry_ts=entry, exit_ts=end, terminal=False)])
    execution = pd.Series([100., 110.], index=pd.MultiIndex.from_tuples([(entry, "A"), (end, "A")]))
    extra = pd.Series([120.], index=pd.MultiIndex.from_tuples([(exit_time, "A")]))
    daily = pd.DataFrame({"close": [105.]}, index=pd.MultiIndex.from_tuples([(day - pd.Timedelta(days=1), "A")]))
    funding = pd.DataFrame({"symbol": ["A", "A"], "ts": pd.to_datetime(["2025-01-15T00:00Z", "2025-01-20T00:00Z"]),
                            "mark_center": [120., 90.], "funding_rate": [-.01, .005]})
    post = 100000. / 1.0014
    q = post / 100.
    fund_before = q * 1.2 if funded else 0.
    fund_all = q * .75 if funded else 0.
    early_equity = post + q * 20. + fund_before - q * 120. * .0014
    day_equity = early_equity if early else post + q * 5. + fund_all
    final = early_equity if early else post + q * 10. + fund_all - q * 110. * .0014
    boundary = early_equity if early else post + q * 20. + fund_before
    nav = pd.DataFrame({"ts": [entry, exit_time, day, end], "sample_kind": ["rebalance", "voluntary_exit" if early else "exit_boundary_mark", "daily", "rebalance"],
                        "equity": [post, boundary, day_equity, final]})
    if early:
        before_exit = pd.DataFrame({"ts": [exit_time], "sample_kind": ["exit_boundary_mark"], "equity": [post + q * 20. + fund_before]})
        nav = pd.concat([nav.iloc[:1], before_exit, nav.iloc[1:]], ignore_index=True)
    found = MOD.reconstruct(h, execution, daily, funding, {}, {(month, "A"): exit_time} if early else {}, extra, nav, .0004, funded)
    assert found["final_equity"] == pytest.approx(final, abs=1e-7)
    assert found["max_nav_absolute_error_usdt"] < 1e-7
    assert found["funding_pnl_usdt"] == pytest.approx(fund_before if early else fund_all)
    assert found["nav_clocks_tested"] == 4
    assert found["nav_rows_tested"] == (5 if early else 4)
    if early:
        with pytest.raises(ValueError, match="pre/post-exit"):
            MOD.reconstruct(h, execution, daily, funding, {}, {(month, "A"): exit_time}, extra,
                            nav.loc[nav.sample_kind.ne("exit_boundary_mark")], .0004, funded)
