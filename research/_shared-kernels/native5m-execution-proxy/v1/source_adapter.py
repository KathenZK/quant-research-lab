# SPDX-License-Identifier: GPL-3.0-or-later
"""Native strategy methods and independently written Boolean rules; no market requests."""

import importlib.util
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from freqtrade.resolvers import StrategyResolver


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(path, name):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def instance(spec, sources):
    sources = Path(sources)
    rid = spec["record_id"]
    source = sources / f"{rid}.py"
    assert sha(source) == spec["source"]["sha256"]
    qt = sources / "qtpylib.py"
    assert sha(qt) == spec["qtpylib"]["sha256"]
    qtpylib = load(qt, "pinned_qt_" + rid)
    module = load(source, "native_source_" + rid)
    module.qtpylib = qtpylib
    obj = getattr(module, spec["source"]["class_name"])({"runmode": "backtest"})
    obj.ft_load_hyper_params()
    for name, default in [
        ("use_exit_signal", True),
        ("exit_profit_only", False),
        ("exit_profit_offset", 0.0),
        ("ignore_roi_if_entry_signal", False),
    ]:
        StrategyResolver._override_attribute_helper(obj, {}, name, default)
    StrategyResolver._normalize_attributes(obj)
    assert obj.timeframe == "5m" and obj.stoploss == spec["risk"]["stoploss"]
    assert obj.minimal_roi == {
        int(k): v for k, v in spec["risk"]["minimal_roi"].items()
    }
    assert (
        obj.exit_profit_only == spec["execution"]["exit_profit_only"]
        and obj.exit_profit_offset == 0.0
    )
    assert (
        not obj.trailing_stop
        and not obj.can_short
        and not obj.ignore_roi_if_entry_signal
    )
    assert obj.order_types == spec["original_orders"]["order_types"]
    assert obj.order_time_in_force == spec["original_orders"]["order_time_in_force"]
    loaded = {name: p.value for name, p in obj.enumerate_parameters()}
    assert loaded == spec["parameters"]["loaded_parameter_values"], loaded
    return obj


def features(data, spec, sources, adapter):
    obj = instance(spec, sources)
    d = data.copy()
    d["date"] = pd.to_datetime(d.open_time, unit="ms", utc=True)
    assert isinstance(d.index, pd.RangeIndex) and d.index.start == 0
    native = obj.populate_indicators(d, {})
    native = obj.populate_entry_trend(native, {})
    native = obj.populate_exit_trend(native, {})
    enter, leave = adapter.rules(native)
    enter = enter.fillna(False).astype(int)
    leave = leave.fillna(False).astype(int)
    for original, derived in [("enter_long", enter), ("exit_long", leave)]:
        values = (
            native[original].fillna(0).astype(int)
            if original in native
            else pd.Series(0, index=native.index)
        )
        assert np.array_equal(values, derived), original
    native["entry_signal"] = enter
    native["exit_signal"] = leave
    return native
