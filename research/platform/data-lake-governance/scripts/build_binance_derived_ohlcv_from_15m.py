#!/usr/bin/env python3
"""Build versioned 1h/4h/1d OHLCV from accepted Binance normalized 15m. Non-destructive."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

import pandas as pd

from strategy_lab.data.catalog import (
    BINANCE_PERP_15M_NORMALIZED_V1,
    BINANCE_PERP_1D_FROM_15M_V1,
    BINANCE_PERP_1H_FROM_15M_V1,
    BINANCE_PERP_4H_FROM_15M_V1,
    DERIVED_SLUGS,
    DatasetKind,
    DatasetRecord,
    DatasetRegistry,
    DatasetScope,
    DatasetStatus,
    FullMarketCoverageSpec,
    register_derived_dataset,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import (
    INPUT_SNAPSHOT_FILENAME,
    INPUT_SNAPSHOTS_DIRNAME,
    assert_safe_dataset_version,
    assert_safe_derived_slug,
    inventory_fingerprint,
    parquet_inventory,
    sha256_file,
    utc_now_iso,
    write_canonical_json,
)
from strategy_lab.data.models import MarketType
from strategy_lab.data.resample import (
    DEFAULT_SOURCE_UNION,
    FORMULA_VERSION,
    PRIORITY_UNION_VERSION,
    aggregation_impl_sha256,
    build_derived_ohlcv,
    derived_manifest,
    publish_staging_dataset,
    verify_existing_derived_publish,
)
from strategy_lab.data.settings import default_settings
from strategy_lab.data.windows import require_aware_utc

ROOT = Path(__file__).resolve().parents[4]
BUILDER = Path("research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py")
V1_OUTPUTS = (
    ("1h", BINANCE_PERP_1H_FROM_15M_V1),
    ("4h", BINANCE_PERP_4H_FROM_15M_V1),
    ("1d", BINANCE_PERP_1D_FROM_15M_V1),
)


def years(cutoff: pd.Timestamp | None) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    bounds = []
    for year in range(2019, 2027):
        start = pd.Timestamp(f"{year}-01-01T00:00:00Z")
        end = pd.Timestamp(f"{year + 1}-01-01T00:00:00Z")
        if cutoff is not None:
            if start >= cutoff:
                break
            end = min(end, cutoff)
        bounds.append((start, end))
    return bounds


def slug_for(timeframe: str, version: str) -> str:
    assert_safe_dataset_version(version)
    if version == "v1":
        dataset_id = dict(V1_OUTPUTS)[timeframe]
        return assert_safe_derived_slug(DERIVED_SLUGS[dataset_id])
    return assert_safe_derived_slug(f"binance_perp_{timeframe}_from_15m_{version}")


def dataset_id_for(timeframe: str, version: str) -> str:
    assert_safe_dataset_version(version)
    if version == "v1":
        return dict(V1_OUTPUTS)[timeframe]
    return f"binance.perp.ohlcv.{timeframe}.from_15m.{version}"


def snapshot_15m(input_root: Path, input_hash: str, inventory: list[dict], *, write: bool) -> Path:
    payload = {
        "schema_version": "1.0",
        "dataset_id": BINANCE_PERP_15M_NORMALIZED_V1,
        "fingerprint_kind": "parquet_inventory_fingerprint",
        "parquet_inventory_fingerprint": input_hash,
        "file_count": len(inventory),
        "bytes": int(sum(int(row["size"]) for row in inventory)),
        "generated_at": utc_now_iso(),
        "note": "directory content snapshot; not a derived publish manifest; v1 derived binds this fingerprint",
    }
    path = input_root / INPUT_SNAPSHOT_FILENAME
    if path.exists():
        import json

        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("parquet_inventory_fingerprint") == input_hash:
            return path
        alt_dir = input_root / INPUT_SNAPSHOTS_DIRNAME
        alt = alt_dir / f"{input_hash}.json"
        if not write:
            return alt
        alt_dir.mkdir(parents=True, exist_ok=True)
        write_canonical_json(alt, payload)
        return alt
    if not write:
        return path
    write_canonical_json(path, payload)
    return path


def derived_record(timeframe: str, version: str, cutoff: str | None) -> DatasetRecord:
    dataset_id = dataset_id_for(timeframe, version)
    slug = slug_for(timeframe, version)
    return DatasetRecord(
        dataset_id=dataset_id,
        layer="derived",
        kind=DatasetKind.OHLCV,
        status=DatasetStatus.TRUSTED_DERIVED,
        declared_scope=DatasetScope.FULL_MARKET,
        exchange="binance",
        market_type=MarketType.PERP,
        timeframe=timeframe,
        relative_root=f"derived/datasets/{slug}",
        source_adjudication="resampled from accepted 15m priority union v1; mixed-source bars use composite: sources; loader passthrough because union is already applied",
        priority_union_version=PRIORITY_UNION_VERSION,
        rebuildable=True,
        is_standard_ohlcv=True,
        cutoff_exclusive_utc=cutoff,
        input_dataset_id=BINANCE_PERP_15M_NORMALIZED_V1,
        builder=BUILDER.as_posix(),
        coverage_spec=FullMarketCoverageSpec(),
        source_union=DEFAULT_SOURCE_UNION.__class__(
            version=PRIORITY_UNION_VERSION,
            priority=(),
            reject_unlisted=False,
            passthrough=True,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeframe", choices=["1h", "4h", "1d", "all"], default="all")
    parser.add_argument(
        "--by-year",
        action="store_true",
        help="stream one calendar year at a time; default is a single DuckDB COPY per timeframe",
    )
    parser.add_argument("--dataset-version", default="v1")
    parser.add_argument("--check", action="store_true", help="verify published output against current input")
    parser.add_argument("--dry-run", action="store_true", help="report actions without writing derived parquet")
    parser.add_argument("--cutoff-exclusive-utc", default=None)
    parser.add_argument("--write-15m-snapshot", action="store_true")
    parser.add_argument("--register", action="store_true", help="write the published version into _DATASET_REGISTRY.json")
    args = parser.parse_args()
    assert_safe_dataset_version(args.dataset_version)
    if args.cutoff_exclusive_utc:
        cutoff = require_aware_utc(args.cutoff_exclusive_utc, field="cutoff_exclusive_utc")
    else:
        cutoff = None
    write_allowed = not (args.check or args.dry_run)
    if args.write_15m_snapshot and not write_allowed:
        raise SystemExit("--write-15m-snapshot cannot be combined with --check or --dry-run")
    if args.register and not write_allowed:
        raise SystemExit("--register cannot be combined with --check or --dry-run")
    layout = DataLakeLayout.from_settings(default_settings())
    layout.ensure_directories()
    registry = DatasetRegistry.from_layout(layout)
    input_record = registry.get(BINANCE_PERP_15M_NORMALIZED_V1)
    input_root = input_record.absolute_root(layout)
    input_files = sorted(path for path in input_root.rglob("*.parquet") if path.is_file())
    if not input_files:
        raise FileNotFoundError(f"no 15m parquet under {input_root}")
    print(f"hashing {len(input_files)} input parquet files", flush=True)
    input_inventory = parquet_inventory(input_root)
    input_hash = inventory_fingerprint(input_inventory)
    if args.write_15m_snapshot:
        snapshot_path = snapshot_15m(input_root, input_hash, input_inventory, write=True)
        print(f"15m snapshot fingerprint={input_hash} path={snapshot_path}", flush=True)
    builder_sha = sha256_file(ROOT / BUILDER)
    impl_sha = aggregation_impl_sha256()
    wanted = [item for item in V1_OUTPUTS if args.timeframe in {item[0], "all"}]
    if args.dataset_version != "v1":
        wanted = [
            (timeframe, dataset_id_for(timeframe, args.dataset_version))
            for timeframe, _dataset_id in wanted
        ]
    cache_dir = layout.cache_dir / "_dataset_quality_audits"
    for timeframe, dataset_id in wanted:
        slug = slug_for(timeframe, args.dataset_version)
        staging = layout.derived_staging_dir / slug
        published = layout.derived_datasets_dir / slug
        print(f"input fingerprint {input_hash} for {dataset_id}", flush=True)
        if published.exists():
            result = verify_existing_derived_publish(
                published_root=published,
                dataset_id=dataset_id,
                input_fingerprint=input_hash,
                formula_version=FORMULA_VERSION,
                cache_dir=cache_dir,
                cutoff_exclusive_utc=None if cutoff is None else cutoff.isoformat(),
                priority_union_version=PRIORITY_UNION_VERSION,
                aggregation_impl_sha256=impl_sha,
            )
            print(result, flush=True)
            continue
        rebuild_command = (
            "python research/platform/data-lake-governance/scripts/"
            f"build_binance_derived_ohlcv_from_15m.py --timeframe {timeframe} "
            f"--dataset-version {args.dataset_version} "
            f"--input-snapshot-fingerprint {input_hash}"
        )
        if cutoff is not None:
            rebuild_command += f" --cutoff-exclusive-utc {cutoff.isoformat()}"
        if args.check or args.dry_run:
            print(
                {
                    "status": "would_publish",
                    "dataset_id": dataset_id,
                    "staging": str(staging),
                    "published": str(published),
                    "cutoff_exclusive_utc": None if cutoff is None else cutoff.isoformat(),
                    "input_snapshot_fingerprint": input_hash,
                    "rebuild_command": rebuild_command,
                    "writes": False,
                },
                flush=True,
            )
            continue
        if staging.exists():
            print(f"removing incomplete unpublished staging {staging}", flush=True)
            shutil.rmtree(staging)
        print(f"building {dataset_id}", flush=True)
        if args.by_year:
            stats = None
            for index, (start, end) in enumerate(years(cutoff)):
                print(f"  {timeframe} {start.year}", flush=True)
                stats = build_derived_ohlcv(
                    input_files=input_files,
                    output_timeframe=timeframe,
                    staging_root=staging,
                    policy=DEFAULT_SOURCE_UNION,
                    start=start,
                    end=end,
                    append=index > 0,
                    write_stats=False,
                    skip_exclusion=True,
                )
            assert stats is not None
        else:
            stats = build_derived_ohlcv(
                input_files=input_files,
                output_timeframe=timeframe,
                staging_root=staging,
                policy=DEFAULT_SOURCE_UNION,
                end=cutoff,
            )
        later_inventory = parquet_inventory(input_root)
        later_hash = inventory_fingerprint(later_inventory)
        if later_hash != input_hash:
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError(
                "15m input changed during build; refusing to publish a mixed snapshot. "
                f"start={input_hash} end={later_hash}"
            )
        stats["cutoff_exclusive_utc"] = None if cutoff is None else cutoff.isoformat()
        stats["rebuild_command"] = rebuild_command
        stats["input_parquet_inventory_fingerprint"] = input_hash
        stats["aggregation_impl_sha256"] = impl_sha
        manifest = derived_manifest(
            dataset_id=dataset_id,
            status="TRUSTED_DERIVED",
            timeframe=timeframe,
            physical_root=str(published),
            input_dataset_id=BINANCE_PERP_15M_NORMALIZED_V1,
            input_manifest_sha256=input_hash,
            builder_path=BUILDER.as_posix(),
            builder_sha256=builder_sha,
            stats=stats,
        )
        result = publish_staging_dataset(
            staging_root=staging,
            published_root=published,
            manifest=manifest.to_dict(),
        )
        if args.register or args.dataset_version != "v1":
            register_derived_dataset(
                layout,
                derived_record(
                    timeframe,
                    args.dataset_version,
                    None if cutoff is None else cutoff.isoformat(),
                ),
            )
            result = dict(result)
            result["registered"] = True
        print(result, flush=True)


if __name__ == "__main__":
    main()
