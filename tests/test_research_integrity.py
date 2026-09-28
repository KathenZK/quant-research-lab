"""Synthetic integrity regressions; all ledgers, data and outputs are isolated."""
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
import multiprocessing
from pathlib import Path
import sys

import numpy as np
import pytest

from strategy_lab.research.accounting import digest
from strategy_lab.research.exposure import read_ledger
from strategy_lab.research.integrity import (
    adjudicate_research, assess_holdout, assess_research_integrity, write_assessment_revision,
)
from strategy_lab.research.statistics import assemble_dsr, dsr_from_moments, deflated_sharpe, evaluate_pbo, pbo
from strategy_lab.research.trials import TrialRegistry

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'tests/fixtures/statistical_reference_v2.json').read_text())


def spec(**changes):
    return dict(hypothesis_family_id='family-a', selection_campaign_id='campaign', identity='strategy-v1',
                parameters={'n': 5}, label_horizon=1, objective='net Sharpe', selection_rule='best observed',
                dataset_fingerprint='a'*64, sample_fingerprint='b'*64, code_hash='c'*64,
                config_hash='d'*64, parent_experiment_id=None, **{}) | changes


def registry(tmp_path, history='COMPLETE_DECLARED'):
    r = TrialRegistry(tmp_path / 'trials.jsonl')
    r.register_campaign('campaign', selection_goal='Choose one comparable return strategy',
                        scope_definition='All families considered for this specific selection; no unrelated studies',
                        history_completeness=history, history_reason='Synthetic closed test universe', evidence_refs=['test protocol'])
    return r


def completed(r, experiment='exp', **changes):
    aid = r.plan(experiment, spec(**changes))
    r.record(aid, event_id='start', state='started', results_observed='UNOBSERVED', affects_selection='NO', reason='started')
    r.record(aid, event_id='complete', state='completed', results_observed='OBSERVED', affects_selection='YES', reason='result observed, including negatives')
    return aid


def numeric_scope(tmp_path, n=12, history='COMPLETE_DECLARED'):
    r = registry(tmp_path, history)
    inputs = {}
    for i in range(n):
        aid = completed(r, parameters={'n': i}, hypothesis_family_id='family-' + str(i % 2))
        mean = .015 if i == n-1 else -.005 + i * .0005
        inputs[aid] = dict(kind='STRATEGY_RETURNS', values=(np.random.default_rng(20260928 + i).normal(0, .005, 1024) + mean).tolist(),
                           dataset_fingerprint='a'*64, sample_fingerprint='b'*64, periods_per_year=252)
    return r, inputs, aid


def dsr_args():
    return dict(dependence={'method': 'INDEPENDENT', 'rationale': 'Assumption for synthetic API test, not inferred from count',
                            'evidence_refs': ['synthetic protocol']},
                return_assumptions={'sampling': 'IID_APPROXIMATION', 'evidence_refs': ['synthetic assumption']})


def pbo_context():
    return dict(input_kind='FIXED_CANDIDATE_RETURNS', synchronous=True, future_information=False,
                preprocessing='NONE_OR_CAUSAL', overlapping_labels=False, boundary_policy='CONTINUOUS_CAUSAL_ACCOUNT',
                selection_scope_complete=True, protocol_frozen_before_results=True,
                dependence_review='Synthetic API test', block_justification='Eight equal blocks fixed before results',
                evidence_refs=['synthetic protocol'])


