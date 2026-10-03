"""Explicit offline public-display preparation; no private NAV, execution or Site access."""
import argparse
import calendar
from copy import deepcopy
import csv
import io
import json
import math
from pathlib import Path
import re
import shutil

import common_public_display as common

PIN = 'dba8d1d64318f9909cdcfd3bc9c382842a1a742b'
KIND = 'PUBLIC_DERIVED_DISPLAY_MANIFEST'
common.PIN = PIN
PINS = {
    'M0287': (4345, '3e320bbf4c9d8ea97630852344a70ed9ec90c8f8571d25c2fd8a4f41541a4edf'),
    'M0289': (3979, '7e98f610a6758332599e5cc66d5e47489b35ec1b4e242a610cecde15c8b599c5'),
    'M1358': (9545, 'd2e05c532ef25fe05c018893bb01ca661cfb9db319761c6b6e045a3a2db8aebc'),
}
NATIVE_ROLES = dict(common.ROLES)
DAILY_BASE = 'artifacts/20261003-coldstart-v2/'
DAILY_ROLES = dict(summary=DAILY_BASE+'summary.json', protocol='specs/protocol-v1.json',
    C0='specs/C0-v2.json', source_rule_card='source/M1358-sourcecard.safe.json',
    report='M1358.md', readme='README.md', original_record=DAILY_BASE+'graph-record.json',
    original_detail=DAILY_BASE+'graph-detail.json', numerics='specs/numerics-and-exposure-v2.json')
require, sha, encode = common.require, common.sha, common.encode


def screen(raw):
    common.screen(raw)
    require(not re.search(r'(?i)(?:api[_-]?key|client[_-]?secret|password|access[_-]?token)["\s]*[:=]',
                          raw.decode()), 'Credential-like display field')


def load_sources(repo, rid):
    require(rid in PINS, 'Unapproved ID')
    prefix = f'research/public-strategies/{rid}/'
    raw = common.git_bytes(repo, prefix+'publication-manifest.json')
    require((len(raw), sha(raw)) == PINS[rid], 'Publication pin mismatch')
    pub = json.loads(raw)
    require(pub['record_id'] == rid, 'Publication identity mismatch')
    refs = {'publication_manifest': common.source_ref(prefix+'publication-manifest.json', raw)}
    data, all_files = {'publication_manifest': raw}, [refs['publication_manifest']]
    allowed = {}
    for f in pub['files']:
        path = common.safe_path(f['path'])
        require(path not in allowed, 'Duplicate public source path')
        body = common.git_bytes(repo, prefix+path)
        require((len(body), sha(body)) == (f['bytes'], f['sha256']), 'Public source hash mismatch')
        allowed[path] = body
        all_files.append(common.source_ref(prefix+path, body))
    for role, path in (DAILY_ROLES if rid == 'M1358' else NATIVE_ROLES).items():
        require(path in allowed, 'Selected source outside publication allowlist')
        data[role] = allowed[path]
        refs[role] = common.source_ref(prefix+path, allowed[path])
    # The public file is only an inventory of private outputs. Neither its
    # private filenames/values nor any referenced local files enter projection.
    if rid == 'M1358':
        name = DAILY_BASE+'private-output-manifest.json'
        refs['private_output_inventory_reference_only'] = common.source_ref(prefix+name, allowed[name])
    return data, refs, all_files


def period(m):
    return dict(start=m['start'][:10], end='2024-12-31', observations=m['daily_observations'],
        native_observations=m['observations'], total_return=m['total_return'], cagr=m['annualized_return'],
        sharpe=m['sharpe'], max_drawdown=-abs(m['max_drawdown']), annualization=365, oos_claim=False)


