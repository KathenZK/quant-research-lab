"""纯合成测试：特征独立公式、候选重置、三臂时序及逐日现金守恒。"""
import copy
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


SPEC = importlib.util.spec_from_file_location("mttc_engine_test", Path(__file__).parents[1]/"engine.py")
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)

CONFIG = {
    "direction": "LONG", "policies": ["A", "B", "C"], "start": "2019-01-01T00:00:00Z",
    "end": "2021-01-01T00:00:00Z", "warmup": 60, "momentum_window": 20, "atr_window": 14,
    "strength_threshold": 2., "pullback_atr": 1., "stop_atr": 2., "wait_days": 20,
    "fixed_hold_days": 20, "max_hold_days": 60, "slot_risk_fraction": .1, "slot_notional_fraction": .9,
}
BASE = {"id": "base", "fee": .001, "slippage": .0004, "daily_carry": 0.}


def source(n=170, symbol="SYNTH", break_at=None):
    rng = np.random.default_rng(47003)
    close = 100*np.exp(np.cumsum(rng.normal(.005, .01, n)))
    opening = close*(1+.002*np.sin(np.arange(n)))
    f = pd.DataFrame({"symbol": symbol, "ts": pd.date_range("2020-01-01", periods=n, tz="UTC"),
                      "open": opening, "high": np.maximum(opening, close)+2,
                      "low": np.minimum(opening, close)-2, "close": close,
                      "volume": 10., "quote_volume": np.arange(n, dtype=float)+100,
                      "eligible": True, "research_segment_id": f"{symbol}#1"})
    if break_at is not None:
        f.loc[break_at, "eligible"] = False
        f.loc[break_at, "research_segment_id"] = None
        f.loc[break_at+1:, "research_segment_id"] = f"{symbol}#2"
    f["research_segment_id"] = f.research_segment_id.astype("string")
    f["research_window_valid"] = f.eligible & f.groupby("research_segment_id").cumcount().ge(59)
    return f


def unit(n=150, at=70, atr=1.):
    dates = pd.date_range("2020-01-01", periods=n, tz="UTC")
    g = pd.DataFrame({"symbol": "UNIT", "segment": "UNIT#1", "ts": dates,
                      "local_index": np.arange(n), "eligible": True,
                      "open": 100., "high": 101., "low": 99., "close": 100., "r20": .1})
    origin = {"origin_id": "unit-origin", "symbol": "UNIT", "segment": "UNIT#1",
              "origin_ts": dates[at], "origin_index": at, "atr": atr, "liquidity": 1000.,
              "first_observable": False}
    return g, origin


def setbar(g, index, *, opening=None, close=None, high=None, low=None, r20=None):
    if opening is not None:
        g.loc[index, "open"] = opening
    if close is not None:
        g.loc[index, "close"] = close
    op, cl = g.loc[index, ["open", "close"]]
    g.loc[index, "high"] = max(op, cl)+1 if high is None else high
    g.loc[index, "low"] = min(op, cl)-1 if low is None else low
    if r20 is not None:
        g.loc[index, "r20"] = r20


def run(g, origin, policy, cost=None, config=None):
    return engine.simulate_opportunity(g, origin, policy, cost or BASE, config or CONFIG)


def assert_accounting(result):
    s, d = result["summary"], result["daily"]
    real = d.loc[d.has_bar]
    np.testing.assert_allclose(real.open_after, real.open_before-real.fee_open-real.slippage_open, atol=1e-14)
    np.testing.assert_allclose(real.close_value, real.open_after+real.qty_open_after*(real.close-real.open)-real.carry_close, atol=1e-14)
    np.testing.assert_allclose(real.close_value, real.cash_close+real.qty_close*real.close, atol=1e-14)
    assert s["fees"] == pytest.approx(d.fee_open.sum())
    assert s["carry"] == pytest.approx(d.carry_close.sum())
    assert s["holding_days"] == d.holding_day.sum()
    assert s["last_value"] == d.close_value.iloc[-1]
    if s["normal_complete"]:
        assert d.release_open.iloc[-1] and s["last_qty"] == 0
        assert s["return"] == s["last_value"]-1


