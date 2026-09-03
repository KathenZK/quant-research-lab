from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os

import pandas as pd
import pytest

from strategy_lab.data import (
    DataLakeLayout,
    DatasetKind,
    DatasetRecord,
    DatasetRegistry,
    DatasetScope,
    DatasetStatus,
    MarketType,
    SourceUnionPolicy,
    build_derived_ohlcv,
    load_trusted_dataset,
    publish_staging_dataset,
    register_derived_dataset,
    verify_existing_derived_publish,
)
from strategy_lab.data.catalog import (
    load_trusted_research_dataset,
    read_verified_ohlcv,
)
from strategy_lab.data.manifest import (
    CACHE_META_FILENAME,
    DATASET_MANIFEST_FILENAME,
    FingerprintMode,
    assert_cache_sidecar_fresh,
    assert_published_derived_manifest,
    assert_safe_dataset_version,
    inventory_fingerprint,
    parquet_inventory,
    resolve_parquet_inventory_fingerprint,
    write_canonical_json,
)
from strategy_lab.data.resample import FORMULA_VERSION, derived_manifest
from strategy_lab.data.windows import holding_window_has_gap, lookback_crosses_gap

VISION = "binance_vision_kline_monthly"


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
    exchange: str = "binance",
    market_type: str = "perp",
) -> pd.DataFrame:
    resolved_freq = freq or {"15m": "15min", "1h": "h", "4h": "4h", "1d": "D"}[timeframe]
    index = pd.date_range(start, periods=periods, freq=resolved_freq, tz="UTC")
    close = [open_px + i for i in range(periods)]
    return pd.DataFrame(
        {
            "ts": index,
            "exchange": [exchange] * periods,
            "symbol": [symbol] * periods,
            "market_type": [market_type] * periods,
            "timeframe": [timeframe] * periods,
            "open": close,
            "high": [value + 1.0 for value in close],
            "low": [value - 1.0 for value in close],
            "close": close,
            "volume": [10.0] * periods,
            "quote_volume": [float(value) * 10.0 for value in close],
            "trade_count": [1.0] * periods,
            "vwap": close,
            "is_closed": [closed] * periods,
            "source": [source] * periods,
        }
    )


def _record(**kwargs) -> DatasetRecord:
    timeframe = kwargs.get("timeframe", "1h")
    return DatasetRecord(
        dataset_id=kwargs["dataset_id"],
        layer=kwargs.get("layer", "normalized"),
        kind=DatasetKind.OHLCV,
        status=kwargs.get("status", DatasetStatus.TRUSTED_BASE),
        declared_scope=kwargs.get("declared_scope", DatasetScope.PARTIAL),
        exchange=kwargs.get("exchange", "binance"),
        market_type=kwargs.get("market_type", MarketType.PERP),
        timeframe=timeframe,
        relative_root=kwargs["relative_root"],
        source_adjudication="test",
        priority_union_version="test-union",
        rebuildable=True,
        is_standard_ohlcv=True,
        source_union=SourceUnionPolicy(
            version="test-union",
            priority=(),
            reject_unlisted=False,
            passthrough=True,
        ),
    )


def _seal_derived(root: Path, dataset_id: str, *, timeframe: str = "1h") -> None:
    inventory = parquet_inventory(root)
    input_hash = hashlib.sha256(b"r3-input").hexdigest()
    cutoff = "2026-08-25T00:00:00+00:00"
    declared_scope = "PARTIAL"
    stats = {
        "file_count": len(inventory),
        "bytes": int(sum(int(row["size"]) for row in inventory)),
        "output_rows": int(sum(1 for _ in root.rglob("*.parquet"))),
        "distinct_keys": 1,
        "symbols": 1,
        "start_utc": "2026-07-01T00:00:00+00:00",
        "end_utc": "2026-07-01T00:00:00+00:00",
        "parquet_inventory_fingerprint": inventory_fingerprint(inventory),
        "cutoff_exclusive_utc": cutoff,
        "rebuild_command": (
            "python research/platform/data-lake-governance/scripts/"
            f"build_binance_derived_ohlcv_from_15m.py --timeframe {timeframe} "
            f"--dataset-version v2 --cutoff-exclusive-utc {cutoff} "
            f"--input-snapshot-fingerprint {input_hash}"
        ),
        "aggregation_impl_sha256": hashlib.sha256(b"r3-impl").hexdigest(),
        "input_parquet_inventory_fingerprint": input_hash,
        "excluded_incomplete_buckets": 0,
        "mixed_source_rows": 0,
        "source_counts": {},
    }
    derived_manifest(
        dataset_id=dataset_id,
        status="TRUSTED_DERIVED",
        timeframe=timeframe,
        physical_root=str(root.resolve()),
        input_dataset_id="binance.perp.ohlcv.15m.normalized.v1",
        input_manifest_sha256=input_hash,
        builder_path="research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py",
        builder_sha256=hashlib.sha256(b"r3-builder").hexdigest(),
        stats=stats,
        declared_scope=declared_scope,
    ).write(root / DATASET_MANIFEST_FILENAME)


