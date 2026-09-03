from __future__ import annotations

from pathlib import Path
import hashlib

import pandas as pd
import pytest

from strategy_lab.data import (
    CACHE_META_FILENAME,
    DataLakeLayout,
    DatasetKind,
    DatasetRecord,
    DatasetRegistry,
    DatasetScope,
    DatasetStatus,
    LINEAGE_INCOMPLETE,
    MarketType,
    SourceUnionPolicy,
    aggregate_complete_bars,
    assert_cache_sidecar_fresh,
    build_derived_ohlcv,
    load_trusted_dataset,
    make_composite_source,
    publish_staging_dataset,
    sha256_canonical,
    write_dataframe,
)
from strategy_lab.data.catalog import BINANCE_PERP_1H_NORMALIZED_LEGACY, default_dataset_records
from strategy_lab.data.manifest import DATASET_MANIFEST_FILENAME, inventory_fingerprint, parquet_inventory, write_canonical_json
from strategy_lab.data.resample import FORMULA_VERSION, RESAMPLE_SPECS, derived_manifest


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
) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="15min", tz="UTC")
    close = [open_px + i for i in range(periods)]
    frame = pd.DataFrame(
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
    return frame


def _write_day(layout: DataLakeLayout, frame: pd.DataFrame, *, timeframe: str) -> None:
    for day, group in frame.groupby(frame["ts"].dt.date, sort=True):
        symbol = str(group["symbol"].iloc[0])
        write_dataframe(
            group.reset_index(drop=True),
            layout=layout,
            layer="normalized",
            kind=DatasetKind.OHLCV,
            exchange="binance",
            market_type=MarketType.PERP,
            symbol=symbol,
            timeframe=timeframe,
            partition_date=day,
        )


def _record(
    *,
    dataset_id: str,
    relative_root: str,
    status: DatasetStatus,
    declared_scope: DatasetScope,
    timeframe: str,
    layer: str = "normalized",
    coverage_spec=None,
    passthrough: bool = False,
    is_standard_ohlcv: bool = True,
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


def _seal_derived(root: Path, dataset_id: str, *, timeframe: str | None = None, declared_scope: str | None = None) -> None:
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
    if declared_scope is None:
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


def test_default_registry_marks_legacy_1h_partial() -> None:
    records = {item.dataset_id: item for item in default_dataset_records()}
    legacy = records[BINANCE_PERP_1H_NORMALIZED_LEGACY]
    assert legacy.status is DatasetStatus.PARTIAL_SCOPE_LEGACY
    assert legacy.declared_scope is DatasetScope.PARTIAL


def test_legacy_1h_full_market_fail_closed(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    frame = _bars(start="2026-07-01", periods=4, timeframe="1h")
    frame["ts"] = pd.date_range("2026-07-01", periods=4, freq="h", tz="UTC")
    _write_day(layout, frame, timeframe="1h")
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="legacy-1h",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
                status=DatasetStatus.PARTIAL_SCOPE_LEGACY,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="1h",
                passthrough=True,
            )
        ]
    )
    with pytest.raises(ValueError, match="cannot satisfy FULL_MARKET"):
        load_trusted_dataset(
            "legacy-1h",
            layout=layout,
            requested_scope=DatasetScope.FULL_MARKET,
            registry=registry,
        )


def test_legacy_1h_single_symbol_still_readable(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    frame = _bars(start="2026-07-01", periods=4, timeframe="1h", source=API)
    frame["ts"] = pd.date_range("2026-07-01", periods=4, freq="h", tz="UTC")
    _write_day(layout, frame, timeframe="1h")
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="legacy-1h",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
                status=DatasetStatus.PARTIAL_SCOPE_LEGACY,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="1h",
                passthrough=True,
            )
        ]
    )
    loaded = load_trusted_dataset(
        "legacy-1h",
        layout=layout,
        requested_scope=DatasetScope.SINGLE_SYMBOL,
        symbol="BTC/USDT:USDT",
        registry=registry,
        require_contiguous=False,
    )
    assert loaded.materialized
    assert len(loaded.frame) == 4
    assert loaded.manifest["dataset_id"] == "legacy-1h"
    assert loaded.source_counts[API] == 4


