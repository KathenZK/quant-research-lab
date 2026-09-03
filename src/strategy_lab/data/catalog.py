from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable
import json

import duckdb
import pandas as pd

from strategy_lab.data.authenticity import (
    DEFAULT_BLOCKED_SOURCE_PATTERNS,
    DEFAULT_REAL_SOURCE_ALLOWLIST,
    unverified_source_mask,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import (
    DATASET_MANIFEST_FILENAME,
    DATASET_REGISTRY_FILENAME,
    INPUT_SNAPSHOT_FILENAME,
    LINEAGE_INCOMPLETE,
    FingerprintMode,
    assert_published_derived_manifest,
    assert_safe_derived_slug,
    parquet_inventory,
    resolve_parquet_inventory_fingerprint,
    sha256_canonical,
    write_canonical_json,
)
from strategy_lab.data.models import DatasetKind, MarketType
from strategy_lab.data.quality import DuplicatePolicy, audit_ohlcv_frame, resolve_duplicates
from strategy_lab.data.resample import (
    PRIORITY_UNION_VERSION,
    SOURCE_PRIORITY_V1,
    SourceUnionPolicy,
    source_priority_sql,
)
from strategy_lab.data.sessions import OHLCVSessionPolicy, timeframe_delta
from strategy_lab.data.sql_audit import (
    SQL_AUDIT_RULE_VERSION,
    audit_parquet_file_schemas,
    audit_selected_sql,
    describe_parquet_columns,
    timeframe_seconds,
)
from strategy_lab.data.windows import (
    GapPolicy,
    LoadPurpose,
    assert_request_window_covered,
    contiguous_segments,
    gap_intervals_from_timestamps,
    require_aware_utc,
)


class DatasetStatus(StrEnum):
    TRUSTED_BASE = "TRUSTED_BASE"
    TRUSTED_DERIVED = "TRUSTED_DERIVED"
    PARTIAL_SCOPE = "PARTIAL_SCOPE"
    PARTIAL_SCOPE_LEGACY = "PARTIAL_SCOPE_LEGACY"
    FAMILY_CACHE = "FAMILY_CACHE"
    UNACCEPTED = "UNACCEPTED"
    DEPRECATED = "DEPRECATED"


class DatasetScope(StrEnum):
    FULL_MARKET = "FULL_MARKET"
    PARTIAL = "PARTIAL"
    SINGLE_SYMBOL = "SINGLE_SYMBOL"
    FAMILY_PANEL = "FAMILY_PANEL"
    EXPLICIT_DIAGNOSTIC = "EXPLICIT_DIAGNOSTIC"


FULL_MARKET_STATUSES = {
    DatasetStatus.TRUSTED_BASE,
    DatasetStatus.TRUSTED_DERIVED,
}
BLOCKED_TRUSTED_STATUSES = {
    DatasetStatus.UNACCEPTED,
    DatasetStatus.DEPRECATED,
}

BINANCE_PERP_15M_NORMALIZED_V1 = "binance.perp.ohlcv.15m.normalized.v1"
BINANCE_PERP_1H_NORMALIZED_LEGACY = "binance.perp.ohlcv.1h.normalized.legacy"
BINANCE_PERP_1H_FROM_15M_V1 = "binance.perp.ohlcv.1h.from_15m.v1"
BINANCE_PERP_4H_FROM_15M_V1 = "binance.perp.ohlcv.4h.from_15m.v1"
BINANCE_PERP_1D_FROM_15M_V1 = "binance.perp.ohlcv.1d.from_15m.v1"
BINANCE_PERP_1D_CACHE_FROM_15M = "binance.perp.ohlcv.1d.cache.from_15m"
BINANCE_PERP_1D_MA7_RC_P0_PANEL = "binance.perp.panel.1d.ma7_rc.p0"
BINANCE_PERP_1D_MA7_RC_P3_PANEL = "binance.perp.panel.1d.ma7_rc.p3"

DERIVED_SLUGS = {
    BINANCE_PERP_1H_FROM_15M_V1: "binance_perp_1h_from_15m_v1",
    BINANCE_PERP_4H_FROM_15M_V1: "binance_perp_4h_from_15m_v1",
    BINANCE_PERP_1D_FROM_15M_V1: "binance_perp_1d_from_15m_v1",
}


@dataclass(frozen=True, slots=True)
class FullMarketCoverageSpec:
    min_distinct_symbols: int = 100
    min_symbol_days: int = 50_000
    min_calendar_span_days: int = 365 * 4
    min_long_history_symbols: int = 50
    long_history_days: int = 365
    max_short_snapshot_share: float = 0.35
    short_snapshot_days: int = 60


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    dataset_id: str
    layer: str
    kind: DatasetKind
    status: DatasetStatus
    declared_scope: DatasetScope
    exchange: str
    market_type: MarketType
    timeframe: str | None
    relative_root: str
    source_adjudication: str
    priority_union_version: str
    rebuildable: bool
    is_standard_ohlcv: bool
    cutoff_exclusive_utc: str | None = None
    input_dataset_id: str | None = None
    builder: str | None = None
    coverage_spec: FullMarketCoverageSpec | None = None
    source_union: SourceUnionPolicy | None = None

    def absolute_root(self, layout: DataLakeLayout) -> Path:
        return (layout.root_dir / self.relative_root).resolve()


@dataclass(frozen=True, slots=True)
class TrustedLoad:
    frame: pd.DataFrame
    record: DatasetRecord
    manifest: dict[str, Any]
    audit: dict[str, Any]
    source_counts: dict[str, int]
    coverage: dict[str, Any]
    materialized: bool
    verified_parquet_files: tuple[Path, ...] = ()
    verified_identity: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DatasetInspection:
    record: DatasetRecord
    coverage: dict[str, Any]
    union_stats: dict[str, Any]
    published_manifest: dict[str, Any] | None
    parquet_file_count: int
    known_limits: tuple[str, ...]
    trusted: bool = False


class DatasetRegistry:
    def __init__(self, records: Iterable[DatasetRecord] | None = None) -> None:
        self._records = {record.dataset_id: record for record in (records or default_dataset_records())}

    def get(self, dataset_id: str) -> DatasetRecord:
        try:
            return self._records[dataset_id]
        except KeyError as exc:
            known = ", ".join(sorted(self._records))
            raise KeyError(f"unknown dataset_id {dataset_id!r}; known={known}") from exc

    def records(self) -> tuple[DatasetRecord, ...]:
        return tuple(self._records.values())

    def overlay(self, record: DatasetRecord) -> "DatasetRegistry":
        copied = dict(self._records)
        copied[record.dataset_id] = record
        return DatasetRegistry(copied.values())

    @classmethod
    def from_layout(cls, layout: DataLakeLayout) -> "DatasetRegistry":
        records = list(default_dataset_records())
        path = layout.derived_datasets_dir / DATASET_REGISTRY_FILENAME
        if not path.exists():
            return cls(records)
        payload = json.loads(path.read_text(encoding="utf-8"))
        extras = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(extras, list):
            raise ValueError(f"dataset registry {path} must contain a records list")
        by_id = {record.dataset_id: record for record in records}
        for item in extras:
            record = dataset_record_from_payload(item)
            by_id[record.dataset_id] = record
        return cls(by_id.values())


def default_dataset_records() -> tuple[DatasetRecord, ...]:
    union = SourceUnionPolicy(
        version=PRIORITY_UNION_VERSION,
        priority=SOURCE_PRIORITY_V1,
        reject_unlisted=True,
    )
    full_market = FullMarketCoverageSpec()
    return (
        DatasetRecord(
            dataset_id=BINANCE_PERP_15M_NORMALIZED_V1,
            layer="normalized",
            kind=DatasetKind.OHLCV,
            status=DatasetStatus.TRUSTED_BASE,
            declared_scope=DatasetScope.FULL_MARKET,
            exchange="binance",
            market_type=MarketType.PERP,
            timeframe="15m",
            relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m",
            source_adjudication=(
                "priority union v1: binance_vision_kline_monthly over "
                "binance_futures_kline_api; unlisted sources are excluded, not trusted"
            ),
            priority_union_version=PRIORITY_UNION_VERSION,
            rebuildable=False,
            is_standard_ohlcv=True,
            coverage_spec=full_market,
            source_union=union,
        ),
        DatasetRecord(
            dataset_id=BINANCE_PERP_1H_NORMALIZED_LEGACY,
            layer="normalized",
            kind=DatasetKind.OHLCV,
            status=DatasetStatus.PARTIAL_SCOPE_LEGACY,
            declared_scope=DatasetScope.PARTIAL,
            exchange="binance",
            market_type=MarketType.PERP,
            timeframe="1h",
            relative_root="normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h",
            source_adjudication=(
                "legacy mixed 1h partitions; majority of codes are 2026-07 snapshots; "
                "not a full-market history"
            ),
            priority_union_version=LINEAGE_INCOMPLETE,
            rebuildable=False,
            is_standard_ohlcv=True,
            coverage_spec=full_market,
            source_union=SourceUnionPolicy(
                version="legacy_1h_passthrough",
                priority=(),
                reject_unlisted=False,
                passthrough=True,
            ),
        ),
        DatasetRecord(
            dataset_id=BINANCE_PERP_1H_FROM_15M_V1,
            layer="derived",
            kind=DatasetKind.OHLCV,
            status=DatasetStatus.TRUSTED_DERIVED,
            declared_scope=DatasetScope.FULL_MARKET,
            exchange="binance",
            market_type=MarketType.PERP,
            timeframe="1h",
            relative_root=f"derived/datasets/{DERIVED_SLUGS[BINANCE_PERP_1H_FROM_15M_V1]}",
            source_adjudication="resampled from accepted 15m priority union v1; mixed-source bars use composite: sources; loader passthrough because union is already applied",
            priority_union_version=PRIORITY_UNION_VERSION,
            rebuildable=True,
            is_standard_ohlcv=True,
            input_dataset_id=BINANCE_PERP_15M_NORMALIZED_V1,
            builder="research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py",
            coverage_spec=full_market,
            source_union=SourceUnionPolicy(
                version=PRIORITY_UNION_VERSION,
                priority=(),
                reject_unlisted=False,
                passthrough=True,
            ),
        ),
        DatasetRecord(
            dataset_id=BINANCE_PERP_4H_FROM_15M_V1,
            layer="derived",
            kind=DatasetKind.OHLCV,
            status=DatasetStatus.TRUSTED_DERIVED,
            declared_scope=DatasetScope.FULL_MARKET,
            exchange="binance",
            market_type=MarketType.PERP,
            timeframe="4h",
            relative_root=f"derived/datasets/{DERIVED_SLUGS[BINANCE_PERP_4H_FROM_15M_V1]}",
            source_adjudication="resampled from accepted 15m priority union v1; mixed-source bars use composite: sources; loader passthrough because union is already applied",
            priority_union_version=PRIORITY_UNION_VERSION,
            rebuildable=True,
            is_standard_ohlcv=True,
            input_dataset_id=BINANCE_PERP_15M_NORMALIZED_V1,
            builder="research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py",
            coverage_spec=full_market,
            source_union=SourceUnionPolicy(
                version=PRIORITY_UNION_VERSION,
                priority=(),
                reject_unlisted=False,
                passthrough=True,
            ),
        ),
        DatasetRecord(
            dataset_id=BINANCE_PERP_1D_FROM_15M_V1,
            layer="derived",
            kind=DatasetKind.OHLCV,
            status=DatasetStatus.TRUSTED_DERIVED,
            declared_scope=DatasetScope.FULL_MARKET,
            exchange="binance",
            market_type=MarketType.PERP,
            timeframe="1d",
            relative_root=f"derived/datasets/{DERIVED_SLUGS[BINANCE_PERP_1D_FROM_15M_V1]}",
            source_adjudication="resampled from accepted 15m priority union v1; mixed-source bars use composite: sources; loader passthrough because union is already applied",
            priority_union_version=PRIORITY_UNION_VERSION,
            rebuildable=True,
            is_standard_ohlcv=True,
            input_dataset_id=BINANCE_PERP_15M_NORMALIZED_V1,
            builder="research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py",
            coverage_spec=full_market,
            source_union=SourceUnionPolicy(
                version=PRIORITY_UNION_VERSION,
                priority=(),
                reject_unlisted=False,
                passthrough=True,
            ),
        ),
        DatasetRecord(
            dataset_id=BINANCE_PERP_1D_CACHE_FROM_15M,
            layer="cache",
            kind=DatasetKind.OHLCV,
            status=DatasetStatus.FAMILY_CACHE,
            declared_scope=DatasetScope.FAMILY_PANEL,
            exchange="binance",
            market_type=MarketType.PERP,
            timeframe="1d",
            relative_root="cache/binance_perp_1d_from_15m",
            source_adjudication="month parquet preferred over date=* overlay; not canonical OHLCV",
            priority_union_version=LINEAGE_INCOMPLETE,
            rebuildable=True,
            is_standard_ohlcv=False,
            input_dataset_id=BINANCE_PERP_15M_NORMALIZED_V1,
            builder="research/asset-portfolios/1d-monthly-cs-momentum-ls3/scripts/research_binance_1d_mcsm_ls3.py",
        ),
        DatasetRecord(
            dataset_id=BINANCE_PERP_1D_MA7_RC_P0_PANEL,
            layer="cache",
            kind=DatasetKind.OHLCV,
            status=DatasetStatus.FAMILY_CACHE,
            declared_scope=DatasetScope.FAMILY_PANEL,
            exchange="binance",
            market_type=MarketType.PERP,
            timeframe="1d",
            relative_root="cache/binance-1d-ma7-rc-p0",
            source_adjudication="family research panel with indicators/labels; not standard OHLCV",
            priority_union_version=LINEAGE_INCOMPLETE,
            rebuildable=True,
            is_standard_ohlcv=False,
            input_dataset_id=BINANCE_PERP_15M_NORMALIZED_V1,
            builder="research/asset-portfolios/1d-ma7-regime-continuation/scripts/research_binance_1d_ma7_regime_continuation.py",
        ),
        DatasetRecord(
            dataset_id=BINANCE_PERP_1D_MA7_RC_P3_PANEL,
            layer="cache",
            kind=DatasetKind.OHLCV,
            status=DatasetStatus.FAMILY_CACHE,
            declared_scope=DatasetScope.FAMILY_PANEL,
            exchange="binance",
            market_type=MarketType.PERP,
            timeframe="1d",
            relative_root="cache/binance-1d-ma7-rc-p3",
            source_adjudication="family research panel with indicators/labels; not standard OHLCV",
            priority_union_version=LINEAGE_INCOMPLETE,
            rebuildable=True,
            is_standard_ohlcv=False,
            input_dataset_id=BINANCE_PERP_15M_NORMALIZED_V1,
            builder="research/asset-portfolios/1d-ma7-regime-continuation/scripts/run_binance_1d_ma7_regime_p3_confirmatory.py",
        ),
    )


def dataset_record_to_payload(record: DatasetRecord) -> dict[str, Any]:
    union = record.source_union
    spec = record.coverage_spec
    return {
        "dataset_id": record.dataset_id,
        "layer": record.layer,
        "kind": record.kind.value,
        "status": record.status.value,
        "declared_scope": record.declared_scope.value,
        "exchange": record.exchange,
        "market_type": record.market_type.value,
        "timeframe": record.timeframe,
        "relative_root": record.relative_root,
        "source_adjudication": record.source_adjudication,
        "priority_union_version": record.priority_union_version,
        "rebuildable": record.rebuildable,
        "is_standard_ohlcv": record.is_standard_ohlcv,
        "cutoff_exclusive_utc": record.cutoff_exclusive_utc,
        "input_dataset_id": record.input_dataset_id,
        "builder": record.builder,
        "coverage_spec": None if spec is None else asdict(spec),
        "source_union": None
        if union is None
        else {
            "version": union.version,
            "priority": list(union.priority),
            "reject_unlisted": union.reject_unlisted,
            "passthrough": union.passthrough,
        },
    }


def dataset_record_from_payload(payload: dict[str, Any]) -> DatasetRecord:
    union_payload = payload.get("source_union")
    union = None
    if isinstance(union_payload, dict):
        union = SourceUnionPolicy(
            version=str(union_payload.get("version") or PRIORITY_UNION_VERSION),
            priority=tuple(union_payload.get("priority") or ()),
            reject_unlisted=bool(union_payload.get("reject_unlisted", True)),
            passthrough=bool(union_payload.get("passthrough", False)),
        )
    spec_payload = payload.get("coverage_spec")
    spec = FullMarketCoverageSpec(**spec_payload) if isinstance(spec_payload, dict) else None
    return DatasetRecord(
        dataset_id=str(payload["dataset_id"]),
        layer=str(payload["layer"]),
        kind=DatasetKind(payload.get("kind") or "ohlcv"),
        status=DatasetStatus(payload["status"]),
        declared_scope=DatasetScope(payload["declared_scope"]),
        exchange=str(payload["exchange"]),
        market_type=MarketType(payload["market_type"]),
        timeframe=payload.get("timeframe"),
        relative_root=str(payload["relative_root"]),
        source_adjudication=str(payload.get("source_adjudication") or ""),
        priority_union_version=str(payload.get("priority_union_version") or PRIORITY_UNION_VERSION),
        rebuildable=bool(payload.get("rebuildable", True)),
        is_standard_ohlcv=bool(payload.get("is_standard_ohlcv", True)),
        cutoff_exclusive_utc=payload.get("cutoff_exclusive_utc"),
        input_dataset_id=payload.get("input_dataset_id"),
        builder=payload.get("builder"),
        coverage_spec=spec,
        source_union=union,
    )


def registry_path(layout: DataLakeLayout) -> Path:
    return layout.derived_datasets_dir / DATASET_REGISTRY_FILENAME


def register_derived_dataset(layout: DataLakeLayout, record: DatasetRecord) -> Path:
    """Persist a published derived dataset into the layout registry file.

    This does not glob the data root. Unpublished staging paths are refused.
    """

    assert_safe_derived_slug(Path(record.relative_root).name)
    root = record.absolute_root(layout)
    if "_staging" in root.as_posix().split("/"):
        raise ValueError(f"refusing to register unpublished staging path: {root}")
    if not (root / DATASET_MANIFEST_FILENAME).exists():
        raise ValueError(f"cannot register {record.dataset_id}: published manifest missing at {root}")
    path = registry_path(layout)
    existing: list[dict[str, Any]] = []
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        existing = list(payload.get("records") or [])
    by_id = {str(item.get("dataset_id")): item for item in existing}
    by_id[record.dataset_id] = dataset_record_to_payload(record)
    write_canonical_json(
        path,
        {
            "schema_version": "1.0",
            "records": [by_id[key] for key in sorted(by_id)],
        },
    )
    return path


def resolve_dataset(
    dataset_id: str,
    *,
    layout: DataLakeLayout,
    registry: DatasetRegistry | None = None,
) -> DatasetRecord:
    record = (registry or DatasetRegistry.from_layout(layout)).get(dataset_id)
    root = record.absolute_root(layout)
    if layout.root_dir.resolve() not in root.parents and root != layout.root_dir.resolve():
        raise ValueError(f"dataset root escapes data lake: {root}")
    return record


def list_dataset_parquet_files(record: DatasetRecord, layout: DataLakeLayout) -> list[Path]:
    root = record.absolute_root(layout)
    if not root.exists():
        raise FileNotFoundError(
            f"dataset {record.dataset_id} physical root does not exist: {root}; "
            "catalog will not fall back to scanning the data lake"
        )
    files = sorted(path for path in root.rglob("*.parquet") if path.is_file())
    if not files:
        raise FileNotFoundError(
            f"dataset {record.dataset_id} has no parquet files under {root}; "
            "catalog will not fall back to scanning the data lake"
        )
    root_resolved = root.resolve()
    for path in files:
        if root_resolved not in path.resolve().parents and path.resolve() != root_resolved:
            raise ValueError(f"parquet path escaped dataset root: {path}")
    return files


def assert_scope_allowed(record: DatasetRecord, requested_scope: DatasetScope) -> None:
    if record.status in BLOCKED_TRUSTED_STATUSES:
        raise ValueError(
            f"dataset {record.dataset_id} status {record.status.value} is not trusted"
        )
    if requested_scope == DatasetScope.FULL_MARKET:
        if record.status not in FULL_MARKET_STATUSES:
            raise ValueError(
                f"dataset {record.dataset_id} status {record.status.value} cannot satisfy "
                f"{requested_scope.value}; fail closed"
            )
        if record.declared_scope != DatasetScope.FULL_MARKET:
            raise ValueError(
                f"dataset {record.dataset_id} declared_scope={record.declared_scope.value} "
                "cannot satisfy FULL_MARKET"
            )
    if requested_scope == DatasetScope.FAMILY_PANEL and record.status != DatasetStatus.FAMILY_CACHE:
        raise ValueError(f"dataset {record.dataset_id} is not a family cache panel")
    if requested_scope in {DatasetScope.PARTIAL, DatasetScope.SINGLE_SYMBOL, DatasetScope.EXPLICIT_DIAGNOSTIC}:
        if record.status == DatasetStatus.FAMILY_CACHE and not record.is_standard_ohlcv:
            raise ValueError(
                f"dataset {record.dataset_id} is a family panel, not standard OHLCV; "
                "use FAMILY_PANEL scope"
            )


def _connect() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    connection.execute("SET TimeZone='UTC'")
    connection.execute("SET enable_progress_bar=false")
    return connection


def _as_utc(value: pd.Timestamp | str | None, *, field: str = "timestamp") -> pd.Timestamp | None:
    if value is None:
        return None
    return require_aware_utc(value, field=field)


def coverage_from_frame(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty or "ts" not in frame.columns or "symbol" not in frame.columns:
        return {
            "rows": int(len(frame)),
            "symbol_count": 0,
            "symbol_days": 0,
            "calendar_span_days": 0,
            "start_utc": None,
            "end_utc": None,
            "long_history_symbols": 0,
            "short_snapshot_symbols": 0,
            "short_snapshot_share": None,
            "symbols_by_year": {},
        }
    ts = pd.to_datetime(frame["ts"], utc=True)
    working = frame.assign(_ts=ts, _day=ts.dt.floor("D"), _year=ts.dt.year.astype("int64"))
    symbol_span = working.groupby("symbol", dropna=False).agg(
        start=("_ts", "min"),
        end=("_ts", "max"),
        days=("_day", "nunique"),
        rows=("_ts", "size"),
    )
    calendar_span_days = 0
    if working["_ts"].notna().any():
        calendar_span_days = int((working["_ts"].max() - working["_ts"].min()).days)
    long_history_symbols = int(symbol_span["days"].ge(365).sum())
    short_snapshot_symbols = int(symbol_span["days"].lt(60).sum())
    symbol_count = int(working["symbol"].nunique())
    by_year = (
        working.groupby("_year")["symbol"].nunique().sort_index().astype(int).to_dict()
    )
    return {
        "rows": int(len(working)),
        "symbol_count": symbol_count,
        "symbol_days": int(working.groupby(["symbol", "_day"], dropna=False).ngroups),
        "calendar_span_days": calendar_span_days,
        "start_utc": working["_ts"].min().isoformat() if not working.empty else None,
        "end_utc": working["_ts"].max().isoformat() if not working.empty else None,
        "long_history_symbols": long_history_symbols,
        "short_snapshot_symbols": short_snapshot_symbols,
        "short_snapshot_share": (
            (short_snapshot_symbols / symbol_count) if symbol_count else None
        ),
        "symbols_by_year": {str(year): int(count) for year, count in by_year.items()},
        "per_symbol": [
            {
                "symbol": str(symbol),
                "start_utc": row["start"].isoformat(),
                "end_utc": row["end"].isoformat(),
                "effective_days": int(row["days"]),
                "rows": int(row["rows"]),
            }
            for symbol, row in symbol_span.sort_index().iterrows()
        ],
    }


def assert_full_market_coverage(
    coverage: dict[str, Any],
    spec: FullMarketCoverageSpec,
    *,
    dataset_id: str,
) -> None:
    failures: list[str] = []
    if int(coverage.get("symbol_count") or 0) < spec.min_distinct_symbols:
        failures.append(
            f"symbol_count {coverage.get('symbol_count')} < {spec.min_distinct_symbols}"
        )
    if int(coverage.get("symbol_days") or 0) < spec.min_symbol_days:
        failures.append(
            f"symbol_days {coverage.get('symbol_days')} < {spec.min_symbol_days}"
        )
    if int(coverage.get("calendar_span_days") or 0) < spec.min_calendar_span_days:
        failures.append(
            f"calendar_span_days {coverage.get('calendar_span_days')} < {spec.min_calendar_span_days}"
        )
    if int(coverage.get("long_history_symbols") or 0) < spec.min_long_history_symbols:
        failures.append(
            f"long_history_symbols {coverage.get('long_history_symbols')} < {spec.min_long_history_symbols}"
        )
    share = coverage.get("short_snapshot_share")
    if share is not None and float(share) > spec.max_short_snapshot_share:
        failures.append(
            f"short_snapshot_share {share:.3f} > {spec.max_short_snapshot_share}"
        )
    if failures:
        raise ValueError(
            f"dataset {dataset_id} fails FULL_MARKET coverage: {failures}; "
            "distinct symbol count alone is not sufficient"
        )


def dataset_known_limits(record: DatasetRecord) -> tuple[str, ...]:
    limits = [
        f"status={record.status.value}",
        f"declared_scope={record.declared_scope.value}",
    ]
    if record.dataset_id == BINANCE_PERP_1H_NORMALIZED_LEGACY:
        limits.extend(
            [
                "cannot satisfy FULL_MARKET",
                "majority of codes are short 2026-07 snapshots",
                "legacy mixed 1h partitions; not a full-market history",
            ]
        )
    if record.status == DatasetStatus.FAMILY_CACHE:
        limits.extend(
            [
                "not standard OHLCV",
                "LINEAGE_INCOMPLETE sidecar cannot enter a new trusted research flow",
                "not a canonical replacement for derived 1d/4h/1h",
            ]
        )
    if record.status == DatasetStatus.TRUSTED_DERIVED:
        limits.extend(
            [
                "published v1 cutoff_exclusive_utc may be null; pass an explicit closed-bar cutoff",
                "observed end is the last stored complete bar, not wall-clock today",
                "aligned internal gaps from dropped incomplete 15m buckets are reported, not filled",
                "new research must set gap_policy=reject or contiguous_segments; report_only is not a research default",
                "FULL_MARKET gap_policy=reject is UNFIT while internal gaps remain",
            ]
        )
    if record.dataset_id == BINANCE_PERP_15M_NORMALIZED_V1:
        limits.append("trusted base is the directory snapshot bound by _INPUT_SNAPSHOT.json")
    if not record.is_standard_ohlcv:
        limits.append("family panel / cache cannot use the trusted OHLCV loader")
    return tuple(limits)


def _filter_clause(
    *,
    symbol: str | None,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    timeframe: str | None = None,
    closed_bar_cutoff: bool = True,
) -> tuple[str, list[Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if symbol:
        filters.append("replace(upper(symbol), '_', '/') = ?")
        params.append(symbol.upper())
    if start is not None:
        filters.append("ts >= ?")
        params.append(start.to_pydatetime())
    if end is not None:
        if closed_bar_cutoff and timeframe:
            seconds = int(timeframe_delta(timeframe).total_seconds())
            filters.append(f"(ts + INTERVAL '{seconds} seconds') <= ?")
        else:
            filters.append("ts < ?")
        params.append(end.to_pydatetime())
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    return where, params


def _selected_cte_sql(record: DatasetRecord, where: str) -> tuple[str, list[Any]]:
    union = record.source_union or SourceUnionPolicy(
        version=PRIORITY_UNION_VERSION,
        priority=SOURCE_PRIORITY_V1,
        reject_unlisted=True,
    )
    source_sql, source_params = source_priority_sql(union, alias="raw")
    sql = f"""
        raw AS (
            SELECT *
            FROM read_parquet(?, hive_partitioning = false, union_by_name = true)
            {where}
        ),
        selected AS (
            {source_sql}
        )
    """
    return sql, source_params


def coverage_from_sql(
    record: DatasetRecord,
    files: list[Path],
    *,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    union = record.source_union or SourceUnionPolicy(
        version=PRIORITY_UNION_VERSION,
        priority=SOURCE_PRIORITY_V1,
        reject_unlisted=True,
    )
    where, filter_params = _filter_clause(
        symbol=None,
        start=start,
        end=end,
        timeframe=record.timeframe,
        closed_bar_cutoff=True,
    )
    cte, source_params = _selected_cte_sql(record, where)
    file_param = [str(path) for path in files]
    with _connect() as connection:
        raw_counts = connection.execute(
            """
            SELECT
                count(*) AS physical_rows,
                count(*) - count(DISTINCT (symbol, ts, source)) AS within_source_duplicate_rows
            FROM read_parquet(?, hive_partitioning = false, union_by_name = true)
            """
            + (f" {where}" if where else ""),
            [file_param, *filter_params],
        ).fetch_df().iloc[0]
        unlisted = connection.execute(
            """
            SELECT source, count(*) AS rows
            FROM read_parquet(?, hive_partitioning = false, union_by_name = true)
            """
            + (f" {where}" if where else "")
            + " GROUP BY 1 ORDER BY rows DESC",
            [file_param, *filter_params],
        ).fetch_df()
        coverage_row = connection.execute(
            f"""
            WITH {cte}
            SELECT
                count(*) AS rows,
                count(DISTINCT symbol) AS symbol_count,
                count(DISTINCT (symbol, CAST(ts AS DATE))) AS symbol_days,
                min(ts) AS start_ts,
                max(ts) AS end_ts,
                datediff('day', min(ts), max(ts)) AS calendar_span_days
            FROM selected
            """,
            [file_param, *filter_params, *source_params],
        ).fetch_df().iloc[0]
        span = connection.execute(
            f"""
            WITH {cte},
            spans AS (
                SELECT
                    symbol,
                    count(DISTINCT CAST(ts AS DATE)) AS days
                FROM selected
                GROUP BY symbol
            )
            SELECT
                count(*) FILTER (WHERE days >= 365) AS long_history_symbols,
                count(*) FILTER (WHERE days < 60) AS short_snapshot_symbols
            FROM spans
            """,
            [file_param, *filter_params, *source_params],
        ).fetch_df().iloc[0]
        years = connection.execute(
            f"""
            WITH {cte}
            SELECT CAST(date_part('year', ts) AS INTEGER) AS year, count(DISTINCT symbol) AS symbols
            FROM selected
            GROUP BY 1
            ORDER BY 1
            """,
            [file_param, *filter_params, *source_params],
        ).fetch_df()
    symbol_count = int(coverage_row["symbol_count"] or 0)
    short_snapshot_symbols = int(span["short_snapshot_symbols"] or 0)
    start_ts = coverage_row["start_ts"]
    end_ts = coverage_row["end_ts"]
    coverage = {
        "rows": int(coverage_row["rows"] or 0),
        "symbol_count": symbol_count,
        "symbol_days": int(coverage_row["symbol_days"] or 0),
        "calendar_span_days": int(coverage_row["calendar_span_days"] or 0),
        "start_utc": pd.Timestamp(start_ts).isoformat() if pd.notna(start_ts) else None,
        "end_utc": pd.Timestamp(end_ts).isoformat() if pd.notna(end_ts) else None,
        "long_history_symbols": int(span["long_history_symbols"] or 0),
        "short_snapshot_symbols": short_snapshot_symbols,
        "short_snapshot_share": (
            (short_snapshot_symbols / symbol_count) if symbol_count else None
        ),
        "symbols_by_year": {
            str(int(row["year"])): int(row["symbols"]) for _, row in years.iterrows()
        },
    }
    stats = {
        "physical_rows": int(raw_counts["physical_rows"]),
        "within_source_duplicate_rows": int(raw_counts["within_source_duplicate_rows"]),
        "unlisted_sources": {
            str(row["source"]): int(row["rows"])
            for _, row in unlisted.iterrows()
            if union.priority
            and str(row["source"]) not in union.priority
            and not union.passthrough
        },
        "selected_rows": coverage["rows"],
    }
    return coverage, stats


def _load_selected_frame(
    record: DatasetRecord,
    files: list[Path],
    *,
    symbol: str | None,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> pd.DataFrame:
    where, filter_params = _filter_clause(
        symbol=symbol,
        start=start,
        end=end,
        timeframe=record.timeframe,
        closed_bar_cutoff=True,
    )
    cte, source_params = _selected_cte_sql(record, where)
    params: list[Any] = [[str(path) for path in files], *filter_params, *source_params]
    sql = f"""
        WITH {cte}
        SELECT * FROM selected
        ORDER BY ts, symbol
    """
    with _connect() as connection:
        frame = connection.execute(sql, params).fetch_df()
    if "ts" in frame.columns:
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="raise")
    return frame


def _requires_derived_manifest(record: DatasetRecord) -> bool:
    return record.layer == "derived" or record.status == DatasetStatus.TRUSTED_DERIVED


def _audit_cache_dir(layout: DataLakeLayout) -> Path:
    return layout.cache_dir / "_dataset_quality_audits"


def _cached_coverage_from_sql(
    record: DatasetRecord,
    files: list[Path],
    *,
    layout: DataLakeLayout,
    parquet_fingerprint: str,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cache_key = sha256_canonical(
        {
            "kind": "coverage_v1",
            "dataset_id": record.dataset_id,
            "parquet_inventory_fingerprint": parquet_fingerprint,
            "union_version": record.priority_union_version,
            "start": None if start is None else start.isoformat(),
            "end": None if end is None else end.isoformat(),
            "closed_bar_cutoff": True,
        }
    )
    cache_dir = _audit_cache_dir(layout)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"coverage-{cache_key}.json"
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache_path.unlink(missing_ok=True)
            cached = None
        else:
            recorded_integrity = str(cached.get("integrity_sha256") or "")
            actual_integrity = sha256_canonical(
                {key: value for key, value in cached.items() if key != "integrity_sha256"}
            )
            if (
                recorded_integrity == actual_integrity
                and cached.get("parquet_inventory_fingerprint") == parquet_fingerprint
                and cached.get("coverage")
                and cached.get("union_stats")
            ):
                return cached["coverage"], cached["union_stats"]
            cache_path.unlink(missing_ok=True)
    coverage, stats = coverage_from_sql(record, files, start=start, end=end)
    payload = {
        "parquet_inventory_fingerprint": parquet_fingerprint,
        "coverage": coverage,
        "union_stats": stats,
    }
    payload["integrity_sha256"] = sha256_canonical(payload)
    write_canonical_json(cache_path, payload)
    return coverage, stats


def _count_cutoff_unclosed(
    connection: duckdb.DuckDBPyConnection,
    files: list[Path],
    *,
    timeframe: str,
    cutoff: pd.Timestamp,
    symbol: str | None = None,
) -> int:
    seconds = timeframe_seconds(timeframe)
    filters = [
        "ts < ?",
        f"(ts + INTERVAL '{seconds} seconds') > ?",
    ]
    params: list[Any] = [
        [str(path) for path in files],
        cutoff.to_pydatetime(),
        cutoff.to_pydatetime(),
    ]
    if symbol:
        filters.append("replace(upper(symbol), '_', '/') = ?")
        params.append(symbol.upper())
    return int(
        connection.execute(
            f"""
            SELECT count(*)
            FROM read_parquet(?, hive_partitioning = false, union_by_name = true)
            WHERE {' AND '.join(filters)}
            """,
            params,
        ).fetchone()[0]
    )


def verify_input_snapshot(
    record: DatasetRecord,
    layout: DataLakeLayout,
    *,
    required: bool,
) -> dict[str, Any] | None:
    if record.dataset_id != BINANCE_PERP_15M_NORMALIZED_V1:
        return None
    root = record.absolute_root(layout)
    path = root / INPUT_SNAPSHOT_FILENAME
    if not path.exists():
        if required:
            raise ValueError(
                f"dataset {record.dataset_id} is missing {INPUT_SNAPSHOT_FILENAME}; "
                "write a content snapshot before treating the 15m directory as a frozen input"
            )
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if str(payload.get("dataset_id") or "") != record.dataset_id:
        raise ValueError(
            f"15m snapshot dataset_id {payload.get('dataset_id')!r} != {record.dataset_id!r}"
        )
    actual = resolve_parquet_inventory_fingerprint(
        root,
        cache_dir=None,
        expected=str(payload.get("parquet_inventory_fingerprint") or ""),
        mode=FingerprintMode.STRICT_CONTENT,
    )
    recorded = str(payload.get("parquet_inventory_fingerprint") or "")
    if actual != recorded:
        raise ValueError(
            "15m input snapshot fingerprint mismatch: "
            f"snapshot={recorded} actual={actual}"
        )
    return {
        "snapshot_path": str(path),
        "parquet_inventory_fingerprint": actual,
        "file_count": payload.get("file_count"),
        "bytes": payload.get("bytes"),
        "generated_at": payload.get("generated_at"),
        "fingerprint_kind": "parquet_inventory_fingerprint",
    }


def inspect_dataset(
    dataset_id: str,
    *,
    layout: DataLakeLayout,
    requested_scope: DatasetScope | None = None,
    start: pd.Timestamp | str | None = None,
    end: pd.Timestamp | str | None = None,
    registry: DatasetRegistry | None = None,
) -> DatasetInspection:
    """Coverage/identity preview. This is not a trusted quality pass."""

    record = resolve_dataset(dataset_id, layout=layout, registry=registry)
    if requested_scope is not None:
        assert_scope_allowed(record, requested_scope)
    files = list_dataset_parquet_files(record, layout)
    parquet_fingerprint = resolve_parquet_inventory_fingerprint(
        record.absolute_root(layout),
        cache_dir=_audit_cache_dir(layout),
        mode=FingerprintMode.FAST_METADATA,
    )
    coverage, union_stats = _cached_coverage_from_sql(
        record,
        files,
        layout=layout,
        parquet_fingerprint=parquet_fingerprint,
        start=_as_utc(start),
        end=_as_utc(end),
    )
    published = read_published_manifest(record, layout)
    return DatasetInspection(
        record=record,
        coverage=coverage,
        union_stats=union_stats,
        published_manifest=published,
        parquet_file_count=len(files),
        known_limits=dataset_known_limits(record),
        trusted=False,
    )


def list_registered_datasets(
    *,
    layout: DataLakeLayout,
    registry: DatasetRegistry | None = None,
) -> list[dict[str, Any]]:
    resolved = registry or DatasetRegistry.from_layout(layout)
    rows: list[dict[str, Any]] = []
    for record in resolved.records():
        root = record.absolute_root(layout)
        published = None
        if (root / DATASET_MANIFEST_FILENAME).exists():
            published = json.loads((root / DATASET_MANIFEST_FILENAME).read_text(encoding="utf-8"))
        snapshot = None
        snapshot_path = root / INPUT_SNAPSHOT_FILENAME
        if snapshot_path.exists():
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        allowed_scopes = [record.declared_scope.value]
        if record.status in FULL_MARKET_STATUSES and record.declared_scope == DatasetScope.FULL_MARKET:
            allowed_scopes = [
                DatasetScope.FULL_MARKET.value,
                DatasetScope.PARTIAL.value,
                DatasetScope.SINGLE_SYMBOL.value,
                DatasetScope.EXPLICIT_DIAGNOSTIC.value,
            ]
        elif record.status == DatasetStatus.PARTIAL_SCOPE_LEGACY:
            allowed_scopes = [
                DatasetScope.PARTIAL.value,
                DatasetScope.SINGLE_SYMBOL.value,
                DatasetScope.EXPLICIT_DIAGNOSTIC.value,
            ]
        elif record.status == DatasetStatus.FAMILY_CACHE:
            allowed_scopes = [DatasetScope.FAMILY_PANEL.value]
        snapshot_fp = None if snapshot is None else snapshot.get("parquet_inventory_fingerprint")
        published_fp = None
        if published is not None:
            published_fp = published.get("parquet_inventory_fingerprint") or (
                (published.get("extra") or {}).get("parquet_inventory_fingerprint")
            )
        rows.append(
            {
                "dataset_id": record.dataset_id,
                "purpose": record.source_adjudication,
                "layer": record.layer,
                "status": record.status.value,
                "declared_scope": record.declared_scope.value,
                "allowed_scopes": allowed_scopes,
                "timeframe": record.timeframe,
                "relative_root": record.relative_root,
                "exists": root.exists(),
                "is_standard_ohlcv": record.is_standard_ohlcv,
                "observed_start_utc": None if published is None else published.get("start_utc"),
                "observed_end_utc": None if published is None else published.get("end_utc"),
                "cutoff_exclusive_utc": (
                    record.cutoff_exclusive_utc
                    if record.cutoff_exclusive_utc is not None
                    else None if published is None else published.get("cutoff_exclusive_utc")
                ),
                "version": record.dataset_id.rsplit(".", 1)[-1],
                "manifest_sha256": None,
                "parquet_inventory_fingerprint": published_fp or snapshot_fp,
                "input_snapshot_fingerprint": snapshot_fp,
                "quality_status": None if published is None else published.get("quality_status"),
                "known_limits": list(dataset_known_limits(record)),
            }
        )
        manifest_path = root / DATASET_MANIFEST_FILENAME
        if manifest_path.exists():
            from strategy_lab.data.manifest import sha256_file

            rows[-1]["manifest_sha256"] = sha256_file(manifest_path)
    return rows


def load_canonical_binance_perp_1d(
    *,
    layout: DataLakeLayout,
    requested_scope: DatasetScope,
    symbol: str | None = None,
    start: pd.Timestamp | str | None = None,
    end: pd.Timestamp | str | None = None,
    require_contiguous: bool | None = False,
    require_closed: bool = True,
    allow_full_scan: bool = False,
    max_materialize_rows: int = 2_000_000,
    expected_parquet_fingerprint: str | None = None,
    expected_manifest_identity: dict[str, Any] | None = None,
    purpose: LoadPurpose = "unspecified",
    gap_policy: GapPolicy | None = None,
    allow_incomplete_request_window: bool = False,
    fingerprint_mode: FingerprintMode | str = FingerprintMode.STRICT_CONTENT,
) -> TrustedLoad:
    """Canonical 1d entry for new daily experiments. Not the family 1d cache."""

    return load_trusted_dataset(
        BINANCE_PERP_1D_FROM_15M_V1,
        layout=layout,
        requested_scope=requested_scope,
        symbol=symbol,
        start=start,
        end=end,
        require_contiguous=require_contiguous,
        require_closed=require_closed,
        allow_full_scan=allow_full_scan,
        max_materialize_rows=max_materialize_rows,
        expected_parquet_fingerprint=expected_parquet_fingerprint,
        expected_manifest_identity=expected_manifest_identity,
        purpose=purpose,
        gap_policy=gap_policy,
        allow_incomplete_request_window=allow_incomplete_request_window,
        fingerprint_mode=fingerprint_mode,
    )


def require_passing_trusted(loaded: TrustedLoad) -> TrustedLoad:
    if not loaded.audit or loaded.audit.get("quality_status") != "PASS":
        raise ValueError(
            f"dataset {loaded.record.dataset_id} is not a passing trusted load: "
            f"{loaded.audit.get('blockers') if loaded.audit else 'empty audit'}"
        )
    if not loaded.verified_parquet_files:
        raise ValueError(
            f"dataset {loaded.record.dataset_id} trusted load has no verified parquet files"
        )
    return loaded


def _sql_audit_for_record(
    record: DatasetRecord,
    files: list[Path],
    *,
    layout: DataLakeLayout,
    symbol: str | None,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    require_closed: bool,
    allowed_sources: tuple[str, ...],
    blocked_source_patterns: tuple[str, ...],
    parquet_fingerprint: str,
    gap_policy: str,
) -> dict[str, Any]:
    where, filter_params = _filter_clause(
        symbol=symbol,
        start=start,
        end=end,
        timeframe=record.timeframe,
        closed_bar_cutoff=True,
    )
    cte, source_params = _selected_cte_sql(record, where)
    params: list[Any] = [[str(path) for path in files], *filter_params, *source_params]
    cache_key = sha256_canonical(
        {
            "rule_version": SQL_AUDIT_RULE_VERSION,
            "dataset_id": record.dataset_id,
            "exchange": record.exchange,
            "market_type": record.market_type.value,
            "timeframe": record.timeframe,
            "source_adjudication": record.source_adjudication,
            "parquet_inventory_fingerprint": parquet_fingerprint,
            "symbol": symbol,
            "start": None if start is None else start.isoformat(),
            "end": None if end is None else end.isoformat(),
            "require_closed": require_closed,
            "closed_bar_cutoff": True,
            "gap_policy": gap_policy,
            "union_version": record.priority_union_version,
            "allowed_sources": list(allowed_sources),
            "blocked_source_patterns": list(blocked_source_patterns),
        }
    )
    cache_dir = _audit_cache_dir(layout)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key}.json"
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache_path.unlink(missing_ok=True)
            cached = None
        else:
            recorded_integrity = str(cached.get("integrity_sha256") or "")
            actual_integrity = sha256_canonical(
                {key: value for key, value in cached.items() if key != "integrity_sha256"}
            )
            identity_ok = (
                recorded_integrity == actual_integrity
                and cached.get("cache_key") == cache_key
                and cached.get("parquet_inventory_fingerprint") == parquet_fingerprint
                and cached.get("rule_version") == SQL_AUDIT_RULE_VERSION
                and cached.get("dataset_id") == record.dataset_id
                and cached.get("gap_policy") == gap_policy
                and isinstance(cached.get("audit"), dict)
                and cached["audit"].get("quality_status") in {"PASS", "FAIL"}
            )
            if identity_ok:
                return cached["audit"]
            cache_path.unlink(missing_ok=True)
    with _connect() as connection:
        columns = describe_parquet_columns(connection, files)
        unclosed = 0
        if end is not None and record.timeframe:
            unclosed = _count_cutoff_unclosed(
                connection,
                files,
                timeframe=record.timeframe,
                cutoff=end,
                symbol=symbol,
            )
        audit = audit_selected_sql(
            connection,
            selected_cte=cte,
            params=params,
            timeframe=record.timeframe or "15m",
            require_closed=require_closed,
            allowed_sources=allowed_sources,
            blocked_source_patterns=blocked_source_patterns,
            columns=columns,
            cutoff_unclosed_excluded_rows=unclosed,
            expected_exchange=record.exchange,
            expected_market_type=record.market_type.value,
            files=files,
        )
    cache_payload = {
        "cache_key": cache_key,
        "parquet_inventory_fingerprint": parquet_fingerprint,
        "rule_version": SQL_AUDIT_RULE_VERSION,
        "dataset_id": record.dataset_id,
        "gap_policy": gap_policy,
        "audit": audit,
    }
    cache_payload["integrity_sha256"] = sha256_canonical(cache_payload)
    write_canonical_json(cache_path, cache_payload)
    return audit


def load_trusted_dataset(
    dataset_id: str,
    *,
    layout: DataLakeLayout,
    requested_scope: DatasetScope,
    symbol: str | None = None,
    start: pd.Timestamp | str | None = None,
    end: pd.Timestamp | str | None = None,
    registry: DatasetRegistry | None = None,
    require_contiguous: bool | None = None,
    require_closed: bool = True,
    allow_full_scan: bool = False,
    max_materialize_rows: int = 2_000_000,
    allowed_sources: tuple[str, ...] = DEFAULT_REAL_SOURCE_ALLOWLIST,
    blocked_source_patterns: tuple[str, ...] = DEFAULT_BLOCKED_SOURCE_PATTERNS,
    expected_parquet_fingerprint: str | None = None,
    expected_manifest_identity: dict[str, Any] | None = None,
    purpose: LoadPurpose = "unspecified",
    gap_policy: GapPolicy | None = None,
    allow_incomplete_request_window: bool = False,
    fingerprint_mode: FingerprintMode | str = FingerprintMode.STRICT_CONTENT,
) -> TrustedLoad:
    record = resolve_dataset(dataset_id, layout=layout, registry=registry)
    assert_scope_allowed(record, requested_scope)
    if requested_scope == DatasetScope.SINGLE_SYMBOL and not symbol:
        raise ValueError("SINGLE_SYMBOL scope requires an explicit symbol")
    if not record.is_standard_ohlcv:
        raise ValueError(
            f"dataset {dataset_id} is not standard OHLCV and cannot use the trusted OHLCV loader"
        )
    resolved_mode = FingerprintMode(fingerprint_mode)
    if purpose == "research" and resolved_mode is not FingerprintMode.STRICT_CONTENT:
        raise ValueError("research trusted load requires fingerprint_mode=strict_content")
    if purpose == "research" and end is None:
        raise ValueError("research trusted load requires an explicit closed-bar cutoff")
    if requested_scope == DatasetScope.FULL_MARKET and end is None and purpose != "governance_audit":
        raise ValueError(
            "FULL_MARKET trusted load without a cutoff requires purpose='governance_audit'"
        )
    if purpose == "research" and requested_scope == DatasetScope.EXPLICIT_DIAGNOSTIC:
        pass
    files = list_dataset_parquet_files(record, layout)
    with _connect() as connection:
        schema_errors = audit_parquet_file_schemas(
            connection,
            files,
            expected_exchange=record.exchange,
            expected_market_type=record.market_type.value,
            expected_timeframe=record.timeframe,
        )
    if schema_errors:
        raise ValueError(f"dataset {dataset_id} is not trusted (schema): {schema_errors}")
    start_ts = _as_utc(start, field="start")
    end_ts = _as_utc(end, field="end")
    if requested_scope == DatasetScope.FULL_MARKET and symbol is not None:
        raise ValueError("FULL_MARKET scope cannot be combined with a single-symbol filter")

    verified_identity: dict[str, Any] = {
        "dataset_id": record.dataset_id,
        "status": record.status.value,
        "declared_scope": record.declared_scope.value,
        "requested_scope": requested_scope.value,
        "layer": record.layer,
        "exchange": record.exchange,
        "market_type": record.market_type.value,
        "timeframe": record.timeframe,
        "closed_bar_cutoff": True,
        "purpose": purpose,
        "fingerprint_mode": resolved_mode.value,
        "fingerprint_is_content_proof": resolved_mode is FingerprintMode.STRICT_CONTENT,
        "known_limits": list(dataset_known_limits(record)),
    }
    if _requires_derived_manifest(record):
        verified_identity.update(
            assert_published_derived_manifest(
                dataset_id=record.dataset_id,
                root=record.absolute_root(layout),
                expected_fingerprint=expected_parquet_fingerprint,
                cache_dir=_audit_cache_dir(layout) if resolved_mode is FingerprintMode.FAST_METADATA else None,
                fingerprint_mode=resolved_mode,
                expected_manifest_identity=expected_manifest_identity,
                exchange=record.exchange,
                market_type=record.market_type.value,
                timeframe=record.timeframe or "",
                declared_scope=record.declared_scope.value,
                layer=record.layer,
                status=record.status.value,
                input_dataset_id=record.input_dataset_id,
            )
        )
        parquet_fingerprint = str(verified_identity["parquet_inventory_fingerprint"])
        if verified_identity.get("historical_null_cutoff") and purpose == "research" and end_ts is None:
            raise ValueError(
                f"dataset {dataset_id} is a historical v1 with null cutoff; "
                "research consumption requires an explicit closed-bar cutoff"
            )
    else:
        parquet_fingerprint = resolve_parquet_inventory_fingerprint(
            record.absolute_root(layout),
            cache_dir=_audit_cache_dir(layout) if resolved_mode is FingerprintMode.FAST_METADATA else None,
            expected=expected_parquet_fingerprint,
            mode=resolved_mode,
        )
        snapshot = verify_input_snapshot(
            record,
            layout,
            required=record.dataset_id == BINANCE_PERP_15M_NORMALIZED_V1,
        )
        if snapshot:
            verified_identity["input_snapshot"] = snapshot
        verified_identity["parquet_inventory_fingerprint"] = parquet_fingerprint

    dataset_coverage, dataset_union_stats = _cached_coverage_from_sql(
        record,
        files,
        layout=layout,
        parquet_fingerprint=parquet_fingerprint,
    )
    if start_ts is None and end_ts is None:
        coverage, union_stats = dataset_coverage, dataset_union_stats
    else:
        coverage, union_stats = _cached_coverage_from_sql(
            record,
            files,
            layout=layout,
            parquet_fingerprint=parquet_fingerprint,
            start=start_ts,
            end=end_ts,
        )
    verified_identity["dataset_coverage"] = dict(dataset_coverage)
    available_start = None
    available_end = None
    if dataset_coverage.get("start_utc"):
        start_raw = pd.Timestamp(dataset_coverage["start_utc"])
        if start_raw.tzinfo is None:
            raise ValueError(f"dataset {dataset_id} is not trusted (schema): coverage start is timezone-naive")
        available_start = start_raw.tz_convert("UTC")
    if dataset_coverage.get("end_utc"):
        end_raw = pd.Timestamp(dataset_coverage["end_utc"])
        if end_raw.tzinfo is None:
            raise ValueError(f"dataset {dataset_id} is not trusted (schema): coverage end is timezone-naive")
        available_end = end_raw.tz_convert("UTC")
    window = assert_request_window_covered(
        dataset_id=dataset_id,
        timeframe=record.timeframe or "15m",
        requested_start=start_ts,
        requested_end=end_ts,
        available_start=available_start,
        available_end=available_end,
        allow_incomplete_request_window=allow_incomplete_request_window
        and requested_scope == DatasetScope.EXPLICIT_DIAGNOSTIC,
    )
    verified_identity["request_window"] = window
    if dataset_union_stats["within_source_duplicate_rows"]:
        raise ValueError(
            f"dataset {dataset_id} has {dataset_union_stats['within_source_duplicate_rows']} "
            "within-source duplicate business keys"
        )
    if union_stats["within_source_duplicate_rows"]:
        raise ValueError(
            f"dataset {dataset_id} has {union_stats['within_source_duplicate_rows']} "
            "within-source duplicate business keys"
        )
    if union_stats["selected_rows"] <= 0:
        raise ValueError(f"dataset {dataset_id} selected union is empty")
    if requested_scope == DatasetScope.FULL_MARKET:
        spec = record.coverage_spec or FullMarketCoverageSpec()
        assert_full_market_coverage(dataset_coverage, spec, dataset_id=dataset_id)

    if gap_policy is None:
        if require_contiguous:
            gap_policy = "reject"
        elif purpose == "research":
            raise ValueError("research trusted load requires gap_policy='reject' or 'contiguous_segments'")
        else:
            gap_policy = "report_only"
    if purpose == "research" and gap_policy == "report_only":
        raise ValueError(
            "new research cannot default to gap_policy=report_only; "
            "choose reject or contiguous_segments"
        )
    contiguous = gap_policy == "reject"
    audit = _sql_audit_for_record(
        record,
        files,
        layout=layout,
        symbol=symbol if requested_scope != DatasetScope.FULL_MARKET else None,
        start=start_ts,
        end=end_ts,
        require_closed=require_closed,
        allowed_sources=allowed_sources,
        blocked_source_patterns=blocked_source_patterns,
        parquet_fingerprint=parquet_fingerprint,
        gap_policy=gap_policy,
    )
    if contiguous:
        audit = dict(audit)
        blockers = dict(audit.get("blockers") or {})
        if int(audit.get("internal_missing_bars") or 0) > 0:
            blockers["missing_bars"] = int(audit["internal_missing_bars"])
            audit["quality_status"] = "FAIL"
            audit["trusted"] = False
        audit["blockers"] = blockers
        audit["gap_policy"] = "reject"
    elif gap_policy == "contiguous_segments":
        audit = dict(audit)
        audit["gap_policy"] = "contiguous_segments"
        audit["excluded_near_gap_windows"] = int(audit.get("internal_gap_transitions") or 0)
    else:
        audit = dict(audit)
        audit["gap_policy"] = "report_only"
        audit["excluded_near_gap_windows"] = 0
    missing = int(audit.get("internal_missing_bars") or 0)
    row_blockers = {
        key: value
        for key, value in (audit.get("blockers") or {}).items()
        if key not in {"missing_bars"} and value
    }
    audit["row_quality"] = "FAIL" if row_blockers else "PASS"
    audit["historical_coverage"] = (
        "INTERNAL_GAPS" if missing else "COMPLETE_WITHIN_OBSERVED_SPAN"
    )
    if gap_policy == "reject" and missing:
        audit["research_window_fitness"] = "UNFIT"
    elif gap_policy == "contiguous_segments" and missing:
        audit["research_window_fitness"] = "SEGMENTS_ONLY"
    elif missing:
        audit["research_window_fitness"] = "GAPS_REPORTED_ONLY"
    else:
        audit["research_window_fitness"] = "FIT"
    audit["listing_evidence"] = "unknown"

    if audit.get("quality_status") != "PASS":
        blockers = audit.get("blockers") or {}
        labels = []
        if blockers.get("unverified_source_rows"):
            labels.append("unverified source")
        if blockers.get("duplicate_business_key_rows") or blockers.get("duplicate_rows"):
            labels.append("duplicate business keys")
        if blockers.get("illegal_ohlc_rows"):
            labels.append("illegal OHLC")
        if blockers.get("open_rows"):
            labels.append("unclosed bars")
        if blockers.get("schema_errors"):
            labels.append("schema")
        detail = ", ".join(labels) if labels else "quality blockers"
        raise ValueError(f"dataset {dataset_id} is not trusted ({detail}): {blockers}")

    should_materialize = allow_full_scan or symbol is not None or (
        int(union_stats["selected_rows"]) <= max_materialize_rows
        and requested_scope != DatasetScope.FULL_MARKET
    )
    if requested_scope == DatasetScope.FULL_MARKET and int(union_stats["selected_rows"]) <= max_materialize_rows:
        should_materialize = True

    stats = parquet_inventory(record.absolute_root(layout), compute_hashes=False)
    manifest = {
        "dataset_id": record.dataset_id,
        "status": record.status.value,
        "declared_scope": record.declared_scope.value,
        "requested_scope": requested_scope.value,
        "layer": record.layer,
        "exchange": record.exchange,
        "market_type": record.market_type.value,
        "timeframe": record.timeframe,
        "physical_root": str(record.absolute_root(layout)),
        "source_adjudication": record.source_adjudication,
        "priority_union_version": record.priority_union_version,
        "file_count": len(stats),
        "bytes": int(sum(row["size"] for row in stats)),
        "parquet_inventory_fingerprint": parquet_fingerprint,
        "union_stats": union_stats,
        "verified_identity": {
            key: value
            for key, value in verified_identity.items()
            if key != "payload"
        },
    }
    source_counts = dict(audit.get("source_counts") or {})
    frame = pd.DataFrame()
    if should_materialize:
        frame = _load_selected_frame(
            record,
            files,
            symbol=symbol,
            start=start_ts,
            end=end_ts,
        )
        if frame.empty:
            raise ValueError(f"dataset {dataset_id} selected union is empty")
        if "source" not in frame.columns:
            raise ValueError(f"dataset {dataset_id} missing source lineage")
        unknown_mask = unverified_source_mask(
            frame,
            allowed_sources=allowed_sources,
            blocked_patterns=blocked_source_patterns,
        )
        if bool(unknown_mask.any()):
            raise ValueError(
                f"dataset {dataset_id} has {int(unknown_mask.sum())} unverified source rows"
            )
        frame, duplicate_stats = resolve_duplicates(
            record.kind,
            frame,
            policy=DuplicatePolicy.ERROR,
        )
        manifest["duplicate_stats"] = duplicate_stats.to_dict()
        if requested_scope != DatasetScope.FULL_MARKET:
            coverage = coverage_from_frame(frame)
        source_counts = {
            str(source): int(count)
            for source, count in frame["source"].value_counts(dropna=False).items()
        }
        if len(frame) <= 250_000:
            report = audit_ohlcv_frame(
                frame,
                expected_timeframe=record.timeframe,
                require_closed=require_closed,
                session_policy=OHLCVSessionPolicy.CONTINUOUS_24_7,
            )
            pandas_blockers = {
                "duplicate_rows": report.duplicate_rows,
                "open_rows": report.open_rows,
                "timeframe_mismatches": report.timeframe_mismatches,
                "schema_errors": list(report.schema_errors),
                "unexpected_intervals": report.unexpected_intervals,
            }
            if contiguous:
                pandas_blockers["missing_bars"] = report.missing_bars
            if any(bool(value) for value in pandas_blockers.values()):
                raise ValueError(f"dataset {dataset_id} is not trusted: {pandas_blockers}")
            audit = {**audit, **report.to_dict(), "quality_status": "PASS", "trusted": True}
    later_fp = resolve_parquet_inventory_fingerprint(
        record.absolute_root(layout),
        cache_dir=_audit_cache_dir(layout) if resolved_mode is FingerprintMode.FAST_METADATA else None,
        expected=parquet_fingerprint,
        mode=resolved_mode,
    )
    if later_fp != parquet_fingerprint:
        raise ValueError(
            f"dataset {dataset_id} input changed during trusted load: "
            f"start={parquet_fingerprint} end={later_fp}"
        )
    if should_materialize and not frame.empty and record.timeframe:
        audit = dict(audit)
        audit["gap_intervals"] = [
            {
                "symbol": interval.symbol,
                "prev_ts": interval.prev_ts.isoformat(),
                "next_ts": interval.next_ts.isoformat(),
                "missing_bars": interval.missing_bars,
                "aligned": interval.aligned,
                "listing_evidence": interval.listing_evidence,
            }
            for interval in symbol_gap_intervals(frame, record.timeframe)
        ]
        if symbol:
            segs = contiguous_segments(frame.loc[frame["symbol"].eq(symbol), "ts"], record.timeframe)
            audit["contiguous_segments"] = [
                {"start_utc": start.isoformat(), "end_utc": end.isoformat(), "bars": count}
                for start, end, count in segs
            ]
    loaded = frame.copy()
    loaded.attrs["dataset_manifest"] = manifest
    loaded.attrs["ohlcv_audit"] = audit
    loaded.attrs["source_counts"] = source_counts
    loaded.attrs["coverage"] = coverage
    return TrustedLoad(
        frame=loaded,
        record=record,
        manifest=manifest,
        audit=audit,
        source_counts=source_counts,
        coverage=coverage,
        materialized=should_materialize,
        verified_parquet_files=tuple(files),
        verified_identity=verified_identity,
    )


def read_published_manifest(record: DatasetRecord, layout: DataLakeLayout) -> dict[str, Any] | None:
    path = record.absolute_root(layout) / DATASET_MANIFEST_FILENAME
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def symbol_gap_intervals(frame: pd.DataFrame, timeframe: str) -> list:
    if frame.empty or "symbol" not in frame.columns or "ts" not in frame.columns:
        return []
    intervals = []
    for symbol, group in frame.groupby("symbol", dropna=False):
        intervals.extend(gap_intervals_from_timestamps(str(symbol), group["ts"], timeframe))
    return intervals


def load_trusted_research_dataset(
    dataset_id: str,
    *,
    layout: DataLakeLayout,
    requested_scope: DatasetScope,
    end: pd.Timestamp | str,
    gap_policy: GapPolicy,
    symbol: str | None = None,
    start: pd.Timestamp | str | None = None,
    **kwargs: Any,
) -> TrustedLoad:
    if gap_policy not in {"reject", "contiguous_segments"}:
        raise ValueError("research gap_policy must be reject or contiguous_segments")
    return load_trusted_dataset(
        dataset_id,
        layout=layout,
        requested_scope=requested_scope,
        symbol=symbol,
        start=start,
        end=end,
        purpose="research",
        gap_policy=gap_policy,
        fingerprint_mode=FingerprintMode.STRICT_CONTENT,
        **kwargs,
    )


def read_verified_ohlcv(
    loaded: TrustedLoad,
    *,
    symbol: str | None = None,
    start: pd.Timestamp | str | None = None,
    end: pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    """Re-read verified parquet files with the same closed-bar cutoff as catalog."""

    if not loaded.verified_parquet_files:
        raise ValueError("trusted load has no verified parquet files")
    start_ts = _as_utc(start, field="start")
    end_ts = _as_utc(end, field="end")
    if end_ts is None:
        raise ValueError("read_verified_ohlcv requires the same explicit closed-bar cutoff")
    return _load_selected_frame(
        loaded.record,
        list(loaded.verified_parquet_files),
        symbol=symbol,
        start=start_ts,
        end=end_ts,
    )
