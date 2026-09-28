"""Hash-bound contracts and reviewed rights; fetchers have no grant authority."""

import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from .candidates import digest


class ContractMismatch(ValueError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_schema(value, name):
    schema = json.loads((Path(__file__).parent / (name + ".schema.json")).read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)


def read_contract(path):
    value = json.loads(Path(path).read_text())
    validate_schema(value, "research_contract_v4")
    import pandas as pd

    if (
        not pd.Timestamp(value["requested_start"])
        <= pd.Timestamp(value["is_start"])
        < pd.Timestamp(value["is_end"])
        == pd.Timestamp(value["oos_start"])
        < pd.Timestamp(value["oos_end"])
        == pd.Timestamp(value["requested_end"])
    ):
        raise ValueError("Invalid frozen IS/OOS windows")
    if (
        value["trial_count"] != len(value["parameter_grid"])
        or value["parameters"] not in value["parameter_grid"]
    ):
        raise ValueError("Invalid frozen trial grid")
    config = value["engine_config"]
    if (
        value["signal_timing"],
        value["execution_timing"],
        value["execution_price"],
    ) != ("CLOSED_BAR", "NEXT_BAR_OPEN", "OPEN"):
        raise ContractMismatch(
            "Current replay adapter only supports closed-bar next-open execution"
        )
    ast = value["rule_ast"]
    if config["signal"] != ast.get("signal") or config["parameters"] != ast.get(
        "parameters"
    ):
        raise ContractMismatch("Engine signal/parameters differ from frozen AST")
    for field in ("stop_loss_fraction", "take_profit_fraction"):
        if config.get(field) != ast.get(field):
            raise ContractMismatch("Engine bracket differs from frozen AST")
    costs = value["execution_contract"]["transaction_cost_model"]
    if (
        costs["fee_bps"] != value["fees_bps"]
        or costs["slippage_bps"] != value["slippage_bps"]
    ):
        raise ContractMismatch("Reviewed execution costs differ from frozen contract")
    pairs = {
        "parameters": "parameters",
        "parameter_grid": "parameter_grid",
        "trial_count": "trial_count",
        "requested_start": "requested_start",
        "end_exclusive": "requested_end",
        "evaluation_start": "is_start",
        "oos_start": "oos_start",
        "fee_bps": "fees_bps",
        "slippage_bps": "slippage_bps",
    }
    for key, other in pairs.items():
        if key in {"requested_start", "end_exclusive", "evaluation_start", "oos_start"}:
            matches = pd.Timestamp(config[key]) == pd.Timestamp(value[other])
        else:
            matches = config[key] == value[other]
        if not matches:
            raise ContractMismatch("Engine configuration differs: " + key)
    if (
        config["symbol"] != value["symbols"][0]
        or config["exchange"] != value["provider"]
        or config["minutes"] != {"1d": 1440, "4h": 240}[value["frequency"]]
    ):
        raise ContractMismatch("Engine dataset identity differs")
    return value


def check_contract_binding(contract_path, manifest):
    actual = sha(contract_path)
    if manifest.get("contract_sha256") != actual:
        raise ContractMismatch(
            "ContractMismatch: frozen download contract bytes changed"
        )
    return read_contract(contract_path)


def reviewed_rights(
    path, *, provider, source, use_context, expected_id=None, expected_sha=None
):
    path = Path(path)
    rights = json.loads(path.read_text())
    validate_schema(rights, "reviewed_rights_v4")
    if expected_id is not None and rights["rights_id"] != expected_id:
        raise ValueError("Rights ID mismatch")
    if expected_sha is not None and digest(rights) != expected_sha:
        raise ValueError("Rights artifact hash mismatch")
    if (
        rights["provider"] != provider
        or rights["source"] != source
        or rights["scope"] != "MARKET_DATA"
    ):
        raise ValueError("Rights scope/provider/source mismatch")
    if (
        rights["status"] != "VERIFIED"
        or rights["research_use_allowed"] is not True
        or rights["confidence"] not in {"HIGH", "MEDIUM"}
    ):
        raise ValueError("Research rights not verified")
    if rights["research_use_scope"] not in {use_context, "PRIVATE_INTERNAL_RESEARCH"}:
        raise ValueError("Research use context not permitted")
    if rights["derivative_allowed"] is not True or (
        rights["attribution_required"] is not False and not rights["attribution"]
    ):
        raise ValueError("Derivation/attribution unresolved")
    evidence = path.parent / rights["evidence_path"]
    if sha(evidence) != rights["evidence_sha256"]:
        raise ValueError("Rights supporting evidence hash mismatch")
    return rights


def validate_candidate_binding(
    candidate, contract, manifest, *, contract_sha256, manifest_sha256
):
    gate = candidate.get("candidate_gate", {})
    if (
        gate.get("gate_version") != "research-candidate-gate-v4"
        or gate.get("status") != "ELIGIBLE"
        or gate.get("eligible") is not True
    ):
        raise ValueError(
            "Explicit ELIGIBLE V4 candidate required before formal computation"
        )
    review = candidate["reviewed_evidence"]
    if review.get("schema_version") != "evidence-enrichment-v4":
        raise ValueError("V4 review required")
    for key in ("strategy_concept_id", "strategy_template_id", "strategy_variant_id"):
        if contract[key] != candidate["variant"][key]:
            raise ContractMismatch(
                "Frozen strategy identity differs from admitted candidate"
            )
    if (
        contract["rule_ast"] != candidate["variant"]["rule_ast"]
        or contract["execution_contract"] != review["execution"]
        or contract["data_requirements"] != review["derived_data_requirement"]
    ):
        raise ContractMismatch("Admitted rules/execution/data requirement mismatch")
    expected = dict(
        contract_sha256=contract_sha256,
        dataset_manifest_sha256=manifest_sha256,
        rights_id=manifest["rights_id"],
        rights_sha256=manifest["rights_sha256"],
    )
    if any(review["dataset_binding"][k] != value for k, value in expected.items()):
        raise ContractMismatch("Admitted dataset/contract/rights binding mismatch")
    if review["data_requirement"]["dataset_hash"] != manifest["dataset_sha256"]:
        raise ContractMismatch("Admitted dataset hash mismatch")
