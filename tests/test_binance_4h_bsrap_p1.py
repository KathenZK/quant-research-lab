"""P1日线可用时刻、标签完整性、入场状态机及预算成交时序。"""

import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

BASE = (
    Path(__file__).resolve().parents[1]
    / "research/asset-portfolios/4h-bull-strong-rsi-atr-pullback/scripts"
)


def module(name):
    spec = importlib.util.spec_from_file_location(name, BASE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


b = module("build_p1_inputs")
s = module("research_p1_states")
r = module("replay_p1_entries")


def daily(n=180):
    x = 100 + np.arange(n) * 0.2 + np.sin(np.arange(n))
    return pd.DataFrame(
        {
            "symbol": "BTC/USDT:USDT",
            "ts": pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC"),
            "open": x,
            "high": x + 2,
            "low": x - 2,
            "close": x + 0.1,
            "quote_volume": 1e8,
            "eligible": True,
            "research_window_valid": True,
            "research_segment_id": "a",
        }
    )


def market_frame(n=8, ns=1, stop=90.0):
    rows = []
    dates = pd.date_range("2026-01-01", periods=n, freq="4h", tz="UTC")
    for j in range(ns):
        for i, t in enumerate(dates):
            rows.append(
                {
                    "symbol": f"COIN{j}/USDT:USDT",
                    "ts": t,
                    "open": 100.0,
                    "low": 99.5,
                    "close": 105.0,
                    "stop_band": stop,
                    "rsi14": 20.0,
                    "daily_mom30": 0.5 - j * 0.01,
                    "eligible": True,
                    "feature_valid": True,
                    "admission": True,
                    "atr_down": True,
                    "research_segment_id": f"{j}-one",
                }
            )
    return pd.DataFrame(rows)


def test_daily_indicators_prefix_invariant_and_segment_warmup():
    f = daily()
    out = b.daily_features(f)
    pd.testing.assert_frame_equal(out.iloc[:120], b.daily_features(f.iloc[:120]))
    f.loc[100:, "research_segment_id"] = "new"
    out = b.daily_features(f)
    assert out.ma50.iloc[100:149].isna().all()
    assert not out.feature_valid.iloc[100:159].any()
    assert out.feature_valid.iloc[159]


def test_daily_state_is_available_only_after_close_and_not_stale():
    symbol = "BTC/USDT:USDT"
    d = pd.DataFrame(
        {
            "symbol": symbol,
            "available_at": pd.to_datetime(["2026-01-01T00:00Z", "2026-01-02T00:00Z"]),
            "pool": True,
            "strong": True,
            "bull": [False, True],
            "state": ["DOWN", "UP"],
            "mom30": [0.1, 0.9],
            "median_quote20": 1e8,
        }
    )
    f = pd.DataFrame(
        {
            "symbol": symbol,
            "ts": pd.to_datetime(
                ["2026-01-01T16:00Z", "2026-01-01T20:00Z", "2026-01-02T20:00Z"]
            ),
            "feature_valid": True,
        }
    )
    out = b.attach_daily(f, d)
    assert out.daily_mom30.iloc[0] == 0.1
    assert out.daily_mom30.iloc[1] == 0.9
    assert out.admission.tolist() == [False, True, False]
    assert out.state.iloc[2] == "UNKNOWN"


def test_breadth_uses_only_liquid_pool_not_all_observed_symbols():
    d = pd.DataFrame(
        {
            "symbol": ["BTC/USDT:USDT"] + [f"C{i}/USDT:USDT" for i in range(40)],
            "ts": pd.Timestamp("2026-01-01T00:00Z"),
            "available_at": pd.Timestamp("2026-01-02T00:00Z"),
            "feature_valid": True,
            "median_quote20": [1e8] * 21 + [1.0] * 20,
            "mom30": 0.1,
            "close": [110.0] * 11 + [90.0] * 10 + [500.0] * 20,
            "ma50": 100.0,
            "ma100": 90.0,
            "ma50_lag5": 95.0,
            "research_segment_id": [str(i) for i in range(41)],
        }
    )
    _, m = b.market_and_strength(d)
    assert m.pool_size.iloc[0] == 21
    assert m.breadth.iloc[0] == pytest.approx(11 / 21)
    assert m.state.iloc[0] == "BTC_UP_NARROW"


def test_labels_enter_next_open_and_have_per_horizon_masks():
    f = b.daily_features(daily(80))
    f["pool"] = True
    f["strong"] = True
    f["state"] = "BTC_UP_BROAD"
    f["bull"] = True
    f["state_valid"] = True
    f["strong_last5_count"] = 5
    cutoff = f.ts.max() + pd.Timedelta(days=1)
    short = s.label_frame(f, 3, cutoff)
    long = s.label_frame(f, 14, cutoff)
    i = 70
    assert short.valid.iloc[i]
    assert not long.valid.iloc[i]
    assert short.gross_return.iloc[i] == pytest.approx(
        f.open.iloc[i + 4] / f.open.iloc[i + 1] - 1
    )
    f.loc[72:, "research_segment_id"] = "new"
    assert not s.label_frame(f, 3, cutoff).valid.iloc[i]


def test_pullback_opens_once_per_oversold_episode_after_stop():
    f = market_frame(n=9)
    f.loc[f.index == 1, "low"] = 89.0
    f.loc[f.index == 4, "rsi14"] = 40.0
    tx, _, summ = r.simulate(r.build_matrix(f), "rsi14_pullback", 4)
    assert tx.entry_time.tolist() == [
        pd.Timestamp("2026-01-01T04:00Z"),
        pd.Timestamp("2026-01-02T00:00Z"),
    ]
    assert summ["counters"]["filled"] == 2


def test_reclaim_waits_until_cross_and_requires_admission_at_cross():
    f = market_frame()
    f.loc[2:, "rsi14"] = 31.0
    tx, _, _ = r.simulate(r.build_matrix(f), "rsi14_reclaim", 4)
    assert len(tx) == 1 and tx.entry_time.iloc[0] == pd.Timestamp("2026-01-01T12:00Z")
    f.loc[2, "admission"] = False
    tx, _, _ = r.simulate(r.build_matrix(f), "rsi14_reclaim", 4)
    assert tx.empty


def capital_case(open_stop=False):
    f = market_frame(n=5, ns=6, stop=99.0)
    idx = (f.symbol.eq("COIN5/USDT:USDT")) & (
        f.ts.eq(pd.Timestamp("2026-01-01T00:00Z"))
    )
    f.loc[idx, "admission"] = False
    first = f.symbol.eq("COIN0/USDT:USDT")
    f.loc[first & f.ts.ge(pd.Timestamp("2026-01-01T04:00Z")), "admission"] = False
    at2 = first & f.ts.eq(pd.Timestamp("2026-01-01T08:00Z"))
    f.loc[at2, "low"] = 98.0
    if open_stop:
        f.loc[at2, "open"] = 98.5
    return f


def test_intrabar_exit_cash_cannot_pay_for_same_bar_open_entry():
    tx, _, _ = r.simulate(r.build_matrix(capital_case()), "direct", 4)
    sixth = tx[tx.symbol.eq("COIN5/USDT:USDT")]
    assert len(sixth) == 1
    assert sixth.entry_time.iloc[0] == pd.Timestamp("2026-01-01T12:00Z")


def test_open_exit_cash_is_available_before_new_open_entries():
    tx, _, _ = r.simulate(r.build_matrix(capital_case(True)), "direct", 4)
    sixth = tx[tx.symbol.eq("COIN5/USDT:USDT")]
    assert sixth.entry_time.iloc[0] == pd.Timestamp("2026-01-01T08:00Z")
    stopped = tx[tx.symbol.eq("COIN0/USDT:USDT")].iloc[0]
    assert stopped.exit_raw == 98.5


def test_budget_enforces_notional_individual_and_total_stop_risk():
    tx, hist, summ = r.simulate(r.build_matrix(market_frame(ns=20)), "direct", 8)
    assert summ["max_positions_seen"] <= 5
    assert (hist.cash_ex_funding >= -1e-7).all()
    assert (tx.notional <= 0.2 * tx.initial_budget_equity + 1e-7).all()
    assert (tx.entry_risk <= 0.005 * tx.initial_budget_equity + 1e-7).all()
    assert (
        tx.risk_before + tx.entry_risk <= 0.02 * tx.initial_budget_equity + 1e-7
    ).all()


def test_holding_gap_invalidates_capital_path_without_fake_sale():
    f = market_frame().drop(index=2)
    tx, _, summ = r.simulate(r.build_matrix(f), "direct", 4)
    assert not summ["path_valid"]
    assert summ["price_contribution_pct_initial_budget"] is None
    assert tx.status.eq("censored").all()


def test_same_bar_new_stop_is_not_applied_retroactively():
    f = market_frame(n=4)
    f.loc[1, ["low", "stop_band", "close"]] = [92.0, 100.0, 110.0]
    f.loc[2, ["open", "low"]] = [108.0, 99.0]
    tx, _, _ = r.simulate(r.build_matrix(f), "rsi14_pullback", 4)
    assert tx.exit_bar_open.iloc[0] == pd.Timestamp("2026-01-01T08:00Z")
    assert tx.exit_raw.iloc[0] == 100.0


def test_stop_marketable_at_close_exits_next_open_even_on_gap_up():
    f = market_frame(n=4)
    f.loc[1, ["stop_band", "close"]] = [106.0, 105.0]
    f.loc[2, ["open", "low"]] = [112.0, 109.0]
    tx, _, _ = r.simulate(r.build_matrix(f), "rsi14_pullback", 4)
    assert tx.reason.iloc[0] == "new_stop_marketable_next_open"
    assert tx.exit_raw.iloc[0] == 112.0