def test_retry_and_config_changes(tmp_path):
    r = registry(tmp_path)
    aid = r.plan('exp', spec())
    assert r.plan('exp', spec()) == aid
    r.record(aid, event_id='start', state='started', results_observed='UNOBSERVED', affects_selection='NO', reason='start')
    r.record(aid, event_id='fail', state='failed', results_observed='UNOBSERVED', affects_selection='NO', reason='process failure')
    assert r.plan('exp', spec()) == aid
    retry = dict(event_id='retry', state='started', results_observed='UNOBSERVED', affects_selection='NO', reason='identical retry')
    assert r.record(aid, **retry) == r.record(aid, **retry)
    r.record(aid, event_id='done', state='completed', results_observed='OBSERVED', affects_selection='YES', reason='negative result retained')
    assert r.record(aid, **retry)['data']['event_id'] == 'retry'  # late delivery is idempotent
    for key, value in [('parameters', {'n': 6}), ('label_horizon', 2), ('identity', 'model-v2'), ('selection_rule', 'different choice')]:
        assert r.plan('exp', spec(**{key: value})) != aid
    snap = r.snapshot(['campaign'])
    assert snap['raw_attempts'] == 5 and snap['completed_trials'] == 1
    assert snap['selection_trial_ids'] == [aid]  # collected/planned models are not completed trials
    assert [e['data']['state'] for e in snap['attempts'][0]['events']] == ['started', 'failed', 'started', 'completed']
    with pytest.raises(ValueError, match='conflicting'):
        r.record(aid, **(retry | {'reason': 'changed intent'}))
    with pytest.raises(ValueError, match='erase'):
        r.record(aid, event_id='hide', state='completed', results_observed='UNOBSERVED', affects_selection='NO', reason='hide')


def _parallel_plan(args):
    path, i = args
    r = TrialRegistry(path)
    return r.plan('exp', spec(parameters={'n': i % 4}))


def test_multiprocess_registration_no_duplicates_or_losses(tmp_path):
    r = registry(tmp_path)
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context('spawn')) as pool:
        ids = list(pool.map(_parallel_plan, [(r.path, i) for i in range(24)]))
    assert len(set(ids)) == 4
    assert r.snapshot(['campaign'])['raw_attempts'] == 4
    assert len(read_ledger(r.path)) == 5


def test_failure_abortion_import_uncertainty_remain(tmp_path):
    r = registry(tmp_path)
    aid = r.plan('old', spec(), historical_import=True, import_source='retained report', import_completeness='UNKNOWN')
    r.record(aid, event_id='start', state='started', results_observed='UNKNOWN', affects_selection='UNKNOWN', reason='import source lacks chronology')
    r.record(aid, event_id='aborted', state='aborted', results_observed='OBSERVED', affects_selection='YES', reason='partial results influenced selection')
    snap = r.snapshot(['campaign'])
    assert snap['history_completeness'] == 'UNKNOWN'
    assert snap['completed_trials'] == 0 and snap['observed_trials'] == 1
    assert aid in snap['selection_trial_ids']
    assert snap['attempts'][0]['timestamps']['aborted']


def test_scope_crosses_families_but_not_unrelated_campaigns(tmp_path):
    r = registry(tmp_path)
    a = completed(r)
    b = completed(r, hypothesis_family_id='family-b', parameters={'n': 20})
    r.register_campaign('unrelated', selection_goal='Different task', scope_definition='Separate data and decision', history_reason='unknown')
    completed(r, selection_campaign_id='unrelated', dataset_fingerprint='f'*64)
    snap = r.snapshot(['campaign'])
    assert set(snap['selection_trial_ids']) == {a, b}
    assert snap['raw_attempts'] == 2


@pytest.mark.parametrize('history', ['UNKNOWN', 'INCOMPLETE'])
def test_dsr_incomplete_history_degrades_without_erasing_numeric_diagnostic(tmp_path, history):
    r, values, selected = numeric_scope(tmp_path, history=history)
    result = assemble_dsr(r.snapshot(['campaign']), values, selected_attempt_id=selected, **dsr_args())
    assert result['status'] == 'CONDITIONAL' and result['value'] is not None
    assert result['decision_use'] == 'DIAGNOSTIC_ONLY' and not result['full_historical_correction']
    assert result['selection_scope']['history_completeness'] == history


