"""TrialRegistry/v1: attempts and transitions on the existing local hash journal.

An experiment is an idempotency namespace. Its fully specified research choices
identify an attempt; retrying those choices does not manufacture another trial.
Campaigns describe the *selection process*, and can span hypothesis families.
The journal records declarations and known events, not omniscient history.
"""
from __future__ import annotations

import json
from pathlib import Path

from .accounting import digest, utc
from .exposure import append_locked, read_ledger

VERSION = "TrialRegistry/v1"
COMPLETENESS = {"COMPLETE_DECLARED", "INCOMPLETE", "UNKNOWN"}
STATES = {"planned", "started", "completed", "failed", "aborted"}
OBSERVED = {"OBSERVED", "UNOBSERVED", "UNKNOWN"}
SELECTION = {"YES", "NO", "UNKNOWN"}
SPEC_FIELDS = {
    "hypothesis_family_id", "selection_campaign_id", "identity", "parameters",
    "label_horizon", "objective", "selection_rule", "dataset_fingerprint",
    "sample_fingerprint", "code_hash", "config_hash", "parent_experiment_id",
}


def _copy(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def valid_snapshot(scope: dict) -> bool:
    """Detect stale/accidentally edited snapshots; this is not an attestation."""
    try:
        return (scope.get("registry_version") == VERSION and bool(scope.get("campaign_ids"))
                and scope.get("scope_sha256") == digest({k: v for k, v in scope.items() if k != "scope_sha256"}))
    except (TypeError, ValueError):
        return False


def _required(value, fields):
    missing = fields - value.keys()
    if missing:
        raise ValueError("Missing trial fields: " + ", ".join(sorted(missing)))


def _campaign(records, campaign_id):
    return next((r for r in records if r["data"]["kind"] == "selection_campaign"
                 and r["data"]["selection_campaign_id"] == campaign_id), None)


def _attempts(records):
    attempts = {}
    for record in records:
        d = record["data"]
        if d["kind"] == "trial_attempt":
            attempts[d["attempt_id"]] = {
                **d, "state": "planned", "results_observed": "UNKNOWN" if d["historical_import"] else "UNOBSERVED",
                "affects_selection": "UNKNOWN", "registered_at": record["registered_at"],
                "timestamps": {"planned": record["registered_at"]}, "events": [],
            }
        elif d["kind"] == "trial_transition":
            a = attempts[d["attempt_id"]]
            a.update(state=d["state"], results_observed=d["results_observed"],
                     affects_selection=d["affects_selection"])
            a["timestamps"][d["state"]] = record["registered_at"]
            a["events"].append(record)
    return attempts


class TrialRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def register_campaign(self, selection_campaign_id: str, *, selection_goal: str,
                          scope_definition: str, history_completeness: str = "UNKNOWN",
                          history_reason: str, evidence_refs: list[str] | None = None) -> dict:
        """Freeze scope once. A narrower family is not a replacement for a campaign.

        COMPLETE_DECLARED needs supporting references; it is still a scoped
        declaration. Later discoveries use a new scope revision including all
        linked campaigns via snapshot(), never deletion of inconvenient trials.
        """
        if (not selection_campaign_id or not selection_goal or not scope_definition
                or not history_reason or history_completeness not in COMPLETENESS):
            raise ValueError("Explicit selection scope and history completeness required")
        if history_completeness == "COMPLETE_DECLARED" and not evidence_refs:
            raise ValueError("Completeness declaration requires evidence references")
        data = dict(id="campaign-" + digest(selection_campaign_id), kind="selection_campaign",
                    family=selection_campaign_id, selection_campaign_id=selection_campaign_id,
                    selection_goal=selection_goal, scope_definition=scope_definition,
                    history_completeness=history_completeness, history_reason=history_reason,
                    evidence_refs=evidence_refs or [], registry_version=VERSION)
        return append_locked(self.path, lambda _: data, idempotent=True)

    def plan(self, experiment_id: str, spec: dict, *, historical_import: bool = False,
             import_completeness: str = "UNKNOWN", import_source: str | None = None) -> str:
        spec = _copy(spec)
        _required(spec, SPEC_FIELDS)
        if not experiment_id or not all(spec[k] for k in SPEC_FIELDS - {"parent_experiment_id", "parameters", "label_horizon"}):
            raise ValueError("Nonempty research identity, hashes and selection scope required")
        for key in ("code_hash", "config_hash", "dataset_fingerprint", "sample_fingerprint"):
            value = spec[key]
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("Expected SHA256 for " + key)
        if import_completeness not in COMPLETENESS or (historical_import and not import_source):
            raise ValueError("Historical import requires provenance and explicit completeness")
        attempt_id = "attempt-" + digest({"experiment_id": experiment_id, "spec": spec})
        data = dict(id=attempt_id, kind="trial_attempt", family=spec["hypothesis_family_id"],
                    attempt_id=attempt_id, experiment_id=experiment_id, spec=spec,
                    historical_import=historical_import, import_source=import_source,
                    import_completeness=import_completeness if historical_import else "NOT_IMPORTED",
                    registry_version=VERSION)

        def build(records):
            if _campaign(records, spec["selection_campaign_id"]) is None:
                raise ValueError("Register selection campaign before attempts")
            return data

        append_locked(self.path, build, idempotent=True)
        return attempt_id

    def record(self, attempt_id: str, *, event_id: str, state: str,
               results_observed: str, affects_selection: str, reason: str,
               result_refs: dict | None = None, occurred_at: str | None = None) -> dict:
        """Append lifecycle evidence. event_id must be stable across a transport retry.

        Failed/aborted attempts may restart unchanged. Previous events survive.
        Human observation or influence can never be retracted by a later event.
        occurred_at is a source claim; registered_at is the actual write time.
        """
        if (not event_id or state not in STATES or state == "planned" or not reason
                or results_observed not in OBSERVED or affects_selection not in SELECTION):
            raise ValueError("Explicit state, observation, selection influence and reason required")
        data = dict(id="event-" + digest([attempt_id, event_id]), kind="trial_transition",
                    attempt_id=attempt_id, event_id=event_id, state=state,
                    results_observed=results_observed, affects_selection=affects_selection,
                    reason=reason, result_refs=result_refs or {}, occurred_at=occurred_at)

        def build(records):
            a = _attempts(records).get(attempt_id)
            if a is None:
                raise ValueError("Unknown attempt")
            data["family"] = a["family"]
            # Return the original intent before checking today's lifecycle state.
            if any(r["data"]["id"] == data["id"] for r in records):
                return data
            allowed = {
                "planned": {"started", "aborted"},
                "started": {"started", "completed", "failed", "aborted"},
                "failed": {"started", "failed"}, "aborted": {"started", "aborted"},
                "completed": {"completed"},
            }
            if state not in allowed[a["state"]]:
                raise ValueError("Invalid attempt transition")
            if a["results_observed"] == "OBSERVED" and results_observed != "OBSERVED":
                raise ValueError("Cannot erase observed results")
            if a["affects_selection"] == "YES" and affects_selection != "YES":
                raise ValueError("Cannot erase selection influence")
            return data

        return append_locked(self.path, build, idempotent=True)

    def snapshot(self, campaign_ids: list[str]) -> dict:
        """Include every family within selected campaigns, with no family filter.

        Unrelated campaigns are not pooled. The caller must explicitly link
        campaigns that contributed to one selection; unknown scope stays unknown.
        """
        if not campaign_ids or len(campaign_ids) != len(set(campaign_ids)):
            raise ValueError("Unique selection campaigns required")
        records = read_ledger(self.path)
        campaigns = [_campaign(records, c) for c in campaign_ids]
        if any(c is None for c in campaigns):
            raise ValueError("Unknown campaign")
        attempts = [a for a in _attempts(records).values()
                    if a["spec"]["selection_campaign_id"] in campaign_ids]
        relevant = [a for a in attempts if (a["state"] == "completed"
                    or a["results_observed"] == "OBSERVED" or a["affects_selection"] == "YES")
                    and not (a["spec"].get("trial_role") == "PRESPECIFIED_DIAGNOSTIC"
                             and a["affects_selection"] == "NO")]
        uncertain = [a["attempt_id"] for a in attempts
                     if a["state"] != "planned" and (a["results_observed"] == "UNKNOWN"
                                                     or a["affects_selection"] == "UNKNOWN")]
        complete = all(c["data"]["history_completeness"] == "COMPLETE_DECLARED" for c in campaigns)
        complete &= all(not a["historical_import"] or a["import_completeness"] == "COMPLETE_DECLARED"
                        for a in attempts)
        history = "COMPLETE_DECLARED" if complete else (
            "INCOMPLETE" if (any(c["data"]["history_completeness"] == "INCOMPLETE" for c in campaigns)
                             or any(a["import_completeness"] == "INCOMPLETE" for a in attempts))
            else "UNKNOWN")
        result = dict(registry_version=VERSION, campaign_ids=sorted(campaign_ids),
                      campaigns=[c["data"] for c in campaigns], attempts=attempts,
                      raw_attempts=len(attempts), completed_trials=sum(a["state"] == "completed" for a in attempts),
                      observed_trials=sum(a["results_observed"] == "OBSERVED" for a in attempts),
                      selection_trial_ids=sorted(a["attempt_id"] for a in relevant),
                      excluded_diagnostic_ids=sorted(a["attempt_id"] for a in attempts
                          if a["spec"].get("trial_role") == "PRESPECIFIED_DIAGNOSTIC" and a["affects_selection"] == "NO"),
                      uncertain_attempt_ids=sorted(uncertain), history_completeness=history,
                      ledger_head=records[-1]["sha256"] if records else None,
                      scope_limitation="Declared campaigns; unrecorded or misclassified research cannot be ruled out")
        result["scope_sha256"] = digest(result)
        return result

    def freeze_holdout(self, holdout_id: str, plan: dict) -> dict:
        """Retain a plan with the journal's actual write time, not a backdated claim.

        Only prospective-after-freeze protocols are supported for decision use in
        v1. Historical sealing protocols may be recorded, but remain UNKNOWN.
        """
        plan = _copy(plan)
        _required(plan, {"contract_hash", "plan_frozen_at", "dataset_version", "sample_fingerprint",
                         "sample_start", "sample_end", "protocol", "max_uses",
                         "known_access_records", "access_history_status", "evidence_refs"})
        if (not holdout_id or utc(plan["sample_start"]) >= utc(plan["sample_end"])
                or type(plan["max_uses"]) is not int or plan["max_uses"] < 1):
            raise ValueError("Invalid holdout plan")
        data = dict(id="holdout-" + digest(holdout_id), kind="holdout_plan", family=holdout_id,
                    holdout_id=holdout_id, plan=plan)
        return append_locked(self.path, lambda _: data, idempotent=True)

    def use_holdout(self, holdout_id: str, *, use_id: str, dataset_fingerprint: str,
                    reason: str) -> dict:
        """Record *before* revealing results, including uses exceeding the limit.

        An exact retry reuses use_id. A new inspection uses a new id; the journal
        cannot monitor unreported human access or other files/copies.
        """
        if not use_id or not dataset_fingerprint or not reason:
            raise ValueError("Holdout use identity, dataset and reason required")
        data = dict(id="holdout-use-" + digest([holdout_id, use_id]), kind="holdout_use",
                    family=holdout_id, holdout_id=holdout_id, use_id=use_id,
                    dataset_fingerprint=dataset_fingerprint, reason=reason)

        def build(records):
            if not any(r["data"]["kind"] == "holdout_plan" and r["data"]["holdout_id"] == holdout_id for r in records):
                raise ValueError("Unknown holdout plan")
            return data

        return append_locked(self.path, build, idempotent=True)

    def holdout_evidence(self, holdout_id: str) -> dict:
        records = read_ledger(self.path)
        plan = next((r for r in records if r["data"]["kind"] == "holdout_plan"
                     and r["data"]["holdout_id"] == holdout_id), None)
        if plan is None:
            return {}
        # Same sample registered under another name does not reset usage/access.
        sample = plan["data"]["plan"]
        names = set()
        for record in records:
            if record["data"]["kind"] != "holdout_plan":
                continue
            other = record["data"]["plan"]
            if (other["dataset_version"] == sample["dataset_version"]
                    and utc(other["sample_start"]) < utc(sample["sample_end"])
                    and utc(other["sample_end"]) > utc(sample["sample_start"])):
                names.add(record["data"]["holdout_id"])
        return dict(plan_record=plan,
                    related_plans=[r for r in records if r["data"]["kind"] == "holdout_plan"
                                   and r["data"]["holdout_id"] in names],
                    use_records=[r for r in records if r["data"]["kind"] == "holdout_use"
                                 and r["data"]["holdout_id"] in names])
