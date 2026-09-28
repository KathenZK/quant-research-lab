from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import duckdb

import pytest



ROOT = Path(__file__).resolve().parents[1]
FAMILY_DIR = (
    ROOT / "research" / "asset-portfolios" / "1d-cross-asset-trend-lifecycle"
)
SCRIPT_PATH = FAMILY_DIR / "scripts" / "run_binance_1d_catl_p0r_modeling_input_repair.py"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
PANEL_GLOB = str(ARTIFACT_DIR / "p0r_donor_directional_modeling_panel/**/*.parquet")
P0_FEATURE_GLOB = str(ARTIFACT_DIR / "p0_asset_day_feature_panel/**/*.parquet")


def load_module():
    spec = importlib.util.spec_from_file_location("catl_p0r", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_frozen_repair_constants_and_hype_asset_boundary():
    mod = load_module()
    assert mod.HYPE_ASSET == "HYPE/USDT:USDT"
    assert mod.HOLDOUT_READ is False
    assert mod.MIN_CAUSAL_VOL_HISTORY == 30
    assert mod.MAX_ATR_TO_ENTRY == 0.50
    assert mod.MAX_ABS_RET_1D == 3.00


@pytest.mark.local_data
def test_output_physically_excludes_hype_but_not_hyper_and_respects_cutoff():
    mod = load_module()
    con = duckdb.connect()
    row = con.execute(
        """
        SELECT
            count(*) AS n,
            count(DISTINCT asset) AS assets,
            count(*) FILTER (WHERE asset = ?) AS hype_n,
            count(*) FILTER (WHERE asset = 'HYPER/USDT:USDT') AS hyper_n,
            max(ts) AS max_ts
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        """,
        [mod.HYPE_ASSET, PANEL_GLOB],
    ).fetchone()
    summary = json.loads(
        (ARTIFACT_DIR / "binance_1d_catl_p0r_summary.json").read_text(encoding="utf-8")
    )["summary"]
    assert row[0] == summary["donor_landmark_rows"]
    assert row[1] == summary["donor_asset_count"]
    assert row[2] == 0
    assert row[3] > 0
    assert str(row[4]) < mod.CUTOFF_UTC


@pytest.mark.local_data
def test_causal_volatility_state_uses_only_strictly_prior_asset_rows():
    mod = load_module()
    con = duckdb.connect()
    mismatch = con.execute(
        f"""
        WITH expected_base AS (
            SELECT
                asset,
                ts,
                atr14_pct,
                count(atr14_pct) OVER prior_rows AS prior_n,
                quantile_cont(atr14_pct, 0.3333333333333333) OVER prior_rows AS q33,
                quantile_cont(atr14_pct, 0.6666666666666666) OVER prior_rows AS q67
            FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
            WHERE asset = 'BTC/USDT:USDT'
            WINDOW prior_rows AS (
                PARTITION BY asset ORDER BY ts
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            )
        ),
        expected AS (
            SELECT
                asset,
                ts,
                prior_n,
                CASE
                    WHEN prior_n < {mod.MIN_CAUSAL_VOL_HISTORY} OR atr14_pct IS NULL
                        THEN 'insufficient_history'
                    WHEN atr14_pct <= q33 THEN 'low'
                    WHEN atr14_pct <= q67 THEN 'mid'
                    ELSE 'high'
                END AS state
            FROM expected_base
        ),
        actual AS (
            SELECT asset, ts, p0r_prior_atr_count, volatility_state_p0r
            FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
            WHERE asset = 'BTC/USDT:USDT' AND side = 'long'
        )
        SELECT count(*)
        FROM actual a
        JOIN expected e USING (asset, ts)
        WHERE a.p0r_prior_atr_count <> e.prior_n
           OR a.volatility_state_p0r <> e.state
        """,
        [P0_FEATURE_GLOB, PANEL_GLOB],
    ).fetchone()[0]
    assert mismatch == 0


@pytest.mark.local_data
def test_liquidity_rank_is_donor_tradable_point_in_time_only():
    mod = load_module()
    con = duckdb.connect()
    ts = con.execute(
        "SELECT max(ts) FROM read_parquet(?, union_by_name=true, hive_partitioning=true)",
        [PANEL_GLOB],
    ).fetchone()[0]
    mismatch, nontradable_ranked = con.execute(
        """
        WITH expected AS (
            SELECT
                asset,
                percent_rank() OVER (ORDER BY quote_volume_30d) AS rank_expected
            FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
            WHERE ts = ?
              AND tradable_marker_p0
              AND asset <> ?
        ),
        actual AS (
            SELECT asset, tradable_marker_p0, liquidity_rank_pct_p0r
            FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
            WHERE ts = ? AND side = 'long'
        )
        SELECT
            count(*) FILTER (
                WHERE a.tradable_marker_p0
                  AND abs(a.liquidity_rank_pct_p0r - e.rank_expected) > 1e-12
            ) AS mismatch,
            count(*) FILTER (
                WHERE NOT a.tradable_marker_p0
                  AND a.liquidity_rank_pct_p0r IS NOT NULL
            ) AS nontradable_ranked
        FROM actual a
        LEFT JOIN expected e USING (asset)
        """,
        [P0_FEATURE_GLOB, ts, mod.HYPE_ASSET, PANEL_GLOB, ts],
    ).fetchone()
    assert mismatch == 0
    assert nontradable_ranked == 0


@pytest.mark.local_data
def test_model_eligibility_is_reconstructable_and_complete_path_specific():
    mod = load_module()
    con = duckdb.connect()
    mismatch = con.execute(
        f"""
        SELECT count(*)
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE base_model_eligible_p0r <>
            (
                tradable_marker_p0
                AND entry_ref > 0
                AND atr_anchor > 0
                AND atr_to_entry_p0r <= {mod.MAX_ATR_TO_ENTRY}
                AND NOT price_scale_discontinuity_p0r
            )
           OR model_eligible_entry_p0r <>
            (base_model_eligible_p0r AND future_path_complete_20d)
           OR model_eligible_continue_p0r <>
            (base_model_eligible_p0r AND future_path_complete_5d)
        """,
        [PANEL_GLOB],
    ).fetchone()[0]
    assert mismatch == 0


@pytest.mark.local_data
def test_feature_allowlist_exists_in_panel_and_excludes_outcomes_and_legacy_fields():
    feature_spec = json.loads(
        (ARTIFACT_DIR / "binance_1d_catl_p0r_feature_blocks.json").read_text(
            encoding="utf-8"
        )
    )
    allowed = feature_spec["all_allowed_features"]
    assert len(allowed) == len(set(allowed))
    assert not any(name.startswith(("label_", "future_")) for name in allowed)
    assert "asset" not in allowed
    assert "side" not in allowed
    assert "volatility_state" not in allowed
    assert "liquidity_rank_pct" not in allowed
    assert "volatility_state_p0r" in allowed
    assert "liquidity_rank_pct_p0r" in allowed

    con = duckdb.connect()
    columns = {
        row[0]
        for row in con.execute(
            "DESCRIBE SELECT * FROM read_parquet(?, union_by_name=true, hive_partitioning=true)",
            [PANEL_GLOB],
        ).fetchall()
    }
    assert set(allowed).issubset(columns)


@pytest.mark.local_data
def test_manifest_lineage_hashes_and_ready_verdict():
    manifest = json.loads(
        (ARTIFACT_DIR / "binance_1d_catl_p0r_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    summary = json.loads(
        (ARTIFACT_DIR / "binance_1d_catl_p0r_summary.json").read_text(encoding="utf-8")
    )
    assert manifest["holdout_read"] is False
    assert manifest["hype_asset_excluded"] == "HYPE/USDT:USDT"
    assert summary["final_verdict"] == "MODELING_INPUT_READY"
    p0_manifest = ROOT / manifest["input_lineage"]["p0_manifest_path"]
    assert sha256_file(p0_manifest) == manifest["input_lineage"]["p0_manifest_sha256"]
    for item in manifest["artifacts"]:
        path = ROOT / item["path"]
        assert path.exists()
        assert sha256_file(path) == item["sha256"]
