from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
BASE_SCRIPT = ROOT / (
    "research/asset-portfolios/1d-ma7-rsi6-direction-aligned-pooled-ml/"
    "scripts/sync_binance_pooled_p0_data.py"
)
FAMILY_DIR = ROOT / "research/asset-portfolios/1d-ma7-taker-flow-meta-label"
CUTOFF = pd.Timestamp("2025-05-31T00:00:00Z")
CONTRACT = (
    "specs/binance-1d-ma7-tfml-p0e-p1e-"
    "universe-expansion-contract-2026-08-10.md"
)
ARTIFACT_PATH = FAMILY_DIR / (
    "artifacts/p0e_price_data_2026-08-10/p0_data_quality_manifest.json"
)
SYMBOLS = {
    "XRPUSDT": ("XRP", "XRP/USDT:USDT", "xrpusdt"),
    "DOGEUSDT": ("DOGE", "DOGE/USDT:USDT", "dogeusdt"),
    "ADAUSDT": ("ADA", "ADA/USDT:USDT", "adausdt"),
    "LINKUSDT": ("LINK", "LINK/USDT:USDT", "linkusdt"),
    "LTCUSDT": ("LTC", "LTC/USDT:USDT", "ltcusdt"),
    "DOTUSDT": ("DOT", "DOT/USDT:USDT", "dotusdt"),
    "AVAXUSDT": ("AVAX", "AVAX/USDT:USDT", "avaxusdt"),
    "UNIUSDT": ("UNI", "UNI/USDT:USDT", "uniusdt"),
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def embedded_generator_hashes(path: Path) -> set[str]:
    frame = pd.read_parquet(path, columns=["derivation_provenance"])
    hashes: set[str] = set()
    for raw in frame["derivation_provenance"].drop_duplicates():
        provenance = json.loads(str(raw))
        script_sha256 = provenance.get("script_sha256")
        if not isinstance(script_sha256, str) or len(script_sha256) != 64:
            raise RuntimeError(f"P0E embedded provenance is invalid: {path}")
        hashes.add(script_sha256)
    if not hashes:
        raise RuntimeError(f"P0E embedded provenance is empty: {path}")
    return hashes


def build_native_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    expected_symbols = list(SYMBOLS)
    if payload.get("symbols") != expected_symbols:
        raise RuntimeError("P0E price/funding symbol identity mismatch")
    if payload.get("source_endpoints") != {
        "hourly": "/fapi/v1/klines interval=1h",
        "funding": "/fapi/v1/fundingRate",
        "mark": "/fapi/v1/markPriceKlines interval=1h",
    }:
        raise RuntimeError("P0E source endpoint identity mismatch")
    source_cutoff = payload.get(
        "binance_server_time",
        payload.get("cutoff_exclusive"),
    )
    if pd.Timestamp(source_cutoff) != CUTOFF:
        raise RuntimeError("P0E source cutoff mismatch")
    source_blocker_count = int(
        payload.get("source_blocker_count", payload.get("blocker_count", -1))
    )
    if source_blocker_count != 0:
        raise RuntimeError("P0E price/funding blockers remain")

    results = payload.get("results")
    if not isinstance(results, dict) or set(results) != set(expected_symbols):
        raise RuntimeError("P0E result universe mismatch")
    feature_files: dict[str, dict[str, dict[str, Any]]] = {}
    embedded_hashes: set[str] = set()
    for symbol in expected_symbols:
        result = results[symbol]
        if not isinstance(result, dict):
            raise RuntimeError(f"P0E result is invalid: {symbol}")
        paths = result.get("feature_paths")
        if not isinstance(paths, dict) or set(paths) != {
            "hourly",
            "daily",
            "funding",
        }:
            raise RuntimeError(f"P0E feature paths are incomplete: {symbol}")
        boundaries = result.get("research_boundaries", {})
        if pd.Timestamp(boundaries.get("development_end")) >= CUTOFF:
            raise RuntimeError(f"P0E feature boundary crossed cutoff: {symbol}")
        feature_files[symbol] = {}
        for kind, relative in paths.items():
            path = ROOT / str(relative)
            if "hype" in str(path).lower() or not path.is_file():
                raise RuntimeError(f"P0E feature identity is invalid: {path}")
            file_generator_hashes = embedded_generator_hashes(path)
            embedded_hashes.update(file_generator_hashes)
            feature_files[symbol][kind] = {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256_path(path),
                "embedded_generator_sha256": sorted(file_generator_hashes),
            }

    retained_base_sha256 = sha256_path(BASE_SCRIPT)
    generator_source_retained = embedded_hashes == {retained_base_sha256}
    provenance_blockers = []
    if not generator_source_retained:
        provenance_blockers.append(
            {
                "code": "EMBEDDED_GENERATOR_SOURCE_NOT_RETAINED",
                "embedded_generator_sha256": sorted(embedded_hashes),
                "retained_base_sha256": retained_base_sha256,
            }
        )

    return {
        "schema_version": "binance-1d-ma7-tfml-p0e-price-v1",
        "generated_at_utc": payload["generated_at_utc"],
        "family": "BIN-1D-MA7-TFML-P0E",
        "contract": CONTRACT,
        "cutoff_exclusive": CUTOFF.isoformat(),
        "symbols": expected_symbols,
        "source_endpoints": payload["source_endpoints"],
        "sealed_policy": {
            "development_end_exclusive": CUTOFF.isoformat(),
            "holdout_start": CUTOFF.isoformat(),
            "p0_model_consumed_holdout_rows": 0,
        },
        "provenance": {
            "mode": "native-wrapper-audit-of-base-output",
            "wrapper_path": str(Path(__file__).resolve().relative_to(ROOT)),
            "wrapper_sha256": sha256_path(Path(__file__).resolve()),
            "base_path": str(BASE_SCRIPT.relative_to(ROOT)),
            "retained_base_sha256": retained_base_sha256,
            "embedded_generator_sha256": sorted(embedded_hashes),
            "generator_source_retained": generator_source_retained,
            "blockers": provenance_blockers,
        },
        "results": results,
        "feature_files": feature_files,
        "source_blocker_count": source_blocker_count,
        "provenance_blocker_count": len(provenance_blockers),
        "blocker_count": source_blocker_count + len(provenance_blockers),
        "hype_rows_consumed": 0,
        "hype_files_opened": 0,
        "hype_requests_sent": 0,
    }


def write_native_manifest_from_base_payload() -> None:
    payload = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    native = build_native_manifest(payload)
    temporary = ARTIFACT_PATH.with_name(f".{ARTIFACT_PATH.name}.tmp")
    temporary.write_text(
        json.dumps(native, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(ARTIFACT_PATH)


def load_base_module():
    spec = importlib.util.spec_from_file_location(
        "binance_1d_ma7_tfml_p0e_price_base",
        BASE_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise ImportError(BASE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    if any("HYPE" in symbol for symbol in SYMBOLS):
        raise RuntimeError("HYPE source is forbidden")
    base = load_base_module()
    base.SYMBOLS = SYMBOLS
    base.FEATURE_DIR = ROOT / "data/features/binance_1d_ma7_tfml_p0e"
    base.ARTIFACT_DIR = FAMILY_DIR / "artifacts/p0e_price_data_2026-08-10"
    base.SEALED_START = CUTOFF
    base.SEALED_END_EXCLUSIVE = CUTOFF
    base.USER_AGENT = "quant-research-lab-bin-1d-ma7-tfml-p0e/1.0"
    cutoff_ms = int(CUTOFF.timestamp() * 1_000)
    base.server_time_ms = lambda timeout: cutoff_ms
    base.main()
    write_native_manifest_from_base_payload()


if __name__ == "__main__":
    main()
