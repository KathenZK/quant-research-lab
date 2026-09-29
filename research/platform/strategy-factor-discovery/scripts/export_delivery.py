"""Export append-only metadata revisions for C; never rerun or rewrite research."""

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from strategy_lab.discovery.capabilities import metadata
from strategy_lab.discovery.campaign import triage
from strategy_lab.factor_study.pipeline import digest, ref, write
from strategy_lab.knowledge.market_contract import sha
from strategy_lab.research.trials import TrialRegistry


def checked(item):
    if sha(item["uri"]) != item["sha256"]:
        raise ValueError("Changed immutable artifact: " + item["uri"])
    return item


def save(path, value):
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError("Changed delivery revision: " + str(path))
    else:
        write(path, value)
    return ref(path)


def main():
    from quantgraph import FactorDB
    from quantgraph.graph.factor_study_store import FactorStudyRepository
    from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
    from quantgraph.models.factor_study import FactorStudyResult, StudyMetadata

    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--factor-config", type=Path, required=True)
    parser.add_argument("--strategy-config", type=Path, required=True)
    a = parser.parse_args()
    root = a.campaign.resolve()
    out = root / "delivery-v1"
    out.mkdir(exist_ok=True)
    fc, sc = [json.loads(p.read_text()) for p in (a.factor_config, a.strategy_config)]
    db = FactorDB(fc["graph_root"])
    factor_repo = FactorStudyRepository(fc["journal"], db)
    strategy_repo = SQLiteIngestionRepository(sc["journal"])
    campaigns = ["discovery-20260928-v1", "factor-study-discovery20-factors-v1"]
    scope = TrialRegistry(root / "trials.jsonl").snapshot(campaigns)
    scope_ref = save(out / "registry-scope.json", scope)
    entries, controls, seen = [], [], set()
    for directory in ["strategies", "confirmation-repair-v1", "factor-component-dev"]:
        folder = root / directory
        plan = json.loads((folder / "plan.json").read_text())
        paths = (
            (folder / "runs").glob("*/result.json")
            if directory != "factor-component-dev"
            else folder.glob("*/result.json")
        )
        for path in sorted(paths):
            r = json.loads(path.read_text())
            t = r.get("trial", {})
            aid = t.get("attempt_id", r.get("attempt_id"))
            if aid in seen:
                continue
            seen.add(aid)
            for artifact in r.get("artifacts", []):
                checked(artifact)
            if t.get("record_id") == "INTERNAL_BUY_HOLD":
                controls.append(
                    {
                        "attempt_id": aid,
                        "result": ref(path),
                        "classification": "INTERNAL_BASELINE",
                    }
                )
                continue
            original = path.parent / "graph-envelope.json"
            previous = path.parent / "graph-enriched-envelope.json"
            value = json.loads(
                (previous if previous.exists() else original).read_text()
            )
            md = value["study_metadata"]
            old_run = value["research_run_id"]
            md["provenance"].update(
                original_result=ref(path),
                original_envelope=ref(original),
                original_registry_scope=scope_ref,
                evidence_revision_of=old_run,
                metadata_revision="B-delivery-v1",
                execution_status=r["status"],
            )
            md["public_summary"]["execution_status"] = r["status"]
            md["public_summary"]["classification"] = (
                "COMPUTATION_FAILED"
                if r["status"] == "FAILED"
                else "EXPLORATORY_RESEARCH_COMPLETED"
            )
            md["public_summary"]["source_reproduction"] = (
                "INDEPENDENT_RESEARCH_IMPLEMENTATION_NOT_SOURCE_EXACT"
            )
            md["public_summary"]["conclusion_reason"] = (
                "Historical previously observed sample; computational completion does not establish predictive or trading effectiveness"
            )
            md["public_summary"]["sample"] = {
                "start": plan["evaluation_start"],
                "end": plan["end"],
                "rows": 519 if directory == "factor-component-dev" else 1153,
                "frequency": "1d",
                "symbols": ["BTC/EUR"],
                "dataset_version": plan["dataset_version"],
                "real_market_data": True,
                "rows_meaning": "Planned evaluation bars, including for failed attempts; source input has1549 bars",
            }
            relations = md["provenance"].get("relationships", [])
            if directory == "factor-component-dev":
                if r["name"] == "parent_MA50":
                    relations = [x for x in relations if x["relation"] != "USES_FACTOR"]
                    md["provenance"]["metadata_correction"] = (
                        "MA50 is the matched control; it does not consume Qlib MA5 values. Old metadata remains retained but superseded."
                    )
                md["public_summary"]["evolution"] = {
                    "reason": "Development-only component redundancy and turnover ablation",
                    "change": "Qlib MA5 positions versus matched SMA50 parent control; same execution",
                    "parent_experiment_id": "EV3-M0234-BTC-EUR--"
                    + (
                        "gross"
                        if r["fee_bps"] == 0
                        else "net"
                        if r["fee_bps"] == 10
                        else "stress"
                    ),
                    "outcome": r["status"],
                    "research_origin": "SELF_OWNED_HYPOTHESIS",
                }
            if r["status"] == "FAILED":
                md["public_summary"]["failure_reason"] = (
                    "Pandas read-only signal array; retained original failed attempt. Repair is a separately registered immutable attempt."
                )
            relations = [x for x in relations if x["relation"] != "TESTED_BY"]
            md["provenance"]["relationships"] = relations
            value["research_run_id"] = "qgrun-" + digest(value)[:32]
            relations.append(
                {
                    "relation": "TESTED_BY",
                    "from": md["lineage"][0] if md["lineage"] else md["entity_refs"][0],
                    "to": {
                        "entity_type": "ResearchEvidence",
                        "entity_id": value["research_run_id"],
                    },
                    "evidence": "Actual retained result; no new experiment from metadata revision",
                }
            )
            StudyMetadata.model_validate(md)
            envelope_ref = save(
                out / "envelopes" / (value["research_run_id"] + ".json"), value
            )
            receipt = strategy_repo.put_evidence(value, "B-delivery-v1")
            assert value in strategy_repo.evidence_for(
                md["entity_refs"][0]["entity_id"]
            )
            entries.append(
                dict(
                    kind="strategy",
                    run_id=value["research_run_id"],
                    study_type=md["study_type"],
                    status=r["status"],
                    entity_refs=md["entity_refs"],
                    attempt_ids=[aid],
                    original_result=ref(path),
                    original_envelope=ref(original),
                    envelope=envelope_ref,
                    registry_scope=scope_ref,
                    metadata_revision=True,
                    receipt=receipt,
                )
            )
    for path in sorted((root / "factors/study/runs").glob("*/result.json")):
        r = json.loads(path.read_text())
        for artifact in r["artifacts"]:
            checked(artifact)
        value = copy.deepcopy(r)
        identity = r["mapping"]["identity"]
        eref = dict(
            entity_type="FactorVariant",
            entity_id=identity["factor_variant_id"],
            definition_revision=identity["definition_revision"],
        )
        md = metadata(
            "FACTOR_DIAGNOSTIC",
            [eref],
            fc,
            r["limitations"],
            {
                "mapping": r["mapping"],
                "dataset": r["dataset"],
                "contract": r["contract"],
                "code": r["code"],
                "execution_status": r["status"],
                "original_result": ref(path),
                "evidence_revision_of": r["run_id"],
                "original_registry_scope": scope_ref,
                "metadata_revision": "B-delivery-v1",
            },
        )
        md["public_summary"].update(
            sample={
                **r["sample"],
                "end": r["sample"]["end_exclusive"],
                "frequency": "1d",
            },
            execution_status=r["status"],
            classification="COMPUTATION_VERIFIED_EXPLORATORY_DIAGNOSTIC",
            conclusion_reason="Computation equivalence verified; retrospective association is not independent prediction evidence",
        )
        value["study_metadata"] = md
        value["run_id"] = "factor-study-" + digest(value)[:32]
        FactorStudyResult.model_validate(value)
        target = save(out / "envelopes" / (value["run_id"] + ".json"), value)
        receipt = factor_repo.put(value)
        assert value in factor_repo.query(
            identity["factor_variant_id"], profile="research"
        )
        attempts = [
            x["attempt_id"]
            for x in r["trial_registry"]["experiments"]
            if x["factor_variant_id"] == identity["factor_variant_id"]
        ]
        entries.append(
            dict(
                kind="factor",
                run_id=value["run_id"],
                study_type="FACTOR_DIAGNOSTIC",
                status=r["status"],
                entity_refs=[eref],
                attempt_ids=attempts,
                original_result=ref(path),
                original_envelope=ref(path),
                envelope=target,
                registry_scope=scope_ref,
                metadata_revision=True,
                receipt=receipt,
            )
        )
    catalog = json.loads(Path(sc["source_catalog"]).read_text())
    variants = db.search_factors(limit=1000) + db.search_factors(
        limit=1000, offset=1000
    )
    inventory = triage(catalog, variants)
    triage_ref = save(out / "complete-catalog-triage.json", inventory)
    smoke_path = root.parent / "smoke-trials.jsonl"
    from strategy_lab.research.exposure import read_ledger

    smoke_campaigns = [
        x["data"]["selection_campaign_id"]
        for x in read_ledger(smoke_path)
        if x["data"]["kind"] == "selection_campaign"
    ]
    smoke_ref = save(
        out / "smoke-registry-scope.json",
        TrialRegistry(smoke_path).snapshot(smoke_campaigns),
    )
    derived = ref(root / "strategies/derived-record-batch.json")
    counts = {
        "strategies": 81,
        "strategy_completed": 75,
        "strategy_failed": 6,
        "factor_label_trials": 40,
        "smoke_factor_labels": 2,
        "strategy_templates": 20,
        "strategy_concepts": 19,
        "factor_concepts": 20,
        "factor_definitions": 20,
        "factor_variants": 20,
        "economic_mechanisms_conservative": 4,
        "strategy_computational_groups": 9,
        "factor_computational_groups": 8,
        "source_exact_strategy_reproduction": 0,
        "TS_definitions": 20,
        "CS_definitions": 0,
        "metadata_import_entries": len(entries),
    }
    manifest = dict(
        schema_version="B-discovery-delivery-manifest/v1",
        import_mode="IMPORTED_COMPLETED_RESEARCH",
        execute_new_trials=False,
        registry_scope=scope_ref,
        smoke_registry_scope=smoke_ref,
        triage=triage_ref,
        triage_counts=dict(Counter(x["status"] for x in inventory)),
        counts=counts,
        internal_baselines=controls,
        derived_record_batches=[derived],
        entries=entries,
        correction="Old comparison.json economic_method_groups=9 counted computational structures. Conservative economic mechanisms=4; old immutable bytes are retained.",
        artifact_display="PUBLIC operational metadata; numerical market derivatives PRIVATE_INTERNAL_RESEARCH under reviewed Bit2Me terms",
        no_promotion=True,
        prior_search_history="UNKNOWN",
        restoration=ref(root / "independent-restoration.json"),
    )
    # Duplicate=true receipts change on retry; expose only stable storage identities.
    for e in entries:
        e["receipt"].pop("duplicate", None)
    target = save(out / "import-manifest.json", manifest)
    print(
        json.dumps(
            {"manifest": target, "counts": counts, "triage": manifest["triage_counts"]},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
