"""Actual original source class/default parameter lifecycle; offline only."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
from unittest.mock import patch
import numpy as np
import pandas as pd
from run_replay import features, load_input

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "b3a62e0d8a26024e7ab5f3613d0964e3954373bc3735c1ffd0678d84ce1b1e32"


def original(path):
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == SOURCE_SHA
    module_spec = importlib.util.spec_from_file_location("m0315_pinned_original", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    obj = module.UniversalMACD({"runmode": "backtest"})
    obj.ft_load_hyper_params()
    params = {k: p.value for k, p in obj.enumerate_parameters()}
    assert params == {
        "buy_umacd_min": -0.01416,
        "buy_umacd_max": -0.01176,
        "sell_umacd_min": -0.00707,
        "sell_umacd_max": -0.02323,
    }
    assert obj.timeframe == "5m" and obj.startup_candle_count == 30
    assert obj.minimal_roi == {"0": 0.213, "27": 0.099, "60": 0.03, "164": 0}
    assert obj.stoploss == -0.318 and obj.trailing_stop is False
    return obj, params


def compare(data, source):
    with patch.object(
        socket.socket, "connect", side_effect=RuntimeError("OFFLINE_ONLY")
    ):
        obj, params = original(source)
        d = data.copy()
        d["date"] = pd.to_datetime(d.open_time, unit="ms", utc=True)
        ref = obj.populate_indicators(d, {})
        ref = obj.populate_entry_trend(ref, {})
        ref = obj.populate_exit_trend(ref, {})
        port = features(data)
        for col in ["ma12", "ma26", "umacd"]:
            assert np.array_equal(ref[col], port[col], equal_nan=True), col
        for a, b in [("enter_long", "entry_signal"), ("exit_long", "exit_signal")]:
            assert np.array_equal(ref[a].fillna(0).astype(int), port[b])
        assert port.exit_signal.sum() == 0
    return {
        "id": "M0315",
        "status": "PASS",
        "rows": len(data),
        "source_sha256": SOURCE_SHA,
        "effective_parameters": params,
        "actual_Freqtrade_parameter_loading": True,
        "indicator_arrays_equal": True,
        "signal_arrays_equal": True,
        "empty_sell_interval_retained": True,
        "engine_used": False,
        "new_market_requests": 0,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    spec = json.loads((ROOT / "specs/M0315-first-replay.json").read_text())
    result = compare(load_input(a.input, spec), a.source)
    with Path(a.output).open("x") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(json.dumps(result, indent=2))