def test_r3_01_cutoff_applies_to_output_bars_and_unaligned_consumer(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    input_root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
    input_root.mkdir(parents=True)
    _bars(start="2026-07-01T00:00:00Z", periods=16).to_parquet(input_root / "in.parquet", index=False)
    staging = layout.derived_staging_dir / "binance_perp_1h_from_15m_v2"
    stats = build_derived_ohlcv(
        input_files=[input_root / "in.parquet"],
        output_timeframe="1h",
        staging_root=staging,
        end=pd.Timestamp("2026-07-01T01:00:00Z"),
    )
    assert stats["end_utc"].startswith("2026-07-01T00:00:00")
    assert stats["output_rows"] == 1
    assert stats["cutoff_exclusive_utc"] == "2026-07-01T01:00:00+00:00"

    staging_u = layout.derived_staging_dir / "binance_perp_1h_from_15m_v2u"
    unaligned = build_derived_ohlcv(
        input_files=[input_root / "in.parquet"],
        output_timeframe="1h",
        staging_root=staging_u,
        end=pd.Timestamp("2026-07-01T01:30:00Z"),
    )
    assert unaligned["output_rows"] == 1
    assert pd.Timestamp(unaligned["end_utc"]) + pd.Timedelta(hours=1) <= pd.Timestamp("2026-07-01T01:30:00Z")

    published = layout.derived_datasets_dir / "binance_perp_1h_from_15m_v2"
    input_hash = inventory_fingerprint(parquet_inventory(input_root))
    stats["input_parquet_inventory_fingerprint"] = input_hash
    stats["rebuild_command"] = (
        "python build.py --timeframe 1h --dataset-version v2 "
        "--cutoff-exclusive-utc 2026-07-01T01:00:00+00:00 "
        f"--input-snapshot-fingerprint {input_hash}"
    )
    manifest = derived_manifest(
        dataset_id="binance.perp.ohlcv.1h.from_15m.v2",
        status="TRUSTED_DERIVED",
        timeframe="1h",
        physical_root=str(published),
        input_dataset_id="binance.perp.ohlcv.15m.normalized.v1",
        input_manifest_sha256=input_hash,
        builder_path="research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py",
        builder_sha256=hashlib.sha256(b"builder").hexdigest(),
        stats=stats,
    )
    publish_staging_dataset(staging_root=staging, published_root=published, manifest=manifest.to_dict())
    same = verify_existing_derived_publish(
        published_root=published,
        dataset_id="binance.perp.ohlcv.1h.from_15m.v2",
        input_fingerprint=input_hash,
        formula_version=FORMULA_VERSION,
        cutoff_exclusive_utc="2026-07-01T01:00:00+00:00",
    )
    assert same["status"] == "already_published"
    with pytest.raises(FileExistsError, match="cutoff"):
        verify_existing_derived_publish(
            published_root=published,
            dataset_id="binance.perp.ohlcv.1h.from_15m.v2",
            input_fingerprint=input_hash,
            formula_version=FORMULA_VERSION,
            cutoff_exclusive_utc="2026-07-01T02:00:00+00:00",
        )

    root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
    root.mkdir(parents=True)
    _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h").to_parquet(root / "h.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="cutoff-1h",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
                timeframe="1h",
            )
        ]
    )
    loaded = load_trusted_dataset(
        "cutoff-1h",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        end="2026-07-01T01:30:00Z",
        require_contiguous=False,
    )
    assert list(loaded.frame["ts"]) == [pd.Timestamp("2026-07-01T00:00:00Z")]
    verified = read_verified_ohlcv(loaded, end="2026-07-01T01:30:00Z")
    assert list(verified["ts"]) == [pd.Timestamp("2026-07-01T00:00:00Z")]
    with pytest.raises(ValueError, match="REQUEST_WINDOW_EXCEEDS_AVAILABLE|exceeds available"):
        load_trusted_dataset(
            "cutoff-1h",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            end="2026-09-03T00:00:00Z",
            require_contiguous=False,
        )