def derived_manifest(rid, refs, run, variant, curve_name, curve, sampling):
    return dict(schema_version='quantgraph-public-derived-display-manifest/v2', manifest_kind=KIND,
        projection_profile='DAILY_SAMPLED_APPROVED_DETAIL_V1' if rid=='M1358' else 'NATIVE_5M_RULE_CARD_V2',
        id=rid, origin_run_id=run, variant_id=variant, origin_lab_commit=PIN,
        original_private_result_manifest=False, original_results_modified=False,
        source_artifacts=refs,
        files={**{role:ref for role,ref in refs.items() if role != 'private_output_inventory_reference_only'},
               curve_name:dict(bytes=len(curve),sha256=sha(curve))},
        curve_contract=sampling, excluded_from_self_hash=['public-display-manifest.json','graph-record.json','graph-detail.json'],
        exclusion_reason='Record and detail bind manifest hash; outer delivery manifest binds all generated files without cycles',
        status='STAGED_NOT_PUBLISHED')


def finish(rid, record, detail, refs, curve_name, curve, sampling):
    manifest = derived_manifest(rid, refs, detail['run_id'], detail['variant_id'], curve_name, curve, sampling)
    raw_manifest = encode(manifest)
    reference = dict(origin_run_id=detail['run_id'],variant_id=detail['variant_id'],
        fidelity_class=detail['fidelity_class'],execution_class='ADAPTED_EXECUTION_PROXY',
        protocol_sha256=refs['protocol']['sha256'],manifest_sha256=sha(raw_manifest),manifest_kind=KIND)
    record.update(manifest_kind=KIND,related_results=[reference],
        implementations=[dict(reference,family=detail['family'])],projection_status='STAGED_NOT_IMPORTED',
        definition_revision_bound=False,control_configurations=0,reused_control_configurations=1,
        strategy_configurations=4,tested_variants=1,source_artifacts=refs)
    detail['lineage'] = dict(manifest_kind=KIND,source_display_manifest_sha256=sha(raw_manifest),
        manifest_sha256=sha(raw_manifest),lab_commit=PIN,protocol_sha256=refs['protocol']['sha256'],
        C0_sha256=refs['C0']['sha256'],source_artifacts=refs,definition_revision_bound=False,new_execution_trials=0,
        source_lineage=detail.get('lineage',{}))
    detail.update(manifest_kind=KIND,projection_status='STAGED_NOT_IMPORTED',
        lab_counts=dict(strategy_ids=1,strategy_configurations=4,new_control_configurations=0,
                        reused_control_configurations=1,strict_reproductions=0))
    output = {'graph-record.json':encode(record),'graph-detail.json':encode(detail),
              'public-display-manifest.json':raw_manifest,curve_name:curve}
    for raw in output.values():
        screen(raw)
    return output


