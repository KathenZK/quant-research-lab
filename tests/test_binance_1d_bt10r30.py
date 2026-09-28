from __future__ import annotations
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

BASE = (
    Path(__file__).resolve().parents[1]
    / "research/asset-portfolios/1d-bull-top10-30d-rotation/scripts"
)


def load(name):
    spec = importlib.util.spec_from_file_location(name, BASE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


r = load("replay_p0")
b = load("build_p0_inputs")


def fixture(days=75):
    dates = pd.date_range("2020-01-01", periods=days * 6, freq="4h", tz="UTC")
    shape = (len(dates), 12)
    m = {c: np.full(shape, 100.0) for c in ["open", "close", "high", "low"]}
    m.update(
        dates=dates,
        symbols=[f"C{i:02d}/USDT:USDT" for i in range(12)],
        eligible=np.ones(shape, bool),
        segment=np.zeros(shape, dtype=int),
    )
    signal = pd.date_range("2020-01-01", periods=days, freq="1D", tz="UTC")
    market = pd.DataFrame({"signal_time": signal, "state_valid": True, "bull": True})
    d = pd.DataFrame(
        [
            {
                "signal_time": t,
                "symbol": s,
                "pool": True,
                "momentum_rank": i + 1,
                "mom30": -0.1,
            }
            for t in signal
            for i, s in enumerate(m["symbols"])
        ]
    )
    return d, market, m


def test_exact_thirty_days_no_midhold_market_exit():
    d, market, m = fixture()
    market.loc[1:29, "bull"] = False
    actions, dec = r.plan(d, market, m, "bull_top10")
    assert list(actions) == [1, 181, 361]
    assert all(len(x) == 10 for x in actions.values())
    assert dec[0]["execution_time"] - dec[0]["signal_time"] == pd.Timedelta(hours=4)
    # Negative formation momentum is still allowed under the user's literal Top10 rule.
    assert dec[0]["filled"] == m["symbols"][:10]


def test_cash_checks_daily_after_due_exit():
    d, market, m = fixture()
    market.loc[30:31, "bull"] = False
    actions, _ = r.plan(d, market, m, "bull_top10")
    assert actions[181] == []
    assert len(actions[193]) == 10
    assert 187 not in actions
    assert 373 in actions


def test_ungated_calendar_stays_thirty_days():
    d, market, m = fixture()
    market["bull"] = False
    actions, _ = r.plan(d, market, m, "always_top10")
    assert list(actions) == [1, 181, 361]


def test_bad_entry_slot_stays_cash_no_eleventh_replacement():
    d, market, m = fixture()
    m["eligible"][1, 0] = False
    actions, dec = r.plan(d, market, m, "bull_top10")
    assert actions[1] == list(range(1, 10))
    assert dec[0]["cancelled"] == [m["symbols"][0]]
    result, h, _, _ = r.simulate(m, {1: actions[1]}, "bull_top10", 4)
    assert np.isclose(h.cash.iloc[0], 10000)
    assert result["open_trades"] == 9


def test_cost_and_budget_reconcile_at_exact_exit():
    _, _, m = fixture(35)
    m["open"][181, :] = 120
    result, h, tx, cycles = r.simulate(
        m, {1: list(range(10)), 181: []}, "bull_top10", 4
    )
    factor = r.leg_factor(100, 120, 4)
    assert np.isclose(h.budget_mark_ex_funding.iloc[-1], 100000 * factor)
    assert np.isclose(result["full_price_contribution_pct"], (factor - 1) * 100)
    assert len(tx) == 10 and len(cycles) == 1
    assert ((tx.exit_time - tx.entry_time) == pd.Timedelta(days=30)).all()
    assert h.cash.min() >= -1e-6


def test_holding_gap_invalidates_account_not_a_zero_return():
    _, _, m = fixture(40)
    m["eligible"][40, 0] = False
    result, h, tx, _ = r.simulate(m, {1: list(range(10)), 181: []}, "bull_top10", 4)
    assert not result["path_valid"]
    assert result["full_price_contribution_pct"] is None
    assert len(tx[tx.status.eq("closed")]) == 0
    assert h.time.max() == m["dates"][40]
    rounds, _ = r.rounds(m, {1: list(range(10))}, "bull_top10", 4)
    assert rounds.status.iloc[0] == "holding_gap"
    assert pd.isna(rounds.return_ex_funding.iloc[0])


def test_terminal_short_round_is_marked_not_realized():
    _, _, m = fixture(20)
    result, _, tx, cycles = r.simulate(m, {1: list(range(10))}, "bull_top10", 4)
    assert result["closed_trades"] == 0 and result["open_trades"] == 10
    assert cycles.empty and tx.status.eq("censored").all()
    rounds, _ = r.rounds(m, {1: list(range(10))}, "bull_top10", 4)
    assert rounds.status.iloc[0] == "right_censor"


def test_no_stop_even_with_large_intrahold_drawdown():
    _, _, m = fixture(35)
    for c in ["open", "close", "high", "low"]:
        m[c][10:100, :] = 30
    result, h, tx, _ = r.simulate(m, {1: list(range(10)), 181: []}, "bull_top10", 4)
    assert tx.exit_time.eq(m["dates"][181]).all()
    assert h.positions.max() == 10
    assert result["drawdown"]["mdd_pct"] < -69


def test_daily_features_prefix_causal_and_gap_reset():
    n = 140
    ts = pd.date_range("2020-01-01", periods=n, freq="1D", tz="UTC")
    f = pd.DataFrame(
        {
            "symbol": "BTC/USDT:USDT",
            "ts": ts,
            "close": np.arange(n) + 100.0,
            "quote_volume": 20e6,
            "eligible": True,
            "research_window_valid": True,
            "research_segment_id": "btc",
        }
    )
    whole = b.daily_features(f)
    prefix = b.daily_features(f.iloc[:110])
    pd.testing.assert_frame_equal(whole.iloc[:110], prefix)
    f.loc[100:, "research_segment_id"] = "btc-new"
    broken = b.daily_features(f)
    assert broken.loc[100:, "ma50"].isna().all()
    assert not broken.loc[100:, "formation_valid"].any()