def test_r3_02_manifest_identity_and_complete_fixture_required(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.derived_datasets_dir / "demo_1h"
    root.mkdir(parents=True)
    _bars(start="2026-07-01T00:00:00Z", periods=2, timeframe="1h").to_parquet(root / "a.parquet", index=False)
    _seal_derived(root, "demo-1h", timeframe="1h")
    verified = assert_published_derived_manifest(
        dataset_id="demo-1h",
        root=root,
        exchange="binance",
        market_type="perp",
        timeframe="1h",
        declared_scope="PARTIAL",
        layer="derived",
        status="TRUSTED_DERIVED",
        input_dataset_id="binance.perp.ohlcv.15m.normalized.v1",
        expected_manifest_identity={
            "content_fingerprint": json.loads((root / DATASET_MANIFEST_FILENAME).read_text())[
                "content_fingerprint"
            ]
        },
    )
    assert verified["manifest_file_sha256"] != verified["content_fingerprint"]
    payload = json.loads((root / DATASET_MANIFEST_FILENAME).read_text(encoding="utf-8"))
    payload["exchange"] = "kraken"
    payload["market_type"] = "spot"
    payload["timeframe"] = "1d"
    write_canonical_json(root / DATASET_MANIFEST_FILENAME, payload)
    with pytest.raises(ValueError, match="content fingerprint mismatch|identity"):
        assert_published_derived_manifest(
            dataset_id="demo-1h",
            root=root,
            exchange="binance",
            market_type="perp",
            timeframe="1h",
        )


def test_r3_03_sql_audit_rejects_bad_schema_and_identity(tmp_path: Path) -> None:
    layout = _layout(tmp_path)

    def _load(root: Path, dataset_id: str, timeframe: str = "1h") -> None:
        registry = DatasetRegistry(
            [
                _record(
                    dataset_id=dataset_id,
                    relative_root=str(root.relative_to(layout.root_dir)),
                    timeframe=timeframe,
                )
            ]
        )
        load_trusted_dataset(
            dataset_id,
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
            max_materialize_rows=0,
        )

    kraken = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-kraken"
    kraken.mkdir(parents=True)
    _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h", exchange="okx").to_parquet(
        kraken / "x.parquet", index=False
    )
    with pytest.raises(ValueError, match="not trusted"):
        _load(kraken, "bad-ex")

    spot = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-spot"
    spot.mkdir(parents=True)
    _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h", market_type="spot").to_parquet(
        spot / "x.parquet", index=False
    )
    with pytest.raises(ValueError, match="not trusted"):
        _load(spot, "bad-mkt")

    closed = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-str"
    closed.mkdir(parents=True)
    frame = _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h")
    frame["is_closed"] = "true"
    frame.to_parquet(closed / "x.parquet", index=False)
    with pytest.raises(ValueError, match="not trusted|schema"):
        _load(closed, "bad-closed")

    naive = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-naive"
    naive.mkdir(parents=True)
    frame = _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h")
    frame["ts"] = pd.DatetimeIndex(frame["ts"].dt.tz_localize(None))
    frame.to_parquet(naive / "x.parquet", index=False)
    with pytest.raises(ValueError, match="not trusted|schema"):
        _load(naive, "bad-naive")

    inf = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-inf"
    inf.mkdir(parents=True)
    frame = _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h")
    frame.loc[0, "trade_count"] = float("inf")
    frame.to_parquet(inf / "x.parquet", index=False)
    with pytest.raises(ValueError, match="not trusted"):
        _load(inf, "bad-inf")

    mixed = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-mix"
    mixed.mkdir(parents=True)
    _bars(start="2026-07-01T00:00:00Z", periods=2, timeframe="1h").to_parquet(mixed / "a.parquet", index=False)
    other = _bars(start="2026-07-01T02:00:00Z", periods=2, timeframe="1h")
    other["is_closed"] = "true"
    other.to_parquet(mixed / "b.parquet", index=False)
    with pytest.raises(ValueError, match="not trusted|schema"):
        _load(mixed, "bad-mix")

    sub = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-sub"
    sub.mkdir(parents=True)
    frame = _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h")
    frame.loc[1, "ts"] = pd.Timestamp("2026-07-01T01:00:00.500Z")
    frame.to_parquet(sub / "x.parquet", index=False)
    with pytest.raises(ValueError, match="not trusted"):
        _load(sub, "bad-sub")

    mixed_numeric = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-num"
    mixed_numeric.mkdir(parents=True)
    bigint = _bars(start="2026-07-01T00:00:00Z", periods=2, timeframe="1h")
    bigint["trade_count"] = bigint["trade_count"].astype("int64")
    bigint.to_parquet(mixed_numeric / "bigint.parquet", index=False)
    double = _bars(start="2026-07-01T02:00:00Z", periods=2, timeframe="1h")
    double["trade_count"] = double["trade_count"].astype("float64")
    double.to_parquet(mixed_numeric / "double.parquet", index=False)
    _load(mixed_numeric, "ok-numeric")


