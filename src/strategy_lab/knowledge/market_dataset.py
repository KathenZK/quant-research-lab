"""Verify byte lineage before any formal replay. No download or permission grant."""

import json
from pathlib import Path
import pandas as pd
from strategy_lab.data.market_coverage import MarketCoverageValidator
from strategy_lab.data.models import DatasetKind
from strategy_lab.data.quality import validate_frame
from .market_contract import check_contract_binding, reviewed_rights, sha


def read_market_dataset(contract_path, manifest_path, *, formal=True):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    contract = check_contract_binding(contract_path, manifest)
    root = manifest_path.parent
    for key in (
        "provider",
        "source",
        "frequency",
        "symbols",
        "requested_start",
        "requested_end",
    ):
        if manifest[key] != contract[key]:
            raise ValueError("Manifest identity differs from contract: " + key)
    rights = reviewed_rights(
        root / manifest["rights_path"],
        provider=contract["provider"],
        source=contract["source"],
        use_context=contract["use_context"],
        expected_id=manifest["rights_id"],
        expected_sha=manifest["rights_sha256"],
    )
    for raw in manifest["raw_files"]:
        if sha(root / raw["path"]) != raw["sha256"]:
            raise ValueError("Raw bytes changed")
    if not manifest["raw_files"]:
        raise ValueError("No raw evidence")
    if sha(root / manifest["dataset_path"]) != manifest["dataset_sha256"]:
        raise ValueError("Dataset bytes changed")
    frame = pd.read_json(
        root / manifest["dataset_path"], lines=True, convert_dates=False
    )
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    coverage = MarketCoverageValidator().validate(
        frame.ts,
        requested_start=contract["requested_start"],
        requested_end=contract["requested_end"],
        frequency=contract["frequency"],
        calendar=contract["data_requirements"]["calendar"],
    )
    if coverage != manifest["coverage"]:
        raise ValueError(
            "Stored coverage differs from independently recomputed coverage"
        )
    if manifest["real_market_data"] is not True:
        raise ValueError("Not real market data")
    if coverage["coverage_status"] == "INVALID":
        raise ValueError("Invalid history: " + coverage["coverage_reason"])
    if formal:
        if coverage["coverage_status"] != "VERIFIED":
            raise ValueError("Formal research requires VERIFIED coverage")
        if (
            manifest["acceptance_status"] != "TRUSTED"
            or manifest["missing_native_fields"]
        ):
            raise ValueError("Formal research requires complete trusted native schema")
        if manifest.get("closure_evidence_status") != "VERIFIED" or not manifest.get(
            "source_identity_verified"
        ):
            raise ValueError("Source identity/closure evidence missing")
        validate_frame(DatasetKind.OHLCV, frame)
        if not frame.is_closed.all():
            raise ValueError("Unclosed candles")
        required = set(contract["data_requirements"]["required_fields"])
        if (
            not required <= set(frame.columns)
            or frame[list(required)].isna().any().any()
        ):
            raise ValueError("Required AST/execution fields missing")
        for key, expected in [
            ("exchange", contract["provider"]),
            ("source", contract["source"]),
            ("symbol", contract["symbols"][0]),
            ("market_type", contract["market_type"]),
            ("timeframe", contract["frequency"]),
        ]:
            if not (frame[key] == expected).all():
                raise ValueError("Dataset row identity mismatch: " + key)
        # A reviewed raw-to-normalized equivalence audit is mandatory. The
        # reader never manufactures absent columns or authorizes a new source.
        audit_path = root / manifest["normalization_audit_path"]
        if sha(audit_path) != manifest["normalization_audit_sha256"]:
            raise ValueError("Normalization audit changed")
        audit = json.loads(audit_path.read_text())
        if (
            audit.get("status") != "PASS"
            or audit.get("dataset_sha256") != manifest["dataset_sha256"]
            or audit.get("raw_hashes") != [r["sha256"] for r in manifest["raw_files"]]
        ):
            raise ValueError("Raw/normalized equivalence not established")
    return frame, contract, manifest, rights, coverage
