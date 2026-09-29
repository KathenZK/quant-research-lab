"""Resumable fixed-profile batch. Server configs are local reviewed files, not web input."""

import argparse
import json
from pathlib import Path
from strategy_lab.discovery import campaign
from strategy_lab.discovery.capabilities import execute
from strategy_lab.factor_study.pipeline import write
from strategy_lab.research.trials import TrialRegistry


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--factor-config", type=Path, required=True)
    p.add_argument("--strategy-config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument(
        "--stage",
        choices=[
            "freeze",
            "factors",
            "baselines",
            "evolve",
            "component",
            "finish",
            "all",
        ],
        default="all",
    )
    a = p.parse_args()
    root = a.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    fc = json.loads(a.factor_config.read_text())
    sc = json.loads(a.strategy_config.read_text())
    sc["registry_path"] = str(root / "trials.jsonl")
    from quantgraph import FactorDB
    from quantgraph.factor_study import definition_identity

    db = FactorDB(fc["graph_root"])
    variants = db.search_factors(limit=1000)
    variants += db.search_factors(limit=1000, offset=1000)
    if a.stage in {"freeze", "all"} and not (root / "strategies/plan.json").exists():
        campaign.freeze(sc["source_catalog"], variants, sc, root / "strategies")
    if a.stage in {"factors", "all"}:
        selected = []
        for name in fc["settings"]["names"]:
            v = next(
                v for v in variants if "Alpha158:" + name in v["source_native_ids"]
            )
            selected.append(
                {
                    "entity_type": "FactorVariant",
                    "entity_id": v["factor_variant_id"],
                    "definition_revision": definition_identity(v)[
                        "definition_revision"
                    ],
                }
            )
        request = {
            "schema_version": "research-request/v1",
            "request_id": "discovery20-draft-v1",
            "study_type": "FACTOR_DIAGNOSTIC",
            "status": "DRAFT",
            "entity_refs": selected,
            "requested_settings": {"profile_id": fc["profile_id"]},
        }
        results = execute(
            request,
            {
                "run_id": "discovery20-factors-v1",
                "server_config": fc,
                "output_dir": str(root / "factors"),
                "registry_path": str(root / "trials.jsonl"),
                "checkpoint": lambda s, v: print(s, v, flush=True),
                "cancelled": lambda: False,
            },
        )
        if not (root / "factor-envelopes.json").exists():
            write(root / "factor-envelopes.json", results)
    if a.stage in {"baselines", "all"}:
        print(campaign.run(root / "strategies", workers=a.workers))
    if a.stage in {"evolve", "all"}:
        campaign.freeze_evolution(root / "strategies")
        print(campaign.run(root / "strategies", round_number=1, workers=a.workers))
    if a.stage in {"component", "all"}:
        from strategy_lab.discovery.component import run

        print(
            {
                "component_configurations": len(
                    run(
                        sc,
                        root / "factor-component-dev",
                        registry_path=root / "trials.jsonl",
                    )
                )
            }
        )
    if a.stage in {"finish", "all"}:
        campaign.report(root / "strategies")
        receipts = campaign.writeback(root / "strategies", sc["journal"])
        from strategy_lab.discovery.publication import publish

        publish(root / "strategies", graph_root=sc["graph_root"], journal=sc["journal"])
        scope = TrialRegistry(root / "trials.jsonl").snapshot(
            ["discovery-20260928-v1", "factor-study-discovery20-factors-v1"]
        )
        if not (root / "all-trials.json").exists():
            write(root / "all-trials.json", scope)
        print(
            {
                "registered_attempts": scope["raw_attempts"],
                "observed_attempts": scope["observed_trials"],
                "strategy_writeback_readback": len(receipts),
            }
        )


if __name__ == "__main__":
    main()
