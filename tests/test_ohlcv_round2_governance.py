from __future__ import annotations

import hashlib
from pathlib import Path
import json

import pandas as pd
import pytest

from strategy_lab.data import (
    DataLakeLayout,
    DatasetKind,
    DatasetRecord,
    DatasetRegistry,
    DatasetScope,
    DatasetStatus,
    LINEAGE_INCOMPLETE,
    MarketType,
    SourceUnionPolicy,
    assert_cache_sidecar_fresh,
    build_derived_ohlcv,
    inspect_dataset,
    load_canonical_binance_perp_1d,
    load_trusted_dataset,
    publish_staging_dataset,
    verify_existing_derived_publish,
)
from strategy_lab.data.catalog import (
    BINANCE_PERP_1D_CACHE_FROM_15M,
    BINANCE_PERP_1D_FROM_15M_V1,
    FullMarketCoverageSpec,
)
from strategy_lab.data.manifest import (
    CACHE_META_FILENAME,
    DATASET_MANIFEST_FILENAME,
    inventory_fingerprint,
    parquet_inventory,
    write_canonical_json,
)
from strategy_lab.data.resample import FORMULA_VERSION, derived_manifest


VISION = "binance_vision_kline_monthly"
API = "binance_futures_kline_api"


def _layout(tmp_path: Path) -> DataLakeLayout:
    layout = DataLakeLayout(
        root_dir=tmp_path / "data",
        raw_dir=tmp_path / "data" / "raw",
        normalized_dir=tmp_path / "data" / "normalized",
        features_dir=tmp_path / "data" / "features",
        cache_dir=tmp_path / "data" / "cache",
        derived_dir=tmp_path / "data" / "derived",
    )
    layout.ensure_directories()
    return layout


def _bars(
    *,
    start: str,
    periods: int,
    symbol: str = "BTC/USDT:USDT",
    source: str = VISION,
    timeframe: str = "15m",
    closed: bool = True,
    open_px: float = 100.0,
    freq: str | None = None,
) -> pd.DataFrame:
    resolved_freq = freq or {"15m": "15min", "1h": "h", "4h": "4h", "1d": "D"}[timeframe]
    index = pd.date_range(start, periods=periods, freq=resolved_freq, tz="UTC")
    close = [open_px + i for i in range(periods)]
    return pd.DataFrame(
        {
            "ts": index,
            "exchange": ["binance"] * periods,
            "symbol": [symbol] * periods,
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
            "is_closed": [closed] * periods,
            "source": [source] * periods,
        }
    )


def _record(
    *,
    dataset_id: str,
    relative_root: str,
    status: DatasetStatus,
    declared_scope: DatasetScope,
    timeframe: str,
    layer: str = "normalized",
    passthrough: bool = False,
    is_standard_ohlcv: bool = True,
    coverage_spec=None,
) -> DatasetRecord:
    return DatasetRecord(
        dataset_id=dataset_id,
        layer=layer,
        kind=DatasetKind.OHLCV,
        status=status,
        declared_scope=declared_scope,
        exchange="binance",
        market_type=MarketType.PERP,
        timeframe=timeframe,
        relative_root=relative_root,
        source_adjudication="test",
        priority_union_version="test-union",
        rebuildable=True,
        is_standard_ohlcv=is_standard_ohlcv,
        coverage_spec=coverage_spec,
        source_union=SourceUnionPolicy(
            version="test-union",
            priority=() if passthrough else (VISION, API),
            reject_unlisted=not passthrough,
            passthrough=passthrough,
        ),
    )


