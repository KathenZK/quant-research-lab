"""Append-only code repair and independent account restoration utilities."""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from .campaign import code_files, register_trials
from strategy_lab.factor_study.pipeline import digest, ref, write


def freeze_confirmation_repair(parent, output):
    """Preserve failed attempts; repeat exactly the predeclared confirmation rule.

    Reused baselines are copies of immutable results, never newly counted trials.
    New code means six new attempts. Already observed validation is disclosed.
    """
    parent, output = Path(parent).resolve(), Path(output).resolve()
    if (output / "plan.json").exists():
        return json.loads((output / "plan.json").read_text())
    output.mkdir(parents=True, exist_ok=False)
    old = json.loads((parent / "plan.json").read_text())
    if digest({k: v for k, v in old.items() if k != "plan_sha256"}) != old["plan_sha256"]:
        raise ValueError("Parent frozen plan changed")
    from strategy_lab.knowledge.market_contract import sha
    for round_number in (0, 1):
        completion = json.loads((parent / f"round-{round_number}-complete.json").read_text())
        for item in completion["results"]:
            if sha(item["uri"]) != item["sha256"]:
                raise ValueError("Parent completed result changed")
            result = json.loads(Path(item["uri"]).read_text())
            for artifact in result["artifacts"]:
                if sha(artifact["uri"]) != artifact["sha256"]:
                    raise ValueError("Parent artifact changed")
    plan = {
        **old,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "code_files": code_files(),
        "repair_parent_plan": ref(parent / "plan.json"),
        "repair_reason": "Nonmutating boolean conjunction fixes pandas3 read-only arrays; original six failed attempts remain immutable",
        "unchanged_hypothesis": ref(parent / "evolution-hypotheses.json"),
        "validation_observation": "Already observed after original baseline and failed round. No changed parameters, source selection or hypothesis; repaired results are retrospective only.",
    }
    plan.pop("plan_sha256")
    plan["plan_sha256"] = digest(plan)
    write(output / "plan.json", plan)
    from .campaign import ROOT

    for relative in plan["code_files"]:
        target = output / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    for name in ("selected-sources.json", "triage.json", "evolution-hypotheses.json"):
        shutil.copy2(parent / name, output / name)
    reused = []
    for path in sorted((parent / "runs").glob("*/result.json")):
        result = json.loads(path.read_text())
        if result["trial"]["round"] == 0:
            shutil.copytree(path.parent, output / "runs" / path.parent.name)
            reused.append(ref(path))
    write(output / "reused-baselines.json", {"not_new_trials": True, "results": reused})
    trials = json.loads((parent / "round-1.json").read_text())
    for t in trials:
        failed = json.loads(
            (parent / "runs" / t["trial_id"] / "result.json").read_text()
        )
        if (
            failed["status"] != "FAILED"
            or failed.get("reason") != "output array is read-only"
        ):
            raise ValueError(
                "Only identified confirmation calculation failure may be repaired"
            )
        t["failed_attempt_id"] = t.pop("attempt_id")
        t["failed_result"] = ref(parent / "runs" / t["trial_id"] / "result.json")
        head, cost = t["trial_id"].rsplit("--", 1)
        t["trial_id"] = head + "--repair1--" + cost
    register_trials(
        output, plan, trials, json.loads((output / "selected-sources.json").read_text())
    )
    write(output / "round-1.json", trials)
    return plan