def native(rid, data, refs):
    s,p,c,card = (json.loads(data[k]) for k in ['summary','protocol','C0','source_rule_card'])
    require(s['id'] == p['record_id'] == c['record_id'] == card['id'] == rid, 'Native identity mismatch')
    require(s['protocol_sha256'] == c['protocol_sha256'] == sha(data['protocol']), 'Native C0/protocol binding mismatch')
    require(s['origin_run_id'] == p['run_id'] and s['variant_id'] == p['variant_id'], 'Native execution identity mismatch')
    require(s['fidelity_class'] == p['fidelity_class'] == 'ADAPTED', 'Native fidelity mismatch')
    require(c['source_sha256'] == p['source']['sha256'] == card['source']['sha256'], 'Native source-code pin mismatch')
    require(s['strategy_configurations'] == c['strategy_configurations_frozen'] == 4
            and s['new_control_configurations'] == c['new_controls'] == 0
            and s['reused_control_configurations'] == 1, 'Native count mismatch')
    require(s['benchmark_reference'] == p['benchmark_reference'], 'Native benchmark mismatch')
    for case,fee,lag in [('base',8,1),('fee0',0,1),('fee20',20,1),('delay2',8,2)]:
        require(s['results'][case]['configuration'] == {'name':case,'fee_bps':fee,'delay_bars':lag}, 'Native cost mismatch')
        require(s['results'][case]['configuration'] in p['cases'], 'Unfrozen native configuration')
        common.curve_csv(json.loads(data[case+'_daily']),s['results'][case]['metrics'],p['execution']['initial_cash'])
    if rid == 'M0289':
        require(p['parameters']['loaded_parameter_values'] == {'buy_pow':3.849,'sell_pow':3.798}, 'Original powers changed')
        require(s['signals']['entry_rows'] == 0, 'Unexpected PowerTower signal result')
        for case,result in s['results'].items():
            metric = result['metrics']
            require(metric['trades'] == metric['round_trips'] == metric['total_return'] == metric['max_drawdown'] == 0
                    and metric['sharpe'] is None and metric['final_equity'] == 100000, 'Zero-trade result changed')
    curve = common.curve_csv(json.loads(data['base_daily']),s['results']['base']['metrics'],100000)
    rows = list(csv.DictReader(io.StringIO(curve.decode())))
    peak, points = 1.0, []
    for row in rows:
        nav=float(row['nav']);peak=max(peak,nav)
        points.append(dict(date=row['date'],equity=nav,drawdown=nav/peak-1,
            valuation_time_utc=row['valuation_time_utc'],source_native_drawdown=float(row['source_native_drawdown'])))
    family='PUBLIC-'+rid+'-'+p['source']['class_name'].upper()
    m=s['results']['base']['metrics']
    explanation = ('保留SMA5>=SMA200与原生/完整10m、40m RSI比较；不按注释反转均线条件。'
                   if rid=='M0287' else '保留绝对价格3.849/3.798次幂、全部三条件/任一退出与无量过滤；四配置零交易，Sharpe未定义。')
    reason = explanation+f" base收益{m['total_return']:.4%}，完整往返{m['round_trips']}次；仅执行改编诊断。"
    rules=dict(source_signal_rules=deepcopy(card['rules']),source_specific_requirements=deepcopy(p['source_specific_requirements']),
        execution=deepcopy(p['execution']),risk=deepcopy(p['risk']),parameters=deepcopy(p['parameters']),
        catalog_omissions=deepcopy(card['catalog_omissions']))
    limits=deepcopy(p['limitations'])+deepcopy(card['hypotheses'])+[
        'Zero-trade null Sharpe is undefined, never zero or an execution error; parameters are not changed to produce trades.',
        'Display equity uses original absolute USDT / frozen100000, not first-sample rebasing; source native drawdown stays separate.',
        'No benchmark curve reconstructed; reused M0311 summary only.']
    if rid=='M0289':limits.append(card['economic_warning'])
    audit=dict(strict_replication=False,data_quality_status=s['data_quality_status'],trusted_input=s['trusted_input'],
               oos_claim=False,promotion=False,definition_bound=False,deployed=False)
    record=dict(id=rid,name=p['source']['class_name']+'：BTC现货5m执行代理',status='tested_adapted_only',
        reason=reason,families=[family],fidelity_class='ADAPTED',execution_class='ADAPTED_EXECUTION_PROXY',
        source=deepcopy(p['source']),rules=rules,results=deepcopy(s['results']),signals=deepcopy(s['signals']),
        benchmark_reference=deepcopy(s['benchmark_reference']),benchmark_curve=[],audit=audit,limitations=limits,
        economic_basis=dict(paper=None,hypothesis=None,status='NOT_ESTABLISHED_IN_APPROVED_SOURCE'))
    metrics=dict(periods={'full':period(m)},same_instrument_benchmark={'full':period(s['benchmark_reference']['metrics'])},
        cost_sensitivity={str(fee):{'full':period(s['results'][case]['metrics'])} for fee,case in [(0,'fee0'),(20,'fee20')]},
        additional_native_bar_lag={'full':period(s['results']['delay2']['metrics'])})
    sampling=dict(total_observations=366,native_observations=105408,returned_points=366,
        sampling='All retained UTC daily closes; original valuation midnight retained',equity_unit='initial_capital_multiple',
        denominator=100000,first_point_rebased=False,drawdown='daily display peaks',
        source_native_drawdown='source full5m peaks; unchanged',benchmark_curve_available=False)
    detail=dict(id=rid,name=record['name'],run_id=s['origin_run_id'],origin_run_id=s['origin_run_id'],variant_id=s['variant_id'],
        family=family,fidelity_class='ADAPTED',fidelity_reason='ADAPTED_EXECUTION_PROXY, not native limit-fill equivalence',
        metrics=metrics,spec=dict(source_url=p['source']['url'],params={'rules':rules},assumptions=limits),
        audit=audit,curve=points,curve_meta=sampling,limitations=limits,
        data_attribution=dict(provider='Binance',license='CC BY-NC-SA-4.0 plus Binance Dataset Terms',
            terms_url='https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md',
            changes='Derived unit NAV and metadata from publicly approved daily equity; no raw candles or full ledgers'))
    return finish(rid,record,detail,refs,'base-nav-light.csv',curve,sampling)