def _seal_derived(root: Path, dataset_id: str, *, timeframe: str | None = None) -> None:
    inventory = parquet_inventory(root)
    tf = timeframe or (
        "1d" if ".1d." in dataset_id or dataset_id.endswith("1d")
        else "4h" if ".4h." in dataset_id or "4h" in dataset_id
        else "1h" if ".1h." in dataset_id or "1h" in dataset_id
        else "4h"
    )
    historical = dataset_id in {
        "binance.perp.ohlcv.1h.from_15m.v1",
        "binance.perp.ohlcv.4h.from_15m.v1",
        "binance.perp.ohlcv.1d.from_15m.v1",
    }
    cutoff = None if historical else "2026-08-25T00:00:00+00:00"
    declared_scope = "FULL_MARKET" if historical else "PARTIAL"
    input_hash = hashlib.sha256(b"test-input").hexdigest()
    stats = {
        "file_count": len(inventory),
        "bytes": int(sum(int(row["size"]) for row in inventory)),
        "output_rows": 0,
        "distinct_keys": 0,
        "symbols": 0,
        "start_utc": "2026-07-01T00:00:00+00:00",
        "end_utc": "2026-07-01T00:00:00+00:00",
        "parquet_inventory_fingerprint": inventory_fingerprint(inventory),
        "cutoff_exclusive_utc": cutoff,
        "rebuild_command": (
            "python research/platform/data-lake-governance/scripts/"
            f"build_binance_derived_ohlcv_from_15m.py --timeframe {tf} "
            f"--dataset-version v1 --input-snapshot-fingerprint {input_hash}"
            + ("" if cutoff is None else f" --cutoff-exclusive-utc {cutoff}")
        ),
        "aggregation_impl_sha256": hashlib.sha256(b"test-impl").hexdigest(),
        "input_parquet_inventory_fingerprint": input_hash,
        "excluded_incomplete_buckets": 0,
        "mixed_source_rows": 0,
        "source_counts": {},
    }
    derived_manifest(
        dataset_id=dataset_id,
        status="TRUSTED_DERIVED",
        timeframe=tf,
        physical_root=str(root.resolve()),
        input_dataset_id="binance.perp.ohlcv.15m.normalized.v1",
        input_manifest_sha256=input_hash,
        builder_path="research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py",
        builder_sha256=hashlib.sha256(b"test-builder").hexdigest(),
        stats=stats,
        declared_scope=declared_scope,
    ).write(root / DATASET_MANIFEST_FILENAME)


def test_non_materialized_path_rejects_illegal_ohlc_and_nulls(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
    root.mkdir(parents=True)
    frame = _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h")
    frame.loc[1, "high"] = 1.0
    frame.loc[1, "low"] = 10.0
    frame.to_parquet(root / "bad.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="bad-ohlc",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
                status=DatasetStatus.TRUSTED_BASE,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="1h",
                passthrough=True,
            )
        ]
    )
    with pytest.raises(ValueError, match="not trusted"):
        load_trusted_dataset(
            "bad-ohlc",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
            max_materialize_rows=0,
        )

    nulls = _bars(start="2026-07-02T00:00:00Z", periods=4, timeframe="1h")
    nulls.loc[0, "close"] = None
    null_root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-null"
    null_root.mkdir(parents=True)
    nulls.to_parquet(null_root / "null.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="null-ohlc",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-null",
                status=DatasetStatus.TRUSTED_BASE,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="1h",
                passthrough=True,
            )
        ]
    )
    with pytest.raises(ValueError, match="not trusted"):
        load_trusted_dataset(
            "null-ohlc",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
            max_materialize_rows=0,
        )


def test_non_materialized_path_rejects_unknown_source_and_unclosed(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    unknown_root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-u"
    unknown_root.mkdir(parents=True)
    unknown = _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h", source="not_a_real_source")
    unknown.to_parquet(unknown_root / "u.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="unknown-1h",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-u",
                status=DatasetStatus.TRUSTED_BASE,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="1h",
                passthrough=True,
            )
        ]
    )
    with pytest.raises(ValueError, match="not trusted"):
        load_trusted_dataset(
            "unknown-1h",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
            max_materialize_rows=0,
        )

    open_root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-open"
    open_root.mkdir(parents=True)
    opened = _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h", closed=False)
    opened.to_parquet(open_root / "o.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="open-1h",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-open",
                status=DatasetStatus.TRUSTED_BASE,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="1h",
                passthrough=True,
            )
        ]
    )
    with pytest.raises(ValueError, match="not trusted"):
        load_trusted_dataset(
            "open-1h",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
            require_closed=True,
            max_materialize_rows=0,
        )


