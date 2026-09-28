"""All raw V3 crosses and post-exit paths, with no new trading policy.

The fixed 5/10/20 day observations are overlapping descriptions, never account
profits. Every forward observation stays inside one frozen continuous segment.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import time

import numpy as np
import pandas as pd

from common import BASE, ROOT, sha, write_json

ROUND = BASE / 'artifacts/v3_opportunity_20260913'
OUT = ROUND / 'diagnostics'
HORIZONS = (5, 10, 20)
FEE = .001
SLIP = .0004
HOUR = pd.Timedelta(hours=1)
DAY = pd.Timedelta(days=1)


def read_csv(path):
    try:
        d = pd.read_csv(path, float_precision='round_trip')
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    for col in ('timestamp', 'signal_day', 'cross_day', 'entry_time', 'exit_time',
                'exit_interval_end', 'tp_signal_day', 'extreme_day', 'arm_day'):
        if col in d:
            d[col] = pd.to_datetime(d[col], utc=True, format='mixed').dt.as_unit('ns')
    return d


def category(value, cuts, labels):
    if not np.isfinite(value):
        return 'missing'
    return labels[int(np.searchsorted(cuts, value, side='right'))]


def causal_features(d):
    """All features end at the indexed daily close, including that closed day."""
    x = d.copy().reset_index(drop=True)
    c = x.close.astype(float)
    den = c.diff().abs().rolling(20, min_periods=20).sum().replace(0, np.nan)
    x['efficiency20_signed'] = (c-c.shift(20))/den
    x['efficiency20_abs'] = x.efficiency20_signed.abs()
    x['cross_count20'] = x.cross.ne(0).rolling(20, min_periods=20).sum()
    span = (x.high-x.low).replace(0, np.nan)
    body = (x.close-x.open).abs()
    # A flat daily bar has no defined wick ratio; it is not filled with zero.
    x['wick_ratio20'] = ((span-body)/span).rolling(20, min_periods=20).median()
    x['atr_price'] = x.atr/x.close
    ma30 = x.ma30 if 'ma30' in x else c.rolling(30, min_periods=30).mean()
    x['feature_ma30_q'] = (ma30-ma30.shift(1))/x.atr
    return x


FEATURE_KEYS = ('efficiency20_signed', 'efficiency20_abs', 'cross_count20',
                'wick_ratio20', 'atr_price', 'feature_ma30_q')


def feature_record(d, i, side):
    r = {'features_signal_day': pd.NaT, 'features_known_at': pd.NaT}
    if i < 0:
        r.update({k: np.nan for k in FEATURE_KEYS})
        r.update(ma30_direction_q=np.nan, efficiency20_direction=np.nan,
                 signal_stop_risk_fraction=np.nan, signal_stop_risk_atr=np.nan)
    else:
        row = d.iloc[i]
        r.update({k: float(row[k]) for k in FEATURE_KEYS})
        r.update(features_signal_day=row.timestamp, features_known_at=row.timestamp+DAY,
                 ma30_direction_q=side*float(row.feature_ma30_q),
                 efficiency20_direction=side*float(row.efficiency20_signed),
                 signal_stop_risk_fraction=(side*(row.close-row.ma)+1.5*row.atr)/row.close,
                 signal_stop_risk_atr=side*(row.close-row.ma)/row.atr+1.5)
    r['efficiency20_bin'] = category(r['efficiency20_abs'], [.2, .5], ['lt_0.2', '0.2_to_0.5', 'ge_0.5'])
    r['cross20_bin'] = category(r['cross_count20'], [4, 8], ['le_3', '4_to_7', 'ge_8'])
    r['wick20_bin'] = category(r['wick_ratio20'], [.4, .6], ['lt_0.4', '0.4_to_0.6', 'ge_0.6'])
    r['initial_risk_bin'] = category(r['signal_stop_risk_fraction'], [.1, .2], ['lt_10pct', '10_to_20pct', 'ge_20pct'])
    q = r['ma30_direction_q']
    r['ma30_bin'] = ('missing' if not np.isfinite(q) else 'conflict_le_-0.05' if q <= -.05
                     else 'aligned_gt_0.05' if q > .05 else 'middle')
    return r


def hypothetical_return(entry_reference, close_reference, side):
    """One unit initial equity, same ~1x quantity convention as saved V3."""
    entry = entry_reference*(1+side*SLIP)
    close = close_reference*(1-side*SLIP)
    qty = 1/(entry*(1+FEE))
    return qty*(side*(close-entry)-FEE*(entry+close))


class HourlyPath:
    def __init__(self, h):
        self.h = h.reset_index(drop=True)
        self.ts = pd.DatetimeIndex(self.h.timestamp).as_unit('ns')
        assert self.ts.is_monotonic_increasing and self.ts.is_unique
        if len(self.ts) > 1:
            assert np.all(np.diff(self.ts.asi8) == HOUR.value), 'Forward windows may not cross a gap'
        self.o = self.h.open.to_numpy(float)
        self.high = self.h.high.to_numpy(float)
        self.low = self.h.low.to_numpy(float)
        self.close = self.h.close.to_numpy(float)

    def index(self, start):
        i = int(self.ts.searchsorted(start))
        return i if i < len(self.ts) and self.ts[i] == start else None

    def first_touch(self, a, b, reference, side, atr, multiple):
        favorable = self.high[a:b] if side == 1 else self.low[a:b]
        adverse = self.low[a:b] if side == 1 else self.high[a:b]
        f = np.flatnonzero(side*(favorable-reference) >= multiple*atr)
        l = np.flatnonzero(side*(adverse-reference) <= -multiple*atr)
        fi, li = (int(f[0]) if len(f) else None), (int(l[0]) if len(l) else None)
        if fi is None and li is None:
            outcome = 'neither'
        elif fi is None:
            outcome = 'adverse_first'
        elif li is None:
            outcome = 'favorable_first'
        elif fi < li:
            outcome = 'favorable_first'
        elif li < fi:
            outcome = 'adverse_first'
        else:
            # Contract deliberately retains every same-hour double touch as
            # ambiguous, including a gap-open beyond one threshold.
            outcome = 'same_hour_ambiguous'
        return {f'first_{multiple}atr': outcome,
                f'first_favorable_{multiple}atr_hour': fi,
                f'first_adverse_{multiple}atr_hour': li}

    def observe(self, start, side, atr, recovery_extreme=None):
        a = self.index(start)
        reference = self.o[a] if a is not None else np.nan
        available = len(self.ts)-a if a is not None else 0
        r = dict(observation_start=start, observation_reference=reference,
                 observation_atr=atr, future_available_hours=available,
                 observation_start_found=a is not None)
        for days in HORIZONS:
            prefix = f'f{days}_'
            n = days*24
            complete = a is not None and available >= n and np.isfinite(atr) and atr > 0
            v = dict(complete=complete, end=start+days*DAY,
                     close_reference=np.nan, directional_close_pct=np.nan,
                     hypothetical_net_return=np.nan, close_atr=np.nan,
                     mfe_atr=np.nan, mae_atr=np.nan, peak_to_final_close_atr=np.nan,
                     first_1atr=None, first_favorable_1atr_hour=None, first_adverse_1atr_hour=None,
                     first_2atr=None, first_favorable_2atr_hour=None, first_adverse_2atr_hour=None,
                     old_extreme_recovered=None, recovery_first_hour=None,
                     recovery_first_day=None, event_extreme_to_worst_atr=np.nan,
                     event_extreme_to_final_atr=np.nan,
                     pre_recovery_retrace_lower_atr=np.nan,
                     pre_recovery_retrace_upper_atr=np.nan)
            if complete:
                b = a+n
                final = self.close[b-1]
                fav = float(np.max(self.high[a:b]) if side == 1 else np.min(self.low[a:b]))
                adv = float(np.min(self.low[a:b]) if side == 1 else np.max(self.high[a:b]))
                v.update(close_reference=final,
                         directional_close_pct=side*(final/reference-1)*100,
                         hypothetical_net_return=hypothetical_return(reference, final, side),
                         close_atr=side*(final-reference)/atr,
                         mfe_atr=max(0., side*(fav-reference)/atr),
                         mae_atr=max(0., -side*(adv-reference)/atr),
                         peak_to_final_close_atr=max(0., side*(fav-final)/atr),
                         **self.first_touch(a, b, reference, side, atr, 1),
                         **self.first_touch(a, b, reference, side, atr, 2))
                if recovery_extreme is not None:
                    favorable = self.high[a:b] if side == 1 else self.low[a:b]
                    hits = np.flatnonzero(side*(favorable-recovery_extreme) > 0)
                    first = int(hits[0]) if len(hits) else None
                    v.update(old_extreme_recovered=bool(len(hits)), recovery_first_hour=first,
                             recovery_first_day=first//24+1 if first is not None else None,
                             event_extreme_to_worst_atr=max(0., side*(recovery_extreme-adv)/atr),
                             event_extreme_to_final_atr=side*(recovery_extreme-final)/atr)
                    # The recovery hour's adverse move may precede or follow
                    # the new extreme. Keep confirmed and possible bounds.
                    adverse_path = self.low[a:b] if side == 1 else self.high[a:b]
                    if first is None:
                        lower = upper = max(0., side*(recovery_extreme-adv)/atr)
                    else:
                        before = list(adverse_path[:first]) + [reference, self.o[a+first]]
                        confirmed = min(before) if side == 1 else max(before)
                        if side*(self.o[a+first]-recovery_extreme) > 0:
                            possible = confirmed  # New extreme is already at the hour open.
                        else:
                            possible = min(confirmed, adverse_path[first]) if side == 1 else max(confirmed, adverse_path[first])
                        lower = max(0., side*(recovery_extreme-confirmed)/atr)
                        upper = max(0., side*(recovery_extreme-possible)/atr)
                    v.update(pre_recovery_retrace_lower_atr=lower,
                             pre_recovery_retrace_upper_atr=upper)
            r.update({prefix+k: value for k, value in v.items()})
        return r


def trade_map(trades):
    return {(pd.Timestamp(t.entry_time), int(t.side)): t for t in trades.itertuples()}


def classify_cross(start, side, events, trades, mapping):
    """Use logged decisions first. Ledger resolves only logged-empty busy periods."""
    hit = events[(events.timestamp == start) & (events.side == side)] if len(events) else events
    actual = mapping.get((start, side))
    if actual is not None:
        assert len(hit) == 1 and hit.iloc[0].status == 'filled', 'Filled entry must have its actual event'
        assert int(hit.iloc[0].trade_id) == int(actual.trade_id)
        return 'filled', actual, str(hit.iloc[0].stage), str(hit.iloc[0].reason)
    if len(hit):
        assert len(hit) == 1 and hit.iloc[0].status != 'filled'
        return str(hit.iloc[0].reason), None, str(hit.iloc[0].stage), str(hit.iloc[0].reason)
    if len(trades):
        # A midnight intrahour stop happens after the day's entry decision;
        # a midnight gap or short TP happens before it and consumes that hour.
        at_open_exit = trades[(trades.exit_time == start) & trades.exit_reason.isin(['stop_gap', 'accel1_rsi30'])]
        if len(at_open_exit):
            assert len(at_open_exit) == 1
            return 'exit_priority_same_hour', None, 'ledger', str(at_open_exit.iloc[0].exit_reason)
        busy = trades[(trades.entry_time < start) & ((trades.exit_time > start)
                      | ((trades.exit_time == start) & trades.exit_reason.eq('stop_intrahour')))]
        if len(busy):
            assert len(busy) == 1
            return 'position_occupied', None, 'ledger', 'position_open_at_entry_decision'
    raise AssertionError(f'Unclassified ready cross {start} side={side}; no entry event or open position')


def identity(meta, run_key):
    return dict(run_key=run_key, symbol=meta['symbol'], slug=meta['slug'],
                segment_start=pd.Timestamp(meta['trade_start']),
                segment_end=pd.Timestamp(meta['end']))


def phase_fields(timestamp):
    year = pd.Timestamp(timestamp).year
    return dict(year=year, phase='2023_2024' if year in (2023, 2024) else '2025_plus' if year >= 2025 else 'before_2023')


def actual_fields(t):
    if t is None:
        return dict(actual_trade_id=None, actual_entry_time=pd.NaT, actual_exit_time=pd.NaT,
                    actual_exit_interval_end=pd.NaT, actual_exit_reason=None,
                    actual_net_pnl=np.nan, actual_unit_return=np.nan,
                    actual_outcome=None, actual_terminal=None)
    return dict(actual_trade_id=int(t.trade_id), actual_entry_time=t.entry_time,
                actual_exit_time=t.exit_time, actual_exit_interval_end=t.exit_interval_end,
                actual_exit_reason=t.exit_reason, actual_net_pnl=float(t.net_pnl),
                actual_unit_return=float(t.return_on_entry_equity),
                actual_outcome='win' if t.net_pnl > 0 else 'loss' if t.net_pnl < 0 else 'flat',
                actual_terminal=t.exit_reason == 'sample_end')


def trade_event_features(d, i, t, daily_ts):
    """Current event descriptors, but initial risk remains the original risk."""
    r = feature_record(d, i, int(t.side))
    original_i = int(daily_ts.get_indexer([t.signal_day])[0])
    assert original_i >= 0
    initial = feature_record(d, original_i, int(t.side))
    for k in ['initial_risk_bin', 'signal_stop_risk_fraction', 'signal_stop_risk_atr']:
        r[k] = initial[k]
    r['initial_risk_signal_day'] = t.signal_day
    return r


def observe_segment(run_key, out_string):
    from v3_opportunity_inputs_20260913 import load_segment
    d, h, meta, trades, stops = load_segment(run_key)
    d = causal_features(d)
    out = Path(out_string)
    dest = out/'segments'/run_key
    dest.mkdir(parents=True, exist_ok=False)
    baseline_dir = Path(meta['baseline_dir'])
    if not baseline_dir.is_absolute():
        baseline_dir = ROOT/baseline_dir
    events = read_csv(baseline_dir/'entry_events.csv')
    assert sha(baseline_dir/'entry_events.csv') == meta['baseline_sha256']['entry_events.csv']
    for frame in (trades, stops):
        for c in ('timestamp', 'signal_day', 'entry_time', 'exit_time', 'exit_interval_end', 'tp_signal_day'):
            if c in frame:
                frame[c] = pd.to_datetime(frame[c], utc=True, format='mixed').dt.as_unit('ns')
    path = HourlyPath(h)
    ident = identity(meta, run_key)
    mapping = trade_map(trades)
    by_id = {int(t.trade_id): t for t in trades.itertuples()}
    daily_ts = pd.DatetimeIndex(d.timestamp)
    signal_rows = []
    for i, row in enumerate(d.itertuples()):
        start = row.timestamp+DAY
        if not int(row.cross) or not row.ready or not (ident['segment_start'] <= start < ident['segment_end']):
            continue
        side = int(row.cross)
        reason, actual, stage, logged = classify_cross(start, side, events, trades, mapping)
        qualified = bool(side*row.slope > .05)
        if reason == 'slope_rejected':
            assert not qualified
        if reason == 'filled':
            assert qualified
        obs = path.observe(start, side, float(row.atr))
        assert obs['observation_start_found'], 'Executable evaluation crossing must have next hour open'
        initial_stop = float(row.ma-side*1.5*row.atr)
        signal_rows.append({**ident, 'event_id': f'{run_key}:cross:{row.timestamp.isoformat()}:{side}',
            'event_type': 'raw_ready_cross', 'signal_day': row.timestamp, 'event_time': start,
            'side': side, **phase_fields(start), 'slope_direction': side*float(row.slope),
            'slope_qualified': qualified, 'entry_disposition': reason,
            'disposition_evidence_stage': stage, 'disposition_evidence_reason': logged,
            'initial_stop_from_signal': initial_stop,
            'next_open_stop_risk_fraction': side*(obs['observation_reference']-initial_stop)/obs['observation_reference'],
            **feature_record(d, i, side), **actual_fields(actual), **obs})
    signal_df = pd.DataFrame(signal_rows)
    assert len(signal_df[signal_df.entry_disposition.eq('filled')]) == len(trades) if len(signal_df) else not len(trades)

    exits = []
    for t in trades.itertuples():
        if t.exit_reason == 'sample_end':
            continue
        # Last completed daily information at recorded exit time, conservatively
        # before the unknown intrahour execution, never the remaining exit bar.
        i = int(daily_ts.searchsorted(t.exit_time-DAY, side='right'))-1
        atr = float(d.iloc[i].atr) if i >= 0 else np.nan
        exits.append({**ident, 'event_id': f'{run_key}:exit:{int(t.trade_id)}',
            'event_type': 'natural_exit', 'signal_day': d.iloc[i].timestamp if i >= 0 else pd.NaT,
            'event_time': t.exit_time, 'side': int(t.side), **phase_fields(t.exit_time),
            **trade_event_features(d, i, t, daily_ts), **actual_fields(t),
            'original_entry_atr': float(t.entry_atr),
            **path.observe(t.exit_interval_end, int(t.side), atr)})
    exit_df = pd.DataFrame(exits)

    stalled = []
    if len(stops):
        selected = stops[stops.full_holding_day.fillna(False).astype(bool)
                         & stops.no_new_extreme_days.ge(4)].sort_values('timestamp').drop_duplicates('trade_id')
        for s in selected.itertuples():
            t = by_id[int(s.trade_id)]
            i = int(daily_ts.get_indexer([s.signal_day])[0])
            assert i >= 0 and s.timestamp == s.signal_day+DAY
            assert s.no_new_extreme_days == 4, 'First full-holding stagnation must be exactly four days'
            feature = trade_event_features(d, i, t, daily_ts)
            stalled.append({**ident, 'event_id': f'{run_key}:stagnation4:{int(s.trade_id)}',
                'event_type': 'first_stagnation4', 'signal_day': s.signal_day,
                'event_time': s.timestamp, 'side': int(s.side), **phase_fields(s.timestamp),
                'event_extreme_price': float(s.extreme_price), 'event_extreme_day': s.extreme_day,
                'event_stop_before': float(s.old_stop), 'event_stop_after': float(s.new_stop),
                'event_mult_before': float(s.old_mult), 'event_mult_after': float(s.new_mult),
                'actual_exit_after_event_hours': (t.exit_interval_end-s.timestamp)/HOUR,
                **feature, **actual_fields(t),
                **path.observe(s.timestamp, int(s.side), float(d.iloc[i].atr), float(s.extreme_price))})
    stall_df = pd.DataFrame(stalled)

    tp = []
    for t in trades.itertuples():
        if t.exit_reason != 'accel1_rsi30':
            continue
        i = int(daily_ts.get_indexer([t.tp_signal_day])[0])
        assert i >= 0 and t.side == -1 and t.exit_time == t.tp_signal_day+DAY
        tp.append({**ident, 'event_id': f'{run_key}:short_tp:{int(t.trade_id)}',
            'event_type': 'first_actual_short_tp', 'signal_day': t.tp_signal_day,
            'event_time': t.exit_time, 'side': -1, **phase_fields(t.exit_time),
            'tp_rsi': float(d.iloc[i].rsi), 'tp_accel1': bool(d.iloc[i].accel1),
            **trade_event_features(d, i, t, daily_ts), **actual_fields(t),
            **path.observe(t.exit_interval_end, -1, float(d.iloc[i].atr))})
    tp_df = pd.DataFrame(tp)
    output_frames = {'crosses': signal_df, 'natural_exits': exit_df,
                     'stagnation4': stall_df, 'short_tp': tp_df}
    for name, frame in output_frames.items():
        if len(frame):
            assert frame.event_id.is_unique
            assert frame.features_known_at.le(frame.event_time).all()
        frame.to_parquet(dest/(name+'.parquet'), index=False, compression='zstd')
    actual = trades.copy()
    for key, value in ident.items():
        actual[key] = value
    actual.to_parquet(dest/'actual_trades.parquet', index=False, compression='zstd')
    result = {**{k: str(v) if isinstance(v, pd.Timestamp) else v for k, v in ident.items()},
              'counts': {k: len(v) for k, v in output_frames.items()}, 'actual_trades': len(trades),
              'dispositions': signal_df.entry_disposition.value_counts().to_dict() if len(signal_df) else {},
              'source_entry_events_sha256': sha(baseline_dir/'entry_events.csv'),
              'artifacts': {str(p.relative_to(out)): sha(p) for p in sorted(dest.iterdir())}}
    for key, frame in output_frames.items():
        result[key+'_complete20'] = int(frame.f20_complete.sum()) if len(frame) else 0
    write_json(out/'checkpoints'/(run_key+'.json'), result)
    return result


def main():
    from v3_opportunity_inputs_20260913 import load_sources
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--output', type=Path, default=OUT)
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--run-key', action='append')
    ap.add_argument('--contract', type=Path, required=True)
    ap.add_argument('--contract-sha256', required=True)
    args = ap.parse_args()
    assert sha(args.contract) == args.contract_sha256
    sources = load_sources()
    assert json.loads((ROUND/'inputs/completion.json').read_text())['complete']
    input_manifest = ROUND/'inputs/artifact_checksums.json'
    assert sha(input_manifest) == 'dabcb7a7ea881744b56e94033b9046e5ad396ea13f17ff6449cfd321c244c4a6'
    selected = sorted(args.run_key or sources)
    assert set(selected) <= set(sources)
    source_path = Path(__file__).with_name('v3_opportunity_inputs_20260913.py')
    pins = {str(Path(__file__).relative_to(ROOT)): sha(Path(__file__)),
            str(source_path.relative_to(ROOT)): sha(source_path),
            str(args.contract.resolve().relative_to(ROOT)): args.contract_sha256,
            str(input_manifest.relative_to(ROOT)): sha(input_manifest)}
    out = args.output.resolve()
    started = dict(source_pins=pins, run_keys=selected, fee=FEE, slip=SLIP,
                   horizons=list(HORIZONS), sources=sources,
                   classification='REVEALED_PRICE_PATH_DIAGNOSTIC_NOT_ACCOUNT_RETURN')
    if out.exists():
        assert args.resume, 'Explicit resume required; never overwrite a completed study'
        assert json.loads((out/'started.json').read_text()) == json.loads(json.dumps(started, default=str))
        assert not (out/'completion.json').exists(), 'Completed outputs are immutable'
    else:
        out.mkdir(parents=True)
        (out/'checkpoints').mkdir()
        write_json(out/'started.json', started)
        shutil.copy2(__file__, out/'source_script.py.txt')
        shutil.copy2(source_path, out/'source_inputs.py.txt')
    done = []
    pending = []
    for key in selected:
        p = out/'checkpoints'/(key+'.json')
        if p.exists():
            item = json.loads(p.read_text())
            for rel, digest in item['artifacts'].items():
                assert sha(out/rel) == digest
            done.append(item)
        else:
            pending.append(key)
    failures = []
    clock = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(observe_segment, key, str(out)): key for key in pending}
        for n, future in enumerate(as_completed(futures), 1):
            key = futures[future]
            try:
                done.append(future.result())
            except Exception as exc:
                failures.append(dict(run_key=key, error=repr(exc)))
                print('FAILED', key, repr(exc), flush=True)
            if n % 20 == 0 or n == len(futures):
                print(f'Segments {n}/{len(futures)} errors={len(failures)} elapsed={time.monotonic()-clock:.1f}s', flush=True)
    write_json(out/'failures.json', failures)
    assert not failures and len(done) == len(selected), 'Diagnose all scopes before summarizing'
    totals = {k: sum(x['counts'][k] for x in done) for k in ['crosses', 'natural_exits', 'stagnation4', 'short_tp']}
    completion = dict(complete=True, segments=len(done), symbols=len({r['symbol'] for r in done}),
                      counts=totals, actual_trades=sum(r['actual_trades'] for r in done),
                      complete20={k: sum(r[k+'_complete20'] for r in done) for k in totals},
                      elapsed_seconds=time.monotonic()-clock, source_pins=pins)
    pd.DataFrame([{k: v for k, v in item.items() if k not in ['artifacts', 'dispositions', 'counts']}
                  | item['counts'] for item in done]).sort_values('run_key').to_csv(out/'scope.csv', index=False)
    write_json(out/'completion.json', completion)
    write_json(out/'artifact_checksums.json', {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*'))
               if p.is_file() and p.name != 'artifact_checksums.json'})
    print(json.dumps(completion, ensure_ascii=False, default=str), flush=True)


if __name__ == '__main__':
    main()