def daily(data, refs):
    s,p,c,d,r = (json.loads(data[k]) for k in ['summary','protocol','C0','original_detail','original_record'])
    require(s['record_id'] == c['record_id'] == d['id'] == r['id'] == 'M1358', 'Daily identity mismatch')
    require(s['C0_sha256'] == d['lineage']['C0_sha256'] == sha(data['C0']), 'Daily C0 binding mismatch')
    require(c['root_contract_sha256'] == sha(data['protocol']), 'Daily protocol binding mismatch')
    require(s['configurations'] == p['strategy_configurations_expected'] == 4
            and s['new_controls'] == p['new_control_configurations_expected'] == 0, 'Daily count mismatch')
    require(s['fidelity'] == p['fidelity'] == c['fidelity'] == 'ADAPTED'
            and d['fidelity_class'] == r['implementations'][0]['fidelity_class'] == 'HYPOTHESIS', 'Daily fidelity mismatch')
    require(p['execution']['initial_cash'] == 100000
            and d['metrics']['capital_state']['initial_cash_usdt'] == 100000, 'Daily unit denominator mismatch')
    expected_dates=['2023-01-01']+[f'{y}-{m:02d}-{calendar.monthrange(y,m)[1]}' for y in [2023,2024] for m in range(1,13)]
    require([x['date'] for x in d['curve']] == expected_dates, 'Daily display must preserve exactly first plus 24 month ends')
    require(d['curve_meta']['returned_points'] == 25 and d['curve_meta']['observations'] == 731
            and d['curve_meta']['equity_unit'] == 'initial_capital_multiple', 'Daily sampled semantics mismatch')
    require(d['curve'][0]['equity'] == 1 and math.isclose(d['curve'][-1]['equity'],
            s['summary']['base']['metrics']['final_equity']/100000,abs_tol=1e-14), 'Daily NAV values mismatch')
    def match(metric, original):
        require(all(metric[k]==v for k,v in original.items()), 'Daily source metrics changed')
        require(metric['sharpe']==original['sharpe_zero_cash'], 'Daily Sharpe alias mismatch')
    for case,fee,lag in [('base',8,1),('fee0',0,1),('fee20',20,1),('lag2',8,2)]:
        cfg=s['summary'][case]
        require(cfg['fee_bps']==fee and cfg['lag_days']==lag, 'Daily cost/day lag mismatch')
        require({'name':case,'fee_bps':fee,'lag_days':lag} in p['cases'], 'Unfrozen daily configuration')
        view=(d['metrics']['periods'] if case=='base' else d['metrics']['additional_native_bar_lag']
              if case=='lag2' else d['metrics']['cost_sensitivity'][case])
        match(view['2023-2024'],cfg['metrics'])
        for year in ['2023','2024']:match(view[year],cfg['periods'][year])
    require(s['existing_buyhold_reference']==p['benchmark_reference']['result'], 'Daily reused benchmark differs')
    match(d['metrics']['same_instrument_benchmark']['2023-2024'],s['existing_buyhold_reference']['metrics'])
    for year in ['2023','2024']:match(d['metrics']['same_instrument_benchmark'][year],s['existing_buyhold_reference']['periods'][year])
    detail=deepcopy(d)
    detail['metrics']['cost_sensitivity']={str(fee):deepcopy(d['metrics']['cost_sensitivity'][case]) for fee,case in [(0,'fee0'),(20,'fee20')]}
    detail['metrics']['source_cost_key_aliases']={'fee0':'0','fee20':'20'}
    detail['implementation_fidelity']='ADAPTED_EXECUTION_PROXY'
    detail['research_fidelity']='ADAPTED'
    detail['curve_meta'].update(full_daily_curve_published=False,interpolation_claim=False,
        source_drawdown_basis='Source drawdown retained at samples; full daily peaks, not recomputed from 25 points',
        private_daily_nav_used=False,first_point_rebased=False)
    detail['spec']['params'].update(execution=deepcopy(p['execution']),source_signal_rules=deepcopy(p['source_signal_rules']),
                                  reference_ema=deepcopy(p['reference_ema']),numerics=deepcopy(json.loads(data['numerics'])))
    detail['limitations']+=['Only first close plus 24 UTC month ends are public; 25 samples do not constitute 731 daily points.',
        'Graph HYPOTHESIS enum retained from original approved display; actual research fidelity ADAPTED_EXECUTION_PROXY remains explicit.',
        'Original private-output manifest is provenance only, never a public derived-display manifest or permission to copy its outputs.']
    record=deepcopy(r)
    record.update(status='tested_hypothesis_only',source_status=r['status'],fidelity_class='HYPOTHESIS',
        research_fidelity='ADAPTED',execution_class='ADAPTED_EXECUTION_PROXY',results=deepcopy(s['summary']),
        benchmark_reference=deepcopy(p['benchmark_reference']),benchmark_curve=[],source=deepcopy(p['source']),
        rules=dict(source_signal_rules=deepcopy(p['source_signal_rules']),execution=deepcopy(p['execution'])),
        economic_basis=dict(paper=None,paper_status='FORUM_NOT_PAPER',hypothesis='趋势延续假设',
            status='RESEARCH_INTERPRETATION_NOT_SOURCE_RISK_PREMIUM_PROOF',evidence_role='report'),
        limitations=deepcopy(detail['limitations']))
    return finish('M1358',record,detail,refs,'base-nav-sampled.json',encode(d['curve']),detail['curve_meta'])


