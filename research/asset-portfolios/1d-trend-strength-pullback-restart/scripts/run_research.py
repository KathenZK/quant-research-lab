"""TSPR一次性面板与描述入口；冻结计算后才允许执行。"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from family_common import FAMILY, save_json, sha, verify_lock
from engine import GROUPS, build_panel, load_verified_frames


def finite(value):
    return float(value) if np.isfinite(value) else None


def describe_subset(p, mask, side):
    d = 1 if side == 'LONG' else -1
    selected = p.loc[mask]
    q = selected.loc[selected.valid20]
    x = selected[f'strength_{side}']
    row = {'opportunities': len(selected), 'symbols': selected.symbol.nunique(),
           'complete20': len(q), 'complete20_symbols': q.symbol.nunique(),
           'censored20': int(selected.censored20.sum()),
           'unmatured20': int(selected.administrative_unmatured20.sum()),
           'x_mean': finite(x.mean()), 'x_median': finite(x.median()),
           'x_p10': finite(x.quantile(.1)), 'x_p90': finite(x.quantile(.9))}
    for h in (1, 5, 10, 20, 40):
        a = selected.loc[selected[f'valid{h}']]
        row[f'complete{h}'] = len(a)
        row[f'Q{h}'] = finite(d * a[f'q{h}'].mean())
    row['Late'] = finite(d * q.l20.mean())
    r = d * q.ret20
    for name, value in {'return20_mean': r.mean(), 'return20_median': r.median(),
                        'return20_p05': r.quantile(.05), 'return20_p95': r.quantile(.95),
                        'positive20_fraction': r.gt(0).mean()}.items():
        row[name] = finite(value)
    suffix = side.lower()
    for name in ('mfe20', 'mae20', 'peak20'):
        col = f'{name}_{suffix}_day' if name == 'peak20' else f'{name}_{suffix}'
        if col in q:
            row[name + '_mean'] = finite(q[col].mean())
    for cost_name, slip in (('base', .0004), ('stress', .0008)):
        a = q.entry_open * (1 + d * slip)
        b = q.exit_close20 * (1 - d * slip)
        net = d * (b - a) / a - .001 * (1 + b / a)
        row[cost_name + '_event_after_fee_slip_mean'] = finite(net.mean())
    return row


def describe(panel, out, cutoff):
    matrices, groups, assets, times, contributions, paths = [], [], [], [], [], []
    for side in ('LONG', 'SHORT'):
        for band in (1, 2, 3):
            b = panel[f'strength_bin_{side}'].eq(band)
            matrices.append({'direction': side, 'band': band, 'P': 'ALL', 'M': 'ALL',
                             **describe_subset(panel, b, side)})
            for p in (False, True):
                for m in (False, True):
                    mask = b & panel[f'P_{side}'].eq(p) & panel[f'M_{side}'].eq(m)
                    matrices.append({'direction': side, 'band': band, 'P': int(p),
                                     'M': int(m), **describe_subset(panel, mask, side)})
    for group in GROUPS:
        side = group.rsplit('_', 1)[1]
        d = 1 if side == 'LONG' else -1
        mask = panel[group]
        groups.append({'group': group, **describe_subset(panel, mask, side)})
        selected = panel.loc[mask]
        valid = selected.loc[selected.valid20].copy()
        valid['month'] = valid.signal_time.dt.strftime('%Y-%m')
        valid['year'] = valid.signal_time.dt.year
        for kind in ('symbol', 'month', 'year'):
            agg = valid.groupby(kind).agg(n=('q20', 'size'), Q20=('q20', 'mean'),
                                         Late=('l20', 'mean'), sum_Q20=('q20', 'sum'),
                                         sum_Late=('l20', 'sum'), return20=('ret20', 'mean'))
            agg[['Q20', 'Late', 'sum_Q20', 'sum_Late', 'return20']] *= d
            target = assets if kind == 'symbol' else times if kind == 'year' else contributions
            for key, row in agg.iterrows():
                target.append({'group': group, 'kind': kind, 'key': str(key), **row.to_dict()})
        for days in (1, 7, 30, 90, 180, 365):
            recent = panel.signal_time.gt(cutoff - pd.Timedelta(days=days)) & panel.signal_time.le(cutoff)
            times.append({'group': group, 'kind': 'recent_days', 'key': str(days),
                          **describe_subset(panel, mask & recent, side)})
        for common in (20, 40):
            q = selected.loc[selected[f'valid{common}']]
            for h in (1, 5, 10, 20, 40):
                if h <= common:
                    paths.append({'group': group, 'common_complete_horizon': common,
                                  'horizon': h, 'n': len(q), 'mean_Q': finite(d * q[f'q{h}'].mean())})
    for name, rows in (('state-matrix', matrices), ('group-summary', groups),
                       ('per-asset', assets), ('time-slices', times),
                       ('month-contributions', contributions), ('common-sample-path', paths)):
        pd.DataFrame(rows).to_csv(out / f'{name}.csv', index=False)
    return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', default='p1-research')
    args = parser.parse_args()
    if Path(args.run_id).name != args.run_id or args.run_id in ('.', '..'):
        raise ValueError('single new output directory name required')
    out = FAMILY / 'artifacts' / args.run_id
    if out.exists():
        raise FileExistsError(out)
    identity = verify_lock()
    inp = FAMILY / 'artifacts/p0-inputs'
    cutoff = pd.Timestamp(json.loads((FAMILY / 'specs/input-request.json').read_text())['end'])
    started = time.time()
    save_json(out / 'started.json', {'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                                    **identity, 'input_manifest_sha256': sha(inp / 'frame-manifest.json'),
                                    'history_role': 'ITERATIVE_REUSED_DIAGNOSTIC'})
    parts, coverage = [], []
    for n, (symbol, frame) in enumerate(load_verified_frames(inp), 1):
        p = build_panel(frame, cutoff)
        parts.append(p)
        coverage.append({'symbol': symbol, 'rows': len(p), 'feature_valid': int(p.feature_valid.sum()),
                         'complete20': int(p.valid20.sum()), 'censored20': int(p.censored20.sum()),
                         'unmatured20': int(p.administrative_unmatured20.sum()),
                         'zero_strength': int((p.feature_valid & p.strength_LONG.eq(0)).sum())})
        if n % 50 == 0:
            print(f'PANEL {n} symbols {time.time() - started:.1f}s', flush=True)
    panel = pd.concat(parts, ignore_index=True)
    del parts
    path = out / 'panel.pkl.gz'
    panel.to_pickle(path, compression={'method': 'gzip', 'compresslevel': 1})
    save_json(out / 'panel-manifest.json', {'path': path.name, 'sha256': sha(path),
                                          'rows': len(panel), 'symbols': panel.symbol.nunique(),
                                          'columns': list(panel.columns), 'pins': identity['files'],
                                          'computation_lock_sha256': identity['computation_lock_sha256'],
                                          'input_manifest_sha256': sha(inp / 'frame-manifest.json')})
    pd.DataFrame(coverage).to_csv(out / 'label-coverage.csv', index=False)
    groups = describe(panel, out, cutoff)
    verify_lock()
    save_json(out / 'summary.json', {'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                                    'status': 'FIXED_HISTORY_STATE_PANEL_COMPLETE',
                                    'rows': len(panel), 'symbols': panel.symbol.nunique(),
                                    'feature_valid': int(panel.feature_valid.sum()),
                                    'complete20': int(panel.valid20.sum()),
                                    'censored20': int(panel.censored20.sum()),
                                    'unmatured20': int(panel.administrative_unmatured20.sum()),
                                    'groups': groups, 'seconds': time.time() - started,
                                    'new_time_oos': False, 'funding_verified': False,
                                    'files': {p.name: sha(p) for p in out.iterdir() if p.is_file()}})
    print('P1 COMPLETE', flush=True)


if __name__ == '__main__':
    main()
