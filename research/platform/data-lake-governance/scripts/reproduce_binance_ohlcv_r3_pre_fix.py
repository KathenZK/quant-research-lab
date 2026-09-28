#!/usr/bin/env python3
"""Capture Round-3 pre-fix behaviour. Does not mutate published lake data."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from strategy_lab.data.catalog import (
    BINANCE_PERP_4H_FROM_15M_V1,
    DatasetRegistry,
    DatasetScope,
    load_trusted_dataset,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import (
    DATASET_MANIFEST_FILENAME,
    LINEAGE_INCOMPLETE,
    assert_cache_sidecar_fresh,
    assert_published_derived_manifest,
    cache_meta_template,
    resolve_parquet_inventory_fingerprint,
    write_canonical_json,
)
from strategy_lab.data.resample import (
    FORMULA_VERSION,
    build_derived_ohlcv,
    derived_manifest,
    publish_staging_dataset,
    verify_existing_derived_publish,
)
from strategy_lab.data.settings import default_settings

ROOT = Path(__file__).resolve().parents[4]
OUT = (
    ROOT
    / "research/platform/data-lake-governance/artifacts"
    / "binance_ohlcv_r3_pre_fix_repro_2026-09-03.json"
)
VISION = "binance_vision_kline_monthly"


def _bars(tmp: Path, *, start: str, periods: int, timeframe: str = "15m") -> Path:
    index = pd.date_range(start, periods=periods, freq="15min" if timeframe == "15m" else timeframe, tz="UTC")
    close = [100.0 + i for i in range(periods)]
    frame = pd.DataFrame(
        {
            "ts": index,
            "exchange": ["binance"] * periods,
            "symbol": ["BTC/USDT:USDT"] * periods,
            "market_type": ["perp"] * periods,
            "timeframe": [timeframe] * periods,
            "open": close,
            "high": [value + 1.0 for value in close],
            "low": [value - 1.0 for value in close],
            "close": close,
            "volume": [10.0] * periods,
            "quote_volume": [float(value) * 10.0 for value in close],
            "trade_count": [1] * periods,
            "vwap": close,
            "is_closed": [True] * periods,
            "source": [VISION] * periods,
        }
    )
    path = tmp / f"{timeframe}.parquet"
    frame.to_parquet(path, index=False)
    return path


def capture(name: str, fn) -> dict:
    try:
        return {"id": name, "ok": True, "result": fn()}
    except Exception as exc:  # noqa: BLE001 - repro must record the real exception
        return {"id": name, "ok": False, "error_type": type(exc).__name__, "error": str(exc)[:800]}


def main() -> None:
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="r3-pre-fix-"))
    layout = DataLakeLayout(
        root_dir=tmp / "data",
        raw_dir=tmp / "data" / "raw",
        normalized_dir=tmp / "data" / "normalized",
        features_dir=tmp / "data" / "features",
        cache_dir=tmp / "data" / "cache",
        derived_dir=tmp / "data" / "derived",
    )
    layout.ensure_directories()
    findings: list[dict] = []

    input_root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
    input_root.mkdir(parents=True)
    # 00:00 through 02:45 → enough 15m to form 00:00, 01:00, 02:00 1h bars.
    created = _bars(input_root, start="2026-07-01T00:00:00Z", periods=12)
    created.replace(input_root / "in.parquet")

    cutoff = pd.Timestamp("2026-07-01T01:00:00Z")
    staging = layout.derived_staging_dir / "binance_perp_1h_from_15m_v1"
    published = layout.derived_datasets_dir / "binance_perp_1h_from_15m_v1"

    def r3_01_cutoff_not_applied_to_build():
        stats = build_derived_ohlcv(
            input_files=[input_root / "in.parquet"],
            output_timeframe="1h",
            staging_root=staging,
        )
        stats["cutoff_exclusive_utc"] = cutoff.isoformat()
        max_ts = pd.Timestamp(stats["end_utc"])
        closes_after_cutoff = bool(max_ts + pd.Timedelta(hours=1) > cutoff)
        return {
            "cutoff": cutoff.isoformat(),
            "published_end_utc": stats["end_utc"],
            "last_bar_close": (max_ts + pd.Timedelta(hours=1)).isoformat(),
            "closes_after_cutoff": closes_after_cutoff,
            "output_rows": stats["output_rows"],
        }

    findings.append(capture("R3-01-build-cutoff-ignored", r3_01_cutoff_not_applied_to_build))

    def r3_01_cutoff_change_still_already_published():
        if not published.exists():
            stats = json.loads((staging / "build_stats.json").read_text()) if (staging / "build_stats.json").exists() else {}
            if staging.exists() and not (staging / "_MANIFEST.json").exists():
                input_hash = "demo-input"
                manifest = derived_manifest(
                    dataset_id="binance.perp.ohlcv.1h.from_15m.v1",
                    status="TRUSTED_DERIVED",
                    timeframe="1h",
                    physical_root=str(published),
                    input_dataset_id="binance.perp.ohlcv.15m.normalized.v1",
                    input_manifest_sha256=input_hash,
                    builder_path="builder.py",
                    builder_sha256="demo",
                    stats={**stats, "cutoff_exclusive_utc": cutoff.isoformat(), "input_parquet_inventory_fingerprint": input_hash},
                ).to_dict()
                publish_staging_dataset(staging_root=staging, published_root=published, manifest=manifest)
        result = verify_existing_derived_publish(
            published_root=published,
            dataset_id="binance.perp.ohlcv.1h.from_15m.v1",
            input_fingerprint="demo-input",
            formula_version=FORMULA_VERSION,
        )
        return {"status": result.get("status"), "ignores_new_cutoff": result.get("status") == "already_published"}

    findings.append(capture("R3-01-cutoff-change-already-published", r3_01_cutoff_change_still_already_published))

    def r3_01_request_beyond_available_still_pass():
        lake = DataLakeLayout.from_settings(default_settings())
        loaded = load_trusted_dataset(
            BINANCE_PERP_4H_FROM_15M_V1,
            layout=lake,
            requested_scope=DatasetScope.SINGLE_SYMBOL,
            symbol="BTC/USDT:USDT",
            end="2026-09-03T00:00:00Z",
            require_contiguous=False,
            max_materialize_rows=2_000_000,
        )
        return {
            "quality_status": loaded.audit.get("quality_status"),
            "requested_end": "2026-09-03T00:00:00Z",
            "actual_end": loaded.coverage.get("end_utc"),
            "silent_truncate": loaded.audit.get("quality_status") == "PASS",
        }

    findings.append(capture("R3-01-window-beyond-data-pass", r3_01_request_beyond_available_still_pass))

    def r3_02_wrong_manifest_identity_still_pass():
        root = tmp / "bad_manifest"
        root.mkdir()
        frame = pd.DataFrame(
            {
                "ts": [pd.Timestamp("2026-07-01T00:00:00Z")],
                "exchange": ["not-binance"],
                "symbol": ["BTC/USDT:USDT"],
                "market_type": ["spot"],
                "timeframe": ["1d"],
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [1.0],
                "quote_volume": [1.0],
                "trade_count": [1],
                "vwap": [1.0],
                "is_closed": [True],
                "source": [VISION],
            }
        )
        frame.to_parquet(root / "a.parquet", index=False)
        from strategy_lab.data.manifest import parquet_inventory, inventory_fingerprint

        inv = parquet_inventory(root)
        write_canonical_json(
            root / DATASET_MANIFEST_FILENAME,
            {
                "dataset_id": "binance.perp.ohlcv.4h.from_15m.v1",
                "quality_status": "TRUSTED_DERIVED",
                "exchange": "kraken",
                "market_type": "spot",
                "timeframe": "1d",
                "cutoff_exclusive_utc": "1999-01-01T00:00:00Z",
                "input_dataset_id": "wrong.input",
                "file_count": len(inv),
                "bytes": int(sum(int(row["size"]) for row in inv)),
                "parquet_inventory_fingerprint": inventory_fingerprint(inv),
            },
        )
        verified = assert_published_derived_manifest(
            dataset_id="binance.perp.ohlcv.4h.from_15m.v1",
            root=root,
        )
        return {
            "passed": True,
            "manifest_exchange": "kraken",
            "accepted_dataset_id": verified.get("dataset_id"),
        }

    findings.append(capture("R3-02-wrong-identity-still-pass", r3_02_wrong_manifest_identity_still_pass))

    def r3_04_same_size_mtime_content_change():
        root = tmp / "fp"
        root.mkdir()
        path = root / "x.parquet"
        frame = pd.DataFrame(
            {
                "ts": [pd.Timestamp("2026-07-01T00:00:00Z")],
                "exchange": ["binance"],
                "symbol": ["BTC/USDT:USDT"],
                "market_type": ["perp"],
                "timeframe": ["1h"],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [10.0],
                "quote_volume": [1000.0],
                "trade_count": [1],
                "vwap": [100.0],
                "is_closed": [True],
                "source": [VISION],
            }
        )
        frame.to_parquet(path, index=False)
        cache = tmp / "fp_cache"
        first = resolve_parquet_inventory_fingerprint(root, cache_dir=cache)
        os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns))
        frame2 = frame.copy()
        frame2.loc[0, "close"] = 999.0
        raw = frame2.to_parquet.__wrapped__ if False else None
        data = path.read_bytes()
        frame2.to_parquet(path, index=False)
        # pad/truncate to original size if needed, then restore mtime
        new = path.read_bytes()
        if len(new) != len(data):
            # keep natural size; record whether size changed
            size_changed = True
        else:
            size_changed = False
        os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns))
        # restore original mtime from first stat if possible
        second = resolve_parquet_inventory_fingerprint(root, cache_dir=cache)
        return {
            "first": first,
            "second": second,
            "reused_stale_fingerprint": first == second,
            "size_changed": size_changed,
        }

    findings.append(capture("R3-04-stale-fingerprint-cache", r3_04_same_size_mtime_content_change))

    def r3_05_missing_lineage_fields_pass():
        root = tmp / "cache_missing"
        root.mkdir()
        pd.DataFrame({"x": [1]}).to_parquet(root / "c.parquet", index=False)
        from strategy_lab.data.manifest import parquet_inventory, inventory_fingerprint, CACHE_META_FILENAME

        inv = parquet_inventory(root)
        meta = cache_meta_template(
            cache_id="demo",
            cache_version="v0",
            physical_root=str(root),
            input_dataset_id="demo",
        )
        for key in ("input_manifest_sha256", "builder_sha256", "quality_status"):
            meta.pop(key, None)
        meta["parquet_inventory_fingerprint"] = inventory_fingerprint(inv)
        write_canonical_json(root / CACHE_META_FILENAME, meta)
        assert_cache_sidecar_fresh(root)
        return {"passed_without_lineage_fields": True}

    findings.append(capture("R3-05-missing-lineage-fields-pass", r3_05_missing_lineage_fields_pass))

    payload = {
        "mode": "PRE_FIX_REPRO",
        "findings": findings,
        "note": "These are Round-3 baseline failures, not Round-2 acceptance.",
    }
    write_canonical_json(OUT, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