def test_dataset_ids_are_not_mixed_by_recursive_glob(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    a_root = layout.derived_datasets_dir / "dataset_a"
    b_root = layout.derived_datasets_dir / "dataset_b"
    a_root.mkdir(parents=True)
    b_root.mkdir(parents=True)
    left = _bars(start="2024-01-01", periods=4, symbol="AAA/USDT:USDT")
    right = _bars(start="2024-01-01", periods=4, symbol="BBB/USDT:USDT")
    left.to_parquet(a_root / "a.parquet", index=False)
    right.to_parquet(b_root / "b.parquet", index=False)
    _seal_derived(a_root, "dataset-a", timeframe="15m", declared_scope="PARTIAL")
    decoy = layout.normalized_dir / "ohlcv" / "exchange=binance" / "market_type=perp" / "timeframe=15m"
    decoy.mkdir(parents=True)
    _bars(start="2024-01-01", periods=4, symbol="DECOY/USDT:USDT").to_parquet(
        decoy / "decoy.parquet", index=False
    )
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="dataset-a",
                relative_root="derived/datasets/dataset_a",
                status=DatasetStatus.TRUSTED_DERIVED,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="15m",
                layer="derived",
            ),
            _record(
                dataset_id="dataset-b",
                relative_root="derived/datasets/dataset_b",
                status=DatasetStatus.TRUSTED_DERIVED,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="15m",
                layer="derived",
            ),
        ]
    )
    loaded = load_trusted_dataset(
        "dataset-a",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        require_contiguous=False,
    )
    assert loaded.frame["symbol"].unique().tolist() == ["AAA/USDT:USDT"]
    assert "BBB/USDT:USDT" not in set(loaded.frame["symbol"])
    assert "DECOY/USDT:USDT" not in set(loaded.frame["symbol"])


def test_duplicate_keys_and_unknown_source_fail_trusted_load(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
    root.mkdir(parents=True)
    frame = _bars(start="2024-01-01", periods=4)
    dup = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    dup.to_parquet(root / "dup.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="dup-15m",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m",
                status=DatasetStatus.TRUSTED_BASE,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="15m",
            )
        ]
    )
    with pytest.raises(ValueError, match="within-source duplicate"):
        load_trusted_dataset(
            "dup-15m",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
        )

    unknown_root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m-unknown"
    unknown_root.mkdir(parents=True)
    unknown = _bars(start="2024-01-01", periods=4, source="not_a_real_source")
    unknown.to_parquet(unknown_root / "u.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="unknown-15m",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m-unknown",
                status=DatasetStatus.TRUSTED_BASE,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="15m",
                passthrough=True,
            )
        ]
    )
    with pytest.raises(ValueError, match="unverified source"):
        load_trusted_dataset(
            "unknown-15m",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
        )


def test_full_market_coverage_uses_history_not_just_symbol_count(tmp_path: Path) -> None:
    from strategy_lab.data.catalog import FullMarketCoverageSpec

    layout = _layout(tmp_path)
    root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
    root.mkdir(parents=True)
    rows = []
    for index, symbol in enumerate(["AAA/USDT:USDT", "BBB/USDT:USDT"]):
        part = _bars(start="2026-07-01", periods=4, symbol=symbol, timeframe="1h", source=API)
        part["ts"] = pd.date_range("2026-07-01", periods=4, freq="h", tz="UTC")
        rows.append(part)
    pd.concat(rows, ignore_index=True).to_parquet(root / "short.parquet", index=False)
    _seal_derived(root, "short-history", timeframe="1h", declared_scope="FULL_MARKET")
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="short-history",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
                status=DatasetStatus.TRUSTED_DERIVED,
                declared_scope=DatasetScope.FULL_MARKET,
                timeframe="1h",
                layer="derived",
                passthrough=True,
                coverage_spec=FullMarketCoverageSpec(
                    min_distinct_symbols=2,
                    min_symbol_days=1,
                    min_calendar_span_days=1,
                    min_long_history_symbols=2,
                    long_history_days=365,
                    max_short_snapshot_share=0.1,
                    short_snapshot_days=60,
                ),
            )
        ]
    )
    with pytest.raises(ValueError, match="FULL_MARKET coverage"):
        load_trusted_dataset(
            "short-history",
            layout=layout,
            requested_scope=DatasetScope.FULL_MARKET,
            registry=registry,
            purpose="governance_audit",
        )


