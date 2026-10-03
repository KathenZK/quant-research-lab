"""Pinned original strategy plus pinned technical CMF; actual framework defaults, offline."""

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import socket
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pandas as pd
from freqtrade.resolvers import StrategyResolver
import freqtrade.strategy.interface as interface
import freqtrade.resolvers.strategy_resolver as resolver
import freqtrade.strategy.hyper as hyper
from run_replay import features, load_input

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def original(source):
    source = Path(source)
    manifest = json.loads((ROOT / "specs/source-manifest.json").read_text())
    files = {x["filename"]: x for x in manifest["files"]}
    for name, item in files.items():
        assert (
            hashlib.sha256((source / name).read_bytes()).hexdigest() == item["sha256"]
        ), name
    for module, name in [
        (interface, "engine-freqtrade__strategy__interface.py"),
        (resolver, "engine-freqtrade__resolvers__strategy_resolver.py"),
        (hyper, "engine-freqtrade__strategy__hyper.py"),
    ]:
        assert (
            hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            == files[name]["sha256"]
        )
    vol = load(
        source / "technical-technical__indicators__volume_indicators.py",
        "m0311_pinned_volume",
    )
    module = load(source / "M0311-TechnicalExampleStrategy.py", "m0311_original")
    module.cmf = (
        vol.cmf
    )  # pin imported dependency, leave original source bytes/methods unchanged
    obj = module.TechnicalExampleStrategy({"runmode": "backtest"})
    obj.ft_load_hyper_params()
    for name, default in [
        ("use_exit_signal", True),
        ("exit_profit_only", False),
        ("exit_profit_offset", 0.0),
        ("ignore_roi_if_entry_signal", False),
    ]:
        StrategyResolver._override_attribute_helper(obj, {}, name, default)
    StrategyResolver._normalize_attributes(obj)
    assert (
        obj.timeframe == "5m" and obj.minimal_roi == {0: 0.01} and obj.stoploss == -0.05
    )
    assert (
        obj.order_types["entry"]
        == obj.order_types["exit"]
        == obj.order_types["stoploss"]
        == "limit"
    )
    assert obj.order_types["stoploss_on_exchange"] is False
    assert obj.order_time_in_force == {"entry": "GTC", "exit": "GTC"}
    assert not obj.trailing_stop and not obj.can_short and obj.startup_candle_count == 0
    assert (
        obj.use_exit_signal
        and not obj.exit_profit_only
        and not obj.ignore_roi_if_entry_signal
    )
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    trade = SimpleNamespace(open_date_utc=now)
    for age in [0, 1, 60, 10000]:
        when = now + timedelta(minutes=age)
        assert not obj.min_roi_reached(trade, 0.01, when)
        assert obj.min_roi_reached(trade, np.nextafter(0.01, np.inf), when)
    return obj


def compare(data, source):
    with patch.object(
        socket.socket, "connect", side_effect=RuntimeError("OFFLINE_ONLY")
    ):
        obj = original(source)
        d = data.copy()
        d["date"] = pd.to_datetime(d.open_time, unit="ms", utc=True)
        ref = obj.populate_indicators(d, {})
        ref = obj.populate_entry_trend(ref, {})
        ref = obj.populate_exit_trend(ref, {})
        port = features(data)
        assert np.array_equal(ref.cmf, port.cmf, equal_nan=True)
        for a, b in [("enter_long", "entry_signal"), ("exit_long", "exit_signal")]:
            assert np.array_equal(ref[a].fillna(0).astype(int), port[b])
        # Independent21-observation window summation, no pandas rolling implementation.
        flow = []
        vol = data.volume.to_numpy()
        for row in data.itertuples():
            flow.append(
                ((row.close - row.low) - (row.high - row.close))
                / (row.high - row.low)
                * row.volume
                if row.high != row.low
                else math.nan
            )
        independent = np.full(len(data), np.nan)
        for i in range(20, len(data)):
            window = flow[i - 20 : i + 1]
            den = math.fsum(vol[i - 20 : i + 1])
            if den != 0 and all(math.isfinite(x) for x in window):
                independent[i] = math.fsum(window) / den
        np.testing.assert_allclose(
            independent, port.cmf, atol=1e-12, rtol=1e-12, equal_nan=True
        )
        assert np.array_equal(independent < 0, port.entry_signal.eq(1))
        assert np.array_equal(independent > 0, port.exit_signal.eq(1))
        finite = np.isfinite(independent)
    return {
        "id": "M0311",
        "status": "PASS",
        "rows": len(data),
        "original_class_signals_identical": True,
        "pinned_CMF_values_identical": True,
        "independent_window_formula_and_signals": "PASS",
        "independent_max_abs_error": float(
            np.max(np.abs(independent[finite] - port.cmf.to_numpy()[finite]))
        )
        if finite.any()
        else 0.0,
        "cmf_nan_rows": int(port.cmf.isna().sum()),
        "roi_strict_greater_boundary": "PASS",
        "native_order_types": obj.order_types,
        "native_time_in_force": obj.order_time_in_force,
        "native_exit_profit_only": obj.exit_profit_only,
        "startup_candle_count": obj.startup_candle_count,
        "fidelity_class": "ADAPTED",
        "execution_class": "ADAPTED_EXECUTION_PROXY",
        "native_engine_used": False,
        "new_market_requests": 0,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--sources", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    spec = json.loads((ROOT / "specs/M0311-first-replay.json").read_text())
    result = compare(load_input(a.input, spec), a.sources)
    with Path(a.output).open("x") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(json.dumps(result, indent=2))
