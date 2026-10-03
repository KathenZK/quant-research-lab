"""Fixed public M1396/M1463 -> private display candidates; never execute a strategy."""
import argparse
import calendar
import json
import math
import shutil
from copy import deepcopy
from pathlib import Path

import common_public_display as common
import frozen_export as prior

PIN = '683fe124f70c0f5b1e36af20ad68256c4a83e180'
PROFILE = 'DAILY_SAMPLED_APPROVED_DETAIL_V1'
SCHEMA = 'quantgraph-public-derived-display-manifest/v2'
KIND = 'PUBLIC_DERIVED_DISPLAY_MANIFEST'
FIDELITY = 'HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED'
EXECUTION = 'ADAPTED_EXECUTION_PROXY'
INPUT = '48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5'
CONTROL_PIN = '2a2e33e0de2b4897d6ccb460e72dcb5e73aa4153'
CONTROL_HASH = 'ea4fb4687cffe69b7ee877312e19ec49b263bf5d21705d0dcfa2e791c24be00a'
PINS = {
    'M1396': (10403, 'ee8d68770a697e372021989c192674b6db6cf96b8ea0eeee450ecb4370454c6f'),
    'M1463': (10404, 'ae06e451a8dcc6f8c09ca4a49205860cefb09efab4cccc06f754032a0dfd94ae'),
}
CONTRACTS = {
    'M1396': 'CATALOG_WEEKDAY_HL2SMA4_FULLCASH_REUSED_CONTROL_V1',
    'M1463': 'CATALOG_BOLLINGER20X2_FULLCASH_REUSED_CONTROL_V1',
}
BASE = 'artifacts/20261003-catalog-v1/'
ROLES = {
    'summary': BASE + 'summary.json', 'original_detail': BASE + 'graph-detail.json',
    'original_record': BASE + 'graph-record.json', 'protocol': 'specs/protocol-v1.json',
    'C0': 'specs/C0-v1.json', 'rules': 'source/root-frozen-rules.json',
    'catalog_fields': 'source/catalog-original-fields.json',
    'control_reference': 'recovery/control-release-v1/control-reference.json',
    'control_release': 'recovery/control-release-v1/release.json',
}
RULE_KEYS = ['entry', 'exit', 'capital', 'capital_provenance', 'cold_start', 'execution',
             'stop_or_roi', 'known_halt', 'cost_cases', 'valuation', 'timeframe']
SPECIFIC = {
    'M1396': ['hl2_SMA4', 'calendar_execution', 'date_filter_adaptation'],
    'M1463': ['bollinger', 'membership_scope', 'date_scope'],
}
require, sha, encode = common.require, common.sha, common.encode


def prefix(rid):
    require(rid in PINS, 'Unapproved ID')
    return f'research/public-strategies/{rid}/'


def destination(rid):
    return prefix(rid) + 'artifacts/20261003-public-display-prep/'


def code_gate():
    for name, digest in [('common_public_display.py', 'f5a8536676f1575f55adcf3b286ba92c198a01c070399250fbf933f8937c9c13'),
                         ('frozen_export.py', '266c93afa0829b0e504b2e008e1ed0ae1b43a4b5fd2869ffaeb047e41fba3128')]:
        require(sha(Path(__file__).with_name(name).read_bytes()) == digest, 'Frozen helper altered')


def publication(rid, raw):
    require((len(raw), sha(raw)) == PINS[rid], 'Publication pin mismatch')
    pub = json.loads(raw)
    require(pub['id'] == rid and pub['schema'] == 'batch016-fixed-publication/v1', 'Publication identity/type mismatch')
    require(len(pub['files']) == 49 and pub['actual_strategy_configurations'] == 4
            and pub['new_controls'] == pub['strict_reproductions'] == 0, 'Publication count mismatch')
    allowed = {}
    for item in pub['files']:
        path = common.safe_path(item['path'])
        require(path.startswith((prefix(rid), 'research/_shared-kernels/catalog-daily-cash/')), 'Unexpected publication scope')
        require(path not in allowed, 'Duplicate publication path')
        allowed[path] = item
    return pub, allowed


