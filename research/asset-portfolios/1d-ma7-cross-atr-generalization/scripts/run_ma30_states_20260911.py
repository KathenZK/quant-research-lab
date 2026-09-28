"""Nine fixed MA30 mechanisms on exactly the previous continuous input segments."""
import argparse,json,time,sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import pandas as pd
import numpy as np
from ma30_study_20260911 import *
from run_market import save_result
from run_exit_state_machine_20260910 import stats
from run_exit_state_history_20260910 import time_blocks

def one_coin(slug,items,out):
    out=Path(out);e=engine();cache={};rows=[];blocks=[];scope=[]
    for key,info in sorted(items):
        lo=max(pd.Timestamp(info['trade_start']),pd.Timestamp('2023-01-01',tz='UTC'))
        hi=pd.Timestamp(info['end']);ins=pd.Timestamp(info['input_start'])
        common={'run_key':key,'slug':slug,'start':str(lo),'end_exclusive':str(hi),'source_segment_start':str(ins)}
        if lo>=hi:scope.append({**common,'status':'NO_EVALUATION_OVERLAP'});continue
        hp=ROOT/info['hourly_path']
        if hp not in cache:
            assert sha(hp)==info['hourly_sha256'];h=pd.read_parquet(hp).rename(columns={'ts':'timestamp'})
            h['timestamp']=pd.to_datetime(h.timestamp,utc=True).dt.as_unit('ns');cache[hp]=h
        h=cache[hp];h=h[(h.timestamp>=ins)&(h.timestamp<hi)].copy()
        assert h.eligible.all() and h.is_closed.all();h=h[['timestamp','open','high','low','close','volume']]
        d=pd.read_parquet(OLD/'cases/daily_features'/(key+'.parquet'))
        assert len(h)==24*len(d) and h.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all()
        ready=bool((d.ready90&(pd.to_datetime(d.timestamp,utc=True)+pd.Timedelta(days=1)>=lo)&(pd.to_datetime(d.timestamp,utc=True)+pd.Timedelta(days=1)<hi)).any())
        scope.append({**common,'status':'ELIGIBLE' if ready else 'INSUFFICIENT_HISTORY90'})
        decisions=[]
        for arm in ARMS:
            q=schedule(d,arm);events=[];res=e.simulate(h,q,config(arm),lo,hi,None,0.,entry_events=events)
            res[0].update(stats(res[1]));path=out/'runs'/key/arm/'full';save_result(path,res)
            pd.DataFrame(events).reindex(columns=e.ENTRY_EVENT_COLUMNS).to_csv(path/'entry_events.csv',index=False)
            rows.append({**common,'case_id':arm,'readiness_status':scope[-1]['status'],
                         'result_path':str(path.relative_to(ROOT)),**res[0]})
            blocks.extend({**common,'case_id':arm,**v} for v in time_blocks(res[2],lo,hi))
            keep=['timestamp','ready90']+[pre+label for label in ['long','short'] for pre in ['admit_','route_','rule_id_']]
            dec=q[keep+['long_q','short_q','long_x','short_x','long_repair','short_repair']].copy()
            dec.insert(0,'case_id',arm);decisions.append(dec)
        pd.concat(decisions,ignore_index=True).to_parquet(out/'decisions'/(key+'.parquet'),index=False)
    result={'summary':rows,'blocks':blocks,'scope':scope};write_json(out/'checkpoints'/(slug+'.json'),result);return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=4);ap.add_argument('--resume',action='store_true');a=ap.parse_args()
    out=R/'results'
    for rel,digest in json.loads((R/'before_results.json').read_text())['pins'].items():assert sha(ROOT/rel)==digest
    for p in [OLD/'cases/artifact_checksums.json',OLD/'results/artifact_checksums.json']:verify_manifest(p)
    pins={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(__file__).with_name('ma30_study_20260911.py'),PIN]}
    if out.exists():assert a.resume and json.loads((out/'started.json').read_text())['pins']==pins
    else:
        (out/'decisions').mkdir(parents=True);write_json(out/'started.json',{'utc':str(pd.Timestamp.now(tz='UTC')),'pins':pins,'arms':list(ARMS)})
        (out/'source_script.py.txt').write_bytes(Path(__file__).read_bytes());(out/'common_script.py.txt').write_bytes(Path(__file__).with_name('ma30_study_20260911.py').read_bytes())
    sources=json.loads((OLD/'cases/sources.json').read_text());by={}
    for key,info in sources.items():by.setdefault(info['slug'],[]).append((key,info))
    start=time.monotonic();records=[];fail=[]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs={}
        for slug,items in sorted(by.items()):
            c=out/'checkpoints'/(slug+'.json')
            if c.exists():records.append(json.loads(c.read_text()))
            else:jobs[pool.submit(one_coin,slug,items,out)]=slug
        for n,f in enumerate(as_completed(jobs),1):
            try:records.append(f.result())
            except Exception as exc:fail.append({'slug':jobs[f],'error':repr(exc)});write_json(out/'failures.json',fail);print('FAILED',jobs[f],repr(exc),flush=True)
            if n%20==0 or n==len(jobs):print(f'MA30 {n}/{len(jobs)} coins, failures {len(fail)}, {time.monotonic()-start:.1f}s',flush=True)
    for kind in ['summary','blocks','scope']:pd.DataFrame([x for r in records for x in r[kind]]).to_csv(out/(kind+'.csv'),index=False)
    write_json(out/'failures.json',fail);write_json(out/'completion.json',{'complete':not fail,'accounts':sum(len(r['summary']) for r in records),'sources':len(sources),'elapsed_seconds':time.monotonic()-start,'failures':len(fail)})
    assert not fail
    write_json(out/'artifact_checksums.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})

if __name__=='__main__':main()