def test_trusted_load_never_returns_empty_audit(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
    root.mkdir(parents=True)
    _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h").to_parquet(root / "ok.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="ok-1h",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
                status=DatasetStatus.TRUSTED_BASE,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="1h",
                passthrough=True,
            )
        ]
    )
    loaded = load_trusted_dataset(
        "ok-1h",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        require_contiguous=False,
        max_materialize_rows=0,
    )
    assert loaded.materialized is False
    assert loaded.audit
    assert loaded.audit["quality_status"] == "PASS"
    assert loaded.audit["rows"] == 4
    assert loaded.source_counts[VISION] == 4
    assert loaded.verified_parquet_files


def test_derived_manifest_missing_tamper_and_file_change_are_rejected(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.derived_datasets_dir / "demo_4h"
    root.mkdir(parents=True)
    frame = _bars(start="2026-07-01T00:00:00Z", periods=2, timeframe="4h")
    frame.to_parquet(root / "a.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="demo-4h",
                relative_root="derived/datasets/demo_4h",
                status=DatasetStatus.TRUSTED_DERIVED,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="4h",
                layer="derived",
                passthrough=True,
            )
        ]
    )
    with pytest.raises(ValueError, match="manifest missing"):
        load_trusted_dataset(
            "demo-4h",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
        )
    _seal_derived(root, "demo-4h")
    loaded = load_trusted_dataset(
        "demo-4h",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        require_contiguous=False,
    )
    assert loaded.audit["quality_status"] == "PASS"
    (root / "extra.parquet").write_bytes(b"not-a-parquet")
    with pytest.raises(ValueError):
        load_trusted_dataset(
            "demo-4h",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
        )
    (root / "extra.parquet").unlink()
    payload = json.loads((root / DATASET_MANIFEST_FILENAME).read_text(encoding="utf-8"))
    payload["dataset_id"] = "other-id"
    write_canonical_json(root / DATASET_MANIFEST_FILENAME, payload)
    with pytest.raises(ValueError, match="dataset_id"):
        load_trusted_dataset(
            "demo-4h",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
        )
    _seal_derived(root, "demo-4h")
    with pytest.raises(ValueError, match="fingerprint"):
        load_trusted_dataset(
            "demo-4h",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
            expected_parquet_fingerprint="0" * 64,
        )


def test_sql_audit_cache_invalidates_when_input_changes(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
    root.mkdir(parents=True)
    path = root / "ok.parquet"
    _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h").to_parquet(path, index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="cache-1h",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
                status=DatasetStatus.TRUSTED_BASE,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="1h",
                passthrough=True,
            )
        ]
    )
    first = load_trusted_dataset(
        "cache-1h",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        require_contiguous=False,
        max_materialize_rows=0,
    )
    assert first.audit["quality_status"] == "PASS"
    bad = _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h")
    bad.loc[0, "high"] = 1.0
    bad.loc[0, "low"] = 50.0
    bad.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="not trusted"):
        load_trusted_dataset(
            "cache-1h",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
            max_materialize_rows=0,
        )


def test_family_cache_cannot_masquerade_as_canonical_ohlcv(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.cache_dir / "binance_perp_1d_from_15m"
    root.mkdir(parents=True)
    _bars(start="2026-07-01T00:00:00Z", periods=2, timeframe="1d").to_parquet(root / "c.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id=BINANCE_PERP_1D_CACHE_FROM_15M,
                relative_root="cache/binance_perp_1d_from_15m",
                status=DatasetStatus.FAMILY_CACHE,
                declared_scope=DatasetScope.FAMILY_PANEL,
                timeframe="1d",
                layer="cache",
                is_standard_ohlcv=False,
            )
        ]
    )
    with pytest.raises(ValueError, match="not standard OHLCV"):
        load_trusted_dataset(
            BINANCE_PERP_1D_CACHE_FROM_15M,
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
        )


def test_lineage_incomplete_rejected_without_expected_hash(tmp_path: Path) -> None:
    root = tmp_path / "cache" / "panel"
    root.mkdir(parents=True)
    frame = _bars(start="2024-01-01T00:00:00Z", periods=4)
    frame.to_parquet(root / "panel.parquet", index=False)
    inventory = parquet_inventory(root)
    write_canonical_json(
        root / CACHE_META_FILENAME,
        {
            "quality_status": "OK",
            "input_manifest_sha256": LINEAGE_INCOMPLETE,
            "builder_sha256": LINEAGE_INCOMPLETE,
            "parquet_inventory_fingerprint": inventory_fingerprint(inventory),
        },
    )
    with pytest.raises(ValueError, match="incomplete"):
        assert_cache_sidecar_fresh(root)
    assert_cache_sidecar_fresh(root, allow_incomplete_lineage=True)