def test_r3_04_strict_hash_detects_same_size_mtime_rewrite(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
    root.mkdir(parents=True)
    path = root / "p.parquet"
    frame = _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h")
    frame.to_parquet(path, index=False)
    original_mtime = path.stat().st_mtime_ns
    original_size = path.stat().st_size
    first = resolve_parquet_inventory_fingerprint(root, mode=FingerprintMode.STRICT_CONTENT)
    cached = resolve_parquet_inventory_fingerprint(
        root,
        cache_dir=layout.cache_dir / "fp",
        mode=FingerprintMode.FAST_METADATA,
    )
    assert cached == first
    raw = bytearray(path.read_bytes())
    raw[min(64, len(raw) - 1)] ^= 0x01
    path.write_bytes(bytes(raw))
    os.utime(path, ns=(original_mtime, original_mtime))
    assert path.stat().st_size == original_size
    assert path.stat().st_mtime_ns == original_mtime
    stale_fast = resolve_parquet_inventory_fingerprint(
        root,
        cache_dir=layout.cache_dir / "fp",
        mode=FingerprintMode.FAST_METADATA,
    )
    strict = resolve_parquet_inventory_fingerprint(root, mode=FingerprintMode.STRICT_CONTENT)
    assert stale_fast == first
    assert strict != first
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="hash-1h",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
                timeframe="1h",
            )
        ]
    )
    with pytest.raises(ValueError):
        load_trusted_dataset(
            "hash-1h",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
            expected_parquet_fingerprint=first,
        )


def test_r3_05_cache_missing_fields_and_registry_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "cache" / "panel"
    root.mkdir(parents=True)
    _bars(start="2026-07-01T00:00:00Z", periods=2).to_parquet(root / "p.parquet", index=False)
    inventory = parquet_inventory(root)
    write_canonical_json(
        root / CACHE_META_FILENAME,
        {
            "quality_status": "OK",
            "parquet_inventory_fingerprint": inventory_fingerprint(inventory),
        },
    )
    with pytest.raises(ValueError, match="incomplete|missing"):
        assert_cache_sidecar_fresh(root)
    restricted = assert_cache_sidecar_fresh(root, allow_incomplete_lineage=True)
    assert restricted["trusted_for_new_research"] is False

    layout = _layout(tmp_path)
    published = layout.derived_datasets_dir / "binance_perp_1h_from_15m_v2"
    published.mkdir(parents=True)
    _bars(start="2026-07-01T00:00:00Z", periods=2, timeframe="1h").to_parquet(published / "x.parquet", index=False)
    _seal_derived(published, "binance.perp.ohlcv.1h.from_15m.v2", timeframe="1h")
    record = _record(
        dataset_id="binance.perp.ohlcv.1h.from_15m.v2",
        relative_root="derived/datasets/binance_perp_1h_from_15m_v2",
        status=DatasetStatus.TRUSTED_DERIVED,
        declared_scope=DatasetScope.PARTIAL,
        timeframe="1h",
        layer="derived",
    )
    register_derived_dataset(layout, record)
    restarted = DatasetRegistry.from_layout(layout)
    assert "binance.perp.ohlcv.1h.from_15m.v2" in {item.dataset_id for item in restarted.records()}
    loaded = load_trusted_dataset(
        "binance.perp.ohlcv.1h.from_15m.v2",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=restarted,
        require_contiguous=False,
        end="2026-07-01T02:00:00Z",
    )
    assert loaded.audit["quality_status"] == "PASS"
    with pytest.raises(ValueError):
        assert_safe_dataset_version("../v2")


