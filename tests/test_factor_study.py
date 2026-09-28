"""Synthetic semantic/admission tests; fixtures never count as market research."""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from strategy_lab.data.factors.engine import compute_factor_bundle
from strategy_lab.factor_study.factors import (
    FORMULAS,
    QlibPriceFactor,
    registry,
    validate_definition,
    definition_name,
)
from strategy_lab.factor_study.semantics import (
    hand_check,
    reference,
    validate_semantics,
)
from strategy_lab.factor_study.diagnostics import association, incremental, label_frame
from strategy_lab.factor_study.pipeline import verify_settings, digest
from strategy_lab.factor_study.trial_adapter import UnavailableTrialAdapter

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/factor_study/qlib-golden.json"
SELECTION = (
    ROOT / "research/platform/factor-research-loop/specs/graph-selection-v1.json"
)


def frame():
    v = json.loads(FIXTURE.read_text())
    f = pd.DataFrame(v["input"], dtype=float)
    f["symbol"], f["ts"] = (
        "SYNTHETIC",
        pd.date_range("2020-01-01", periods=len(f), tz="UTC"),
    )
    return f


@pytest.mark.parametrize("name", FORMULAS)
def test_official_oracle_hand_arithmetic_missing_and_warmup(name):
    hand_check(name)
    f = frame()
    golden = json.loads(FIXTURE.read_text())["expected"]
    golden.update(
        json.loads(FIXTURE.with_name("qlib-golden-extended.json").read_text())[
            "expected"
        ]
    )
    expected = np.array(golden[name], dtype=float)
    actual = QlibPriceFactor(name).compute(f)
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12, equal_nan=True)
    np.testing.assert_allclose(
        actual, reference(f, name), rtol=1e-12, atol=1e-12, equal_nan=True
    )


@pytest.mark.parametrize("name", FORMULAS)
def test_no_future_dependency_or_asset_crosstalk(name):
    a = frame().fillna(5.0)
    b = a.copy()
    b["symbol"] = "OTHER"
    for c in ["open", "high", "low", "close"]:
        b[c] *= 10
    joined = pd.concat([b, a]).sample(frac=1, random_state=20)
    values = compute_factor_bundle(joined, registry([name]))
    expected = QlibPriceFactor(name).compute(a).to_numpy()
    np.testing.assert_allclose(
        values[values.symbol == "SYNTHETIC"][name], expected, equal_nan=True
    )
    changed = a.copy()
    changed.loc[8:, "close"] = 999.0
    np.testing.assert_allclose(
        QlibPriceFactor(name).compute(changed).iloc[:8], expected[:8], equal_nan=True
    )


def test_same_name_and_malicious_formula_do_not_create_mapping():
    definitions = json.loads(SELECTION.read_text())["definitions"]
    for v in definitions:
        assert validate_definition(v).metadata.name == definition_name(v)
    for field, value in [
        ("raw_formula", '__import__("os").system("false")'),
        ("source_revision", "same-name-other-source"),
        ("required_fields", ["volume"]),
    ]:
        bad = {**definitions[0], field: value}
        with pytest.raises(ValueError, match="reviewed"):
            validate_definition(bad)


def test_rank_is_time_series_ddof_and_inverse_roc():
    f = pd.DataFrame({"close": [1.0, 2.0, 2.0, 4.0, 5.0, 8.0]})
    assert QlibPriceFactor("RANK5").compute(f).iloc[2] == 2.5 / 3
    assert QlibPriceFactor("ROC5").compute(f).iloc[-1] == 1 / 8
    assert (
        QlibPriceFactor("STD5").compute(f).iloc[0]
        != QlibPriceFactor("STD5").compute(f).iloc[0]
    )
    assert QlibPriceFactor("STD5").compute(f).iloc[1] == pytest.approx(np.sqrt(0.5) / 2)


def test_label_tail_and_constant_or_infinite_diagnostics():
    f = frame()
    y = label_frame(f, 5)
    assert y.label.tail(5).isna().all()
    assert y.label.iloc[0] == 7.0
    stat = association(
        np.ones(40), np.arange(40), block_bars=5, replications=100, seed=9
    )
    assert stat["status"] == "CONSTANT_FEATURE_OR_LABEL" and stat["pearson"] is None
    stat = association(
        [np.inf, np.nan, 1.0], [1.0, 2.0, 3.0], block_bars=5, replications=100, seed=9
    )
    assert stat["status"] == "INSUFFICIENT_PAIRS" and stat["n"] == 1


def test_bootstrap_reproducible_on_original_missing_grid():
    rng = np.random.default_rng(9)
    x, y = rng.normal(size=(2, 200))
    x[40:50] = np.nan
    args = dict(block_bars=20, replications=100, seed=9)
    a = association(x, y, **args)
    assert a == association(x, y, **args)
    assert a["n"] == 190 and a["grid_rows"] == 200 and a["axis"] == "TIME_SERIES"
    assert a["ci95"]["pearson"][0] < a["pearson"] < a["ci95"]["pearson"][1]


def test_incremental_train_boundary_is_purged():
    rng = np.random.default_rng(4)
    f = pd.DataFrame(
        {
            "ts": pd.date_range("2020-01-01", periods=180, tz="UTC"),
            "close": np.exp(np.cumsum(rng.normal(0, 0.01, 180))),
        }
    )
    a = incremental(
        f,
        pd.Series(rng.normal(size=180)),
        5,
        "2020-04-01T00:00:00Z",
        "2020-01-07T00:00:00Z",
    )
    assert a["train_n"] == 80 and a["late_n"] == 84
    assert a["holdout_certified"] is False and "mse_reduction" in a


def test_frozen_settings_reject_future_or_cross_sectional_claims():
    s = json.loads(SELECTION.read_text())["request"]["requested_settings"]
    verify_settings(s)
    for change in [
        {"label_horizons": [-1]},
        {"axis": "CROSS_SECTIONAL"},
        {"research_status": "RESEARCH_PASSED"},
        {"evaluation_start": s["end"]},
    ]:
        with pytest.raises(ValueError):
            verify_settings({**s, **change})
    c = UnavailableTrialAdapter()
    r = c.register({"plan_sha256": digest(s)}, [dict(id="synthetic")])
    assert r["status"] == "UNAVAILABLE"
    assert c.evaluate(r, [])["promotion_allowed"] is False


def test_both_semantic_layers_reported():
    result = validate_semantics("KMID", frame(), FIXTURE)
    assert (
        result["hand_calculated"]
        == result["reference_parity"]
        == result["real_market_boundaries"]
        == "PASS"
    )
    # This invocation is synthetic test-only; no study result is written.
