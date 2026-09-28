"""Group structural templates before research. Unknown rights never pass admission."""
from collections import Counter
import hashlib
import json
import math


SUPPORTED_GATE_VERSION = 'research-candidate-gate-v4'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def collect_candidates(client):
    rows, offset = [], 0
    while True:
        page = client.export_research_candidates(limit=1000, offset=offset)
        if page.get('scope') != 'TRIAGE_ONLY':
            raise ValueError('Unexpected candidate export contract')
        if page.get('projection_status') != 'READY':
            raise ValueError('UPSTREAM_CONTRACT_UNSUPPORTED: projection_status must explicitly be READY')
        items = page['items']
        if not items:
            break
        rows.extend(items)
        offset += len(items)
    return rows


def select_candidates(rows, *, target=20, minimum_required=1):
    if not 1 <= target <= 300:
        raise ValueError('Research target must be 1..300 independent templates')
    if not 1 <= minimum_required <= target:
        raise ValueError('minimum_required must be positive and <= target')
    groups, excluded, source_urls = {}, Counter(), {}
    for row in rows:
        v = row['variant']
        template_id = v.get('strategy_template_id')
        if not template_id or not v.get('rule_ast') or not row.get('definition_admitted'):
            excluded['RULE_INCOMPLETE'] += 1
            continue
        # All sources of one structural template share a testing family. Citation
        # changes, ETF substitution and threshold enumeration do not inflate N.
        group = groups.setdefault(template_id, {'experiment_family_id': 'qg-' + digest(template_id)[:24],
            'template_id': template_id, 'concept_id': v['strategy_concept_id'], 'source_strategy_ids': [],
            'parameter_grid': [], 'source_urls': set(), 'variant_blockers': {}, 'eligible_variants': [],
            'readiness_scores': {}, 'diversity_metadata': row.get('diversity_metadata', {})})
        vid = v['strategy_variant_id']
        source_urls[vid] = v['source_url']
        group['source_strategy_ids'].append(vid)
        group['parameter_grid'].append({'variant_id': vid, 'spec_sha256': v['spec_sha256'], 'rule_ast': v['rule_ast']})
        group['source_urls'].add(v['source_url'])
        blockers = []
        if row.get('research_allowed') is not True or row.get('research_rights_status') != 'ALLOWED':
            blockers.append('RIGHTS_REVIEW_REQUIRED')
        source_verified = v.get('source_verification') == 'VERIFIED' and bool(v.get('source_url'))
        if not source_verified:
            blockers.append('SOURCE_NOT_VERIFIED')
        contract = row.get('execution_contract') or {}
        execution_complete = all(contract.get(k) for k in ('timing', 'price_adjustment', 'missing_data_policy', 'indicator_semantics'))
        costs = contract.get('costs') or {}
        execution_complete = execution_complete and contract.get('closed_bar_only') is True
        execution_complete = execution_complete and all(type(costs.get(k)) in (int, float) and math.isfinite(costs[k]) and costs[k] >= 0 for k in ('fee_bps', 'slippage_bps'))
        if not execution_complete:
            blockers.append('EXECUTION_CONTRACT_PENDING')
        if row.get('data_available') is not True:
            blockers.append('DATA_AVAILABILITY_UNCONFIRMED')
        gate = row.get('candidate_gate')
        if not isinstance(gate, dict) or gate.get('gate_version') != SUPPORTED_GATE_VERSION:
            blockers.append('UPSTREAM_CONTRACT_UNSUPPORTED')
        elif gate.get('status') != 'ELIGIBLE' or gate.get('eligible') is not True:
            blockers.extend(gate.get('blocking_reasons') or ['UPSTREAM_GATE_BLOCKED'])
        # Recompute readiness from observed admission facts. Never rank on an
        # untrusted API-provided score or return metric.
        score = 20 + 20 * int(source_verified)
        score += 20 * int(row.get('research_allowed') is True and row.get('research_rights_status') == 'ALLOWED')
        score += 20 * int(row.get('data_available') is True)
        score += 20 * int('EXECUTION_CONTRACT_PENDING' not in blockers)
        group['readiness_scores'][vid] = score
        blockers = sorted(set(blockers))
        group['variant_blockers'][vid] = blockers
        if not blockers:
            group['eligible_variants'].append(vid)
    candidates = []
    for _, group in sorted(groups.items()):
        group['source_strategy_ids'] = sorted(set(group['source_strategy_ids']))
        group['parameter_grid'] = sorted({r['variant_id']: r for r in group['parameter_grid']}.values(), key=lambda x: x['variant_id'])
        group['source_urls'] = sorted(group['source_urls'])
        group['planned_trial_count'] = len(group['parameter_grid'])
        group['trial_count'] = 0
        group['status'] = 'READY_FOR_CONTRACT_FREEZE' if group['eligible_variants'] else 'BLOCKED'
        group['candidate_quality_score'] = max(group['readiness_scores'].values())
        group['parameter_enumeration_penalty'] = min(20, max(0, len(group['parameter_grid']) - 1))
        candidates.append(group)
    ready = [c for c in candidates if c['eligible_variants']]
    # Greedy coverage: take a new concept before another template from an already
    # represented concept. Readiness and enumeration penalty break ties, IDs only
    # provide deterministic ordering at the final tie.
    ordered, coverage, diversity = [], Counter(), Counter()
    def dimensions(c):
        meta = c['diversity_metadata']
        result = []
        for key in ('strategy_family', 'factor_families', 'asset_class', 'market', 'frequency', 'source_type'):
            value = meta.get(key)
            if value:
                result.extend((key, str(x)) for x in (value if isinstance(value, list) else [value]))
        return result
    while ready:
        chosen = min(ready, key=lambda c: (coverage[c['concept_id']], sum(diversity[x] for x in dimensions(c)), -c['candidate_quality_score'],
                                          c['parameter_enumeration_penalty'], c['template_id']))
        ordered.append(chosen)
        coverage[chosen['concept_id']] += 1
        diversity.update(dimensions(chosen))
        ready.remove(chosen)
    selected = []
    for group in ordered[:target]:
        # The triage list retains blocked siblings for audit, but a selected
        # experiment must never inherit their rules or research identities.
        eligible = set(group['eligible_variants'])
        admitted_grid = [r for r in group['parameter_grid'] if r['variant_id'] in eligible]
        selected.append({**group, 'source_strategy_ids': sorted(eligible),
                         'parameter_grid': admitted_grid,
                         'source_urls': sorted({source_urls[vid] for vid in eligible}),
                         'variant_blockers': {vid: [] for vid in sorted(eligible)},
                         'eligible_variants': sorted(eligible),
                         'planned_trial_count': len(admitted_grid)})
    return {'schema_version': '3.0', 'input_records': len(rows), 'concepts': len({c['concept_id'] for c in candidates}),
            'templates': len(candidates), 'target': target, 'selected_count': len(selected),
            'eligible_count': len(ordered), 'minimum_required': minimum_required,
            'minimum_shortfall': max(0, minimum_required - len(selected)),
            'target_shortfall': max(0, target - len(selected)), 'research_runs': 0,
            'selected_concepts': len({c['concept_id'] for c in selected}),
            'selection_policy': 'concept_then_six_dimension_diversity_then_readiness_then_enumeration_penalty',
            'status': 'READY' if len(selected) >= minimum_required else 'INSUFFICIENT_EVIDENCE',
            'excluded': dict(excluded), 'candidates': candidates, 'selected': selected,
            'promotion_status': 'NOT_REQUESTED', 'source_snapshot_sha256': digest(rows)}


def public_summary(report):
    blockers = Counter(reason for c in report['candidates'] for reasons in c['variant_blockers'].values() for reason in reasons)
    keys = ('schema_version', 'input_records', 'concepts', 'templates', 'target', 'selected_count',
            'eligible_count', 'minimum_required', 'minimum_shortfall', 'target_shortfall', 'selected_concepts',
            'selection_policy', 'research_runs', 'status', 'excluded', 'promotion_status', 'source_snapshot_sha256')
    return {**{k: report[k] for k in keys}, 'blockers': dict(blockers),
            'parameter_variants_are_independent_hypotheses': False}