def export(repo, output):
    require(not output.exists(), 'Use a fresh immutable output directory')
    files, inventory, checks = {}, [], []
    for rid in PINS:
        data,refs,source_files=load_sources(repo,rid)
        inventory.extend(source_files)
        output_files=daily(data,refs) if rid=='M1358' else native(rid,data,refs)
        prefix=f'research/public-strategies/{rid}/artifacts/20261003-public-display-prep/'
        files.update({prefix+name:raw for name,raw in output_files.items()})
        p=json.loads(data['protocol']);ref=p['benchmark_reference']
        raw=common.git_bytes(repo,ref['summary_path'])
        require(sha(raw)==ref['summary_sha256'], 'Reused benchmark summary hash mismatch')
        benchmark=json.loads(raw)
        expected=benchmark['buyhold'] if rid=='M1358' else benchmark['results']['buyhold']
        require((expected==ref['result']) if rid=='M1358' else (expected['metrics']==ref['metrics']),
                'Reused benchmark values differ')
        checks.append(dict(id=rid,curve_points=25 if rid=='M1358' else 366,configurations=4,
            benchmark_summary_sha256=sha(raw),new_runs=0,private_daily_nav_used=False))
    manifest=dict(schema_version='explicit-three-id-public-display-preparation/v1',source_commit=PIN,
        status='STAGED_NOT_IMPORTED',ids=list(PINS),records=3,frozen_configurations=12,new_executions=0,new_controls=0,
        default_graph_inventory_changed=False,site_operations=0,source_files=inventory,checks=checks,
        files={name:dict(bytes=len(raw),sha256=sha(raw)) for name,raw in sorted(files.items())})
    files['DELIVERY-MANIFEST.json']=encode(manifest)
    require(shutil.disk_usage(output.parent).free>5*1024**3+sum(map(len,files.values())), '5GiB reserve required')
    output.mkdir(mode=0o700)
    for name,raw in files.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    return manifest


if __name__=='__main__':
    require(sha(Path(__file__).with_name('common_public_display.py').read_bytes())=='f5a8536676f1575f55adcf3b286ba92c198a01c070399250fbf933f8937c9c13', 'Frozen export helper changed')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab-repo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=export(args.lab_repo,args.output)
    print(json.dumps({k:result[k] for k in ['status','ids','records','frozen_configurations','new_executions','site_operations']}))
