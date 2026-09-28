"""Frozen all-coin exit experiments and equal-entry episode comparisons."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd
from common import BASE, INPUT, RESULTS, ROOT, sha, write_json
from run_market import load_selected_frames, select_scope, verify_inputs, save_result
from run_four_tests_20260910 import verify_reused, enrich_and_check

ROUND = BASE / 'artifacts/state_machine_20260910'
PIN = BASE / 'specs/exit-state-engine-pin-20260910.json'
OUT = ROUND / 'results_current'


def load_engine():
    pin = json.loads(PIN.read_text()); path = ROOT / pin['engine_path']
    assert sha(path) == pin['engine_sha256']
    name = 'ma7_exit_state_frozen_v3'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod)
    return sys.modules[name]


def cases():
    e = load_engine()
    base = e.Config(reverse=False, progress_days=4, fee=.001, slip=.0004)
    return [('V3', 'V3新成本基准', base),
            ('S1_DEFENSE', '失败与回撤防守', replace(base, exit_state_policy='defense')),
            ('S2_TREND', '防守加健康暂停', replace(base, exit_state_policy='trend')),
            ('S3_EXTENSION', '防守健康加延伸保护', replace(base, exit_state_policy='extension', short_exit='none'))]


def stats(trades):
    if not len(trades):
        return {'terminal_trades': 0, 'average_win': None, 'average_loss': None, 'payoff_ratio': None,
                'expectancy_cash': None, 'worst_trade_pct': None, 'top5_winners_share_pct': None}
    pnl = trades.net_pnl; win = pnl[pnl > 0]; loss = -pnl[pnl < 0]
    return {'terminal_trades': int(trades.exit_reason.eq('sample_end').sum()),
            'average_win': float(win.mean()) if len(win) else None,
            'average_loss': float(loss.mean()) if len(loss) else None,
            'payoff_ratio': float(win.mean()/loss.mean()) if len(win) and len(loss) else None,
            'expectancy_cash': float(pnl.mean()),
            'average_trade_pct': float(trades.return_on_entry_equity.mean()*100),
            'worst_trade_pct': float(trades.return_on_entry_equity.min()*100),
            'top5_winners_share_pct': float(win.nlargest(5).sum()/win.sum()*100) if len(win) else None}


def account(e, path, h, d, cfg, lo, hi, carry=0.):
    events=[]; r=e.simulate(h,d,cfg,lo,hi,None,carry,entry_events=events)
    assert pd.Timestamp(r[0]['start']) == lo and pd.Timestamp(r[0]['end_exclusive']) == hi
    r[0].update(stats(r[1])); save_result(path,r)
    pd.DataFrame(events).reindex(columns=e.ENTRY_EVENT_COLUMNS).to_csv(path/'entry_events.csv',index=False)
    return r


def one_coin(item, manifests, out_string):
    out=Path(out_string); h, old, sources=load_selected_frames(item,manifests)
    e=load_engine(); d=enrich_and_check(e,old); lo=pd.Timestamp(item['trade_start']);hi=pd.Timestamp(item['end'])
    identity={k:item[k] for k in ['symbol','slug','cohort','trade_days']}
    write_json(out/'inputs_used'/(item['slug']+'.json'),{**item,'source':sources,'features_old_columns_exact':True})
    rows=[]; stress=[]; baseline=None
    for cid,label,cfg in cases():
        r=account(e,out/'runs'/item['slug']/cid/'full',h,d,cfg,lo,hi)
        rows.append({**identity,'case_id':cid,'label':label,'window':'full',**r[0]})
        if cid=='V3': baseline=r[1].copy()
        del r
        for scenario,altered,carry in [('slippage_10bp',replace(cfg,slip=.001),0.),('carry_5bp_day',cfg,.0005)]:
            r=account(e,out/'sensitivity'/item['slug']/cid/scenario,h,d,altered,lo,hi,carry)
            stress.append({**identity,'case_id':cid,'scenario':scenario,**r[0]})
            del r
    episode_rows=[]
    for cid,label,cfg in cases()[1:]:
        counter=[]; changes=[]
        for base in baseline.to_dict('records'):
            r=e.simulate(h,d,cfg,start=pd.Timestamp(base['entry_time']),end=hi,fixed_episode=base)
            assert len(r[1])==1, 'Fixed original entry did not yield exactly one trade'
            tr=r[1].iloc[0].to_dict()
            for key in ['entry_time','entry_reference','entry_price','entry_equity','entry_fee','qty','side','initial_stop']:
                assert tr[key]==base[key], f'Fixed entry mismatch {key}: {tr[key]} != {base[key]}'
            tr.update(source_trade_id=int(base['trade_id']),case_id=cid,
                      baseline_exit_time=base['exit_time'],baseline_exit_reason=base['exit_reason'],
                      baseline_net_pnl=base['net_pnl'],baseline_return=base['return_on_entry_equity'],
                      delta_net_pnl=tr['net_pnl']-base['net_pnl'],
                      delta_return=tr['return_on_entry_equity']-base['return_on_entry_equity'],
                      either_terminal=tr['exit_reason']=='sample_end' or base['exit_reason']=='sample_end')
            counter.append(tr)
            stops=r[3].copy();stops['source_trade_id']=int(base['trade_id']);changes.append(stops)
        path=out/'fixed_entries'/item['slug']/cid;path.mkdir(parents=True,exist_ok=False)
        ct=pd.DataFrame(counter);ct.to_csv(path/'trades.csv',index=False)
        (pd.concat(changes,ignore_index=True) if changes else pd.DataFrame()).to_parquet(path/'stops.parquet',index=False,compression='zstd')
        summary={**identity,'case_id':cid,'pairs':len(ct),'fixed_entry_fields_exact':True,
                 'improved':int(ct.delta_net_pnl.gt(1e-9).sum()) if len(ct) else 0,
                 'worsened':int(ct.delta_net_pnl.lt(-1e-9).sum()) if len(ct) else 0,
                 'equal':int(ct.delta_net_pnl.abs().le(1e-9).sum()) if len(ct) else 0,
                 'either_terminal':int(ct.either_terminal.sum()) if len(ct) else 0,
                 'delta_cash_sum':float(ct.delta_net_pnl.sum()) if len(ct) else 0,
                 'delta_return_mean_pct':float(ct.delta_return.mean()*100) if len(ct) else None}
        episode_rows.append(summary);write_json(path/'summary.json',summary)
    result={'summary':rows,'stress':stress,'fixed':episode_rows}
    write_json(out/'checkpoints'/(item['slug']+'.json'),result)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=4);ap.add_argument('--output',type=Path,default=OUT)
    ap.add_argument('--resume',action='store_true');args=ap.parse_args();out=args.output.resolve()
    verify_inputs();oldpins=verify_reused();pin=json.loads(PIN.read_text())
    for name in ['strategy_contract_pin.json','cost_amendment_pin.json']:
        p=json.loads((ROUND/name).read_text());assert sha(ROOT/p['path'])==p['sha256']
    assert pin['fee']==.001 and pin['slip']==.0004
    source_pins={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),PIN,INPUT/'checksums.json']}
    scope=select_scope();frames=json.loads((INPUT/'frames_manifest.json').read_text())
    if out.exists():
        assert args.resume,'Existing results require explicit resume, never overwrite'
        old=json.loads((out/'run_manifest.json').read_text());assert old['source_pins']==source_pins
    else:
        out.mkdir(parents=True)
        scope.to_csv(out/'scope.csv',index=False)
        write_json(out/'run_manifest.json',{'created_utc':str(pd.Timestamp.now(tz='UTC')),
            'source_pins':source_pins,'engine_pin':pin,'old_control_pins':oldpins,
            'fee':.001,'slip':.0004,'cases':[{'case_id':cid,'label':label,'config':asdict(c)} for cid,label,c in cases()],
            'classification':'REVEALED_PRICE_DIAGNOSTIC','funding_window_verified':False,
            'old_v3_rerun_reason':'new_user_costs_change_profit_gates','expected_accounts':7332})
    pending=[];results=[];failures=[]
    for item in scope[scope.cohort.ne('excluded')].to_dict('records'):
        path=out/'checkpoints'/(item['slug']+'.json')
        if path.exists():results.append(json.loads(path.read_text()))
        else:pending.append(item)
    start=time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs={pool.submit(one_coin,it,{'main/'+it['symbol']:frames['main/'+it['symbol']]},str(out)):it for it in pending}
        for n,future in enumerate(as_completed(jobs),1):
            it=jobs[future]
            try:results.append(future.result())
            except Exception as exc:
                failures.append({'symbol':it['symbol'],'error':repr(exc)});print('FAILED',it['symbol'],repr(exc),flush=True)
                write_json(out/'execution_failures.json',failures)
            if n%10==0 or n==len(jobs): print(f'Coins {n}/{len(jobs)}, errors {len(failures)}, elapsed {time.monotonic()-start:.1f}s',flush=True)
    for key in ['summary','stress','fixed']:
        table=pd.DataFrame([x for r in results for x in r[key]])
        table.sort_values(['symbol','case_id']).to_csv(out/(key+'.csv'),index=False)
    write_json(out/'execution_failures.json',failures)
    manifest={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ['artifact_checksums.json','completion.json']}
    write_json(out/'artifact_checksums.json',manifest)
    write_json(out/'completion.json',{'complete':len(results)==611 and not failures,'coins':len(results),
        'accounts':sum(len(r['summary'])+len(r['stress']) for r in results),'fixed_pairs':sum(x['pairs'] for r in results for x in r['fixed']),
        'elapsed_seconds':time.monotonic()-start,'manifest_sha256':sha(out/'artifact_checksums.json')})
    assert not failures and len(results)==611

if __name__=='__main__':main()
