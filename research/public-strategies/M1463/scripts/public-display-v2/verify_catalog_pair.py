"""Offline candidate checks; never import, publish, replay, or read private NAV."""
import argparse
import json
from copy import deepcopy
from functools import partial
from pathlib import Path

import export_catalog_pair as e


def inventory(root):
    return {str(p.relative_to(root)): {'bytes': p.stat().st_size, 'sha256': e.sha(p.read_bytes())}
            for p in sorted(root.rglob('*')) if p.is_file()}


def candidate_checks(rid, result, data, refs):
    r, d, m, curve = [json.loads(result[k]) for k in
                     ['graph-record.json', 'graph-detail.json', 'public-display-manifest.json', 'base-nav-sampled.json']]
    original, summary, catalog = [json.loads(data[k]) for k in ['original_detail', 'summary', 'catalog_fields']]
    require = e.require
    require(r['id'] == d['id'] == m['id'] == rid, 'Candidate ID mismatch')
    require(r['source_contract'] == d['source_contract'] == m['source_contract'] == e.CONTRACTS[rid], 'Candidate contract mismatch')
    require(m['schema_version'] == e.SCHEMA and m['manifest_kind'] == r['manifest_kind'] == d['manifest_kind'] == e.KIND, 'Candidate manifest type mismatch')
    require(m['original_private_result_manifest'] is False and m['original_results_modified'] is False, 'False source manifest identity')
    require(r['projection_profile'] == d['projection_profile'] == m['projection_profile'] == e.PROFILE, 'Candidate profile mismatch')
    require(d['curve'] == curve == original['curve'] and len(curve) == 25, 'Original approved curve changed')
    require(d['curve_meta']['total_observations'] == 731 and d['curve_meta']['returned_points'] == 25
            and d['curve_meta']['equity_unit'] == 'initial_capital_multiple', 'Curve contract changed')
    require(d['curve_meta']['private_daily_nav_used'] is False and d['curve_meta']['first_point_rebased'] is False, 'Unauthorized curve use')
    for field in ['periods', 'same_instrument_benchmark', 'additional_native_bar_lag', 'capital_state']:
        require(d['metrics'][field] == original['metrics'][field], 'Original metrics changed')
    for key, alias in [('fee0', '0'), ('fee20', '20')]:
        require(d['metrics']['cost_sensitivity'][alias] == original['metrics']['cost_sensitivity'][key], 'Cost alias changed')
    require(r['results'] == {x['case']: x for x in summary['cases']}, 'Original result values changed')
    require(r['catalog_fields'] == catalog['fields'], 'Public original fields changed')
    require(r['catalog_public_scope']['public_field_count'] == len(catalog['fields'])
            and r['catalog_public_scope']['original_field_count'] == 11, 'Original field scope hidden')
    require(r['catalog_public_scope']['complete_original_fields_public'] is (rid == 'M1396'), 'Redaction falsely complete')
    if rid == 'M1463':
        require('别名来源' not in r['catalog_fields'], 'Private alias recreated')
        omitted = r['catalog_public_scope']['omitted_fields']['别名来源']
        require(set(omitted) == {'reason', 'public_alias_url'}, 'Private redacted values/hash leaked')
    require(r['benchmark_curve'] == [] and r['monthly'] is None, 'Unpublished series invented')
    require(r['research_fidelity'] == d['research_fidelity'] == e.FIDELITY
            and r['execution_class'] == d['execution_class'] == e.EXECUTION
            and r['fidelity_class'] == d['fidelity_class'] == 'HYPOTHESIS', 'Fidelity promoted/conflated')
    require(d['lab_counts'] == {'strategy_ids': 1, 'strategy_configurations': 4, 'new_control_configurations': 0,
            'reused_control_configurations': 1, 'strict_reproductions': 0}, 'Counts changed')
    require(d['projection_activity'] == {'new_strategy_trials': 0, 'new_controls': 0}, 'Projection invents runs')
    require(r['control_configurations'] == 0 and r['reused_control_configurations'] == 1
            and r['new_control_runs'] == 0, 'Reused control counted as new')
    require(r['benchmark_reference']['metrics'] == json.loads(data['control_reference'])['metrics'], 'Control metrics changed')
    require(m['origin_lab_commit'] == e.PIN and m['source_artifacts'] == r['source_artifacts'] == d['lineage']['source_artifacts'] == refs, 'Source roles changed')
    require(set(m['files']) == set(refs) | {'base-nav-sampled.json'}, 'Manifest cycle or unknown source')
    require(m['files']['base-nav-sampled.json'] == {'bytes': len(result['base-nav-sampled.json']), 'sha256': e.sha(result['base-nav-sampled.json'])}, 'Curve hash mismatch')
    mh = e.sha(result['public-display-manifest.json'])
    require(d['lineage']['manifest_sha256'] == d['lineage']['source_display_manifest_sha256'] == mh, 'Derived manifest binding changed')
    binding = d['transport_binding']
    require(set(binding) == {'origin_run_id', 'variant_id', 'fidelity_class', 'execution_class', 'protocol_sha256', 'manifest_sha256'}
            and all(isinstance(v, str) and v for v in binding.values()), 'Six-field provenance changed')
    for ref in [r['related_results'][0], r['implementations'][0]]:
        require(ref['manifest_kind'] == e.KIND and all(ref[k] == v for k, v in binding.items()), 'Related result binding changed')
    require(binding['manifest_sha256'] == mh and binding['protocol_sha256'] == refs['protocol']['sha256'], 'Wrong manifest/protocol binding')
    require(d['definition_revision_bound'] is False if 'definition_revision_bound' in d else d['lineage']['definition_revision_bound'] is False, 'False revision binding')
    require(r['definition_revision_bound'] is False and r['projection_status'] == d['projection_status'] == 'STAGED_NOT_IMPORTED', 'False active state')
    for body in result.values():
        e.prior.screen(body)