def test_closed_bar_cutoff_excludes_unclosed_open_time(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
    root.mkdir(parents=True)
    frame = _bars(start="2026-08-24T06:00:00Z", periods=3, timeframe="1h")
    frame.to_parquet(root / "cut.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="cutoff-1h",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
                status=DatasetStatus.TRUSTED_BASE,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="1h",
                passthrough=True,
            )
        ]
    )
    loaded = load_trusted_dataset(
        "cutoff-1h",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        require_contiguous=False,
        end="2026-08-24T07:30:00Z",
    )
    assert loaded.materialized
    assert list(loaded.frame["ts"]) == [pd.Timestamp("2026-08-24T06:00:00Z")]
    assert loaded.audit["cutoff_unclosed_excluded_rows"] >= 1


def test_duplicate_keys_and_composite_source_on_sql_path(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.derived_datasets_dir / "comp_4h"
    root.mkdir(parents=True)
    frame = _bars(start="2026-07-01T00:00:00Z", periods=2, timeframe="4h")
    frame["source"] = "composite:binance_futures_kline_api+binance_vision_kline_monthly"
    frame.to_parquet(root / "c.parquet", index=False)
    _seal_derived(root, "comp-4h")
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="comp-4h",
                relative_root="derived/datasets/comp_4h",
                status=DatasetStatus.TRUSTED_DERIVED,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="4h",
                layer="derived",
                passthrough=True,
            )
        ]
    )
    loaded = load_trusted_dataset(
        "comp-4h",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        require_contiguous=False,
        max_materialize_rows=0,
    )
    assert loaded.audit["quality_status"] == "PASS"
    assert any(str(key).startswith("composite:") for key in loaded.source_counts)


