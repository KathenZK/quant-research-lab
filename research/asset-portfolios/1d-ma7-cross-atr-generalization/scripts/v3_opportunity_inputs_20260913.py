"""Read only the retained V3 history inputs; prepare a hash-bound source audit.

No lake defaults, no fresh price pulls, no strategy execution and no return
recalculation. Each call preserves one original continuous segment and its
original trade_start/end. CLI copies existing V3 summaries/blocks for reuse.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parents[1]
R = BASE / 'artifacts/v3_opportunity_20260913'
OUT = R / 'inputs'
OLD = BASE / 'artifacts/state_machine_20260910'
CASES = BASE / 'artifacts/adaptation_20260911/cases'
CASES_MANIFEST_SHA = '6841835f8c915cad6070235197fce32fa8d74de311fc3c115b7d9dd1c283f712'
RESULT_MANIFEST_SHA = {
    'history_results': '7be6f60634dc54888ed19023ff07aa5e272fd89359df90e46f80dd41e82914a8',
    'history_verified_results': 'b6b3a98c5e4171b6808b57ff10a54d0efcea7385ef73eb44a5739ac57adfb7d4',
}
DAILY_COLUMNS = [
    'timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'quote_volume',
    'trade_count', 'is_closed', 'observed_valid', 'identity_verified', 'eligible',
    'research_segment_id', 'research_window_valid', 'joint_eligible', 'hour_rows',
    'eligible_hours', 'joint_segment_id', 'ma', 'ma30', 'prev_ma30', 'ma30_ready',
    'atr', 'rsi', 'slope', 'cross', 'accel1', 'accel2', 'ready', 'ma_step',
    'prev_ma_step', 'ma_step_change', 'sm_delta', 'sm_previous_delta',
    'sm_previous_atr', 'sm_previous_atr2',
]
DATETIME_COLUMNS = ['timestamp', 'entry_time', 'exit_time', 'exit_interval_end',
                    'signal_day', 'cross_day', 'tp_signal_day', 'signal_time',
                    'effective_from', 'effective_until', 'signal_day_next']


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str,
                               allow_nan=False) + '\n')


def relative(path):
    return str(Path(path).relative_to(ROOT))


def checked(path, digest):
    path = Path(path)
    assert sha(path) == digest, f'Frozen file content changed: {path}'
    return path


def table(path):
    try:
        frame = pd.read_csv(path, float_precision='round_trip')
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    for c in DATETIME_COLUMNS:
        if c in frame:
            frame[c] = pd.to_datetime(frame[c], utc=True, format='mixed').dt.as_unit('ns')
    return frame


@lru_cache(maxsize=1)
def _source_context():
    cm = read_json(checked(CASES/'artifact_checksums.json', CASES_MANIFEST_SHA))
    assert read_json(CASES/'completion.json')['manifest_sha256'] == CASES_MANIFEST_SHA
    for name in ['sources.json', 'started.json']:
        checked(CASES/name, cm[name])
    original = read_json(CASES/'sources.json')
    assert len(original) == 975 and len({v['symbol'] for v in original.values()}) == 676
    rms = {}
    for name, digest in RESULT_MANIFEST_SHA.items():
        result = OLD/name
        rms[relative(result)] = read_json(checked(result/'artifact_checksums.json', digest))
        assert read_json(result/'completion.json')['manifest_sha256'] == digest
    return original, cm, rms


def load_sources() -> dict:
    """975 run_key records; copies preserve every original source field.

    The added baseline_dir contains original V3 full/summary.json, trades.csv,
    stops.csv, entry_events.csv and equity.parquet. Paths are repo-relative.
    No 90-day readiness filter is introduced.
    """
    original, cm, rms = _source_context()
    result = {}
    for key, source in original.items():
        baseline = source['source_result'] + '/runs/' + key + '/V3/full'
        result[key] = {**source, 'run_key': key, 'baseline_dir': baseline,
                       'daily_sha256': cm[str((ROOT/source['daily_source']).relative_to(CASES))],
                       'baseline_sha256': {name: rms[source['source_result']][
                           'runs/' + key + '/V3/full/' + name]
                           for name in ['summary.json', 'trades.csv', 'stops.csv',
                                        'entry_events.csv', 'equity.parquet']}}
    return result


@lru_cache(maxsize=4)
def _read_frame(path_string, digest):
    # A small per-process cache reduces repeated loads for adjacent segments.
    # Cached frames are never returned directly or mutated.
    return pd.read_parquet(checked(ROOT/path_string, digest))


def load_segment(run_key) -> tuple:
    """Return (daily, hourly, meta, baseline_trades, baseline_stops).

    daily/hourly include the segment's original warmup and are independent
    copies. UTC ns `timestamp` denotes candle OPEN. `meta['trade_start']` is
    the account start; `meta['end']` is exclusive. Missing future windows must
    remain incomplete in downstream diagnostics.
    """
    sources = load_sources()
    if run_key not in sources:
        raise KeyError(f'No original tradable V3 segment: {run_key}')
    s = sources[run_key]; _, _, rms = _source_context()
    mr = str((ROOT/s['input_meta_path']).relative_to(ROOT/s['source_result']))
    meta = read_json(checked(ROOT/s['input_meta_path'], rms[s['source_result']][mr]))
    assert all(meta[k] == s[k] for k in ['symbol', 'slug', 'input_start', 'end',
                                        'trade_start', 'segment_id', 'boundary_end_due_to_data'])
    assert meta['run_key'] == run_key and meta['has_trading_window']
    d = pd.read_parquet(checked(ROOT/s['daily_source'], s['daily_sha256']),
                        columns=DAILY_COLUMNS).copy()
    h = _read_frame(s['hourly_path'], s['hourly_sha256'])
    ins, end = pd.Timestamp(meta['input_start']), pd.Timestamp(meta['end'])
    h = h.loc[(h.ts >= ins) & (h.ts < end)].copy().reset_index(drop=True)
    h = h.rename(columns={'ts': 'timestamp'})
    d['timestamp'] = pd.to_datetime(d.timestamp, utc=True).dt.as_unit('ns')
    h['timestamp'] = pd.to_datetime(h.timestamp, utc=True).dt.as_unit('ns')
    _check_segment_frames(d, h, meta)
    baseline = ROOT/s['baseline_dir']
    t = table(checked(baseline/'trades.csv', s['baseline_sha256']['trades.csv']))
    stops = table(checked(baseline/'stops.csv', s['baseline_sha256']['stops.csv']))
    meta.update({k: s[k] for k in ['source_result', 'baseline_dir', 'daily_source',
                                  'daily_sha256', 'baseline_sha256', 'hourly_path',
                                  'hourly_sha256']})
    return d, h, meta, t, stops


def _check_segment_frames(d, h, meta):
    ins, end, start = [pd.Timestamp(meta[k]) for k in ['input_start', 'end', 'trade_start']]
    assert start == ins + pd.Timedelta(days=29)
    assert end > start
    assert len(d) == meta['input_days'] and len(h) == len(d)*24
    assert len(d)-29 == meta['trade_days']
    for frame, freq in [(d, 'D'), (h, 'h')]:
        actual = pd.DatetimeIndex(frame.timestamp).as_unit('ns')
        expected = pd.date_range(ins, end, freq=freq, inclusive='left').as_unit('ns')
        assert actual.equals(expected), (meta['run_key'], freq, 'unsorted/duplicate/gap/out-of-range')
        assert frame.symbol.eq(meta['symbol']).all()
        assert frame.eligible.all() and frame.is_closed.all() and frame.observed_valid.all()
        assert frame.research_segment_id.nunique() == 1
    assert d.joint_segment_id.eq(meta['segment_id']).all()
    assert d.joint_eligible.all() and d.hour_rows.eq(24).all() and d.eligible_hours.eq(24).all()
    valid = np.arange(len(d)) >= 28
    assert np.array_equal(d.research_window_valid, valid)
    assert np.array_equal(d.ready, valid)
    assert h.research_window_valid.all()
    assert d.loc[d.ready, 'atr'].gt(0).all()
    assert d.loc[d.ready, ['ma', 'atr', 'rsi', 'slope']].notna().all().all()
    assert not d.ready.iloc[:28].any()


def _collect_pins(sources):
    original, cm, rms = _source_context()
    pins = {relative(CASES/'artifact_checksums.json'): CASES_MANIFEST_SHA}
    for name in ['sources.json', 'started.json']:
        pins[relative(CASES/name)] = cm[name]
    for result_rel, manifest in rms.items():
        result = ROOT/result_rel
        pins[relative(result/'artifact_checksums.json')] = RESULT_MANIFEST_SHA[result.name]
        for name in ['summary.csv', 'blocks.csv', 'scope.csv', 'segments.csv', 'run_manifest.json']:
            pins[relative(result/name)] = manifest[name]
        run = read_json(checked(result/'run_manifest.json', manifest['run_manifest.json']))
        for rel, digest in run['source_pins'].items():
            pins[rel] = digest
        ep = run['engine_pin']; pins[ep['engine_path']] = ep['engine_sha256']
        for rel, digest in ep['contracts'].items():
            pins[rel] = digest
        inp = ROOT/run['input_source']
        im = read_json(checked(inp/'checksums.json', run['source_pins'][relative(inp/'checksums.json')]))
        # All retained startup frames, requests and receipts are verified,
        # including the four candidates without an original trading window.
        for rel, digest in im.items():
            pins[relative(inp/rel)] = digest
    for key, s in sources.items():
        pins[s['daily_source']] = s['daily_sha256']
        result = ROOT/s['source_result']; manifest = rms[s['source_result']]
        for path in [ROOT/s['input_meta_path'], result/'market'/key/'daily_features.csv']:
            pins[relative(path)] = manifest[str(path.relative_to(result))]
        for name, digest in s['baseline_sha256'].items():
            pins[s['baseline_dir']+'/'+name] = digest
    return pins


def _audit_segment(key, source):
    d, h, m, t, stops = load_segment(key)
    inp = ROOT/m['source_input_directory']; frames = m['source_frames']
    for role in ['1d', '1h', 'joint_daily']:
        assert frames[role]['saved_roundtrip_exact']
    assert frames['joint_daily']['source_daily_sha256'] == frames['1d']['sha256']
    assert frames['joint_daily']['source_hourly_sha256'] == frames['1h']['sha256']
    raw = _read_frame(relative(inp/frames['joint_daily']['path']), frames['joint_daily']['sha256'])
    raw = raw.loc[raw.joint_segment_id.eq(m['segment_id'])].reset_index(drop=True)
    pd.testing.assert_frame_equal(d[[c for c in d if c in raw.columns]],
                                  raw[[c for c in d if c in raw.columns]], check_exact=True)
    assert pd.DatetimeIndex(d.timestamp).equals(pd.DatetimeIndex(raw.ts).as_unit('ns'))
    original = table(ROOT/source['source_result']/'market'/key/'daily_features.csv')
    # Compare persisted indicators with the exact old V3 CSV reader, not a
    # newly chosen indicator implementation or a different engine version.
    pd.testing.assert_frame_equal(d, original[DAILY_COLUMNS], check_exact=True,
                                  check_dtype=False)
    receipts = {}
    for role in ['1d', '1h']:
        info = frames[role]
        req = read_json(checked(inp/info['request_path'], info['request_sha256']))
        report = read_json(checked(inp/info['startup_report_path'], info['startup_report_sha256']))
        assert req == report['request']
        assert req['mode'] == 'price_diagnostic' and req['gap_policy'] == 'contiguous_segments'
        assert req['backward_bars'] == (29 if role == '1d' else 1)
        assert req['forward_bars'] == 0 and m['symbol'] in req['symbols']
        assert report['price_inputs_verified'] and not report['funding_window_verified']
        assert pd.Timestamp(req['start']) <= pd.Timestamp(m['input_start'])
        assert pd.Timestamp(req['end']) >= pd.Timestamp(m['end'])
        receipts[role] = {'request': relative(inp/info['request_path']),
                          'request_sha256': info['request_sha256'],
                          'startup_report': relative(inp/info['startup_report_path']),
                          'startup_report_sha256': info['startup_report_sha256']}
    # Hourly/daily OHLC aggregation uses the original retained-data tolerance.
    arr = h[['open', 'high', 'low', 'close']].to_numpy().reshape(len(d), 24, 4)
    agg = np.column_stack([arr[:, 0, 0], arr[:, :, 1].max(1),
                           arr[:, :, 2].min(1), arr[:, -1, 3]])
    actual = d[['open', 'high', 'low', 'close']].to_numpy()
    assert np.allclose(actual, agg, rtol=1e-12, atol=1e-9)
    summary = read_json(ROOT/source['baseline_dir']/'summary.json')
    assert summary['fee'] == .001 and summary['slip'] == .0004
    assert summary['progress_days'] == 4 and summary['reverse'] is False
    assert summary['progress_source'] == 'high_low' and summary['entry_wait_days'] == 0
    assert summary['exit_state_policy'] == 'v3'
    assert pd.Timestamp(summary['start']) == pd.Timestamp(m['trade_start'])
    assert pd.Timestamp(summary['end_exclusive']) == pd.Timestamp(m['end'])
    assert summary['trades'] == len(t)
    if len(t):
        assert t.entry_time.ge(pd.Timestamp(m['trade_start'])).all()
        assert t.entry_time.lt(pd.Timestamp(m['end'])).all()
        assert t.exit_time.le(pd.Timestamp(m['end'])).all()
    return {'run_key': key, 'symbol': m['symbol'], 'slug': m['slug'],
            'input_start': m['input_start'], 'trade_start': m['trade_start'], 'end': m['end'],
            'daily_rows': len(d), 'hourly_rows': len(h), 'trade_days': m['trade_days'],
            'valid_signal_days': int(d.ready.sum()), 'baseline_trades': len(t),
            'baseline_stop_records': len(stops),
            'hourly_daily_ohlc_max_abs_difference': float(np.max(np.abs(actual-agg))),
            'boundary_end_due_to_data': m['boundary_end_due_to_data'],
            'grid_exact': True, 'masks_exact': True, 'old_features_exact': True,
            'original_start_end_preserved': True, 'no_added_90_day_gate': True,
            'receipts': receipts}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--output', type=Path, default=OUT)
    ap.add_argument('--hash-workers', type=int, default=4); args = ap.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise FileExistsError(f'Never overwrite a retained input audit: {out}')
    sources = load_sources(); pins = _collect_pins(sources)
    out.mkdir(parents=True)
    begin = time.monotonic()
    write_json(out/'started.json', {'created_before_new_diagnostics_utc': str(pd.Timestamp.now(tz='UTC')),
               'expected_segments': 975, 'expected_coins_with_windows': 676,
               'candidate_universe': 680, 'source_script_sha256': sha(Path(__file__)),
               'mode': 'REUSE_RETAINED_PRICE_DIAGNOSTIC', 'returns_recalculated': False,
               'new_strategy_executed': False, 'fee_per_side': .001, 'slip_per_side': .0004})
    (out/'source_script.py.txt').write_text(Path(__file__).read_text())
    write_json(out/'consumed_files.json', pins)
    items = list(pins.items())
    with ThreadPoolExecutor(max_workers=args.hash_workers) as pool:
        for n, _ in enumerate(pool.map(lambda pair: checked(ROOT/pair[0], pair[1]), items), 1):
            if n % 1000 == 0:
                print(f'Frozen files {n}/{len(items)} elapsed {time.monotonic()-begin:.1f}s', flush=True)
    write_json(out/'sources.json', sources)
    summaries, blocks, scopes, segments = [], [], [], []
    for name in RESULT_MANIFEST_SHA:
        result = OLD/name
        for filename, target in [('summary.csv', summaries), ('blocks.csv', blocks),
                                  ('scope.csv', scopes), ('segments.csv', segments)]:
            frame = pd.read_csv(result/filename, float_precision='round_trip')
            if 'case_id' in frame:
                frame = frame.loc[frame.case_id.eq('V3')].copy()
            frame['source_result'] = relative(result); target.append(frame)
    summary = pd.concat(summaries, ignore_index=True).sort_values('run_key')
    block = pd.concat(blocks, ignore_index=True)
    scope = pd.concat(scopes, ignore_index=True).sort_values('symbol')
    segs = pd.concat(segments, ignore_index=True).sort_values(['symbol', 'input_start'])
    assert len(summary) == 975 and set(summary.run_key) == set(sources)
    assert len(scope) == 680 and scope.symbol.nunique() == 680
    assert scope.segments_with_trading_window.gt(0).sum() == 676
    assert summary.trades.sum() == 22028
    assert summary.loc[summary.slug.eq('HYPE'), 'trades'].tolist() == [17]
    summary.to_csv(out/'baseline_summary.csv', index=False)
    block.to_csv(out/'baseline_blocks.csv', index=False)
    scope.to_csv(out/'universe_scope.csv', index=False)
    segs.to_csv(out/'all_retained_segments.csv', index=False)
    audits = []
    for n, (key, source) in enumerate(sorted(sources.items()), 1):
        record = _audit_segment(key, source); audits.append(record)
        if n % 50 == 0 or n == len(sources):
            print(f'Segments {n}/{len(sources)} trades {sum(x["baseline_trades"] for x in audits)} elapsed {time.monotonic()-begin:.1f}s', flush=True)
    for record in audits:
        write_json(out/'segment_receipts'/(record['run_key']+'.json'), record)
    pd.DataFrame([{k: v for k, v in r.items() if k != 'receipts'} for r in audits]).to_csv(out/'range_checks.csv', index=False)
    write_json(out/'limitations.json', {
        'old_price_source_conflict_unresolved': True,
        'funding_window_verified': False, 'historical_identity_verified': False,
        'pit_universe_proven': False, 'tradability_proven': False,
        'no_new_current_market_universe': True, 'no_cross_segment_splicing': True,
        'no_additional_90_day_warmup': True,
        'price_coverage_end_exclusive': '2026-09-05T00:00:00Z',
        'not_full_cycle_for_every_coin': True,
        'baseline_amounts_reused_not_recalculated': True,
        'blank_funding_or_zero_charged_does_not_mean_verified_zero_funding': True,
        'future_labels_must_respect_segment_boundary': True,
        'masked_daily_warmup_length': 28,
        'first_possible_signal_row_index': 28,
        'first_account_open_offset_days': 29,
    })
    hashes = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()
              and p.name not in ['artifact_checksums.json', 'completion.json']}
    write_json(out/'artifact_checksums.json', hashes)
    done = {'complete': True, 'candidate_coins': len(scope),
            'coins_with_original_trading_windows': 676, 'original_v3_accounts': len(summary),
            'all_retained_segments': len(segs), 'segments_without_trading_window': int(segs.trade_days.eq(0).sum()),
            'original_v3_trades': int(summary.trades.sum()),
            'hype_original_v3_trades': 17, 'baseline_block_rows': len(block),
            'daily_rows': sum(x['daily_rows'] for x in audits),
            'hourly_rows': sum(x['hourly_rows'] for x in audits),
            'baseline_stop_records': sum(x['baseline_stop_records'] for x in audits),
            'consumed_files_verified': len(pins), 'range_checks': len(audits),
            'failed_checks': 0, 'new_strategy_executed': False, 'returns_recalculated': False,
            'funding_window_verified': False, 'elapsed_seconds': time.monotonic()-begin,
            'manifest_sha256': sha(out/'artifact_checksums.json')}
    write_json(out/'completion.json', done)
    print(json.dumps(done, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
