"""Isolated synthetic contract checks; never production research evidence."""

import copy
import importlib.util
import json
from pathlib import Path
import pandas as pd
import pytest
from strategy_lab.data.market_coverage import MarketCoverageValidator
from strategy_lab.knowledge.market_contract import (
    ContractMismatch,
    check_contract_binding,
    reviewed_rights,
    sha,
)
from strategy_lab.knowledge.candidates import digest
from test_quantgraph_market_v3 import sample, engine as previous_engine

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("tail", "PARTIAL"),
        ("middle", "PARTIAL"),
        ("duplicate", "INVALID"),
        ("order", "INVALID"),
        ("none", "VERIFIED"),
    ],
)
def test_complete_crypto_coverage(mutation, expected):
    ts = list(pd.date_range("2025-01-01", periods=12, freq="4h", tz="UTC"))
    if mutation == "tail":
        ts = ts[:-2]
    if mutation == "middle":
        del ts[4]
    if mutation == "duplicate":
        ts.insert(4, ts[4])
    if mutation == "order":
        ts[3], ts[4] = ts[4], ts[3]
    result = MarketCoverageValidator().validate(
        ts,
        requested_start="2025-01-01T00:00:00Z",
        requested_end="2025-01-03T00:00:00Z",
        frequency="4h",
        calendar="CRYPTO_24_7",
    )
    assert result["coverage_status"] == expected
    assert result["expected_count"] == 12
    assert result["actual_count"] == len(ts)


def test_stock_sessions_skip_weekends_holiday_but_include_half_day():
    # Thanksgiving closed; Friday half-day still counts as one daily session.
    ts = pd.to_datetime(["2025-11-26", "2025-11-28", "2025-12-01"], utc=True)
    result = MarketCoverageValidator().validate(
        ts,
        requested_start="2025-11-26T00:00:00Z",
        requested_end="2025-12-02T00:00:00Z",
        frequency="1d",
        calendar="XNYS",
    )
    assert result["coverage_status"] == "VERIFIED"
    assert result["expected_count"] == 3
    assert result["calendar_version"].startswith("exchange-calendars-")


def test_unknown_calendar_is_not_covered():
    result = MarketCoverageValidator().validate(
        [],
        requested_start="2025-01-01T00:00:00Z",
        requested_end="2025-01-03T00:00:00Z",
        frequency="4h",
        calendar="UNKNOWN",
    )
    assert result["coverage_status"] == "UNKNOWN"


@pytest.mark.parametrize(
    "field",
    [
        "parameters",
        "parameter_grid",
        "is_start",
        "oos_start",
        "fees_bps",
        "slippage_bps",
        "requested_start",
        "requested_end",
        "execution_contract",
    ],
)
def test_downloaded_contract_mutation_fails_before_replay(tmp_path, field):
    # Binding check must precede parsing, so even otherwise valid mutations fail.
    path = tmp_path / "contract.json"
    path.write_text(json.dumps({field: "before"}))
    manifest = {"contract_sha256": sha(path)}
    path.write_text(json.dumps({field: "after"}))
    with pytest.raises(ContractMismatch, match="ContractMismatch"):
        check_contract_binding(path, manifest)


def rights_fixture(tmp_path):
    evidence = tmp_path / "review.md"
    evidence.write_text("Synthetic license fixture, isolated unit test only.")
    value = dict(
        schema_version="reviewed-rights-v4",
        rights_id="unit-only",
        provider="unit",
        source="unit",
        scope="MARKET_DATA",
        research_use_allowed=True,
        research_use_scope="PRIVATE_INTERNAL_RESEARCH",
        commercial_use_allowed=None,
        redistribution_allowed=False,
        derivative_allowed=True,
        attribution_required=False,
        attribution=None,
        license_source="unit-only",
        license_url="https://example.org/unit",
        reviewed_at="2026-01-01T00:00:00Z",
        reviewed_by="unit",
        confidence="HIGH",
        status="VERIFIED",
        evidence_path="review.md",
        evidence_sha256=sha(evidence),
        rationale="Unit only",
    )
    path = tmp_path / "rights.json"
    path.write_text(json.dumps(value))
    return path, value


def test_reviewed_rights_independent_permissions_and_hash(tmp_path):
    path, value = rights_fixture(tmp_path)
    result = reviewed_rights(
        path,
        provider="unit",
        source="unit",
        use_context="PRIVATE_INTERNAL_RESEARCH",
        expected_id="unit-only",
        expected_sha=digest(value),
    )
    assert (
        result["commercial_use_allowed"] is None
        and result["redistribution_allowed"] is False
    )
    value["commercial_use_allowed"] = True
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="hash mismatch"):
        reviewed_rights(
            path,
            provider="unit",
            source="unit",
            use_context="PRIVATE_INTERNAL_RESEARCH",
            expected_sha="0" * 64,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("research_use_allowed", None),
        ("scope", "IMPLEMENTATION_CODE"),
        ("status", "REVIEW_REQUIRED"),
        ("research_use_scope", "PERSONAL_NONCOMMERCIAL"),
        ("provider", "other"),
    ],
)
def test_rights_unknown_scope_and_personal_do_not_authorize_business(
    tmp_path, field, value
):
    path, rights = rights_fixture(tmp_path)
    rights[field] = value
    path.write_text(json.dumps(rights))
    with pytest.raises(ValueError):
        reviewed_rights(
            path,
            provider="unit",
            source="unit",
            use_context="PRIVATE_INTERNAL_RESEARCH",
        )


