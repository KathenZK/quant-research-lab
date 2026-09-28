"""Fixed original V3 entries: replay only the reachable short-TP intervention.

This ledger includes every original trade. Other exits are reused only after
checking the original closed-bar stop path for an earlier reachable TP. Their
entry size/equity and exact original PnL are never recalculated or improved.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from v3_opportunity_study_20260913 import R, ROOT, PIN, engine, config, verify_preconditions
from v3_opportunity_inputs_20260913 import load_sources, load_segment, sha, write_json

OUT = R / 'pairs'
BASE_TP = 'accel1_rsi30'
EXACT_ENTRY = [
    'side', 'entry_time', 'entry_reference', 'entry_price', 'entry_equity', 'qty',
    'entry_fee', 'signal_day', 'cross_day', 'initial_stop', 'entry_atr',
]


def legacy_tp_observations(trade, stop_rows, daily_by_day):
    """Independent legacy condition; each old stop row is a processed boundary."""
    result = []
    if int(trade['side']) != -1:
        return result
    for stop in stop_rows.itertuples(index=False):
        if not bool(stop.full_holding_day):
            continue
        row = daily_by_day.loc[pd.Timestamp(stop.signal_day)]
        fill = float(row.close) * 1.0004
        profit = (float(trade['qty']) * (float(trade['entry_price']) - fill)
                  - float(trade['entry_fee']) - float(trade['qty']) * fill * .001)
        # This round is explicitly funding=None/carry=0. Missing funding is
        # not being assumed verified zero; these are the original price runs.
        if bool(row.accel1) and float(row.rsi) <= 30 and profit > 0:
            result.append({'signal_day': pd.Timestamp(stop.signal_day),
                           'effective_at': pd.Timestamp(stop.timestamp),
                           'expected_profit_at_close': profit})
    return result


def prove_reuse(trade, observations):
    """Any eligible TP before an original non-TP exit makes reuse invalid."""
    if int(trade['side']) == 1:
        assert not observations
        return 'long_branch_unreachable'
    assert trade['exit_reason'] != BASE_TP
    for obs in observations:
        assert obs['effective_at'] == pd.Timestamp(trade['exit_time'])
        assert trade['exit_reason'] == 'stop_gap'
    return ('terminal_gap_precedes_eligible_tp' if observations
            else 'no_eligible_tp_before_original_exit')


def compare_entry(original, replay):
    for name in EXACT_ENTRY:
        a, b = original[name], replay[name]
        if name.endswith('_time') or name.endswith('_day'):
            assert pd.Timestamp(a) == pd.Timestamp(b), (name, a, b)
        else:
            assert a == b, (name, a, b)


def common_record(info, original, changed, method, proof, observations, trade_path, stop_path):
    old_pnl, new_pnl = float(original['net_pnl']), float(changed['net_pnl'])
    eq = float(original['entry_equity'])
    old_end, new_end = pd.Timestamp(original['exit_interval_end']), pd.Timestamp(changed['exit_interval_end'])
    entry = pd.Timestamp(original['entry_time'])
    return {
        'run_key': info['run_key'], 'slug': info['slug'], 'symbol': info['symbol'],
        'baseline_trade_id': int(original['trade_id']), 'side': int(original['side']),
        'entry_time': entry, 'cross_day': original['cross_day'], 'signal_day': original['signal_day'],
        'entry_equity': eq, 'qty': float(original['qty']), 'entry_reference': float(original['entry_reference']),
        'entry_price': float(original['entry_price']), 'entry_fee': float(original['entry_fee']),
        'baseline_exit_time': original['exit_time'], 'new_exit_time': changed['exit_time'],
        'baseline_exit_interval_end': old_end, 'new_exit_interval_end': new_end,
        'baseline_exit_reason': original['exit_reason'], 'new_exit_reason': changed['exit_reason'],
        'baseline_net_pnl': old_pnl, 'new_net_pnl': new_pnl,
        'baseline_return_on_entry_equity': old_pnl / eq,
        'new_return_on_entry_equity': new_pnl / eq,
        'delta_net_pnl': new_pnl - old_pnl,
        'delta_return_on_entry_equity': (new_pnl - old_pnl) / eq,
        'baseline_holding_days': (old_end-entry).total_seconds()/86400,
        'new_holding_days': (new_end-entry).total_seconds()/86400,
        'additional_holding_days': (new_end-old_end).total_seconds()/86400,
        'baseline_is_sample_end': original['exit_reason'] == 'sample_end',
        'new_is_sample_end': changed['exit_reason'] == 'sample_end',
        'common_natural': original['exit_reason'] != 'sample_end' and changed['exit_reason'] != 'sample_end',
        'method': method, 'reuse_proof': proof,
        'baseline_eligible_tp_boundary_count': len(observations),
        'baseline_first_eligible_signal_day': observations[0]['signal_day'] if observations else None,
        'baseline_first_eligible_at': observations[0]['effective_at'] if observations else None,
        'new_tp_signal_day': changed.get('tp_protect_signal_day'),
        'new_tp_event_atr': changed.get('tp_protect_event_atr'),
        'new_tp_eligible_signal_count': changed.get('tp_protect_eligible_signal_count'),
        'new_tp_suppressed_count': changed.get('tp_protect_suppressed_count'),
        'new_trade_path': trade_path, 'new_stop_path': stop_path,
        'baseline_dir': info['baseline_dir'],
    }


def one_coin(slug, keys, output):
    output = Path(output); e = engine(); rows, proofs = [], []
    for key in sorted(keys):
        d, h, info, baseline, stops = load_segment(key)
        daily_by_day = d.set_index('timestamp')
        stop_groups = dict(tuple(stops.groupby('trade_id'))) if len(stops) else {}
        segment_rows = []
        for original in baseline.to_dict('records'):
            tid = int(original['trade_id'])
            assert original['funding_paid'] == 0 and original['carry_paid'] == 0
            observations = legacy_tp_observations(original, stop_groups[tid], daily_by_day)
            if original['exit_reason'] != BASE_TP:
                proof = prove_reuse(original, observations)
                changed = original
                method = 'exact_original_reused'
                trade_path = info['baseline_dir'] + '/trades.csv'
                stop_path = info['baseline_dir'] + '/stops.csv'
            else:
                assert int(original['side']) == -1 and len(observations) == 1
                assert observations[0]['effective_at'] == pd.Timestamp(original['exit_time'])
                assert observations[0]['signal_day'] == pd.Timestamp(original['tp_signal_day'])
                fixed = {name: original[name] for name in ['entry_time', 'entry_equity', 'qty', 'side']}
                out = e.simulate(h, d, config('TP_PROTECT'), start=pd.Timestamp(original['entry_time']),
                                 end=pd.Timestamp(info['end']), funding=None, carry_daily=0.,
                                 fixed_episode=fixed)
                assert len(out[1]) == 1
                changed = out[1].iloc[0].to_dict()
                compare_entry(original, changed)
                assert changed['tp_protect_active']
                assert pd.Timestamp(changed['tp_protect_signal_day']) == pd.Timestamp(original['tp_signal_day'])
                assert pd.Timestamp(changed['exit_time']) >= pd.Timestamp(original['exit_time'])
                dest = output / 'fixed' / key / f'trade_{tid:05d}'
                dest.mkdir(parents=True, exist_ok=False)
                t = out[1].copy(); s = out[3].copy()
                t.insert(0, 'baseline_trade_id', tid); s.insert(0, 'baseline_trade_id', tid)
                t.to_csv(dest/'trade.csv', index=False); s.to_csv(dest/'stops.csv', index=False)
                write_json(dest/'entry_comparison.json', {
                    'run_key': key, 'baseline_trade_id': tid, 'checked_fields': EXACT_ENTRY,
                    'all_exact': True, 'baseline_entry_equity': original['entry_equity'],
                    'baseline_qty': original['qty'], 'baseline_trade_path': info['baseline_dir']+'/trades.csv',
                    'baseline_trade_sha256': info['baseline_sha256']['trades.csv'],
                    'baseline_tp_observations': observations,
                })
                method, proof = 'fixed_original_entry_replay', 'original_short_tp_is_first_reachable_intervention'
                trade_path, stop_path = str((dest/'trade.csv').relative_to(ROOT)), str((dest/'stops.csv').relative_to(ROOT))
            segment_rows.append(common_record(info, original, changed, method, proof,
                                              observations, trade_path, stop_path))
            proofs.append({'run_key': key, 'baseline_trade_id': tid, 'method': method,
                           'proof': proof, 'eligible_boundaries': observations})
        rows.extend(segment_rows)
    part = output/'parts'/f'{slug}.parquet'; part.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(part, index=False)
    proof_path = output/'proofs'/f'{slug}.json'
    write_json(proof_path, proofs)
    result = {'slug': slug, 'trades': len(rows),
              'replayed': sum(x['method'] == 'fixed_original_entry_replay' for x in rows),
              'reused': sum(x['method'] == 'exact_original_reused' for x in rows),
              'part_sha256': sha(part), 'proof_sha256': sha(proof_path)}
    write_json(output/'checkpoints'/f'{slug}.json', result)
    return result


def summary(frame, label, cohort):
    old, new = frame.baseline_return_on_entry_equity, frame.new_return_on_entry_equity
    wins, losses = old > 0, old < 0
    top = old >= old[old > 0].quantile(.95) if wins.any() else wins
    def retention(mask):
        return float(new[mask].sum()/old[mask].sum()*100) if old[mask].sum() != 0 else None
    coin_delta = frame.assign(delta=new-old).groupby('slug').delta.mean()
    return {'period': label, 'cohort': cohort, 'trades': len(frame), 'coins': frame.slug.nunique(),
            'replayed': int(frame.method.eq('fixed_original_entry_replay').sum()),
            'baseline_mean_return_pct': float(old.mean()*100), 'new_mean_return_pct': float(new.mean()*100),
            'equal_coin_mean_improvement_pp': float(coin_delta.mean()*100),
            'improved_trades': int((new>old).sum()), 'worsened_trades': int((new<old).sum()),
            'unchanged_trades': int((new==old).sum()),
            'losers_improved': int((losses & (new>old)).sum()),
            'winners_turned_loss': int((wins & (new<0)).sum()),
            'winners_turned_zero': int((wins & (new==0)).sum()),
            'original_winner_signed_net_retention_pct': retention(wins),
            'original_top5pct_signed_net_retention_pct': retention(top),
            'new_sample_end_count': int(frame.new_is_sample_end.sum()),
            'median_added_holding_days_replayed': float(frame.loc[frame.method.eq('fixed_original_entry_replay'), 'additional_holding_days'].median()),
            'not_an_aggregate_account_return': True}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--resume', action='store_true'); args = ap.parse_args()
    verify_preconditions()
    completion_path = R/'accounts/TP_PROTECT/completion.json'
    assert json.loads(completion_path.read_text())['complete']
    sources = load_sources()
    files = [Path(__file__), Path(__file__).with_name('v3_opportunity_study_20260913.py'),
             Path(__file__).with_name('v3_opportunity_inputs_20260913.py'), PIN,
             ROOT/'tests/test_ma7_car_opportunity_pairs.py',
             R/'before_results.json', R/'inputs/artifact_checksums.json',
             R/'diagnostics/artifact_checksums.json', R/'accounts/TP_PROTECT/artifact_checksums.json',
             completion_path]
    pins = {str(p.relative_to(ROOT)): sha(p) for p in files}
    if OUT.exists():
        assert args.resume and json.loads((OUT/'started.json').read_text())['pins'] == pins
    else:
        OUT.mkdir(parents=True)
        write_json(OUT/'started.json', {'utc': str(pd.Timestamp.now(tz='UTC')), 'pins': pins,
                   'baseline_trade_count': 22028, 'cost_fee_per_side': .001, 'slippage_per_side': .0004,
                   'same_entry_quantity_and_equity': True, 'no_combined_account_claim': True})
        (OUT/'source_script.py.txt').write_text(Path(__file__).read_text())
    by_coin = {}
    for key, source in sources.items():
        by_coin.setdefault(source['slug'], []).append(key)
    receipts, failures = [], []
    start = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = {}
        for slug, keys in sorted(by_coin.items()):
            check = OUT/'checkpoints'/f'{slug}.json'
            if check.exists():
                r = json.loads(check.read_text())
                assert sha(OUT/'parts'/f'{slug}.parquet') == r['part_sha256']
                assert sha(OUT/'proofs'/f'{slug}.json') == r['proof_sha256']
                receipts.append(r)
            else:
                # An incomplete coin has no trusted checkpoint and must not
                # silently overwrite any prior fixed-episode evidence.
                jobs[pool.submit(one_coin, slug, keys, OUT)] = slug
        for n, job in enumerate(as_completed(jobs), 1):
            try:
                receipts.append(job.result())
            except Exception as exc:
                failures.append({'slug': jobs[job], 'error': repr(exc)})
                write_json(OUT/'failures.json', failures)
                print('FAILED', jobs[job], repr(exc), flush=True)
            if n % 25 == 0 or n == len(jobs):
                print(f'Pairs {n}/{len(jobs)} coins, failures {len(failures)}, {time.monotonic()-start:.1f}s', flush=True)
    if failures:
        write_json(OUT/'completion.json', {'complete': False, 'failures': failures})
        raise RuntimeError('Fixed-entry proof or replay failed')
    cases = pd.concat([pd.read_parquet(OUT/'parts'/f'{r["slug"]}.parquet')
                       for r in sorted(receipts, key=lambda r: r['slug'])], ignore_index=True)
    assert len(cases) == 22028
    assert not cases.duplicated(['run_key', 'baseline_trade_id']).any()
    cases.to_parquet(OUT/'cases.parquet', index=False)
    cases.to_csv(OUT/'cases.csv', index=False)
    years = pd.to_datetime(cases.entry_time, utc=True).dt.year
    groups = {'ALL': np.ones(len(cases), dtype=bool),
              '2023_2024': years.between(2023, 2024), '2025_PLUS': years >= 2025}
    groups.update({str(year): years == year for year in sorted(years.unique())})
    rows = []
    for label, mask in groups.items():
        for cohort, selected in [('all_retained', mask),
                                 ('common_natural', mask & cases.common_natural),
                                 ('original_short_tp', mask & cases.method.eq('fixed_original_entry_replay'))]:
            if selected.any():
                rows.append(summary(cases.loc[selected], label, cohort))
    pd.DataFrame(rows).to_csv(OUT/'summary.csv', index=False)
    write_json(OUT/'completion.json', {
        'complete': True, 'trades': len(cases), 'coins': len(receipts), 'segments': len(sources),
        'replayed': int(cases.method.eq('fixed_original_entry_replay').sum()),
        'reused': int(cases.method.eq('exact_original_reused').sum()),
        'entry_exact_failures': 0, 'branch_proof_failures': 0,
        'failures': [], 'elapsed_seconds': time.monotonic()-start,
        'funding_window_verified': False, 'not_an_aggregate_account': True})
    write_json(OUT/'artifact_checksums.json', {str(p.relative_to(OUT)): sha(p)
               for p in OUT.rglob('*') if p.is_file() and p.name != 'artifact_checksums.json'})
    print((OUT/'completion.json').read_text(), flush=True)


if __name__ == '__main__':
    main()
