"""Pre-performance synthetic execution contracts, no market files."""

import numpy as np
import pandas as pd
from run_replay import features, replay, roi_at_open


def frame(count=60):
    t = np.arange(count, dtype=np.int64) * 300000 + 1704067200000
    return pd.DataFrame(
        {
            "open_time": t,
            "close_time": t + 299999,
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
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
        "risk": {
            "stoploss": -0.318,
            "minimal_roi": {"0": 0.213, "27": 0.099, "60": 0.03, "164": 0},
        },
        "evaluation": {
            "start": "2024-01-01T00:00:00Z",
            "end_exclusive": "2024-01-01T05:00:00Z",
        },
    }


def test_roi_source_minutes_and_native_open_approximation():
    schedule = contract()["risk"]["minimal_roi"]
    for minute, expected in [
        (0, 0.213),
        (25, 0.213),
        (27, 0.099),
        (30, 0.099),
        (55, 0.099),
        (60, 0.03),
        (160, 0.03),
        (164, 0),
        (165, 0),
    ]:
        assert roi_at_open(schedule, minute * 60000, 0)[2] == expected
    z = frame()
    z.loc[0, "entry_signal"] = 1
    z.loc[6, "high"] = 110.1  # entry at5min ->25min old21.3% ROI
    z.loc[7, "high"] = 110.1  # age30min ->9.9% ROI
    trades = replay(z, contract(), {"fee_bps": 8, "delay_bars": 1})[2]
    assert len(trades) == 2 and trades.iloc[1].bar_index == 7


def test_stop_roi_ambiguity_and_inclusive_budget():
    z = frame()
    z.loc[0, "entry_signal"] = 1
    z.loc[1, ["low", "high"]] = [50, 200]
    nav, _, trades, m = replay(z, contract(), {"fee_bps": 8, "delay_bars": 1})
    assert (
        trades.iloc[1].reason == "stoploss" and m["intrabar_stop_roi_ambiguities"] == 1
    )
    assert np.isclose(trades.iloc[0].notional + trades.iloc[0].fee, 95000)
    assert np.isclose(
        nav.iloc[-1].equity, 5000 + trades.iloc[1].notional - trades.iloc[1].fee
    )


def test_fee_inclusive_roi_then_adverse_slip():
    z = frame()
    z.loc[0, "entry_signal"] = 1
    z.loc[1, "high"] = 130
    t = replay(z, contract(), {"fee_bps": 8, "delay_bars": 1})[2]
    net = (t.iloc[1].notional - t.iloc[1].fee) / (
        t.iloc[0].notional + t.iloc[0].fee
    ) - 1
    assert np.isclose(net, 1.213 * 0.9998 - 1)


def test_delay_terminal_and_no_warmup_order():
    z = frame()
    z.loc[59, "entry_signal"] = 1
    assert replay(z, contract(), {"fee_bps": 8, "delay_bars": 1})[2].empty
    z.loc[0, "entry_signal"] = 1
    t = replay(z, contract(), {"fee_bps": 8, "delay_bars": 2})[2]
    assert len(t) == 1 and t.iloc[0].bar_index == 2


def test_empty_sell_and_ema_causality():
    z = frame(1000)
    z["close"] = 100 + 6 * np.sin(np.arange(1000) / 19)
    full = features(z)
    assert not full.exit_signal.any() and full.ma26.first_valid_index() == 25
    for cut in [30, 650, 999]:
        pref = features(z.iloc[:cut])
        altered = z.copy()
        altered.loc[cut:, "close"] *= 2
        changed = features(altered)
        for col in ["ma12", "ma26", "umacd", "entry_signal", "exit_signal"]:
            assert np.array_equal(pref[col], full.iloc[:cut][col], equal_nan=True)
            assert np.array_equal(
                changed.iloc[:cut][col], full.iloc[:cut][col], equal_nan=True
            )


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    for name, test in tests:
        test()
        print(name + ": PASS")
