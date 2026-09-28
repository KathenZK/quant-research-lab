"""Worker entry point. Paths and executable choices come only from server config."""

from pathlib import Path
import json
from strategy_lab.factor_study.pipeline import digest, freeze, run, write
from strategy_lab.factor_study.registered_trials import RegisteredTrialAdapter


def _get(context, key):
    return context[key] if isinstance(context, dict) else getattr(context, key)


def execute(request: dict, context) -> list[dict]:
    """Execute an approved factor profile; stable job context makes retries resumable.

    context: run_id, server_config, output_dir, registry_path, checkpoint(stage,
    progress), cancelled(). server_config is trusted worker configuration, never
    request content. It pins profile_id/settings/manifest/acquisition_contract/
    graph_root/lab_root/journal. No submitted expression or module is executed.
    """
    cfg = _get(context, "server_config")
    if request.get("status") != "DRAFT" or request.get("study_type") not in {
        "FACTOR_DIAGNOSTIC",
        "STRATEGY_REPLICATION",
        "STRATEGY_EVOLUTION",
    }:
        raise ValueError("Only approved research DRAFTs are supported")
    settings = request.get("requested_settings", {})
    if (
        set(settings) - {"profile_id", "notes"}
        or settings.get("profile_id") != cfg["profile_id"]
    ):
        raise ValueError("Request must select the approved server profile only")
    if request["study_type"] != "FACTOR_DIAGNOSTIC":
        return execute_strategy(request, context)
    from quantgraph import FactorDB
    from quantgraph.factor_study import definition_identity
    from strategy_lab.factor_study.factors import definition_name

    db = FactorDB(cfg["graph_root"], profile="commercial")
    definitions = []
    for ref in request["entity_refs"]:
        if ref["entity_type"] != "FactorVariant":
            raise ValueError("A concrete factor variant is required")
        v = db.get_variant(ref["entity_id"])
        if definition_identity(v)["definition_revision"] != ref["definition_revision"]:
            raise ValueError("Definition revision changed")
        definitions.append(v)
    names = [definition_name(v) for v in definitions]
    if (
        not names
        or len(set(names)) != len(names)
        or set(names) - set(cfg["settings"]["names"])
    ):
        raise ValueError("Unapproved factor selection")
    root = Path(_get(context, "output_dir")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    binding = {
        "request": request,
        "server_config": cfg,
        "run_id": _get(context, "run_id"),
        "registry_path": str(_get(context, "registry_path")),
    }
    receipt = root / "request-binding.json"
    if receipt.exists():
        if json.loads(receipt.read_text()) != binding:
            raise ValueError("Job inputs changed during retry")
    else:
        write(receipt, binding)
    adapter = RegisteredTrialAdapter(_get(context, "registry_path"))
    plan = root / "study" / "plan.json"
    if not plan.exists():
        if plan.parent.exists():
            raise ValueError(
                "BLOCKED_PARTIAL_FREEZE: retained incomplete freeze; operator must inspect and use a new job, never overwrite evidence"
            )
        approved = {**cfg["settings"], "names": names}
        draft = {
            k: request[k]
            for k in ("schema_version", "entity_refs", "study_type", "status")
        }
        draft.update(request_id=_get(context, "run_id"), requested_settings=approved)
        selection = {
            "request": draft,
            "definitions": definitions,
            "resolved_settings": approved,
        }
        p = root / ("selection-" + digest(selection) + ".json")
        if not p.exists():
            write(p, selection)
        freeze(
            p,
            cfg["manifest"],
            cfg["acquisition_contract"],
            plan.parent,
            graph_root=cfg["graph_root"],
            lab_root=cfg["lab_root"],
            trial_adapter=adapter,
        )
    for i, name in enumerate(names):
        if _get(context, "cancelled")():
            _get(context, "checkpoint")(
                "CANCELLED_BETWEEN_FACTORS", {"completed": i, "total": len(names)}
            )
            return []
        run(
            plan,
            graph_root=cfg["graph_root"],
            lab_root=cfg["lab_root"],
            journal=cfg["journal"],
            only=name,
            trial_adapter=adapter,
        )
        _get(context, "checkpoint")(
            "FACTOR_COMPLETE", {"completed": i + 1, "total": len(names)}
        )
    outcomes = [
        json.loads((plan.parent / "runs" / n / "result.json").read_text())
        for n in names
    ]
    for r in outcomes:
        identity = r["mapping"]["identity"]
        refs = [
            dict(
                entity_type="FactorVariant",
                entity_id=identity["factor_variant_id"],
                definition_revision=identity["definition_revision"],
            )
        ]
        r["study_metadata"] = metadata(
            request["study_type"],
            refs,
            cfg,
            r["limitations"],
            {
                "mapping": r["mapping"],
                "dataset": r["dataset"],
                "contract": r["contract"],
                "code": r["code"],
            },
        )
        r["study_metadata"]["public_summary"]["sample"] = {
            **r["sample"],
            "end": r["sample"]["end_exclusive"],
            "frequency": cfg["settings"]["frequency"],
        }
        r["study_metadata"]["provenance"]["execution_status"] = r["status"]
    return outcomes


def metadata(study_type, refs, cfg, limitations, provenance, lineage=None):
    return dict(
        entity_refs=refs,
        study_type=study_type,
        study_kind="EXPLORATORY_ANALYSIS",
        provenance=provenance,
        limitations=limitations,
        conclusion_level="EXPLORATORY",
        lineage=lineage or [],
        display_policy=cfg.get("display_policy", "bit2me-derived-results-restricted"),
        public_summary={
            "metrics": {},
            "assessment_version": "ResearchIntegrityAssessment/v1",
            "numerical_display": "RESTRICTED_BY_REVIEWED_BIT2ME_TERMS",
            "business_visibility": "PUBLIC",
            "promotion_allowed": False,
        },
    )


def execute_strategy(request, context):
    """Registered method IDs only; strategy assumptions are fixed in campaign.py."""
    from . import campaign

    cfg = _get(context, "server_config")
    catalog = json.loads(Path(cfg["source_catalog"]).read_text())
    byvariant = {r["variant"]["strategy_variant_id"]: r for r in catalog}
    selected = []
    for ref in request["entity_refs"]:
        if ref["entity_type"] != "StrategyVariant":
            raise ValueError("Concrete StrategyVariant required")
        row = byvariant.get(ref["entity_id"])
        if not row or row["variant"]["spec_sha256"] != ref["definition_revision"]:
            raise ValueError("Unknown or changed strategy definition")
        rid = row["variant"]["source_native_id"]
        if rid not in cfg["record_ids"] or rid not in campaign.METHODS:
            raise ValueError("Unregistered strategy implementation")
        selected.append(rid)
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("Unique strategy selection required")
    root = Path(_get(context, "output_dir"))
    root.mkdir(parents=True, exist_ok=True)
    binding = {
        "request": request,
        "server_config": cfg,
        "run_id": _get(context, "run_id"),
        "registry_path": str(_get(context, "registry_path")),
    }
    receipt = root / "request-binding.json"
    if receipt.exists():
        if json.loads(receipt.read_text()) != binding:
            raise ValueError("Job inputs changed during retry")
    else:
        write(receipt, binding)
    study = root / "campaign"
    if not (study / "plan.json").exists():
        if study.exists():
            raise ValueError("BLOCKED_PARTIAL_FREEZE: retained incomplete campaign")
        campaign.freeze(
            cfg["source_catalog"],
            [],
            {
                **cfg,
                "record_ids": selected,
                "registry_path": str(_get(context, "registry_path")),
            },
            study,
            campaign_id=_get(context, "run_id"),
        )
    if _get(context, "cancelled")():
        return []
    campaign.run(study, workers=cfg.get("workers", 1))
    _get(context, "checkpoint")("BASELINES_COMPLETE", {"completed": 1, "total": 2})
    if request["study_type"] == "STRATEGY_EVOLUTION":
        if _get(context, "cancelled")():
            return []
        campaign.freeze_evolution(study)
        campaign.run(study, round_number=1, workers=cfg.get("workers", 1))
    campaign.writeback(study, cfg["journal"])
    outcomes = []
    plan = json.loads((study / "plan.json").read_text())
    for p in sorted((study / "runs").glob("*/graph-envelope.json")):
        envelope = json.loads(p.read_text())
        result = json.loads((p.parent / "result.json").read_text())
        t = result["trial"]
        v = next(
            r["variant"]
            for r in catalog
            if r["variant"]["source_native_id"] == t["record_id"]
        )
        refs = [
            dict(
                entity_type="StrategyVariant",
                entity_id=v["strategy_variant_id"],
                definition_revision=v["spec_sha256"],
            )
        ]
        envelope["study_metadata"] = metadata(
            request["study_type"],
            refs,
            cfg,
            [
                "Independent BTC/EUR/cash research implementation; no source-exact reproduction claim",
                "Retrospective observed history; no independent confirmation",
                "Market/derived numeric attachments restricted by Bit2Me reviewed terms",
            ],
            {
                "source_record_id": v["source_native_id"],
                "source_sha256": v["source_sha256"],
                "concept_id": v["strategy_concept_id"],
                "template_id": v["strategy_template_id"],
                "trial": t,
                "relation": "DERIVED_FROM" if t["round"] else "TESTED_BY",
                "execution_status": result["status"],
            },
            refs if t["round"] else [],
        )
        summary = envelope["study_metadata"]["public_summary"]
        summary["sample"] = {
            "start": plan["evaluation_start"],
            "end": plan["end"],
            "rows": sum(
                result.get("metrics", {}).get(k, {}).get("observations", 0)
                for k in ("development", "validation")
            ),
            "frequency": "1d",
            "symbols": ["BTC/EUR"],
            "dataset_version": plan["dataset_version"],
            "real_market_data": True,
        }
        if t["round"]:
            summary["evolution"] = {
                "parent_experiment_id": t["parent_experiment_id"],
                "reason": "Observed development turnover and execution-cost erosion",
                "change": "Two consecutive closed-bar conditions; all other rules fixed",
                "outcome": result["status"],
                "interpretation": "Execution status only; numerical hypothesis test remains in restricted artifact",
            }
        outcomes.append(envelope)
    _get(context, "checkpoint")("STRATEGIES_COMPLETE", {"completed": 2, "total": 2})
    return outcomes
