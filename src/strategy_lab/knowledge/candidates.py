"""Group structural templates before research. Unknown rights never pass admission."""
from collections import Counter
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def collect_candidates(client):
    rows, offset = [], 0
    while True:
        page = client.export_research_candidates(limit=1000, offset=offset)
        if page.get('scope') != 'TRIAGE_ONLY':
            raise ValueError('Unexpected candidate export contract')
        items = page['items']
        if not items:
            break
        rows.extend(items)
        offset += len(items)
    return rows


def select_candidates(rows, *, target=200):
    if not 100 <= target <= 300:
        raise ValueError('Research target must be 100..300 independent templates')
    groups, excluded = {}, Counter()
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
            'parameter_grid': [], 'source_urls': set(), 'variant_blockers': {}, 'eligible_variants': []})
        vid = v['strategy_variant_id']
        group['source_strategy_ids'].append(vid)
        group['parameter_grid'].append({'variant_id': vid, 'spec_sha256': v['spec_sha256'], 'rule_ast': v['rule_ast']})
        group['source_urls'].add(v['source_url'])
        blockers = []
        if row.get('research_allowed') is not True or row.get('research_rights_status') != 'ALLOWED':
            blockers.append('RIGHTS_REVIEW_REQUIRED')
        if v.get('source_verification') != 'VERIFIED':
            blockers.append('SOURCE_NOT_VERIFIED')
        contract = row.get('execution_contract') or {}
        if not all(contract.get(k) is not None for k in ('timing', 'costs', 'price_adjustment', 'missing_data_policy')):
            blockers.append('EXECUTION_CONTRACT_PENDING')
        if row.get('data_available') is not True:
            blockers.append('DATA_AVAILABILITY_UNCONFIRMED')
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
        candidates.append(group)
    ready = [c for c in candidates if c['eligible_variants']]
    selected = ready[:target]
    return {'schema_version': '1.0', 'input_records': len(rows), 'concepts': len({c['concept_id'] for c in candidates}),
            'templates': len(candidates), 'target': target, 'selected_count': len(selected),
            'shortfall': max(0, 100 - len(selected)), 'research_runs': 0,
            'status': 'READY' if len(selected) >= 100 else 'INSUFFICIENT_EVIDENCE',
            'excluded': dict(excluded), 'candidates': candidates, 'selected': selected,
            'promotion_status': 'NOT_REQUESTED', 'source_snapshot_sha256': digest(rows)}


def public_summary(report):
    blockers = Counter(reason for c in report['candidates'] for reasons in c['variant_blockers'].values() for reason in reasons)
    keys = ('schema_version', 'input_records', 'concepts', 'templates', 'target', 'selected_count',
            'shortfall', 'research_runs', 'status', 'excluded', 'promotion_status', 'source_snapshot_sha256')
    return {**{k: report[k] for k in keys}, 'blockers': dict(blockers),
            'parameter_variants_are_independent_hypotheses': False}