def test_dsr_scope_and_dependence_are_required(tmp_path):
    r, values, selected = numeric_scope(tmp_path)
    scope = r.snapshot(['campaign'])
    result = assemble_dsr(scope, values, selected_attempt_id=selected)
    assert result['status'] == 'NOT_ESTIMABLE' and result['value'] is None
    small = {selected: values[selected]}
    result = assemble_dsr(scope, small, selected_attempt_id=selected, **dsr_args())
    assert result['status'] == 'NOT_ESTIMABLE' and 'missing=' in result['reasons'][0]
    result = assemble_dsr(scope, values, selected_attempt_id=selected, **dsr_args())
    assert result['effective_independent_trials'] == 12
    assert set(result['trial_sharpes']) == set(scope['selection_trial_ids'])
    assert result['trial_sharpe_variance'] > 0
    args = dsr_args()
    args['dependence'].update(method='SENSITIVITY', effective_trials=[2, 6, 12])
    result = assemble_dsr(scope, values, selected_attempt_id=selected, **args)
    assert result['value'] is None and result['status'] == 'CONDITIONAL'
    assert len(result['sensitivity']) == 3


@pytest.mark.parametrize('mutation', ['ic', 'incomparable', 'nan', 'constant', 'short', 'fingerprint'])
def test_dsr_invalid_inputs_not_estimable(tmp_path, mutation):
    r, values, selected = numeric_scope(tmp_path)
    if mutation == 'ic':
        values[selected]['kind'] = 'FACTOR_IC'
    elif mutation == 'incomparable':
        values[selected]['periods_per_year'] = 365
    elif mutation == 'fingerprint':
        values[selected]['sample_fingerprint'] = 'f'*64
    else:
        values[selected]['values'] = {'nan': [0, .1, np.nan, .2], 'constant': [1]*1024, 'short': [0, .1]}[mutation]
    result = assemble_dsr(r.snapshot(['campaign']), values, selected_attempt_id=selected, **dsr_args())
    assert result['status'] == 'NOT_ESTIMABLE'
    if mutation == 'ic':
        assert result['applicability_status'] == 'NOT_APPLICABLE'


def test_new_math_keeps_frozen_dsr_and_cscv_reference_values():
    case = FIXTURE['dsr']
    actual = deflated_sharpe(case['returns'], trial_sharpes=case['trial_sharpes'], effective_trials=6)
    for key, value in case['expected'].items():
        assert actual[key] == pytest.approx(value, abs=1e-13)
    case = FIXTURE['pbo']
    actual = pbo(case['returns_by_trial'], blocks=4)
    expected = [(v, 1/len(s['logits'])) for s in case['splits'] for v in s['logits']]
    np.testing.assert_allclose(actual['weighted_logits'], expected, atol=1e-13)
    assert actual['value'] == pytest.approx(2/3)


@pytest.mark.parametrize('n,skew,kurt,value', [(100, -3, 10, .9004), (46, -3, 10, .9505), (88, 0, 3, .9505)])
def test_paper_annualization_example(n, skew, kurt, value):
    r = dsr_from_moments(sr=2.5/np.sqrt(250), trial_variance=.5/250, effective_trials=n,
                         observations=1250, skew=skew, kurtosis=kurt)
    assert r['value'] == pytest.approx(value, abs=5e-5)


@pytest.mark.parametrize('context,status', [({}, 'UNKNOWN'), ({'input_kind': 'FOLD_FITTED_PREDICTIONS'}, 'NOT_APPLICABLE'),
    ({'input_kind': 'FIXED_CANDIDATE_RETURNS', 'overlapping_labels': True}, 'CONDITIONAL'),
    ({'input_kind': 'FIXED_CANDIDATE_RETURNS', 'preprocessing': 'FULL_SAMPLE_FIT'}, 'NOT_APPLICABLE')])
def test_pbo_applicability_is_separate_from_numeric_value(context, status):
    r = evaluate_pbo(FIXTURE['pbo']['returns_by_trial'], blocks=4, context=context)
    assert r['status'] == 'COMPUTED' and r['applicability_status'] == status
    assert r['decision_use'] == 'DIAGNOSTIC_ONLY' and r['purged'] is False


