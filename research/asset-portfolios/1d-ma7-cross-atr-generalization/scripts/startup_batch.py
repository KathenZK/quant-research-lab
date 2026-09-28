"""Versioned, price-only startup context for one immutable explicit market scope.

Uses the existing validators and verified-file reader without modifying them.
Only their exact no-complete-window error becomes a structured symbol result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from strategy_lab.data import catalog as catalog_module
from strategy_lab.data import research_bundle as original_startup
from strategy_lab.data.catalog import (
    DatasetScope, load_trusted_research_dataset, read_verified_ohlcv,
    require_passing_trusted, resolve_dataset,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import sha256_canonical, sha256_file
from strategy_lab.data.research_bundle import (
    base_report, local_path, read_bundle_contract, validate_price_frame,
    validate_request, verify_bundle_files,
)


@dataclass
class BatchStartupContext:
    project_root: Path
    data_root: Path
    bundle: dict
    pin: dict
    verified_components: dict
    symbols: tuple[str, ...]
    start: str
    end: str
    source_hashes: dict
    created_utc: str
    loaded: dict = field(default_factory=dict)
    catalog_receipts: dict = field(default_factory=dict)

    def receipt(self):
        return {"status": "PRICE_BATCH_CONTEXT_VERIFIED_NOT_ALL_SYMBOLS_APPROVED",
                **self.pin, "created_utc": self.created_utc,
                "symbols": list(self.symbols), "start": self.start, "end": self.end,
                "verified_components": self.verified_components,
                "source_hashes": self.source_hashes, "catalog_receipts": self.catalog_receipts,
                "funding_window_verified": False, "pit_universe_proven": False,
                "bundle_content_verifications": 1}


@dataclass
class BatchStartupResult:
    prices: dict[str, pd.DataFrame]
    failures: dict[str, str]
    report: dict


def create_startup_context(*, project_root: Path, data_root: Path, pin: dict,
                           symbols: list[str], start: str, end: str) -> BatchStartupContext:
    bundle, frozen_pin = read_bundle_contract(project_root, pin=pin)
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("Batch context needs an explicit unique universe")
    for tf, backward in (("1d", 29), ("1h", 1)):
        validate_request({"schema_version": 1, **frozen_pin, "mode": "price_diagnostic",
                          "timeframe": tf, "symbols": symbols, "start": start, "end": end,
                          "gap_policy": "contiguous_segments", "asset_policy": "crypto_only",
                          "backward_bars": backward, "forward_bars": 0}, bundle)
    lake = data_root.resolve()
    verified = verify_bundle_files(bundle, data_root=lake)
    source_hashes = {
        "batch_startup_sha256": sha256_file(Path(__file__)),
        "startup_core_sha256": sha256_file(Path(original_startup.__file__)),
        "catalog_sha256": sha256_file(Path(catalog_module.__file__)),
        **bundle["frozen_readers"],
    }
    return BatchStartupContext(project_root.resolve(), lake, bundle, frozen_pin, verified,
                               tuple(symbols), start, end, source_hashes,
                               datetime.now(timezone.utc).isoformat())


def _scope_token(context: BatchStartupContext, request: dict):
    tf = request["timeframe"]
    if tf in context.loaded:
        return context.loaded[tf]
    lake = context.data_root
    layout = DataLakeLayout(root_dir=lake, raw_dir=lake / "raw", normalized_dir=lake / "normalized",
                           features_dir=lake / "features", cache_dir=lake / "cache", derived_dir=lake / "derived")
    component = context.bundle["components"][tf]
    record = resolve_dataset(component["dataset_id"], layout=layout)
    if record.absolute_root(layout).resolve() != local_path(lake, component["root"]):
        raise ValueError("Catalog root differs from frozen bundle")
    loaded = require_passing_trusted(load_trusted_research_dataset(
        component["dataset_id"], layout=layout, requested_scope=DatasetScope.FULL_MARKET,
        start=pd.Timestamp(context.start), end=pd.Timestamp(context.end),
        gap_policy="contiguous_segments", max_materialize_rows=0))
    context.loaded[tf] = loaded
    receipt = {"dataset_id": component["dataset_id"], "start": context.start, "end": context.end,
               "manifest_sha256": component["manifest_sha256"],
               "parquet_inventory_fingerprint": component["parquet_inventory_fingerprint"],
               "verified_identity": loaded.verified_identity,
               "audit": loaded.audit, "materialized": loaded.materialized,
               "verified_parquet_files": [str(p.relative_to(lake)) for p in loaded.verified_parquet_files],
               "fingerprint_mode": "STRICT_CONTENT", "gap_policy": "contiguous_segments"}
    receipt["scope_token_sha256"] = sha256_canonical(receipt)
    context.catalog_receipts[tf] = receipt
    return loaded


def require_research_startup_batch(request: dict, *, context: BatchStartupContext) -> BatchStartupResult:
    """Return individually approved frames, exact unavailable symbols, and both statuses."""
    if {key: request.get(key) for key in context.pin} != context.pin:
        raise ValueError("Batch request changed frozen bundle pin")
    validate_request(request, context.bundle)
    if (request["mode"] != "price_diagnostic" or request["asset_policy"] != "crypto_only"
            or request["gap_policy"] != "contiguous_segments"
            or request["timeframe"] not in {"1d", "1h"}
            or request["start"] != context.start or request["end"] != context.end
            or not set(request["symbols"]).issubset(context.symbols)
            or request["forward_bars"] != 0
            or request["backward_bars"] != (29 if request["timeframe"] == "1d" else 1)):
        raise ValueError("Batch request escapes its exact frozen price scope")
    loaded = _scope_token(context, request)
    prices, stats, failures, statuses = {}, {}, {}, {}
    for symbol in request["symbols"]:
        frame = read_verified_ohlcv(loaded, symbol=symbol,
                                   start=pd.Timestamp(request["start"]), end=pd.Timestamp(request["end"]))
        try:
            approved, stat = validate_price_frame(frame, request, symbol, [])
        except ValueError as exc:
            if str(exc) != f"{symbol}: no complete eligible feature/label window":
                raise
            failures[symbol] = str(exc)
            statuses[symbol] = {"status": "NO_USABLE_WINDOW", "error": str(exc),
                                "row_count_before_window_gate": len(frame), "data_returned": False}
            continue
        prices[symbol], stats[symbol] = approved, stat
        statuses[symbol] = {"status": "PRICE_DIAGNOSTIC_INPUTS_VERIFIED", **stat}
    report = base_report("PRICE_DIAGNOSTIC_BATCH_EVALUATED", context.pin)
    report.update(price_inputs_verified=bool(prices), all_requested_symbols_verified=not failures,
                  verified_components=context.verified_components, request=request, symbols=stats,
                  symbol_status=statuses, failures=failures,
                  request_canonical_sha256=sha256_canonical(request),
                  scope_token_sha256=context.catalog_receipts[request["timeframe"]]["scope_token_sha256"],
                  **context.source_hashes,
                  identity_evidence_scope="observed crypto classification only; no historical identity/PIT proof",
                  startup_api_implementation="versioned_batch_context_same_original_validators",
                  original_api_modified=False)
    return BatchStartupResult(prices, failures, report)
