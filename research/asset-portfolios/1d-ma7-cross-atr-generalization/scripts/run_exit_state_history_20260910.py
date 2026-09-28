"""Apply the frozen exit rules to every eligible retained historical segment."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
from pathlib import Path
import time
import numpy as np
import pandas as pd
from common import BASE,ROOT,sha,write_json
from run_exit_state_machine_20260910 import ROUND,PIN,load_engine,cases,account

BLOCKS=[('cycle_2020_2024','2020-01-01','2025-01-01'),
        ('calendar_2021_2023','2021-01-01','2024-01-01'),('calendar_2023_2025','2023-01-01','2026-01-01'),
        ('phase_2020_2021','2020-01-01','2022-01-01'),('phase_2022','2022-01-01','2023-01-01'),
        ('phase_2023_2024','2023-01-01','2025-01-01'),('phase_2025_2026','2025-01-01','2026-09-05')]
BLOCKS += [(f'year_{y}',f'{y}-01-01',f'{y+1}-01-01' if y<2026 else '2026-09-05') for y in range(2019,2027)]


def time_blocks(curve,lo,hi):
    stamps=pd.to_datetime(curve.timestamp,utc=True).dt.as_unit('ns').astype('int64').to_numpy()
    values=curve.equity.to_numpy(float);rows=[]
    for block,bs,be in BLOCKS:
        start=pd.Timestamp(bs,tz='UTC');end=pd.Timestamp(be,tz='UTC');a=max(lo,start);b=min(hi,end)
        row={'block':block,'requested_start':str(start),'requested_end':str(end),
             'complete_coverage':lo<=start and hi>=end,'account_position_inherited':True}
        if a>=b:
            rows.append({**row,'status':'NO_OVERLAP'});continue
        ia=int(np.searchsorted(stamps,a.value,side='left'))
        ib=int(np.searchsorted(stamps,b.value,side='right' if b==hi else 'left'))-int(b==hi)
        assert stamps[ia]==a.value and stamps[ib]==b.value
        ev=values[ia:ib+1];base=float(ev[0]);last=float(ev[-1])
        ret=(last/base-1)*100 if base>0 else None
        dd=float(np.min(ev/np.maximum.accumulate(ev)-1)*100) if base>0 else None
        rows.append({**row,'status':'COMPLETE' if row['complete_coverage'] else 'PARTIAL',
                     'actual_start':str(a),'actual_end':str(b),'days':(b-a).days,
                     'start_equity':base,'end_equity':last,'return_pct':ret,'max_drawdown_pct':dd})
    return rows


def one_coin(item,segments,frames,input_string,out_string):
    source=Path(input_string);out=Path(out_string);e=load_engine();symbol=item['symbol'];slug=item['slug']
    info=frames[symbol]
    for key in ['joint_daily','1h']:
        assert sha(source/info[key]['path'])==info[key]['sha256']
    da=pd.read_parquet(source/info['joint_daily']['path']);ha=pd.read_parquet(source/info['1h']['path'])
    rows=[];blocks=[]
    for n,seg in enumerate(sorted(segments,key=lambda s:s['input_start']),1):
        if seg['trade_days']<=0:continue
        key=f'{slug}__seg{n:03d}';lo=pd.Timestamp(seg['first_trade_open']);hi=pd.Timestamp(seg['end']);ins=pd.Timestamp(seg['input_start'])
        d=da[da.joint_segment_id.eq(seg['segment_id'])].copy().sort_values('ts').reset_index(drop=True)
        h=ha[(ha.ts>=ins)&(ha.ts<hi)].copy().sort_values('ts').reset_index(drop=True)
        assert len(d)==seg['input_days'] and len(h)==len(d)*24
        assert d.joint_eligible.all() and d.eligible.all() and h.eligible.all() and d.is_closed.all() and h.is_closed.all()
        assert pd.DatetimeIndex(d.ts).as_unit('ns').equals(pd.date_range(ins,hi,freq='D',inclusive='left').as_unit('ns'))
        assert pd.DatetimeIndex(h.ts).as_unit('ns').equals(pd.date_range(ins,hi,freq='h',inclusive='left').as_unit('ns'))
        assert not d.iloc[:28].research_window_valid.any() and d.iloc[28:].research_window_valid.all()
        h=h.rename(columns={'ts':'timestamp'});d=d.rename(columns={'ts':'timestamp'})
        d=e.enrich_features(e.features(d));assert d.ready.equals(d.research_window_valid)
        assert d.loc[d.ready,'atr'].gt(0).all()
        meta={**seg,'slug':slug,'run_key':key,'source_input_directory':str(source.relative_to(ROOT)),
              'source_frames':info,'boundary_kind':'DATA_BOUNDARY' if seg['boundary_end_due_to_data'] else 'SAMPLE_END',
              'fully_covers_cycle_2020_2024':lo<=pd.Timestamp('2020-01-01',tz='UTC') and hi>=pd.Timestamp('2025-01-01',tz='UTC')}
        write_json(out/'inputs_used'/(key+'.json'),meta)
        market=out/'market'/key;market.mkdir(parents=True,exist_ok=False)
        d.to_csv(market/'daily_features.csv',index=False)
        for cid,label,cfg in cases():
            r=account(e,out/'runs'/key/cid/'full',h,d,cfg,lo,hi)
            identity={'symbol':symbol,'slug':slug,'run_key':key,'segment_id':seg['segment_id'],'trade_days':seg['trade_days'],
                      'case_id':cid,'label':label,'boundary_end_due_to_data':seg['boundary_end_due_to_data'],
                      'fully_covers_cycle_2020_2024':meta['fully_covers_cycle_2020_2024']}
            rows.append({**identity,**r[0]})
            blocks.extend({**identity,**z} for z in time_blocks(r[2],lo,hi))
    result={'summary':rows,'blocks':blocks}
    write_json(out/'checkpoints'/(slug+'.json'),result)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--workers',type=int,default=2);ap.add_argument('--resume',action='store_true');args=ap.parse_args()
    source=args.input.resolve();out=args.output.resolve();assert json.loads((source/'completion.json').read_text())['complete']
    hashes=json.loads((source/'checksums.json').read_text())
    for rel,digest in hashes.items():assert sha(source/rel)==digest,rel
    pin=json.loads(PIN.read_text())
    for rel,digest in pin['contracts'].items():assert sha(ROOT/rel)==digest,rel
    scope=pd.read_csv(source/'scope.csv');segs=pd.read_csv(source/'segments.csv');frames=json.loads((source/'frames_manifest.json').read_text())
    assert set(scope.symbol)==set(frames)
    source_pins={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),PIN,source/'checksums.json']}
    if out.exists():
        assert args.resume
        assert json.loads((out/'run_manifest.json').read_text())['source_pins']==source_pins
    else:
        out.mkdir(parents=True);scope.to_csv(out/'scope.csv',index=False);segs.to_csv(out/'segments.csv',index=False)
        write_json(out/'run_manifest.json',{'created_before_results_utc':str(pd.Timestamp.now(tz='UTC')),'source_pins':source_pins,
            'engine_pin':pin,'input_source':str(source.relative_to(ROOT)),'all_segments_preserved':True,
            'new_candidates_selected_by_current_results':False,'calendar_blocks':BLOCKS,
            'expected_segment_accounts':int(segs.trade_days.gt(0).sum())*4,
            'funding_window_verified':False,'classification':'HISTORICAL_PRICE_DIAGNOSTIC'})
    pending=[];results=[];fails=[];start=time.monotonic()
    for item in scope.to_dict('records'):
        p=out/'checkpoints'/(item['slug']+'.json')
        if p.exists():results.append(json.loads(p.read_text()))
        else:pending.append(item)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs={pool.submit(one_coin,it,segs[segs.symbol.eq(it['symbol'])].to_dict('records'),{it['symbol']:frames[it['symbol']]},str(source),str(out)):it for it in pending}
        for n,f in enumerate(as_completed(jobs),1):
            it=jobs[f]
            try:results.append(f.result())
            except Exception as exc:
                fails.append({'symbol':it['symbol'],'error':repr(exc)});write_json(out/'execution_failures.json',fails)
                print('FAILED',it['symbol'],repr(exc),flush=True)
            if n%10==0 or n==len(jobs):print(f'Historical coins {n}/{len(jobs)}, errors {len(fails)}, seconds {time.monotonic()-start:.1f}',flush=True)
    for kind in ['summary','blocks']:
        pd.DataFrame([z for r in results for z in r[kind]]).to_csv(out/(kind+'.csv'),index=False)
    write_json(out/'execution_failures.json',fails)
    manifest={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ['artifact_checksums.json','completion.json']}
    write_json(out/'artifact_checksums.json',manifest)
    write_json(out/'completion.json',{'complete':len(results)==len(scope) and not fails,'coins':len(results),
        'segment_accounts':sum(len(r['summary']) for r in results),'expected_segment_accounts':int(segs.trade_days.gt(0).sum())*4,
        'elapsed_seconds':time.monotonic()-start,'manifest_sha256':sha(out/'artifact_checksums.json')})
    assert len(results)==len(scope) and not fails

if __name__=='__main__':main()