def test_r3_06_gap_policy_and_ma7_window(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=4h"
    root.mkdir(parents=True)
    left = _bars(start="2026-07-01T00:00:00Z", periods=3, timeframe="4h")
    right = _bars(start="2026-07-02T00:00:00Z", periods=3, timeframe="4h", open_px=200.0)
    pd.concat([left, right], ignore_index=True).to_parquet(root / "g.parquet", index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="gap-4h",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=4h",
                timeframe="4h",
            )
        ]
    )
    reported = load_trusted_dataset(
        "gap-4h",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        require_contiguous=False,
        gap_policy="report_only",
        end="2026-07-02T12:00:00Z",
    )
    assert reported.audit["quality_status"] == "PASS"
    assert int(reported.audit["internal_missing_bars"]) > 0
    with pytest.raises(ValueError, match="not trusted"):
        load_trusted_research_dataset(
            "gap-4h",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            end="2026-07-02T12:00:00Z",
            gap_policy="reject",
        )
    segments = load_trusted_research_dataset(
        "gap-4h",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        end="2026-07-02T12:00:00Z",
        gap_policy="contiguous_segments",
    )
    assert segments.audit["research_window_fitness"] == "SEGMENTS_ONLY"
    ts = pd.concat([left["ts"], right["ts"]], ignore_index=True)
    assert lookback_crosses_gap(ts, timeframe="4h", lookback=7)
    assert holding_window_has_gap(
        ts,
        timeframe="4h",
        start=pd.Timestamp("2026-07-01T08:00:00Z"),
        horizon_bars=3,
    )


def test_r3_03_missing_column_nan_and_unclosed(tmp_path: Path) -> None:
    layout = _layout(tmp_path)

    def _load(root: Path, dataset_id: str) -> None:
        registry = DatasetRegistry(
            [
                _record(
                    dataset_id=dataset_id,
                    relative_root=str(root.relative_to(layout.root_dir)),
                    timeframe="1h",
                )
            ]
        )
        load_trusted_dataset(
            dataset_id,
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
            max_materialize_rows=0,
        )

    missing = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-miss"
    missing.mkdir(parents=True)
    frame = _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h").drop(columns=["vwap"])
    frame.to_parquet(missing / "x.parquet", index=False)
    with pytest.raises(ValueError, match="not trusted|schema"):
        _load(missing, "bad-missing")

    nan = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-nan"
    nan.mkdir(parents=True)
    frame = _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h")
    frame.loc[0, "close"] = float("nan")
    frame.to_parquet(nan / "x.parquet", index=False)
    with pytest.raises(ValueError, match="not trusted"):
        _load(nan, "bad-nan")

    opened = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h-open"
    opened.mkdir(parents=True)
    frame = _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h", closed=False)
    frame.to_parquet(opened / "x.parquet", index=False)
    with pytest.raises(ValueError, match="not trusted"):
        _load(opened, "bad-open")


