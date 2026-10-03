"""Offline additive display export from one exact approved Git commit.

No source edits, execution, fetching, Graph inventory edits or Site operations.
"""
import argparse
from copy import deepcopy
import csv
from datetime import date, timedelta
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

PIN = '8abc1556d2bf249ce12de7f08a0311331b6a0d39'
KIND = 'PUBLIC_DERIVED_DISPLAY_MANIFEST'
PINS = {
    'M0253': (4364, '239c3391025b553bc6badfdde8c24940d62a2db2fcd6826f90fe8b33252133a5'),
    'M0272': (4181, '507e045e5e2a29f688dd9b2dc47d014d58b48d5c850c8754e734daaa9a6cfff6'),
    'M0264': (4181, 'c1251b3131c375f774b28da6e65abea7aeae842338bcebd967ff61b5eeb47876'),
    'M0266': (4181, '1248e3abf5f98ddada05b1b4c5c87acafbc496f95b9c605846ab697ac7db7ada'),
}
BLURBS = {
    'M0253': 'MACD为正且高于信号线时入场，MACD转弱时退出，同时执行固定止损与分时ROI规则。',
    'M0272': '过滤放量后选择低于短中均线且触及布林下轨的短期低点，反弹到上轨附近高点时退出。',
    'M0264': '在EMA50下方且跌破布林下轨折价线、成交量未异常放大时入场，反弹到布林中轨上方时退出。',
    'M0266': '合并两种布林带超卖入场分支，回到中轨上方并通过盈利门时信号退出，另保留ROI和固定止损。',
}
ROLES = {
    'summary': 'artifacts/results/summary.json',
    'protocol': 'specs/protocol.json',
    'C0': 'specs/C0.json',
    'source_rule_card': 'specs/source-rule-card.json',
    'readme': 'README.md',
    'attribution': 'ATTRIBUTION.md',
    'validation_summary': 'artifacts/results/validation-summary.json',
    **{f'{case}_daily': f'artifacts/results/{case}-daily-equity.json'
       for case in ['base', 'fee0', 'fee20', 'delay2']},
}


def require(test, message):
    if not test:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def safe_path(path):
    p = PurePosixPath(path)
    require(not p.is_absolute() and p.as_posix() == path and '..' not in p.parts
            and '\\' not in path and '\x00' not in path, 'Unsafe source path')
    return path


def git_bytes(repo, path):
    safe_path(path)
    size = int(subprocess.check_output(['git', '-C', str(repo), 'cat-file', '-s', PIN + ':' + path]))
    require(0 <= size <= 8 * 1024 * 1024, 'Source exceeds bounded size')
    return subprocess.check_output(['git', '-C', str(repo), 'show', PIN + ':' + path])


def source_ref(path, raw):
    return dict(path=path, bytes=len(raw), sha256=sha(raw),
                url=f'https://github.com/KathenZK/quant-research-lab/blob/{PIN}/{path}')


def sources(repo, rid):
    require(rid in PINS, 'Unapproved ID')
    prefix = f'research/public-strategies/{rid}/'
    publication = git_bytes(repo, prefix + 'publication-manifest.json')
    require((len(publication), sha(publication)) == PINS[rid], 'Publication pin mismatch')
    manifest = json.loads(publication)
    require(manifest['record_id'] == rid, 'Publication identity mismatch')
    data, refs = {'publication_manifest': publication}, {
        'publication_manifest': source_ref(prefix + 'publication-manifest.json', publication)}
    seen, all_refs = set(), [refs['publication_manifest']]
    files = {}
    for entry in manifest['files']:
        rel = safe_path(entry['path'])
        require(rel not in seen, 'Duplicate publication file')
        seen.add(rel)
        raw = git_bytes(repo, prefix + rel)
        require(sha(raw) == entry['sha256'] and len(raw) == entry['bytes'], 'Publication artifact mismatch')
        files[rel] = raw
        all_refs.append(source_ref(prefix + rel, raw))
    for role, rel in ROLES.items():
        require(rel in files, 'Display input outside publication allowlist')
        data[role] = files[rel]
        refs[role] = source_ref(prefix + rel, files[rel])
    return data, refs, all_refs