def test_fixed_causal_pbo_needs_no_mechanical_purge(tmp_path):
    r, values, _ = numeric_scope(tmp_path)
    scope = r.snapshot(['campaign'])
    ids = scope['selection_trial_ids']
    matrix = np.column_stack([values[i]['values'] for i in ids])
    result = evaluate_pbo(matrix, context=pbo_context(), selection_scope=scope, trial_ids=ids)
    assert result['applicability_status'] == 'APPLICABLE'
    assert result['decision_use'] == 'DECISION_SUPPORT' and result['value'] == 0
    bad = evaluate_pbo(matrix, context=pbo_context(), selection_scope=scope, trial_ids=ids[::-1][1:])
    assert bad['decision_use'] == 'DIAGNOSTIC_ONLY'


def holdout_fixture(tmp_path, monkeypatch, r=None):
    import strategy_lab.research.exposure as exposure
    class Clock(datetime):
        instant = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
        @classmethod
        def now(cls, tz=None):
            return cls.instant
    monkeypatch.setattr(exposure, 'datetime', Clock)
    r = r or registry(tmp_path)
    contract = dict(frozen_at='2024-01-01T00:00:00Z', oos_start='2025-01-01T00:00:00Z',
                    oos_end='2026-01-01T00:00:00Z', holdout_status='UNOBSERVED_AT_FREEZE')
    plan = dict(contract_hash=digest(contract), plan_frozen_at=contract['frozen_at'], dataset_version='logical-dataset-v1',
                sample_fingerprint='b'*64, sample_start=contract['oos_start'], sample_end=contract['oos_end'],
                protocol='PROSPECTIVE_AFTER_FREEZE_SINGLE_USE', max_uses=1, known_access_records=[],
                access_history_status='KNOWN_RECORDS_REVIEWED', evidence_refs=['known access audit checkpoint'])
    r.freeze_holdout('h', plan)
    Clock.instant = datetime(2026, 1, 2, tzinfo=timezone.utc)
    r.use_holdout('h', use_id='validation', dataset_fingerprint='a'*64, reason='first reveal')
    return r, contract, plan


def test_contract_unobserved_claim_or_missing_evidence_is_unknown():
    assert assess_holdout({'holdout_status': 'UNOBSERVED_AT_FREEZE'})['status'] == 'UNKNOWN'
    a = assess_research_integrity(study_kind='CONFIRMATORY_HOLDOUT_TEST', contract={})
    assert 'HOLDOUT_EVIDENCE_NOT_CONFIRMATORY' in a['blockers']
    assert a['computation_permitted']


def test_known_observation_cannot_be_upgraded(tmp_path, monkeypatch):
    r, c, _ = holdout_fixture(tmp_path, monkeypatch)
    args = dict(evidence=r.holdout_evidence('h'), dataset_fingerprint='a'*64)
    assert assess_holdout(c, **args)['status'] == 'DOCUMENTED_PROSPECTIVE_PROTOCOL'
    assert assess_holdout(c | {'holdout_status': 'RETROSPECTIVE_PREVIOUSLY_OBSERVED'}, **args)['status'] == 'OBSERVED'
    records = [{'data': dict(kind='exposure', window_start=c['oos_start'], window_end=c['oos_end'])}]
    assert assess_holdout(c, exposure_records=records, **args)['status'] == 'OBSERVED'
    assert assess_holdout(c, evidence=r.holdout_evidence('h'), dataset_fingerprint='f'*64)['status'] == 'UNKNOWN'


def test_relabelled_holdout_does_not_reset_usage(tmp_path, monkeypatch):
    r, c, plan = holdout_fixture(tmp_path, monkeypatch)
    r.use_holdout('h', use_id='validation', dataset_fingerprint='a'*64, reason='first reveal')
    assert len(r.holdout_evidence('h')['use_records']) == 1
    r.freeze_holdout('new-name', plan | {'sample_fingerprint': 'f'*64})
    r.use_holdout('new-name', use_id='second', dataset_fingerprint='a'*64, reason='repeat inspection')
    result = assess_holdout(c, evidence=r.holdout_evidence('new-name'), dataset_fingerprint='a'*64)
    assert result['status'] == 'REUSED' and result['use_count'] == 2


