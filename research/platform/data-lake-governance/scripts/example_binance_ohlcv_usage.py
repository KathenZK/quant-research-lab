#!/usr/bin/env python3
"""Runnable Binance OHLCV catalog examples. Commands match docs/data-lake-spec.md."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pandas as pd

from strategy_lab.data.catalog import (
    BINANCE_PERP_1D_CACHE_FROM_15M,
    BINANCE_PERP_1H_NORMALIZED_LEGACY,
    BINANCE_PERP_4H_FROM_15M_V1,
    DatasetKind,
    DatasetRecord,
    DatasetRegistry,
    DatasetScope,
    DatasetStatus,
    inspect_dataset,
    list_registered_datasets,
    load_canonical_binance_perp_1d,
    load_trusted_dataset,
    load_trusted_research_dataset,
    register_derived_dataset,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import (
    CACHE_META_FILENAME,
    assert_cache_sidecar_fresh,
    inventory_fingerprint,
    parquet_inventory,
    write_canonical_json,
)
from strategy_lab.data.models import MarketType
from strategy_lab.data.resample import (
    FORMULA_VERSION,
    SourceUnionPolicy,
    build_derived_ohlcv,
    derived_manifest,
    publish_staging_dataset,
)
from strategy_lab.data.settings import default_settings

ROOT = Path(__file__).resolve().parents[4]
PINNED_4H_V1 = {
    "parquet_inventory_fingerprint": (
        "a52be016421363b2bfbcdcc6d61b02288de206dfc330d3b4df0a2fa11d0be8a6"
    ),
    "manifest_sha256": "de567a5cea103f104dc52a0bd925db9ea9d3bf824b62cc7d4b8cb82246e612cf",
    "content_fingerprint": "a766fc203621e73c2025b11e87676f4b53d5b27d16c2b373184ede0b5ad82522",
}


def layout() -> DataLakeLayout:
    return DataLakeLayout.from_settings(default_settings())


def _loaded_payload(loaded) -> dict:
    identity = loaded.verified_identity or {}
    return {
        "dataset_id": loaded.record.dataset_id,
        "materialized": loaded.materialized,
        "quality_status": loaded.audit.get("quality_status"),
        "row_quality": loaded.audit.get("row_quality"),
        "historical_coverage": loaded.audit.get("historical_coverage"),
        "research_window_fitness": loaded.audit.get("research_window_fitness"),
        "listing_evidence": loaded.audit.get("listing_evidence"),
        "gap_policy": loaded.audit.get("gap_policy"),
        "internal_missing_bars": loaded.audit.get("internal_missing_bars"),
        "rows": loaded.audit.get("rows"),
        "start_utc": loaded.audit.get("start_utc"),
        "end_utc": loaded.audit.get("end_utc"),
        "cutoff_exclusive_utc": identity.get("cutoff_exclusive_utc"),
        "request_window": identity.get("request_window"),
        "fingerprint_mode": identity.get("fingerprint_mode"),
        "manifest_file_sha256": identity.get("manifest_file_sha256"),
        "content_fingerprint": identity.get("content_fingerprint"),
        "parquet_inventory_fingerprint": loaded.manifest.get("parquet_inventory_fingerprint"),
        "source_counts": loaded.source_counts,
        "coverage": {key: value for key, value in loaded.coverage.items() if key != "per_symbol"},
        "verified_file_count": len(loaded.verified_parquet_files),
        "frame_rows": int(len(loaded.frame)),
        "trusted": loaded.audit.get("quality_status") == "PASS",
    }


def dump(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def cmd_list(_args: argparse.Namespace) -> int:
    rows = list_registered_datasets(layout=layout())
    slim = [
        {
            "dataset_id": row["dataset_id"],
            "purpose": row["purpose"],
            "allowed_scopes": row["allowed_scopes"],
            "status": row["status"],
            "timeframe": row["timeframe"],
            "observed_start_utc": row["observed_start_utc"],
            "observed_end_utc": row["observed_end_utc"],
            "cutoff_exclusive_utc": row["cutoff_exclusive_utc"],
            "version": row["version"],
            "quality_status": row["quality_status"],
            "manifest_sha256": row["manifest_sha256"],
            "parquet_inventory_fingerprint": row["parquet_inventory_fingerprint"],
            "input_snapshot_fingerprint": row["input_snapshot_fingerprint"],
            "known_limits": row["known_limits"],
        }
        for row in rows
    ]
    dump({"datasets": slim, "count": len(slim)})
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    preview = inspect_dataset(
        args.dataset_id,
        layout=layout(),
        requested_scope=DatasetScope(args.scope) if args.scope else None,
        start=args.start,
        end=args.end,
    )
    dump(
        {
            "trusted": preview.trusted,
            "dataset_id": preview.record.dataset_id,
            "status": preview.record.status.value,
            "coverage": {key: value for key, value in preview.coverage.items() if key != "per_symbol"},
            "union_stats": preview.union_stats,
            "parquet_file_count": preview.parquet_file_count,
            "known_limits": list(preview.known_limits),
            "published_cutoff_exclusive_utc": (
                None if preview.published_manifest is None else preview.published_manifest.get("cutoff_exclusive_utc")
            ),
        }
    )
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    loaded = load_trusted_dataset(
        args.dataset_id,
        layout=layout(),
        requested_scope=DatasetScope(args.scope),
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        require_contiguous=False,
        require_closed=True,
        max_materialize_rows=args.max_materialize_rows,
    )
    dump(_loaded_payload(loaded))
    return 0


def cmd_load_research(args: argparse.Namespace) -> int:
    loaded = load_trusted_research_dataset(
        args.dataset_id,
        layout=layout(),
        requested_scope=DatasetScope(args.scope),
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        gap_policy=args.gap_policy,
        max_materialize_rows=args.max_materialize_rows,
        expected_parquet_fingerprint=args.expected_parquet_fingerprint,
        expected_manifest_identity={
            "manifest_sha256": args.expected_manifest_sha256,
            "content_fingerprint": args.expected_content_fingerprint,
            "parquet_inventory_fingerprint": args.expected_parquet_fingerprint,
        },
    )
    dump(_loaded_payload(loaded))
    return 0


def cmd_load_1d(args: argparse.Namespace) -> int:
    loaded = load_canonical_binance_perp_1d(
        layout=layout(),
        requested_scope=DatasetScope(args.scope),
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        require_contiguous=False,
        max_materialize_rows=args.max_materialize_rows,
    )
    dump(_loaded_payload(loaded))
    return 0


def _expect_raise(fn, match: str) -> dict[str, str]:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - example must show the real refusal
        text = str(exc)
        if match not in text:
            raise RuntimeError(f"expected {match!r} in {text!r}") from exc
        return {"rejected": True, "match": match, "error": text[:500]}
    raise RuntimeError(f"expected refusal matching {match!r}")


def cmd_reject(args: argparse.Namespace) -> int:
    lake = layout()
    if args.case == "legacy-1h-full-market":
        result = _expect_raise(
            lambda: load_trusted_dataset(
                BINANCE_PERP_1H_NORMALIZED_LEGACY,
                layout=lake,
                requested_scope=DatasetScope.FULL_MARKET,
            ),
            "cannot satisfy FULL_MARKET",
        )
    elif args.case == "cache-as-ohlcv":
        result = _expect_raise(
            lambda: load_trusted_dataset(
                BINANCE_PERP_1D_CACHE_FROM_15M,
                layout=lake,
                requested_scope=DatasetScope.PARTIAL,
            ),
            "not standard OHLCV",
        )
    elif args.case == "missing-dataset":
        result = _expect_raise(
            lambda: load_trusted_dataset(
                "binance.perp.ohlcv.does_not_exist.v1",
                layout=lake,
                requested_scope=DatasetScope.PARTIAL,
            ),
            "unknown dataset_id",
        )
    elif args.case == "bad-fingerprint":
        result = _expect_raise(
            lambda: load_trusted_dataset(
                BINANCE_PERP_4H_FROM_15M_V1,
                layout=lake,
                requested_scope=DatasetScope.PARTIAL,
                symbol="BTC/USDT:USDT",
                require_contiguous=False,
                expected_parquet_fingerprint="0" * 64,
            ),
            "fingerprint",
        )
    elif args.case == "missing-manifest":
        tmp = Path(tempfile.mkdtemp(prefix="ohlcv-missing-manifest-"))
        fake = DataLakeLayout(
            root_dir=tmp / "data",
            raw_dir=tmp / "data" / "raw",
            normalized_dir=tmp / "data" / "normalized",
            features_dir=tmp / "data" / "features",
            cache_dir=tmp / "data" / "cache",
            derived_dir=tmp / "data" / "derived",
        )
        fake.ensure_directories()
        root = fake.derived_datasets_dir / "binance_perp_4h_from_15m_v1"
        root.mkdir(parents=True)
        pd.DataFrame(
            {
                "ts": [pd.Timestamp("2026-07-01T00:00:00Z")],
                "exchange": ["binance"],
                "symbol": ["BTC/USDT:USDT"],
                "market_type": ["perp"],
                "timeframe": ["4h"],
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [1.0],
                "quote_volume": [1.0],
                "trade_count": [1],
                "vwap": [1.0],
                "is_closed": [True],
                "source": ["binance_vision_kline_monthly"],
            }
        ).to_parquet(root / "x.parquet", index=False)
        result = _expect_raise(
            lambda: load_trusted_dataset(
                BINANCE_PERP_4H_FROM_15M_V1,
                layout=fake,
                requested_scope=DatasetScope.PARTIAL,
                require_contiguous=False,
            ),
            "manifest missing",
        )
    elif args.case == "over-range-window":
        result = _expect_raise(
            lambda: load_trusted_dataset(
                BINANCE_PERP_4H_FROM_15M_V1,
                layout=lake,
                requested_scope=DatasetScope.SINGLE_SYMBOL,
                symbol="BTC/USDT:USDT",
                end="2026-09-03T00:00:00Z",
                require_contiguous=False,
            ),
            "REQUEST_WINDOW_EXCEEDS_AVAILABLE",
        )
    elif args.case == "missing-lineage":
        tmp = Path(tempfile.mkdtemp(prefix="ohlcv-missing-lineage-"))
        root = tmp / "cache" / "panel"
        root.mkdir(parents=True)
        pd.DataFrame(
            {
                "ts": [pd.Timestamp("2026-07-01T00:00:00Z")],
                "close": [1.0],
            }
        ).to_parquet(root / "p.parquet", index=False)
        write_canonical_json(
            root / CACHE_META_FILENAME,
            {
                "quality_status": "OK",
                "parquet_inventory_fingerprint": inventory_fingerprint(parquet_inventory(root)),
            },
        )
        result = _expect_raise(lambda: assert_cache_sidecar_fresh(root), "incomplete")
    elif args.case == "bad-manifest":
        tmp = Path(tempfile.mkdtemp(prefix="ohlcv-bad-manifest-"))
        fake = DataLakeLayout(
            root_dir=tmp / "data",
            raw_dir=tmp / "data" / "raw",
            normalized_dir=tmp / "data" / "normalized",
            features_dir=tmp / "data" / "features",
            cache_dir=tmp / "data" / "cache",
            derived_dir=tmp / "data" / "derived",
        )
        fake.ensure_directories()
        root = fake.derived_datasets_dir / "binance_perp_4h_from_15m_v1"
        root.mkdir(parents=True)
        frame = pd.DataFrame(
            {
                "ts": [pd.Timestamp("2026-07-01T00:00:00Z")],
                "exchange": ["binance"],
                "symbol": ["BTC/USDT:USDT"],
                "market_type": ["perp"],
                "timeframe": ["4h"],
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [1.0],
                "quote_volume": [1.0],
                "trade_count": [1.0],
                "vwap": [1.0],
                "is_closed": [True],
                "source": ["binance_vision_kline_monthly"],
            }
        )
        frame.to_parquet(root / "x.parquet", index=False)
        inventory = parquet_inventory(root)
        input_hash = "a" * 64
        stats = {
            "file_count": len(inventory),
            "bytes": int(sum(int(row["size"]) for row in inventory)),
            "output_rows": 1,
            "distinct_keys": 1,
            "symbols": 1,
            "start_utc": "2026-07-01T00:00:00+00:00",
            "end_utc": "2026-07-01T00:00:00+00:00",
            "parquet_inventory_fingerprint": inventory_fingerprint(inventory),
            "cutoff_exclusive_utc": "2026-08-25T00:00:00+00:00",
            "rebuild_command": "python build.py --timeframe 4h --dataset-version v1 --cutoff-exclusive-utc 2026-08-25T00:00:00+00:00 --input-snapshot-fingerprint " + input_hash,
            "aggregation_impl_sha256": "b" * 64,
            "input_parquet_inventory_fingerprint": input_hash,
            "excluded_incomplete_buckets": 0,
            "mixed_source_rows": 0,
            "source_counts": {},
        }
        derived_manifest(
            dataset_id=BINANCE_PERP_4H_FROM_15M_V1,
            status="TRUSTED_DERIVED",
            timeframe="4h",
            physical_root=str(root.resolve()),
            input_dataset_id="binance.perp.ohlcv.15m.normalized.v1",
            input_manifest_sha256=input_hash,
            builder_path="research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py",
            builder_sha256="c" * 64,
            stats=stats,
        ).write(root / "_MANIFEST.json")
        payload = json.loads((root / "_MANIFEST.json").read_text(encoding="utf-8"))
        payload["exchange"] = "kraken"
        write_canonical_json(root / "_MANIFEST.json", payload)
        result = _expect_raise(
            lambda: load_trusted_dataset(
                BINANCE_PERP_4H_FROM_15M_V1,
                layout=fake,
                requested_scope=DatasetScope.PARTIAL,
                require_contiguous=False,
                end="2026-07-01T04:00:00Z",
            ),
            "fingerprint",
        )
    else:
        raise SystemExit(f"unknown reject case {args.case}")
    dump({"case": args.case, **result})
    return 0


def cmd_publish_register_load(_args: argparse.Namespace) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ohlcv-r3-publish-"))
    lake = DataLakeLayout(
        root_dir=tmp / "data",
        raw_dir=tmp / "data" / "raw",
        normalized_dir=tmp / "data" / "normalized",
        features_dir=tmp / "data" / "features",
        cache_dir=tmp / "data" / "cache",
        derived_dir=tmp / "data" / "derived",
    )
    lake.ensure_directories()
    input_root = lake.root_dir / "normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m"
    input_root.mkdir(parents=True)
    index = pd.date_range("2026-07-01T00:00:00Z", periods=16, freq="15min", tz="UTC")
    close = [100.0 + i for i in range(16)]
    pd.DataFrame(
        {
            "ts": index,
            "exchange": ["binance"] * 16,
            "symbol": ["BTC/USDT:USDT"] * 16,
            "market_type": ["perp"] * 16,
            "timeframe": ["15m"] * 16,
            "open": close,
            "high": [value + 1.0 for value in close],
            "low": [value - 1.0 for value in close],
            "close": close,
            "volume": [10.0] * 16,
            "quote_volume": [float(value) * 10.0 for value in close],
            "trade_count": [1.0] * 16,
            "vwap": close,
            "is_closed": [True] * 16,
            "source": ["binance_vision_kline_monthly"] * 16,
        }
    ).to_parquet(input_root / "in.parquet", index=False)
    cutoff = "2026-07-01T04:00:00+00:00"
    staging = lake.derived_staging_dir / "binance_perp_1h_from_15m_v2"
    stats = build_derived_ohlcv(
        input_files=[input_root / "in.parquet"],
        output_timeframe="1h",
        staging_root=staging,
        end=pd.Timestamp(cutoff),
    )
    published = lake.derived_datasets_dir / "binance_perp_1h_from_15m_v2"
    input_hash = inventory_fingerprint(parquet_inventory(input_root))
    stats["input_parquet_inventory_fingerprint"] = input_hash
    stats["rebuild_command"] = (
        "python research/platform/data-lake-governance/scripts/"
        "build_binance_derived_ohlcv_from_15m.py --timeframe 1h --dataset-version v2 "
        f"--cutoff-exclusive-utc {cutoff} --input-snapshot-fingerprint {input_hash}"
    )
    stats["aggregation_impl_sha256"] = "d" * 64
    manifest = derived_manifest(
        dataset_id="binance.perp.ohlcv.1h.from_15m.v2",
        status="TRUSTED_DERIVED",
        timeframe="1h",
        physical_root=str(published.resolve()),
        input_dataset_id="binance.perp.ohlcv.15m.normalized.v1",
        input_manifest_sha256=input_hash,
        builder_path="research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py",
        builder_sha256="e" * 64,
        stats=stats,
        declared_scope="PARTIAL",
    )
    published_result = publish_staging_dataset(
        staging_root=staging,
        published_root=published,
        manifest=manifest.to_dict(),
    )
    record = DatasetRecord(
        dataset_id="binance.perp.ohlcv.1h.from_15m.v2",
        layer="derived",
        kind=DatasetKind.OHLCV,
        status=DatasetStatus.TRUSTED_DERIVED,
        declared_scope=DatasetScope.PARTIAL,
        exchange="binance",
        market_type=MarketType.PERP,
        timeframe="1h",
        relative_root="derived/datasets/binance_perp_1h_from_15m_v2",
        source_adjudication="example",
        priority_union_version="example",
        rebuildable=True,
        is_standard_ohlcv=True,
        cutoff_exclusive_utc=cutoff,
        input_dataset_id="binance.perp.ohlcv.15m.normalized.v1",
        source_union=SourceUnionPolicy(
            version="example",
            priority=(),
            reject_unlisted=False,
            passthrough=True,
        ),
    )
    registry_path = register_derived_dataset(lake, record)
    restarted = DatasetRegistry.from_layout(lake)
    listed = [item.dataset_id for item in restarted.records()]
    loaded = load_trusted_dataset(
        "binance.perp.ohlcv.1h.from_15m.v2",
        layout=lake,
        requested_scope=DatasetScope.PARTIAL,
        registry=restarted,
        end=cutoff,
        require_contiguous=False,
    )
    dump(
        {
            "temp_root": str(tmp),
            "published": published_result,
            "registry_path": str(registry_path),
            "listed_contains_v2": "binance.perp.ohlcv.1h.from_15m.v2" in listed,
            "loaded": _loaded_payload(loaded),
            "formula_version": FORMULA_VERSION,
        }
    )
    return 0


def cmd_bundle(_args: argparse.Namespace) -> int:
    payload: dict[str, object] = {}

    def capture(name: str, fn) -> None:
        payload[name] = json.loads(_capture_stdout(fn))

    capture("list", lambda: cmd_list(argparse.Namespace()))
    capture(
        "inspect_4h",
        lambda: cmd_inspect(
            argparse.Namespace(
                dataset_id=BINANCE_PERP_4H_FROM_15M_V1,
                scope=DatasetScope.FULL_MARKET.value,
                start=None,
                end=None,
            )
        ),
    )
    capture(
        "load_single_4h",
        lambda: cmd_load(
            argparse.Namespace(
                dataset_id=BINANCE_PERP_4H_FROM_15M_V1,
                scope=DatasetScope.SINGLE_SYMBOL.value,
                symbol="BTC/USDT:USDT",
                start=None,
                end="2026-08-24T08:00:00Z",
                max_materialize_rows=2_000_000,
            )
        ),
    )
    capture(
        "load_full_market_4h_window",
        lambda: cmd_load(
            argparse.Namespace(
                dataset_id=BINANCE_PERP_4H_FROM_15M_V1,
                scope=DatasetScope.FULL_MARKET.value,
                symbol=None,
                start="2026-08-01T00:00:00Z",
                end="2026-08-24T08:00:00Z",
                max_materialize_rows=0,
            )
        ),
    )
    capture(
        "load_research_single_4h",
        lambda: cmd_load_research(
            argparse.Namespace(
                dataset_id=BINANCE_PERP_4H_FROM_15M_V1,
                scope=DatasetScope.SINGLE_SYMBOL.value,
                symbol="BTC/USDT:USDT",
                start=None,
                end="2026-08-24T08:00:00Z",
                gap_policy="reject",
                max_materialize_rows=2_000_000,
                expected_parquet_fingerprint=PINNED_4H_V1["parquet_inventory_fingerprint"],
                expected_manifest_sha256=PINNED_4H_V1["manifest_sha256"],
                expected_content_fingerprint=PINNED_4H_V1["content_fingerprint"],
            )
        ),
    )
    capture(
        "load_1d",
        lambda: cmd_load_1d(
            argparse.Namespace(
                scope=DatasetScope.SINGLE_SYMBOL.value,
                symbol="BTC/USDT:USDT",
                start=None,
                end="2026-08-25T00:00:00Z",
                max_materialize_rows=0,
            )
        ),
    )
    for case in (
        "legacy-1h-full-market",
        "cache-as-ohlcv",
        "missing-dataset",
        "bad-fingerprint",
        "missing-manifest",
        "over-range-window",
        "missing-lineage",
        "bad-manifest",
    ):
        capture(f"reject_{case.replace('-', '_')}", lambda case=case: cmd_reject(argparse.Namespace(case=case)))
    capture("publish_register_load", lambda: cmd_publish_register_load(argparse.Namespace()))
    dump(payload)
    return 0


def _capture_stdout(fn) -> str:
    from io import StringIO
    from contextlib import redirect_stdout

    buffer = StringIO()
    with redirect_stdout(buffer):
        code = fn()
    if code:
        raise RuntimeError(f"command failed with {code}")
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")
    inspect_p = sub.add_parser("inspect")
    inspect_p.add_argument("--dataset-id", required=True)
    inspect_p.add_argument("--scope")
    inspect_p.add_argument("--start")
    inspect_p.add_argument("--end")

    load_p = sub.add_parser("load")
    load_p.add_argument("--dataset-id", required=True)
    load_p.add_argument("--scope", required=True)
    load_p.add_argument("--symbol")
    load_p.add_argument("--start")
    load_p.add_argument("--end")
    load_p.add_argument("--max-materialize-rows", type=int, default=2_000_000)

    research_p = sub.add_parser("load-research")
    research_p.add_argument("--dataset-id", default=BINANCE_PERP_4H_FROM_15M_V1)
    research_p.add_argument("--scope", default=DatasetScope.SINGLE_SYMBOL.value)
    research_p.add_argument("--symbol", default="BTC/USDT:USDT")
    research_p.add_argument("--start")
    research_p.add_argument("--end", default="2026-08-24T08:00:00Z")
    research_p.add_argument("--gap-policy", default="reject")
    research_p.add_argument("--max-materialize-rows", type=int, default=2_000_000)
    research_p.add_argument(
        "--expected-parquet-fingerprint",
        default=PINNED_4H_V1["parquet_inventory_fingerprint"],
    )
    research_p.add_argument(
        "--expected-manifest-sha256",
        default=PINNED_4H_V1["manifest_sha256"],
    )
    research_p.add_argument(
        "--expected-content-fingerprint",
        default=PINNED_4H_V1["content_fingerprint"],
    )

    load1d = sub.add_parser("load-1d")
    load1d.add_argument("--scope", default="PARTIAL")
    load1d.add_argument("--symbol")
    load1d.add_argument("--start")
    load1d.add_argument("--end")
    load1d.add_argument("--max-materialize-rows", type=int, default=0)

    reject_p = sub.add_parser("reject")
    reject_p.add_argument(
        "--case",
        required=True,
        choices=[
            "legacy-1h-full-market",
            "cache-as-ohlcv",
            "missing-dataset",
            "bad-fingerprint",
            "missing-manifest",
            "over-range-window",
            "missing-lineage",
            "bad-manifest",
        ],
    )
    sub.add_parser("bundle")
    sub.add_parser("publish-register-load")

    args = parser.parse_args()
    commands = {
        "list": cmd_list,
        "inspect": cmd_inspect,
        "load": cmd_load,
        "load-research": cmd_load_research,
        "load-1d": cmd_load_1d,
        "reject": cmd_reject,
        "bundle": cmd_bundle,
        "publish-register-load": cmd_publish_register_load,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