def bind_sources(rid, data, refs):
    require(set(data) == set(refs) == set(ROLES) | {'publication_manifest'}, 'Unexpected source role')
    common.PIN = PIN
    pub, allowed = publication(rid, data['publication_manifest'])
    for role, body in data.items():
        path = prefix(rid) + (ROLES[role] if role != 'publication_manifest' else 'publication-manifest.v1.json')
        require(refs[role] == common.source_ref(path, body), 'Selected source reference mismatch')
        if role != 'publication_manifest':
            item = allowed[path]
            require((len(body), sha(body)) == (item['bytes'], item['sha256']), 'Selected source outside exact publication bytes')
    c0 = json.loads(data['C0'])
    require(pub['original_C0_sha256'] == sha(data['C0']), 'Publication C0 mismatch')
    require(len(c0['files']) == 23, 'C0 count mismatch')
    # Compare all frozen descriptors with the publication; only selected display bodies are read.
    for item in c0['files']:
        path = prefix(rid) + common.safe_path(item['path'])
        require(allowed[path]['sha256'] == item['sha256'] and allowed[path]['bytes'] == item['bytes'], 'C0/public descriptor mismatch')
    return pub


def load_sources(repo, rid):
    code_gate()
    common.PIN = PIN
    path = prefix(rid) + 'publication-manifest.v1.json'
    raw = common.git_bytes(repo, path)
    publication(rid, raw)
    data, refs = {'publication_manifest': raw}, {'publication_manifest': common.source_ref(path, raw)}
    for role, rel in ROLES.items():
        path = prefix(rid) + rel
        body = common.git_bytes(repo, path)
        data[role], refs[role] = body, common.source_ref(path, body)
    bind_sources(rid, data, refs)
    return data, refs


def same(a, b, message):
    require(type(a) is type(b) and a == b, message)


def metric_match(view, case):
    for key in ['total_return', 'cagr', 'max_drawdown', 'sharpe_zero_cash', 'observations', 'final_equity']:
        same(view[key], case[key], 'Source metric changed: ' + key)
    same(view['sharpe'], case['sharpe_zero_cash'], 'Sharpe alias changed')
    require(view['annualization'] == 365 and view['start'] == '2023-01-01' and view['end'] == '2024-12-31', 'Window changed')


