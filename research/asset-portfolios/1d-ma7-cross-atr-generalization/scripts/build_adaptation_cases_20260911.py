"""Build causal daily features and matched V3/defense/extension outcomes.

Consumes only hash-pinned retained family inputs; never reads a lake default.
All output directories are new. Completed outputs are never overwritten.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from common import BASE, ROOT, sha, write_json
from run_exit_state_machine_20260910 import load_engine, cases, PIN

OLD = BASE / 'artifacts/state_machine_20260910'
OUT = BASE / 'artifacts/adaptation_20260911/cases'
CONTRACT = BASE / 'specs/contract-adaptation-learning-20260911.md'
HISTORY = ['history_results', 'history_verified_results']
ACTIONS = {'V3': 'v3', 'S1_DEFENSE': 'defense', 'S3_EXTENSION': 'extension'}
ASSET_COLUMNS = [
    'asset_observed_days_capped90', 'asset_efficiency60', 'asset_cross_frequency60',
    'asset_return_autocorr60', 'asset_wick_ratio60', 'asset_atr_pct_median60',
    'asset_gap_atr_p95_60', 'asset_log10_quote_volume_median60', 'asset_cost_to_tr60',
    'asset_v3_closed_count12', 'asset_v3_mean_return12', 'asset_v3_pf_bounded12',
    'asset_v3_win_rate12',
]
ENTRY_SUFFIXES = [
    'slope', 'previous_slope', 'slope_deceleration', 'rsi', 'ma7_distance_atr',
    'ma30_distance_atr', 'ma30_slope_atr', 'body_atr', 'close_location',
    'favorable_wick_atr', 'adverse_wick_atr', 'pre_displacement5_atr',
    'pre_displacement10_atr', 'pre_displacement20_atr', 'pre_efficiency20',
    'pre_tr_ratio5_20', 'pre_cross_count20', 'signal_stop_distance_pct',
    'btc_return20', 'btc_return60', 'btc_ma30_distance',
]
FEATURE_DESCRIPTIONS = {
    'asset_observed_days_capped90': '当前连续段已闭合日数，上限90日',
    'asset_efficiency60': '本日收盘与60日前收盘净位移绝对值/最近60个收盘变化绝对值之和',
    'asset_cross_frequency60': '截至本日最近60日MA7穿越次数/60',
    'asset_return_autocorr60': '截至本日最近60个收盘简单收益与各自前一期收益的相关系数',
    'asset_wick_ratio60': '最近60日(上影线+下影线)/(最高-最低)的中位数',
    'asset_atr_pct_median60': '最近60日ATR14/收盘价的中位数，小数',
    'asset_gap_atr_p95_60': '最近60日abs(开盘-前收盘)/前ATR14的95分位',
    'asset_log10_quote_volume_median60': '最近60日成交额中位数的10底对数',
    'asset_cost_to_tr60': '往返成本0.0028/最近60日真实波幅除以收盘价的中位数',
    'asset_v3_closed_count12': '信号收盘前已自然退出的最近最多12笔本段影子V3数量',
    'asset_v3_mean_return12': '上述已结束交易的入场权益收益率均值',
    'asset_v3_pf_bounded12': '上述正收益之和/(正收益之和+亏损绝对值之和)，无交易或全零为缺失',
    'asset_v3_win_rate12': '上述已结束交易收益严格大于0的比例',
    'slope': '方向乘信号日MA7斜率/ATR14',
    'previous_slope': '方向乘前日MA7斜率/前ATR14',
    'slope_deceleration': '方向乘(前日归一斜率-本日归一斜率)，正值表示顺势斜率降速',
    'rsi': '方向乘(RSI6-50)/50',
    'ma7_distance_atr': '方向乘(信号收盘-MA7)/ATR14',
    'ma30_distance_atr': '方向乘(信号收盘-MA30)/ATR14',
    'ma30_slope_atr': '方向乘(MA30-前MA30)/ATR14',
    'body_atr': '方向乘(信号收盘-开盘)/ATR14',
    'close_location': '多头为(收盘-最低)/(最高-最低)，空头为(最高-收盘)/(最高-最低)',
    'favorable_wick_atr': '多头上影线或空头下影线/ATR14',
    'adverse_wick_atr': '多头下影线或空头上影线/ATR14',
    'pre_displacement5_atr': '信号前1日结束的5日方向位移/该前日ATR14',
    'pre_displacement10_atr': '信号前1日结束的10日方向位移/该前日ATR14',
    'pre_displacement20_atr': '信号前1日结束的20日方向位移/该前日ATR14',
    'pre_efficiency20': '信号前1日结束的20日绝对净位移/收盘变化绝对值之和',
    'pre_tr_ratio5_20': '信号前1日结束的5日真实波幅均值/20日真实波幅均值',
    'pre_cross_count20': '信号前1日结束的20日MA7穿越次数',
    'signal_stop_distance_pct': '(方向乘(信号收盘-MA7)+1.5ATR14)/信号收盘，小数，不用次日开盘',
    'btc_return20': '方向乘BTC截至信号日收盘的20日简单收益',
    'btc_return60': '方向乘BTC截至信号日收盘的60日简单收益',
    'btc_ma30_distance': '方向乘(BTC信号收盘/BTC MA30-1)',
}


def read_trades(path):
    try:
        t = pd.read_csv(path, float_precision='round_trip')
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    for c in ['entry_time', 'signal_day', 'exit_time', 'exit_interval_end']:
        if c in t:
            t[c] = pd.to_datetime(t[c], utc=True)
    return t


def divide(a, b):
    return a.div(b.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def closed_trade_features(d, baseline):
    result = np.full((len(d), 4), np.nan)
    result[:, 0] = 0
    if baseline.empty:
        return result
    t = baseline[baseline.exit_reason.ne('sample_end')].sort_values('exit_time')
    stamps = pd.DatetimeIndex(t.exit_time).as_unit('ns').asi8
    values = t.return_on_entry_equity.to_numpy(float)
    for i, stamp in enumerate(d.timestamp):
        # The signal candle closes at t+1d. Equality is unavailable here.
        n = int(np.searchsorted(stamps, (stamp + pd.Timedelta(days=1)).value, side='left'))
        v = values[max(0, n-12):n]
        result[i, 0] = len(v)
        if len(v):
            positive = float(v[v > 0].sum()); negative = float(-v[v < 0].sum())
            result[i, 1] = float(v.mean())
            result[i, 2] = positive/(positive+negative) if positive+negative > 0 else np.nan
            result[i, 3] = float((v > 0).mean())
    return result


def causal_features(d, baseline, btc):
    out = d.copy()
    c = d.close; a = d.atr; prev = c.shift(1)
    tr = pd.concat([d.high-d.low, (d.high-prev).abs(), (d.low-prev).abs()], axis=1).max(axis=1)
    move = c.diff(); ret = c.pct_change(fill_method=None); span = d.high-d.low
    upper = d.high-pd.concat([d.open, c], axis=1).max(axis=1)
    lower = pd.concat([d.open, c], axis=1).min(axis=1)-d.low
    out['ready90'] = np.arange(len(d)) >= 89
    out['asset_observed_days_capped90'] = np.minimum(np.arange(len(d))+1, 90)
    out['asset_efficiency60'] = divide((c-c.shift(60)).abs(), move.abs().rolling(60).sum())
    out['asset_cross_frequency60'] = d.cross.ne(0).rolling(60).mean()
    out['asset_return_autocorr60'] = ret.rolling(60).corr(ret.shift(1))
    out['asset_wick_ratio60'] = divide(upper+lower, span).rolling(60).median()
    out['asset_atr_pct_median60'] = divide(a, c).rolling(60).median()
    out['asset_gap_atr_p95_60'] = divide((d.open-prev).abs(), a.shift(1)).rolling(60).quantile(.95)
    out['asset_log10_quote_volume_median60'] = np.log10(d.quote_volume.where(d.quote_volume.gt(0)).rolling(60).median())
    out['asset_cost_to_tr60'] = .0028/divide(tr, c).rolling(60).median()
    out[ASSET_COLUMNS[-4:]] = closed_trade_features(d, baseline)
    market = btc.reindex(pd.DatetimeIndex(d.timestamp))
    for side, prefix in [(1, 'long_'), (-1, 'short_')]:
        vals = {
            'slope': side*d.slope,
            'previous_slope': side*d.slope.shift(1),
            'slope_deceleration': side*(d.slope.shift(1)-d.slope),
            'rsi': side*(d.rsi-50)/50,
            'ma7_distance_atr': side*divide(c-d.ma, a),
            'ma30_distance_atr': side*divide(c-d.ma30, a),
            'ma30_slope_atr': side*divide(d.ma30-d.prev_ma30, a),
            'body_atr': side*divide(c-d.open, a),
            'close_location': divide(c-d.low if side == 1 else d.high-c, span),
            'favorable_wick_atr': divide(upper if side == 1 else lower, a),
            'adverse_wick_atr': divide(lower if side == 1 else upper, a),
            'pre_efficiency20': divide((c-c.shift(20)).abs(), move.abs().rolling(20).sum()).shift(1),
            'pre_tr_ratio5_20': divide(tr.rolling(5).mean(), tr.rolling(20).mean()).shift(1),
            'pre_cross_count20': d.cross.ne(0).rolling(20).sum().shift(1),
            'signal_stop_distance_pct': divide(side*(c-d.ma)+1.5*a, c),
            'btc_return20': side*market.btc_return20.to_numpy(),
            'btc_return60': side*market.btc_return60.to_numpy(),
            'btc_ma30_distance': side*market.btc_ma30_distance.to_numpy(),
        }
        for n in [5, 10, 20]:
            vals[f'pre_displacement{n}_atr'] = side*divide(c-c.shift(n), a).shift(1)
        for suffix in ENTRY_SUFFIXES:
            out[prefix+suffix] = vals[suffix]
    feature_columns = ASSET_COLUMNS + [p+s for p in ['long_', 'short_'] for s in ENTRY_SUFFIXES]
    out[feature_columns] = out[feature_columns].replace([np.inf, -np.inf], np.nan)
    return out


def entry_match(base, candidate):
    if pd.Timestamp(base['entry_time']) != pd.Timestamp(candidate['entry_time']) or int(base['side']) != int(candidate['side']):
        return False
    for key in ['entry_reference', 'entry_price', 'initial_stop', 'initial_stop_fill', 'initial_stop_unit_risk', 'entry_atr']:
        if not np.isclose(float(base[key]), float(candidate[key]), rtol=2e-12, atol=1e-14):
            return False
    eb = float(base['entry_equity']); ec = float(candidate['entry_equity'])
    if eb <= 0 or ec <= 0:
        return False
    for key in ['qty', 'entry_fee', 'initial_planned_risk']:
        if not np.isclose(float(base[key])/eb, float(candidate[key])/ec, rtol=2e-12, atol=1e-14):
            return False
    return True


def verify_fixed(base, actual):
    assert entry_match(base, actual), 'Fixed episode entry fields changed'
    for key in ['entry_equity', 'qty', 'entry_fee']:
        assert np.isclose(float(base[key]), float(actual[key]), rtol=2e-12, atol=1e-12), key


def outcome_record(t):
    e = float(t['entry_equity']); q = float(t['qty']); side = int(t['side'])
    expected = (side*q*(float(t['exit_price'])-float(t['entry_price']))-float(t['entry_fee'])-float(t['exit_fee']))/e
    assert np.isclose(expected, float(t['return_on_entry_equity']), rtol=2e-12, atol=1e-12)
    assert float(t.get('funding_paid', 0)) == 0 and float(t.get('carry_paid', 0)) == 0
    return {'u': float(t['return_on_entry_equity']), 'exit': pd.Timestamp(t['exit_time']),
            'exit_interval_end': pd.Timestamp(t['exit_interval_end']),
            'reason': t['exit_reason'], 'terminal': t['exit_reason'] == 'sample_end'}


def one_coin(jobs, output, btc_path):
    out = Path(output); engine = load_engine(); cfgs = {k: c for k, _, c in cases() if k in ACTIONS}
    btc = pd.read_parquet(btc_path).set_index('timestamp')
    first = jobs[0]; info = first['input_meta']; src = ROOT/info['source_input_directory']
    rawd = pd.read_parquet(src/info['source_frames']['joint_daily']['path'])
    rawh = pd.read_parquet(src/info['source_frames']['1h']['path'])
    reports = []
    for job in jobs:
        key = job['run_key']; meta = job['input_meta']; result = ROOT/job['source_result']
        lo = pd.Timestamp(meta['input_start']); hi = pd.Timestamp(meta['end'])
        d = rawd[rawd.joint_segment_id.eq(meta['segment_id'])].copy().sort_values('ts').reset_index(drop=True).rename(columns={'ts':'timestamp'})
        h = rawh[(rawh.ts >= lo) & (rawh.ts < hi)].copy().sort_values('ts').reset_index(drop=True).rename(columns={'ts':'timestamp'})
        assert len(d) == meta['input_days'] and len(h) == len(d)*24
        assert d.eligible.all() and d.joint_eligible.all() and h.eligible.all() and d.is_closed.all() and h.is_closed.all()
        assert pd.DatetimeIndex(d.timestamp).as_unit('ns').equals(pd.date_range(lo, hi, freq='D', inclusive='left').as_unit('ns'))
        assert pd.DatetimeIndex(h.timestamp).as_unit('ns').equals(pd.date_range(lo, hi, freq='h', inclusive='left').as_unit('ns'))
        d = engine.enrich_features(engine.features(d))
        assert d.ready.equals(d.research_window_valid)
        baseline = read_trades(result/'runs'/key/'V3/full/trades.csv')
        full = causal_features(d, baseline, btc)
        destination = out/'daily_features'/(key+'.parquet')
        assert not destination.exists()
        full.to_parquet(destination, index=False, compression='zstd')
        index = {stamp: i for i, stamp in enumerate(d.timestamp)}
        candidate_maps = {}
        for cid in ['S1_DEFENSE', 'S3_EXTENSION']:
            t = read_trades(result/'runs'/key/cid/'full/trades.csv')
            candidate_maps[cid] = {(r['entry_time'], int(r['side'])): r for r in t.to_dict('records')}
            assert len(candidate_maps[cid]) == len(t)
        rows = []; audit = []; reused = 0; calculated = 0; sample_replays = 0
        for base in baseline.to_dict('records'):
            signal = pd.Timestamp(base['signal_day']); entry = pd.Timestamp(base['entry_time'])
            assert entry == signal+pd.Timedelta(days=1)
            f = full.iloc[index[signal]]; side = int(base['side']); prefix = 'long_' if side == 1 else 'short_'
            row = {'source_result': job['source_result'], 'run_key': key, 'slug': meta['slug'],
                   'symbol': meta['symbol'], 'source_trade_id': int(base['trade_id']), 'signal_day': signal,
                   'entry_time': entry, 'side': side, 'ready90': bool(f.ready90)}
            row.update({k: f[k] for k in ASSET_COLUMNS})
            row.update({'entry_'+s: f[prefix+s] for s in ENTRY_SUFFIXES})
            baseline_outcome = outcome_record(base)
            for field, val in baseline_outcome.items(): row[field+'_v3'] = val
            row['label_source_v3'] = 'original_baseline'
            for cid, action in [('S1_DEFENSE', 'defense'), ('S3_EXTENSION', 'extension')]:
                candidate = candidate_maps[cid].get((entry, side))
                can_reuse = candidate is not None and entry_match(base, candidate)
                # Independently rerun the first reusable trade of each action in each segment.
                sample = can_reuse and not any(z['action'] == action and z['sample_replay'] for z in audit)
                if not can_reuse or sample:
                    r = engine.simulate(h, d, cfgs[cid], start=entry, end=hi, fixed_episode=base)
                    assert len(r[1]) == 1
                    actual = r[1].iloc[0].to_dict(); verify_fixed(base, actual)
                    if sample:
                        co = outcome_record(candidate); ao = outcome_record(actual)
                        assert co['exit'] == ao['exit'] and co['reason'] == ao['reason'] and co['exit_interval_end'] == ao['exit_interval_end']
                        assert np.isclose(co['u'], ao['u'], rtol=2e-12, atol=1e-12)
                        sample_replays += 1
                    else: candidate = actual
                if can_reuse: reused += 1
                else: calculated += 1
                outcome = outcome_record(candidate)
                for field, val in outcome.items(): row[field+'_'+action] = val
                row['label_source_'+action] = 'matching_natural_account' if can_reuse else 'fixed_episode_replay'
                audit.append({'run_key': key, 'source_trade_id': int(base['trade_id']), 'action': action,
                              'reused': can_reuse, 'sample_replay': sample,
                              'candidate_source_trade_id': int(candidate['trade_id']),
                              'entry_fields_verified': True, 'normalized_cash_verified': True})
            row['terminal_any'] = any(row['terminal_'+a] for a in ACTIONS.values())
            row['label_known_at'] = max(row['exit_'+a] for a in ACTIONS.values())
            rows.append(row)
        case = pd.DataFrame(rows)
        if len(case): assert not case.duplicated(['run_key', 'source_trade_id']).any()
        case.to_parquet(out/'case_parts'/(key+'.parquet'), index=False, compression='zstd')
        pd.DataFrame(audit).to_parquet(out/'label_audits'/(key+'.parquet'), index=False, compression='zstd')
        # Prefix recomputation tests signal-time causality, including completed-trade history.
        prefix_checks = 0
        for count in sorted(set([min(len(d), 90), min(len(d), 150)])):
            before = causal_features(d.iloc[:count].copy(), baseline, btc)
            pd.testing.assert_frame_equal(before, full.iloc[:count].reset_index(drop=True), check_exact=True)
            prefix_checks += 1
        report = {'run_key': key, 'symbol': meta['symbol'], 'daily_rows': len(d), 'cases': len(rows),
                  'reused_labels': reused, 'calculated_labels': calculated, 'reuse_sample_replays': sample_replays,
                  'prefix_checks': prefix_checks, 'ready90_cases': int(case.ready90.sum()) if len(case) else 0,
                  'terminal_cases': int(case.terminal_any.sum()) if len(case) else 0}
        write_json(out/'checkpoints'/(key+'.json'), report); reports.append(report)
    return reports


def collect_jobs():
    jobs = []; consumed = {}; source_manifests = {}
    for name in HISTORY:
        result = OLD/name; manifest = json.loads((result/'artifact_checksums.json').read_text())
        source_manifests[str((result/'artifact_checksums.json').relative_to(ROOT))] = sha(result/'artifact_checksums.json')
        summary = pd.read_csv(result/'summary.csv').query("case_id == 'V3'")
        for row in summary.itertuples():
            p = result/'inputs_used'/(row.run_key+'.json'); meta = json.loads(p.read_text())
            files = [p, result/'market'/row.run_key/'daily_features.csv']
            files += [result/'runs'/row.run_key/cid/'full/trades.csv' for cid in ACTIONS]
            for file in files:
                rel = str(file.relative_to(result)); assert sha(file) == manifest[rel], file
                consumed[str(file.relative_to(ROOT))] = manifest[rel]
            src = ROOT/meta['source_input_directory']
            for field in ['joint_daily', '1h']:
                info = meta['source_frames'][field]; file = src/info['path']; rel = str(file.relative_to(ROOT))
                if rel not in consumed:
                    assert sha(file) == info['sha256'], file
                    consumed[rel] = info['sha256']
            jobs.append({'run_key': row.run_key, 'symbol': row.symbol, 'source_result': str(result.relative_to(ROOT)), 'input_meta': meta})
    assert len(jobs) == 975 and len({j['run_key'] for j in jobs}) == 975
    return jobs, consumed, source_manifests


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--output', type=Path, default=OUT)
    ap.add_argument('--workers', type=int, default=2); args = ap.parse_args()
    out = args.output.resolve(); assert not out.exists(), 'Fresh output required'
    started = time.monotonic(); jobs, consumed, manifests = collect_jobs(); engine = load_engine()
    imports = [Path(__file__), Path(__file__).with_name('common.py'), Path(__file__).with_name('run_exit_state_machine_20260910.py'), PIN, CONTRACT]
    pin = json.loads(PIN.read_text()); imports.append(ROOT/pin['engine_path'])
    source_pins = {str(p.relative_to(ROOT)): sha(p) for p in imports}
    out.mkdir(parents=True)
    for directory in ['daily_features', 'case_parts', 'label_audits', 'checkpoints']:
        (out/directory).mkdir()
    (out/'source_script.py.txt').write_text(Path(__file__).read_text())
    write_json(out/'input_pins.json', consumed)
    write_json(out/'feature_manifest.json', {
        'asset_columns': ASSET_COLUMNS, 'entry_columns': ['entry_'+s for s in ENTRY_SUFFIXES],
        'all_feature_columns': ASSET_COLUMNS+['entry_'+s for s in ENTRY_SUFFIXES],
        'definitions': {**{k: FEATURE_DESCRIPTIONS[k] for k in ASSET_COLUMNS},
                        **{'entry_'+s: FEATURE_DESCRIPTIONS[s] for s in ENTRY_SUFFIXES}},
        'daily_mapping': {**{k: {'long': k, 'short': k} for k in ASSET_COLUMNS},
                          **{'entry_'+s: {'long': 'long_'+s, 'short': 'short_'+s} for s in ENTRY_SUFFIXES}},
        'excluded_identity_fields': ['symbol', 'slug', 'run_key', 'source_trade_id', 'signal_day', 'entry_time', 'side'],
        'completed_trade_rule': 'same-segment frozen shadow V3; exit_time < signal_day + 1 day; exit_reason != sample_end',
        'ready90': 'At least90 complete days in the same retained continuous segment',
    })
    write_json(out/'started.json', {'created_before_results_utc': str(pd.Timestamp.now(tz='UTC')),
        'source_pins': source_pins, 'consumed_manifests': manifests, 'expected_segments': 975,
        'expected_cases': 22028, 'fee_per_side': .001, 'slippage_per_side': .0004,
        'asset_columns': ASSET_COLUMNS, 'entry_suffixes': ENTRY_SUFFIXES,
        'reuse_absolute_tolerance': 1e-14, 'reuse_relative_tolerance': 2e-12,
        'missing_history_performance_is_nan': True, 'history_count_missing_is_zero': True,
        'completed_trade_condition': 'exit_time strictly before signal_day plus one day; sample_end excluded',
        'ready90_definition': 'signal row index >=89 within its own continuous segment',
        'rsi_normalization': 'side*(RSI6-50)/50',
        'cost_to_tr': '0.0028 divided by trailing60 median of true_range/close',
        'pf_bounded': 'positive sum divided by positive sum plus absolute negative sum; empty or all flat is missing',
        'lookbacks': 'asset ending signal day; entry pre_* ending signal day minus one day',
        'classification': 'REVEALED_HISTORICAL_PRICE_DIAGNOSTIC_SOURCE_CONFLICT_UNRESOLVED'})
    source_map = {}
    for job in jobs:
        m = job['input_meta']; src = ROOT/m['source_input_directory']; hf = m['source_frames']['1h']
        source_map[job['run_key']] = {'source_result': job['source_result'], 'symbol': m['symbol'], 'slug': m['slug'],
            'daily_source': str((out/'daily_features'/(job['run_key']+'.parquet')).relative_to(ROOT)),
            'input_meta_path': job['source_result']+'/inputs_used/'+job['run_key']+'.json',
            'hourly_path': str((src/hf['path']).relative_to(ROOT)), 'hourly_sha256': hf['sha256'],
            **{k: m[k] for k in ['input_start', 'end', 'trade_start', 'segment_id', 'boundary_end_due_to_data']}}
    write_json(out/'sources.json', source_map)
    btc_job = next(j for j in jobs if j['run_key'] == 'BTC__seg001')
    m = btc_job['input_meta']; raw = pd.read_parquet(ROOT/m['source_input_directory']/m['source_frames']['joint_daily']['path'])
    raw = raw[raw.joint_segment_id.eq(m['segment_id'])].sort_values('ts').reset_index(drop=True).rename(columns={'ts':'timestamp'})
    bd = engine.enrich_features(engine.features(raw))
    btc = pd.DataFrame({'timestamp': bd.timestamp, 'btc_return20': bd.close.pct_change(20, fill_method=None),
                        'btc_return60': bd.close.pct_change(60, fill_method=None), 'btc_ma30_distance': bd.close/bd.ma30-1})
    btc.to_parquet(out/'btc_closed_features.parquet', index=False)
    grouped = {}
    for job in jobs: grouped.setdefault(job['symbol'], []).append(job)
    results = []; failures = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(one_coin, items, str(out), str(out/'btc_closed_features.parquet')): symbol for symbol, items in grouped.items()}
        for n, future in enumerate(as_completed(pending), 1):
            symbol = pending[future]
            try: results.extend(future.result())
            except Exception as exc:
                failures.append({'symbol': symbol, 'error': repr(exc)}); print('FAILED', symbol, repr(exc), flush=True)
            if n % 10 == 0 or n == len(pending):
                print(f'Coins {n}/{len(pending)} segments {len(results)} cases {sum(r["cases"] for r in results)} reused {sum(r["reused_labels"] for r in results)} calculated {sum(r["calculated_labels"] for r in results)} errors {len(failures)} elapsed {time.monotonic()-started:.1f}s', flush=True)
    write_json(out/'execution_failures.json', failures)
    if failures:
        write_json(out/'completion.json', {'complete': False, 'failures': len(failures), 'completed_segments': len(results)})
        raise RuntimeError('Preserved failed attempt; do not overwrite')
    combined = pd.concat([pd.read_parquet(out/'case_parts'/(r['run_key']+'.parquet')) for r in results if r['cases']], ignore_index=True)
    combined = combined.sort_values(['signal_day', 'symbol', 'source_trade_id']).reset_index(drop=True)
    assert len(combined) == 22028 and len(results) == 975
    assert not combined.duplicated(['run_key', 'source_trade_id']).any()
    combined.to_parquet(out/'cases.parquet', index=False, compression='zstd')
    pd.DataFrame(results).sort_values('run_key').to_csv(out/'segment_summary.csv', index=False)
    checksums = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ['artifact_checksums.json', 'completion.json']}
    write_json(out/'artifact_checksums.json', checksums)
    write_json(out/'completion.json', {'complete': True, 'segments': len(results), 'coins': len(grouped),
        'cases': len(combined), 'ready90_cases': int(combined.ready90.sum()), 'terminal_any_cases': int(combined.terminal_any.sum()),
        'reused_labels': sum(r['reused_labels'] for r in results), 'calculated_labels': sum(r['calculated_labels'] for r in results),
        'reuse_sample_replays': sum(r['reuse_sample_replays'] for r in results), 'prefix_checks': sum(r['prefix_checks'] for r in results),
        'elapsed_seconds': time.monotonic()-started, 'manifest_sha256': sha(out/'artifact_checksums.json')})
    print(json.dumps(json.loads((out/'completion.json').read_text())), flush=True)


if __name__ == '__main__':
    main()
