#!/usr/bin/env python3
"""Write non-destructive .cache-meta.json sidecars for existing Binance OHLCV caches."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from strategy_lab.data.catalog import (
    BINANCE_PERP_15M_NORMALIZED_V1,
    BINANCE_PERP_1D_CACHE_FROM_15M,
    BINANCE_PERP_1D_MA7_RC_P0_PANEL,
    BINANCE_PERP_1D_MA7_RC_P3_PANEL,
)
from strategy_lab.data.manifest import (
    CACHE_META_FILENAME,
    LINEAGE_INCOMPLETE,
    cache_meta_template,
    inventory_fingerprint,
    parquet_inventory,
    sha256_file,
    utc_now_iso,
    write_canonical_json,
)

ROOT = Path(__file__).resolve().parents[4]


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    con.execute("SET enable_progress_bar=false")
    return con


def write_public_1d_sidecar() -> Path:
    root = ROOT / "data/cache/binance_perp_1d_from_15m"
    ohlcv = root / "ohlcv_1d"
    monthly = str(ohlcv / "month=*.parquet")
    overlay = ohlcv / "overlay_date_partitions.parquet"
    marker = json.loads((root / "_build_complete.json").read_text(encoding="utf-8"))
    builder = ROOT / "research/asset-portfolios/1d-monthly-cs-momentum-ls3/scripts/research_binance_1d_mcsm_ls3.py"
    con = connect()
    month_rows = int(con.execute(f"SELECT count(*) FROM read_parquet('{monthly}')").fetchone()[0])
    overlay_rows = int(con.execute(f"SELECT count(*) FROM read_parquet('{overlay}')").fetchone()[0])
    overlap = int(
        con.execute(
            f"""
            SELECT count(*) FROM (
                SELECT DISTINCT sym_key, day FROM read_parquet('{monthly}')
                INTERSECT
                SELECT DISTINCT sym_key, day FROM read_parquet('{overlay}')
            )
            """
        ).fetchone()[0]
    )
    effective = con.execute(
        f"""
        SELECT * EXCLUDE (prio) FROM (
            SELECT *, 0 AS prio FROM read_parquet('{monthly}')
            UNION ALL BY NAME
            SELECT *, 1 AS prio FROM read_parquet('{overlay}')
        )
        QUALIFY row_number() OVER (PARTITION BY sym_key, day ORDER BY prio) = 1
        """
    ).fetch_df()
    complete = effective.loc[effective["bars_15m"].eq(96) & effective["all_closed"].fillna(False)]
    inventory = parquet_inventory(root)
    meta = cache_meta_template(
        cache_id=BINANCE_PERP_1D_CACHE_FROM_15M,
        cache_version="legacy-mcsm-ls3-2026-08-18",
        physical_root=str(root),
        input_dataset_id=BINANCE_PERP_15M_NORMALIZED_V1,
        extra={
            "generated_at": marker.get("generated_at", LINEAGE_INCOMPLETE),
            "builder_path": str(builder.relative_to(ROOT)),
            "builder_sha256": sha256_file(builder) if builder.exists() else LINEAGE_INCOMPLETE,
            "input_manifest_sha256": LINEAGE_INCOMPLETE,
            "config_parameter_sha256": LINEAGE_INCOMPLETE,
            "cutoff_exclusive_utc": "2026-07-01T00:00:00+00:00",
            "consumer_cutoff_exclusive_utc": "2026-07-01T00:00:00+00:00",
            "consumer_clip_inclusive_utc": "2026-06-30T00:00:00+00:00",
            "consumer_cutoff_note": "MCSM-LS3 clips the research panel to 2026-06-30 inclusive; cache parquet itself extends later",
            "rows": int(len(effective)),
            "physical_rows": month_rows + overlay_rows,
            "monthly_rows": month_rows,
            "overlay_rows": overlay_rows,
            "overlap_keys": overlap,
            "month_first_effective_keys": int(len(effective)),
            "complete_days_96_closed": int(len(complete)),
            "distinct_keys": int(len(effective)),
            "symbols": int(effective["sym_key"].nunique()),
            "start_utc": pd.Timestamp(effective["day"].min()).isoformat(),
            "end_utc": pd.Timestamp(effective["day"].max()).isoformat(),
            "duplicate_overlap_resolution": "month parquet priority over date=* overlay",
            "completeness_rules": "legacy cache stores partial days; complete UTC day is bars_15m=96 and all_closed",
            "null_fill_policy": "no filling; missing 15m bars shrink the 1d aggregate",
            "rebuild_command": "python research/asset-portfolios/1d-monthly-cs-momentum-ls3/scripts/research_binance_1d_mcsm_ls3.py --rebuild-cache",
            "quality_status": "FAMILY_CACHE / LINEAGE_INCOMPLETE",
            "is_standard_ohlcv": False,
            "parquet_inventory_fingerprint": inventory_fingerprint(inventory),
            "audited_at": utc_now_iso(),
        },
    )
    path = root / CACHE_META_FILENAME
    write_canonical_json(path, meta)
    return path


def write_panel_sidecar(
    *,
    cache_id: str,
    root: Path,
    parquet_name: str,
    builder: Path,
    cutoff: str,
    rebuild_command: str,
) -> Path:
    parquet_path = root / parquet_name
    frame = pd.read_parquet(parquet_path)
    inventory = parquet_inventory(root)
    start = pd.to_datetime(frame["ts"], utc=True).min().isoformat() if "ts" in frame.columns else None
    end = pd.to_datetime(frame["ts"], utc=True).max().isoformat() if "ts" in frame.columns else None
    meta = cache_meta_template(
        cache_id=cache_id,
        cache_version=parquet_name,
        physical_root=str(root),
        input_dataset_id=BINANCE_PERP_15M_NORMALIZED_V1,
        extra={
            "generated_at": LINEAGE_INCOMPLETE,
            "builder_path": str(builder.relative_to(ROOT)) if builder.exists() else LINEAGE_INCOMPLETE,
            "builder_sha256": sha256_file(builder) if builder.exists() else LINEAGE_INCOMPLETE,
            "input_manifest_sha256": LINEAGE_INCOMPLETE,
            "config_parameter_sha256": LINEAGE_INCOMPLETE,
            "cutoff_exclusive_utc": cutoff,
            "rows": int(len(frame)),
            "distinct_keys": int(len(frame)),
            "symbols": int(frame["symbol"].nunique()) if "symbol" in frame.columns else None,
            "start_utc": start,
            "end_utc": end,
            "columns": list(frame.columns),
            "duplicate_overlap_resolution": LINEAGE_INCOMPLETE,
            "completeness_rules": "family panel of complete UTC days plus indicators/labels/future-path fields",
            "null_fill_policy": LINEAGE_INCOMPLETE,
            "rebuild_command": rebuild_command,
            "quality_status": "FAMILY_CACHE / LINEAGE_INCOMPLETE",
            "is_standard_ohlcv": False,
            "parquet_inventory_fingerprint": inventory_fingerprint(inventory),
            "audited_at": utc_now_iso(),
        },
    )
    path = root / CACHE_META_FILENAME
    write_canonical_json(path, meta)
    return path


def main() -> None:
    paths = [
        write_public_1d_sidecar(),
        write_panel_sidecar(
            cache_id=BINANCE_PERP_1D_MA7_RC_P0_PANEL,
            root=ROOT / "data/cache/binance-1d-ma7-rc-p0",
            parquet_name="binance_1d_ma7_rc_p0_daily_panel.parquet",
            builder=ROOT
            / "research/asset-portfolios/1d-ma7-regime-continuation/scripts/research_binance_1d_ma7_regime_continuation.py",
            cutoff="2026-07-01T00:00:00+00:00",
            rebuild_command="python research/asset-portfolios/1d-ma7-regime-continuation/scripts/research_binance_1d_ma7_regime_continuation.py",
        ),
        write_panel_sidecar(
            cache_id=BINANCE_PERP_1D_MA7_RC_P3_PANEL,
            root=ROOT / "data/cache/binance-1d-ma7-rc-p3",
            parquet_name="binance_1d_ma7_rc_p3_daily_panel.parquet",
            builder=ROOT
            / "research/asset-portfolios/1d-ma7-regime-continuation/scripts/run_binance_1d_ma7_regime_p3_confirmatory.py",
            cutoff="2026-08-25T00:00:00+00:00",
            rebuild_command="python research/asset-portfolios/1d-ma7-regime-continuation/scripts/run_binance_1d_ma7_regime_p3_confirmatory.py",
        ),
    ]
    for path in paths:
        print(path.relative_to(ROOT).as_posix(), flush=True)


if __name__ == "__main__":
    main()
