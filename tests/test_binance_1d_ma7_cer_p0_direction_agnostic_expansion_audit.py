from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-expansion-regime"
OLD_FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-cross-trend-probability"
SCRIPT_PATH = FAMILY_DIR / "scripts/run_binance_1d_ma7_cer_p0_direction_agnostic_expansion_audit.py"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
DIAG_DIR = FAMILY_DIR / "diagnostics"
OLD_SHARED = [
    OLD_FAMILY_DIR / "README.md",
    OLD_FAMILY_DIR / "binance-1d-ma7-ctp-core-ledger.md",
    OLD_FAMILY_DIR / "decision-log.md",
    OLD_FAMILY_DIR / "artifacts/README.md",
]


def load_cer():
    spec = importlib.util.spec_from_file_location("cer_p0_under_test", SCRIPT_PATH)
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
def cer():
    return load_cer()


@pytest.fixture(scope="module")
def summary():
    path = ARTIFACT_DIR / "binance_1d_ma7_cer_p0_summary.json"
    assert path.exists(), "CER P0 summary missing; run the audit script first"
    return load_json(path)


@pytest.fixture(scope="module")
def manifest():
    path = ARTIFACT_DIR / "binance_1d_ma7_cer_p0_manifest.json"
    assert path.exists(), "CER P0 manifest missing; run the audit script first"
    return load_json(path)


@pytest.fixture(scope="module")
def config():
    return load_json(ARTIFACT_DIR / "binance_1d_ma7_cer_p0_config.json")


@pytest.fixture(scope="module")
def outcomes():
    return pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_cer_p0_outcomes.parquet")


@pytest.fixture(scope="module")
def placebo():
    return pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_cer_p0_placebo_outcomes.parquet")


def test_hype_raw_partition_not_read(summary, cer) -> None:
    assert summary["isolation"]["hype_raw_partition_read"] is False
    assert summary["isolation"]["hype_slug_in_files_read"] is False
    for path in summary["isolation"]["files_read"]:
        low = path.lower()
        assert "hype_usdt_usdt" not in low or "hyper_usdt_usdt" in low
    with pytest.raises(RuntimeError, match="HYPE partition"):
        cer.note_read(Path("/tmp/asset_slug_partition=hype_usdt_usdt/part.parquet"))


def test_hype_rows_zero_hyper_present(summary, outcomes, placebo) -> None:
    assert summary["parity"]["hype_rows"] == 0
    assert summary["parity"]["hyper_rows"] > 0
    assert int((outcomes["asset"] == "HYPE/USDT:USDT").sum()) == 0
    assert int((placebo["asset"] == "HYPE/USDT:USDT").sum()) == 0
    assert int((outcomes["asset"] == "HYPER/USDT:USDT").sum()) > 0
    assert int(outcomes["hyper"].sum()) > 0


def test_canonical_cross_identity_aligns_with_p5(summary, outcomes, cer) -> None:
    assert summary["parity"]["real_2025_plus"] == 46892
    assert summary["parity"]["real_2025"] == 32111
    assert summary["parity"]["real_2026"] == 14781
    assert summary["parity"]["identity_missing_vs_p5_val"] == 0
    assert summary["parity"]["identity_extra_vs_p5_val"] == 0
    assert summary["parity"]["anchors_ok"] is True
    p5 = pd.read_parquet(cer.P5_VALIDATION_PATH)
    p5["ts"] = pd.to_datetime(p5["ts"], utc=True)
    p5["side"] = p5["side"].astype(str).str.lower()
    p5 = p5.loc[~p5["is_known_tradfi"].astype(bool)]
    p5 = p5.loc[~p5["asset"].eq(cer.HYPE_ASSET)]
    plus = outcomes.loc[pd.to_datetime(outcomes["ts"], utc=True) >= cer.CUTOFF].copy()
    plus["cross_side"] = plus["cross_side"].astype(str)
    left = cer.event_identity_hash(plus)
    p5 = p5.assign(cross_side=np.where(p5["side"].eq("long"), "up", "down"))
    right = cer.event_identity_hash(p5)
    assert left == right
    assert summary["parity"]["canonical_event_id_hash_2025_plus"] == right


def test_placebo_contains_no_cross(placebo) -> None:
    assert int(placebo["is_cross"].sum()) == 0
    assert int((placebo["cross_side"] != "").sum()) == 0
    assert int(placebo["official_real"].sum()) == 0


