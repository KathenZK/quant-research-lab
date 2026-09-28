from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
import hashlib
import json
import re

from strategy_lab.data.fs import atomic_write_text

LINEAGE_INCOMPLETE = "LINEAGE_INCOMPLETE"
CACHE_META_FILENAME = ".cache-meta.json"
DATASET_MANIFEST_FILENAME = "_MANIFEST.json"
DATASET_REGISTRY_FILENAME = "_DATASET_REGISTRY.json"
INPUT_SNAPSHOT_FILENAME = "_INPUT_SNAPSHOT.json"
INPUT_SNAPSHOTS_DIRNAME = "_INPUT_SNAPSHOTS"
CACHE_META_SCHEMA_VERSION = "1.0"
DATASET_MANIFEST_SCHEMA_VERSION = "1.0"
# Canonical publish value for newly written derived manifests.
CANONICAL_DERIVED_QUALITY = "TRUSTED_DERIVED"
# Read-side compatibility: historical manifests may still use the three synonyms.
ACCEPTED_DERIVED_QUALITY = {
    CANONICAL_DERIVED_QUALITY,
    "ACCEPTED",
    "PASS",
    "TRUSTED",
}
ACCEPTED_CACHE_QUALITY = {"OK", "PASS", "ACCEPTED", "TRUSTED", "FRESH", "TRUSTED_DERIVED"}
HISTORICAL_NULL_CUTOFF_DATASET_IDS = frozenset(
    {
        "binance.perp.ohlcv.1h.from_15m.v1",
        "binance.perp.ohlcv.4h.from_15m.v1",
        "binance.perp.ohlcv.1d.from_15m.v1",
    }
)
SAFE_VERSION_RE = re.compile(r"^v[1-9][0-9]*$")
SAFE_SLUG_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
MANIFEST_CONTENT_EXCLUDED_FIELDS = ("generated_at", "content_fingerprint")
REQUIRED_DERIVED_MANIFEST_FIELDS = (
    "schema_version",
    "dataset_id",
    "layer",
    "status",
    "declared_scope",
    "exchange",
    "market_type",
    "timeframe",
    "physical_root",
    "source_adjudication",
    "priority_union_version",
    "aggregation_formula_version",
    "input_dataset_id",
    "input_manifest_sha256",
    "builder_path",
    "builder_sha256",
    "generated_at",
    "file_count",
    "bytes",
    "rows",
    "distinct_business_keys",
    "duplicate_key_rows",
    "symbol_count",
    "rebuildable",
    "rebuild_command",
    "quality_status",
    "content_fingerprint",
    "parquet_inventory_fingerprint",
)
DERIVED_INT_FIELDS = (
    "file_count",
    "bytes",
    "rows",
    "distinct_business_keys",
    "duplicate_key_rows",
    "symbol_count",
)
REQUIRED_CACHE_FIELDS = (
    "schema_version",
    "cache_id",
    "cache_version",
    "physical_root",
    "input_dataset_id",
    "input_manifest_sha256",
    "builder_path",
    "builder_sha256",
    "config_parameter_sha256",
    "generated_at",
    "cutoff_exclusive_utc",
    "rows",
    "distinct_keys",
    "symbols",
    "start_utc",
    "end_utc",
    "duplicate_overlap_resolution",
    "completeness_rules",
    "null_fill_policy",
    "rebuild_command",
    "quality_status",
    "parquet_inventory_fingerprint",
)


class FingerprintMode(StrEnum):
    STRICT_CONTENT = "strict_content"
    FAST_METADATA = "fast_metadata"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode(
        "utf-8"
    )


def sha256_canonical(payload: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(payload))


def write_canonical_json(path: Path, payload: dict[str, Any]) -> Path:
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)
    if not encoded.endswith("\n"):
        encoded += "\n"
    return atomic_write_text(path, encoded, encoding="utf-8")