def test_resample_requires_exact_component_counts_and_utc_phase() -> None:
    complete_hour = _bars(start="2024-01-01T00:00:00Z", periods=4)
    complete_hour.loc[0, "open"] = 10.0
    complete_hour.loc[0, "low"] = 9.0
    complete_hour.loc[1, "high"] = 200.0
    complete_hour.loc[2, "low"] = 1.0
    complete_hour.loc[3, "close"] = 40.0
    complete_hour.loc[3, "high"] = 103.0
    complete_hour.loc[3, "low"] = 39.0
    complete_hour["volume"] = [10.0, 0.0, 20.0, 20.0]
    complete_hour["quote_volume"] = [100.0, 0.0, 400.0, 800.0]
    complete_hour["trade_count"] = [1, 2, 3, 4]
    hourly, stats = aggregate_complete_bars(complete_hour, "1h")
    assert stats["required_component_count"] == 4
    assert len(hourly) == 1
    assert hourly.iloc[0]["ts"] == pd.Timestamp("2024-01-01T00:00:00Z")
    assert hourly.iloc[0]["open"] == 10.0
    assert hourly.iloc[0]["high"] == 200.0
    assert hourly.iloc[0]["low"] == 1.0
    assert hourly.iloc[0]["close"] == 40.0
    assert hourly.iloc[0]["volume"] == 50.0
    assert hourly.iloc[0]["quote_volume"] == 1300.0
    assert hourly.iloc[0]["trade_count"] == 10
    assert hourly.iloc[0]["vwap"] == pytest.approx(1300.0 / 50.0)
    assert bool(hourly.iloc[0]["is_closed"]) is True
    assert hourly.iloc[0]["aggregation_formula_version"] == FORMULA_VERSION

    missing = complete_hour.drop(index=1).reset_index(drop=True)
    hourly_missing, missing_stats = aggregate_complete_bars(missing, "1h")
    assert hourly_missing.empty
    assert missing_stats["excluded_incomplete_buckets"] == 1

    unclosed = complete_hour.copy()
    unclosed.loc[2, "is_closed"] = False
    hourly_open, open_stats = aggregate_complete_bars(unclosed, "1h")
    assert hourly_open.empty
    assert open_stats["excluded_incomplete_buckets"] == 1

    off_grid = _bars(start="2024-01-01T00:05:00Z", periods=4)
    hourly_phase, phase_stats = aggregate_complete_bars(off_grid, "1h")
    assert hourly_phase.empty
    assert phase_stats["candidate_buckets"] == 0

    shifted = _bars(start="2024-01-01T00:15:00Z", periods=4)
    hourly_shift, shift_stats = aggregate_complete_bars(shifted, "1h")
    assert hourly_shift.empty
    assert shift_stats["excluded_incomplete_buckets"] >= 1

    four_hours = _bars(start="2024-01-01T00:00:00Z", periods=16)
    h4, h4_stats = aggregate_complete_bars(four_hours, "4h")
    assert RESAMPLE_SPECS["4h"]["component_count"] == 16
    assert len(h4) == 1
    assert h4.iloc[0]["ts"] == pd.Timestamp("2024-01-01T00:00:00Z")
    assert h4_stats["excluded_incomplete_buckets"] == 0

    day = _bars(start="2024-01-01T00:00:00Z", periods=96)
    daily, daily_stats = aggregate_complete_bars(day, "1d")
    assert len(daily) == 1
    assert daily.iloc[0]["ts"] == pd.Timestamp("2024-01-01T00:00:00Z")
    assert daily.iloc[0]["component_count"] == 96
    assert daily_stats["excluded_incomplete_buckets"] == 0


