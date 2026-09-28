from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

import pytest



ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "research/hype/1d-ma7-machine-learning-trend/scripts/"
    "run_hype_1d_ma7_mlt_p0.py"
)
ARTIFACT_DIR = ROOT / "research/hype/1d-ma7-machine-learning-trend/artifacts"
STEM = "hype_1d_ma7_mlt_p0_365d_train_validation_2026-08-27"


def load_module():
    spec = importlib.util.spec_from_file_location("test_hype_1d_ma7_mlt_p0_module", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_frozen_boundaries_and_candidate_counts() -> None:
    module = load_module()
    assert module.TRAIN_DAYS == 365
    assert module.HORIZONS == (3, 7, 14)
    assert module.folds_for_horizon(3)[-1] == (300, 360)
    assert module.folds_for_horizon(14)[-1] == (300, 349)
    assert len(module.model_factories()) * len(module.HORIZONS) * len(module.EDGE_THRESHOLDS) == 72
    assert (
        len(module.RULE_MA_WINDOWS)
        * len(module.RULE_SLOPE_LOOKBACKS)
        * len(module.RULE_MIN_SLOPES)
        * len(module.RULE_GAPS)
        * len(module.HORIZONS)
        * len(module.RULE_DIRECTIONS)
        == 4_320
    )


def test_single_trade_return_charges_both_fills_and_funding() -> None:
    module = load_module()
    daily = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=4, freq="1D", tz="UTC"),
            "open": [100.0, 100.0, 110.0, 121.0],
            "high": [101.0, 111.0, 122.0, 122.0],
            "low": [99.0, 99.0, 109.0, 120.0],
            "close": [100.0, 110.0, 121.0, 121.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        }
    )
    market = module.MarketData(
        daily=daily,
        open_ts=pd.date_range("2026-01-01", periods=5, freq="1D", tz="UTC"),
        opens=np.asarray([100.0, 100.0, 110.0, 121.0, 121.0]),
        funding_by_open=np.asarray([0.0, 0.0, 0.001, 0.001, 0.0]),
        quality={},
        funding_quality={},
    )
    actual = module.single_trade_return(market, 0, 2, 1)
    expected = 1.0 - module.COST_PER_FILL
    expected *= 1.10
    expected -= expected * 0.001
    expected *= 1.10
    expected -= expected * 0.001
    expected *= 1.0 - module.COST_PER_FILL
    assert math.isclose(actual, expected - 1.0, rel_tol=0.0, abs_tol=1e-12)


@pytest.mark.local_data
def test_locked_artifacts_match_frozen_champions_and_validation() -> None:
    summary = json.loads((ARTIFACT_DIR / f"{STEM}_summary.json").read_text())
    ml = pd.read_csv(ARTIFACT_DIR / f"{STEM}_ml_candidates.csv")
    rule = pd.read_csv(ARTIFACT_DIR / f"{STEM}_rule_candidates.csv")
    assert len(ml) == 72
    assert len(rule) == 4_320
    assert summary["ml_champion_train_oof"]["candidate_id"] == "LGBM_B|H7|E0.0000"
    assert (
        summary["rule_champion_train_oof"]["candidate_id"]
        == "MA7|SL1|MIN0.00|GAP0.50|H14|long_only"
    )
    validation = summary["validation"]
    assert math.isclose(validation["ml"]["total_return"], -0.38639396769195944)
    assert math.isclose(validation["rule_search"]["total_return"], -0.026418619357925333)
    assert math.isclose(validation["buy_hold"]["total_return"], 0.0062335687895767045)
    assert math.isclose(
        validation["v7_1_descriptive_reference"]["metrics"]["net_return_pct"],
        28.19315476579338,
    )
    assert summary["verdict"] == "ML_NO_EDGE"


@pytest.mark.local_data
def test_trade_path_contains_every_ml_and_rule_trade() -> None:
    html = (ARTIFACT_DIR / f"{STEM}_trade_paths.html").read_text()
    trades = pd.read_csv(ARTIFACT_DIR / f"{STEM}_validation_trades.csv")
    expected = trades.loc[trades["strategy"].isin(["ML", "RULE_SEARCH"])]
    for row in expected.itertuples(index=False):
        assert row.entry_ts in html
        assert row.exit_ts in html
    assert "dragmode:'pan'" in html
    assert "scrollZoom:true" in html

