"""Sequential isolated arms; original full-history V3 accounts remain reused."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import json
from pathlib import Path
import time
import pandas as pd
from v3_opportunity_study_20260913 import *
from v3_opportunity_inputs_20260913 import load_sources, load_segment
from run_exit_state_machine_20260910 import stats
from run_exit_state_history_20260910 import time_blocks
from run_market import save_result

def one_coin(slug, keys, arm, out):
    out=Path(out); e=engine(); rows=[]; blocks=[]; entries=[]
    for key in sorted(keys):
        d,h,info,bt,bs=load_segment(key)
        lo=pd.Timestamp(info['trade_start']); hi=pd.Timestamp(info['end'])
        common={'run_key':key,'slug':slug,'symbol':info['symbol'],'case_id':arm,
                'start':str(lo),'end_exclusive':str(hi),'boundary_end_due_to_data':info['boundary_end_due_to_data']}
        events=[]; res=e.simulate(h,d,config(arm),lo,hi,None,0.,entry_events=events)
        res[0].update(stats(res[1])); p=out/'runs'/key/arm/'full'
        if p.exists():
            # A partial coin from an interrupted process is never silently accepted.
            assert json.loads((p/'summary.json').read_text()) == json.loads(json.dumps(res[0],default=str))
            pd.testing.assert_frame_equal(pd.read_csv(p/'trades.csv'),res[1].reset_index(drop=True),check_dtype=False,check_exact=False,rtol=1e-12,atol=1e-10)
        else:
            save_result(p,res)
            pd.DataFrame(events).reindex(columns=list(dict.fromkeys(e.ENTRY_EVENT_COLUMNS+getattr(e,'CANDIDATE_EVENT_COLUMNS',[])))).to_csv(p/'entry_events.csv',index=False)
        rows.append({**common,'result_path':str(p.relative_to(ROOT)),**res[0]})
        blocks.extend({**common,**x} for x in time_blocks(res[2],lo,hi))
        old={(str(pd.Timestamp(t['cross_day'])),int(t['side'])):t for t in bt.to_dict('records')}
        new={(str(pd.Timestamp(t['cross_day'])),int(t['side'])):t for t in res[1].to_dict('records')}
        for signal in sorted(set(old)|set(new)):
            b=old.get(signal); n=new.get(signal)
            entries.append({**common,'cross_day':signal[0],'side':signal[1],
                'baseline_trade_id':b['trade_id'] if b else None,'new_trade_id':n['trade_id'] if n else None,
                'baseline_entry_time':b['entry_time'] if b else None,'new_entry_time':n['entry_time'] if n else None,
                'relationship':'same_entry' if b and n and pd.Timestamp(b['entry_time'])==pd.Timestamp(n['entry_time']) else 'shifted_entry' if b and n else 'new_cross_entry' if n else 'baseline_cross_missed',
                'new_wait_days':n['entry_wait_days_used'] if n else None,
                'baseline_return':b['return_on_entry_equity'] if b else None,'new_return':n['return_on_entry_equity'] if n else None})
    result={'summary':rows,'blocks':blocks,'entry_comparison':entries}
    write_json(out/'checkpoints'/(slug+'.json'),result)
    return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--arm',required=True,choices=['E_STATE','TP_PROTECT']);ap.add_argument('--workers',type=int,default=4);ap.add_argument('--resume',action='store_true');a=ap.parse_args()
    verify_preconditions()
    if a.arm=='TP_PROTECT':assert json.loads((R/'accounts/E_STATE/completion.json').read_text())['complete']
    out=R/'accounts'/a.arm
    files=[Path(__file__),Path(__file__).with_name('v3_opportunity_study_20260913.py'),Path(__file__).with_name('v3_opportunity_inputs_20260913.py'),PIN,Path(__file__).with_name('run_exit_state_history_20260910.py'),Path(__file__).with_name('run_exit_state_machine_20260910.py'),Path(__file__).with_name('run_market.py')]
    pins={str(p.relative_to(ROOT)):sha(p) for p in files}
    if out.exists():assert a.resume and json.loads((out/'started.json').read_text())['pins']==pins
    else:
        out.mkdir(parents=True)
        write_json(out/'started.json',{'utc':str(pd.Timestamp.now(tz='UTC')),'pins':pins,'arm':a.arm,'config':asdict(config(a.arm)),'original_baseline_reused':True})
    sources=load_sources(); by={}
    for key,info in sources.items():by.setdefault(info['slug'],[]).append(key)
    records=[]; fail=[]; start=time.monotonic()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        jobs={}
        for slug,keys in sorted(by.items()):
            p=out/'checkpoints'/(slug+'.json')
            if p.exists():records.append(json.loads(p.read_text()))
            else:jobs[pool.submit(one_coin,slug,keys,a.arm,out)]=slug
        for n,f in enumerate(as_completed(jobs),1):
            try:records.append(f.result())
            except Exception as exc:fail.append({'slug':jobs[f],'error':repr(exc)});write_json(out/'failures.json',fail);print('FAILED',jobs[f],repr(exc),flush=True)
            if n%25==0 or n==len(jobs):print(f'{a.arm} {n}/{len(jobs)} coins, failures {len(fail)}, {time.monotonic()-start:.1f}s',flush=True)
    for kind in ['summary','blocks','entry_comparison']:pd.DataFrame([x for r in records for x in r[kind]]).to_csv(out/(kind+'.csv'),index=False)
    write_json(out/'completion.json',{'complete':not fail,'accounts':sum(len(r['summary']) for r in records),'coins':len(records),'failures':fail,'elapsed_seconds':time.monotonic()-start})
    assert not fail
    write_json(out/'artifact_checksums.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})

if __name__=='__main__':main()
