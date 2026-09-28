from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pandas as pd
import pytest

pytestmark = pytest.mark.local_data

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = (
    ROOT / "research/hype/1d-15m-hierarchical-trend-opportunity/scripts"
)
ARTIFACT_DIR = SCRIPT_DIR.parent / "artifacts"
sys.path.insert(0, str(SCRIPT_DIR))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


engine = load_module("hto_engine", SCRIPT_DIR / "hto_engine.py")
v2 = load_module("hto_v2", SCRIPT_DIR / "hto_v2.py")


def _require_local_evidence(*paths: Path) -> None:
    missing = [path for path in paths if not path.is_file()]
    if missing:
        pytest.skip(
            "local HTO evidence is unavailable: "
            + ", ".join(path.name for path in missing)
        )


def test_prefit_book_stops_before_locked_oos() -> None:
    _require_local_evidence(engine.MANIFEST_PATH)
    book = engine.build_book(include_locked_oos=False)
    assert book.rows == 32_034
    assert book.terminal_ts == pd.Timestamp("2026-04-29 03:00:00+00:00")
    assert book.ts[-1] == pd.Timestamp("2026-04-29 02:45:00+00:00")


def test_clean_v2_is_trade_path_equal_to_v1() -> None:
    _require_local_evidence(
        engine.MANIFEST_PATH,
        ARTIFACT_DIR / "hype_d15_hto_v1_search_2026-07-29.json",
    )
    payload = json.loads(
        (ARTIFACT_DIR / "hype_d15_hto_v1_search_2026-07-29.json").read_text()
    )
    book = engine.build_book(include_locked_oos=False)
    v1_config = engine.config_from_dict(payload["config"])
    clean = v2.from_v1(v1_config)
    v1_result = engine.run_backtest(book, v1_config)
    v2_result = engine.run_backtest(book, v2.to_engine(clean))
    assert engine.trade_signature(v1_result) == engine.trade_signature(v2_result)
    assert v1_result.metrics == v2_result.metrics


def test_daily_features_are_constant_within_each_utc_day() -> None:
    _require_local_evidence(engine.MANIFEST_PATH)
    book = engine.build_book(include_locked_oos=False)
    days = book.ts.floor("D")
    series = pd.Series(book.daily_ema[40], index=days)
    per_day_unique = series.groupby(level=0).nunique(dropna=False)
    assert int(per_day_unique.max()) == 1


def test_entries_use_next_bar_open() -> None:
    _require_local_evidence(
        engine.MANIFEST_PATH,
        ARTIFACT_DIR / "hype_d15_hto_v3_tune_2026-07-29.json",
    )
    payload = json.loads(
        (ARTIFACT_DIR / "hype_d15_hto_v3_tune_2026-07-29.json").read_text()
    )
    book = engine.build_book(include_locked_oos=False)
    config = v2.to_engine(v2.from_dict(payload["clean_config"]))
    result = engine.run_backtest(book, config)
    assert result.trades
    for trade in result.trades:
        signal_ts = pd.Timestamp(trade["signal_ts"])
        entry_ts = pd.Timestamp(trade["entry_ts"])
        assert entry_ts - signal_ts == pd.Timedelta(minutes=15)