def test_r3_04_cache_corruption_file_add_and_mid_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout = _layout(tmp_path)
    root = layout.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h"
    root.mkdir(parents=True)
    path = root / "p.parquet"
    _bars(start="2026-07-01T00:00:00Z", periods=4, timeframe="1h").to_parquet(path, index=False)
    registry = DatasetRegistry(
        [
            _record(
                dataset_id="hash-1h",
                relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
                timeframe="1h",
            )
        ]
    )
    first = load_trusted_dataset(
        "hash-1h",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        require_contiguous=False,
        max_materialize_rows=0,
    )
    assert first.audit["quality_status"] == "PASS"
    cache_dir = layout.cache_dir / "_dataset_quality_audits"
    cache_files = list(cache_dir.glob("*.json"))
    assert cache_files
    for item in cache_files:
        item.write_text("{not-json", encoding="utf-8")
    second = load_trusted_dataset(
        "hash-1h",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        require_contiguous=False,
        max_materialize_rows=0,
    )
    assert second.audit["quality_status"] == "PASS"
    for item in cache_dir.glob("*.json"):
        if item.name.startswith("coverage-"):
            continue
        payload = json.loads(item.read_text(encoding="utf-8"))
        if not isinstance(payload.get("audit"), dict):
            continue
        payload["audit"] = {**payload["audit"], "quality_status": "PASS", "rows": 0}
        item.write_text(json.dumps(payload), encoding="utf-8")
    third = load_trusted_dataset(
        "hash-1h",
        layout=layout,
        requested_scope=DatasetScope.PARTIAL,
        registry=registry,
        require_contiguous=False,
        max_materialize_rows=0,
    )
    assert third.audit["rows"] == 4
    extra = root / "extra.parquet"
    _bars(start="2026-07-01T04:00:00Z", periods=1, timeframe="1h").to_parquet(extra, index=False)
    with pytest.raises(ValueError, match="fingerprint"):
        load_trusted_dataset(
            "hash-1h",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
            expected_parquet_fingerprint=first.manifest["parquet_inventory_fingerprint"],
        )
    extra.unlink()
    from strategy_lab.data import catalog as catalog_mod

    real_audit = catalog_mod._sql_audit_for_record
    calls = {"n": 0}

    def _mutating_audit(*args, **kwargs):
        calls["n"] += 1
        raw = bytearray(path.read_bytes())
        raw[min(32, len(raw) - 1)] ^= 0x01
        path.write_bytes(bytes(raw))
        return real_audit(*args, **kwargs)

    monkeypatch.setattr(catalog_mod, "_sql_audit_for_record", _mutating_audit)
    with pytest.raises(ValueError, match="fingerprint|input changed"):
        load_trusted_dataset(
            "hash-1h",
            layout=layout,
            requested_scope=DatasetScope.PARTIAL,
            registry=registry,
            require_contiguous=False,
            max_materialize_rows=0,
        )
    assert calls["n"] == 1


def test_r3_05_unknown_cache_quality_and_empty_lineage(tmp_path: Path) -> None:
    root = tmp_path / "cache" / "panel"
    root.mkdir(parents=True)
    _bars(start="2026-07-01T00:00:00Z", periods=2).to_parquet(root / "p.parquet", index=False)
    inventory = parquet_inventory(root)
    fingerprint = inventory_fingerprint(inventory)
    write_canonical_json(
        root / CACHE_META_FILENAME,
        {
            "schema_version": "1.0",
            "cache_id": "panel",
            "cache_version": "v1",
            "physical_root": str(root),
            "input_dataset_id": "binance.perp.ohlcv.15m.normalized.v1",
            "input_manifest_sha256": "a" * 64,
            "builder_path": "builder.py",
            "builder_sha256": "b" * 64,
            "config_parameter_sha256": "c" * 64,
            "generated_at": "2026-09-03T00:00:00+00:00",
            "cutoff_exclusive_utc": "2026-08-25T00:00:00+00:00",
            "rows": 2,
            "distinct_keys": 1,
            "symbols": 1,
            "start_utc": "2026-07-01T00:00:00+00:00",
            "end_utc": "2026-07-01T00:15:00+00:00",
            "duplicate_overlap_resolution": "none",
            "completeness_rules": "none",
            "null_fill_policy": "none",
            "rebuild_command": "rebuild",
            "quality_status": "MYSTERIOUS",
            "parquet_inventory_fingerprint": fingerprint,
        },
    )
    with pytest.raises(ValueError, match="unknown quality"):
        assert_cache_sidecar_fresh(root)
    payload = json.loads((root / CACHE_META_FILENAME).read_text(encoding="utf-8"))
    payload["quality_status"] = "OK"
    payload["input_manifest_sha256"] = ""
    write_canonical_json(root / CACHE_META_FILENAME, payload)
    with pytest.raises(ValueError, match="incomplete"):
        assert_cache_sidecar_fresh(root)
