"""已锁候选的固定筛选、反手/方向、成本、延迟和参数邻域真实回放。"""
from dataclasses import replace,asdict
from pathlib import Path
import datetime as dt
import argparse
import gzip
import json
import math
import time
import numpy as np
import pandas as pd
from engine import Config,FILTERS,replay,qualify
from run_research import FAMILY,INPUT,sha,save,compressed,groups,btc_reference,windows,clean,trade_rows

def variants(candidate):
    base=Config(candidate)
    result={'unfiltered':base,'long_only':replace(base,direction=1),'short_only':replace(base,direction=-1),
        'half_size':replace(base,size=.5),'delay_t2':replace(base,delay=2)}
    if candidate!='C0' and not candidate.startswith('B'):
        result.update({'band_0.125':replace(base,band=.125),'band_0.5':replace(base,band=.5),
                       'initial_1.5':replace(base,initial_atr=1.5),'initial_2.5':replace(base,initial_atr=2.5)})
    if candidate in ('C4','C5'):
        result.update({'trail_2':replace(base,trail_atr=2),'trail_4':replace(base,trail_atr=4)})
    result.update({name:replace(base,filter_name=name,direction=-1 if name in ('low_er_short','liquid_short') else 0) for name in FILTERS})
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='p2-applicability-20260908-r2');parser.add_argument('--selection-dir',default='p1-development-20260908-r1');args=parser.parse_args()
    out=FAMILY/'artifacts'/args.run_id;assert not out.exists()
    lockpath=FAMILY/'artifacts'/args.selection_dir/'selection-lock.json';lock=json.loads(lockpath.read_text())
    candidate=lock['selected_bidirectional_candidate'];configs=variants(candidate)
    manifest=json.loads((INPUT/'frame-manifest.json').read_text());universe=json.loads((FAMILY/'specs/observed-universe-20260908.json').read_text())
    save(out/'started.json',{'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'selection_lock_sha256':sha(lockpath),
        'candidate':candidate,'configs':{k:asdict(v) for k,v in configs.items()},'script_sha256':sha(Path(__file__)),
        'contract_sha256':sha(FAMILY/'specs/research-contract-p1-20260908.md'),'no_new_selection':True})
    btc=btc_reference(manifest);rows=[];alltrades=[];monthrows=[];beg=time.time();count=0
    for symbol in sorted(manifest):
        cls=universe[symbol]
        if cls!='COIN':continue
        import hashlib
        fold=int.from_bytes(hashlib.sha256(symbol.encode()).digest()[:8],'big')%100
        gs=groups(symbol,manifest,btc)
        ws=list(windows(gs,'evaluation',fold))
        if fold<60:ws.extend(windows(gs,'development',fold))
        for label,f,start,full in ws:
            relevant=label=='main' or label=='development' or (label=='middle' and 60<=fold<80) or (label=='held' and fold>=80)
            if not relevant:continue
            common={'symbol':symbol,'asset_class':cls,'asset_fold':fold,'window':label,'full_requested_window':full,
                'segment_id':str(f.research_segment_id.iloc[0]),'first':str(f.ts.iloc[start]),'last':str(f.ts.iloc[-1]),
                'n_bars':len(f)-start,'run_id':f'{symbol}|{label}|{f.ts.iloc[start].date()}|{f.ts.iloc[-1].date()}'}
            for variant,cfg in configs.items():
                r=replay(f,cfg,start_idx=start);stress=replay(f,replace(cfg,slip=.0008),start_idx=start)
                q=qualify(r,stress['metrics']['return_pct']);m=r['metrics']
                rows.append({**common,'candidate':candidate,'variant':variant,**m,'strict':q['strict_without_stress'],
                    'cagr_pct':q['cagr_pct'],'stress_return_pct':stress['metrics']['return_pct'],
                    'failed_gates':','.join(k for k,v in q['gates'].items() if not v),
                    **{f'third{i+1}_return':v for i,v in enumerate(q['third_returns'])}})
                alltrades.extend(trade_rows(r,f,{**common,'candidate':candidate,'variant':variant}))
                nav=np.array(r['nav']);prev=1.
                sub=pd.DataFrame({'ts':f.ts.iloc[start:].to_numpy(),'nav':nav[start:]})
                sub['month']=pd.DatetimeIndex(sub.ts).strftime('%Y-%m')
                for month,g in sub.groupby('month',sort=True):
                    end=float(g.nav.iloc[-1]);monthrows.append({**common,'variant':variant,'month':month,'month_return':end/prev-1 if prev>0 else -1});prev=end
        count+=1
        if count%50==0:print('applicability',count,'symbols',len(rows),'replays',round(time.time()-beg),'seconds',flush=True)
    pd.DataFrame(rows).to_csv(out/'results.csv',index=False)
    pd.DataFrame(alltrades).to_csv(out/'trades.csv.gz',index=False,compression='gzip')
    pd.DataFrame(monthrows).to_csv(out/'monthly-returns.csv.gz',index=False,compression='gzip')
    save(out/'completed.json',{'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'seconds':time.time()-beg,
        'configs':len(configs),'rows':len(rows),'trades':len(alltrades),'result_sha256':sha(out/'results.csv')})
    print('DONE',out,flush=True)

if __name__=='__main__':main()
