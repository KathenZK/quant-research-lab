"""All U_READY entries: matched exits or fixed original-equity episode replay."""
import argparse,json,time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
import pandas as pd
from ma30_study_20260911 import *
from build_adaptation_cases_20260911 import entry_match,verify_fixed,outcome_record
EXIT_ARMS=['C_DEFENSE','C_EXTENSION','M_DEFEND','M_EXTEND','M_MANAGE']

def one_coin(slug,items):
    e=engine();rows=[];proof=[];cache={};fixed_count=reused_count=0
    out=R/'pairs'
    for key,info in items:
        bp=OLD/'results/runs'/key/'U_READY/full/trades.csv'
        if not bp.exists():continue
        base=read_trades(bp)
        if not len(base):continue
        d=pd.read_parquet(OLD/'cases/daily_features'/(key+'.parquet'));d['timestamp']=pd.to_datetime(d.timestamp,utc=True).dt.as_unit('ns')
        hp=ROOT/info['hourly_path']
        if hp not in cache:
            assert sha(hp)==info['hourly_sha256'];h=pd.read_parquet(hp).rename(columns={'ts':'timestamp'})
            h['timestamp']=pd.to_datetime(h.timestamp,utc=True).dt.as_unit('ns');cache[hp]=h
        h=cache[hp];hi=pd.Timestamp(info['end']);h=h[(h.timestamp>=pd.Timestamp(info['input_start']))&(h.timestamp<hi)][['timestamp','open','high','low','close','volume']]
        scheduled={a:schedule(d,a) for a in ARMS};di=d.set_index('timestamp');decisions={a:q.set_index('timestamp') for a,q in scheduled.items()}
        maps={a:{(r['entry_time'],int(r['side'])):r for r in read_trades(R/'results/runs'/key/a/'full/trades.csv').to_dict('records')} for a in EXIT_ARMS}
        fixed_rows={a:[] for a in EXIT_ARMS};fixed_stops={a:[] for a in EXIT_ARMS}
        for t in base.to_dict('records'):
            stamp=pd.Timestamp(t['signal_day']);s=int(t['side']);direction='long' if s==1 else 'short';f=di.loc[stamp]
            q=s*(f.ma30-f.prev_ma30)/f.atr;x=s*(f.close-f.ma30)/f.atr
            row={'run_key':key,'slug':slug,'source_trade_id':int(t['trade_id']),'case_id':key+'::'+str(int(t['trade_id'])),
                 'entry_time':t['entry_time'],'signal_day':stamp,'side':s,'q':q,'x':x,
                 'btc_return60':f[direction+'_btc_return60'],'ready90':bool(f.ready90)}
            assert row['ready90']
            for fld,v in outcome_record(t).items():row[fld+'_U_READY']=v
            for a in EXIT_ARMS:
                candidate=maps[a].get((t['entry_time'],s));reused=candidate is not None and entry_match(t,candidate)
                if not reused:
                    res=e.simulate(h,scheduled[a],config(a),t['entry_time'],hi,None,0.,fixed_episode=t)
                    assert len(res[1])==1;candidate=res[1].iloc[0].to_dict();verify_fixed(t,candidate)
                    candidate.update(source_trade_id=int(t['trade_id']),baseline_exit_time=t['exit_time'],baseline_exit_reason=t['exit_reason'],
                        baseline_net_pnl=t['net_pnl'],baseline_return=t['return_on_entry_equity'],
                        delta_net_pnl=candidate['net_pnl']-t['net_pnl'],delta_return=candidate['return_on_entry_equity']-t['return_on_entry_equity'],
                        either_terminal=candidate['exit_reason']=='sample_end' or t['exit_reason']=='sample_end')
                    fixed_rows[a].append(candidate);st=res[3].copy();st.insert(0,'source_trade_id',int(t['trade_id']));fixed_stops[a].append(st);fixed_count+=1
                else:reused_count+=1
                for fld,v in outcome_record(candidate).items():row[fld+'_'+a]=v
                proof.append({'case_id':row['case_id'],'arm':a,'reused':reused,'candidate_trade_id':int(candidate['trade_id'])})
            for a,source in [('M_SKIP','U_READY'),('M_FULL','M_MANAGE'),('M_REPAIR','M_MANAGE'),('M_BTC','M_MANAGE')]:
                allow=bool(decisions[a].loc[stamp,'admit_'+direction]);row['allow_'+a]=allow
                row['u_'+a]=row['u_'+source] if allow else 0.
            rows.append(row)
        for a in EXIT_ARMS:
            path=out/'fixed'/key/a;path.mkdir(parents=True,exist_ok=True)
            pd.DataFrame(fixed_rows[a]).to_csv(path/'trades.csv',index=False)
            (pd.concat(fixed_stops[a],ignore_index=True) if fixed_stops[a] else pd.DataFrame()).to_csv(path/'stops.csv',index=False)
    pd.DataFrame(rows).to_parquet(out/'parts'/(slug+'.parquet'),index=False)
    pd.DataFrame(proof).to_csv(out/'proof'/(slug+'.csv'),index=False)
    result={'slug':slug,'cases':len(rows),'fixed':fixed_count,'reused':reused_count};write_json(out/'checkpoints'/(slug+'.json'),result);return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=3);ap.add_argument('--resume',action='store_true');args=ap.parse_args();out=R/'pairs'
    assert json.loads((R/'results/completion.json').read_text())['complete'];verify_manifest(R/'results/artifact_checksums.json')
    pins={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(__file__).with_name('ma30_study_20260911.py'),R/'results/artifact_checksums.json',OLD/'results/artifact_checksums.json',PIN]}
    if out.exists():assert args.resume and json.loads((out/'started.json').read_text())['pins']==pins
    else:
        (out/'parts').mkdir(parents=True);(out/'proof').mkdir();write_json(out/'started.json',{'pins':pins,'utc':str(pd.Timestamp.now(tz='UTC'))});(out/'source_script.py.txt').write_bytes(Path(__file__).read_bytes())
    sources=json.loads((OLD/'cases/sources.json').read_text());by={}
    for key,info in sources.items():by.setdefault(info['slug'],[]).append((key,info))
    t=time.monotonic();results=[];fail=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs={}
        for slug,items in by.items():
            p=out/'checkpoints'/(slug+'.json')
            if p.exists():results.append(json.loads(p.read_text()))
            else:jobs[pool.submit(one_coin,slug,items)]=slug
        for n,f in enumerate(as_completed(jobs),1):
            try:results.append(f.result())
            except Exception as exc:fail.append({'slug':jobs[f],'error':repr(exc)});write_json(out/'errors.json',fail);print('ERROR',jobs[f],repr(exc),flush=True)
            if n%20==0 or n==len(jobs):print(f'Pairs {n}/{len(jobs)}, errors {len(fail)}, {time.monotonic()-t:.1f}s',flush=True)
    write_json(out/'completion.json',{'complete':not fail,'cases':sum(x['cases'] for x in results),'fixed':sum(x['fixed'] for x in results),'reused':sum(x['reused'] for x in results),'errors':fail})
    assert not fail
    pd.concat([pd.read_parquet(p) for p in sorted((out/'parts').glob('*.parquet'))],ignore_index=True).to_parquet(out/'cases.parquet',index=False)
    write_json(out/'artifact_checksums.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})

if __name__=='__main__':main()
