from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "research/us-indexes/1d-nasdaq100-ma7-regime-continuation"
SCRIPT_PATH = FAMILY_DIR / "scripts/research_ndx100_1d_ma7_regime_continuation.py"
SPEC = importlib.util.spec_from_file_location("ndx100_1d_ma7_rc", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

Y1_AUDIT_SCRIPT_PATH = (
    FAMILY_DIR / "scripts/audit_yahoo_historical_ndx100_coverage.py"
)
Y1_AUDIT_SPEC = importlib.util.spec_from_file_location(
    "ndx100_y1_coverage_audit", Y1_AUDIT_SCRIPT_PATH
)
assert Y1_AUDIT_SPEC is not None and Y1_AUDIT_SPEC.loader is not None
Y1_AUDIT_MODULE = importlib.util.module_from_spec(Y1_AUDIT_SPEC)
Y1_AUDIT_SPEC.loader.exec_module(Y1_AUDIT_MODULE)

Y2_SCRIPT_PATH = FAMILY_DIR / "scripts/analyze_ndx100_yahoo_current_y2_atr_path.py"
Y2_SPEC = importlib.util.spec_from_file_location("ndx100_y2_atr_path", Y2_SCRIPT_PATH)
assert Y2_SPEC is not None and Y2_SPEC.loader is not None
Y2_MODULE = importlib.util.module_from_spec(Y2_SPEC)
Y2_SPEC.loader.exec_module(Y2_MODULE)

Y3_SCRIPT_PATH = (
    FAMILY_DIR / "scripts/analyze_ndx100_yahoo_current_y3_structure_atlas.py"
)
Y3_SPEC = importlib.util.spec_from_file_location(
    "ndx100_y3_structure_atlas", Y3_SCRIPT_PATH
)
assert Y3_SPEC is not None and Y3_SPEC.loader is not None
Y3_MODULE = importlib.util.module_from_spec(Y3_SPEC)
Y3_SPEC.loader.exec_module(Y3_MODULE)


def test_frozen_config_hash_identity_and_no_threshold_search() -> None:
    config = MODULE.read_config()
    assert config["study_id"] == "NDX100-1D-MA7-RC-P0"
    assert config["event"]["primary_ma_period"] == 7
    assert config["regime"]["regime_uses_ma_trigger"] is False
    assert config["binning"]["threshold_search"] is False


def test_access_audit_requires_a_2010_daily_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeClient:
        def get_json(self, path: str, params: dict | None = None) -> dict:
            if path.startswith("/v3/reference/tickers/AAPL"):
                return {
                    "status": "OK",
                    "request_id": "details",
                    "results": {"composite_figi": "BBG000B9XRY4"},
                }
            if path.startswith("/vX/reference/tickers/"):
                return {"status": "OK", "request_id": "events", "results": {}}
            if "/2010-01-04/2010-01-04" in path:
                return {
                    "status": "OK",
                    "request_id": "history",
                    "resultsCount": 0,
                    "results": [],
                }
            return {
                "status": "OK",
                "request_id": "current",
                "resultsCount": 1,
                "results": [{"c": 1.0}],
            }

    monkeypatch.setattr(MODULE, "ACCESS_AUDIT_PATH", tmp_path / "access.json")
    result = MODULE.check_massive_access(
        FakeClient(), MODULE.read_config(), "MASSIVE_API_KEY"
    )
    historical = next(
        check for check in result["checks"] if check["name"] == "historical_daily_aggregates"
    )
    assert result["all_required_checks_pass"] is False
    assert historical["ok"] is False
    assert historical["result_count"] == 0


@pytest.mark.local_data
def test_membership_reconstruction_has_expected_integrity_and_corporate_actions() -> None:
    membership = pd.read_parquet(
        FAMILY_DIR / "artifacts/ndx100_1d_ma7_rc_p0_membership_daily.parquet"
    )
    membership["session_date"] = pd.to_datetime(membership["session_date"])
    first = membership.loc[membership["session_date"].eq(pd.Timestamp("2010-01-04"))]
    # Nasdaq-100 is 100 non-financial issuers, not always exactly 100 securities;
    # multiple eligible share classes can coexist in the index.
    assert len(first) == 102
    assert membership.groupby("session_date").size().min() == 100

    before_conversion = membership.loc[
        membership["session_date"].eq(pd.Timestamp("2015-12-11")), "ticker"
    ]
    after_conversion = membership.loc[
        membership["session_date"].eq(pd.Timestamp("2015-12-14")), "ticker"
    ]
    assert "CMCSK" in set(before_conversion)
    assert "CMCSK" not in set(after_conversion)

    hans = membership.loc[
        membership["session_date"].eq(pd.Timestamp("2012-01-06")),
        ["ticker", "entity_key"],
    ]
    mnst = membership.loc[
        membership["session_date"].eq(pd.Timestamp("2012-01-09")),
        ["ticker", "entity_key"],
    ]
    assert ((hans["ticker"] == "HANS") & (hans["entity_key"] == "MNST")).any()
    assert ((mnst["ticker"] == "MNST") & (mnst["entity_key"] == "MNST")).any()


def test_y1_mapping_prefers_direct_then_unique_entity_lineage() -> None:
    dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    membership = pd.DataFrame(
        {
            "session_date": dates,
            "ticker": ["OLD", "OLD", "MISSING"],
            "entity_key": ["ENTITY", "ENTITY", "OTHER"],
        }
    )
    prices = pd.DataFrame(
        {
            "session_date": [dates[0], dates[1]],
            "ticker": ["OLD", "NEW"],
        }
    )
    intervals = pd.DataFrame(
        {
            "ticker": ["OLD", "NEW", "MISSING"],
            "entity_key": ["ENTITY", "ENTITY", "OTHER"],
        }
    )
    mapped = Y1_AUDIT_MODULE.build_price_mapping(membership, prices, intervals)
    assert mapped["mapping_method"].tolist() == [
        "direct",
        "unique_entity_lineage",
        "missing",
    ]
    assert mapped["source_ticker"].tolist()[:2] == ["OLD", "NEW"]
    assert pd.isna(mapped["source_ticker"].iloc[2])


@pytest.mark.local_data
def test_y1_historical_yahoo_coverage_fails_closed() -> None:
    audit_path = FAMILY_DIR / "artifacts/ndx100_1d_ma7_rc_y1_coverage_audit.json"
    if not audit_path.exists():
        pytest.skip("Y1 Yahoo coverage audit has not been generated")
    audit = pd.read_json(audit_path, typ="series")
    assert audit["study_id"] == "NDX100-1D-MA7-RC-Y1"
    assert audit["point_in_time_membership"]["membership_tickers"] == 252
    assert audit["historical_exit_tickers"]["with_any_price_coverage_after_lineage_fallback"] > 0
    assert audit["coverage"]["missing_member_stock_days"] > 0
    assert audit["gate"]["pass"] is False
    assert audit["gate"]["outcome_statistics_allowed"] is False


def test_y2_config_is_frozen_external_transfer_without_stock_search() -> None:
    assert Y2_MODULE.sha256_file(Y2_MODULE.CONFIG_PATH) == Y2_MODULE.EXPECTED_CONFIG_SHA256
    config = pd.read_json(Y2_MODULE.CONFIG_PATH, typ="series")
    assert config["study_id"] == "NDX100-1D-MA7-RC-Y2"
    assert config["external_crypto_hypotheses"]["stock_outcome_parameter_search"] is False
    assert config["external_crypto_hypotheses"]["long"].startswith(
        "MA-slope-aligned Q5_FAST_EXPANSION"
    )
    assert config["external_crypto_hypotheses"]["short"].startswith(
        "MA-slope-aligned Q1_FAST_CONTRACTION"
    )


def test_y2_transfer_mask_keeps_only_crypto_selected_directional_cells() -> None:
    frame = pd.DataFrame(
        {
            "direction": ["long", "long", "short", "short"],
            "ma_slope_aligned": [True, True, True, True],
            "atr_path_q": [5, 1, 1, 5],
            "breakout_style": ["BURST", "BURST", "BURST", "BURST"],
        }
    )
    assert Y2_MODULE.transfer_mask(frame).tolist() == [True, False, True, False]


@pytest.mark.local_data
def test_y2_completed_result_rejects_stable_cross_market_optimization() -> None:
    summary_path = FAMILY_DIR / "artifacts/ndx100_1d_ma7_rc_y2_summary.json"
    if not summary_path.exists():
        pytest.skip("Y2 ATR-path study has not been generated")
    summary = pd.read_json(summary_path, typ="series")
    assert summary["data"]["ma7_events"] == 77_957
    assert summary["data"]["common_atr_path_rv_ma7_aligned_events"] == 38_451
    assert summary["outcome_conclusion"].startswith("未形成稳定可迁移优化")


def test_y3_contract_freezes_interpretable_pre_breakout_states_without_ml() -> None:
    assert Y3_MODULE.sha256_file(Y3_MODULE.CONFIG_PATH) == Y3_MODULE.EXPECTED_CONFIG_SHA256
    config = pd.read_json(Y3_MODULE.CONFIG_PATH, typ="series")
    assert config["study_id"] == "NDX100-1D-MA7-RC-Y3"
    assert config["events"]["trigger_ma_periods"] == [7, 30]
    assert config["events"]["all_market_state_features_end_at"] == "t-1"
    assert config["statistics"]["no_machine_learning"] is True
    assert config["statistics"]["no_cross_sectional_relative_strength"] is True
    assert len(config["named_long_states"]) == 11
    assert len(config["named_short_states"]) == 12


def test_y3_named_state_masks_encode_recovery_and_distribution_paths() -> None:
    frame = pd.DataFrame(
        {
            "direction": ["long", "short"],
            "pre_ma_hierarchy": ["MIXED", "MIXED"],
            "pre_ret20": [-0.05, 0.04],
            "pre_drawdown60": [-0.20, -0.02],
            "pre_runup20": [0.08, 0.10],
            "pre_ret10": [0.02, 0.01],
            "pre_range20_q": [2, 2],
            "pre_price_to_ma30_atr": [-1.0, 1.0],
            "pre_drawdown20": [-0.08, -0.04],
            "pre_ret60": [-0.10, 0.25],
            "pre_breadth_above_ma30": [0.30, 0.80],
            "pre_breadth_change10": [0.06, -0.06],
            "pre_qqq_phase": ["bear", "bull"],
            "pre_natr20_q": [4, 2],
            "pre_runup60": [0.10, 0.25],
        }
    )
    masks = Y3_MODULE.named_state_masks(frame)
    assert masks["L02_DEEP_DRAWDOWN_RECOVERY"].tolist() == [True, False]
    assert masks["L04_EARLY_RECOVERY_BELOW_MA30"].tolist() == [True, False]
    assert masks["S03_RALLY_DISTRIBUTION"].tolist() == [False, True]


@pytest.mark.local_data
def test_y3_generated_atlas_finds_recovery_structure_but_no_short_state() -> None:
    summary_path = FAMILY_DIR / "artifacts/ndx100_1d_ma7_rc_y3_summary.json"
    if not summary_path.exists():
        pytest.skip("Y3 structure atlas has not been generated")
    summary = pd.read_json(summary_path, typ="series")
    assert summary["data"]["events"] == 110_154
    supported = summary["supported_descriptive_states_20d_raw_fdr10"]
    assert any(row["state_name"] == "L02_DEEP_DRAWDOWN_RECOVERY" for row in supported)
    assert any(row["state_name"] == "L04_EARLY_RECOVERY_BELOW_MA30" for row in supported)
    assert all(row["direction"] == "long" for row in supported)


def test_rolling_percentile_requires_a_full_finite_window() -> None:
    values = np.array([1.0, 3.0, 2.0, 4.0, 0.0])
    actual = MODULE.rolling_percentile_current(values, 3)
    expected = np.array([np.nan, np.nan, 2 / 3, 1.0, 1 / 3])
    np.testing.assert_allclose(actual, expected, equal_nan=True)
    missing = MODULE.rolling_percentile_current(
        np.array([1.0, np.nan, 2.0, 3.0]), 3
    )
    assert np.isnan(missing).all()


def test_feature_block_matches_stock_formulas_and_records_gap() -> None:
    close = pd.Series(np.arange(100.0, 410.0))
    frame = pd.DataFrame(
        {
            "session_date": pd.bdate_range("2020-01-01", periods=310),
            "open": close.shift(1).fillna(close.iloc[0]) * 1.01,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.arange(1_000.0, 1_310.0),
        }
    )
    result = MODULE._feature_block(frame)
    row = result.iloc[309]
    assert row["atr14"] == pytest.approx(2.0)
    assert row["normalized_slope"] == pytest.approx(0.5)
    assert row["er20"] == pytest.approx(1.0)
    assert row["rv20"] > 0
    assert 0 < row["rv_percentile"] <= 1
    assert row["gap"] == pytest.approx(0.01)
    assert np.isnan(row["future_close_1"])


def test_assign_entity_keys_breaks_same_symbol_generations() -> None:
    bars = pd.DataFrame(
        {
            "session_date": pd.to_datetime(["2014-04-02", "2014-04-03"]),
            "ticker": ["GOOG", "GOOG"],
            "open": [1.0, 1.0],
            "high": [1.0, 1.0],
            "low": [1.0, 1.0],
            "close": [1.0, 1.0],
            "volume": [1.0, 1.0],
        }
    )
    intervals = pd.DataFrame(
        {
            "ticker": ["GOOG", "GOOG"],
            "entity_key": ["ALPHABET_CLASS_A", "ALPHABET_CLASS_C"],
            "start_session": pd.to_datetime(["2010-01-04", "2014-04-03"]),
            "end_session_inclusive": pd.to_datetime(["2014-04-02", "2026-08-21"]),
        }
    )
    mapped = MODULE.assign_entity_keys(bars, intervals)
    assert mapped["entity_key"].tolist() == ["ALPHABET_CLASS_A", "ALPHABET_CLASS_C"]


def _event_panel() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=8)
    close = pd.Series([10.0, 9.0, 8.0, 12.0, 13.0, 8.0, 7.0, 6.0])
    frame = pd.DataFrame(
        {
            "ticker": ["X"] * 8,
            "entity_key": ["X_ENTITY"] * 8,
            "session_date": dates,
            "block_id": [1] * 8,
            "close": close,
            "atr14": [2.0] * 8,
            "normalized_slope": [0.1] * 8,
            "er20": [0.5] * 8,
            "rv20": [0.8] * 8,
            "rv_percentile": [0.5] * 8,
            "slope_q": pd.Series([3] * 8, dtype="Int64"),
            "er_q": pd.Series([3] * 8, dtype="Int64"),
            "rv_q": pd.Series([3] * 8, dtype="Int64"),
            "gap": [0.0] * 8,
            "adv30_median": [1_000_000.0] * 8,
            "liquidity_rank": [1.0] * 8,
            "liquidity_segment": ["top20"] * 8,
            "membership_tenure_sessions": [500] * 8,
            "membership_tenure_segment": ["seasoned_member"] * 8,
            "market_phase": ["bull"] * 8,
            "calendar_year": [2024] * 8,
            "eligible_regime": [True] * 8,
        }
    )
    for period in MODULE.MA_PERIODS:
        frame[f"sma{period}"] = [10.0] * 8
    for horizon in MODULE.HORIZONS:
        frame[f"future_close_{horizon}"] = close.shift(-horizon)
    return frame


