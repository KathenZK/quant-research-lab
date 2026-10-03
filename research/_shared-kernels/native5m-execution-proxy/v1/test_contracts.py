# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic parity/profit-only/strictROI tests; no new strategy historical outputs."""

import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
from account import replay


def frame():
    t = np.arange(576, dtype=np.int64) * 300000 + 1704067200000
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


def spec():
    return {
        "execution": {
            "initial_cash": 100000,
            "slippage_bps": 0,
            "cash_budget_fraction": 0.95,
            "exit_profit_only": True,
            "exit_profit_offset": 0,
        },
        "risk": {
            "stoploss": -0.1,
            "minimal_roi": {"0": 0.05, "20": 0.04, "30": 0.03, "60": 0.01},
        },
        "evaluation": {
            "start": "2024-01-01T00:00:00Z",
            "end_exclusive": "2024-01-03T00:00:00Z",
        },
    }


def test_profit_only_zero_loss_positive_and_risk():
    d = frame()
    d.loc[0, "entry_signal"] = 1
    d.loc[1, "exit_signal"] = 1
    c = {"fee_bps": 0, "delay_bars": 1}
    s = spec()
    assert len(replay(d, s, c)[2]) == 1  # exactzero not positive
    d.loc[2, ["open", "high", "low", "close"]] = 99
    assert len(replay(d, s, c)[2]) == 1  # loss signal blocked
    d.loc[2, ["open", "high", "low", "close"]] = 100.5
    t = replay(d, s, c)[2]
    assert len(t) == 2 and t.iloc[1].reason == "exit_signal"
    d.loc[2, ["open", "high", "low", "close"]] = 89
    t = replay(d, s, c)[2]
    assert len(t) == 2 and t.iloc[1].reason == "stoploss"  # not blocked by profit-only
    d = frame()
    d.loc[0, "entry_signal"] = 1
    d.loc[1, "entry_signal"] = 1
    d.loc[2, "high"] = 106
    assert replay(d, s, c)[2].iloc[1].reason == "roi"  # ignore_roi_if_entry_signalFalse


def test_fee_inclusive_profit_gate_and_later_slip():
    d = frame()
    d.loc[0, "entry_signal"] = 1
    d.loc[1, "exit_signal"] = 1
    s = spec()
    s["execution"]["slippage_bps"] = 2
    entry = 100 * 1.0002
    fee = 0.0008
    break_even = entry * (1 + fee) / (1 - fee)
    d.loc[2, ["open", "high", "low", "close"]] = break_even * 0.99999
    t = replay(d, s, {"fee_bps": 8, "delay_bars": 1})[2]
    assert len(t) == 1
    d.loc[2, ["open", "high", "low", "close"]] = break_even * 1.00001
    t = replay(d, s, {"fee_bps": 8, "delay_bars": 1})[2]
    assert len(t) == 2 and t.iloc[1].reason == "exit_signal"
    assert (
        t.iloc[1].notional - t.iloc[1].fee < t.iloc[0].notional + t.iloc[0].fee
    )  # rawmarkpositive, fillednetnegative due exit slip


def test_disabled_gate_matches_optimized_predecessor():
    p = Path(PREDECESSOR_PATH)
    module_spec = importlib.util.spec_from_file_location("predecessor", p)
    old = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(old)
    for profitflag in [False]:
        d = frame()
        d.loc[::17, "entry_signal"] = 1
        d.loc[7::19, "exit_signal"] = 1
        d["close"] = 100 + 0.8 * np.sin(np.arange(len(d)) / 7)
        d["high"] = np.maximum(d.open, d.close) + 0.5
        d["low"] = np.minimum(d.open, d.close) - 0.5
        s = spec()
        s["execution"]["exit_profit_only"] = profitflag
        for fee in [0, 8, 20]:
            c = {"fee_bps": fee, "delay_bars": 1}
            a = replay(d, s, c)
            b = old.replay(d, s, c)
            for k in [0, 1, 2]:
                assert a[k].equals(b[k])
            assert a[3] == b[3]


if __name__ == "__main__":
    import argparse
    import hashlib

    parser = argparse.ArgumentParser()
    parser.add_argument("--predecessor", required=True)
    PREDECESSOR_PATH = parser.parse_args().predecessor
    assert (
        hashlib.sha256(Path(PREDECESSOR_PATH).read_bytes()).hexdigest()
        == "daf10c6189d7523f99d851ae289ff70f0b2393342b3c6fa335c96cfb09550581"
    )
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name + ": PASS")
