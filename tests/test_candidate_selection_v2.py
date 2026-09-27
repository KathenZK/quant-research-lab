from strategy_lab.knowledge.candidates import select_candidates, collect_candidates
from test_quantgraph_integration import candidate
import pytest


def test_minimum_and_target_shortfalls_are_different():
    rows = [candidate('v' + str(i), 't' + str(i), True) for i in range(120)]
    report = select_candidates(rows, target=200)
    assert report['eligible_count'] == 120
    assert report['minimum_shortfall'] == 0 and report['target_shortfall'] == 80
    assert 'shortfall' not in report


def test_diversity_precedes_ids_and_parameter_enumeration():
    rows = [candidate('v' + str(i), 'aaa-' + str(i), True) for i in range(120)]
    last = candidate('last', 'zzz', True)
    last['variant']['strategy_concept_id'] = 'new-concept'
    rows.append(last)
    report = select_candidates(rows, target=100)
    assert report['selected_concepts'] == 2
    assert report['selected'][1]['concept_id'] == 'new-concept'
    assert select_candidates(rows[::-1], target=100)['selected'] == report['selected']


def test_upstream_blocker_cannot_be_overruled_by_score_or_returns():
    row = candidate(eligible=True)
    row['candidate_quality_score'] = 10000
    row['candidate_gate'] = {'gate_version': 'research-candidate-gate-v2', 'eligible': False, 'blockers': ['EXPIRED_RIGHTS']}
    assert select_candidates([row])['selected_count'] == 0


def test_stale_projection_is_not_an_empty_universe():
    class Client:
        def export_research_candidates(self, **kwargs):
            return {'scope': 'TRIAGE_ONLY', 'items': [], 'projection_status': 'STALE'}
    with pytest.raises(ValueError, match='projection'):
        collect_candidates(Client())


@pytest.mark.parametrize('field,value', [('costs', {}), ('costs', {'fee_bps': -1, 'slippage_bps': 0}), ('closed_bar_only', False)])
def test_lab_independently_rejects_incomplete_execution_even_if_upstream_says_eligible(field, value):
    row = candidate(eligible=True)
    row['candidate_gate'] = {'gate_version': 'research-candidate-gate-v2', 'eligible': True}
    row['execution_contract'][field] = value
    report = select_candidates([row])
    assert report['eligible_count'] == 0
    assert 'EXECUTION_CONTRACT_PENDING' in report['candidates'][0]['variant_blockers']['v1']
