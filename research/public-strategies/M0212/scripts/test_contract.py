"""Synthetic boundary cases: index anchor and six completed holding bars."""

import importlib.util
from pathlib import Path
import pandas as pd

spec = importlib.util.spec_from_file_location(
    "m0212", Path(__file__).with_name("run_replay_v2.py")
)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def test_previous_execution_bar_anchor():
    dates = pd.date_range("2022-12-01", periods=50, freq="D", tz="UTC")
    df = pd.DataFrame(
        {
            "open_time": dates.as_unit("ms").asi8,
            "open": 100.0,
            "close": 100.0,
            "low": 99.0,
            "volume": 100.0,
        }
    )
    df.loc[32, ["close", "low", "volume"]] = [90.0, 89.0, 50.0]
    _, tx = engine.run(df)
    assert tx.iloc[0]["date"] == "2023-01-03"  # close index32=Jan2 -> next open
    assert tx.iloc[0]["signal_index"] == 32


def test_six_completed_bars_cap():
    dates = pd.date_range("2022-12-01", periods=60, freq="D", tz="UTC")
    close = [200 - i for i in range(60)]
    df = pd.DataFrame(
        {
            "open_time": dates.as_unit("ms").asi8,
            "open": close,
            "close": close,
            "low": [c - 0.5 for c in close],
            "volume": 100.0,
        }
    )
    _, tx = engine.run(df)
    assert tx.iloc[0]["date"] == "2023-01-02"
    assert tx.iloc[1]["date"] == "2023-01-08"  # Jan2..7 six closes, Jan8 open exit
    assert tx.iloc[1]["side"] == "SELL"


def test_pending_lag_retains_order():
    dates = pd.date_range("2022-12-01", periods=60, freq="D", tz="UTC")
    close = [200 - i for i in range(60)]
    df = pd.DataFrame(
        {
            "open_time": dates.as_unit("ms").asi8,
            "open": close,
            "close": close,
            "low": [c - 0.5 for c in close],
            "volume": 100.0,
        }
    )
    _, tx = engine.run(df, lag=2)
    assert tx.iloc[0]["date"] == "2023-01-03"
    assert tx.iloc[1]["date"] == "2023-01-10"  # six closes then second next open
