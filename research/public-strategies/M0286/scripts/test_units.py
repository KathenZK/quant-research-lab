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
            "stoploss": -0.345,
            "minimal_roi": {"0": 0.523, "1553": 0.123, "2332": 0.076, "3169": 0},
        },
        "evaluation": {
            "start": "2023-01-01T00:00:00Z",
            "end_exclusive": "2023-01-06T00:00:00Z",
        },
    }


def test_minute_roi_boundaries_and_grid_proxy():
    roi = contract()["risk"]["minimal_roi"]
    assert roi_at_open(roi, 1552 * 60000, 0) == (1552, 0, 0.523)
    assert roi_at_open(roi, 1553 * 60000, 0) == (1553, 1553, 0.123)
    assert roi_at_open(roi, 6 * 240 * 60000, 0)[2] == 0.523
    assert roi_at_open(roi, 7 * 240 * 60000, 0)[2] == 0.123
    assert roi_at_open(roi, 14 * 240 * 60000, 0)[2] == 0


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


def test_tema_nan_no_future_fill_and_partial_exit_comparisons():
    z = frame(2400)
    z["close"] = 100 + np.sin(np.arange(2400) / 20) * 5
    feat = features(z)
    assert feat.tema45.first_valid_index() == 132
    assert feat.tema136.first_valid_index() == 405
    assert feat.tema748.first_valid_index() == 2241
    assert feat.iloc[:405].exit_signal.eq(0).all()
    assert feat.iloc[405:2241].exit_signal.sum() > 0
    prefix = features(z.iloc[:1000])
    assert np.array_equal(feat.iloc[:1000].entry_signal, prefix.entry_signal)
    assert np.array_equal(feat.iloc[:1000].exit_signal, prefix.exit_signal)
