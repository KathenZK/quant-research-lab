from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace
import sys
from typing import Any

import numpy as np
import pandas as pd

import pytest



ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / (
    "research/hype/1d-ma7-asymmetric-body-trend/scripts/"
    "audit_hype_1d_ma7_v6_missed_trend_attribution.py"
)


def load_script() -> Any:
    name = "test_hype_1d_ma7_v6_missed_trend_attribution_script"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def synthetic_context(
    close: list[float],
    ma7: list[float],
) -> Any:
    count = len(close)
    index = pd.date_range("2026-01-01", periods=count, tz="UTC", freq="D")
    return SimpleNamespace(
        book=SimpleNamespace(
            count=count,
            ts=index,
            terminal_ts=index[-1] + pd.Timedelta(days=1),
            open=np.asarray(close, dtype=float),
            close=np.asarray(close, dtype=float),
            quality={"terminal_open": float(close[-1])},
        ),
        features=SimpleNamespace(
            ma7=np.asarray(ma7, dtype=float),
            atr7=np.ones(count, dtype=float),
        ),
    )


def test_reference_episode_extraction_keeps_flat_gap() -> None:
    script = load_script()
    index = pd.date_range("2026-01-01", periods=9, tz="UTC", freq="D")
    daily = pd.DataFrame(
        {
            "close": np.linspace(10.0, 11.0, 9),
            "ma7": np.linspace(10.0, 10.8, 9),
            "atr7": np.ones(9),
        },
        index=index,
    )
    stable = pd.Series(
        [np.nan, 1, 1, 1, 0, -1, -1, -1, np.nan],
        index=index,
        dtype=float,
    )
    raw = pd.Series(
        [None, "up_slow", "up_slow", "up_slow", "neutral",
         "down_slow", "down_slow", "down_slow", None],
        index=index,
        dtype=object,
    )
    episodes = script.extract_reference_episodes(stable, daily, raw)
    assert [(row["side"], row["duration_days"]) for row in episodes] == [
        (1, 3),
        (-1, 3),
    ]
    assert episodes[0]["end_index"] < episodes[1]["start_index"]


def test_exact_criteria_keeps_buffer_strict() -> None:
    script = load_script()
    context = synthetic_context(
        [10.0, 10.0, 9.9],
        [10.0, 10.0, 10.0],
    )
    context.long_config = SimpleNamespace(
        slope_lookback=1,
        slope_min_atr=0.0,
        entry_buffer_atr=0.0,
    )
    context.short_config = SimpleNamespace(
        slope_lookback=2,
        slope_min_atr=0.0,
        entry_buffer_atr=0.10,
    )
    long_row = script._criteria(context, 1, 1)
    short_row = script._criteria(context, -1, 2)
    assert long_row["buffer_pass"] is False
    assert short_row["distance_atr"] == 0.09999999999999964
    assert short_row["buffer_pass"] is False


def test_probe_schedule_rejects_core_open_and_preempts_later() -> None:
    script = load_script()
    context = synthetic_context(
        [9.8, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8],
        [10.0] * 8,
    )
    runtime = script.Runtime(None, None, None, None, None, None, context)
    roots = [
        {
            "root_id": "ROOT001",
            "side": 1,
            "cross_index": 1,
            "maturity_index": 1,
            "reference_episode_id": None,
        },
        {
            "root_id": "ROOT002",
            "side": 1,
            "cross_index": 2,
            "maturity_index": 3,
            "reference_episode_id": None,
        },
    ]
    core = [
        {
            "trade_id": "V6T001",
            "source": "core",
            "side": 1,
            "entry_ts": context.book.ts[2],
            "exit_ts": context.book.ts[3],
            "entry_price": 10.3,
            "exit_price": 10.4,
        },
        {
            "trade_id": "V6T002",
            "source": "core",
            "side": -1,
            "entry_ts": context.book.ts[5],
            "exit_ts": context.book.ts[6],
            "entry_price": 10.6,
            "exit_price": 10.7,
        },
    ]
    probes, decisions = script.build_probe_schedule(runtime, roots, core)
    assert decisions[0]["reason"] == "CORE_PRECEDENCE"
    assert len(probes) == 1
    assert probes[0]["root_id"] == "ROOT002"
    assert probes[0]["exit_reason"] == "core_preempt"
    assert probes[0]["exit_ts"] == context.book.ts[5]


@pytest.mark.local_data
def test_custom_core_replay_matches_exact_v6() -> None:
    script = load_script()
    runtime = script.load_runtime()
    exact = runtime.transition.run_v6(
        runtime.context,
        start_index=0,
        terminal_index=runtime.context.book.count,
        retain=True,
    )
    core = script.build_core_schedule(runtime.context, exact.raw)
    replay = script.replay_schedule(runtime, core)
    risk = runtime.risk.replay_chronological_1h(runtime.context, exact.raw)
    assert math.isclose(
        replay["metrics"]["equity_multiple"],
        risk.terminal_equity,
        rel_tol=2e-10,
        abs_tol=2e-10,
    )
    assert math.isclose(
        replay["metrics"]["chronological_1h_mdd_pct"],
        risk.chronological_1h_mdd_pct,
        rel_tol=2e-10,
        abs_tol=2e-10,
    )


@pytest.mark.local_data
def test_full_payload_is_causal_and_internally_valid() -> None:
    script = load_script()
    payload = script.build_payload()
    assert payload["schema_version"].endswith("-v1")
    assert payload["invariant_failures"] == []
    assert payload["v6_anchor"]["metrics"]["closed_trades"] == 19
    assert all(
        root["hindsight_used_for_probe"] is False
        for root in payload["root_opportunities"]
    )
    assert all(
        trade["trend_hit_not_used"] is True
        for trade in payload["probe_results"]["base"]["probe_trades"]
    )
    assert payload["final_conclusion_code"] in {
        "HINDSIGHT_ONLY_MISSES",
        "INSUFFICIENT_INDEPENDENT_EPISODES",
        "NON_ECONOMIC_MISSES",
        "NO_DUAL_IMPROVEMENT",
        "FRAGILE_EXPOSED_INCREMENT",
        "EXPOSED_CAUSAL_LEAK_SUPPORTED",
    }
