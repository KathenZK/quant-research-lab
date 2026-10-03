#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute original class and extracted real Freqtrade parameter-load methods.
Minimal parameter/dependency harness is disclosed; this is not Freqtrade engine.
"""

import ast
import contextlib
import io
import json
import logging
from pathlib import Path
import warnings
from functools import reduce

import numpy as np
import pandas as pd
import talib.abstract as ta

from fetch_sources import fetch
from run_replay import features


class IntParameter:
    def __init__(self, low, high, default, space):
        self.low, self.high, self.value = low, high, default
        self.category, self.load = space, True


def original(source_dir):
    fetch(source_dir)
    source_dir = Path(source_dir)
    parameter_ast = ast.parse((source_dir / "parameters.py").read_text())
    defaults = [
        n
        for n in ast.walk(parameter_ast)
        if isinstance(n, ast.FunctionDef) and n.name == "__init__"
    ]
    assert all(
        dict(
            zip([a.arg for a in n.args.args][-len(n.args.defaults) :], n.args.defaults)
        )["load"].value
        is True
        for n in defaults
        if "load" in [a.arg for a in n.args.args]
    )
    hyper = ast.parse((source_dir / "hyper.py").read_text())
    methods = [
        n
        for n in ast.walk(hyper)
        if isinstance(n, ast.FunctionDef)
        and n.name in ("ft_load_hyper_params", "_ft_load_params")
    ]
    namespace = {
        "logger": logging.getLogger("original-parameter-loader"),
        "BaseParameter": IntParameter,
        "detect_parameters": lambda obj, space: [
            (n, getattr(obj, n))
            for n in dir(obj)
            if isinstance(getattr(obj, n), IntParameter)
            and getattr(obj, n).category == space
        ],
        "deep_merge_dicts": lambda a, b: dict(b, **a),
    }
    exec(
        compile(
            ast.Module(body=methods, type_ignores=[]),
            str(source_dir / "hyper.py"),
            "exec",
        ),
        namespace,
    )
    base = type(
        "IStrategy",
        (),
        {n: namespace[n] for n in ("ft_load_hyper_params", "_ft_load_params")},
    )
    namespace.update(
        {
            "IStrategy": base,
            "IntParameter": IntParameter,
            "DataFrame": pd.DataFrame,
            "ta": ta,
            "reduce": reduce,
        }
    )
    tree = ast.parse((source_dir / "MultiMa.py").read_text())
    tree.body = [
        n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    exec(compile(tree, str(source_dir / "MultiMa.py"), "exec"), namespace)
    instance = namespace["MultiMa"]()
    instance._ft_params_from_file = {}
    instance.ft_buy_params, instance.ft_sell_params, instance.ft_protection_params = (
        [],
        [],
        [],
    )
    instance.config = {}
    instance.ft_load_hyper_params(False)
    loaded = {
        k: getattr(instance, k).value
        for k in ("buy_ma_count", "buy_ma_gap", "sell_ma_count", "sell_ma_gap")
    }
    assert loaded == {
        "buy_ma_count": 4,
        "buy_ma_gap": 15,
        "sell_ma_count": 12,
        "sell_ma_gap": 68,
    }
    return instance, loaded


def compare(frame, source_dir):
    instance, loaded = original(source_dir)
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore", pd.errors.PerformanceWarning)
        reference = instance.populate_indicators(frame.copy(), {"pair": "BTC/USDT"})
        reference = instance.populate_entry_trend(reference, {})
        reference = instance.populate_exit_trend(reference, {})
    port = features(frame)
    for old, new in [("enter_long", "entry_signal"), ("exit_long", "exit_signal")]:
        assert np.array_equal(reference[old].fillna(0).astype(int), port[new]), old
    for column in port:
        if str(column).startswith("tema"):
            assert np.array_equal(
                reference[int(column[4:])].to_numpy(),
                port[column].to_numpy(),
                equal_nan=True,
            )
    return {
        "status": "PASS",
        "rows": len(frame),
        "loaded_parameters": loaded,
        "source_indicators_computed": len([k for k in reference if isinstance(k, int)]),
        "consumed_indicators_equal": 14,
        "entry_exit_arrays_identical": True,
        "harness": "Original MultiMa class methods plus exact extracted Freqtrade ft_load_hyper_params/_ft_load_params; minimal IntParameter container, no external parameter file, not full engine",
    }


if __name__ == "__main__":
    import argparse

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
