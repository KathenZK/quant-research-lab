# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import numpy as np
import pandas as pd

from run_replay import features, replay, roi_at_open


def frame(count=30, price=100):
    time = np.arange(count, dtype=np.int64) * 14400000 + 1672531200000
    return pd.DataFrame(
        {
            "open_time": time,
            "close_time": time + 14400000 - 1,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
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
            "stoploss": -0.2,
            "minimal_roi": {"0": 0.5},
        },
        "evaluation": {
            "start": "2023-01-01T00:00:00Z",
            "end_exclusive": "2023-01-06T00:00:00Z",
        },
    }


def test_constant_roi_does_not_expire_on_minute_boundaries():
    schedule = contract()["risk"]["minimal_roi"]
    for minutes in [0, 1552, 1553, 2332, 3169, 4320]:
        assert roi_at_open(schedule, minutes * 60000, 0)[2] == 0.5


def test_collision_suppresses_entry_and_signal_exit():
    z = frame()
    z.loc[0, ["entry_signal", "exit_signal"]] = 1
    assert len(replay(z, contract(), {"fee_bps": 8, "delay_bars": 1})[2]) == 0
    z.loc[0, "exit_signal"] = 0
    z.loc[1, ["entry_signal", "exit_signal"]] = 1
    trades = replay(z, contract(), {"fee_bps": 8, "delay_bars": 1})[2]
    assert len(trades) == 1 and trades.iloc[0]["side"] == "BUY"


def test_stop_first_intrabar_ambiguity_and_cash():
    z = frame()
    z.loc[0, "entry_signal"] = 1
    z.loc[1, ["low", "high"]] = [50, 200]
    nav, _, trades, metrics = replay(z, contract(), {"fee_bps": 8, "delay_bars": 1})
    assert trades.iloc[1]["reason"] == "stoploss"
    assert metrics["intrabar_stop_roi_ambiguities"] == 1
    assert (nav.quantity == 0).all()
    assert np.isclose(
        nav.iloc[-1].equity, 5000 + trades.iloc[1].notional - trades.iloc[1].fee
    )


def test_terminal_mark_and_no_warmup_order():
    z = frame()
    z.loc[29, "entry_signal"] = 1
    assert len(replay(z, contract(), {"fee_bps": 8, "delay_bars": 1})[2]) == 0
    z.loc[0, "entry_signal"] = 1
    _, _, trades, metrics = replay(z, contract(), {"fee_bps": 8, "delay_bars": 1})
    assert len(trades) == 1 and metrics["final_quantity"] > 0


def test_halt_open_override_and_roi_age():
    z = frame()
    z.loc[0, "entry_signal"] = 1
    spec = copy.deepcopy(contract())
    nominal = int(z.iloc[1].open_time)
    spec["execution"]["open_execution_overrides"] = {
        str(nominal): {
            "effective_open_ms": nominal + 7200000,
            "basis": "synthetic_resume_proxy",
        }
    }
    trades = replay(z, spec, {"fee_bps": 8, "delay_bars": 1})[2]
    assert trades.iloc[0].execution_time_utc == "2023-01-01T06:00:00Z"


def test_48h_merge_no_future_fill_and_prefix_invariance():
    z = frame(720)
    z["close"] = 100 + np.arange(720) / 100
    full = features(z)
    assert full.ema21.first_valid_index() == 20
    assert full.sma48h50.first_valid_index() == 599
    assert full.iloc[:599].entry_signal.eq(0).all()
    for cut in [601, 607, 611, 612, 623, 624, 719]:
        prefix = features(z.iloc[:cut])
        changed = z.copy()
        changed.loc[cut:, ["open", "high", "low", "close"]] *= 3
        altered = features(changed)
        for column in ["ema8", "ema21", "sma48h50", "entry_signal", "exit_signal"]:
            assert np.array_equal(
                prefix[column], full.iloc[:cut][column], equal_nan=True
            )
            assert np.array_equal(
                altered.iloc[:cut][column], full.iloc[:cut][column], equal_nan=True
            )


def test_roi_exit_is_fee_inclusive_and_slip_adverse():
    z = frame()
    z.loc[0, "entry_signal"] = 1
    z.loc[1, "high"] = 160
    _, _, trades, _ = replay(z, contract(), {"fee_bps": 8, "delay_bars": 1})
    assert len(trades) == 2 and trades.iloc[1]["reason"] == "roi"
    cost = trades.iloc[0].notional + trades.iloc[0].fee
    received = trades.iloc[1].notional - trades.iloc[1].fee
    assert np.isclose(received / cost - 1, 0.4997)