def test_build_events_uses_symmetric_cross_and_directional_returns() -> None:
    events = MODULE.build_events(_event_panel())
    long_event = events.loc[
        events["ma_period"].eq(7) & events["direction"].eq("long")
    ].iloc[0]
    short_event = events.loc[
        events["ma_period"].eq(7)
        & events["direction"].eq("short")
        & events["session_date"].eq(pd.Timestamp("2024-01-08"))
    ].iloc[0]
    assert long_event["session_date"] == pd.Timestamp("2024-01-04")
    assert long_event["raw_return_1"] == pytest.approx(13.0 / 12.0 - 1.0)
    assert long_event["atr_return_1"] == pytest.approx(0.5)
    assert short_event["raw_return_1"] == pytest.approx(1.0 - 7.0 / 8.0)
    assert short_event["atr_return_1"] == pytest.approx(0.5)


def test_two_way_cluster_bh_and_cross_market_wide_table() -> None:
    values = pd.Series([0.01, 0.02, -0.01, 0.03, 0.00, 0.02])
    securities = pd.Series(["A", "A", "B", "B", "C", "C"])
    dates = pd.Series(pd.date_range("2024-01-01", periods=3).repeat(2))
    result = MODULE.infer_mean(values, securities, dates)
    assert result["sample_count"] == 6
    assert result["security_count"] == 3
    assert result["event_date_count"] == 3
    assert np.isfinite(result["cluster_se"])

    adjusted = MODULE.benjamini_hochberg(pd.Series([0.01, 0.04, 0.03, 0.20]))
    assert adjusted.tolist() == pytest.approx([0.04, 0.0533333333, 0.0533333333, 0.20])

    cross = pd.DataFrame(
        {
            "market": ["Crypto", "Crypto", "Nasdaq100", "Nasdaq100"],
            "direction": ["long", "short", "long", "short"],
            "variable": ["er20"] * 4,
            "quintile": [5] * 4,
            "horizon_days": [20] * 4,
            "return_metric": ["raw_return"] * 4,
            "mean": [0.01, 0.02, 0.03, 0.04],
            "sample_count": [100] * 4,
        }
    )
    wide = MODULE._wide_cross_market(
        cross, ["variable", "quintile", "horizon_days", "return_metric"]
    )
    assert wide.loc[0, "crypto_long_mean"] == pytest.approx(0.01)
    assert wide.loc[0, "nasdaq100_short_mean"] == pytest.approx(0.04)
