"""Research statistics/v1. Numerical core preserved from frozen quantgraph-diagnostics/v2.

The frozen kernel remains untouched; reference tests cover both implementations.
High-level consumers use assemble_dsr/evaluate_pbo for scope and applicability.

DSR: Bailey and Lopez de Prado (2014), equations 1-3; unannualized SR.
CSCV: Bailey et al., The Probability of Backtest Overfitting, section 2.
"""
from itertools import combinations
from math import comb, e, sqrt
from statistics import NormalDist
import numpy as np

from .accounting import digest
from .trials import valid_snapshot


def finite(values, ndim=1):
    x = np.asarray(values, dtype=float)
    if x.ndim != ndim or not np.isfinite(x).all():
        raise ValueError('Finite data with the expected dimensions required')
    return x


def sharpe(x):
    x = np.asarray(x, dtype=float)
    sd = np.std(x, axis=0, ddof=1)
    if np.any(np.ptp(x, axis=0) == 0) or np.any(sd <= 0):
        raise ValueError('Zero variance; Sharpe is undefined')
    return np.mean(x, axis=0) / sd


def deflated_sharpe(returns, *, trial_sharpes, effective_trials):
    r, trials = finite(returns), finite(trial_sharpes)
    if len(r) < 4 or len(trials) < 2 or not 2 <= effective_trials <= len(trials):
        raise ValueError('DSR requires >=4 observations, >=2 trial SRs and declared effective trials')
    sr = float(sharpe(r))
    z = (r - r.mean()) / r.std(ddof=0)
    skew, kurt = float(np.mean(z ** 3)), float(np.mean(z ** 4))
    result = dsr_from_moments(sr=sr, trial_variance=float(trials.var(ddof=1)),
                              effective_trials=effective_trials, observations=len(r), skew=skew, kurtosis=kurt)
    return {**result, 'unannualized_sr': sr, 'skew': skew, 'pearson_kurtosis': kurt,
            'effective_trials': effective_trials, 'observed_trials': len(trials),
            'assumption': 'IID returns approximation; effective trial count supplied, not inferred'}


def dsr_from_moments(*, sr, trial_variance, effective_trials, observations, skew, kurtosis):
    """Paper Eq. 2, all Sharpe quantities in per-observation units.

    Annual Sharpe divides by sqrt(periods/year); annual trial variance divides
    by periods/year. Pearson kurtosis is used, NOT excess kurtosis.
    """
    finite([sr, trial_variance, effective_trials, observations, skew, kurtosis])
    if observations < 4 or int(observations) != observations or effective_trials < 2 or trial_variance < 0 or kurtosis < 1:
        raise ValueError('Invalid DSR moments/sample/trial count')
    normal, gamma = NormalDist(), 0.5772156649015329
    threshold = sqrt(trial_variance) * ((1 - gamma) * normal.inv_cdf(1 - 1 / effective_trials)
                                      + gamma * normal.inv_cdf(1 - 1 / (effective_trials * e)))
    variance = 1 - skew * sr + (kurtosis - 1) * sr * sr / 4
    if variance <= 0:
        raise ValueError('Invalid Sharpe sampling variance')
    return {'value': normal.cdf((sr - threshold) * sqrt(observations - 1) / sqrt(variance)),
            'benchmark_sr': float(threshold)}