def validate_semantics(rid, data):
    s, p, c, d, r, rules, catalog, control, release = [json.loads(data[k]) for k in
        ['summary', 'protocol', 'C0', 'original_detail', 'original_record', 'rules', 'catalog_fields', 'control_reference', 'control_release']]
    require(s['id'] == p['id'] == c['id'] == d['id'] == r['id'] == rules['id'] == catalog['fields']['id'] == rid, 'ID mismatch')
    require(s['classification'] == FIDELITY and s['execution_class'] == EXECUTION, 'Research/execution fidelity changed')
    require(p['classification'] == rules['classification'] == FIDELITY + ' / ' + EXECUTION + '; strict0', 'Frozen classification changed')
    require(d['fidelity_class'] == r['implementations'][0]['fidelity_class'] == 'HYPOTHESIS', 'Graph fidelity changed')
    require(s['strict_reproductions'] == c['strict_reproductions'] == d['audit']['strict_reproductions'] == 0, 'Strict count changed')
    require(d['audit']['original_runtime_equivalence'] is False and d['audit']['PIT'] == 'NOT_PROVEN', 'Quality promoted')
    require(s['strategy_configurations'] == c['planned_strategy_configurations'] == r['configuration_runs'] == 4, 'Configuration count changed')
    require(s['new_controls'] == c['planned_new_controls'] == r['new_control_runs'] == 0, 'New control count changed')
    require(d['origin_run_id'] == d['run_id'] == f'{rid.lower()}-catalog-daily-20261003-v1'
            and d['variant_id'] == f'{rid}-catalog-daily-v1-base', 'Original identity changed')
    require(d['lineage']['C0_sha256'] == sha(data['C0']), 'C0 lineage mismatch')
    require(d['lineage']['source_commit'] == '56c7cae289700d73d0e2f4df582ea044c2363b0c', 'Execution source pin changed')
    require(p['input']['sha256'] == rules['input']['sha256'] == c['canonical_sha256'] == d['lineage']['input_sha256'] == INPUT, 'Input pin changed')
    for key, value in rules.items():
        if key != 'input':
            same(p[key], value, 'Frozen protocol rule mismatch: ' + key)
    require(catalog['original_field_count'] == 11 and len(catalog['fields']) == (11 if rid == 'M1396' else 10), 'Public catalog scope changed')
    require(set(catalog['redacted_fields']) == (set() if rid == 'M1396' else {'别名来源'}), 'Catalog redaction changed')
    capital = rules['capital']
    require(capital['fraction'] == '1' and capital['initial_cash'] == '100000' and capital['entry_fee_inclusive'] is True
            and capital['Decimal_precision'] == 50 and capital['rounding'] == 'ROUND_HALF_EVEN', 'Fullcash convention changed')
    require(p['evaluation_start_ms'] == 1672531200000 and p['evaluation_end_ms'] == 1735689600000, 'Evaluation boundary changed')
    require(control['id'] == release['source_id'] == 'M1258' and control['control_name'] == 'buyhold', 'Wrong control identity')
    require(release['status'] == 'RELEASED_FOR_EXACT_IDENTITY_REUSE' and rid in release['consumers'], 'Control not released for ID')
    require(release['control_reference']['sha256'] == d['lineage']['control_reference_sha256'] == sha(data['control_reference']) == CONTROL_HASH, 'Control reference changed')
    require(release['remote_public_core_commit'] == s['control_remote_commit'] == d['lineage']['control_remote_commit'] == CONTROL_PIN, 'Control remote pin changed')
    require(release['new_controls_authorized'] == p['benchmark']['new_control_configurations'] == 0, 'Control reuse changed')
    require(control['initial_cash'] == '100000' and control['allocation'] == '100% fee-inclusive'
            and control['fee_bps_each_side'] == 8 and control['slippage_bps_each_side'] == 2
            and control['native_timeframe'] == '1d' and control['bars'] == 731 and control['input_sha256'] == INPUT, 'Wrong control capital/cost/unit')
    require(control['window_OOS'] is False and control['trusted'] is False and control['PIT'] == 'NOT_PROVEN', 'Control quality promoted')
    require(control['statistics'] == p['statistics'], 'Control metric convention mismatch')
    cases = {x['case']: x for x in s['cases']}
    require(len(s['cases']) == len(cases) == 4 and set(cases) == {'base', 'fee0', 'fee20', 'delay2'}, 'Unexpected cases')
    for name, fee, lag in [('base', 8, 1), ('fee0', 0, 1), ('fee20', 20, 1), ('delay2', 8, 2)]:
        case = cases[name]
        cfg = {'name': name, 'fee_bps_each_side': fee, 'slippage_bps_each_side': 2, 'delay_bars': lag}
        require(cfg in p['cases'] and cfg in rules['cost_cases'], 'Cost config changed')
        require(case['kind'] == 'STRATEGY' and case['fee_bps'] == fee and case['slippage_bps'] == 2
                and case['delay_bars'] == lag and case['observations'] == 731 and case['monthly_observations'] == 24, 'Result cost/count changed')
        view = d['metrics']['periods'] if name == 'base' else d['metrics']['additional_native_bar_lag'] if name == 'delay2' else d['metrics']['cost_sensitivity'][name]
        metric_match(view['2023-2024'], case)
    same(d['metrics']['periods']['full'], d['metrics']['periods']['2023-2024'], 'Full alias changed')
    metric_match(d['metrics']['same_instrument_benchmark']['2023-2024'], control['metrics'])
    same(d['metrics']['capital_state']['terminal_pending'], cases['base']['terminal_pending'], 'Terminal null changed')
    require(d['metrics']['capital_state']['initial_cash_usdt'] == 100000, 'Initial capital changed')
    dates = ['2023-01-01'] + [f'{y}-{m:02d}-{calendar.monthrange(y, m)[1]}' for y in [2023, 2024] for m in range(1, 13)]
    require([x['date'] for x in d['curve']] == dates, 'Exactly25 approved point dates required')
    require(d['curve_meta']['observations'] == d['curve_meta']['total_observations'] == 731
            and d['curve_meta']['returned_points'] == 25, 'Sample/full observations changed')
    require(d['curve_meta']['equity_unit'] == 'initial_capital_multiple'
            and d['curve_meta']['drawdown_unit'] == 'fraction', 'Curve units changed')
    require(d['curve'][0]['equity'] == 1.0 and math.isclose(d['curve'][-1]['equity'], cases['base']['final_equity']/100000, abs_tol=1e-14), 'Curve rescaled/rebased')
    for point in d['curve']:
        require(type(point['equity']) in [int, float] and math.isfinite(point['equity']) and point['equity'] >= 0, 'Invalid equity')
        require(type(point['drawdown']) in [int, float] and math.isfinite(point['drawdown']) and -1 <= point['drawdown'] <= 0, 'Invalid drawdown')
    require(all(key in rules for key in SPECIFIC[rid]), 'Wrong rule contract')
    require(('bollinger' not in rules) if rid == 'M1396' else ('hl2_SMA4' not in rules), 'Cross-strategy rule contamination')
    return s, p, d, r, rules, catalog, control, cases


