"""构造固定机会面板和路径描述；统计推断与资金账由独立阶段消费。"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from engine import GROUPS, build_panel, event_probe, load_verified_frames, sha

FAMILY = Path(__file__).resolve().parents[1]


def save_json(path: Path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str,allow_nan=False)+'\n')


def describe(panel: pd.DataFrame, group: str) -> dict:
    d = 1 if group.endswith('LONG') else -1
    selected = panel.loc[panel.feature_valid & panel[group]]
    valid = selected.loc[selected.valid20]
    row = {'group':group,'direction':d,'opportunities':len(selected),
           'symbols_with_opportunities':selected.symbol.nunique(),
           'complete20':len(valid),'complete20_symbols':valid.symbol.nunique(),
           'censored20':int(selected.censored20.sum()),
           'administrative_unmatured20':int(selected.administrative_unmatured20.sum())}
    if valid.empty:
        return row
    controls = panel.loc[panel.feature_valid & panel.valid20]
    weights = valid.groupby('symbol').size()/len(valid)
    for metric in ('q20','l20'):
        means = controls.groupby('symbol')[metric].mean()*d
        base = float((means.reindex(weights.index)*weights).sum())
        row[metric] = float((valid[metric]*d).mean())
        row['control_'+metric] = base
        row['delta_'+metric] = row[metric]-base
    if group.startswith('S'):
        m = controls.loc[controls['M_LONG' if d==1 else 'M_SHORT']]
        base = float((m.groupby('symbol').q20.mean().reindex(weights.index)*d*weights).sum())
        row['delta_filter'] = row['q20']-base
    r = valid.ret20*d
    row.update(mean_return20=float(r.mean()),median_return20=float(r.median()),
               win_fraction20=float(r.gt(0).mean()),q05_return20=float(r.quantile(.05)),
               q95_return20=float(r.quantile(.95)))
    for h in (1,5,10,40):
        z = selected.loc[selected[f'valid{h}']]
        row[f'complete{h}'] = len(z)
        row[f'mean_q{h}'] = float((d*z[f'q{h}']).mean()) if len(z) else np.nan
    side = 'long' if d==1 else 'short'
    row.update(mean_mfe20=float(valid[f'mfe20_{side}'].mean()),
               mean_mae20=float(valid[f'mae20_{side}'].mean()),
               median_peak_day=float(valid[f'peak20_{side}_day'].median()),
               mean_giveback20=float((valid[f'mfe20_{side}']-d*valid.q20).mean()),
               positive_q20_contribution=float((d*valid.q20).clip(lower=0).sum()),
               negative_q20_contribution=float((d*valid.q20).clip(upper=0).sum()))
    for name, slip in (('base',.0004),('stress',.0008)):
        probe = event_probe(panel,group,slippage=slip)
        row[f'{name}_event_mean_after_fee_slippage'] = float(probe.return_after_fee_slippage.mean())
        row[f'{name}_event_median_after_fee_slippage'] = float(probe.return_after_fee_slippage.median())
        row[f'{name}_additional_cost_break_even'] = row[f'{name}_event_mean_after_fee_slippage']
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-run',default='p0-inputs')
    parser.add_argument('--run-id',default='p1-research')
    args = parser.parse_args()
    for name in (args.input_run,args.run_id):
        if Path(name).name!=name or name in ('.','..'):
            raise ValueError('run IDs must be directory names')
    out = FAMILY/'artifacts'/args.run_id
    if out.exists():
        raise FileExistsError(out)
    inp = FAMILY/'artifacts'/args.input_run
    cutoff = pd.Timestamp(json.loads((FAMILY/'specs/input-request.json').read_text())['end'])
    pinned_files = ['specs/research-contract.md','specs/statistics-contract.md',
                    'specs/input-request.json','specs/source-pins.json',
                    'scripts/engine.py','scripts/run_research.py']
    pins = {p:sha(FAMILY/p) for p in pinned_files}
    save_json(out/'started.json',{'utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'pins':pins,'input_manifest_sha256':sha(inp/'frame-manifest.json'),
        'purpose':'fixed signals and future path labels; all history reused',
        'cutoff_utc':str(cutoff),'groups':list(GROUPS),'new_hypotheses_added':False})
    panels=[];coverage=[];started=time.time()
    for k,(symbol,frame) in enumerate(load_verified_frames(inp),1):
        p = build_panel(frame,cutoff)
        panels.append(p)
        coverage.append({'symbol':symbol,'rows':len(p),'past_eligible':int(p.feature_valid.sum()),
                         'complete20':int(p.valid20.sum()),'censored20':int(p.censored20.sum()),
                         'administrative_unmatured20':int(p.administrative_unmatured20.sum()),
                         'segments':int(p.research_segment_id.nunique())})
        if k%50==0:
            print(f'PANEL symbols={k} elapsed={time.time()-started:.1f}s',flush=True)
    panel = pd.concat(panels,ignore_index=True)
    del panels
    panel_path = out/'panel.pkl.gz'
    panel.to_pickle(panel_path,compression={'method':'gzip','compresslevel':1})
    save_json(out/'panel-manifest.json',{'sha256':sha(panel_path),'rows':len(panel),
        'symbols':panel.symbol.nunique(),'columns':list(panel.columns),'input_manifest_sha256':sha(inp/'frame-manifest.json'),
        'pins':pins,'path':'panel.pkl.gz','role':'own research features/labels, not cross-family market data'})
    pd.DataFrame(coverage).to_csv(out/'label-coverage.csv',index=False)
    columns=['symbol','signal_time','research_segment_id','feature_valid','atr14',
             'momentum20_delta','prior20_delta','prior5_delta',*GROUPS,
             'label20_status','q1','q5','q10','q20','q40','l20','ret20']
    panel.loc[panel.feature_valid,columns].to_csv(out/'opportunities.csv.gz',index=False,compression='gzip')
    summaries = [describe(panel,g) for g in GROUPS]
    pd.DataFrame(summaries).to_csv(out/'point-summary.csv',index=False)
    per_asset=[]
    for symbol,p in panel.groupby('symbol',sort=False):
        for group in GROUPS:
            per_asset.append(dict(symbol=symbol,**describe(p,group)))
    pd.DataFrame(per_asset).to_csv(out/'per-asset.csv',index=False)
    slices=[]
    windows=[(str(year),pd.Timestamp(f'{year}-01-01',tz='UTC'),pd.Timestamp(f'{year+1}-01-01',tz='UTC'))
             for year in range(2019,2027)]
    windows += [(f'recent_{days}d',cutoff-pd.Timedelta(days=days),cutoff)
                for days in (1,7,30,90,180,365)]
    for label,start,end in windows:
        mask = (panel.signal_time.gt(start)&panel.signal_time.le(end)) if label.startswith('recent_') else (panel.signal_time.ge(start)&panel.signal_time.lt(end))
        p = panel.loc[mask]
        for group in GROUPS:
            slices.append(dict(slice=label,start=str(start),end=str(end),**describe(p,group)))
    pd.DataFrame(slices).to_csv(out/'time-slices.csv',index=False)
    contribution=[]
    for group in GROUPS:
        d = 1 if group.endswith('LONG') else -1
        p = panel.loc[panel[group]&panel.valid20,['symbol','signal_time','q20','l20','ret20']].copy()
        p[['q20','l20','ret20']] *= d
        for kind,col in (('symbol','symbol'),('month','signal_time')):
            if kind=='month':
                p['month'] = p.signal_time.dt.strftime('%Y-%m');col='month'
            agg = p.groupby(col).agg(events=('q20','size'),sum_q20=('q20','sum'),mean_q20=('q20','mean'),
                                     sum_l20=('l20','sum'),sum_return20=('ret20','sum'))
            for key,row in agg.iterrows():
                contribution.append({'group':group,'kind':kind,'key':str(key),**row.to_dict()})
    pd.DataFrame(contribution).to_csv(out/'contributions.csv',index=False)
    changed=[p for p,h in pins.items() if sha(FAMILY/p)!=h]
    if changed:
        raise ValueError(f'Frozen computation source/contract changed: {changed}')
    save_json(out/'summary.json',{'utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'rows':len(panel),'symbols':panel.symbol.nunique(),'feature_valid':int(panel.feature_valid.sum()),
        'complete20':int(panel.valid20.sum()),'censored20':int(panel.censored20.sum()),
        'administrative_unmatured20':int(panel.administrative_unmatured20.sum()),
        'seconds':time.time()-started,'inference_computed':False,'funding_verified':False,
        'status':'FIXED_HISTORY_PATH_DIAGNOSTIC_COMPLETE','new_time_oos':False,
        'files':{p.name:sha(p) for p in out.iterdir() if p.is_file()}})
    print((out/'summary.json').read_text(),flush=True)


if __name__=='__main__':
    main()
