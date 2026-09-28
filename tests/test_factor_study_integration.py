"""Synthetic unit evidence only, not market study results."""
import copy
import json
from pathlib import Path
import pytest
from strategy_lab.factor_study.registered_trials import RegisteredTrialAdapter
from strategy_lab.factor_study.pipeline import digest


def test_registry_is_started_before_completion_and_keeps_failed_outcomes(tmp_path):
    adapter = RegisteredTrialAdapter(tmp_path / 'trials.jsonl')
    plan = dict(request_id='unit-only', plan_sha256='a'*64, frozen_at='2026-01-01T00:00:00Z',
                settings=dict(start='2020-01-01', end='2021-01-01', split='2020-06-01',
                              segments=[], symbols=['SYNTHETIC']), code_files={'test': 'b'*64},
                dataset={'sha256': 'c'*64})
    exp = dict(experiment_id='MA5-h1', factor_variant_id='test-factor', definition_revision='d'*64,
               implementation_id='test-only', parameters={}, horizon_bars=1)
    registration = adapter.register(plan, [exp])
    assert adapter.registry.snapshot([registration['campaign_id']])['completed_trials'] == 0
    with pytest.raises(ValueError, match='transition'):
        adapter.complete(registration, {'status':'SUCCESS', 'run_id':'test-run',
                         'mapping': {'identity': {'factor_variant_id': 'test-factor'}}})
    adapter.start(registration, 'test-factor')
    failed = {'status':'FAILED', 'run_id':'test-run', 'mapping': {'identity': {'factor_variant_id': 'test-factor'}}}
    assessment = adapter.complete(registration, failed)
    assert assessment['holdout_evidence_status'] == 'OBSERVED'
    assert assessment['permitted_conclusion_level'] == 'EXPLORATORY_RESULT'
    assert assessment['registry_selection_scope']['observed_trials'] == 1
    assert assessment['registry_selection_scope']['history_completeness'] == 'UNKNOWN'
    assert assessment['statistical_methods_applicability']['dsr']['status'] == 'NOT_APPLICABLE'
    assert adapter.evaluate(registration, [failed]) == assessment
    assert adapter.register(plan, [exp]) == registration


def test_web_draft_requires_same_definition_and_reviewed_scope(tmp_path):
    pytest.importorskip("quantgraph", reason="Explicit optional Graph SDK dependency")
    from strategy_lab.factor_study.request_adapter import resolve_request
    root = Path(__file__).resolve().parents[1]
    graph = root.parent / 'quant-knowledge-graph'
    if not (graph / 'contracts/factor-study/v1').exists():
        pytest.skip('Explicit sibling Graph SDK integration dependency not installed')
    selection = json.loads((root / 'research/platform/factor-research-loop/specs/graph-selection-v1.json').read_text())
    request = copy.deepcopy(selection['request'])
    settings = request['requested_settings']
    request['requested_settings'] = {'market': 'crypto', 'notes': 'synthetic adapter test'}
    draft, review = tmp_path/'request.json', tmp_path/'settings.json'
    draft.write_text(json.dumps(request))
    review.write_text(json.dumps(settings))
    assert resolve_request(draft, review, graph)['request'] == request
    request['requested_settings']['market'] = 'equity'
    draft.write_text(json.dumps(request))
    with pytest.raises(ValueError, match='scope'):
        resolve_request(draft, review, graph)
    request['requested_settings'] = {}
    request['entity_refs'][0]['definition_revision'] = digest('stale')
    draft.write_text(json.dumps(request))
    with pytest.raises(ValueError, match='stale'):
        resolve_request(draft, review, graph)
