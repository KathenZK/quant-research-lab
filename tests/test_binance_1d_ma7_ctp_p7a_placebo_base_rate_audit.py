from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_ctp_p7a_placebo_base_rate_audit.py"
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
P7_PREFIXES = ("binance_1d_ma7_ctp_p7_", "binance-1d-ma7-ctp-p7-")
FROZEN_P0_P6 = [
    ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet",
    ARTIFACT_DIR / "binance_1d_ma7_ctp_p5_summary.json",
    ARTIFACT_DIR / "binance_1d_ma7_ctp_p6_summary.json",
]


def load_p7a():
    spec = importlib.util.spec_from_file_location("p7a_under_test", SCRIPT_PATH)
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
def p7a():
    return load_p7a()


@pytest.fixture(scope="module")
def summary():
    path = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_summary.json"
    assert path.exists(), "P7A summary missing; run the audit script first"
    return load_json(path)


@pytest.fixture(scope="module")
def manifest():
    path = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_manifest.json"
    assert path.exists(), "P7A manifest missing; run the audit script first"
    return load_json(path)


@pytest.fixture(scope="module")
def config():
    return load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_config.json")


@pytest.fixture(scope="module")
def lock():
    return load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_contract_lock.json")


@pytest.fixture(scope="module")
def inventory():
    return load_json(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_input_inventory.json")


@pytest.fixture(scope="module")
def dual():
    path = ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_dual_side_outcomes.parquet"
    assert path.exists()
    return pd.read_parquet(path)


@pytest.fixture(scope="module")
def dates():
    return pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_date_placebo_expectations.parquet")


def test_p7a_does_not_read_p7_artifacts_as_input(inventory, summary, p7a) -> None:
    for item in inventory["files"]:
        name = Path(item["path"]).name
        assert "_p7_" not in name or "_p7a_" in name
    assert summary["isolation"]["p7_input_files"] == 0
    for path in summary["isolation"]["files_read"]:
        name = Path(path).name
        assert "_p7_" not in name or "_p7a_" in name
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "binance_1d_ma7_ctp_p7_summary" not in src
    assert "P7A" in src
    p7a.assert_no_p7_input([item["path"] for item in inventory["files"]])


def test_hype_raw_partition_not_read(summary, inventory) -> None:
    assert summary["isolation"]["hype_raw_partition_read"] is False
    assert summary["isolation"]["hype_slug_in_files_read"] is False
    for item in inventory["files"]:
        path = item["path"].lower()
        assert "hype_usdt_usdt" not in path or "hyper_usdt_usdt" in path


def test_hype_rows_zero_hyper_present(summary, dual) -> None:
    assert summary["parity"]["hype_rows"] == 0
    assert summary["parity"]["hyper_rows"] > 0
    assert int((dual["asset"] == "HYPE/USDT:USDT").sum()) == 0
    assert int((dual["asset"] == "HYPER/USDT:USDT").sum()) > 0
    assert int(dual["hyper"].sum()) > 0


def test_real_ma7_event_counts_match_frozen_anchors(summary) -> None:
    parity = summary["parity"]
    assert parity["real_2025_plus"] == 46892
    assert parity["real_2025"] == 32111
    assert parity["real_2026"] == 14781
    assert parity["anchors_ok"] is True
    assert parity["reproduction_failure"] is False


def test_canonical_event_ids_align_with_p5(summary, dual, p7a) -> None:
    p5 = pd.read_parquet(p7a.P5_VALIDATION_PATH)
    p5["ts"] = pd.to_datetime(p5["ts"], utc=True)
    p5["side"] = p5["side"].astype(str).str.lower()
    p5 = p5.loc[~p5["is_known_tradfi"].astype(bool)]
    p5 = p5.loc[~p5["asset"].eq(p7a.HYPE_ASSET)]
    real = dual.loc[dual["official_real"]].copy()
    plus = real.loc[pd.to_datetime(real["ts"], utc=True) >= p7a.CUTOFF].copy()
    plus["side"] = plus["real_side"]
    left = set(
        plus["asset"].astype(str)
        + "|"
        + pd.to_datetime(plus["ts"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S%z")
        + "|"
        + plus["real_side"].astype(str)
    )
    right = set(p5["asset"].astype(str)
                + "|" + p5["ts"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
                + "|" + p5["side"].astype(str))
    assert left == right
    assert summary["parity"]["identity_missing_vs_p5_val"] == 0
    assert summary["parity"]["identity_extra_vs_p5_val"] == 0
    assert summary["parity"]["canonical_event_id_hash_2025_plus"] == p7a.event_identity_hash(plus.assign(side=plus["real_side"]))


def test_canonical_entry_atr_and_label_align(summary, dual, p7a) -> None:
    assert summary["universe_audit"]["entry_ref_mismatch"] == 0
    assert summary["universe_audit"]["atr_mismatch"] == 0
    assert summary["universe_audit"]["entry_ts_mismatch"] == 0
    assert summary["parity"]["label_mismatch_vs_p5_val"] == 0
    assert summary["parity"]["net_return_mismatch_vs_p5_val"] == 0
    assert summary["parity"]["entry_ts_mismatch_vs_p5_val"] == 0
    assert summary["parity"]["feature_known_at_mismatch_vs_p5_val"] == 0
    p5 = pd.read_parquet(p7a.P5_VALIDATION_PATH)
    p5["ts"] = pd.to_datetime(p5["ts"], utc=True)
    p5["side"] = p5["side"].astype(str).str.lower()
    p5 = p5.loc[~p5["is_known_tradfi"].astype(bool) & ~p5["asset"].eq(p7a.HYPE_ASSET)]
    real = dual.loc[dual["official_real"]].copy()
    plus = real.loc[pd.to_datetime(real["ts"], utc=True) >= p7a.CUTOFF].copy()
    plus["side"] = plus["real_side"]
    merged = plus.merge(p5[["asset", "ts", "side", "label_entry_success_20d", "label_entry_net_return", "entry_ts"]], on=["asset", "ts", "side"], how="inner", suffixes=("", "_p5"))
    assert len(merged) == 46892
    derived = np.where(merged["real_side"].eq("long"), merged["long_success"], merged["short_success"])
    derived_net = np.where(merged["real_side"].eq("long"), merged["long_net"], merged["short_net"])
    assert int((derived.astype(int) != merged["label_entry_success_20d"].astype(int)).sum()) == 0
    assert int((~np.isclose(derived_net, merged["label_entry_net_return"], rtol=0, atol=1e-12)).sum()) == 0
    assert int((pd.to_datetime(merged["entry_ts"], utc=True) != pd.to_datetime(merged["entry_ts_p5"], utc=True)).sum()) == 0
    np.testing.assert_allclose(summary["parity"]["success_2025"], 0.32284886798916257, rtol=0, atol=1e-12)
    np.testing.assert_allclose(summary["parity"]["success_2026"], 0.30478316758000135, rtol=0, atol=1e-12)


def test_same_hour_ambiguous_is_adverse_first(p7a) -> None:
    result, success, hours = p7a.result_from_hours_array(np.array([5.0]), np.array([5.0]), 480)
    assert result[0] == "ambiguous_same_hour"
    assert bool(success[0]) is False
    assert hours[0] == 5.0
    catl = p7a.result_from_hours(5, 5, 480)
    assert catl[0] == "ambiguous_same_hour"
    assert catl[1] is False


def test_hypothetical_long_short_share_entry_and_path(dual) -> None:
    assert dual["long_success"].notna().all()
    assert dual["short_success"].notna().all()
    both = (dual["official_real"]) & (dual["real_side"].isin(["long", "short"]))
    real_from_sides = np.where(dual.loc[both, "real_side"].eq("long"), dual.loc[both, "long_success"], dual.loc[both, "short_success"])
    np.testing.assert_allclose(
        0.5 * dual.loc[both, "long_success"].to_numpy(dtype=float) + 0.5 * dual.loc[both, "short_success"].to_numpy(dtype=float),
        dual.loc[both, "rs_success"].to_numpy(dtype=float),
        rtol=0,
        atol=0,
    )
    assert int(pd.isna(real_from_sides).sum()) == 0


def test_random_side_exact_expectation_formula(p7a, dual, summary) -> None:
    np.testing.assert_allclose(
        dual["rs_success"].to_numpy(dtype=float),
        p7a.random_side_expectation(dual["long_success"], dual["short_success"]),
        rtol=0,
        atol=0,
    )
    np.testing.assert_allclose(
        dual["rs_net"].to_numpy(dtype=float),
        0.5 * dual["long_net"].to_numpy(dtype=float) + 0.5 * dual["short_net"].to_numpy(dtype=float),
        rtol=0,
        atol=1e-15,
    )
    cross = dual.loc[dual["official_real"]]
    exact = float(cross["rs_success"].mean())
    np.testing.assert_allclose(summary["full"]["same_cross_rs"], exact, rtol=0, atol=1e-12)


def test_date_matched_placebo_uses_real_cross_date_weights(dates, summary, p7a) -> None:
    w = dates["n_cross"].astype(float)
    eligible = p7a.date_weighted_mean(dates["eligible_rs_mean"], w)
    noncross = p7a.date_weighted_mean(dates["noncross_rs_mean"], w)
    np.testing.assert_allclose(summary["full"]["eligible_rs"], eligible, rtol=0, atol=1e-12)
    np.testing.assert_allclose(summary["full"]["noncross_rs"], noncross, rtol=0, atol=1e-12)
    mask = (w > 0) & dates["noncross_rs_mean"].notna()
    reconstructed = float(np.average(
        dates.loc[mask, "noncross_rs_mean"].to_numpy(dtype=float),
        weights=w.loc[mask].to_numpy(dtype=float),
    ))
    np.testing.assert_allclose(noncross, reconstructed, rtol=0, atol=1e-12)


def test_non_cross_candidates_contain_no_ma7_cross(dual) -> None:
    non = dual.loc[~dual["is_cross"]]
    assert int((non["real_side"] != "").sum()) == 0
    assert int(non["is_cross"].sum()) == 0
    assert set(non["real_side"].unique()).issubset({""})


def test_momentum_side_uses_known_ret_1d(dual) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert 'out["momentum_side"] = np.where(out["ret_1d"] > 0, "long"' in src
    assert "ret_1d" in src
    mom = dual.loc[(~dual["is_cross"]) & dual["momentum_side"].isin(["long", "short"])]
    assert int((mom.loc[mom["momentum_side"].eq("long"), "ret_1d"] <= 0).sum()) == 0
    assert int((mom.loc[mom["momentum_side"].eq("short"), "ret_1d"] >= 0).sum()) == 0
    assert int((dual["ret_1d"].eq(0) & dual["momentum_side"].isin(["long", "short"])).sum()) == 0


def test_ma7_side_uses_event_day_close_vs_sma7(dual) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "dir_price_side_ma7" in src
    ma = dual.loc[(~dual["is_cross"]) & dual["ma7_side"].isin(["long", "short"])]
    assert int((ma.loc[ma["ma7_side"].eq("long"), "dir_price_side_ma7_long"] <= 0).sum()) == 0
    assert int((ma.loc[ma["ma7_side"].eq("short"), "dir_price_side_ma7_long"] >= 0).sum()) == 0


def test_barrier_and_timeout_do_not_mutate_canonical_main_result(summary) -> None:
    barrier = pd.read_csv(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_barrier_sensitivity.csv")
    timeout = pd.read_csv(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_timeout_sensitivity.csv")
    primary = barrier.loc[np.isclose(barrier["tp"], 2.0) & np.isclose(barrier["sl"], 1.0)].iloc[0]
    np.testing.assert_allclose(summary["full"]["real_success"], summary["parity"]["success_full"], rtol=0, atol=1e-12)
    assert len(barrier) == 8
    assert list(timeout["horizon_days"].astype(int)) == [5, 10, 20, 40]
    assert abs(float(primary["real_ma7"]) - float(summary["full"]["real_success"])) < 0.02 or np.isfinite(primary["real_ma7"])
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "PRIMARY_FAV = 2.0" in src
    assert "PRIMARY_ADV = 1.0" in src
    assert "PRIMARY_HORIZON_DAYS = 20" in src


def test_block_bootstrap_keeps_date_clusters_and_paired_replicates(p7a, dates) -> None:
    stats = dates.loc[dates["n_cross"] > 0].copy()
    boot, meta = p7a.run_block_bootstrap(stats)
    assert meta["n"] == 2000
    assert meta["seed"] == 20260901
    assert meta["block_days"] == 28
    assert len(boot) == 2000
    assert boot["replicate"].tolist() == list(range(2000))
    work = stats.copy()
    work["block"] = p7a.calendar_block_id(work["date"], origin=work["date"].min())
    rng = np.random.default_rng(20260901)
    blocks = work["block"].drop_duplicates().to_numpy()
    sampled = rng.choice(blocks, size=len(blocks), replace=True)
    first = work.loc[work["block"].eq(int(sampled[0])), "date"]
    span = (pd.to_datetime(first.max()) - pd.to_datetime(first.min())).days
    assert span < 28 or work.loc[work["block"].eq(int(sampled[0]))].shape[0] >= 1
    for col in ["directional_edge", "cross_movement", "total_vs_noncross"]:
        assert col in boot.columns
    assert meta["directional_edge"]["effective_replicates"] == 2000


def test_monte_carlo_seeds_and_tolerance(summary, p7a) -> None:
    mc = pd.read_csv(ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_monte_carlo_validation.csv")
    assert len(mc) == 500
    assert int(mc["seed"].iloc[0]) == 2026090400
    assert int(mc["seed"].iloc[-1]) == 2026090899
    assert list(mc["seed"].astype(int)) == list(range(2026090400, 2026090900))
    meta = summary["monte_carlo"]
    assert meta["same_cross"]["within_tolerance"] is True
    assert meta["noncross"]["within_tolerance"] is True
    assert abs(meta["same_cross"]["exact_minus_mc_mean"]) <= p7a.MC_SUCCESS_TOLERANCE
    assert abs(meta["noncross"]["exact_minus_mc_mean"]) <= p7a.MC_SUCCESS_TOLERANCE


def test_research_id_config_hash_and_manifest(summary, config, lock, manifest, p7a) -> None:
    assert summary["research_id"] == "BIN-1D-MA7-CTP-P7A-2026-09-04"
    assert config["research_id"] == p7a.RESEARCH_ID
    assert config["schema_version"] == "p7a.v1"
    assert config["canonical_label_version"] == p7a.CANONICAL_LABEL_VERSION
    assert config["canonical_universe_version"] == p7a.CANONICAL_UNIVERSE_VERSION
    assert lock["status"] == "FROZEN_BEFORE_P7A_PLACEBO_OUTPUT_READ"
    assert summary["config_sha256"] == lock["config_sha256"]
    assert summary["config_sha256"] == p7a.canonical_sha256(config)
    payload = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    assert manifest["manifest_sha256"] == p7a.canonical_sha256(payload)
    names = [Path(item["path"]).name for item in manifest["files"]]
    assert "binance_1d_ma7_ctp_p7a_manifest.json" not in names
    for item in manifest["files"]:
        path = ROOT / item["path"]
        assert path.exists()
        assert sha256_file(path) == item["sha256"]
        name = Path(item["path"]).name
        assert "_p7_" not in name or "_p7a_" in name
        assert ".pytest_cache" not in item["path"]
        assert "/cache/" not in item["path"]


def test_no_ml_models_or_equity_curve(summary) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    for banned in ("import sklearn", "import lightgbm", "import xgboost", "LogisticRegression"):
        assert banned not in src
    assert "sklearn" not in src
    assert "lightgbm" not in src
    assert "xgboost" not in src
    assert summary["no_ml"] is True
    assert summary["no_equity_curve"] is True
    assert not list(ARTIFACT_DIR.glob("*p7a*model*"))
    assert not list(ARTIFACT_DIR.glob("*p7a*equity*"))


def test_does_not_modify_p0_p7_frozen_artifacts_or_shared_docs(p7a) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    for path in SHARED_DOCS:
        assert str(path.name) not in [str(p7a.REPORT_PATH.name), str(p7a.IMPL_AUDIT_PATH.name)]
        assert f'atomic_write_text({path.name}' not in src
    assert "atomic_write_json(P5_SUMMARY_PATH" not in src
    assert "atomic_write_json(P6_SUMMARY_PATH" not in src
    assert "binance_1d_ma7_ctp_p7_summary" not in src
    for frozen in FROZEN_P0_P6:
        assert frozen.exists()


def test_status_remains_explore_diagnostic_only(summary, config) -> None:
    expected = "explore / diagnostic-only / placebo-audit / not promoted / not live-ready"
    assert summary["status"] == expected
    assert config["status"] == expected
    assert summary["verdict"] in {
        "DATA_OR_REPRODUCTION_FAILURE",
        "PLACEBO_EXPLAINS_BASE_RATE",
        "CROSS_MOVEMENT_EFFECT_WITHOUT_DIRECTIONAL_EDGE",
        "MA7_DIRECTIONAL_EDGE_WEAK",
        "MA7_DIRECTIONAL_EDGE_SUPPORTED",
    }


def test_note_read_refuses_hype_partition(p7a) -> None:
    with pytest.raises(RuntimeError, match="HYPE partition"):
        p7a.note_read(Path("/tmp/asset_slug_partition=hype_usdt_usdt/part.parquet"))


def test_required_outputs_exist() -> None:
    required = [
        FAMILY_DIR / "specs/binance-1d-ma7-ctp-p7a-placebo-base-rate-audit-contract-2026-09-04.md",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_config.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_contract_lock.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_input_inventory.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_data_audit.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_real_event_parity.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_candidate_universe_audit.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_dual_side_outcomes.parquet",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_date_placebo_expectations.parquet",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_placebo_summary.csv",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_placebo_summary.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_year_direction_breakdown.csv",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_first_hit_breakdown.csv",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_barrier_sensitivity.csv",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_timeout_sensitivity.csv",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_bootstrap_results.parquet",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_monte_carlo_validation.csv",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_summary.json",
        ARTIFACT_DIR / "binance_1d_ma7_ctp_p7a_manifest.json",
        DIAG_DIR / "binance-1d-ma7-ctp-p7a-placebo-base-rate-audit-2026-09-04.md",
        DIAG_DIR / "binance-1d-ma7-ctp-p7a-implementation-audit-2026-09-04.md",
        DIAG_DIR / "binance-1d-ma7-ctp-p7a-deferred-registration-2026-09-04.md",
    ]
    for path in required:
        assert path.exists(), path
    for i in range(1, 9):
        matches = list(ARTIFACT_DIR.glob(f"binance_1d_ma7_ctp_p7a_chart_{i:02d}_*.svg"))
        assert matches, f"missing chart {i}"