def test_mixed_source_uses_composite_label() -> None:
    vision = _bars(start="2024-01-01T00:00:00Z", periods=2, source=VISION)
    api = _bars(start="2024-01-01T00:30:00Z", periods=2, source=API)
    mixed = pd.concat([vision, api], ignore_index=True)
    hourly, _stats = aggregate_complete_bars(mixed, "1h")
    assert len(hourly) == 1
    assert hourly.iloc[0]["source"] == make_composite_source((API, VISION))
    assert hourly.iloc[0]["source"].startswith("composite:")
    assert VISION in hourly.iloc[0]["source"]
    assert API in hourly.iloc[0]["source"]
    single = _bars(start="2024-01-01T00:00:00Z", periods=4, source=VISION)
    hourly_single, _ = aggregate_complete_bars(single, "1h")
    assert hourly_single.iloc[0]["source"] == VISION


def test_zero_volume_vwap_uses_output_close() -> None:
    frame = _bars(start="2024-01-01T00:00:00Z", periods=4)
    frame["volume"] = 0.0
    frame["quote_volume"] = 0.0
    hourly, _ = aggregate_complete_bars(frame, "1h")
    assert hourly.iloc[0]["vwap"] == hourly.iloc[0]["close"]


def test_duplicate_input_keys_fail_union() -> None:
    frame = _bars(start="2024-01-01T00:00:00Z", periods=4)
    dup = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="within-source duplicate"):
        aggregate_complete_bars(dup, "1h")


def test_manifest_fingerprint_is_stable() -> None:
    first = derived_manifest(
        dataset_id="demo",
        status="TRUSTED_DERIVED",
        timeframe="1h",
        physical_root="/tmp/a",
        input_dataset_id="input",
        input_manifest_sha256="abc",
        builder_path="builder.py",
        builder_sha256="def",
        stats={"output_rows": 10, "distinct_keys": 10, "symbols": 2, "file_count": 1, "bytes": 8},
    )
    second = derived_manifest(
        dataset_id="demo",
        status="TRUSTED_DERIVED",
        timeframe="1h",
        physical_root="/tmp/a",
        input_dataset_id="input",
        input_manifest_sha256="abc",
        builder_path="builder.py",
        builder_sha256="def",
        stats={"output_rows": 10, "distinct_keys": 10, "symbols": 2, "file_count": 1, "bytes": 8},
    )
    assert first.content_fingerprint == second.content_fingerprint
    assert first.content_fingerprint == sha256_canonical(first.stable_payload())
    assert first.generated_at != "" and second.generated_at != ""


def test_cache_sidecar_stale_and_mismatch_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "cache" / "panel"
    root.mkdir(parents=True)
    frame = _bars(start="2024-01-01", periods=4)
    parquet_path = root / "panel.parquet"
    frame.to_parquet(parquet_path, index=False)
    inventory = parquet_inventory(root)
    input_hash = hashlib.sha256(b"input-hash").hexdigest()
    meta = {
        "schema_version": "1.0",
        "cache_id": "demo",
        "cache_version": "v1",
        "physical_root": str(root),
        "input_dataset_id": "binance.perp.ohlcv.15m.normalized.v1",
        "input_manifest_sha256": input_hash,
        "builder_path": "builder.py",
        "builder_sha256": hashlib.sha256(b"builder").hexdigest(),
        "config_parameter_sha256": hashlib.sha256(b"config").hexdigest(),
        "generated_at": "2026-09-03T00:00:00+00:00",
        "cutoff_exclusive_utc": "2026-08-25T00:00:00+00:00",
        "rows": 4,
        "distinct_keys": 4,
        "symbols": 1,
        "start_utc": "2024-01-01T00:00:00+00:00",
        "end_utc": "2024-01-01T01:00:00+00:00",
        "duplicate_overlap_resolution": "none",
        "completeness_rules": "none",
        "null_fill_policy": "none",
        "rebuild_command": "rebuild",
        "quality_status": "OK",
        "parquet_inventory_fingerprint": inventory_fingerprint(inventory),
    }
    write_canonical_json(root / CACHE_META_FILENAME, meta)
    assert_cache_sidecar_fresh(root, expected_input_manifest_sha256=input_hash)
    frame.iloc[0, frame.columns.get_loc("close")] = 999.0
    frame.to_parquet(parquet_path, index=False)
    with pytest.raises(ValueError, match="does not match sidecar"):
        assert_cache_sidecar_fresh(root)
    _bars(start="2024-01-01", periods=4).to_parquet(parquet_path, index=False)
    inventory = parquet_inventory(root)
    meta["parquet_inventory_fingerprint"] = inventory_fingerprint(inventory)
    meta["quality_status"] = "STALE"
    write_canonical_json(root / CACHE_META_FILENAME, meta)
    with pytest.raises(ValueError, match="quality_status=STALE"):
        assert_cache_sidecar_fresh(root)
    meta["quality_status"] = "OK"
    meta["input_manifest_sha256"] = LINEAGE_INCOMPLETE
    write_canonical_json(root / CACHE_META_FILENAME, meta)
    with pytest.raises(ValueError, match="incomplete"):
        assert_cache_sidecar_fresh(root)
    with pytest.raises(ValueError, match="incomplete"):
        assert_cache_sidecar_fresh(root, expected_input_manifest_sha256=input_hash)


