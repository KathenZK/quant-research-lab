"""Synthetic CMF/ROI/proxy boundary tests before performance; no market files."""

import numpy as np
import pandas as pd
from run_replay import features, replay, roi_at_open


def frame(count=576):
    t = np.arange(count, dtype=np.int64) * 300000 + 1704067200000
    return pd.DataFrame(
        {
            "open_time": t,
            "close_time": t + 299999,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
            "entry_signal": 0,
            "exit_signal": 0,
        }
    )


def contract():
    return {
        "execution": {
            "initial_cash": 100000,
            "slippage_bps": 2,
            "cash_budget_fraction": 0.95,
        },
        "risk": {"stoploss": -0.05, "minimal_roi": {"0": 0.01}},
        "evaluation": {
            "start": "2024-01-01T00:00:00Z",
            "end_exclusive": "2024-01-03T00:00:00Z",
        },
    }


def test_cmf_nan_zero_and_signed_states():
    d = frame(100)
    f = features(d)
    assert f.cmf.iloc[:20].isna().all() and (f.cmf.iloc[20:] == 0).all()
    assert not f.entry_signal.any() and not f.exit_signal.any()
    d.loc[40, ["high", "low", "close"]] = 100
    z = features(d)
    assert z.cmf.iloc[40:61].isna().all() and np.isfinite(z.cmf.iloc[61])
    d = frame(100)
    d.loc[30:50, "volume"] = 0
    z = features(d)
    assert (
        np.isnan(z.cmf.iloc[50])
        and np.isfinite(z.cmf.iloc[49])
        and np.isfinite(z.cmf.iloc[51])
    )
    d = frame(100)
    d["close"] = 99.5
    assert features(d).entry_signal.iloc[20:].eq(1).all()
    d["close"] = 100.5
    assert features(d).exit_signal.iloc[20:].eq(1).all()


def test_strict_roi_equal_does_not_exit_nextafter_does():
    d = frame()
    d.loc[0, "entry_signal"] = 1
    s = contract()
    s["execution"]["slippage_bps"] = 0
    case = {"fee_bps": 0, "delay_bars": 1}
    # high==target on everybar; no strict greater trigger.
    t = replay(d, s, case)[2]
    assert len(t) == 1
    d.loc[2, "high"] = np.nextafter(101.0, np.inf)
    t = replay(d, s, case)[2]
    assert len(t) == 2 and t.iloc[1].bar_index == 2 and t.iloc[1].reason == "roi"
    for age in [0, 27, 164, 10000]:
        assert roi_at_open({"0": 0.01}, age * 60000, 0)[2] == 0.01


def test_proxy_fill_is_not_native_limit_execution():
    d = frame()
    d["low"] = 100.0
    d["high"] = 100.0
    d.loc[0, "entry_signal"] = 1
    t = replay(d, contract(), {"fee_bps": 8, "delay_bars": 1})[2]
    assert t.iloc[0].side == "BUY" and t.iloc[0].fill_price > 100
    illustrative_limit = 99.0
    assert (
        d.loc[1:, "low"].min() > illustrative_limit
    )  # native resting99buy cannot fill this path
    # Gap below stop: proxy sells at gap open, whereas a95sell-limit cannot execute below95.
    d.loc[2, ["open", "high", "low", "close"]] = 90.0
    t = replay(d, contract(), {"fee_bps": 8, "delay_bars": 1})[2]
    assert (
        t.iloc[1].reason == "stoploss"
        and t.iloc[1].phase == "open_gap"
        and t.iloc[1].fill_price < 90
    )
    assert d.loc[2, "high"] < 95.0


def test_loss_signal_exit_and_stop_order_priority():
    d = frame()
    d["high"] = 100.0
    d.loc[0, "entry_signal"] = 1
    d.loc[1, "exit_signal"] = 1
    d.loc[2, ["open", "high", "low", "close"]] = 94.0
    t = replay(d, contract(), {"fee_bps": 8, "delay_bars": 1})[2]
    assert (
        t.iloc[1].reason == "exit_signal"
        and t.iloc[1].fill_price < t.iloc[0].fill_price
    )
    d.loc[1, "exit_signal"] = 0
    d.loc[1, ["high", "low"]] = [120, 90]
    m = replay(d, contract(), {"fee_bps": 8, "delay_bars": 1})
    assert (
        m[2].iloc[1].reason == "stoploss" and m[3]["intrabar_stop_roi_ambiguities"] == 1
    )


def test_budget_cost_and_delay_terminal():
    d = frame()
    d["high"] = 100.0
    d.loc[0, "entry_signal"] = 1
    t = replay(d, contract(), {"fee_bps": 8, "delay_bars": 2})[2]
    assert t.iloc[0].bar_index == 2 and np.isclose(
        t.iloc[0].notional + t.iloc[0].fee, 95000
    )
    d = frame()
    d.loc[575, "entry_signal"] = 1
    assert replay(d, contract(), {"fee_bps": 8, "delay_bars": 1})[2].empty
    d = frame()
    d.loc[0, "entry_signal"] = 1
    d.loc[1, "high"] = 103
    t = replay(d, contract(), {"fee_bps": 8, "delay_bars": 1})[2]
    assert np.isclose(
        (t.iloc[1].notional - t.iloc[1].fee) / (t.iloc[0].notional + t.iloc[0].fee) - 1,
        1.01 * 0.9998 - 1,
    )


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_"):
            func()
            print(name + ": PASS")