def parquet_file_stats(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.parquet")):
        if not path.is_file():
            continue
        stat = path.stat()
        rows.append(
            {
                "relpath": path.relative_to(root).as_posix(),
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            }
        )
    return rows


def inventory_signature(rows: list[dict[str, Any]]) -> str:
    return sha256_canonical(
        {
            "files": [
                {
                    "relpath": row["relpath"],
                    "size": int(row["size"]),
                    "mtime_ns": int(row["mtime_ns"]),
                }
                for row in rows
            ]
        }
    )


def parquet_inventory(root: Path, *, compute_hashes: bool = True) -> list[dict[str, Any]]:
    if not compute_hashes:
        return parquet_file_stats(root)
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.parquet")):
        if not path.is_file():
            continue
        stat = path.stat()
        rows.append(
            {
                "relpath": path.relative_to(root).as_posix(),
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
                "sha256": sha256_file(path),
            }
        )
    return rows


def inventory_fingerprint(rows: list[dict[str, Any]]) -> str:
    return sha256_canonical(
        {
            "files": [
                {"relpath": row["relpath"], "size": row["size"], "sha256": row["sha256"]}
                for row in rows
            ]
        }
    )


def resolve_parquet_inventory_fingerprint(
    root: Path,
    *,
    cache_dir: Path | None = None,
    expected: str | None = None,
    mode: FingerprintMode | str = FingerprintMode.STRICT_CONTENT,
) -> str:
    """Return the parquet inventory fingerprint.

    `strict_content` always hashes file bytes. `fast_metadata` may reuse a
    (relpath, size, mtime_ns) cache and is not a content proof.
    """

    resolved_mode = FingerprintMode(mode)
    if resolved_mode is FingerprintMode.STRICT_CONTENT:
        inventory = parquet_inventory(root, compute_hashes=True)
        fingerprint = inventory_fingerprint(inventory)
        if expected is not None and fingerprint != expected:
            raise ValueError(
                f"parquet inventory fingerprint mismatch: expected={expected} actual={fingerprint}"
            )
        return fingerprint

    stats = parquet_file_stats(root)
    signature = inventory_signature(stats)
    cache_path = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"parquet_fp_{sha256_bytes(str(root.resolve()).encode())[:16]}.json"
        if cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload.get("signature") == signature and payload.get("fingerprint"):
                fingerprint = str(payload["fingerprint"])
                if expected is None or fingerprint == expected:
                    return fingerprint
    inventory = parquet_inventory(root, compute_hashes=True)
    fingerprint = inventory_fingerprint(inventory)
    if cache_path is not None:
        write_canonical_json(
            cache_path,
            {
                "root": str(root.resolve()),
                "signature": signature,
                "fingerprint": fingerprint,
                "file_count": len(inventory),
                "bytes": int(sum(int(row["size"]) for row in inventory)),
                "mode": FingerprintMode.FAST_METADATA.value,
                "not_a_content_proof": True,
            },
        )
    if expected is not None and fingerprint != expected:
        raise ValueError(
            f"parquet inventory fingerprint mismatch: expected={expected} actual={fingerprint}"
        )
    return fingerprint


def assert_safe_dataset_version(version: str) -> str:
    if not SAFE_VERSION_RE.fullmatch(version):
        raise ValueError(
            f"illegal dataset version {version!r}; expected vN with N >= 1 and no path characters"
        )
    return version


def assert_safe_derived_slug(slug: str) -> str:
    if not SAFE_SLUG_RE.fullmatch(slug) or ".." in slug or "/" in slug or "\\" in slug:
        raise ValueError(f"illegal derived dataset slug {slug!r}")
    return slug


def manifest_content_fingerprint(payload: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in payload.items()
        if key not in MANIFEST_CONTENT_EXCLUDED_FIELDS
    }
    return sha256_canonical(stable)


def verify_manifest_content_fingerprint(payload: dict[str, Any]) -> str:
    recorded = str(payload.get("content_fingerprint") or "")
    if not recorded or recorded in {LINEAGE_INCOMPLETE, "test"}:
        raise ValueError("manifest content_fingerprint is missing, incomplete, or a test stub")
    actual = manifest_content_fingerprint(payload)
    if actual != recorded:
        raise ValueError(
            f"manifest content fingerprint mismatch: recorded={recorded} recomputed={actual}"
        )
    return actual


def _missing_or_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def assert_derived_manifest_schema(
    payload: dict[str, Any],
    *,
    dataset_id: str | None = None,
) -> None:
    errors: list[str] = []
    for field in REQUIRED_DERIVED_MANIFEST_FIELDS:
        if field not in payload:
            errors.append(f"missing {field}")
            continue
        if field == "cutoff_exclusive_utc":
            continue
        if field in DERIVED_INT_FIELDS:
            if isinstance(payload[field], bool) or not isinstance(payload[field], int):
                errors.append(f"{field} must be int, got {type(payload[field]).__name__}")
            elif int(payload[field]) < 0:
                errors.append(f"{field} must be non-negative")
            continue
        if field == "rebuildable":
            if type(payload[field]) is not bool:
                errors.append("rebuildable must be bool")
            continue
        if _missing_or_blank(payload[field]):
            errors.append(f"{field} is null or blank")
    recorded_id = str(payload.get("dataset_id") or "")
    if dataset_id is not None and recorded_id != dataset_id:
        errors.append(f"dataset_id {recorded_id!r} != {dataset_id!r}")
    cutoff = payload.get("cutoff_exclusive_utc")
    if cutoff is None:
        if recorded_id not in HISTORICAL_NULL_CUTOFF_DATASET_IDS:
            errors.append("cutoff_exclusive_utc is required except for registered historical v1")
    elif not isinstance(cutoff, str) or not cutoff.strip():
        errors.append("cutoff_exclusive_utc must be a non-empty string when present")
    quality = str(payload.get("quality_status") or "")
    if quality not in ACCEPTED_DERIVED_QUALITY:
        errors.append(f"quality_status={quality!r} is not an accepted publish")
    hex64 = re.compile(r"^[0-9a-f]{64}$")
    for field in (
        "content_fingerprint",
        "input_manifest_sha256",
        "builder_sha256",
        "parquet_inventory_fingerprint",
    ):
        value = payload.get(field)
        if isinstance(value, str) and not hex64.fullmatch(value):
            errors.append(f"{field} must be a 64-char sha256 hex digest")
    if errors:
        raise ValueError(f"derived manifest schema rejected: {errors}")


def assert_manifest_matches_record(
    payload: dict[str, Any],
    *,
    dataset_id: str,
    exchange: str,
    market_type: str,
    timeframe: str,
    declared_scope: str | None = None,
    layer: str | None = None,
    status: str | None = None,
    physical_root: Path | None = None,
    input_dataset_id: str | None = None,
) -> None:
    mismatches: list[str] = []
    if str(payload.get("exchange") or "") != exchange:
        mismatches.append(f"exchange {payload.get('exchange')!r} != {exchange!r}")
    if str(payload.get("market_type") or "") != market_type:
        mismatches.append(f"market_type {payload.get('market_type')!r} != {market_type!r}")
    if str(payload.get("timeframe") or "") != timeframe:
        mismatches.append(f"timeframe {payload.get('timeframe')!r} != {timeframe!r}")
    if str(payload.get("dataset_id") or "") != dataset_id:
        mismatches.append(f"dataset_id {payload.get('dataset_id')!r} != {dataset_id!r}")
    if declared_scope is not None and str(payload.get("declared_scope") or "") != declared_scope:
        mismatches.append(
            f"declared_scope {payload.get('declared_scope')!r} != {declared_scope!r}"
        )
    if layer is not None and str(payload.get("layer") or "") != layer:
        mismatches.append(f"layer {payload.get('layer')!r} != {layer!r}")
    if status is not None and str(payload.get("status") or "") != status:
        mismatches.append(f"status {payload.get('status')!r} != {status!r}")
    if input_dataset_id is not None and str(payload.get("input_dataset_id") or "") != input_dataset_id:
        mismatches.append(
            f"input_dataset_id {payload.get('input_dataset_id')!r} != {input_dataset_id!r}"
        )
    if physical_root is not None:
        declared = Path(str(payload.get("physical_root") or ""))
        if declared.resolve() != physical_root.resolve():
            mismatches.append(
                f"physical_root {declared} != actual {physical_root.resolve()}"
            )
    if mismatches:
        raise ValueError(f"manifest identity does not match registry/data: {mismatches}")


def assert_expected_manifest_identity(
    *,
    manifest_sha256: str,
    content_fingerprint: str,
    parquet_inventory_fingerprint: str,
    input_manifest_sha256: str | None,
    expected: dict[str, Any] | None,
) -> None:
    if not expected:
        return
    mapping = {
        "manifest_sha256": manifest_sha256,
        "content_fingerprint": content_fingerprint,
        "parquet_inventory_fingerprint": parquet_inventory_fingerprint,
        "input_manifest_sha256": input_manifest_sha256,
    }
    for key, actual in mapping.items():
        if key in expected and expected[key] is not None and str(expected[key]) != str(actual):
            raise ValueError(
                f"expected manifest identity {key}={expected[key]!r} != actual {actual!r}"
            )


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    schema_version: str
    dataset_id: str
    layer: str
    status: str
    declared_scope: str
    exchange: str
    market_type: str
    timeframe: str
    physical_root: str
    source_adjudication: str
    priority_union_version: str
    aggregation_formula_version: str | None
    input_dataset_id: str | None
    input_manifest_sha256: str
    builder_path: str | None
    builder_sha256: str
    generated_at: str
    cutoff_exclusive_utc: str | None
    start_utc: str | None
    end_utc: str | None
    file_count: int
    bytes: int
    rows: int
    distinct_business_keys: int
    duplicate_key_rows: int
    symbol_count: int
    rebuildable: bool
    rebuild_command: str
    quality_status: str
    content_fingerprint: str
    extra: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        extra = payload.pop("extra") or {}
        payload.update(extra)
        return payload

    def stable_payload(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("generated_at", None)
        payload.pop("content_fingerprint", None)
        return payload

    def with_fingerprint(self) -> "DatasetManifest":
        fingerprint = sha256_canonical(self.stable_payload())
        return DatasetManifest(**{**asdict(self), "content_fingerprint": fingerprint})

    def write(self, path: Path) -> Path:
        return write_canonical_json(path, self.to_dict())


def cache_meta_template(
    *,
    cache_id: str,
    cache_version: str,
    physical_root: str,
    input_dataset_id: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": CACHE_META_SCHEMA_VERSION,
        "cache_id": cache_id,
        "cache_version": cache_version,
        "physical_root": physical_root,
        "input_dataset_id": input_dataset_id,
        "input_manifest_sha256": LINEAGE_INCOMPLETE,
        "builder_path": LINEAGE_INCOMPLETE,
        "builder_sha256": LINEAGE_INCOMPLETE,
        "config_parameter_sha256": LINEAGE_INCOMPLETE,
        "generated_at": LINEAGE_INCOMPLETE,
        "cutoff_exclusive_utc": LINEAGE_INCOMPLETE,
        "rows": None,
        "distinct_keys": None,
        "symbols": None,
        "start_utc": None,
        "end_utc": None,
        "duplicate_overlap_resolution": LINEAGE_INCOMPLETE,
        "completeness_rules": LINEAGE_INCOMPLETE,
        "null_fill_policy": LINEAGE_INCOMPLETE,
        "rebuild_command": LINEAGE_INCOMPLETE,
        "quality_status": "LINEAGE_INCOMPLETE",
        "is_standard_ohlcv": False,
        "rebuildable": True,
    }
    if extra:
        payload.update(extra)
    return payload


def _incomplete_cache_fields(meta: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    for key in REQUIRED_CACHE_FIELDS:
        if key not in meta:
            flags.append(f"missing:{key}")
            continue
        value = meta.get(key)
        if value is None:
            flags.append(f"null:{key}")
            continue
        if isinstance(value, str) and (value.strip() == "" or value == LINEAGE_INCOMPLETE):
            flags.append(f"incomplete:{key}")
    return flags


def assert_cache_sidecar_fresh(
    root: Path,
    *,
    expected_input_manifest_sha256: str | None = None,
    allow_incomplete_lineage: bool = False,
    expected_cache_id: str | None = None,
    expected_cache_version: str | None = None,
    expected_cutoff: str | None = None,
) -> dict[str, Any]:
    meta_path = root / CACHE_META_FILENAME
    if not meta_path.exists():
        raise ValueError(f"cache sidecar missing: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    inventory = parquet_inventory(root, compute_hashes=True)
    actual_fingerprint = inventory_fingerprint(inventory)
    recorded = meta.get("parquet_inventory_fingerprint")
    if recorded != actual_fingerprint:
        raise ValueError(
            "cache parquet inventory does not match sidecar; "
            f"recorded={recorded} actual={actual_fingerprint}"
        )
    incomplete = _incomplete_cache_fields(meta)
    quality = str(meta.get("quality_status") or "")
    if quality in {"STALE", "MISMATCH", "REJECTED"}:
        raise ValueError(f"cache sidecar quality_status={quality}")
    if quality not in ACCEPTED_CACHE_QUALITY and quality != LINEAGE_INCOMPLETE:
        if not allow_incomplete_lineage:
            raise ValueError(f"cache sidecar unknown quality_status={quality!r}")
    if incomplete and not allow_incomplete_lineage:
        raise ValueError(
            "cache sidecar schema/lineage is incomplete and cannot enter a new "
            f"trusted research flow: {incomplete}"
        )
    if expected_input_manifest_sha256 is not None:
        recorded_input = meta.get("input_manifest_sha256")
        if recorded_input in {None, "", LINEAGE_INCOMPLETE}:
            raise ValueError("cache sidecar has LINEAGE_INCOMPLETE input manifest hash")
        if recorded_input != expected_input_manifest_sha256:
            raise ValueError(
                "cache input manifest mismatch: "
                f"{recorded_input} != {expected_input_manifest_sha256}"
            )
    if expected_cache_id is not None and str(meta.get("cache_id") or "") != expected_cache_id:
        raise ValueError(f"cache_id {meta.get('cache_id')!r} != {expected_cache_id!r}")
    if expected_cache_version is not None and str(meta.get("cache_version") or "") != expected_cache_version:
        raise ValueError(
            f"cache_version {meta.get('cache_version')!r} != {expected_cache_version!r}"
        )
    if expected_cutoff is not None and str(meta.get("cutoff_exclusive_utc") or "") != expected_cutoff:
        raise ValueError(
            f"cache cutoff {meta.get('cutoff_exclusive_utc')!r} != {expected_cutoff!r}"
        )
    meta = dict(meta)
    meta["trusted_for_new_research"] = not incomplete and quality in ACCEPTED_CACHE_QUALITY
    meta["restricted_historical_opt_in"] = bool(allow_incomplete_lineage and incomplete)
    return meta


def published_manifest_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob(DATASET_MANIFEST_FILENAME)
        if path.is_file()
    )


def manifest_parquet_fingerprint(payload: dict[str, Any]) -> str | None:
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    return (
        payload.get("parquet_inventory_fingerprint")
        or extra.get("parquet_inventory_fingerprint")
        or None
    )


def assert_published_derived_manifest(
    *,
    dataset_id: str,
    root: Path,
    expected_fingerprint: str | None = None,
    cache_dir: Path | None = None,
    fingerprint_mode: FingerprintMode | str = FingerprintMode.STRICT_CONTENT,
    expected_manifest_identity: dict[str, Any] | None = None,
    exchange: str | None = None,
    market_type: str | None = None,
    timeframe: str | None = None,
    declared_scope: str | None = None,
    layer: str | None = None,
    status: str | None = None,
    input_dataset_id: str | None = None,
) -> dict[str, Any]:
    if "_staging" in root.as_posix().split("/"):
        raise ValueError(f"refusing unpublished staging path: {root}")
    paths = published_manifest_paths(root)
    root_manifest = root / DATASET_MANIFEST_FILENAME
    if not root_manifest.exists():
        raise ValueError(f"published derived manifest missing: {root_manifest}")
    extra_manifests = [path for path in paths if path.resolve() != root_manifest.resolve()]
    if extra_manifests:
        raise ValueError(
            f"dataset {dataset_id} has extra manifest files: "
            f"{[path.as_posix() for path in extra_manifests]}"
        )
    payload = json.loads(root_manifest.read_text(encoding="utf-8"))
    assert_derived_manifest_schema(payload, dataset_id=dataset_id)
    content_fp = verify_manifest_content_fingerprint(payload)
    if exchange is not None and market_type is not None and timeframe is not None:
        assert_manifest_matches_record(
            payload,
            dataset_id=dataset_id,
            exchange=exchange,
            market_type=market_type,
            timeframe=timeframe,
            declared_scope=declared_scope,
            layer=layer,
            status=status,
            physical_root=root,
            input_dataset_id=input_dataset_id,
        )
    stats = parquet_file_stats(root)
    if int(payload.get("file_count") or 0) != len(stats):
        raise ValueError(
            f"dataset {dataset_id} parquet file_count mismatch: "
            f"manifest={payload.get('file_count')} actual={len(stats)}"
        )
    actual_bytes = int(sum(int(row["size"]) for row in stats))
    if int(payload.get("bytes") or 0) != actual_bytes:
        raise ValueError(
            f"dataset {dataset_id} parquet bytes mismatch: "
            f"manifest={payload.get('bytes')} actual={actual_bytes}"
        )
    recorded_fp = manifest_parquet_fingerprint(payload)
    if not recorded_fp:
        raise ValueError(f"dataset {dataset_id} manifest lacks parquet_inventory_fingerprint")
    actual_fp = resolve_parquet_inventory_fingerprint(
        root,
        cache_dir=cache_dir if FingerprintMode(fingerprint_mode) is FingerprintMode.FAST_METADATA else None,
        expected=recorded_fp,
        mode=fingerprint_mode,
    )
    if expected_fingerprint is not None and actual_fp != expected_fingerprint:
        raise ValueError(
            f"dataset {dataset_id} expected parquet fingerprint {expected_fingerprint} "
            f"!= actual {actual_fp}"
        )
    if payload.get("rows") is not None and type(payload["rows"]) is bool:
        raise ValueError("manifest rows must be int, not bool")
    manifest_hash = sha256_file(root_manifest)
    assert_expected_manifest_identity(
        manifest_sha256=manifest_hash,
        content_fingerprint=content_fp,
        parquet_inventory_fingerprint=actual_fp,
        input_manifest_sha256=payload.get("input_manifest_sha256"),
        expected=expected_manifest_identity,
    )
    quality = str(payload.get("quality_status") or "")
    return {
        "dataset_id": dataset_id,
        "manifest_path": str(root_manifest),
        "manifest_sha256": manifest_hash,
        "manifest_file_sha256": manifest_hash,
        "content_fingerprint": content_fp,
        "parquet_inventory_fingerprint": actual_fp,
        "input_manifest_sha256": payload.get("input_manifest_sha256"),
        "input_snapshot_fingerprint": (
            payload.get("input_snapshot_fingerprint") or payload.get("input_manifest_sha256")
        ),
        "builder_path": payload.get("builder_path"),
        "builder_sha256": payload.get("builder_sha256"),
        "aggregation_formula_version": payload.get("aggregation_formula_version"),
        "priority_union_version": payload.get("priority_union_version"),
        "cutoff_exclusive_utc": payload.get("cutoff_exclusive_utc"),
        "start_utc": payload.get("start_utc"),
        "end_utc": payload.get("end_utc"),
        "quality_status": quality,
        "file_count": len(stats),
        "bytes": actual_bytes,
        "rows": payload.get("rows"),
        "symbol_count": payload.get("symbol_count"),
        "fingerprint_mode": FingerprintMode(fingerprint_mode).value,
        "historical_null_cutoff": payload.get("cutoff_exclusive_utc") is None
        and dataset_id in HISTORICAL_NULL_CUTOFF_DATASET_IDS,
        "payload": payload,
    }


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