def test_features_match_direct_returns_sample_std_simple_atr_and_quote_volume():
    f = source()
    p = engine.build_panel({"SYNTH": f}, CONFIG)
    for t in (59, 80, 130, 169):
        c = f.close.to_numpy()
        returns = [np.log(c[j]/c[j-1]) for j in range(t-19, t+1)]
        r20 = np.log(c[t]/c[t-20])
        sigma = np.std(returns, ddof=1)
        tr = [max(f.high.iloc[j]-f.low.iloc[j], abs(f.high.iloc[j]-c[j-1]), abs(f.low.iloc[j]-c[j-1])) for j in range(t-13, t+1)]
        assert p.at[t, "r20"] == r20
        assert p.at[t, "sigma20"] == pytest.approx(sigma, rel=1e-14)
        assert p.at[t, "strength"] == pytest.approx(r20/(sigma*np.sqrt(20)), rel=1e-14)
        assert p.at[t, "atr14"] == pytest.approx(sum(tr)/14, rel=1e-14)
        assert p.at[t, "liquidity20"] == f.quote_volume.iloc[t-19:t+1].mean()
    assert not p.feature_valid.iloc[:59].any()
    assert p.feature_valid.iloc[59:].all()


def test_atr_is_simple_mean_and_finite_shock_expires_after_fourteen_bars():
    f = source()
    f.loc[65, "high"] += 1000
    p = engine.build_panel({"SYNTH": f}, CONFIG)
    regular = source()
    q = engine.build_panel({"SYNTH": regular}, CONFIG)
    assert p.at[65, "atr14"]-q.at[65, "atr14"] == pytest.approx(1000/14)
    assert p.at[78, "atr14"]-q.at[78, "atr14"] == pytest.approx(1000/14)
    assert p.at[79, "atr14"] == q.at[79, "atr14"]


def test_segment_resets_features_and_preserves_ineligible_original_row():
    f = source(n=200, break_at=90)
    p = engine.build_panel({"SYNTH": f}, CONFIG)
    assert len(p) == len(f) and not p.at[90, "eligible"] and p.at[90, "local_index"] == -1
    assert p.at[91, "local_index"] == 0
    assert not p.feature_valid.iloc[91:150].any() and p.at[150, "feature_valid"]
    assert pd.isna(p.at[90, "segment"])


def test_origin_rearms_only_at_nonpositive_return_not_merely_strength_below_two():
    p = engine.build_panel({"SYNTH": source(n=90)}, CONFIG)
    p["strength"], p["r20"] = 1., .1
    p.loc[[59, 61, 63, 89], "strength"] = 3.
    p.loc[62, "r20"] = 0.
    p.loc[88, "r20"] = -.1
    origins = engine.build_origins(p, CONFIG)
    assert origins.origin_index.tolist() == [59, 63, 89]
    assert origins.first_observable.tolist() == [True, False, False]
    assert origins.iloc[-1].origin_ts == p.ts.iloc[-1]
    assert origins.origin_id.nunique() == 3


def test_features_and_origins_are_prefix_invariant_and_keep_terminal_candidate():
    f = source(n=210)
    full = engine.build_panel({"SYNTH": f}, CONFIG)
    prefix = engine.build_panel({"SYNTH": f.iloc[:120].copy()}, CONFIG)
    columns = ["r20", "sigma20", "strength", "atr14", "liquidity20", "feature_valid"]
    pd.testing.assert_frame_equal(full.loc[:119, columns], prefix[columns])
    ofull, oprefix = engine.build_origins(full, CONFIG), engine.build_origins(prefix, CONFIG)
    pd.testing.assert_frame_equal(ofull.loc[ofull.origin_ts <= prefix.ts.iloc[-1]].reset_index(drop=True), oprefix)


def test_zero_volatility_cannot_create_a_strength_candidate():
    f = source(n=100)
    f[["open", "close"]], f["high"], f["low"] = 100., 101., 99.
    p = engine.build_panel({"SYNTH": f}, CONFIG)
    assert not p.feature_valid.any()
    assert engine.build_origins(p, CONFIG).empty


@pytest.mark.parametrize("policy,days", [("A", 20), ("B", 60)])
def test_immediate_entry_and_exact_open_exit_dates(policy, days):
    g, origin = unit()
    result = run(g, origin, policy)
    s, d = result["summary"], result["daily"]
    assert s["entry_ts"] == g.ts.iloc[71]
    assert s["exit_ts"] == g.ts.iloc[71+days]
    assert s["holding_days"] == days
    assert s["exit_reason"] == f"TIME_{days}"
    assert not d.iloc[0].entry_open and d.iloc[0].origin_row
    assert d.iloc[1].entry_open and d.iloc[-1].exit_open and d.iloc[-1].release_open
    assert s["qty"] > 0 and s["last_qty"] == 0
    assert_accounting(result)


def test_a_ignores_trend_failure_b_exits_next_open_and_both_share_entry():
    g, origin = unit()
    g.loc[75, "r20"] = 0.
    a, b = run(g, origin, "A"), run(g, origin, "B")
    assert a["summary"]["entry_price"] == b["summary"]["entry_price"]
    assert a["summary"]["exit_index"] == 91
    assert b["summary"]["exit_index"] == 76 and b["summary"]["exit_reason"] == "TREND_FAILURE"


