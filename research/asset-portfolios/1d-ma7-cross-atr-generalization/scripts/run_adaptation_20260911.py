"""Replay learned daily admission and whole-trade exit routing, with real position timing."""
from __future__ import annotations
import argparse,importlib.util,json,sys,time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import pandas as pd
import numpy as np
from common import BASE,ROOT,sha,write_json
from learn_adaptation_20260911 import R,ARMS,schedules
from run_market import save_result
from run_exit_state_machine_20260910 import stats
from run_exit_state_history_20260910 import time_blocks
PIN=BASE/'specs/adaptation-engine-pin-20260911.json'

def engine():
    x=json.loads(PIN.read_text());p=ROOT/x['engine_path'];assert sha(p)==x['engine_sha256']
    name='ma7_adaptation_frozen_v4'
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
    return sys.modules[name]

def one_coin(slug,items,models,case_dir,out):
    e=engine();case_dir=Path(case_dir);out=Path(out);rows=[];blocks=[];scope=[];cache={}
    cfg=e.Config(reverse=False,progress_days=4,fee=.001,slip=.0004,admission_routing=True)
    for key,info in sorted(items):
        lo=max(pd.Timestamp(info['trade_start']),pd.Timestamp('2023-01-01',tz='UTC'));hi=pd.Timestamp(info['end']);ins=pd.Timestamp(info['input_start'])
        common={'run_key':key,'slug':slug,'source_result':info['source_result'],'source_segment_start':str(ins),'start':str(lo),'end_exclusive':str(hi)}
        if lo>=hi:scope.append({**common,'status':'NO_EVALUATION_OVERLAP','days':0});continue
        p=ROOT/info['hourly_path']
        if str(p) not in cache:
            assert sha(p)==info['hourly_sha256'];z=pd.read_parquet(p).rename(columns={'ts':'timestamp'});z['timestamp']=pd.to_datetime(z.timestamp,utc=True).dt.as_unit('ns');cache[str(p)]=z
        h=cache[str(p)];h=h[(h.timestamp>=ins)&(h.timestamp<hi)].copy();assert h.eligible.all() and h.is_closed.all()
        h=h[['timestamp','open','high','low','close','volume']]
        d=pd.read_parquet(case_dir/'daily_features'/(key+'.parquet'));d['timestamp']=pd.to_datetime(d.timestamp,utc=True).dt.as_unit('ns')
        assert d.timestamp.iloc[0]==ins and d.timestamp.iloc[-1]+pd.Timedelta(days=1)==hi
        assert len(h)==len(d)*24 and h.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all()
        if not (d.ready90&(d.timestamp+pd.Timedelta(days=1)>=lo)&(d.timestamp+pd.Timedelta(days=1)<hi)).any():status='INSUFFICIENT_HISTORY90'
        else:status='ELIGIBLE'
        scope.append({**common,'status':status,'days':(hi-lo).days,'ready90_signal_days':int((d.ready90&(d.timestamp+pd.Timedelta(days=1)>=lo)&(d.timestamp+pd.Timedelta(days=1)<hi)).sum())})
        daily=schedules(d,slug,models);meta={**info,'run_key':key,'slug':slug,'eval_start':str(lo),'eval_end':str(hi)};write_json(out/'inputs_used'/(key+'.json'),meta)
        schedule_rows=[]
        for arm,q in daily.items():
            path=out/'runs'/key/arm/'full';events=[];r=e.simulate(h,q,cfg,lo,hi,None,0.,entry_events=events)
            r[0].update(stats(r[1]));save_result(path,r);pd.DataFrame(events).reindex(columns=e.ENTRY_EVENT_COLUMNS).to_csv(path/'entry_events.csv',index=False)
            counts=r[1].exit_route.value_counts().to_dict() if len(r[1]) else {}
            row={**common,'case_id':arm,'days':(hi-lo).days,'readiness_status':status,**r[0],**{'route_'+a+'_trades':int(counts.get(a,0)) for a in ['v3','defense','extension']}}
            row['admission_retained_ratio']=float(r[0]['entry_fills']/r[0]['entry_attempts']) if r[0]['entry_attempts'] else None
            rows.append(row);blocks.extend({**common,'case_id':arm,**z} for z in time_blocks(r[2],lo,hi))
            cols=['timestamp','ready90','cross','ready','slope','admit_long','admit_short','route_long','route_short','rule_id_long','rule_id_short']+[s+'_'+f for s in ['long','short'] for f in ['model_id','fold','train_cutoff','leaf_id','reason']]
            keep=q[cols].copy();keep.insert(0,'case_id',arm);schedule_rows.append(keep)
        pd.concat(schedule_rows,ignore_index=True).to_parquet(out/'inputs_used'/(key+'_decisions.parquet'),index=False)
    result={'summary':rows,'blocks':blocks,'scope':scope};write_json(out/'checkpoints'/(slug+'.json'),result);return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cases',type=Path,default=R/'cases');ap.add_argument('--learning',type=Path,default=R/'learning');ap.add_argument('--output',type=Path,default=R/'results');ap.add_argument('--workers',type=int,default=2);ap.add_argument('--resume',action='store_true');args=ap.parse_args();out=args.output
    for source in [args.cases,args.learning]:
        assert json.loads((source/'completion.json').read_text())['complete']
        for rel,h in json.loads((source/'artifact_checksums.json').read_text()).items():assert sha(source/rel)==h,rel
    pin=json.loads(PIN.read_text())
    for rel,h in pin['contracts'].items():assert sha(ROOT/rel)==h
    source_pins={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(__file__).with_name('learn_adaptation_20260911.py'),PIN,args.cases/'artifact_checksums.json',args.learning/'artifact_checksums.json',Path(__file__).with_name('run_market.py'),Path(__file__).with_name('run_exit_state_history_20260910.py')]}
    if out.exists():assert args.resume and json.loads((out/'started.json').read_text())['source_pins']==source_pins
    else:
        out.mkdir(parents=True);write_json(out/'started.json',{'utc':str(pd.Timestamp.now(tz='UTC')),'source_pins':source_pins,'engine_pin':pin,'costs':{'fee_per_side':.001,'slip_per_side':.0004},'arms':['U_READY']+ARMS,'all_original_segments_retained_in_scope':True,'no_gap_splicing':True,'funding_verified':False})
        (out/'source_script.py.txt').write_bytes(Path(__file__).read_bytes());(out/'learner_at_run.py.txt').write_bytes(Path(__file__).with_name('learn_adaptation_20260911.py').read_bytes())
    models=json.loads((args.learning/'models.json').read_text());sources=json.loads((args.cases/'sources.json').read_text());by={}
    for key,info in sources.items():by.setdefault(info.get('slug',key.rsplit('__seg',1)[0]),[]).append((key,info))
    results=[];jobs=[];fail=[];start=time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for slug,items in sorted(by.items()):
            chk=out/'checkpoints'/(slug+'.json')
            if chk.exists():results.append(json.loads(chk.read_text()))
            else:jobs.append((slug,pool.submit(one_coin,slug,items,models,str(args.cases),str(out))))
        lookup={f:s for s,f in jobs}
        for n,f in enumerate(as_completed(lookup),1):
            try:results.append(f.result())
            except Exception as exc:fail.append({'slug':lookup[f],'error':repr(exc)});write_json(out/'execution_failures.json',fail);print('FAILED',lookup[f],repr(exc),flush=True)
            if n%20==0 or n==len(lookup):print(f'Adaptation coins {n}/{len(lookup)}, failures {len(fail)}, seconds {time.monotonic()-start:.1f}',flush=True)
    for kind in ['summary','blocks','scope']:pd.DataFrame([z for r in results for z in r[kind]]).to_csv(out/(kind+'.csv'),index=False)
    write_json(out/'execution_failures.json',fail)
    write_json(out/'completion.json',{'complete':len(results)==len(by) and not fail,'coins_with_source_segments':len(by),'account_runs':sum(len(r['summary']) for r in results),'source_segments':len(sources),'elapsed_seconds':time.monotonic()-start,'failures':len(fail)})
    assert len(results)==len(by) and not fail
    write_json(out/'artifact_checksums.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})
if __name__=='__main__':main()
