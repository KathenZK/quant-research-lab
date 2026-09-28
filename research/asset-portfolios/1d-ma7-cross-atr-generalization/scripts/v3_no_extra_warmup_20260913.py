"""Remove only the fixed observation-age mask; consume frozen family inputs."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
import json
import time
import numpy as np
import pandas as pd
from common import ROOT, BASE, sha, write_json
from v3_opportunity_study_20260913 import engine, config, PIN, R as OLD
from v3_opportunity_inputs_20260913 import load_sources, load_segment, table, checked
from run_market import save_result
from run_exit_state_machine_20260910 import stats
from run_exit_state_history_20260910 import time_blocks
from build_v3_opportunity_report_20260913 import trade_stats

R=BASE/'artifacts/v3_no_extra_warmup_20260913'
CONTRACT=BASE/'specs/contract-v3-no-extra-warmup-20260913.md'
ARMS=['V3','E_STATE','TP_PROTECT']
INDICATORS=['ma','atr','rsi','slope','cross','accel1','accel2']

def natural_ready(d):
    """Input validity stays intact; old 29-day research-window flags stay archived."""
    x=d.copy()
    quality=x[['eligible','observed_valid','is_closed','joint_eligible']].all(axis=1)
    x['ready']=quality & np.isfinite(x[['ma','atr','rsi','slope']]).all(axis=1) & x.atr.gt(0)
    pd.testing.assert_frame_equal(x.drop(columns='ready'),d.drop(columns='ready'),check_exact=True)
    return x

@lru_cache(maxsize=1)
def catalog():
    return json.loads((R/'inputs/catalog.json').read_text())

def load_new(key):
    info=catalog()[key]
    if info['legacy']:
        d,h,_,_,_=load_segment(key)
    else:
        d=pd.read_parquet(checked(ROOT/info['joint_path'],info['joint_sha256']))
        d=d[d.joint_segment_id.eq(info['segment_id'])].rename(columns={'ts':'timestamp'}).reset_index(drop=True)
        h=pd.read_parquet(checked(ROOT/info['hourly_path'],info['hourly_sha256']))
        h=h[(h.ts>=pd.Timestamp(info['input_start']))&(h.ts<pd.Timestamp(info['end']))].rename(columns={'ts':'timestamp'}).reset_index(drop=True)
        for f in [d,h]:f['timestamp']=pd.to_datetime(f.timestamp,utc=True).dt.as_unit('ns')
        d=engine().enrich_features(engine().features(d))
    for f,freq in [(d,'D'),(h,'h')]:
        expected=pd.date_range(info['input_start'],info['end'],freq=freq,inclusive='left').as_unit('ns')
        assert pd.DatetimeIndex(f.timestamp).as_unit('ns').equals(expected),(key,'gap')
        assert f[['eligible','observed_valid','is_closed']].all().all(),(key,'invalid market row')
    assert d.joint_eligible.all() and d.hour_rows.eq(24).all() and d.eligible_hours.eq(24).all()
    x=natural_ready(d)
    ready=x.loc[x.ready,'timestamp']
    start=ready.iloc[0]+pd.Timedelta(days=1) if len(ready) else None
    return x,h,{**info,'new_start':str(start) if start is not None else None,
                'tradable':bool(start is not None and start<pd.Timestamp(info['end']))}

def old_directory(key,arm):
    s=catalog()[key]
    if not s['legacy']:return None
    return ROOT/s['baseline_dir'] if arm=='V3' else OLD/'accounts'/arm/'runs'/key/arm/'full'

def prepare():
    assert not R.exists(), 'Use a new output directory; never overwrite frozen results'
    old_sources=load_sources();consumed=json.loads((OLD/'inputs/consumed_files.json').read_text())
    paths=[CONTRACT,Path(__file__),PIN,Path(__file__).with_name('v3_opportunity_study_20260913.py'),
           Path(__file__).with_name('v3_opportunity_inputs_20260913.py'),Path(__file__).with_name('common.py'),
           Path(__file__).with_name('run_market.py'),Path(__file__).with_name('run_exit_state_machine_20260910.py'),
           Path(__file__).with_name('run_exit_state_history_20260910.py'),Path(__file__).with_name('build_v3_opportunity_report_20260913.py')]
    pins={str(p.relative_to(ROOT)):sha(p) for p in paths};ep=json.loads(PIN.read_text());pins[ep['engine_path']]=ep['engine_sha256'];engine()
    out=R/'inputs';out.mkdir(parents=True)
    write_json(R/'started.json',{'created_before_results_utc':str(pd.Timestamp.now(tz='UTC')),'pins':pins,
        'change':'remove_fixed_28_day_mask_only','fees_per_side':.001,'slippage_per_side':.0004,'arms':ARMS,'old_results_preserved':True})
    scope_path=OLD/'inputs/universe_scope.csv'; om=json.loads((OLD/'inputs/artifact_checksums.json').read_text())
    checked(scope_path,om['universe_scope.csv']);scope=pd.read_csv(scope_path);scope.to_csv(out/'scope.csv',index=False)
    inputs={}
    for s in old_sources.values():
        m=json.loads(checked(ROOT/s['input_meta_path'],consumed[s['input_meta_path']]).read_text())
        inputs[m['source_input_directory']]=True
    index={};consumed_now={str(scope_path.relative_to(ROOT)):sha(scope_path)}
    for src in inputs:
        p=ROOT/src;manifest=json.loads(checked(p/'checksums.json',consumed[src+'/checksums.json']).read_text())
        for rel in ['segments.csv','frames_manifest.json','scope.csv']:
            checked(p/rel,manifest[rel]);consumed_now[str((p/rel).relative_to(ROOT))]=manifest[rel]
        frames=json.loads((p/'frames_manifest.json').read_text());segs=pd.read_csv(p/'segments.csv')
        slugs=dict(zip(scope.symbol,scope.slug))
        for symbol,g in segs.groupby('symbol'):
            slug=slugs[symbol];f=frames[symbol]
            for n,row in enumerate(g.sort_values('input_start').to_dict('records'),1):
                key=f'{slug}__seg{n:03d}';old=old_sources.get(key)
                if old:assert old['segment_id']==row['segment_id'] and old['input_start']==row['input_start']
                info={**row,**(old or {}),'run_key':key,'slug':slug,'symbol':symbol,'legacy':old is not None,
                      'joint_path':str((p/f['joint_daily']['path']).relative_to(ROOT)),'joint_sha256':f['joint_daily']['sha256'],
                      'hourly_path':str((p/f['1h']['path']).relative_to(ROOT)),'hourly_sha256':f['1h']['sha256']}
                index[key]=info
                for kind in ['1h','joint_daily']:
                    rel=str((p/f[kind]['path']).relative_to(ROOT));consumed_now[rel]=f[kind]['sha256']
    assert len(scope)==680 and sum(s['legacy'] for s in index.values())==975
    for rel,digest in consumed_now.items():checked(ROOT/rel,digest)
    write_json(out/'catalog.json',index);write_json(out/'consumed_files.json',consumed_now)
    write_json(out/'completion.json',{'complete':True,'codes':len(scope),'segments':len(index),'legacy_segments':975,
        'source_packages':list(inputs),'all_quality_flags_preserved':True,'no_new_market_data':True})
    print('Inputs verified:',len(index),'segments /',len(scope),'codes',flush=True)

def verify_frozen():
    for p,d in json.loads((R/'started.json').read_text())['pins'].items():checked(ROOT/p,d)
    assert json.loads((R/'inputs/completion.json').read_text())['complete']

def one_coin(slug,keys,audit=False):
    rows=[];periods=[];ranges=[];comparisons=[];audits=[]
    if audit:from audit_v3_opportunity_20260913 import audit_run
    for key in sorted(keys):
        d,h,m=load_new(key);ranges.append({k:m[k] for k in ['run_key','slug','legacy','input_start','end','new_start','tradable']})
        if not m['tradable']:continue
        lo,hi=pd.Timestamp(m['new_start']),pd.Timestamp(m['end'])
        for arm in ARMS:
            p=R/'accounts'/key/arm
            if audit:
                rec=audit_run(p,d.set_index('timestamp',drop=False),h.set_index('timestamp',drop=False))
                audits.append({'run_key':key,'arm':arm,**rec});continue
            events=[];result=engine().simulate(h,d,config(arm),lo,hi,None,0.,entry_events=events)
            result[0].update(stats(result[1]))
            event_frame=pd.DataFrame(events).reindex(columns=list(dict.fromkeys(engine().ENTRY_EVENT_COLUMNS+engine().CANDIDATE_EVENT_COLUMNS)))
            if p.exists():
                assert json.loads((p/'summary.json').read_text())==json.loads(json.dumps(result[0],default=str))
                for name,frame in [('trades.csv',result[1]),('stops.csv',result[3])]:
                    if len(frame):assert (p/name).read_text()==frame.to_csv(index=False),(key,arm,name,'resume mismatch')
                    else:assert len(table(p/name))==0
                pd.testing.assert_frame_equal(pd.read_parquet(p/'equity.parquet'),result[2],check_exact=True)
                assert (p/'entry_events.csv').read_text()==event_frame.to_csv(index=False)
            else:
                save_result(p,result);event_frame.to_csv(p/'entry_events.csv',index=False)
            ident={'run_key':key,'slug':slug,'symbol':m['symbol'],'case_id':arm,'legacy':m['legacy'],'result_path':str(p.relative_to(ROOT))}
            rows.append({**ident,**result[0]})
            full={'block':'full_segment','status':'FULL_SEGMENT','actual_start':str(lo),'actual_end':str(hi),
                  'return_pct':result[0]['return_pct'],'max_drawdown_pct':result[0]['max_drawdown_pct']}
            for rec in [full,*time_blocks(result[2],lo,hi)]:
                if rec['status']=='NO_OVERLAP':continue
                periods.append({**ident,**rec,**trade_stats(result[1],pd.Timestamp(rec['actual_start']),pd.Timestamp(rec['actual_end']),hi)})
            oldp=old_directory(key,arm)
            if oldp:
                old=table(oldp/'trades.csv');a={(str(t.cross_day),int(t.side)):t for t in old.itertuples()}
                b={(str(t.cross_day),int(t.side)):t for t in result[1].itertuples()}
                for k in sorted(a.keys()|b.keys()):
                    ot,nt=a.get(k),b.get(k)
                    comparisons.append({**ident,'cross_day':k[0],'side':k[1],
                        'relationship':'same_entry' if ot and nt and ot.entry_time==nt.entry_time else 'shifted_entry' if ot and nt else 'new_entry' if nt else 'old_entry_missed',
                        'old_entry_time':str(ot.entry_time) if ot else None,'new_entry_time':str(nt.entry_time) if nt else None,
                        'old_return_pct':ot.return_on_entry_equity*100 if ot else None,'new_return_pct':nt.return_on_entry_equity*100 if nt else None})
    payload={'summary':rows,'periods':periods,'ranges':ranges,'entry_comparison':comparisons,'audits':audits}
    # A period with no closed trades has undefined means; JSON null preserves missingness.
    payload=json.loads(json.dumps(payload,default=str),parse_constant=lambda _:None)
    dest=R/('audit_checkpoints' if audit else 'checkpoints');write_json(dest/(slug+'.json'),payload)
    return payload

def run(audit=False,workers=4):
    verify_frozen();by={}
    for key,s in catalog().items():by.setdefault(s['slug'],[]).append(key)
    checkpoint=R/('audit_checkpoints' if audit else 'checkpoints');records=[];jobs={};start=time.monotonic();fail=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for slug,keys in by.items():
            p=checkpoint/(slug+'.json')
            if p.exists():records.append(json.loads(p.read_text()))
            else:jobs[pool.submit(one_coin,slug,keys,audit)]=slug
        for n,f in enumerate(as_completed(jobs),1):
            try:records.append(f.result())
            except Exception as exc:fail.append({'slug':jobs[f],'error':repr(exc)});print('FAILED',jobs[f],repr(exc),flush=True)
            if n%25==0 or n==len(jobs):print('AUDIT' if audit else 'REPLAY',n,'/',len(jobs),'errors',len(fail),round(time.monotonic()-start,1),'s',flush=True)
    dest=R/('audit' if audit else 'results');dest.mkdir(exist_ok=True)
    for name in (['audits'] if audit else ['summary','periods','ranges','entry_comparison']):
        pd.DataFrame([row for rec in records for row in rec[name]]).to_csv(dest/(name+'.csv'),index=False)
    write_json(dest/'completion.json',{'complete':not fail,'coins':len(records),'accounts':sum(len(rec['audits' if audit else 'summary']) for rec in records),'failures':fail,'elapsed_seconds':time.monotonic()-start})
    assert not fail,fail

def smoke():
    verify_frozen();d,h,m=load_new('HYPE__seg001');old_d,_,_,_,_=load_segment('HYPE__seg001')
    assert str(d.loc[d.ready,'timestamp'].iloc[0])=='2025-06-14 00:00:00+00:00'
    assert not d.ready.iloc[:14].any() and d.ready.iloc[14:].all()
    assert old_d.ready.iloc[:28].eq(False).all()
    for n in [14,15,18,29,90]:
        fresh=engine().enrich_features(engine().features(d.iloc[:n].drop(columns=[c for c in d.columns if c in INDICATORS])))
        for c in INDICATORS:np.testing.assert_allclose(fresh[c],d[c].iloc[:n],equal_nan=True,rtol=1e-12,atol=1e-12)
        assert natural_ready(fresh).ready.tolist()==d.ready.iloc[:n].tolist()
    first=natural_ready(d.iloc[:14]);assert not first.ready.any()
    # The unmodified engine and original readiness must still reproduce frozen trades.
    for arm in ARMS:
        expected=table(old_directory('HYPE__seg001',arm)/'trades.csv')
        res=engine().simulate(h,old_d,config(arm),pd.Timestamp(m['trade_start']),pd.Timestamp(m['end']))
        for col in ['entry_time','exit_time','side','entry_price','exit_price','net_pnl','return_on_entry_equity']:
            pd.testing.assert_series_equal(res[1][col].reset_index(drop=True),expected[col].reset_index(drop=True),check_dtype=False,check_names=False,rtol=1e-11,atol=1e-10)
    write_json(R/'smoke.json',{'complete':True,'natural_ready_day':'2025-06-14','first_allowed_open':'2025-06-15','old_hype_three_arm_trade_parity':True,'future_prefix_invariance':True,'incomplete_indicators_not_accepted':True})
    print('Smoke checks PASS',flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['prepare','smoke','run','audit']);ap.add_argument('--workers',type=int,default=4);a=ap.parse_args()
    if a.stage=='prepare':prepare()
    elif a.stage=='smoke':smoke()
    else:
        assert json.loads((R/'smoke.json').read_text())['complete']
        run(a.stage=='audit',a.workers)

if __name__=='__main__':main()
