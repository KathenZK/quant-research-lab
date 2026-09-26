import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest
from strategy_lab.knowledge.candidates import select_candidates, public_summary
from strategy_lab.knowledge.results import evidence_envelope
from strategy_lab.knowledge.promotion import export_artifact, validate_artifact

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('qg_metrics', ROOT / 'research/_shared-kernels/quantgraph-diagnostics/v1/metrics.py')
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def candidate(variant='v1', template='t1', eligible=False):
    return {'variant': {'strategy_template_id': template, 'strategy_concept_id': 'c1',
            'strategy_variant_id': variant, 'spec_sha256': 'a' * 64, 'source_url': 'https://example.org',
            'source_verification': 'VERIFIED' if eligible else 'NOT_INDEPENDENTLY_VERIFIED',
            'rule_ast': {'type': 'threshold_switch'}}, 'definition_admitted': True,
            'research_allowed': eligible, 'research_rights_status': 'ALLOWED' if eligible else 'REVIEW_REQUIRED',
            'data_available': eligible,
            'execution_contract': {'timing': 'next_bar', 'costs': {'fee': 0.001},
                                   'price_adjustment': 'adjusted', 'missing_data_policy': 'fail'}}


def test_template_variants_do_not_inflate_independence_or_rights():
    rows = [candidate('v1'), candidate('v2'), candidate('v3')]
    report = select_candidates(rows)
    assert report['templates'] == 1 and report['selected_count'] == report['research_runs'] == 0
    assert report['candidates'][0]['planned_trial_count'] == 3
    assert report['status'] == 'INSUFFICIENT_EVIDENCE'
    assert public_summary(report)['blockers']['RIGHTS_REVIEW_REQUIRED'] == 3
    assert select_candidates(rows[::-1])['candidates'] == report['candidates']


def test_ready_candidates_require_all_independent_gates():
    rows = [candidate('v' + str(i), 't' + str(i), True) for i in range(120)]
    report = select_candidates(rows, target=100)
    assert report['selected_count'] == 100 and report['templates'] == 120
    rows[0]['research_allowed'] = False
    assert select_candidates(rows)['selected_count'] == 119


def test_selected_template_excludes_unapproved_parameter_siblings():
    allowed = candidate('allowed', eligible=True)
    blocked = candidate('blocked')
    blocked['variant']['source_url'] = 'https://example.org/restricted'
    report = select_candidates([blocked, allowed])
    assert report['candidates'][0]['planned_trial_count'] == 2
    chosen = report['selected'][0]
    assert chosen['source_strategy_ids'] == chosen['eligible_variants'] == ['allowed']
    assert chosen['planned_trial_count'] == 1
    assert [p['variant_id'] for p in chosen['parameter_grid']] == ['allowed']
    assert chosen['source_urls'] == ['https://example.org']
    assert chosen['variant_blockers'] == {'allowed': []}
    assert select_candidates([allowed, blocked])['selected'] == report['selected']


def test_evidence_uncomputed_metrics_null_and_identity_immutable():
    args = dict(family_id='qg-test', source_strategy_ids=['v1'], contract={'costs': 0.001}, trial_count=3,
                artifact_uri='fixture:local', artifact_sha256='a' * 64, results={}, evidence_kind='PIPELINE_DIAGNOSTIC')
    value = evidence_envelope(**args)
    assert all(x['value'] is None for x in value['results'].values())
    assert evidence_envelope(**args)['research_run_id'] == value['research_run_id']
    args['trial_count'] = 4
    assert evidence_envelope(**args)['research_run_id'] != value['research_run_id']


def test_metrics_initial_drawdown_and_dsr_trial_penalty():
    r = np.array([-0.2, 0.1, 0.02, -0.01, 0.01] * 20)
    assert metrics.performance([-0.2, 0.1, 0.02])['max_drawdown'] == pytest.approx(0.2)
    trials = np.linspace(-0.2, 0.2, 100)
    low = metrics.deflated_sharpe(r, trial_sharpes=trials, effective_trials=2)
    high = metrics.deflated_sharpe(r, trial_sharpes=trials, effective_trials=100)
    assert high['value'] <= low['value'] and high['benchmark_sr'] > low['benchmark_sr']
    assert metrics.plateau([1, 2, 2.1, 2, 1])['contiguous_width'] == 3
    with pytest.raises(ValueError):
        metrics.deflated_sharpe([1, 1, 1, 1], trial_sharpes=trials, effective_trials=2)


def test_pbo_ties_and_stable_winner():
    base = np.tile([-0.01, 0.02, 0.0, 0.01], 16)
    x = np.column_stack([base, base + 0.005, base - 0.003])
    assert metrics.pbo(x)['value'] == 0
    assert metrics.pbo(np.column_stack([base, base]))['value'] == 1
    with pytest.raises(ValueError):
        metrics.pbo(x[:-1])


def test_paper_artifact_roundtrip_and_live_refusal(tmp_path):
    value = json.loads((ROOT / 'contracts/synthetic-paper-artifact.json').read_text())
    saved = export_artifact(value, tmp_path / 'artifact.json')
    assert saved['sha256'] == hashlib.sha256((tmp_path / 'artifact.json').read_bytes()).hexdigest()
    assert (tmp_path / 'artifact.json').read_bytes() == (ROOT / 'contracts/synthetic-paper-artifact.json').read_bytes()
    assert not saved['runtime_enabled']
    with pytest.raises(ValueError, match='Live activation'):
        validate_artifact(value, environment='live')
    for key, replacement in [('promotion_status', 'REVIEW'), ('approved_at', '2999-01-01T00:00:00Z')]:
        bad = copy.deepcopy(value)
        bad[key] = replacement
        with pytest.raises(Exception):
            validate_artifact(bad)