def test_same_input_idempotent_different_input_refuses_new_version_publish(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    input_root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
    input_root.mkdir(parents=True)
    frame = _bars(start="2024-01-01T00:00:00Z", periods=4)
    frame.to_parquet(input_root / "in.parquet", index=False)
    staging = layout.derived_staging_dir / "binance_perp_1h_from_15m_v1"
    published = layout.derived_datasets_dir / "binance_perp_1h_from_15m_v1"
    stats = build_derived_ohlcv(
        input_files=[input_root / "in.parquet"],
        output_timeframe="1h",
        staging_root=staging,
    )
    input_hash = inventory_fingerprint(parquet_inventory(input_root))
    stats["input_parquet_inventory_fingerprint"] = input_hash
    manifest = derived_manifest(
        dataset_id="binance.perp.ohlcv.1h.from_15m.v1",
        status="TRUSTED_DERIVED",
        timeframe="1h",
        physical_root=str(published),
        input_dataset_id="binance.perp.ohlcv.15m.normalized.v1",
        input_manifest_sha256=input_hash,
        builder_path="builder.py",
        builder_sha256="demo",
        stats=stats,
    ).to_dict()
    first = publish_staging_dataset(staging_root=staging, published_root=published, manifest=manifest)
    assert first["status"] == "published"
    same = verify_existing_derived_publish(
        published_root=published,
        dataset_id="binance.perp.ohlcv.1h.from_15m.v1",
        input_fingerprint=input_hash,
        formula_version=FORMULA_VERSION,
        cache_dir=layout.cache_dir / "_dataset_quality_audits",
    )
    assert same["status"] == "already_published"
    with pytest.raises(FileExistsError, match="new dataset version"):
        verify_existing_derived_publish(
            published_root=published,
            dataset_id="binance.perp.ohlcv.1h.from_15m.v1",
            input_fingerprint="different-input",
            formula_version=FORMULA_VERSION,
        )
    staging_v2 = layout.derived_staging_dir / "binance_perp_1h_from_15m_v2"
    published_v2 = layout.derived_datasets_dir / "binance_perp_1h_from_15m_v2"
    stats_v2 = build_derived_ohlcv(
        input_files=[input_root / "in.parquet"],
        output_timeframe="1h",
        staging_root=staging_v2,
    )
    manifest_v2 = derived_manifest(
        dataset_id="binance.perp.ohlcv.1h.from_15m.v2",
        status="TRUSTED_DERIVED",
        timeframe="1h",
        physical_root=str(published_v2),
        input_dataset_id="binance.perp.ohlcv.15m.normalized.v1",
        input_manifest_sha256="different-input",
        builder_path="builder.py",
        builder_sha256="demo2",
        stats=stats_v2,
    ).to_dict()
    second = publish_staging_dataset(
        staging_root=staging_v2,
        published_root=published_v2,
        manifest=manifest_v2,
    )
    assert second["status"] == "published"
    assert published.exists()
    interrupted = layout.derived_staging_dir / "binance_perp_1h_from_15m_v1"
    interrupted.mkdir(parents=True)
    (interrupted / "half.parquet").write_text("partial", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        publish_staging_dataset(
            staging_root=interrupted,
            published_root=published,
            manifest={**manifest, "content_fingerprint": "other"},
        )
    assert (published / DATASET_MANIFEST_FILENAME).exists()


def test_inspect_is_not_trusted_and_canonical_1d_uses_derived_id(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.derived_datasets_dir / "binance_perp_1d_from_15m_v1"
    root.mkdir(parents=True)
    frame = _bars(start="2026-07-01T00:00:00Z", periods=3, timeframe="1d")
    frame.to_parquet(root / "d.parquet", index=False)
    _seal_derived(root, BINANCE_PERP_1D_FROM_15M_V1)
    preview = inspect_dataset(
        BINANCE_PERP_1D_FROM_15M_V1,
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
    )
    assert preview.trusted is False
    loaded = load_canonical_binance_perp_1d(
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        require_contiguous=False,
        max_materialize_rows=0,
    )
    assert loaded.record.dataset_id == BINANCE_PERP_1D_FROM_15M_V1
    assert loaded.audit["quality_status"] == "PASS"


def test_full_market_window_uses_dataset_coverage_not_query_span(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1d"
    root.mkdir(parents=True)
    rows = []
    for symbol in ("AAA/USDT:USDT", "BBB/USDT:USDT"):
        rows.append(_bars(start="2024-01-01T00:00:00Z", periods=400, symbol=symbol, timeframe="1d"))
    pd.concat(rows, ignore_index=True).to_parquet(root / "long.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="long-history",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1d",
                status=DatasetStatus.TRUSTED_BASE,
                declared_scope=DatasetScope.FULL_MARKET,
                timeframe="1d",
                passthrough=True,
                coverage_spec=FullMarketCoverageSpec(
                    min_distinct_symbols=2,
                    min_symbol_days=700,
                    min_calendar_span_days=300,
                    min_long_history_symbols=2,
                    max_short_snapshot_share=0.5,
                ),
            )
        ]
    )
    loaded = load_trusted_dataset(
        "long-history",
        layout=layout,
        requested_scope=DatasetScope.FULL_MARKET,
        start="2025-01-20T00:00:00Z",
        end="2025-01-31T00:00:00Z",
        registry=registry,
        require_contiguous=False,
        max_materialize_rows=0,
    )
    assert loaded.audit["quality_status"] == "PASS"
    assert loaded.materialized is False
    assert int(loaded.coverage["calendar_span_days"]) < 30
    assert int(loaded.verified_identity["dataset_coverage"]["calendar_span_days"]) >= 300
    assert int(loaded.verified_identity["dataset_coverage"]["long_history_symbols"]) == 2


def test_docs_example_entrypoints_exist() -> None:
    from strategy_lab.data.catalog import inspect_dataset as inspect_fn
    from strategy_lab.data.catalog import list_registered_datasets
    from strategy_lab.data.catalog import load_canonical_binance_perp_1d as load_1d
    from strategy_lab.data.catalog import load_trusted_dataset as load_fn

    assert callable(inspect_fn)
    assert callable(list_registered_datasets)
    assert callable(load_1d)
    assert callable(load_fn)
    assert inspect_fn.__name__ == "inspect_dataset"
    assert load_fn.__name__ == "load_trusted_dataset"