def test_rights_evidence_tampering_and_missing_file_reject(tmp_path):
    path, _ = rights_fixture(tmp_path)
    (tmp_path / "review.md").write_text("changed")
    with pytest.raises(ValueError, match="supporting evidence hash"):
        reviewed_rights(
            path,
            provider="unit",
            source="unit",
            use_context="PRIVATE_INTERNAL_RESEARCH",
        )
    with pytest.raises(FileNotFoundError):
        reviewed_rights(
            tmp_path / "missing",
            provider="unit",
            source="unit",
            use_context="PRIVATE_INTERNAL_RESEARCH",
        )


def test_exposure_fix_keeps_all_accounting_and_fills_identical():
    spec = importlib.util.spec_from_file_location(
        "market_v2_test",
        ROOT / "research/_shared-kernels/quantgraph-market/v2/engine.py",
    )
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    bars, contract = sample()
    for bracket in [False, True]:
        c = copy.deepcopy(contract)
        if bracket:
            c.update(stop_loss_fraction=0.1, take_profit_fraction=0.1)
            bars.loc[3, ["open", "close", "high", "low"]] = [70, 72, 73, 69]
        before, f1, t1 = previous_engine.replay(bars, c)
        after, f2, t2 = engine.replay(bars, c)
        pd.testing.assert_frame_equal(f1, f2)
        pd.testing.assert_frame_equal(t1, t2)
        pd.testing.assert_frame_equal(
            before.drop(columns="exposure"),
            after.drop(
                columns=[
                    "exposure",
                    "exposure_duration_lower",
                    "exposure_duration_upper",
                ]
            ),
        )
        open_exits = f2[
            (f2.side == "sell") & f2.reason.isin(["prior_closed_signal", "stop_gap"])
        ]
        assert len(open_exits)
        for ts in open_exits.ts:
            assert after[after.ts == pd.Timestamp(ts)].exposure.iloc[0] == 0
        assert (after.exposure_duration_lower <= after.exposure_duration_upper).all()


def dataset_fixture(tmp_path):
    """Synthetic data restricted to pytest tmp_path; no real journal access."""
    from strategy_lab.knowledge.market_contract import read_contract

    contract_source = (
        ROOT / "research/btc/1d-quantgraph-source-sma/specs/research-contract-v4.json"
    )
    contract_path = tmp_path / "contract.json"
    contract_path.write_bytes(contract_source.read_bytes())
    c = read_contract(contract_path)
    rights_path, rights = rights_fixture(tmp_path)
    rights.update(provider=c["provider"], source=c["source"])
    rights_path.write_text(json.dumps(rights))
    ts = pd.date_range(
        c["requested_start"], c["requested_end"], inclusive="left", freq="1d"
    )
    frame = pd.DataFrame(
        dict(
            ts=ts,
            open=100.0,
            high=102.0,
            low=98.0,
            close=100.0,
            volume=10.0,
            quote_volume=1000.0,
            trade_count=5,
            vwap=100.0,
            is_closed=True,
            exchange=c["provider"],
            symbol=c["symbols"][0],
            market_type="spot",
            timeframe="1d",
            source=c["source"],
        )
    )
    frame.to_json(
        tmp_path / "dataset.jsonl", orient="records", lines=True, date_format="iso"
    )
    (tmp_path / "raw.jsonl").write_bytes((tmp_path / "dataset.jsonl").read_bytes())
    coverage = MarketCoverageValidator().validate(
        ts,
        requested_start=c["requested_start"],
        requested_end=c["requested_end"],
        frequency="1d",
        calendar="CRYPTO_24_7",
    )
    audit = dict(
        status="PASS",
        dataset_sha256=sha(tmp_path / "dataset.jsonl"),
        raw_hashes=[sha(tmp_path / "raw.jsonl")],
    )
    (tmp_path / "audit.json").write_text(json.dumps(audit))
    manifest = {
        k: c[k]
        for k in (
            "provider",
            "source",
            "frequency",
            "symbols",
            "requested_start",
            "requested_end",
        )
    }
    manifest.update(
        contract_sha256=sha(contract_path),
        rights_path="rights.json",
        rights_id=rights["rights_id"],
        rights_sha256=digest(rights),
        raw_files=[dict(path="raw.jsonl", sha256=sha(tmp_path / "raw.jsonl"))],
        dataset_path="dataset.jsonl",
        dataset_sha256=sha(tmp_path / "dataset.jsonl"),
        coverage=coverage,
        real_market_data=True,
        acceptance_status="TRUSTED",
        missing_native_fields=[],
        closure_evidence_status="VERIFIED",
        source_identity_verified=True,
        normalization_audit_path="audit.json",
        normalization_audit_sha256=sha(tmp_path / "audit.json"),
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return contract_path, path, manifest


def test_unchanged_contract_and_full_chain_pass_in_isolated_fixture(tmp_path):
    from strategy_lab.knowledge.market_dataset import read_market_dataset

    contract, path, manifest = dataset_fixture(tmp_path)
    assert check_contract_binding(contract, manifest)["trial_count"] == 3
    bars, _, _, _, coverage = read_market_dataset(contract, path, formal=True)
    assert (
        len(bars) == coverage["expected_count"]
        and coverage["coverage_status"] == "VERIFIED"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "raw_bytes",
        "dataset_bytes",
        "rights_hash",
        "coverage_claim",
        "native_field",
        "unclosed",
        "identity",
        "normalization",
    ],
)
def test_formal_reader_rejects_broken_evidence_chain(tmp_path, fault):
    from strategy_lab.knowledge.market_dataset import read_market_dataset

    contract, path, manifest = dataset_fixture(tmp_path)
    if fault in {"raw_bytes", "dataset_bytes"}:
        (
            tmp_path / ("raw.jsonl" if fault == "raw_bytes" else "dataset.jsonl")
        ).write_text("changed")
    elif fault == "rights_hash":
        manifest["rights_sha256"] = "0" * 64
    elif fault == "coverage_claim":
        manifest["coverage"]["actual_count"] -= 1
    elif fault == "native_field":
        manifest["missing_native_fields"] = ["trade_count"]
    elif fault in {"unclosed", "identity"}:
        frame = pd.read_json(
            tmp_path / "dataset.jsonl", lines=True, convert_dates=False
        )
        frame.loc[0, "is_closed" if fault == "unclosed" else "exchange"] = (
            False if fault == "unclosed" else "unknown-venue"
        )
        frame.to_json(tmp_path / "dataset.jsonl", orient="records", lines=True)
        manifest["dataset_sha256"] = sha(tmp_path / "dataset.jsonl")
    else:
        (tmp_path / "audit.json").write_text("{}")
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        read_market_dataset(contract, path, formal=True)