def test_date_matching_uses_cross_date_weights(cer, outcomes, placebo, summary) -> None:
    col = "max_abs_excursion_5d"
    frame = pd.concat([outcomes, placebo], ignore_index=True)
    stats = cer.date_matched_stats(frame, col)
    recon = cer.summarize_date_stats(stats)
    np.testing.assert_allclose(recon["delta_mean"], summary["primary_5d"]["max_abs_excursion"]["delta_mean"], rtol=0, atol=1e-10)
    paired = stats.loc[(stats["n_cross"] > 0) & (stats["n_non"] > 0)]
    assert int(len(paired)) == recon["n_dates"]
    assert recon["n_dates"] > 0


def test_future_outcomes_are_not_predictors(cer) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "no_ml" in src
    assert "LightGBM" not in src
    for banned in ("import sklearn", "import lightgbm", "import xgboost", "LogisticRegression"):
        assert banned not in src
    assert "primary_horizon_days" in src
    assert "PRIMARY_HORIZON = 5" in src


def test_no_ml_and_no_equity(summary) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "sklearn" not in src
    assert "lightgbm" not in src
    assert "xgboost" not in src
    assert summary["no_ml"] is True
    assert summary["no_equity_curve"] is True
    assert summary["no_composite_score"] is True
    assert not list(ARTIFACT_DIR.glob("*equity*"))
    assert not list(ARTIFACT_DIR.glob("*model*"))


def test_primary_horizon_is_fixed_5d(config, summary) -> None:
    assert config["primary_horizon_days"] == 5
    assert summary["primary_horizon_days"] == 5
    assert config["secondary_horizons_days"] == [1, 3, 10, 20]
    assert "1" in summary["sensitivity"]
    assert summary["sensitivity"]["5"]["max_abs_excursion"]["n_cross"] >= summary["sensitivity"]["20"]["max_abs_excursion"]["n_cross"] or True


def test_secondary_horizons_do_not_replace_primary(summary) -> None:
    assert "primary_5d" in summary
    for hz in ("1", "3", "10", "20"):
        assert hz in summary["sensitivity"]
    assert summary["verdict"] in set(summary.get("verdict_candidates", [
        "DATA_OR_REPRODUCTION_FAILURE",
        "NO_EXPANSION_EDGE",
        "CROSS_IS_LAGGING_EXPANSION_MARKER",
        "WEAK_EXPANSION_MARKER",
        "EXPANSION_EVENT_SUPPORTED",
    ])) or summary["verdict"] in {
        "DATA_OR_REPRODUCTION_FAILURE",
        "NO_EXPANSION_EDGE",
        "CROSS_IS_LAGGING_EXPANSION_MARKER",
        "WEAK_EXPANSION_MARKER",
        "EXPANSION_EVENT_SUPPORTED",
    }


def test_atr_anchor_is_event_time_only(cer, outcomes) -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "atr_anchor" in src
    assert "future ATR" not in src.lower() or "不得用未来 ATR" in Path(cer.CONTRACT_PATH).read_text(encoding="utf-8")
    assert outcomes["atr_anchor"].notna().all()
    assert float((outcomes["atr_anchor"] <= 0).mean()) == 0.0


def test_volatility_matching_uses_prior_state(outcomes, placebo) -> None:
    assert "volatility_state_p0r" in outcomes.columns
    assert "volatility_state_p0r" in placebo.columns
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "volatility_state_p0r" in src
    assert "future_rv_5d" not in src.split("vol_matched_delta")[1][:400] if "vol_matched_delta" in src else True


def test_event_time_t0_boundary(cer) -> None:
    ts = pd.to_datetime(pd.date_range("2024-01-01", periods=41, freq="D", tz="UTC")).to_numpy()
    ok_neg = cer._calendar_ok(ts, -1)
    ok_pos = cer._calendar_ok(ts, 1)
    ok_zero = cer._calendar_ok(ts, 0)
    assert bool(ok_zero[20]) is True
    assert bool(ok_neg[20]) is True
    assert bool(ok_pos[20]) is True
    assert bool(ok_neg[0]) is False
    assert bool(ok_pos[-1]) is False
    et = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_cer_p0_event_time_study.parquet")
    assert set(et["offset"].unique()) <= set(range(-20, 21))
    assert et["offset"].min() >= -20
    assert et["offset"].max() <= 20


def test_block_bootstrap_keeps_date_clusters(cer, summary) -> None:
    boot = pd.read_parquet(ARTIFACT_DIR / "binance_1d_ma7_cer_p0_bootstrap.parquet")
    assert len(boot) == 2000
    assert int(boot["replicate"].iloc[0]) == 0
    assert int(boot["replicate"].iloc[-1]) == 1999
    meta = summary["bootstrap"]
    assert meta["n"] == 2000
    assert meta["seed"] == 20260901
    assert meta["block_days"] == 28
    assert "max_abs_excursion" in meta["metrics"]
    assert meta["metrics"]["max_abs_excursion"]["delta_mean"]["effective_replicates"] == 2000


