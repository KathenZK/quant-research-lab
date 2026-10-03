#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare against original class plus pinned technical/qtpylib, not full engine."""

import argparse
import ast
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd
import talib.abstract as ta

from fetch_sources import fetch
from run_replay import features


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def original(source_dir):
    source_dir = Path(source_dir)
    fetch(source_dir)
    util = load_module(source_dir / "technical-util-1.5.3.py", "technical_pinned")
    qtpylib = load_module(source_dir / "qtpylib-indicators.py", "qtpylib_pinned")
    path = source_dir / "M0293-ReinforcedAverageStrategy.py"
    tree = ast.parse(path.read_text())
    tree.body = [
        node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    namespace = {
        "IStrategy": object,
        "DataFrame": pd.DataFrame,
        "ta": ta,
        "qtpylib": qtpylib,
        "resample_to_interval": util.resample_to_interval,
        "resampled_merge": util.resampled_merge,
        "timeframe_to_minutes": lambda value: {"4h": 240}[value],
    }
    exec(compile(tree, str(path), "exec"), namespace)
    strategy = namespace["ReinforcedAverageStrategy"]()
    assert (
        strategy.timeframe == "4h"
        and strategy.minimal_roi == {"0": 0.5}
        and strategy.stoploss == -0.2
    )
    assert strategy.trailing_stop is False and strategy.use_exit_signal is True
    assert (
        strategy.exit_profit_only is False
        and strategy.ignore_roi_if_entry_signal is False
    )
    return strategy


def compare(data, source_dir):
    port = features(data)
    strategy = original(source_dir)
    original_input = data.copy()
    original_input["date"] = pd.to_datetime(
        original_input.open_time, unit="ms", utc=True
    )
    reference = strategy.populate_indicators(original_input, {"pair": "BTC/USDT"})
    reference = strategy.populate_entry_trend(reference, {})
    reference = strategy.populate_exit_trend(reference, {})
    for a, b in [
        ("maShort", "ema8"),
        ("maMedium", "ema21"),
        ("resample_2880_sma", "sma48h50"),
    ]:
        assert np.array_equal(
            reference[a].to_numpy(), port[b].to_numpy(), equal_nan=True
        ), a
    for a, b in [("enter_long", "entry_signal"), ("exit_long", "exit_signal")]:
        assert np.array_equal(reference[a].fillna(0).astype(int), port[b]), a
    return {
        "id": "M0293",
        "status": "PASS",
        "rows": len(data),
        "consumed_indicators_equal": 3,
        "entry_exit_arrays_identical": True,
        "original_risk": {
            "minimal_roi": strategy.minimal_roi,
            "stoploss": strategy.stoploss,
            "trailing": False,
        },
        "resample_interval_minutes": strategy.resample_interval,
        "harness": "Original class methods and exact pinned technical/qtpylib; empty IStrategy base and explicit4h-to240 minute conversion; not full Freqtrade engine",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = compare(pd.read_csv(args.input), args.sources)
    with Path(args.output).open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))