def screen(raw):
    text = raw.decode()
    for pattern in [r'(?i)libfile_[a-z0-9]+|sediment://|appgprj_|app://',
                    r'(?i)/(?:workspace|tmp|Users|home)/|[A-Z]:\\',
                    r'(?i)(?:https?://[^\s"<>]+)[?&](?:token|sig|signature|key|x-amz-[^=]*)=',
                    r'(?i)authorization\s*[:=]|bearer\s+[A-Za-z0-9._-]+|BEGIN .*PRIVATE KEY',
                    r'私人批注|私密批注|个人批注|个人备注|不要公开']:
        require(not re.search(pattern, text), 'Private/credential-like display content')


def curve_csv(daily, metric, initial):
    require(initial == daily['initial_equity'] == 100000, 'Frozen initial cash mismatch')
    points = daily['points']
    require(len(points) == metric['daily_observations'] == 366, 'Daily count mismatch')
    require(daily['observations'] == metric['observations'] == 105408, 'Native count mismatch')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=['date', 'valuation_time_utc', 'equity', 'nav',
                                              'source_native_drawdown'], lineterminator='\n')
    writer.writeheader()
    for n, point in enumerate(points):
        expected = date(2024, 1, 1) + timedelta(days=n)
        require(point['date'] == expected.isoformat(), 'Daily date mismatch')
        require(point['timestamp_utc'] == (expected + timedelta(days=1)).isoformat() + 'T00:00:00Z',
                'Exclusive valuation timestamp mismatch')
        require(math.isfinite(point['equity']) and point['equity'] >= 0, 'Invalid equity')
        require(math.isfinite(point['drawdown']) and -1 <= point['drawdown'] <= 0, 'Invalid native drawdown')
        writer.writerow(dict(date=point['date'], valuation_time_utc=point['timestamp_utc'],
                             equity=point['equity'], nav=point['equity'] / initial,
                             source_native_drawdown=point['drawdown']))
    require(points[-1]['equity'] == metric['final_equity'], 'Terminal cash mismatch')
    require(math.isclose(points[-1]['equity'] / initial - 1, metric['total_return'], abs_tol=1e-14),
            'Terminal return mismatch')
    return stream.getvalue().encode()


