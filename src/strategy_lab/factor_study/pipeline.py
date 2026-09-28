"""Graph definition -> frozen diagnostic -> real values -> private Graph evidence."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import shutil

import numpy as np
import pandas as pd
from jsonschema import Draft202012Validator

from strategy_lab.data.factors.engine import compute_factor_bundle
from strategy_lab.knowledge.market_dataset import read_market_dataset
from strategy_lab.knowledge.market_contract import sha
from strategy_lab.research.exposure import append_record, overlaps, read_ledger
from .factors import SEMANTICS, code_hash, registry, validate_definition, definition_name
from .semantics import validate_semantics
from .diagnostics import association, incremental, label_frame
from .trial_adapter import UnavailableTrialAdapter


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')
    return path


def ref(path):
    path = Path(path).resolve()
    return {'uri': str(path), 'sha256': sha(path)}


def validate_schema(value, graph_root, name):
    path = Path(graph_root) / 'contracts/factor-study/v1' / (name + '.schema.json')
    Draft202012Validator(json.loads(path.read_text())).validate(value)


def code_files(lab_root):
    root = Path(lab_root)
    paths = list((root / 'src/strategy_lab/factor_study').glob('*.py'))
    paths += [root / p for p in [
        'src/strategy_lab/data/factors/base.py', 'src/strategy_lab/data/factors/engine.py',
        'src/strategy_lab/knowledge/market_core.py', 'src/strategy_lab/knowledge/market_contract.py',
        'src/strategy_lab/knowledge/market_dataset.py', 'src/strategy_lab/research/exposure.py',
        'tests/fixtures/factor_study/qlib-golden.json',
        'src/strategy_lab/research/trials.py', 'src/strategy_lab/research/integrity.py',
        'src/strategy_lab/research/accounting.py',
    ]]
    return {str(p.relative_to(root)): sha(p) for p in sorted(paths)}


def verify_settings(s):
    if s['axis'] != 'TIME_SERIES' or s['frequency'] != '1d' or len(s['symbols']) != 1:
        raise ValueError('V1 implements single-asset daily TIME_SERIES studies only')
    horizons = s['label_horizons']
    if not horizons or len(set(horizons)) != len(horizons) or any(type(h) is not int or not 1 <= h <= 120 for h in horizons):
        raise ValueError('Positive unique horizons required')
    a, e, split, b = [pd.Timestamp(s[k]) for k in ('start', 'evaluation_start', 'split', 'end')]
    if any(t.tzinfo is None for t in (a, e, split, b)) or not a <= e < split < b:
        raise ValueError('Invalid aware study windows')
    segments = s['segments']
    if (not segments or pd.Timestamp(segments[0][1]) != e or pd.Timestamp(segments[-1][2]) != b
            or any(pd.Timestamp(x[1]) >= pd.Timestamp(x[2]) for x in segments)
            or any(x[2] != y[1] for x, y in zip(segments, segments[1:]))):
        raise ValueError('Segments must partition the evaluation grid')
    boot = s['bootstrap']
    if boot['block_bars'] < max(horizons) or boot['replications'] < 100 or boot['confidence'] != .95:
        raise ValueError('Invalid dependence-aware bootstrap settings')
    if s['research_status'] != 'EXPLORATORY_RETROSPECTIVE':
        raise ValueError('Task C confirmation unavailable in this pipeline')


def load_input(plan):
    """Re-audit native bytes and rights on every consumption; no persisted PASS shortcut."""
    dataset = plan['input']
    for key in ('manifest', 'acquisition_contract'):
        if sha(dataset[key]['uri']) != dataset[key]['sha256']:
            raise ValueError('Pinned input changed: ' + key)
    f, acquisition, manifest, rights, coverage = read_market_dataset(
        dataset['acquisition_contract']['uri'], dataset['manifest']['uri'], formal=True)
    s = plan['settings']
    if (manifest['dataset_profile'] != 'TRUSTED_OHLCV_CORE_V1'
            or manifest['symbols'] != s['symbols'] or manifest['provider'] != s['provider']
            or manifest['frequency'] != s['frequency'] or acquisition['use_context'] != 'PRIVATE_INTERNAL_RESEARCH'):
        raise ValueError('Study and trusted market identity/rights differ')
    f = f[(f.ts >= pd.Timestamp(s['start'])) & (f.ts < pd.Timestamp(s['end']))].reset_index(drop=True)
    expected = pd.date_range(s['start'], s['end'], freq='1D', inclusive='left')
    if list(f.ts) != list(expected) or not f.ts.is_unique:
        raise ValueError('Requested study grid missing, duplicated or disordered')
    if f[['exchange', 'symbol', 'market_type', 'timeframe']].drop_duplicates().shape[0] != 1:
        raise ValueError('Mixed market identities')
    if not np.isfinite(f[['open', 'high', 'low', 'close']]).all().all() or (f.close <= 0).any():
        raise ValueError('Invalid required prices')
    return f, manifest, rights, coverage


def freeze(selection_path, manifest_path, acquisition_contract, output, *, graph_root, lab_root,
           exposure_ledger=None, trial_adapter=None):
    from quantgraph import FactorDB
    from quantgraph.factor_study import definition_identity
    output, lab_root = Path(output).resolve(), Path(lab_root).resolve()
    output.mkdir(parents=True, exist_ok=False)
    selection = json.loads(Path(selection_path).read_text())
    request = selection['request']
    validate_schema(request, graph_root, 'research-request')
    if request['study_type'] != 'FACTOR_DIAGNOSTIC':
        raise ValueError('Only factor diagnostic requests are implemented')
    s = selection.get('resolved_settings', request['requested_settings'])
    verify_settings(s)
    definitions = selection['definitions']
    db = FactorDB(graph_root, profile='commercial')
    if s['names'] != [definition_name(v) for v in definitions]:
        raise ValueError('Settings and selected definition order differ')
    expected_refs = []
    for v in definitions:
        factor = validate_definition(v)
        if v != db.get_variant(v['factor_variant_id']):
            raise ValueError('Graph definition snapshot changed')
        identity = definition_identity(v)
        expected_refs.append(dict(entity_type='FactorVariant', entity_id=identity['factor_variant_id'],
                                  definition_revision=identity['definition_revision']))
        if (pd.Timestamp(s['evaluation_start']) - pd.Timestamp(s['start'])).days < factor.metadata.lookback - 1:
            raise ValueError('Insufficient frozen warmup')
    if request['entity_refs'] != expected_refs:
        raise ValueError('DRAFT references do not match the selected definitions')
    plan = {'schema_version': 'lab-factor-plan/v1', 'request_id': request['request_id'],
            'frozen_at': datetime.now(timezone.utc).isoformat(), 'settings': s,
            'definitions': definitions, 'selection': ref(selection_path),
            'input': {'manifest': ref(manifest_path), 'acquisition_contract': ref(acquisition_contract)},
            'code_files': code_files(lab_root), 'code_commit_at_freeze': subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], cwd=lab_root, text=True).strip(),
            'schema_files': {n: ref(Path(graph_root) / 'contracts/factor-study/v1' / (n + '.schema.json'))
                             for n in ('research-request', 'factor-study-result')},
            'graph_code_files': {p: ref(Path(graph_root) / p) for p in (
                'sdk/quantgraph/factor_study.py', 'models/factor_study.py', 'graph/factor_study_store.py')},
            'counts': {'concept': len({v['canonical_factor_id'] for v in definitions}),
                       'definition': len({v['formula_id'] for v in definitions}),
                       'variant': len(definitions), 'economic_groups': s['economic_group_count']},
            'environment': {n: importlib.metadata.version(n) for n in ('numpy', 'pandas', 'jsonschema')},
            'promotion_allowed': False}
    f, manifest, rights, coverage = load_input(plan)
    for relative in plan['code_files']:
        target = output / 'source' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(lab_root / relative, target)
    plan['code_artifact'] = ref(write(output / 'code-manifest.json', plan['code_files']))
    plan['dataset'] = {'uri': str(Path(manifest_path).resolve().parent / manifest['dataset_path']),
                       'sha256': manifest['dataset_sha256']}
    plan['dataset_version'] = manifest['dataset_version']
    plan['rights'] = rights
    plan['coverage'] = coverage
    plan['plan_sha256'] = digest(plan)
    write(output / 'plan.json', plan)
    experiments = [dict(experiment_id=definition_name(v) + '-h' + str(h),
                        factor_variant_id=v['factor_variant_id'], definition_revision=definition_identity(v)['definition_revision'],
                        implementation_id='lab:qlib-price-v1:' + definition_name(v), parameters=v['parameters'],
                        horizon_bars=h, axis='TIME_SERIES', preprocessing=s['preprocessing'],
                        segments=s['segments'], status='PLANNED') for v in definitions for h in s['label_horizons']]
    write(output / 'experiments.json', experiments)
    prior = overlaps(read_ledger(Path(exposure_ledger)), start=s['start'], end=s['end']) if exposure_ledger else []
    write(output / 'prior-exposure.json', {'records': prior, 'source': str(exposure_ledger),
          'completeness': 'UNKNOWN; empty records never certify unseen history'})
    append_record(output / 'exposure.jsonl', {
        'id': plan['plan_sha256'], 'kind': 'exposure', 'family': 'factor-research-loop',
        'window_start': s['start'], 'window_end': s['end'], 'evidence_class': 'historical_replay',
        'trial_count': len(experiments), 'trial_count_scope': 'THIS_BATCH_DEFINITION_X_HORIZON',
        'cumulative_trial_count': None, 'selection_reason': s['selection_basis'],
        'artifacts': {'plan.json': sha(output / 'plan.json'), 'experiments.json': sha(output / 'experiments.json')},
    })
    adapter = trial_adapter or UnavailableTrialAdapter()
    write(output / 'trial-registration.json', adapter.register(plan, experiments))
    return plan


def permissions(rights):
    internal = {'internal_use': 'ALLOWED', 'public_display': 'DENIED',
                'evidence': rights['rights_id'] + ': ' + rights['license_url']}
    return {
        'definition': {'internal_use': 'ALLOWED', 'public_display': 'ALLOWED', 'evidence': 'Qlib MIT, Microsoft attribution retained'},
        'implementation': {'internal_use': 'ALLOWED', 'public_display': 'ALLOWED', 'evidence': 'Lab MIT implementation; upstream Qlib MIT notice'},
        'market_data': internal, 'derived_result': dict(internal),
    }


def study_one(plan, frame, v, output, plan_path, lab_root, registration):
    from quantgraph.factor_study import definition_identity
    name = definition_name(v)
    factor = validate_definition(v)
    folder = output / 'runs' / name
    folder.mkdir(parents=True, exist_ok=False)
    implementation = dict(implementation_id='lab:qlib-price-v1:' + name, version=factor.version(),
        code={'uri': str(Path(__file__).with_name('factors.py')), 'sha256': code_hash()},
        semantic_version='qlib-price-v1', parameters=v['parameters'], required_fields=list(factor.metadata.inputs),
        axis='TIME_SERIES', semantics=SEMANTICS)
    mapping = {'identity': definition_identity(v), 'implementation': implementation,
               'mapping_status': 'UNVERIFIED', 'semantic_tests': []}
    rights = permissions(plan['rights'])
    value = dict(schema_version='factor-study-result/v1',
        run_id='factor-study-' + digest([plan['plan_sha256'], name])[:32], request_id=plan['request_id'],
        study_type='FACTOR_DIAGNOSTIC', mapping=mapping, dataset=plan['dataset'], contract=ref(plan_path),
        code=plan['code_artifact'],
        sample={'axis': 'TIME_SERIES', 'real_market_data': True, 'rows': len(frame),
                'symbols': plan['settings']['symbols'], 'start': plan['settings']['start'],
                'end_exclusive': plan['settings']['end'], 'dataset_version': plan['dataset_version']},
        labels=[{'horizon_bars': h, 'formula': 'close[t+h]/close[t]-1', 'tail': 'missing, excluded',
                 'label_overlap': h > 1} for h in plan['settings']['label_horizons']],
        methods={'association': 'TIME_SERIES Pearson / average-tie Spearman across dates, never cross-sectional IC',
                 'bootstrap': plan['settings']['bootstrap'], 'preprocessing': plan['settings']['preprocessing'],
                 'incremental': plan['settings']['incremental_baseline']},
        results={}, status='FAILED', permissions=rights, artifacts=[], trial_registry=registration,
        integrity_assessment={'status': 'UNKNOWN', 'evidence': [], 'independent_verification': False},
        limitations=[
            'Exploratory retrospective; Task C confirmation and virgin holdout unavailable; cumulative search count unknown.',
            'Single BTC/EUR spot asset; original Qlib equity definitions transferred across markets; no equity reproduction or CS claim.',
            'Historical as-of data; real-time received_at and later source revisions not proven.',
            'Paired circular block bootstrap mitigates overlap/autocorrelation; block length 20 fixed, stationarity uncertain; no multiplicity-adjusted discovery.',
            'Association is not causation or portfolio return; no Sharpe, DSR, PBO, trading costs or profitability conclusion.',
            'Private internal use only; source rights prohibit public data and derivative research display.',
        ], research_status='EXPLORATORY_RETROSPECTIVE', promotion_allowed=False)
    try:
        semantic = validate_semantics(name, frame, Path(lab_root) / 'tests/fixtures/factor_study/qlib-golden.json')
        semantic_path = write(folder / 'semantic-tests.json', semantic)
        mapping['semantic_tests'] = [dict(name=k, status=semantic[k], evidence=ref(semantic_path))
                                     for k in ('hand_calculated', 'reference_parity', 'real_market_boundaries')]
        mapping['mapping_status'] = 'VERIFIED'
        raw = compute_factor_bundle(frame, registry([name]))[name]
        full = frame[list(factor.metadata.inputs)].notna().all(axis=1).rolling(
            factor.metadata.lookback, min_periods=factor.metadata.lookback).sum().eq(factor.metadata.lookback)
        values = raw.where(full & np.isfinite(raw))
        features = frame[['ts', 'symbol']].copy()
        features['bar_close_time'] = frame.ts + pd.Timedelta(days=1)
        features[name] = values
        settings = plan['settings']
        results = {'quality': {'raw_missing': int(raw.isna().sum()), 'raw_infinite': int(np.isinf(raw).sum()),
                   'warmup_excluded': int((~full).sum()), 'finite_count': int(values.notna().sum()),
                   'coverage': float(values.notna().mean()), 'constant': bool(values.nunique() <= 1)},
                   'associations': [], 'incremental': []}
        for h in settings['label_horizons']:
            labels = label_frame(frame, h)
            features['label_' + str(h)] = labels.label
            for segment, start, end in settings['segments']:
                mask = (frame.ts >= pd.Timestamp(start)) & (frame.ts < pd.Timestamp(end))
                # Labels may not cross descriptive segment boundaries either.
                y = labels.label.where(labels.label_end < pd.Timestamp(end))
                boot = settings['bootstrap']
                stat = association(values[mask], y[mask], block_bars=boot['block_bars'],
                    replications=boot['replications'], seed=boot['seed'] + h, minimum_pairs=settings['minimum_pairs'])
                results['associations'].append({'segment': segment, 'horizon_bars': h, **stat})
            results['incremental'].append({'horizon_bars': h, **incremental(frame, values, h, settings['split'], settings['evaluation_start'])})
        feature_path = folder / 'factor-values.parquet'
        features.to_parquet(feature_path, index=False)
        value['results'] = results
        valid_stats = all(a['status'] == 'DESCRIPTIVE' for a in results['associations'])
        value['status'] = ('SUCCESS' if valid_stats and not results['quality']['constant']
                           and not results['quality']['raw_infinite'] and results['quality']['coverage'] >= .95
                           else 'INVALID')
        value['integrity_assessment'] = {'status': 'INTERNAL_CHECKED', 'evidence': [ref(semantic_path), plan['input']['manifest']],
                                         'independent_verification': False}
        value['artifacts'] = [{**ref(p), 'kind': kind, 'permissions': rights['derived_result']}
                              for p, kind in [(semantic_path, 'semantic-tests'), (feature_path, 'factor-values')]]
    except Exception as exc:
        mapping['mapping_status'] = 'FAILED'
        value['results'] = {'failure_type': type(exc).__name__, 'reason': str(exc)}
        value['integrity_assessment']['status'] = 'FAILED'
    return value


def run(plan_path, *, graph_root, lab_root, journal, only=None, trial_adapter=None):
    from quantgraph import FactorDB
    from quantgraph.graph.factor_study_store import FactorStudyRepository
    plan_path = Path(plan_path).resolve()
    output = plan_path.parent
    plan = json.loads(plan_path.read_text())
    if digest({k: v for k, v in plan.items() if k != 'plan_sha256'}) != plan['plan_sha256']:
        raise ValueError('Frozen plan changed')
    if code_files(lab_root) != plan['code_files']:
        raise ValueError('Code or semantic reference changed after freeze; create a new plan')
    for item in [*plan['schema_files'].values(), *plan['graph_code_files'].values()]:
        if sha(item['uri']) != item['sha256']:
            raise ValueError('Contract schema changed after freeze')
    frame, _, _, _ = load_input(plan)
    definitions = plan['definitions']
    if only is not None:
        if only not in [definition_name(v) for v in definitions]:
            raise ValueError('Unplanned factor')
        definitions = [v for v in definitions if definition_name(v) == only]
    registration = json.loads((output / 'trial-registration.json').read_text())
    repo = FactorStudyRepository(journal, FactorDB(graph_root, profile='commercial'))
    receipts = []
    for v in definitions:
        result_path = output / 'runs' / definition_name(v) / 'result.json'
        if result_path.exists():
            result = json.loads(result_path.read_text())
            for artifact in result['artifacts']:
                if sha(artifact['uri']) != artifact['sha256']:
                    raise ValueError('Existing study artifact changed')
        else:
            if trial_adapter is not None and hasattr(trial_adapter, 'start'):
                trial_adapter.start(registration, v['factor_variant_id'])
            result = study_one(plan, frame, v, output, plan_path, lab_root, registration)
            if trial_adapter is not None and hasattr(trial_adapter, 'complete'):
                assessment = trial_adapter.complete(registration, result)
                assessment_path = write(result_path.parent / 'integrity-assessment.json', assessment)
                result['trial_registry'] = {**registration, 'assessment': assessment}
                result['integrity_assessment']['evidence'].append(ref(assessment_path))
                result['artifacts'].append({**ref(assessment_path), 'kind': 'integrity-assessment',
                                           'permissions': result['permissions']['derived_result']})
                result['limitations'][0] = ('Historical exploratory result; prior exposure is known and '
                    'historical search completeness remains UNKNOWN. Trial registration is not independent confirmation.')
            validate_schema(result, graph_root, 'factor-study-result')
            write(result_path, result)
        receipt = repo.put(result)
        receipt['study_status'] = result['status']
        back = repo.query(v['factor_variant_id'], profile='research')
        if result not in back:
            raise ValueError('FactorStudy readback differs from submitted evidence')
        receipt_path = result_path.parent / 'writeback.json'
        if not receipt_path.exists():
            write(receipt_path, receipt)
        receipts.append(receipt)
    # Only finish batch diagnostics when every planned definition has an outcome.
    paths = [output / 'runs' / definition_name(v) / 'result.json' for v in plan['definitions']]
    if all(p.exists() for p in paths) and not (output / 'batch-result.json').exists():
        outcomes = [json.loads(p.read_text()) for p in paths]
        names = [definition_name(v) for v, r in zip(plan['definitions'], outcomes) if r['status'] == 'SUCCESS']
        bundle = compute_factor_bundle(frame, registry(names)) if names else pd.DataFrame()
        # Full common warmup, no future labels used for the redundancy matrix.
        corr = bundle[names].iloc[6:].corr(method='spearman') if names else pd.DataFrame()
        redundancy = [{'left': a, 'right': b, 'spearman': float(corr.loc[a, b])}
                      for i, a in enumerate(names) for b in names[i + 1:] if np.isfinite(corr.loc[a, b])]
        adapter = trial_adapter or UnavailableTrialAdapter()
        adjudication = adapter.evaluate(registration, outcomes)
        write(output / 'batch-result.json', {
            'planned': plan['counts'], 'real_computation': sum(r['mapping']['mapping_status'] == 'VERIFIED' for r in outcomes),
            'successful_diagnostics': sum(r['status'] == 'SUCCESS' for r in outcomes),
            'failed_or_invalid': [r['run_id'] for r in outcomes if r['status'] != 'SUCCESS'],
            'ts': len(outcomes), 'cs': 0, 'writeback_readback': len(outcomes), 'redundancy': redundancy,
            'task_c_assessment': adjudication, 'research_status': 'EXPLORATORY_RETROSPECTIVE',
            'promotion_allowed': False, 'result_files': [ref(p) for p in paths],
        })
        experiments = json.loads((output / 'experiments.json').read_text())
        for item in experiments:
            idx = next(i for i, v in enumerate(plan['definitions']) if v['factor_variant_id'] == item['factor_variant_id'])
            item.update(status=outcomes[idx]['status'], run_id=outcomes[idx]['run_id'], result=ref(paths[idx]))
        write(output / 'trial-outcomes.json', experiments)
        write_report(output, plan, outcomes, redundancy)
    return receipts


def write_report(output, plan, outcomes, redundancy):
    lines = ['# 因子研究诊断（私有）', '', 'EXPLORATORY_RETROSPECTIVE；不构成因果、盈利或晋级结论。', '',
             f"计划：{plan['counts']}；标签：{plan['settings']['label_horizons']} 根。", '',
             '| 定义 | 状态 | 标签 | 分段 | 样本数 | TS Pearson | TS Spearman | Spearman 95% CI |',
             '|---|---|---:|---|---:|---:|---:|---|']
    for v, r in zip(plan['definitions'], outcomes):
        for a in r['results'].get('associations', []):
            lines.append(f"| {definition_name(v)} | {r['status']} | {a['horizon_bars']} | {a['segment']} | {a['n']} | {a['pearson']} | {a['spearman']} | {a['ci95'].get('spearman')} |")
        if r['status'] != 'SUCCESS':
            lines.append(f"\n失败或无效：{definition_name(v)} {r['results']}\n")
    lines += ['', '## 简单基准的增量信息', '', '正数仅表示后段 MSE 降低；历史曝光未知，不能称为确认性 OOS。', '',
              '| 定义 | 标签 | 训练样本 | 后段样本 | MSE 降低 |', '|---|---:|---:|---:|---:|']
    for v, r in zip(plan['definitions'], outcomes):
        for a in r['results'].get('incremental', []):
            lines.append(f"| {definition_name(v)} | {a['horizon_bars']} | {a['train_n']} | {a['late_n']} | {a.get('mse_reduction')} |")
    lines += ['', '## 相关与冗余', '', '完整成对 Spearman 矩阵保存在 batch-result.json；不按最大关联挑赢家。',
              f"共 {len(redundancy)} 个成对关系。", '', '## 限制', '']
    lines += ['- ' + s for s in outcomes[0]['limitations']]
    (output / 'report.md').write_text('\n'.join(lines) + '\n')