def pbo(returns_by_trial, *, blocks=8):
    x = finite(returns_by_trial, 2)
    if type(blocks) is not int or x.shape[1] < 2 or not 4 <= blocks <= 12 or blocks % 2 or x.shape[0] % blocks or x.shape[0] // blocks < 2:
        raise ValueError('CSCV requires >=2 trials, 4..12 even equal blocks and >=2 observations/block')
    pieces = np.split(np.arange(x.shape[0]), blocks)
    logits = []
    for chosen in combinations(range(blocks), blocks // 2):
        other = [i for i in range(blocks) if i not in chosen]
        train = x[np.concatenate([pieces[i] for i in chosen])]
        test = x[np.concatenate([pieces[i] for i in other])]
        train_sr = sharpe(train)
        # Include all tied in-sample winners; do not favor an arbitrary column.
        winners = np.flatnonzero(train_sr == train_sr.max())
        test_sr = sharpe(test)
        for winner in winners:
            rank = 1 + np.sum(test_sr < test_sr[winner]) + (np.sum(test_sr == test_sr[winner]) - 1) / 2
            percentile = rank / (x.shape[1] + 1)
            logits.append((float(np.log(percentile / (1 - percentile))), 1 / len(winners)))
    total_weight = sum(w for _, w in logits)
    return {'value': sum(w for v, w in logits if v <= 0) / total_weight,
            'splits': comb(blocks, blocks // 2), 'blocks': blocks, 'trial_count': x.shape[1],
            'weighted_logits': logits,
            'tie_policy': 'midrank; average all tied IS winners', 'purged': False}


def assemble_dsr(scope, returns_by_attempt, *, selected_attempt_id, dependence=None,
                 return_assumptions=None):
    """Assemble Eq. 2 from the declared selection campaign, never a grid length.

    Each return entry contains values, kind=STRATEGY_RETURNS, sample_fingerprint,
    dataset_fingerprint and periods_per_year. All entries must be comparable.
    Dependence: UNKNOWN (default), INDEPENDENT with rationale/evidence, or an
    EXPLICIT_ESTIMATE/SENSITIVITY with supplied effective_trials values. We do
    not estimate independence from an arbitrary count or from factor ICs.
    """
    dependence = dependence or {"method": "UNKNOWN"}
    return_assumptions = return_assumptions or {}
    result = dict(method="DSR_BAILEY_2014_EQ2", method_version="research-statistics/v1",
                  status="NOT_ESTIMABLE", value=None, applicability_status="UNKNOWN",
                  decision_use="DIAGNOSTIC_ONLY", full_historical_correction=False,
                  selection_scope=scope, dependence_assumptions=dependence,
                  raw_attempts=scope.get("raw_attempts"), completed_trials=scope.get("completed_trials"),
                  observed_trials=scope.get("observed_trials"), numerical_input_trials=len(returns_by_attempt),
                  return_assumptions=return_assumptions, effective_independent_trials=None,
                  sharpe_units="PER_OBSERVATION", limitations=[
                      "Conditional on recorded selection scope and supplied dependence assumptions",
                      "IID-return sampling approximation; does not correct serial dependence",
                      "Registry completeness is a declaration, not proof of all past research"],
                  reasons=[])
    ids = scope.get("selection_trial_ids", [])
    if not valid_snapshot(scope) or selected_attempt_id not in ids or len(ids) < 2:
        result["reasons"].append("At least two registered selection trials including the selected strategy required")
        return result
    missing, extra = set(ids) - returns_by_attempt.keys(), returns_by_attempt.keys() - set(ids)
    if missing or extra:
        result["reasons"].append("Return input must match selection scope exactly; missing=" + str(sorted(missing))
                                 + "; extra=" + str(sorted(extra)))
        return result
    entries = [returns_by_attempt[i] for i in ids]
    if any(e.get("kind") != "STRATEGY_RETURNS" for e in entries):
        result.update(applicability_status="NOT_APPLICABLE", reasons=["DSR requires strategy returns, not IC or factor scores"])
        return result
    try:
        keys = [(e["dataset_fingerprint"], e["sample_fingerprint"], e["periods_per_year"]) for e in entries]
        if len(set(keys)) != 1 or not all(keys[0]) or not np.isfinite(keys[0][2]) or keys[0][2] <= 0:
            raise ValueError("Incomparable datasets, samples or return frequencies in selection scope")
        records = {a["attempt_id"]: a for a in scope["attempts"]}
        for i, entry in zip(ids, entries):
            spec = records[i]["spec"]
            if any(entry[k] != spec[k] for k in ("dataset_fingerprint", "sample_fingerprint")):
                raise ValueError("Returns differ from registered dataset/sample fingerprint")
        arrays = [finite(e["values"]) for e in entries]
        if len({len(r) for r in arrays}) != 1 or len(arrays[0]) < 4:
            raise ValueError("Comparable samples with at least four observations required")
        sharpes = [float(sharpe(r)) for r in arrays]
        method = dependence.get("method")
        if method == "UNKNOWN" or not dependence.get("rationale") or not dependence.get("evidence_refs"):
            raise ValueError("Dependence unknown: supply documented assumptions or a sensitivity range")
        if method == "INDEPENDENT":
            counts = [len(ids)]  # Only under the explicit, retained independence assumption.
        elif method in {"EXPLICIT_ESTIMATE", "SENSITIVITY"}:
            counts = dependence.get("effective_trials", [])
            if not counts or (method == "EXPLICIT_ESTIMATE" and len(counts) != 1):
                raise ValueError("Explicit effective independent trial estimate(s) required")
        else:
            raise ValueError("Unsupported dependence method")
        if any(type(n) not in {int, float} or not np.isfinite(n) or not 2 <= n <= len(ids) for n in counts):
            raise ValueError("This Eq. 2 approximation supports 2 <= effective trials <= scoped observed returns")
        chosen = returns_by_attempt[selected_attempt_id]["values"]
        values = [deflated_sharpe(chosen, trial_sharpes=sharpes, effective_trials=n) for n in counts]
    except (ValueError, KeyError, TypeError) as exc:
        result["reasons"].append(str(exc))
        return result
    complete = (scope.get("history_completeness") == "COMPLETE_DECLARED"
                and not scope.get("uncertain_attempt_ids")
                and all(a["state"] != "started" for a in scope["attempts"]))
    iid_documented = (return_assumptions.get("sampling") == "IID_APPROXIMATION"
                      and bool(return_assumptions.get("evidence_refs")))
    usable = complete and iid_documented and method == "INDEPENDENT"
    result.update(status="COMPUTED" if usable else "CONDITIONAL", applicability_status="APPLICABLE",
                  decision_use="DECISION_SUPPORT" if usable else "DIAGNOSTIC_ONLY",
                  value=values[0]["value"] if len(values) == 1 else None,
                  effective_independent_trials=counts[0] if len(counts) == 1 else None,
                  sensitivity=values,
                  trial_sharpes=dict(zip(ids, sharpes)), trial_sharpe_variance=float(np.var(sharpes, ddof=1)),
                  annualization_periods=keys[0][2], observations=len(arrays[0]),
                  input_sha256=digest(returns_by_attempt))
    if len(values) == 1:
        result.update({k: v for k, v in values[0].items() if k not in {"value", "observed_trials"}})
    if not complete:
        result["reasons"].append("Historical registry, execution state or selection influence is incomplete/unknown")
    if not iid_documented:
        result["reasons"].append("Return sampling assumptions have not been documented")
    if method != "INDEPENDENT":
        result["reasons"].append("Effective-count estimate/sensitivity is conditional, not verified independence")
    return result


def evaluate_pbo(returns_by_trial, *, blocks=8, context=None, selection_scope=None, trial_ids=None):
    """CSCV of fixed synchronous candidate P&L; no invented purged CSCV variant.

    Fold-fitted predictions and unresolved training/test overlap need a separate
    validated protocol. Cross-block holdings alone do not imply such overlap.
    Numerics may be retained as diagnostics even when decision use is denied.
    """
    context = context or {}
    scope = selection_scope or {}
    ids = trial_ids or []
    result = dict(method="CSCV_FIXED_RETURNS", method_version="research-statistics/v1",
                  status="NOT_ESTIMABLE", value=None, applicability_status="UNKNOWN",
                  decision_use="DIAGNOSTIC_ONLY", context=context, reasons=[],
                  limitations=["Finite candidate set and recorded sample only; not a proof of independent discovery",
                               "Block choice, serial dependence, rank granularity and selection completeness matter"],
                  purged=False, embargoed=False, selection_scope_sha256=scope.get("scope_sha256"),
                  tie_policy="midrank; equal weight to tied IS winners; logit <= 0 counts as overfit")
    try:
        numeric = pbo(returns_by_trial, blocks=blocks)
    except (ValueError, TypeError) as exc:
        result["reasons"].append(str(exc))
        return result
    result.update(numeric, status="COMPUTED", observations=len(returns_by_trial))
    kind = context.get("input_kind")
    if kind not in {None, "FIXED_CANDIDATE_RETURNS"}:
        result.update(applicability_status="NOT_APPLICABLE",
                      reasons=["This fixed-return CSCV does not validate fold-fitted model predictions or factor ICs"])
        return result
    if context.get("future_information") is True or context.get("preprocessing") == "FULL_SAMPLE_FIT":
        result.update(applicability_status="NOT_APPLICABLE",
                      reasons=["Known future information or preprocessing fitted across train/test"])
        return result
    checks = {
        "fixed synchronous candidate returns": kind == "FIXED_CANDIDATE_RETURNS" and context.get("synchronous") is True,
        "causal returns and preprocessing": context.get("future_information") is False and context.get("preprocessing") == "NONE_OR_CAUSAL",
        "label overlap reviewed": context.get("overlapping_labels") is False,
        "boundary state reviewed": context.get("boundary_policy") == "CONTINUOUS_CAUSAL_ACCOUNT",
        "selection scope complete": context.get("selection_scope_complete") is True
            and valid_snapshot(scope)
            and scope.get("history_completeness") == "COMPLETE_DECLARED"
            and not scope.get("uncertain_attempt_ids")
            and len(ids) == numeric["trial_count"] and len(set(ids)) == len(ids)
            and set(ids) == set(scope.get("selection_trial_ids", [])),
        "sampling and block justification": bool(context.get("dependence_review")) and bool(context.get("block_justification")),
        "protocol frozen before observing results": context.get("protocol_frozen_before_results") is True,
        "supporting evidence references": bool(context.get("evidence_refs")),
    }
    result["reasons"] = ["Not established: " + name for name, passed in checks.items() if not passed]
    if all(checks.values()):
        result.update(applicability_status="APPLICABLE", decision_use="DECISION_SUPPORT")
    elif kind == "FIXED_CANDIDATE_RETURNS":
        result["applicability_status"] = "CONDITIONAL"
    if numeric["trial_count"] <= 10:
        result["limitations"].append("At most 10 candidates: coarse OOS ranks; small PBO is weak evidence")
        result["decision_use"] = "DIAGNOSTIC_ONLY"
    return result