def test_late_freeze_never_establishes_prospective_holdout(tmp_path):
    r = registry(tmp_path)
    c = dict(frozen_at='2000-01-01T00:00:00Z', oos_start='2001-01-01T00:00:00Z', oos_end='2002-01-01T00:00:00Z')
    plan = dict(contract_hash=digest(c), plan_frozen_at=c['frozen_at'], dataset_version='v1', sample_fingerprint='b'*64,
                sample_start=c['oos_start'], sample_end=c['oos_end'], protocol='PROSPECTIVE_AFTER_FREEZE_SINGLE_USE',
                max_uses=1, known_access_records=[], access_history_status='KNOWN_RECORDS_REVIEWED', evidence_refs=['self claim'])
    r.freeze_holdout('h', plan)
    r.use_holdout('h', use_id='x', dataset_fingerprint='a'*64, reason='historical replay')
    assert assess_holdout(c, evidence=r.holdout_evidence('h'), dataset_fingerprint='a'*64)['status'] == 'UNKNOWN'


def good_result(dsr=None, pb=None):
    return dict(oos=dict(observations=1000, closed_trades=40, total_return=.2, sharpe=1.5, max_drawdown=.1),
                deflated_sharpe=dsr or {'status': 'COMPUTED', 'value': .99}, pbo=pb or {'status': 'COMPUTED', 'value': .01})


def test_historical_and_unknown_can_compute_but_not_confirm():
    for kind in ['HISTORICAL_REPLICATION', 'EXPLORATORY_ANALYSIS', None]:
        a = assess_research_integrity(study_kind=kind)
        assert a['computation_permitted'] and adjudicate_research(good_result(), a) == 'INCONCLUSIVE'
    a = assess_research_integrity(study_kind='HISTORICAL_REPLICATION')
    assert a['permitted_conclusion_level'] == 'REPRODUCIBLE_HISTORICAL_RESULT'


def test_confirmation_is_possible_but_diagnostic_pbo_cannot_pass(tmp_path, monkeypatch):
    r, values, selected = numeric_scope(tmp_path)
    r, c, _ = holdout_fixture(tmp_path, monkeypatch, r)
    scope = r.snapshot(['campaign'])
    dsr = assemble_dsr(scope, values, selected_attempt_id=selected, **dsr_args())
    ids = scope['selection_trial_ids']
    pb = evaluate_pbo(np.column_stack([values[i]['values'] for i in ids]), context=pbo_context(), selection_scope=scope, trial_ids=ids)
    result = good_result(dsr, pb)
    args = dict(study_kind='CONFIRMATORY_HOLDOUT_TEST', contract=c, selection_scope=scope,
                holdout_evidence=r.holdout_evidence('h'), dataset_fingerprint='a'*64)
    assessment = assess_research_integrity(statistical_methods={'dsr': dsr, 'pbo': pb}, **args)
    assert assessment['blockers'] == []
    assert adjudicate_research(result, assessment) == 'RESEARCH_PASSED'
    for status in ['DIAGNOSTIC_ONLY', 'NOT_APPLICABLE']:
        bad = pb | ({'decision_use': status} if status == 'DIAGNOSTIC_ONLY' else {'applicability_status': status})
        a = assess_research_integrity(statistical_methods={'dsr': dsr, 'pbo': bad}, **args)
        assert adjudicate_research(good_result(dsr, bad), a) == 'INCONCLUSIVE'
    # Stale assessment of another result cannot pass.
    assert adjudicate_research(good_result(dsr, pb | {'value': .5}), assessment) == 'INCONCLUSIVE'
    bad = deepcopy(result)
    bad['oos']['total_return'] = -.1
    assert adjudicate_research(bad, assessment) == 'RESEARCH_FAILED'