def test_partial_can_only_use_explicit_private_diagnostic(tmp_path):
    from strategy_lab.knowledge.market_dataset import read_market_dataset

    contract, path, manifest = dataset_fixture(tmp_path)
    frame = pd.read_json(
        tmp_path / "dataset.jsonl", lines=True, convert_dates=False
    ).iloc[:-1]
    frame.to_json(tmp_path / "dataset.jsonl", orient="records", lines=True)
    manifest["dataset_sha256"] = sha(tmp_path / "dataset.jsonl")
    manifest["coverage"] = MarketCoverageValidator().validate(
        pd.to_datetime(frame.ts, utc=True),
        requested_start=manifest["requested_start"],
        requested_end=manifest["requested_end"],
        frequency="1d",
        calendar="CRYPTO_24_7",
    )
    path.write_text(json.dumps(manifest))
    assert (
        read_market_dataset(contract, path, formal=False)[4]["coverage_status"]
        == "PARTIAL"
    )
    with pytest.raises(ValueError, match="VERIFIED coverage"):
        read_market_dataset(contract, path, formal=True)


def test_admitted_contract_pins_are_checked_before_account_computation(tmp_path):
    from strategy_lab.knowledge.market_contract import validate_candidate_binding

    contract_path, manifest_path, manifest = dataset_fixture(tmp_path)
    contract = json.loads(contract_path.read_text())
    row = dict(
        candidate_gate=dict(
            gate_version="research-candidate-gate-v4", status="ELIGIBLE", eligible=True
        ),
        variant={
            k: contract[k]
            for k in (
                "strategy_concept_id",
                "strategy_template_id",
                "strategy_variant_id",
                "rule_ast",
            )
        },
        reviewed_evidence=dict(
            schema_version="evidence-enrichment-v4",
            execution=contract["execution_contract"],
            derived_data_requirement=contract["data_requirements"],
            data_requirement=dict(dataset_hash=manifest["dataset_sha256"]),
            dataset_binding=dict(
                contract_sha256=sha(contract_path),
                dataset_manifest_sha256=sha(manifest_path),
                rights_id=manifest["rights_id"],
                rights_sha256=manifest["rights_sha256"],
            ),
        ),
    )
    kwargs = dict(
        contract_sha256=sha(contract_path), manifest_sha256=sha(manifest_path)
    )
    validate_candidate_binding(row, contract, manifest, **kwargs)
    for key in (
        "contract_sha256",
        "dataset_manifest_sha256",
        "rights_sha256",
        "rights_id",
    ):
        bad = copy.deepcopy(row)
        bad["reviewed_evidence"]["dataset_binding"][key] = "wrong"
        with pytest.raises(ContractMismatch):
            validate_candidate_binding(bad, contract, manifest, **kwargs)
    row["candidate_gate"]["gate_version"] = "research-candidate-gate-v3"
    with pytest.raises(ValueError, match="ELIGIBLE V4"):
        validate_candidate_binding(row, contract, manifest, **kwargs)