def test_staging_atomic_publish_and_no_overwrite(tmp_path: Path) -> None:
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
    assert stats["output_rows"] == 1
    manifest = derived_manifest(
        dataset_id="binance.perp.ohlcv.1h.from_15m.v1",
        status="TRUSTED_DERIVED",
        timeframe="1h",
        physical_root=str(published),
        input_dataset_id="binance.perp.ohlcv.15m.normalized.v1",
        input_manifest_sha256="demo",
        builder_path="builder.py",
        builder_sha256="demo",
        stats=stats,
    ).to_dict()
    result = publish_staging_dataset(
        staging_root=staging,
        published_root=published,
        manifest=manifest,
    )
    assert result["status"] == "published"
    assert not staging.exists()
    assert (published / "_MANIFEST.json").exists()
    staging_again = layout.derived_staging_dir / "retry"
    staging_again.mkdir(parents=True)
    (staging_again / "dummy.txt").write_text("no", encoding="utf-8")
    different = dict(manifest)
    different["rows"] = 999
    different["content_fingerprint"] = "different"
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        publish_staging_dataset(
            staging_root=staging_again,
            published_root=published,
            manifest=different,
        )


def test_derived_passthrough_keeps_composite_source(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.derived_datasets_dir / "binance_perp_4h_from_15m_v1"
    root.mkdir(parents=True)
    frame = _bars(start="2024-01-01T00:00:00Z", periods=1, timeframe="4h")
    frame["source"] = make_composite_source((VISION, API))
    frame.to_parquet(root / "mixed.parquet", index=False)
    _seal_derived(root, "binance.perp.ohlcv.4h.from_15m.v1")
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="binance.perp.ohlcv.4h.from_15m.v1",
                relative_root="derived/datasets/binance_perp_4h_from_15m_v1",
                status=DatasetStatus.TRUSTED_DERIVED,
                    declared_scope=DatasetScope.FULL_MARKET,
                    timeframe="4h",
                    layer="derived",
                    passthrough=True,
            )
        ]
    )
    loaded = load_trusted_dataset(
        "binance.perp.ohlcv.4h.from_15m.v1",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        require_contiguous=False,
    )
    assert len(loaded.frame) == 1
    assert str(loaded.frame.iloc[0]["source"]).startswith("composite:")


def test_warehouse_rejects_derived_layer_glob(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    from strategy_lab.data.warehouse import DuckDBWarehouse

    warehouse = DuckDBWarehouse(layout=layout)
    with pytest.raises(ValueError, match="must be loaded by dataset_id"):
        warehouse.load_dataset(layer="derived", kind=DatasetKind.OHLCV)


def test_missing_dataset_root_does_not_fall_back(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="missing",
                relative_root="derived/datasets/does-not-exist",
                status=DatasetStatus.TRUSTED_DERIVED,
                declared_scope=DatasetScope.PARTIAL,
                timeframe="1h",
                layer="derived",
            )
        ]
    )
    with pytest.raises(FileNotFoundError, match="will not fall back"):
        load_trusted_dataset(
            "missing",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
        )
