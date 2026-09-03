from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = (
    ROOT
    / "research/hype/1h-multi-mechanism-trend-following/scripts/mmtf_engine.py"
)
SPEC = importlib.util.spec_from_file_location("hype_1h_mmtf_engine_test", ENGINE_PATH)
assert SPEC is not None and SPEC.loader is not None
ENGINE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ENGINE
SPEC.loader.exec_module(ENGINE)

V2_PATH = ENGINE_PATH.with_name("mmtf_v2.py")
V2_SPEC = importlib.util.spec_from_file_location("hype_1h_mmtf_v2_test", V2_PATH)
assert V2_SPEC is not None and V2_SPEC.loader is not None
V2 = importlib.util.module_from_spec(V2_SPEC)
sys.modules[V2_SPEC.name] = V2
sys.modules["mmtf_engine"] = ENGINE
V2_SPEC.loader.exec_module(V2)


def _require_local_evidence(*paths: Path) -> None:
    missing = [path for path in paths if not path.is_file()]
    if missing:
        pytest.skip(
            "local MMTF evidence is unavailable: "
            + ", ".join(path.name for path in missing)
        )


def _config(**changes: object) -> object:
    payload = {
        "mechanism": 0,
        "direction": 1,
        "entry_window": 12,
        "exit_window": 6,
        "ema_fast": 8,
        "ema_slow": 12,
        "atr_window": 10,
        "adx_min": 0.0,
        "rvol_min": 0.0,
        "breakout_atr": 0.0,
        "expansion_min": 1.0,
        "sl_atr": 1.0,
        "tp_atr": 1.0,
        "trail_activation_atr": 4.0,
        "trail_atr": 4.0,
        "breakeven_trigger_atr": 0.0,
        "max_hold_bars": 12,
        "cooldown_bars": 0,
        "leverage": 3.0,
        "trend_exit": False,
    }
    payload.update(changes)
    return ENGINE.Config(**payload)


def _synthetic_book() -> object:
    rows = 20
    ts = pd.date_range("2026-01-01", periods=rows, freq="1h", tz="UTC")
    open_values = np.full(rows, 100.0)
    high = np.full(rows, 100.2)
    low = np.full(rows, 99.8)
    close = np.full(rows, 100.0)
    prior_high = np.full(rows, 101.0)
    prior_low = np.full(rows, 99.0)
    close[5] = 102.0
    open_values[6] = 102.0
    high[6] = 104.0
    low[6] = 100.0
    return ENGINE.FeatureBook(
        ts=ts,
        terminal_ts=ts[-1] + pd.Timedelta(hours=1),
        open=open_values,
        high=high,
        low=low,
        close=close,
        volume=np.ones(rows),
        atr={10: np.ones(rows)},
        adx=np.full(rows, 25.0),
        ema={8: np.full(rows, 101.0), 12: np.full(rows, 100.0)},
        prior_high={12: prior_high, 6: prior_high},
        prior_low={12: prior_low, 6: prior_low},
        momentum_atr={(6, 10): np.zeros(rows), (12, 10): np.zeros(rows)},
        rvol=np.ones(rows),
        tr_over_atr={10: np.ones(rows)},
        funding_by_bar=np.zeros(rows),
        source_start=ts[0],
        selection_end=ts[-1] + pd.Timedelta(hours=1),
    )


def test_leverage_above_three_is_rejected() -> None:
    with pytest.raises(ValueError, match="leverage"):
        _config(leverage=3.01).validate()


def test_closed_bar_signal_enters_on_next_open_and_stop_first() -> None:
    result = ENGINE.run_backtest(_synthetic_book(), _config(), detailed=True)
    assert result.metrics["trades"] == 1
    trade = result.trades[0]
    assert trade["signal_ts"] == "2026-01-01T05:00:00+00:00"
    assert trade["entry_ts"] == "2026-01-01T06:00:00+00:00"
    assert trade["exit_reason"] == "stop"
    assert trade["net_return"] < 0.0


def test_primary_entry_ablation_produces_no_trades() -> None:
    result = ENGINE.run_backtest(
        _synthetic_book(),
        _config(),
        disabled_components=frozenset({"primary_entry"}),
    )
    assert result.metrics["trades"] == 0


@pytest.mark.local_data
def test_selection_book_excludes_locked_oos() -> None:
    _require_local_evidence(ENGINE.MANIFEST_PATH)
    book = ENGINE.build_book(include_locked_oos=False)
    manifest = ENGINE.load_manifest()
    assert book.rows == manifest["rows"]["prefit"]
    assert book.terminal_ts == pd.Timestamp(
        manifest["freeze_contract"]["locked_oos_start_inclusive"]
    )
    assert bool((book.ts < book.terminal_ts).all())


@pytest.mark.local_data
def test_v2_clean_baseline_is_path_equal_to_registered_v1() -> None:
    _require_local_evidence(
        ENGINE.MANIFEST_PATH,
        ROOT
        / "research/hype/1h-multi-mechanism-trend-following/artifacts"
        / "hype_1h_mmtf_v1_search_2026-07-22.json",
    )
    book = ENGINE.build_book(include_locked_oos=False)
    v1 = _config_from_registered_v1()
    v2 = V2.to_engine_config(V2.v2_baseline())
    assert ENGINE.trade_signature(ENGINE.run_backtest(book, v1, detailed=True)) == ENGINE.trade_signature(
        ENGINE.run_backtest(book, v2, detailed=True)
    )


def _config_from_registered_v1() -> object:
    import json

    artifact = (
        ROOT
        / "research/hype/1h-multi-mechanism-trend-following/artifacts"
        / "hype_1h_mmtf_v1_search_2026-07-22.json"
    )
    return ENGINE.config_from_dict(json.loads(artifact.read_text(encoding="utf-8"))["config"])
