"""Small independent account tests; no production or strategy outcome reads."""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "research/asset-portfolios/1d-monthly-cs-momentum-long10/scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("weekly_audit_0911", SCRIPTS / "audit_mcsm_weekly_account_20260911.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def fixture_inputs():
    start, mid, end = [pd.Timestamp(x) for x in ["2021-03-01T00:15Z", "2021-03-03T00:15Z", "2021-03-05T00:15Z"]]
    h = pd.DataFrame({"entry_ts": [start, mid], "symbol": ["A", "A"], "weight": [1., 1.]})
    endpoints = pd.DataFrame([{"ts": t+offset, "symbol": "A", "open": p, "eligible": True, "research_window_valid": True}
                              for t, p in [(start, 100.), (mid, 120.), (end, 110.)]
                              for offset in [pd.Timedelta(0), -mod.MIN15]])
    days = pd.date_range(start.floor("D"), end.floor("D")-mod.DAY, freq="D")
    daily = pd.DataFrame({"ts": days, "symbol": "A", "close": [105., 119., 115., 111.], "eligible": True})
    return h, endpoints, daily, [start, mid, end], start, end


def test_initial_postcost_target_and_no_double_cost():
    post, q, turn = mod.solve_postcost(100000., {}, {"A": 100.}, {"A": 1.}, .0014)
    assert post == pytest.approx(100000/1.0014)
    assert q["A"] == pytest.approx(post/100)
    assert turn == pytest.approx(post)
    same, nq, turnover = mod.solve_postcost(post, q, {"A": 100.}, {"A": 1.}, .0014)
    assert same == pytest.approx(post)
    assert nq == pytest.approx(q)
    assert turnover == pytest.approx(0., abs=1e-8)


def test_fixed_quantity_between_rebalances_and_final_clearing():
    h, endpoints, daily, grid, start, end = fixture_inputs()
    r = mod.independent_replay(h, endpoints, daily, {}, grid, .0004, start, end)
    assert r["failure"] is None
    assert r["remaining_positions"] == {}
    q = 100000/1.0014/100
    expected_final = q*110*(1-.0014)
    assert r["nav"].equity.iloc[-1] == pytest.approx(expected_final)
    assert r["nav"].loc[r["nav"].ts.eq(pd.Timestamp("2021-03-02T00:00Z")), "equity"].iloc[0] == pytest.approx(q*105)
    assert r["trades"].loc[r["trades"].ts.eq(grid[1]), "traded_notional"].iloc[0] == pytest.approx(0, abs=1e-7)


def test_terminal_fee_once_no_market_slippage():
    h, endpoints, daily, grid, start, end = fixture_inputs()
    h = h.iloc[:1]
    ts = pd.Timestamp("2021-03-02T12:00Z")
    r = mod.independent_replay(h, endpoints, daily, {("A", ts): 90.}, grid, .0004, start, end)
    q = 100000/1.0014/100
    assert r["nav"].equity.iloc[-1] == pytest.approx(q*90 - q*90*.001)
    assert len(r["terminals"]) == 1
    assert r["nav"].slippage.iloc[-1] == pytest.approx((q*100)*.0004)


def test_first_missing_daily_is_not_skipped():
    h, endpoints, daily, grid, start, end = fixture_inputs()
    daily = daily.loc[daily.ts.ne(pd.Timestamp("2021-03-02T00:00Z"))]
    r = mod.independent_replay(h, endpoints, daily, {}, grid, .0004, start, end)
    assert r["failure"]["code"] == "DAILY_MARK_MISSING"
    assert r["failure"]["event_ts"] == pd.Timestamp("2021-03-03T00:00Z")
    assert r["nav"].ts.max() == pd.Timestamp("2021-03-02T00:00Z")
    assert len(r["trades"]) == 1


def test_invalid_prior_activity_blocks_even_with_valid_current_open():
    h, endpoints, daily, grid, start, end = fixture_inputs()
    endpoints.loc[endpoints.ts.eq(start-mod.MIN15), "eligible"] = False
    r = mod.independent_replay(h, endpoints, daily, {}, grid, .0004, start, end)
    assert r["failure"]["code"] == "PRIOR_ACTIVITY_INELIGIBLE"
    assert r["failure"]["event_ts"] == start
    assert len(r["nav"]) == 0