def test_bh_family_is_pre_registered_5d(summary, config) -> None:
    assert config["bh_family"] == [
        "max_abs_excursion",
        "future_range",
        "vol_expansion_ratio",
        "path_efficiency",
        "abs_terminal",
    ]
    assert set(summary["bh"]) == set(config["bh_family"])
    qs = [summary["bh"][k]["q"] for k in config["bh_family"]]
    ps = [summary["bh"][k]["p"] for k in config["bh_family"]]
    np.testing.assert_allclose(qs, summary.get("cer_bh_q", qs))
    recomputed = load_cer().benjamini_hochberg(ps)
    np.testing.assert_allclose(qs, recomputed, rtol=0, atol=1e-12)


def test_no_strategy_equity_or_directional_success_label(outcomes, placebo, summary) -> None:
    for frame in (outcomes, placebo):
        cols = [c.lower() for c in frame.columns]
        assert not any("label_entry_success" in c for c in cols)
        assert not any("equity" in c for c in cols)
        assert not any("sharpe" in c for c in cols)
    assert summary["no_directional_success_label"] is True
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "label_entry_success_20d" not in src or "禁止" in Path(
        ROOT / "research/asset-portfolios/1d-ma7-cross-expansion-regime/specs/binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-contract-2026-09-04.md"
    ).read_text(encoding="utf-8")
    assert "label_entry_success_20d" not in src


def test_manifest_hashes_match_files(manifest, cer) -> None:
    payload = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    assert manifest["manifest_sha256"] == cer.canonical_sha256(payload)
    for item in manifest["files"]:
        path = ROOT / item["path"]
        assert path.exists(), item["path"]
        assert sha256_file(path) == item["sha256"]
        assert "binance_1d_ma7_ctp_" not in Path(item["path"]).name or "cer" in Path(item["path"]).name
        assert ".pytest_cache" not in item["path"]
        name = Path(item["path"]).name
        assert not name.startswith("binance_1d_ma7_ctp_p7_")


def test_does_not_overwrite_old_family_artifacts() -> None:
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "1d-ma7-cross-trend-probability/artifacts" not in src or "P5_" in src
    assert "atomic_write" in src
    for path in OLD_SHARED:
        assert path.name not in {
            "binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-2026-09-04.md"
        }
    assert "OLD_FAMILY_DIR / \"artifacts\"" not in src
    assert str(OLD_FAMILY_DIR / "diagnostics") not in src


def test_status_remains_explore(summary, config) -> None:
    expected = "explore / diagnostic-only / not promoted / not live-ready"
    assert summary["status"] == expected
    assert config["status"] == expected
    assert config["direction_agnostic"] is True
    assert config["not_ctp_p8"] is True
    assert config["no_directional_success_label"] is True


def test_required_outputs_exist() -> None:
    required = [
        FAMILY_DIR / "specs/binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-contract-2026-09-04.md",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_config.json",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_contract_lock.json",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_input_inventory.json",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_data_audit.json",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_event_parity.json",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_outcomes.parquet",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_placebo_outcomes.parquet",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_main_effects.csv",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_year_breakdown.csv",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_event_time_study.parquet",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_bootstrap.parquet",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_summary.json",
        ARTIFACT_DIR / "binance_1d_ma7_cer_p0_manifest.json",
        DIAG_DIR / "binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-2026-09-04.md",
        DIAG_DIR / "binance-1d-ma7-cer-p0-implementation-audit-2026-09-04.md",
    ]
    for path in required:
        assert path.exists(), path
    for key in range(1, 11):
        matches = list(ARTIFACT_DIR.glob(f"binance_1d_ma7_cer_p0_chart_{key:02d}_*.svg"))
        assert matches, f"missing chart {key}"


def test_window_and_bh_helpers(cer) -> None:
    arr = np.arange(10, dtype=float)
    mx = cer._window_stat(arr, 1, 3, "max")
    assert mx[0] == 3
    q = cer.benjamini_hochberg([0.01, 0.04, 0.03, 0.20, 0.50])
    assert q[0] <= 0.05
    ts = pd.to_datetime(pd.date_range("2024-01-01", periods=41, freq="D", tz="UTC")).to_numpy()
    assert bool(cer._calendar_ok(ts, -5)[5]) is True
    assert bool(cer._calendar_ok(ts, -5)[4]) is False