def project(rid, data, refs):
    s, p, c0, card, validation = (json.loads(data[k]) for k in
                                 ['summary', 'protocol', 'C0', 'source_rule_card', 'validation_summary'])
    require(s['id'] == p['record_id'] == c0['record_id'] == card['record_id'] == rid, 'Source identity mismatch')
    require(s['origin_run_id'] == p['run_id'] and s['variant_id'] == p['variant_id'], 'Execution identity mismatch')
    require(s['fidelity_class'] == p['fidelity_class'] == 'ADAPTED'
            and s['execution_class'] == p['execution_class'] == 'ADAPTED_EXECUTION_PROXY', 'Fidelity mismatch')
    require(s['protocol_sha256'] == c0['protocol_sha256'] == sha(data['protocol']), 'Frozen protocol hash mismatch')
    require(c0['source_sha256'] == p['source']['sha256'] == card['source']['sha256'], 'Source code hash mismatch')
    require(s['strategy_configurations'] == c0['strategy_configurations_frozen'] == 4
            and s['new_control_configurations'] == c0['new_controls'] == 0
            and s['reused_control_configurations'] == 1 and s['actual_strategy_ids'] == 1, 'Count mismatch')
    require(s['benchmark_reference'] == p['benchmark_reference'], 'Reused benchmark mismatch')
    for case, fee, delay in [('base', 8, 1), ('fee0', 0, 1), ('fee20', 20, 1), ('delay2', 8, 2)]:
        require(s['results'][case]['configuration'] == {'name': case, 'fee_bps': fee, 'delay_bars': delay},
                'Configuration alias mismatch')
        require(s['results'][case]['configuration'] in p['cases'], 'Configuration outside frozen protocol')
        curve_csv(json.loads(data[case + '_daily']), s['results'][case]['metrics'], p['execution']['initial_cash'])
    curve = curve_csv(json.loads(data['base_daily']), s['results']['base']['metrics'], p['execution']['initial_cash'])
    output_prefix = f'research/public-strategies/{rid}/artifacts/20261003-dot006-display/'
    derived = dict(schema_version='quantgraph-public-derived-display-manifest/v1', manifest_kind=KIND,
                   id=rid, origin_run_id=s['origin_run_id'], variant_id=s['variant_id'],
                   origin_lab_commit=PIN, status='STAGED_NOT_PUBLISHED',
                   original_private_result_manifest=False, original_results_modified=False,
                   source_artifacts=refs,
                   files={'summary.json': refs['summary'], 'protocol.json': refs['protocol'],
                          'C0.json': refs['C0'],
                          'base-nav-light.csv': dict(path=output_prefix + 'base-nav-light.csv',
                                                     sha256=sha(curve), bytes=len(curve))},
                   transformation=dict(equity='Original absolute USDT value, unchanged',
                                       nav='Original equity / frozen initial_cash 100000; never rebase at first sample',
                                       date='Original date unchanged; valuation_time_utc retains exclusive midnight timestamp',
                                       source_native_drawdown='Original full5m-peak drawdown unchanged; not daily-peak drawdown',
                                       benchmark_curve='Unavailable in this source bundle; no curve generated'),
                   excluded_from_self_hash=['public-display-manifest.json', 'graph-record.json'],
                   exclusion_reason='Manifest hashes source inputs and derived curve; record references this manifest hash; outer delivery manifest binds all new files')
    manifest_raw = encode(derived)
    family = 'PUBLIC-' + rid + '-' + p['source']['class_name'].upper()
    ref = dict(origin_run_id=s['origin_run_id'], variant_id=s['variant_id'], fidelity_class='ADAPTED',
               execution_class='ADAPTED_EXECUTION_PROXY', protocol_sha256=sha(data['protocol']),
               manifest_sha256=sha(manifest_raw), manifest_kind=KIND,
               manifest_path=output_prefix + 'public-display-manifest.json')
    limits = deepcopy(p['limitations']) + [
        card['runtime_boundary'], card['catalog_difference_or_omission'],
        'Source-rule-card preflight status and C0 pre-return status are historical freeze-stage labels; later validation-summary supplies reported checks.',
        'Advanced TA formula independence is not established; predecessor kernel parity was not run.',
        'One strategy, four frozen configurations; benchmark reused from M0311, zero new control runs.',
        'Summary maximum drawdown uses full5m peaks; source_native_drawdown is sampled from those peaks, not a daily-only drawdown.',
        'Benchmark curve unavailable in this source bundle; summary metrics retained without inventing a curve.',
        'Display derived manifest is not the private original result manifest or a native Graph collection manifest.',
    ]
    metric = s['results']['base']['metrics']
    reason = (BLURBS[rid] + ' 明示执行改编，仅诊断。'
              + f"base收益{metric['total_return']:.4%}、原生最大回撤{metric['max_drawdown']:.4%}、"
              + f"完整往返{metric['round_trips']}次；不代表严格复现、样本外或可实盘。")
    record = dict(id=rid, name=p['source']['class_name'] + '：BTC现货5m执行代理',
                  status='tested_adapted_only', reason=reason, tested_variants=1,
                  strategy_configurations=4, control_configurations=0, reused_control_configurations=1,
                  families=[family], implementations=[dict(ref, family=family)], related_results=[ref],
                  fidelity_class='ADAPTED', execution_class='ADAPTED_EXECUTION_PROXY',
                  original_research_classification=p['classification'],
                  projection_status='STAGED_NOT_IMPORTED', definition_revision_bound=False,
                  source_url=p['source']['url'], source=deepcopy(p['source']),
                  plain_language_rule=dict(text=BLURBS[rid], status='SOURCE_GROUNDED_PARAPHRASE',
                                           evidence_roles=['source_rule_card', 'protocol', 'readme']),
                  rules=dict(entry=card['entry'], exit=card['exit'], risk=deepcopy(p['risk']),
                             execution=deepcopy(p['execution']), parameters=deepcopy(p['parameters']),
                             catalog_difference_or_omission=card['catalog_difference_or_omission']),
                  market={k:p['input'][k] for k in ['exchange', 'market_type', 'symbol', 'timeframe']},
                  evaluation=deepcopy(p['evaluation']),
                  economic_basis=dict(paper=dict(status='NOT_ESTABLISHED_IN_APPROVED_SOURCE', value=None),
                                      hypothesis=dict(status='NOT_ESTABLISHED_IN_APPROVED_SOURCE', value=None),
                                      evidence_roles=['readme', 'protocol', 'source_rule_card'],
                                      explanation='Technical source rules are specified; no independently supported economic mechanism or paper is claimed.'),
                  results=deepcopy(s['results']), metric_conventions=deepcopy(p['metric_conventions']),
                  benchmark_reference=deepcopy(s['benchmark_reference']), benchmark_curve=[],
                  audit=dict(source_verification_status=validation['source_signal'],
                             independent_validation=validation['frozen_decimal_oracle'],
                             causality_validation=validation['prefix_future_perturbation'],
                             supplementary_event_time_notional_all_metrics=validation['supplementary_event_time_notional_all_metrics'],
                             validation_basis='Reported by approved public validation-summary; exporter checks bindings and conversions only',
                             strict_replication=False, data_quality_status=s['data_quality_status'],
                             trusted_input=s['trusted_input'], pit_proven=False, oos_claim=s['oos_claim'],
                             promotion=False, definition_bound=False, deployed=False),
                  source_artifacts=refs,
                  data_attribution=dict(provider='Binance', license='CC BY-NC-SA-4.0 plus Binance Dataset Terms',
                                        terms_url='https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md',
                                        strategy_license=card['license'],
                                        changes='Derived normalized daily NAV and display metadata; original source results unchanged',
                                        commercial_or_live_entitlement=False, evidence_role='attribution'),
                  limitations=limits)
    output = {'graph-record.json': encode(record), 'base-nav-light.csv': curve,
              'public-display-manifest.json': manifest_raw}
    for raw in output.values():
        screen(raw)
    return output