def verify(repo, first, rebuild, receipt):
    e.require(not receipt.exists(), 'Immutable receipt exists')
    e.export(repo, rebuild)
    a, b = inventory(first), inventory(rebuild)
    e.require(a == b and len(a) == 9, 'Fresh builds not byte-identical')
    checks = []

    def rejected(call, label):
        try:
            call()
        except (ValueError, TypeError, KeyError, IndexError):
            checks.append(label)
        else:
            raise AssertionError('Guard accepted invalid case: ' + label)

    total = 0
    for rid in e.PINS:
        data, refs = e.load_sources(repo, rid)
        total += len(refs)
        result = {name: (first/e.destination(rid)/name).read_bytes() for name in
                  ['graph-record.json', 'graph-detail.json', 'public-display-manifest.json', 'base-nav-sampled.json']}
        candidate_checks(rid, result, data, refs)
        for role, ref in refs.items():
            body = e.common.git_bytes(repo, ref['path'])
            e.require(body == data[role] and len(body) == ref['bytes'] and e.sha(body) == ref['sha256'], 'Source readback mismatch')

        def changed(role, edit, data=data):
            bad = deepcopy(data)
            obj = json.loads(bad[role])
            edit(obj)
            bad[role] = e.encode(obj)
            return bad

        # Exercise semantic guards independently of the stricter immutable publication hash gate.
        for label, role, edit in [
            ('wrong_id', 'summary', lambda x: x.update(id='M1258')),
            ('promote_research', 'summary', lambda x: x.update(classification='STRICT')),
            ('promote_graph', 'original_detail', lambda x: x.update(fidelity_class='STRICT')),
            ('promote_OOS_control', 'control_reference', lambda x: x.update(window_OOS=True)),
            ('new_control_count', 'summary', lambda x: x.update(new_controls=1)),
            ('wrong_control_identity', 'control_reference', lambda x: x.update(id='M1358')),
            ('95percent_control', 'control_reference', lambda x: x.update(allocation='95%')),
            ('wrong_control_remote', 'summary', lambda x: x.update(control_remote_commit='0'*40)),
            ('wrong_control_release', 'control_release', lambda x: x.update(consumers=[])),
            ('wrong_C0_hash', 'original_detail', lambda x: x['lineage'].update(C0_sha256='0'*64)),
            ('wrong_curve_units', 'original_detail', lambda x: x['curve_meta'].update(equity_unit='USDT')),
            ('curve_double_division', 'original_detail', lambda x: [p.update(equity=p['equity']/100000) for p in x['curve']]),
            ('curve_26th_point', 'original_detail', lambda x: x['curve'].append(deepcopy(x['curve'][-1]))),
            ('731_display_points', 'original_detail', lambda x: x['curve_meta'].update(returned_points=731)),
            ('curve_null', 'original_detail', lambda x: x['curve'][5].update(equity=None)),
            ('drawdown_positive', 'original_detail', lambda x: x['curve'][5].update(drawdown=0.1)),
            ('fee0_changed', 'summary', lambda x: x['cases'][1].update(fee_bps=8)),
            ('delay2_changed', 'summary', lambda x: x['cases'][3].update(delay_bars=1)),
            ('terminal_null_to_zero', 'original_detail', lambda x: x['metrics']['capital_state'].update(terminal_pending=0)),
            ('full_metric_alias', 'original_detail', lambda x: x['metrics']['periods']['full'].update(cagr=0)),
            ('public_field_drop', 'catalog_fields', lambda x: x['fields'].pop('规则')),
        ]:
            bad = changed(role, edit)
            rejected(partial(e.validate_semantics, rid, bad), rid + ':' + label)
        bad = deepcopy(refs)
        bad['summary']['sha256'] = '0'*64
        rejected(partial(e.project, rid, data, bad), rid + ':role_hash')
        bad = deepcopy(refs)
        bad['summary']['url'] = bad['summary']['url'].replace(e.PIN, '0'*40)
        rejected(partial(e.project, rid, data, bad), rid + ':source_url_pin')
        bad = changed('publication_manifest', lambda x: x.update(schema='NATIVE_GRAPH_MANIFEST'))
        rejected(partial(e.project, rid, bad, refs), rid + ':publication_type_hash')
        bad = changed('publication_manifest', lambda x: x['files'][0].update(path='../outside'))
        rejected(partial(e.project, rid, bad, refs), rid + ':publication_path')
        r, d = [json.loads(result[k]) for k in ['graph-record.json', 'graph-detail.json']]
        altered = deepcopy(d)
        altered['source_contract'] = 'CATALOG_RSI5_FULLCASH_V1'
        rejected(partial(e.finish, rid, deepcopy(r), altered, refs, result['base-nav-sampled.json']), rid + ':wrong_source_contract')
        altered = deepcopy(d)
        altered['projection_profile'] = 'NATIVE_5M_RULE_CARD_V2'
        rejected(partial(e.finish, rid, deepcopy(r), altered, refs, result['base-nav-sampled.json']), rid + ':wrong_profile')
        altered = deepcopy(d)
        altered['origin_run_id'] = 0
        rejected(partial(e.finish, rid, deepcopy(r), altered, refs, result['base-nav-sampled.json']), rid + ':transport_nonstring')
        for label, name, edit in [
            ('derived_manifest_type', 'public-display-manifest.json', lambda x: x.update(manifest_kind='PRIVATE_RESULT_MANIFEST')),
            ('invented_private_alias', 'graph-record.json', lambda x: x['catalog_fields'].update(规则='invented')),
            ('result_ref_type', 'graph-record.json', lambda x: x['related_results'][0].update(manifest_kind='NATIVE_GRAPH_MANIFEST')),
            ('private_annotation', 'graph-detail.json', lambda x: x['limitations'].append('libfile_do_not_publish')),
        ]:
            bad = deepcopy(result)
            obj = json.loads(bad[name])
            edit(obj)
            bad[name] = e.encode(obj)
            rejected(partial(candidate_checks, rid, bad, data, refs), rid + ':' + label)
    rejected(lambda: e.export(repo, first), 'immutable_output_collision')
    rejected(lambda: e.prefix('M9999'), 'unapproved_id')
    for path in ['../outside', '/workspace/private', 'a/../b', 'a\\b']:
        rejected(partial(e.common.safe_path, path), 'unsafe_path:' + path)
    for value in ['libfile_private', '/workspace/private-file', 'Bearer secret001', 'https://example.org/x?sig=secret']:
        rejected(partial(e.prior.screen, e.encode({'field': value})), 'privacy_screen:' + value.split('/')[0])
    rejected(lambda: e.same(None, 0, 'null'), 'null_is_not_zero')
    delivery = json.loads((first/'DELIVERY-MANIFEST.json').read_bytes())
    e.require(len(delivery['files']) == 8 and all(a[k] == v for k, v in delivery['files'].items()), 'Outer delivery mismatch')
    result = {'status': 'PASS_SELF_CHECK_NOT_INDEPENDENT_APPROVAL', 'source_commit': e.PIN,
        'source_roles_read_back': total, 'actual_fresh_builds': 2, 'byte_identical_files': 9, 'candidate_files': 8,
        'records': 2, 'curve_points': 50, 'source_metric_observations_per_id': 731,
        'public_catalog_fields': {'M1396': 11, 'M1463': 10}, 'original_strategy_configurations': 8,
        'original_new_controls': 0, 'reused_unique_control_ids': ['M1258'], 'control_references': 2,
        'new_strategy_trials': 0, 'new_controls': 0, 'guard_count': len(checks), 'guards': checks,
        'private_NAV_or_ZIP_read': False, 'private_output_manifest_body_read': False, 'monthly_values_invented': False,
        'source_rule_or_identity_changed': False, 'native_definition_revision_bound': False,
        'repository_writes': 0, 'Graph_inventory_changes': 0, 'Site_operations': 0, 'files': a}
    with receipt.open('xb') as handle:
        handle.write(e.encode(result))
    print(json.dumps({k: result[k] for k in ['status', 'source_roles_read_back', 'byte_identical_files', 'curve_points', 'guard_count']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ['lab-repo', 'first', 'rebuild', 'receipt']:
        parser.add_argument('--' + arg, type=Path, required=True)
    a = parser.parse_args()
    verify(a.lab_repo, a.first, a.rebuild, a.receipt)