def finish(rid, record, detail, refs, curve):
    require(record['projection_profile'] == detail['projection_profile'] == PROFILE, 'Display profile mismatch')
    require(record['source_contract'] == detail['source_contract'] == CONTRACTS[rid], 'Source contract mismatch')
    require(record['id'] == detail['id'] == rid, 'Display ID mismatch')
    manifest = {'schema_version': SCHEMA, 'manifest_kind': KIND, 'projection_profile': PROFILE, 'source_contract': CONTRACTS[rid],
        'id': rid, 'origin_run_id': detail['run_id'], 'variant_id': detail['variant_id'], 'origin_lab_commit': PIN,
        'original_private_result_manifest': False, 'original_results_modified': False, 'source_artifacts': refs,
        'files': {**refs, 'base-nav-sampled.json': {'bytes': len(curve), 'sha256': sha(curve)}},
        'curve_contract': deepcopy(detail['curve_meta']),
        'excluded_from_self_hash': ['public-display-manifest.json', 'graph-record.json', 'graph-detail.json'],
        'exclusion_reason': 'Record/detail bind this manifest; outer delivery binds all4 candidates without cycles',
        'status': 'STAGED_NOT_PUBLISHED'}
    manifest_raw = encode(manifest)
    oldlineage = deepcopy(detail['lineage'])
    detail['lineage'] = {'manifest_kind': KIND, 'source_contract': CONTRACTS[rid], 'source_display_manifest_sha256': sha(manifest_raw),
        'manifest_sha256': sha(manifest_raw), 'lab_commit': PIN, 'protocol_sha256': refs['protocol']['sha256'], 'C0_sha256': refs['C0']['sha256'],
        'source_artifacts': refs, 'definition_revision_bound': False, 'new_execution_trials': 0, 'new_control_trials': 0, 'source_lineage': oldlineage}
    binding = {key: detail[key] for key in ['origin_run_id', 'variant_id', 'fidelity_class', 'execution_class']}
    binding.update(protocol_sha256=detail['lineage']['protocol_sha256'], manifest_sha256=detail['lineage']['manifest_sha256'])
    require(len(binding) == 6 and all(isinstance(v, str) and v for v in binding.values()), 'Six-field provenance type mismatch')
    reference = dict(binding, manifest_kind=KIND)
    record.update(manifest_kind=KIND, related_results=[reference], implementations=[dict(reference, family=detail['family'])],
        projection_status='STAGED_NOT_IMPORTED', definition_revision_bound=False, control_configurations=0,
        reused_control_configurations=1, strategy_configurations=4, tested_variants=1, source_artifacts=refs)
    detail.update(manifest_kind=KIND, projection_status='STAGED_NOT_IMPORTED', transport_binding=binding,
        lab_counts={'strategy_ids': 1, 'strategy_configurations': 4, 'new_control_configurations': 0, 'reused_control_configurations': 1, 'strict_reproductions': 0},
        projection_activity={'new_strategy_trials': 0, 'new_controls': 0})
    output = {'graph-record.json': encode(record), 'graph-detail.json': encode(detail),
              'base-nav-sampled.json': curve, 'public-display-manifest.json': manifest_raw}
    for body in output.values():
        prior.screen(body)
    return output


