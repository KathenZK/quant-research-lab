"""ResearchIntegrityAssessment/v1: conclusion strength, separate from computation.

No historical result, contract or dataset is rewritten by this module. A
documented protocol is evidence about known records, never proof that a person
has not seen prices elsewhere. Missing fields withhold stronger conclusions.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path

from .accounting import digest, utc
from .exposure import overlaps
from .trials import valid_snapshot

VERSION = "ResearchIntegrityAssessment/v1"
STUDY_KINDS = {"HISTORICAL_REPLICATION", "EXPLORATORY_ANALYSIS", "CONFIRMATORY_HOLDOUT_TEST"}
BOUNDARY = ("Automatic checks cover recorded chronology, fingerprints, known access and recorded uses only. "
            "They cannot prove a researcher never saw market data elsewhere or that the journal is complete.")


def assess_holdout(contract, *, evidence=None, exposure_records=(), dataset_fingerprint=None):
    out = dict(status="UNKNOWN", evidence=evidence or {}, known_exposures=[],
               plan_frozen_at=contract.get("frozen_at"), use_count=None, max_uses=None,
               reasons=[], automatic_verification_boundary=BOUNDARY)
    if contract.get("holdout_status") == "RETROSPECTIVE_PREVIOUSLY_OBSERVED":
        out.update(status="OBSERVED", reasons=["Contract records previously observed history"])
    try:
        if contract.get("oos_start") and contract.get("oos_end"):
            out["known_exposures"] = overlaps(list(exposure_records), start=contract["oos_start"], end=contract["oos_end"])
            if out["known_exposures"]:
                out.update(status="OBSERVED", reasons=out["reasons"] + ["Known exposure overlaps the holdout window"])
        if not evidence or not evidence.get("plan_record"):
            out["reasons"].append("No independently retained plan/use evidence; UNOBSERVED_AT_FREEZE alone is a claim")
            return out
        receipt = evidence["plan_record"]
        plan = receipt["data"]["plan"]
        uses = evidence.get("use_records", [])
        related = evidence.get("related_plans", [receipt])
        out.update(plan_frozen_at=plan["plan_frozen_at"], use_count=len(uses), max_uses=plan["max_uses"])
        if any(r["data"]["plan"].get("known_access_records") for r in related):
            out.update(status="OBSERVED", reasons=out["reasons"] + ["Retained plan contains known prior access/research"])
        if out["status"] == "OBSERVED":
            return out
        if len(uses) > plan["max_uses"] or len(uses) > 1:
            out.update(status="REUSED", reasons=["Recorded sample usage exceeds single confirmation or frozen limit"])
            return out
        tests = {
            "frozen contract binding": plan["contract_hash"] == digest(contract),
            "dataset and sample identity": bool(plan["dataset_version"]) and bool(plan["sample_fingerprint"])
                and plan["sample_start"] == contract.get("oos_start") and plan["sample_end"] == contract.get("oos_end"),
            "freeze chronology": utc(plan["plan_frozen_at"]) == utc(contract["frozen_at"])
                and utc(plan["plan_frozen_at"]) <= utc(receipt["registered_at"]) < utc(plan["sample_start"]),
            "supported protocol": plan["protocol"] == "PROSPECTIVE_AFTER_FREEZE_SINGLE_USE" and plan["max_uses"] == 1,
            "known access review": plan["access_history_status"] == "KNOWN_RECORDS_REVIEWED" and bool(plan["evidence_refs"]),
            "recorded validation use": len(uses) == 1 and utc(uses[0]["registered_at"]) >= utc(plan["sample_end"]),
            "realized dataset binding": bool(dataset_fingerprint) and len(uses) == 1
                and uses[0]["data"]["dataset_fingerprint"] == dataset_fingerprint,
        }
        out["reasons"] = ["Not established: " + k for k, v in tests.items() if not v]
        if all(tests.values()):
            out["status"] = "DOCUMENTED_PROSPECTIVE_PROTOCOL"
    except (KeyError, ValueError, TypeError) as exc:
        out["reasons"].append("Incomplete/invalid holdout evidence: " + str(exc))
    return out


def assess_research_integrity(*, study_kind=None, contract=None, selection_scope=None,
                              statistical_methods=None, holdout_evidence=None,
                              exposure_records=(), dataset_fingerprint=None):
    """Stable package API for task A and other callers; no research-script import.

    Historical reproducibility is permitted regardless of holdout freshness.
    Independent confirmation needs a documented prospective protocol, a scoped
    registry and applicable decision-support statistics. It is not promotion.
    """
    contract = contract or {}
    kind = study_kind if study_kind in STUDY_KINDS else "EXPLORATORY_ANALYSIS"
    scope = selection_scope or {}
    methods = statistical_methods or {}
    holdout = assess_holdout(contract, evidence=holdout_evidence, exposure_records=exposure_records,
                             dataset_fingerprint=dataset_fingerprint)
    blockers, warnings = [], [BOUNDARY]
    if study_kind not in STUDY_KINDS:
        warnings.append("Study kind missing/unknown; defaulted to exploratory")
    level = "REPRODUCIBLE_HISTORICAL_RESULT" if kind == "HISTORICAL_REPLICATION" else "EXPLORATORY_RESULT"
    if kind == "CONFIRMATORY_HOLDOUT_TEST":
        if holdout["status"] != "DOCUMENTED_PROSPECTIVE_PROTOCOL":
            blockers.append("HOLDOUT_EVIDENCE_NOT_CONFIRMATORY")
        if (not valid_snapshot(scope)
                or scope.get("history_completeness") != "COMPLETE_DECLARED" or scope.get("uncertain_attempt_ids")):
            blockers.append("SELECTION_SCOPE_INCOMPLETE_OR_UNKNOWN")
        for name in ("dsr", "pbo"):
            m = methods.get(name, {})
            if (m.get("status") != "COMPUTED" or m.get("applicability_status") != "APPLICABLE"
                    or m.get("decision_use") != "DECISION_SUPPORT" or m.get("method_version") != "research-statistics/v1"
                    or m.get("method") != {"dsr": "DSR_BAILEY_2014_EQ2", "pbo": "CSCV_FIXED_RETURNS"}[name]):
                blockers.append(name.upper() + "_NOT_DECISION_EVIDENCE")
        dsr_scope = methods.get("dsr", {}).get("selection_scope", {})
        if not scope.get("scope_sha256") or dsr_scope.get("scope_sha256") != scope.get("scope_sha256"):
            blockers.append("DSR_SELECTION_SCOPE_MISMATCH")
        if not scope.get("scope_sha256") or methods.get("pbo", {}).get("selection_scope_sha256") != scope.get("scope_sha256"):
            blockers.append("PBO_SELECTION_SCOPE_MISMATCH")
        if not blockers:
            level = "INDEPENDENT_CONFIRMATION_UNDER_RECORDED_PROTOCOL"
    else:
        warnings.append("Historical/exploratory results do not establish independent confirmation of a new discovery")
    result = dict(assessment_version=VERSION, study_kind=kind, registry_selection_scope=scope,
                holdout_evidence_status=holdout["status"], holdout=holdout,
                statistical_methods_applicability=methods, permitted_conclusion_level=level,
                blockers=blockers, warnings=warnings, computation_permitted=True,
                promotion_allowed=False)
    # Detach caller-owned dicts: later mutations cannot silently change an assessment.
    result = json.loads(json.dumps(result, allow_nan=False))
    result["assessment_sha256"] = digest(result)
    return result


def adjudicate_research(result, assessment=None):
    """Compatibility decision with fixed existing thresholds, not a new gate.

    RESEARCH_PASSED now means the recorded confirmatory requirements passed.
    NOT_APPLICABLE is neither numeric success nor proof of economic failure.
    """
    oos = result.get("oos", {})
    counts = [oos.get("observations"), oos.get("closed_trades")]
    if any(type(v) is not int or v < minimum for v, minimum in zip(counts, (3, 30))):
        return "INCONCLUSIVE"
    values = [oos.get(k) for k in ("total_return", "sharpe", "max_drawdown")]
    if any(type(v) not in {float, int} or not math.isfinite(v) for v in values):
        return "INCONCLUSIVE"
    ret, sr, dd = values
    if ret <= 0 or sr <= 0 or dd > .3:
        return "RESEARCH_FAILED"
    if (not assessment or assessment.get("assessment_version") != VERSION or assessment.get("blockers")
            or assessment.get("permitted_conclusion_level") != "INDEPENDENT_CONFIRMATION_UNDER_RECORDED_PROTOCOL"):
        return "INCONCLUSIVE"
    if assessment.get("assessment_sha256") != digest({k: v for k, v in assessment.items() if k != "assessment_sha256"}):
        return "INCONCLUSIVE"
    for name, key, predicate in (("dsr", "deflated_sharpe", lambda x: x >= .95),
                                  ("pbo", "pbo", lambda x: x <= .1)):
        m = result.get(key, {})
        if digest(m) != digest(assessment.get("statistical_methods_applicability", {}).get(name)):
            return "INCONCLUSIVE"
        if (m.get("status") != "COMPUTED" or m.get("applicability_status") != "APPLICABLE"
                or m.get("decision_use") != "DECISION_SUPPORT"):
            return "INCONCLUSIVE"
        value = m.get("value")
        if type(value) not in {float, int} or not math.isfinite(value) or not 0 <= value <= 1:
            return "INCONCLUSIVE"
        if not predicate(value):
            return "RESEARCH_FAILED"
    return "RESEARCH_PASSED"


def write_assessment_revision(path, *, original_result_path, assessment, research_status):
    """Create a linked revision exclusively. Never rewrite a frozen artifact."""
    from hashlib import sha256

    original = Path(original_result_path)
    revision = dict(assessment_version=VERSION, assessed_at=datetime.now(timezone.utc).isoformat(),
                    original_result_uri=str(original.resolve()), original_result_sha256=sha256(original.read_bytes()).hexdigest(),
                    assessment=assessment, research_status=research_status)
    revision["revision_id"] = "integrity-" + digest(revision)
    with Path(path).open("x", encoding="utf-8") as f:
        f.write(json.dumps(revision, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return revision