@pytest.mark.parametrize("policy,stop_day", [("A", 90), ("B", 130)])
def test_close_risk_stop_beats_trend_and_time_and_fills_next_gap_open(policy, stop_day):
    g, origin = unit()
    setbar(g, stop_day, close=97., r20=-.1)
    setbar(g, stop_day+1, opening=90., close=90.)
    result = run(g, origin, policy)
    s = result["summary"]
    assert s["exit_index"] == stop_day+1 and s["exit_reason"] == "RISK_STOP"
    assert s["exit_price"] == 90*(1-BASE["slippage"])
    assert s["exit_price"] != s["stop_price"]
    assert_accounting(result)


def test_intraday_low_does_not_fill_a_close_only_stop():
    g, origin = unit()
    g.loc[75, "low"] = 1.
    result = run(g, origin, "A")
    assert result["summary"]["exit_reason"] == "TIME_20"
    assert result["summary"]["intraday_stop_breach"]
    assert result["daily"].loc[result["daily"].local_index == 75, "intraday_stop_breach"].item()


def test_trend_exit_has_priority_over_common_maximum_time():
    g, origin = unit()
    g.loc[130, "r20"] = 0.
    result = run(g, origin, "B")
    assert result["summary"]["exit_index"] == 131
    assert result["summary"]["exit_reason"] == "TREND_FAILURE"


def test_c_waits_for_causal_pullback_then_later_previous_high_breakout():
    g, origin = unit()
    setbar(g, 71, close=103.)
    setbar(g, 72, close=102.)
    setbar(g, 73, close=104.)
    result = run(g, origin, "C")
    s = result["summary"]
    assert s["pullback_index"] == 72 and s["restart_index"] == 73
    assert s["entry_index"] == 74
    assert s["exit_index"] == 131 and s["holding_days"] == 57
    assert s["stop_price"] == s["entry_price"]-2*origin["atr"]
    assert_accounting(result)


def test_c_never_triggered_is_zero_return_but_not_removed():
    g, origin = unit()
    result = run(g, origin, "C")
    s = result["summary"]
    assert not s["entered"] and s["normal_complete"] and s["return"] == 0.
    assert s["terminal_status"] == "WAIT_EXPIRED" and s["release_ts"] == g.ts.iloc[90]
    assert s["fees"] == s["carry"] == 0 and s["holding_days"] == 0
    assert_accounting(result)


def test_c_trend_invalidation_beats_same_day_restart_and_releases_next_open():
    g, origin = unit()
    setbar(g, 71, close=99.)
    setbar(g, 72, close=102., r20=0.)
    result = run(g, origin, "C")
    s = result["summary"]
    assert not s["entered"] and s["restart_index"] is None
    assert s["terminal_status"] == "WAIT_TREND_FAILURE" and s["release_ts"] == g.ts.iloc[73]
    assert s["return"] == 0.


def test_last_permitted_restart_day_can_enter_at_expiry_open():
    g, origin = unit()
    setbar(g, 88, close=99.)
    setbar(g, 89, close=102.)
    result = run(g, origin, "C")
    assert result["summary"]["restart_index"] == 89
    assert result["summary"]["entry_index"] == 90
    assert result["summary"]["terminal_status"] == "COMPLETED_TRADE"


def test_c_does_not_use_a_restart_on_the_expired_twentieth_close():
    g, origin = unit()
    setbar(g, 89, close=99.)
    setbar(g, 90, close=102.)
    result = run(g, origin, "C")
    assert not result["summary"]["entered"]
    assert result["summary"]["terminal_status"] == "WAIT_EXPIRED"


@pytest.mark.parametrize("atr", [1., 20.])
def test_quantity_cash_reserve_and_planned_risk_caps(atr):
    g, origin = unit(atr=atr)
    s = run(g, origin, "A")["summary"]
    expected = min(.9/(100.04*1.001), .1/(2*atr))
    assert s["qty"] == pytest.approx(expected, rel=1e-14, abs=1e-17)
    assert s["entry_fee"] == pytest.approx(expected*100.04*.001, rel=1e-14, abs=1e-17)
    assert expected*100.04*1.001 <= .9+1e-15


def test_carry_charged_on_entry_and_held_closes_but_not_exit_open_day():
    g, origin = unit()
    cost = dict(BASE, id="carry", daily_carry=.001)
    result = run(g, origin, "A", cost)
    s, d = result["summary"], result["daily"]
    assert s["carry"] == pytest.approx(s["qty"]*100*.001*20)
    assert d.loc[d.entry_open, "carry_close"].iloc[0] > 0
    assert d.loc[d.exit_open, "carry_close"].iloc[0] == 0
    expected = s["qty"]*(100*(1-.0004)-100*(1+.0004))-s["fees"]-s["carry"]
    assert s["return"] == pytest.approx(expected, abs=1e-15)
    assert_accounting(result)