def project(rid, data, refs):
    bind_sources(rid, data, refs)
    _s, p, d, r, rules, catalog, control, cases = validate_semantics(rid, data)
    detail, record = deepcopy(d), deepcopy(r)
    for obj in [detail, record]:
        obj.update(projection_profile=PROFILE, source_contract=CONTRACTS[rid], research_fidelity=FIDELITY,
                   execution_class=EXECUTION, fidelity_class='HYPOTHESIS')
    detail['implementation_fidelity'] = EXECUTION
    detail['metrics']['cost_sensitivity'] = {str(fee): deepcopy(d['metrics']['cost_sensitivity'][name]) for name, fee in [('fee0', 0), ('fee20', 20)]}
    detail['metrics']['source_cost_key_aliases'] = {'fee0': '0', 'fee20': '20'}
    detail['curve_meta'].update(full_daily_curve_published=False, interpolation_claim=False, private_daily_nav_used=False,
        first_point_rebased=False, denominator=100000, source_drawdown_basis='Original25 samples retain drawdown against full daily peaks; not recomputed from samples')
    selected_rules = {key: deepcopy(rules[key]) for key in RULE_KEYS + SPECIFIC[rid]}
    detail['spec']['params'].update(capital=deepcopy(rules['capital']), entry=rules['entry'], exit=rules['exit'],
                                  metric_conventions=deepcopy(p['statistics']), source_contract=CONTRACTS[rid])
    detail['limitations'] += [
        'Only25 approved normalized public points;731 is source metric observations. No rescaling/interpolation or private dailyNAV use.',
        'Four original strategy configurations;0 original new controls. Existing accepted M1258 fullcash fee-inclusive control is reused.',
        'This display preparation runs0 strategies and0 controls; Graph HYPOTHESIS remains distinct from ADAPTED_EXECUTION_PROXY.',
        'Prior-exposed2023-2024 is not untouched OOS;strict0;source webpage/runtime equivalence remains unverified.',
        'Monthly observations count24 is preserved, but selected light summary does not publish monthly return values; none invented.',
        'Original private-result hash in approved source lineage is provenance only, never a public display manifest or permission to read private outputs.',
    ]
    disclosure = {'original_field_count': catalog['original_field_count'], 'public_field_count': len(catalog['fields']),
        'omitted_fields': {key: {k: deepcopy(v) for k, v in value.items() if k in ['reason', 'public_alias_url']}
                        for key, value in catalog['redacted_fields'].items()}, 'complete_original_fields_public': not catalog['redacted_fields']}
    record.update(status='tested_hypothesis_only', source_status=r['status'], results=deepcopy(cases),
        catalog_fields=deepcopy(catalog['fields']), catalog_public_scope=disclosure, rules=selected_rules,
        metric_conventions=deepcopy(p['statistics']),
        economic_basis={'paper': None, 'hypothesis': rules['economic_hypothesis'], 'status': 'INFERRED_RESEARCH_RATIONALE_NOT_SOURCE_VERIFIED'},
        benchmark_reference={'kind': 'REUSED_ACCEPTED_M1258_CONTROL', 'id': 'M1258', 'name': 'buyhold',
            'source_commit': CONTROL_PIN, 'evidence_role': 'control_reference', 'acceptance_role': 'control_release',
            'new_controls_for_this_strategy': 0, 'allocation': '100% fee-inclusive', 'initial_cash': '100000',
            'fee_bps_each_side': 8, 'slippage_bps_each_side': 2, 'timeframe': '1d', 'observations': 731,
            'evaluation_start': control['evaluation_start'], 'evaluation_end_exclusive': control['evaluation_end_exclusive'],
            'metrics': deepcopy(control['metrics']), 'window_OOS': False},
        benchmark_curve=[], monthly=None, monthly_status='NOT_PUBLISHED_IN_SELECTED_LIGHT_SUMMARY',
        limitations=deepcopy(detail['limitations']))
    return finish(rid, record, detail, refs, encode(d['curve']))


def export(repo, output):
    require(not output.exists(), 'Immutable output directory exists')
    files, source_refs = {}, {}
    for rid in PINS:
        data, refs = load_sources(repo, rid)
        source_refs[rid] = refs
        files.update({destination(rid) + name: body for name, body in project(rid, data, refs).items()})
    delivery = {'schema_version': 'catalog-pair-public-display-preparation/v1', 'source_commit': PIN,
        'status': 'STAGED_NOT_IMPORTED_NOT_PUBLISHED', 'ids': list(PINS), 'records': 2, 'original_strategy_configurations': 8,
        'original_new_controls': 0, 'reused_unique_control_ids': ['M1258'], 'control_references': 2,
        'new_executions': 0, 'new_controls': 0, 'private_daily_NAV_used': False, 'Graph_inventory_changed': False, 'Site_operations': 0,
        'source_artifacts': source_refs, 'selected_public_source_objects': 20,
        'manifest_scope': 'Two49entry public manifests pinned;only20selected source bodies read, not all96 original union bodies',
        'generated_candidates': 8, 'generated_files_including_delivery': 9,
        'files': {name: {'bytes': len(body), 'sha256': sha(body)} for name, body in sorted(files.items())}}
    files['DELIVERY-MANIFEST.json'] = encode(delivery)
    require(shutil.disk_usage(output.parent).free > 5*1024**3 + sum(map(len, files.values())), '5GiB reserve required')
    output.mkdir(mode=0o700)
    for name, body in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as handle:
            handle.write(body)
    return delivery


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab-repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = export(args.lab_repo, args.output)
    print(json.dumps({k: result[k] for k in ['status', 'ids', 'generated_candidates', 'new_executions', 'new_controls']}))
