"""MTTC完整机会与账户研究；只读取本轮新可信启动返回帧，拒绝覆盖已运行结果。"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[2]
KERNEL = REPO / 'research/_shared-kernels/medium-term-trend-capture/v1'
sys.path.insert(0, str(KERNEL))
sys.path.insert(0, '/Users/ZK/OpenCode/quant-strategy-lab/src')
from engine import build_panel, build_origins, simulate_opportunity  # noqa: E402
from portfolio import simulate_portfolio, portfolio_metrics  # noqa: E402
from inference import paired_statistics  # noqa: E402


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save_json(path, value):
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False)+'\n')


def verify_lock():
    path = FAMILY/'specs/computation-lock.json'
    lock = json.loads(path.read_text())
    for relative, expected in lock['files'].items():
        if sha(REPO/relative) != expected:
            raise ValueError(f'Frozen computation differs: {relative}')
    pins=json.loads((FAMILY/'specs/source-pins.json').read_text())
    for relative, expected in pins['files'].items():
        if sha(Path('/Users/ZK/OpenCode/quant-strategy-lab')/relative) != expected:
            raise ValueError(f'Pinned formal data source differs: {relative}')
    return {'path': str(path.relative_to(REPO)), 'sha256': sha(path)}


def load_inputs():
    root = FAMILY/'artifacts/p0-inputs'
    manifest = json.loads((root/'frame-manifest.json').read_text())
    frames = {}
    for symbol, row in manifest.items():
        path = root/row['path']
        if sha(path) != row['sha256']:
            raise ValueError(f'New returned input changed: {symbol}')
        f = pd.read_pickle(path, compression='gzip')
        if len(f) != row['rows']:
            raise ValueError('Input dimensions changed')
        frames[symbol] = f
    return frames


def price_label(segment, start, base, atr, horizon):
    if start >= len(segment) or not np.isfinite(base) or base <= 0:
        return dict(outcome='CENSORED', endpoint_return=None, first_hit_day=None)
    closes = segment.close.iloc[start:start+horizon].to_numpy(float)
    z = (closes-base)/atr
    success, failure = np.flatnonzero(z >= 2), np.flatnonzero(z <= -2)
    up = success[0] if len(success) else np.inf
    down = failure[0] if len(failure) else np.inf
    outcome = ('CONTINUATION' if up < down else 'FAILURE' if down < up else
               'TIMEOUT' if len(closes) == horizon else 'CENSORED')
    return dict(outcome=outcome, endpoint_return=float(closes[-1]/base-1) if len(closes)==horizon else None,
                first_hit_day=int(min(up, down)+1) if np.isfinite(min(up, down)) else None)


def freeze():
    if (FAMILY/'specs/computation-lock.json').exists():
        raise FileExistsError('Computation already frozen; do not modify v1')
    files = list(KERNEL.rglob('*.py')) + [Path(__file__)]
    files += [FAMILY/'specs/config.json', FAMILY/'specs/research-contract.md']
    files += [FAMILY/'specs/input-request.json', FAMILY/'specs/source-pins.json', FAMILY/'specs/input-contract.md']
    files += [FAMILY/'scripts/audit_funding.py', FAMILY/'scripts/test_audit_funding.py']
    files += [FAMILY/'artifacts/p0-inputs'/name for name in
              ('frame-manifest.json','summary.json','independent-verification.json')]
    manifest = {'files': {str(p.relative_to(KERNEL)): sha(p) for p in sorted(KERNEL.rglob('*.py'))}}
    save_json(KERNEL/'manifest.json', manifest)
    files.append(KERNEL/'manifest.json')
    save_json(FAMILY/'specs/computation-lock.json',
              {'frozen_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'stage': 'before_new_returns',
               'files': {str(p.relative_to(REPO)): sha(p) for p in files}})


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--freeze', action='store_true')
    args = p.parse_args()
    if args.freeze:
        freeze()
        return
    lock = verify_lock()
    config = json.loads((FAMILY/'specs/config.json').read_text())
    out = FAMILY/'artifacts'/config['run_id']
    out.mkdir(exist_ok=False)
    save_json(out/'started.json', {'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                                 'lock': lock, 'python': sys.executable})
    started = time.time()
    frames = load_inputs()
    panel = build_panel(frames, config)
    panel.attrs = {}
    panel.to_parquet(out/'panel.parquet', index=False)
    segments = {(str(s), str(k)): g.reset_index(drop=True)
                for (s,k), g in panel.groupby(['symbol', 'segment'], sort=False, dropna=True)}
    origins = build_origins(panel, config)
    labeled = []
    for r in origins.to_dict('records'):
        g = segments[(str(r['symbol']), str(r['segment']))]
        t = int(r['origin_index'])
        r['complete_window_60'] = t+61 < len(g)
        r['segment_rows_after_origin'] = len(g)-t-1
        for h in (20,60):
            label = price_label(g, t+1, float(g.open.iloc[t+1]) if t+1<len(g) else np.nan, r['atr'], h)
            r.update({f'origin_{h}_{key}': value for key,value in label.items()})
        labeled.append(r)
    origins = pd.DataFrame(labeled)
    origins.to_parquet(out/'origins.parquet', index=False)
    print(f'INPUT panel={len(panel)} symbols={len(frames)} origins={len(origins)} elapsed={time.time()-started:.1f}s', flush=True)
    opportunities, unit_parts, daily_parts, action_parts, accounts, comparisons = [], [], [], [], {}, {}
    for cost in config['costs']:
        cost_summaries = []
        for policy in config['policies']:
            paths = {}
            for r in origins.to_dict('records'):
                g = segments[(str(r['symbol']), str(r['segment']))]
                simulated = simulate_opportunity(g, r, policy, cost, config)
                row, path = dict(simulated['summary']), simulated['daily'].copy()
                row.update(origin_id=r['origin_id'], symbol=r['symbol'], policy=policy,
                           cost_id=cost['id'], origin_ts=r['origin_ts'], atr=r['atr'],
                           complete_window_60=bool(r['complete_window_60']))
                for h in (20,60):
                    if row.get('entered', False):
                        locs = np.flatnonzero(g.ts.eq(pd.Timestamp(row['entry_ts'])).to_numpy())
                        if len(locs) != 1:
                            raise ValueError('Entry timestamp not in its segment')
                        label = price_label(g, int(locs[0]), float(row['entry_price']), r['atr'], h)
                    else:
                        label = dict(outcome='NOT_ENTERED', endpoint_return=None, first_hit_day=None)
                    row.update({f'entry_{h}_{key}': value for key,value in label.items()})
                for key, value in (('origin_id',r['origin_id']), ('symbol',r['symbol']), ('policy',policy), ('cost_id',cost['id'])):
                    path[key] = value
                cost_summaries.append(row)
                paths[r['origin_id']] = path
                unit_parts.append(path)
            daily, actions = simulate_portfolio(origins, paths, policy, cost['id'], config)
            daily_parts.append(daily)
            action_parts.append(actions)
            accounts[cost['id']+'.'+policy] = portfolio_metrics(daily, actions, config)
            print(f'ACCOUNT {cost["id"]} {policy} return={accounts[cost["id"]+"."+policy]["total_return"]:.6f} elapsed={time.time()-started:.1f}s', flush=True)
        obs = pd.DataFrame(cost_summaries)
        opportunities.extend(cost_summaries)
        subset = obs.loc[obs.complete_window_60 & obs.normal_complete]
        wide = subset.pivot(index='origin_id', columns='policy', values='return').dropna()
        wide = wide.join(origins.set_index('origin_id')[['symbol','origin_ts']]).reset_index()
        wide.to_parquet(out/f'paired-{cost["id"]}.parquet', index=False)
        if cost['id'] == 'base':
            comparisons[cost['id']] = paired_statistics(wide, config)
        else:
            means = wide[['A','B','C']].mean()
            comparisons[cost['id']] = dict(n=len(wide), points={**means.to_dict(),
                                           'B_minus_A':float(means.B-means.A), 'C_minus_B':float(means.C-means.B)})
    all_obs = pd.DataFrame(opportunities)
    all_obs.to_parquet(out/'opportunities.parquet', index=False)
    pd.concat(unit_parts, ignore_index=True).to_parquet(out/'unit_daily.parquet', index=False)
    pd.concat(daily_parts, ignore_index=True).to_parquet(out/'portfolio_daily.parquet', index=False)
    pd.concat(action_parts, ignore_index=True).to_parquet(out/'portfolio_actions.parquet', index=False)
    save_json(out/'account-metrics.json', accounts)
    save_json(out/'paired-statistics.json', comparisons)
    save_json(out/'completed.json', {'completed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'elapsed_seconds': time.time()-started, 'symbols': len(frames), 'panel_rows':len(panel),
               'origins':len(origins), 'opportunity_rows':len(all_obs), 'lock_reverified':verify_lock(),
               'files':{p.name:sha(p) for p in out.glob('*') if p.is_file()}})
    print('COMPLETED', flush=True)


if __name__ == '__main__':
    main()