def test_carry_shortfall_preserves_negative_cash_pressure_without_fictitious_borrow_fill():
    g, origin = unit()
    g.loc[72:, ["open", "close"]] = 1000.
    g.loc[72:, "high"], g.loc[72:, "low"] = 1001., 999.
    cost = dict(BASE, id="carry", daily_carry=.001)
    result = run(g, origin, "B", cost)
    assert result["summary"]["cost_cash_shortfall"]
    assert result["summary"]["minimum_cash"] < 0
    assert result["daily"].entry_open.sum() == result["daily"].exit_open.sum() == 1
    assert_accounting(result)


def test_administrative_last_bar_candidate_is_pending_not_a_zero_return_completed_case():
    g, origin = unit(n=71)
    config = dict(CONFIG, end=(g.ts.iloc[-1]+engine.DAY).isoformat())
    result = run(g, origin, "A", config=config)
    s = result["summary"]
    assert not s["entered"] and not s["normal_complete"] and s["unresolved"]
    assert s["terminal_status"] == "ADMIN_END_PENDING_ENTRY"
    assert np.isnan(s["return"]) and s["observed_return"] == 0
    assert len(result["daily"]) == 1 and not result["daily"].release_open.any()


@pytest.mark.parametrize("administrative", [False, True])
def test_unobserved_next_exit_does_not_sell_at_last_close(administrative):
    g, origin = unit(n=77)
    setbar(g, 76, close=97.)
    config = dict(CONFIG, end=(g.ts.iloc[-1]+engine.DAY).isoformat()) if administrative else CONFIG
    result = run(g, origin, "A", config=config)
    s, d = result["summary"], result["daily"]
    assert s["entered"] and not s["normal_complete"] and s["unresolved"]
    assert s["exit_ts"] is None and s["exit_fee"] == 0 and s["last_qty"] == s["qty"] > 0
    assert not d.release_open.any() and not d.exit_open.any()
    assert np.isnan(s["return"]) and np.isfinite(s["observed_return"])
    if administrative:
        assert not d.data_gap.any() and s["terminal_status"] == "ADMIN_END_POSITION"
    else:
        assert d.iloc[-1].data_gap and not d.iloc[-1].has_bar
        assert d.iloc[-1].ts == g.ts.iloc[-1]+engine.DAY
        assert not d.iloc[-2].data_gap
        assert s["terminal_status"] == "UNRESOLVED_POSITION"
    assert_accounting(result)


def test_missing_data_while_waiting_releases_cash_but_never_counts_normal_zero_profit():
    g, origin = unit(n=75)
    result = run(g, origin, "C")
    s, d = result["summary"], result["daily"]
    assert not s["entered"] and s["released"] and not s["normal_complete"]
    assert s["terminal_status"] == "DATA_GAP_CANCELLED" and np.isnan(s["return"])
    assert s["observed_return"] == 0 and s["last_cash"] == 1
    assert d.release_open.iloc[-1] and d.data_gap.iloc[-1]


def test_prefix_preserves_all_unit_cash_and_actions_before_new_future_information():
    g, origin = unit()
    cost = dict(BASE, id="carry", daily_carry=.001)
    full = run(g, origin, "B", cost)
    truncated = g.iloc[:90].copy()
    config = dict(CONFIG, end=(truncated.ts.iloc[-1]+engine.DAY).isoformat())
    prefix = run(truncated, origin, "B", cost, config)
    expected = full["daily"].loc[full["daily"].local_index < 90].reset_index(drop=True)
    pd.testing.assert_frame_equal(expected, prefix["daily"])


@pytest.mark.parametrize("problem", ["mask", "duplicate", "quote", "wrong_identity"])
def test_invalid_frames_are_rejected_instead_of_silently_repaired(problem):
    f = source()
    if problem == "mask":
        f.loc[10, "research_window_valid"] = True
    elif problem == "duplicate":
        f.loc[70, "ts"] = f.at[69, "ts"]
    elif problem == "quote":
        f = f.drop(columns="quote_volume")
    else:
        f.loc[50, "symbol"] = "FOREIGN"
    with pytest.raises(ValueError):
        engine.build_panel({"SYNTH": f}, CONFIG)


def test_nonmatching_origin_and_wrong_cost_are_rejected():
    g, origin = unit()
    bad = copy.deepcopy(origin)
    bad["origin_ts"] += engine.DAY
    with pytest.raises(ValueError, match="origin"):
        run(g, bad, "A")
    with pytest.raises(ValueError, match="slippage"):
        run(g, origin, "A", dict(BASE, slippage=-.001))
