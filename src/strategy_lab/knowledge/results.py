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


def market_evidence_envelope(*, family_id, candidate_rows, contract, parameter_grid,
                             artifact_uri, artifact_sha256, code_sha256, config_sha256,
                             data_provenance, results, research_status, limitations):
    """Only an explicitly admitted, pinned real-data study can use schema 2.0.

    Validation is repeated by QuantGraph against the current immutable review.
    These hashes are lineage claims, not independent economic verification.
    """
    from pathlib import Path
    import json
    from jsonschema import validate
    from .candidates import SUPPORTED_GATE_VERSION
    if not candidate_rows:
        raise ValueError('No admitted candidates')
    concepts, templates = set(), set()
    for row in candidate_rows:
        gate = row.get('candidate_gate') or {}
        if gate.get('gate_version') != SUPPORTED_GATE_VERSION or gate.get('status') != 'ELIGIBLE' or gate.get('eligible') is not True:
            raise ValueError('UPSTREAM_CONTRACT_UNSUPPORTED: explicit ELIGIBLE V3 gate required')
        if row.get('reviewed_evidence', {}).get('data_requirement') != data_provenance:
            raise ValueError('Data differs from admitted evidence')
        concepts.add(row['variant']['strategy_concept_id'])
        templates.add(row['variant']['strategy_template_id'])
    if len(concepts) != 1 or len(templates) != 1:
        raise ValueError('One concept/template per experiment family')
    if data_provenance.get('real_market_data') is not True or data_provenance.get('quality_status') != 'PASS' or data_provenance.get('data_availability_status') != 'VERIFIED_AVAILABLE':
        raise ValueError('Untrusted or synthetic data cannot become formal market evidence')
    for value in (artifact_uri, data_provenance['data_source'], data_provenance['exchange'], data_provenance['dataset_version'], data_provenance['evidence']['uri']):
        if not value or any(marker in value.lower() for marker in ('fixture', 'synthetic', 'example.org', 'test-only')):
            raise ValueError('Diagnostic/fixture payload cannot be formal market evidence')
    if not {'in_sample', 'oos', 'costs', 'turnover', 'robustness', 'deflated_sharpe', 'pbo'} <= results.keys():
        raise ValueError('Incomplete research result sections')
    payload = dict(schema_version='2.0', experiment_family_id=family_id,
                   source_strategy_ids=sorted({r['variant']['strategy_variant_id'] for r in candidate_rows}),
                   strategy_concept_id=next(iter(concepts)), strategy_template_id=next(iter(templates)),
                   artifact_uri=artifact_uri, artifact_sha256=artifact_sha256,
                   contract_sha256=digest(contract), code_sha256=code_sha256, config_sha256=config_sha256,
                   candidate_snapshot_sha256=digest(candidate_rows), real_market_data=True,
                   data_provenance=data_provenance, trial_count=len(parameter_grid), parameter_grid=parameter_grid,
                   results=results, evidence_kind='REAL_MARKET_BACKTEST', research_status=research_status,
                   limitations=limitations, validation_status='SUBMITTED_NOT_INDEPENDENTLY_VERIFIED', promotion_allowed=False)
    payload['research_run_id'] = 'qgrun-' + digest(payload)[:32]
    schema = json.loads((Path(__file__).parent/'market_research_evidence_v2.schema.json').read_text())
    validate(payload, schema)
    return payload


def submit_market_evidence(client, envelope):
    """Stable SDK writeback followed by readback; no promotion side effects."""
    if envelope.get('schema_version') != '2.0' or envelope.get('evidence_kind') != 'REAL_MARKET_BACKTEST':
        raise ValueError('Only schema 2.0 formal market evidence may use this entry point')
    receipt = client.submit_research_evidence(envelope)
    for vid in envelope['source_strategy_ids']:
        rows = client.research_evidence(vid)['items']
        if not any(row == envelope for row in rows):
            raise ValueError('ResearchEvidence readback mismatch')
    return receipt
