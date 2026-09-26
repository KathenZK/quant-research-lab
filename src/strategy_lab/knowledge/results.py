"""Versioned evidence envelope. Uncomputed measurements remain null with reasons."""
from .candidates import digest

SECTIONS = ('in_sample', 'oos', 'walk_forward', 'monte_carlo', 'turnover', 'costs', 'drawdown',
            'sharpe', 'sortino', 'calmar', 'stability', 'ic', 'rank_ic', 'icir',
            'pbo', 'deflated_sharpe', 'parameter_plateau')


def evidence_envelope(*, family_id, source_strategy_ids, contract, trial_count, artifact_uri,
                      artifact_sha256, results, evidence_kind='LAB_REPRODUCED'):
    if not source_strategy_ids or trial_count < 1 or len(artifact_sha256) != 64:
        raise ValueError('Evidence requires lineage, positive trial count and artifact hash')
    unknown = set(results) - set(SECTIONS)
    if unknown:
        raise ValueError('Unknown result sections: ' + ', '.join(sorted(unknown)))
    sections = {k: results.get(k, {'value': None, 'status': 'NOT_COMPUTED', 'reason': 'Not supplied by this run'}) for k in SECTIONS}
    contract_hash = digest(contract)
    payload = dict(schema_version='1.0', experiment_family_id=family_id,
                   source_strategy_ids=sorted(set(source_strategy_ids)), contract_sha256=contract_hash,
                   trial_count=trial_count, artifact_uri=artifact_uri, artifact_sha256=artifact_sha256,
                   results=sections, evidence_kind=evidence_kind,
                   validation_status='SUBMITTED_NOT_INDEPENDENTLY_VERIFIED')
    payload['research_run_id'] = 'qgrun-' + digest(payload)[:32]
    return payload