def test_current_bar_future_activity_does_not_filter_execution():
    h, endpoints, daily, grid, start, end = fixture_inputs()
    endpoints.loc[endpoints.ts.eq(start), ["eligible", "research_window_valid"]] = False
    r = mod.independent_replay(h, endpoints, daily, {}, grid, .0004, start, end)
    assert r["failure"] is None


def test_month_boundary_is_calendar_00_not_weekly_exit():
    nav = pd.DataFrame({"ts": pd.to_datetime(["2021-03-01T00:15Z", "2021-04-01T00:00Z", "2021-05-01T00:15Z"], utc=True),
                        "equity": [99900., 120000., 150000.], "price_pnl": [0., 20100., 50100.], "fees": 100., "slippage": 0.})
    m = mod.calendar_months(nav, pd.Timestamp("2021-03-01T00:15Z"), pd.Timestamp("2021-05-01T00:15Z"))
    assert len(m) == 2
    assert m['return'].tolist() == pytest.approx([.2, .25])
    assert m.pnl_usdt.sum() == pytest.approx(50000)
    assert m.price_pnl_usdt.sum() == pytest.approx(50100)
    assert m.fees_usdt.sum() == pytest.approx(100)


def test_numeric_comparator_refuses_missing_duplicate_and_nonfinite():
    a = pd.DataFrame({"ts": [1, 2], "equity": [1., 2.]})
    for bad in [a.iloc[:1], pd.concat([a, a.iloc[:1]]), a.assign(equity=[1., np.nan])]:
        with pytest.raises(ValueError):
            mod.compare_numeric(a, bad, ["ts"], ["equity"], "synthetic")


def test_complete_decision_schedule_cannot_skip_week():
    start, end = pd.Timestamp("2021-03-01T00:15Z"), pd.Timestamp("2021-04-01T00:15Z")
    rows, grid = [], {end}
    for strategy in ["B0", "M28", "W28", "W7"]:
        dates = ([start] if strategy in {"B0", "M28"} else list(pd.date_range(start, end-mod.DAY, freq="W-MON")))
        grid.update(dates)
        for entry, exit_ts in zip(dates, dates[1:]+[end]):
            rows += [{"strategy": strategy, "entry_ts": entry, "scheduled_exit_ts": exit_ts, "symbol": f"C{x}", "weight": .1} for x in range(10)]
    h = pd.DataFrame(rows)
    mod.verify_schedule(h, sorted(grid), start, end)
    missing = h.loc[~(h.strategy.eq("W28") & h.entry_ts.eq(pd.Timestamp("2021-03-15T00:15Z")))]
    with pytest.raises(ValueError, match="missing decision"):
        mod.verify_schedule(missing, sorted(grid), start, end)


def test_same_earliest_event_keeps_all_missing_symbols():
    h, endpoints, daily, grid, start, end = fixture_inputs()
    h = pd.concat([h.assign(symbol="A", weight=.5), h.assign(symbol="B", weight=.5)])
    endpoints = pd.concat([endpoints, endpoints.assign(symbol="B")])
    daily = pd.concat([daily, daily.assign(symbol="B")])
    endpoints = endpoints.loc[endpoints.ts.ne(start)]
    r = mod.independent_replay(h, endpoints, daily, {}, grid, .0004, start, end)
    assert {f["symbol"] for f in r["failure"]["same_event_failures"]} == {"A", "B"}
    assert {f["event_ts"] for f in r["failure"]["same_event_failures"]} == {start}
    assert len(r["nav"]) == 0


def test_leg_endpoint_cash_matches_full_account_price_pnl():
    h, endpoints, daily, grid, start, end = fixture_inputs()
    h["exit_ts"] = [grid[1], end]
    h["terminal"] = False
    r = mod.independent_replay(h, endpoints, daily, {}, grid, .0004, start, end)
    legs = mod.independent_leg_cash(h, r["trades"], endpoints, {})
    assert len(legs) == 2
    assert legs.period_price_pnl_usdt.sum() == pytest.approx(r["nav"].price_pnl.iloc[-1])