def test_legacy_adjudicator_fails_closed_and_revision_is_append_only(tmp_path):
    path = ROOT / 'research/platform/quantgraph-integration/scripts'
    sys.path.insert(0, str(path))
    try:
        loader = importlib.util.spec_from_file_location('integrity_v4_test', path / 'research_v4.py')
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
    finally:
        sys.path.remove(str(path))
    assert module.adjudicate(good_result()) == 'INCONCLUSIVE'
    old = tmp_path / 'frozen.json'
    old.write_text(json.dumps(good_result()))
    before = old.read_bytes()
    a = assess_research_integrity(study_kind='HISTORICAL_REPLICATION')
    revision = tmp_path / 'revision.json'
    data = write_assessment_revision(revision, original_result_path=old, assessment=a, research_status='INCONCLUSIVE')
    assert old.read_bytes() == before and data['original_result_sha256']
    with pytest.raises(FileExistsError):
        write_assessment_revision(revision, original_result_path=old, assessment=a, research_status='INCONCLUSIVE')


def load_study():
    path = ROOT / 'research/platform/quantgraph-integration/scripts/research_v3.py'
    loader = importlib.util.spec_from_file_location('registered_study_test', path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def synthetic_study_input():
    import pandas as pd
    close = 100 + np.sin(np.arange(128) / 3) * 10 + np.arange(128) / 10
    bars = pd.DataFrame(dict(ts=pd.date_range('2020-01-01', periods=128, tz='UTC'),
                             open=close, close=close, high=close+1, low=close-1, volume=1.))
    contract = dict(signal='PRICE_SMA', parameters=[3], parameter_grid=[[2], [3], [4]],
                    initial_cash=1000, evaluation_start='2020-01-01T00:00:00Z', minutes=1440,
                    fee_bps=10, slippage_bps=4, stop_loss_fraction=None, take_profit_fraction=None,
                    oos_start=str(bars.ts.iloc[64]), stress_cost_multipliers=[2], limitations=['synthetic test only'])
    return bars, contract


def test_study_registers_before_replay_and_retry_reuses_attempts(tmp_path, monkeypatch):
    module = load_study()
    bars, contract = synthetic_study_input()
    r = registry(tmp_path)
    original = module.engine.replay
    seen = []
    def replay(*args, **kwargs):
        seen.append(r.snapshot(['campaign'])['raw_attempts'])
        return original(*args, **kwargs)
    monkeypatch.setattr(module.engine, 'replay', replay)
    context = dict(registry_path=r.path, selection_campaign_id='campaign', experiment_id='experiment',
                   **dsr_args())
    result = module.study(bars, contract, tmp_path / 'first', trial_context=context)
    assert seen == [1, 2, 3, 4]
    assert result['trial_registry']['raw_attempts'] == 4
    assert result['trial_registry']['completed_trials'] == 4
    assert len(result['trial_registry']['selection_trial_ids']) == 3
    assert len(result['deflated_sharpe']['trial_sharpes']) == 3
    assert result['pbo']['decision_use'] == 'DIAGNOSTIC_ONLY'
    other = module.study(bars, contract, tmp_path / 'retry', trial_context=context)
    assert result['attempt_ids'] == other['attempt_ids']
    assert other['trial_registry']['raw_attempts'] == 4
    # A candidate from a different family in the same campaign is not hidden.
    completed(r, 'earlier-experiment', hypothesis_family_id='other-family')
    third = module.study(bars, contract, tmp_path / 'with-history', trial_context=context)
    assert third['deflated_sharpe']['status'] == 'NOT_ESTIMABLE'
    assert third['trial_registry']['raw_attempts'] == 5


def test_study_failure_is_retained(tmp_path, monkeypatch):
    module = load_study()
    bars, contract = synthetic_study_input()
    r = registry(tmp_path)
    def fail(*args, **kwargs):
        raise ValueError('synthetic crash')
    monkeypatch.setattr(module.engine, 'replay', fail)
    with pytest.raises(ValueError, match='synthetic crash'):
        module.study(bars, contract, tmp_path / 'failed', trial_context=dict(
            registry_path=r.path, selection_campaign_id='campaign', experiment_id='experiment'))
    snapshot = r.snapshot(['campaign'])
    assert snapshot['attempts'][0]['state'] == 'failed' and snapshot['completed_trials'] == 0


@pytest.mark.parametrize('field', ['observations', 'closed_trades', 'total_return', 'sharpe', 'max_drawdown'])
def test_missing_decision_fields_are_inconclusive(field):
    result = good_result()
    result['oos'][field] = None
    assert adjudicate_research(result) == 'INCONCLUSIVE'


def test_non_integer_constant_returns_are_undefined():
    with pytest.raises(ValueError, match='variance'):
        deflated_sharpe([.01]*1000, trial_sharpes=[.1, .2], effective_trials=2)
    result = evaluate_pbo(np.full((32, 3), .01))
    assert result['status'] == 'NOT_ESTIMABLE'


def test_edited_scope_cannot_be_used_for_statistics(tmp_path):
    r, values, selected = numeric_scope(tmp_path)
    scope = r.snapshot(['campaign'])
    scope['selection_trial_ids'] = [selected]
    result = assemble_dsr(scope, values, selected_attempt_id=selected, **dsr_args())
    assert result['status'] == 'NOT_ESTIMABLE'


def test_v4_orchestration_preserves_historical_identity(tmp_path, monkeypatch):
    """Admission is stubbed, not claimed; test only the V4 orchestration wiring."""
    path = ROOT / 'research/platform/quantgraph-integration/scripts'
    sys.path.insert(0, str(path))
    try:
        loader = importlib.util.spec_from_file_location('integrity_v4_wiring', path / 'research_v4.py')
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
    finally:
        sys.path.remove(str(path))
    bars, config = synthetic_study_input()
    c = dict(engine_config=config, experiment_family_id='family', strategy_variant_id='variant',
             strategy_concept_id='concept', strategy_template_id='template', trial_count=3, prior_trial_count=500,
             oos_start=config['oos_start'], oos_end=str(bars.ts.iloc[-1]),
             frozen_at='2026-01-01T00:00:00Z', holdout_status='RETROSPECTIVE_PREVIOUSLY_OBSERVED')
    manifest = dict(dataset_sha256='a'*64, rights_sha256='f'*64)
    cp, mp = tmp_path / 'contract.json', tmp_path / 'manifest.json'
    cp.write_text(json.dumps(c))
    mp.write_text(json.dumps(manifest))
    monkeypatch.setattr(module, 'read_market_dataset', lambda *a, **k: (bars, c, manifest, {'rights_id': 'test'}, {}))
    monkeypatch.setattr(module, 'check_contract_binding', lambda *a, **k: None)
    from strategy_lab.knowledge import market_contract
    monkeypatch.setattr(market_contract, 'validate_candidate_binding', lambda *a, **k: None)
    envelope_calls = []
    def envelope(**kwargs):
        envelope_calls.append(kwargs)
        return {'synthetic_admission_stub': True}
    monkeypatch.setattr(module, 'market_evidence_v4', envelope)
    report = module.run(cp, mp, tmp_path / 'result', candidate={'synthetic_admission_stub': True})
    assessment = report['integrity_assessment']
    assert assessment['study_kind'] == 'HISTORICAL_REPLICATION'
    assert assessment['holdout_evidence_status'] == 'OBSERVED'
    assert report['research_status'] != 'RESEARCH_PASSED'
    assert report['results']['deflated_sharpe']['status'] == 'NOT_ESTIMABLE'
    assert report['results']['pbo']['decision_use'] == 'DIAGNOSTIC_ONLY'
    assert envelope_calls[0]['research_status'] == report['research_status']
    assert 'src/strategy_lab/research/integrity.py' in report['code_manifest']