def export(repo, output):
    require(not output.exists(), 'Output already exists; immutable export')
    require(shutil.disk_usage(output.parent).free > 5 * 1024**3, '5GiB disk reserve required')
    files, all_sources = {}, []
    for rid in PINS:
        data, refs, originals = sources(repo, rid)
        all_sources.extend(originals)
        prefix = f'research/public-strategies/{rid}/artifacts/20261003-dot006-display/'
        files.update({prefix + name: raw for name, raw in project(rid, data, refs).items()})
    require(len(all_sources) == 101 and sum(r['bytes'] for r in all_sources) == 1389229,
            'Approved source inventory count/bytes mismatch')
    receipt = dict(schema_version='dot006-public-display-export/v1', status='STAGED_NOT_IMPORTED',
                   source_lab_commit=PIN, ids=list(PINS), records=4, frozen_strategy_configurations=16,
                   new_backtests=0, new_controls=0, reused_benchmark_id='M0311',
                   source_files=all_sources, files={name:dict(sha256=sha(raw), bytes=len(raw)) for name, raw in sorted(files.items())},
                   publication_manifest_updates_pending=True, graph_default_inventory_modified=False,
                   site_operations=0, source_files_modified=False)
    files['DELIVERY-MANIFEST.json'] = encode(receipt)
    require(shutil.disk_usage(output.parent).free > 5 * 1024**3 + sum(map(len, files.values())),
            '5GiB disk reserve required for complete output')
    output.mkdir(mode=0o700)
    for name, raw in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab-repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = export(args.lab_repo, args.output)
    print(json.dumps({k:result[k] for k in ['status', 'ids', 'records', 'frozen_strategy_configurations',
                                          'new_backtests', 'new_controls', 'source_files_modified']}, ensure_ascii=False))
