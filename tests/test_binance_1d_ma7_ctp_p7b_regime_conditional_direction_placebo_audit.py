from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p7b_regime_conditional_direction_placebo_audit.py"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAG_DIR = FAMILY_DIR / "diagnostics"
SHARED_DOCS = [
    ROOT / "research/README.md",
    ROOT / "research/asset-portfolios/README.md",
    FAMILY_DIR / "README.md",
    FAMILY_DIR / "binance-1d-ma7-ctp-core-ledger.md",
    FAMILY_DIR / "decision-log.md",
    FAMILY_DIR / "artifacts/README.md",
]
FROZEN_P0_P7A = [
    ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet",
    ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_summary.json",
    ARTIFACT_DIR / "binance_1d_ma7_ctp_p6_summary.json",
    ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_dual_side_outcomes.parquet",
    ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_summary.json",
    FAMILY_DIR / "diagnostics/binance-1d-ma7-ctp-p7-temporal-drift-calibration-decomposition-2026-09-04.md",
    FAMILY_DIR / "diagnostics/binance-1d-ma7-ctp-p7a-placebo-base-rate-audit-2026-09-04.md",
]


def load_p7b():
    spec = importlib.util.spec_from_file_location("p7b_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.fixture(scope="module")
def p7b():
    return load_p7b()


@pytest.fixture(scope="module")
def summary():
    path = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_summary.json"
    assert path.exists(), "P7B summary missing; run the audit script first"
    return load_json(path)


@pytest.fixture(scope="module")
def manifest():
    path = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_manifest.json"
    assert path.exists(), "P7B manifest missing; run the audit script first"
    return load_json(path)


@pytest.fixture(scope="module")
def config():
    return load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_config.json")


@pytest.fixture(scope="module")
def lock():
    return load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_contract_lock.json")


@pytest.fixture(scope="module")
def inventory():
    return load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_input_inventory.json")


@pytest.fixture(scope="module")
def six_grid():
    return pd.read_csv(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_six_grid_summary.csv")


def test_hype_raw_partition_not_read(summary, inventory) -> None:
    assert summary["isolation"]["hype_raw_partition_read"] is False
    assert summary["isolation"]["hype_slug_in_files_read"] is False
    for item in inventory["files"]:
        path = item["path"].lower()
        assert "hype_usdt_usdt" not in path or "hyper_usdt_usdt" in path


def test_hype_rows_zero_hyper_present(summary, p7b) -> None:
    assert summary["parity"]["hype_rows"] == 0
    assert summary["parity"]["hyper_rows"] > 0
    dual = pd.read_parquet(p7b.P7A_DUAL_PATH)
    assert int((dual["asset"] == "HYPE/USDT:USDT").sum()) == 0
    assert int((dual["asset"] == "HYPER/USDT:USDT").sum()) > 0


def test_p7a_canonical_event_identity(summary, p7b) -> None:
    parity = summary["parity"]
    assert parity["real_n"] == 101029
    assert parity["real_2025_plus"] == 46892
    assert parity["real_2025"] == 32111
    assert parity["real_2026"] == 14781
    assert parity["canonical_event_id_hash"] == p7b.EXPECTED_P7A_EVENT_HASH
    assert parity["canonical_event_id_hash_2025_plus"] == p7b.EXPECTED_P7A_EVENT_HASH_2025_PLUS
    assert parity["anchors_ok"] is True
    assert summary["p7a_dual_parity"]["ok"] is True
    assert summary["p7a_dual_parity"]["success_mismatch"] == 0
    assert summary["p7a_dual_parity"]["net_mismatch"] == 0


def test_hypothetical_long_short_match_p7a(summary, p7b) -> None:
    assert summary["p7a_dual_parity"]["ok"] is True
    p7a = pd.read_parquet(p7b.P7A_DUAL_PATH)
    np.testing.assert_allclose(
        p7a["rs_success"].to_numpy(dtype=float),
        0.5 * p7a["long_success"].to_numpy(dtype=float) + 0.5 * p7a["short_success"].to_numpy(dtype=float),
        rtol=0,
        atol=0,
    )


def test_p6_regime_parity(summary, p7b) -> None:
    assert summary["regime_parity"]["ok"] is True
    assert summary["regime_parity"]["state_mismatch"] == 0
    assert summary["regime_parity"]["six_grid_mismatch"] == 0
    assert summary["regime_parity"]["bull_threshold"] == 0.60
    assert summary["regime_parity"]["bear_threshold"] == 0.40
    assert summary["regime_parity"]["unknown_official_rows"] == 0
    assert summary["regime_parity"]["dates_with_multiple_states"] == 0


def test_regime_does_not_use_future_information(p7b) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "feature_known_at_ne_ts_plus_1d" in src
    assert "no_future_regime" in src
    audit = load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_event_regime_parity.json")
    assert audit["timing"]["feature_known_at_equals_entry_ts"] is True
    assert audit["timing"]["no_future_regime"] is True
    assert p7b.BULL_BREADTH == 0.60
    assert p7b.BEAR_BREADTH == 0.40


def test_six_grid_frozen(config, six_grid, p7b) -> None:
    assert list(config["six_grid"]) == list(p7b.SIX_GRID)
    assert list(six_grid["cell"]) == [
        "BULL_UP", "BULL_DOWN", "BEAR_UP", "BEAR_DOWN", "MIXED_UP", "MIXED_DOWN",
    ]
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "SIX_GRID = (" in src
    assert "0.65" not in src
    assert "0.75" not in src
    assert "0.80" not in src or "80-100%" in src
    assert "for thresh" not in src
    assert "grid_search" not in src.lower()


def test_bull_bear_thresholds_frozen(config, lock, p7b) -> None:
    assert config["bull_breadth_gte"] == 0.60
    assert config["bear_breadth_lte"] == 0.40
    assert lock["bull_breadth_gte"] == 0.60
    assert lock["bear_breadth_lte"] == 0.40
    assert p7b.BULL_BREADTH == 0.60
    assert p7b.BEAR_BREADTH == 0.40
    assert p7b.STRONG_BULL_BREADTH == 0.70
    assert p7b.STRONG_BEAR_BREADTH == 0.30


def test_no_primary_regime_threshold_search(p7b) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "BULL_BREADTH = 0.60" in src
    assert "BEAR_BREADTH = 0.40" in src
    assert "restore_market_state_fields(" in src
    assert "for bull in" not in src
    assert "np.linspace" not in src


def test_date_matching_uses_cross_date_weights(six_grid, p7b) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert 'n_by_date = c.groupby("date").size()' in src or "n_cell" in src
    assert "date_weighted_mean" in src
    row = six_grid.loc[six_grid["cell"].eq("BULL_UP")].iloc[0]
    if int(row["dates_missing_noncross"]) == 0 and int(row["n"]) > 0:
        np.testing.assert_allclose(
            row["incremental_edge"],
            (row["real_success"] - row["random_success"]) - (row["noncross_same_success"] - row["noncross_random_success"]),
            rtol=0,
            atol=1e-12,
        )


def test_non_cross_candidates_have_no_cross(p7b) -> None:
    dual = pd.read_parquet(p7b.P7A_DUAL_PATH)
    non = dual.loc[~dual["is_cross"]]
    assert int(non["is_cross"].sum()) == 0
    assert set(non["real_side"].unique()).issubset({""})


def test_same_side_baseline_and_random_side(p7b) -> None:
    np.testing.assert_allclose(
        p7b.random_side_expectation(np.array([1.0, 0.0]), np.array([0.0, 1.0])),
        np.array([0.5, 0.5]),
        rtol=0,
        atol=0,
    )
    long_s = np.array([0.4, 0.2])
    short_s = np.array([0.1, 0.3])
    rs = p7b.random_side_expectation(long_s, short_s)
    np.testing.assert_allclose(rs, 0.5 * long_s + 0.5 * short_s, rtol=0, atol=0)


def test_incremental_formula_subtracts_regime_drift(p7b) -> None:
    # Cross looks +5pp vs random, but bull non-cross long also +5pp vs random.
    cross_real, cross_rs = 0.38, 0.33
    non_long, non_rs = 0.37, 0.32
    dir_edge = cross_real - cross_rs
    drift = non_long - non_rs
    inc = p7b.incremental_edge(dir_edge, drift)
    np.testing.assert_allclose(inc, 0.0, rtol=0, atol=1e-15)
    assert inc == pytest.approx((cross_real - cross_rs) - (non_long - non_rs))


def test_bull_and_bear_drift_not_credited_to_ma7(six_grid, p7b) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "incremental = (real - random) - (noncross_same - noncross_random)" in src or "incremental_edge(dir_edge, drift)" in src
    report = (DIAG_DIR / "binance-1d-ma7-ctp-p7b-regime-conditional-direction-placebo-audit-2026-09-04.md").read_text(encoding="utf-8")
    assert "禁止把 Bull 本身的 Long drift" in report
    drift = pd.read_csv(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_regime_drift_decomposition.csv")
    assert bool(drift.loc[drift["cell"].str.startswith("BULL"), "bull_drift_not_ma7"].all())
    assert bool(drift.loc[drift["cell"].str.startswith("BEAR"), "bear_drift_not_ma7"].all())
    for _, row in six_grid.iterrows():
        if np.isfinite(row["incremental_edge"]) and np.isfinite(row["directional_edge"]) and np.isfinite(row["regime_drift"]):
            np.testing.assert_allclose(
                row["incremental_edge"],
                row["directional_edge"] - row["regime_drift"],
                rtol=0,
                atol=1e-10,
            )


def test_block_bootstrap_keeps_date_clusters_and_paired_replicates(summary, p7b) -> None:
    boot = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_bootstrap.parquet")
    assert len(boot) == 2000
    assert boot["replicate"].tolist() == list(range(2000))
    meta = summary["bootstrap"]
    assert meta["n"] == 2000
    assert meta["seed"] == 20260901
    assert meta["block_days"] == 28
    for col in ["BULL_UP_INCREMENTAL_EDGE", "BEAR_DOWN_INCREMENTAL_EDGE", "REGIME_ALIGNMENT_EFFECT"]:
        assert col in boot.columns
        assert meta["stats"][col]["effective_replicates"] == 2000
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "rng.choice(blocks, size=len(blocks), replace=True)" in src
    assert "metrics_from_pack(pack, idx)" in src


def test_bh_families(summary) -> None:
    primary = summary["bh_primary"]
    assert set(primary) == {
        "BULL_UP_INCREMENTAL_EDGE",
        "BEAR_DOWN_INCREMENTAL_EDGE",
        "REGIME_ALIGNMENT_EFFECT",
    }
    secondary = summary["bh_secondary"]
    assert set(secondary) == {
        "BULL_UP_incremental_edge",
        "BULL_DOWN_incremental_edge",
        "BEAR_UP_incremental_edge",
        "BEAR_DOWN_incremental_edge",
        "MIXED_UP_incremental_edge",
        "MIXED_DOWN_incremental_edge",
    }
    assert len(secondary) == 6


def test_2025_plus_marked_reused_diagnostic(summary, config) -> None:
    assert config["2025plus_role"] == "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS"
    assert summary["2025plus_role"] == "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS"
    years = pd.read_csv(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_year_breakdown.csv")
    reused = years.loc[years["period"].isin(["2025", "2026", "2025+"])]
    assert (reused["role"] == "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS").all()
    report = (DIAG_DIR / "binance-1d-ma7-ctp-p7b-regime-conditional-direction-placebo-audit-2026-09-04.md").read_text(encoding="utf-8")
    assert "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS" in report
    assert "不是新盲测" in report


def test_no_b0_ml_or_equity(summary, inventory) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    for banned in ("import sklearn", "import lightgbm", "import xgboost", "LogisticRegression"):
        assert banned not in src
    assert "sklearn" not in src
    assert "lightgbm" not in src
    assert summary["no_ml"] is True
    assert summary["no_equity_curve"] is True
    assert summary["no_b0"] is True
    assert summary["isolation"]["no_b0_input"] is True
    for item in inventory["files"]:
        name = Path(item["path"]).name
        assert "_p7_model_reconstruction" not in name
        assert "_p7_frozen_coefficients" not in name
        assert "_p7_feature_contribution" not in name
    assert not list(ARTIFACT_DIR.glob("*p7b*model*"))
    assert not list(ARTIFACT_DIR.glob("*p7b*equity*"))
    assert "R_B0_69_score" not in src or "forbidden_b0" in src
    assert "b0_raw_probability" not in src


def test_manifest_hash_and_p7b_prefix(summary, config, lock, manifest, p7b) -> None:
    assert summary["research_id"] == "BIN-1D-MA7-CTP-P7B-2026-09-04"
    assert config["research_id"] == p7b.RESEARCH_ID
    assert lock["status"] == "FROZEN_BEFORE_P7B_REGIME_OUTCOME_READ"
    assert summary["config_sha256"] == lock["config_sha256"]
    payload = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    assert manifest["manifest_sha256"] == p7b.canonical_sha256(payload)
    for item in manifest["files"]:
        path = ROOT / item["path"]
        assert path.exists()
        assert sha256_file(path) == item["sha256"]
        name = Path(item["path"]).name
        if "p7" in name and "p7a" not in name and "p7b" not in name and "p0-p6" not in name:
            raise AssertionError(name)
        assert ".pytest_cache" not in item["path"]


def test_does_not_overwrite_p0_p7a_or_shared_docs(p7b) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "atomic_write_json(P5_SUMMARY_PATH" not in src
    assert "atomic_write_json(P6_SUMMARY_PATH" not in src
    assert "atomic_write_parquet(P7A_DUAL_PATH" not in src
    assert "binance_1d_ma7_ctp_p7_summary" not in src
    for frozen in FROZEN_P0_P7A:
        assert frozen.exists()
    for path in SHARED_DOCS:
        assert path.name not in {p7b.REPORT_PATH.name, p7b.IMPL_AUDIT_PATH.name}


def test_status_remains_diagnostic_only(summary, config) -> None:
    expected = "explore / diagnostic-only / placebo-audit / not promoted / not live-ready"
    assert summary["status"] == expected
    assert config["status"] == expected
    assert summary["verdict"] in {
        "DATA_OR_REPRODUCTION_FAILURE",
        "NO_REGIME_CONDITIONAL_DIRECTIONAL_EDGE",
        "REGIME_DRIFT_EXPLAINS_APPARENT_EDGE",
        "BULL_ONLY_CONDITIONAL_EDGE",
        "BEAR_ONLY_CONDITIONAL_EDGE",
        "REGIME_ALIGNED_DIRECTIONAL_EDGE_SUPPORTED",
        "REGIME_EFFECT_TEMPORALLY_UNSTABLE",
    }


def test_note_read_refuses_hype_partition(p7b) -> None:
    with pytest.raises(RuntimeError, match="HYPE partition"):
        p7b.note_read(Path("/tmp/asset_slug_partition=hype_usdt_usdt/part.parquet"))


def test_restore_market_state_matches_p6_definition(p7b) -> None:
    breadth = np.array([0.70, 0.70, 0.30, 0.30, 0.50, 0.50])
    btc = np.array([1.0, 1.0, -1.0, -1.0, 1.0, -1.0])
    is_long = np.array([True, False, True, False, True, True])
    raw_b, raw_btc, state = p7b.restore_market_state_fields(breadth, btc, is_long)
    # long: breadth unchanged; short: 1-breadth, -btc
    np.testing.assert_allclose(raw_b, np.array([0.70, 0.30, 0.30, 0.70, 0.50, 0.50]))
    np.testing.assert_allclose(raw_btc, np.array([1.0, -1.0, -1.0, 1.0, 1.0, -1.0]))
    assert list(state) == ["BULL", "BEAR", "BEAR", "BULL", "MIXED", "MIXED"]


def test_required_outputs_exist() -> None:
    required = [
        FAMILY_DIR / "specs/binance-1d-ma7-ctp-p7b-regime-conditional-direction-placebo-audit-2026-09-04.md",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_config.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_contract_lock.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_input_inventory.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_data_audit.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_event_regime_parity.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_six_grid_summary.csv",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_regime_drift_decomposition.csv",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_incremental_edges.csv",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_year_breakdown.csv",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_breadth_bins.csv",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_matching_robustness.csv",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_leave_one_out.parquet",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_bootstrap.parquet",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_summary.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7b_manifest.json",
        DIAG_DIR / "binance-1d-ma7-ctp-p7b-regime-conditional-direction-placebo-audit-2026-09-04.md",
        DIAG_DIR / "binance-1d-ma7-ctp-p7b-implementation-audit-2026-09-04.md",
        DIAG_DIR / "binance-1d-ma7-ctp-p7b-deferred-registration-2026-09-04.md",
    ]
    for path in required:
        assert path.exists(), path
    for i in range(1, 13):
        matches = list(ARTIFACT_DIR.glob(f"binance_1d_ma7_ctp_p7b_chart_{i:02d}_*.svg"))
        assert matches, f"missing chart {i}"


def test_assert_no_p7_input(p7b) -> None:
    p7b.assert_no_p7_input(["research/x/binance_1d_ma7_ctp_p7a_summary.json"])
    with pytest.raises(RuntimeError, match="must not read P7"):
        p7b.assert_no_p7_input(["research/x/binance_1d_ma7_ctp_p7_summary.json"])
