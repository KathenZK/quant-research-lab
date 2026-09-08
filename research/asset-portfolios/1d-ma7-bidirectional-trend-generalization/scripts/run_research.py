"""冻结候选的开发选择、随后揭示验证；只消费本任务可信启动返回帧。"""
from pathlib import Path
from dataclasses import asdict, replace
import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
import time
import numpy as np
import pandas as pd
from engine import Config, CANDIDATES, features, replay, qualify

FAMILY=Path(__file__).resolve().parents[1]
INPUT=FAMILY/'artifacts/p0-inputs-20260908'
FEATURES=('relative60','liquidity90','atr_pct','er30','age_days','momentum60','slow_slope','ma30','market_state')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(x) for x in value]
    if isinstance(value,(float,np.floating)):return float(value) if math.isfinite(value) else None
    if isinstance(value,(np.integer,)):return int(value)
    if isinstance(value,(np.bool_,)):return bool(value)
    if isinstance(value,(pd.Timestamp,np.datetime64)):return str(value)
    if isinstance(value,np.ndarray):return clean(value.tolist())
    return value

def save(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def compressed(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(p,'wt') as h:json.dump(clean(value),h,separators=(',',':'),allow_nan=False)

def read_frame(symbol,manifest):
    m=manifest[symbol];p=INPUT/m['path'];assert sha(p)==m['sha256'],'returned frame changed'
    f=pd.read_pickle(p,compression='gzip')
    assert hashlib.sha256(pd.util.hash_pandas_object(f,index=True).values.tobytes()).hexdigest()==m['dataframe_hash']
    return f

def groups(symbol,manifest,btc=None):
    f=read_frame(symbol,manifest)
    return [features(g,btc) for _,g in f.loc[f.eligible].groupby('research_segment_id',sort=False) if len(g)>=122]

def btc_reference(manifest):
    frames=groups('BTC/USDT:USDT',manifest)
    out=[]
    for f in frames:
        ma=f.close.rolling(120).mean()
        f['market_state']=np.where((f.close>ma)&(f.momentum60>0),'BULL',np.where((f.close<ma)&(f.momentum60<0),'BEAR','MIXED'))
        out.append(f.set_index('ts')[['momentum60','market_state']])
    return pd.concat(out).sort_index()

def clip(g,a,b):
    end=int(g.ts.searchsorted(b));start=max(121,int(g.ts.searchsorted(a)))
    if end-start<30:return None
    # Retain full past segment for Wilder recursion; start_idx prohibits warmup trades.
    f=g.iloc[:end].reset_index(drop=True)
    full=bool(f.ts.iloc[start]==a and f.ts.iloc[-1]+pd.Timedelta(days=1)==b)
    return f,start,full

def windows(gs,stage,fold):
    if stage=='development':
        a=pd.Timestamp('2020-01-01',tz='UTC');b=pd.Timestamp('2024-01-01',tz='UTC')
        possible=[x for g in gs if (x:=clip(g,a,b)) is not None and len(x[0])-x[1]>=365]
        if possible:
            f,i,full=sorted(possible,key=lambda x:(-(len(x[0])-x[1]),x[0].ts.iloc[x[1]]))[0]
            yield 'development',f,i,full
        return
    for g in gs:
        if len(g)>=151:yield 'available_segment',g,121,False
        for year in range(2020,2027):
            a=pd.Timestamp(f'{year}-01-01',tz='UTC');b=min(pd.Timestamp(f'{year+1}-01-01',tz='UTC'),pd.Timestamp('2026-09-05',tz='UTC'))
            result=clip(g,a,b)
            if result is not None:yield str(year),*result
        a=pd.Timestamp('2024-12-05',tz='UTC');b=pd.Timestamp('2026-09-05',tz='UTC')
        result=clip(g,a,b)
        if result is not None and result[2]:yield 'main',*result
        for label,a,b in [('middle','2024-01-01','2025-01-01'),('held','2025-01-01','2026-09-05')]:
            result=clip(g,pd.Timestamp(a,tz='UTC'),pd.Timestamp(b,tz='UTC'))
            if result is not None:yield label,*result

def trade_rows(result,f,common):
    rows=[]
    for t in result['trades']:
        j=t['signal_idx'];rows.append({**common,**t,**{k:f[k].iloc[j] for k in FEATURES}})
    return rows

def run_one(f,start,common,candidate,store_path=False):
    cfg=Config(candidate);results={}
    for scenario,fee,slip in [('default',.001,.0004),('gross',0.,0.),('stress',.001,.0008)]:
        results[scenario]=replay(f,replace(cfg,fee=fee,slip=slip),start_idx=start)
    base=results['default'];q=qualify(base,results['stress']['metrics']['return_pct'])
    row={**common,'candidate':candidate,**base['metrics'],'cagr_pct':q['cagr_pct'],
        'strict':q['strict_without_stress'],'failed_gates':','.join(k for k,v in q['gates'].items() if not v),
        **{f'third{i+1}_return':x for i,x in enumerate(q['third_returns'])},
        'gross_return_pct':results['gross']['metrics']['return_pct'],'stress_return_pct':results['stress']['metrics']['return_pct']}
    assert math.prod(t['equity_after']/t['equity_before'] for t in base['trades'])==pytest_approx(base['nav'][-1])
    return row,trade_rows(base,f,{**common,'candidate':candidate}),base

class pytest_approx:
    def __init__(self,value):self.value=value
    def __eq__(self,other):return math.isclose(self.value,other,abs_tol=1e-10,rel_tol=1e-11)

def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['development','evaluation']);p.add_argument('--run-id');p.add_argument('--selection-dir',default='p1-development-20260908-r1');args=p.parse_args()
    run_id=args.run_id or f'p1-{args.stage}-20260908';out=FAMILY/'artifacts'/run_id
    assert not out.exists(),'retained run exists'
    manifest=json.loads((INPUT/'frame-manifest.json').read_text());universe=json.loads((FAMILY/'specs/observed-universe-20260908.json').read_text())
    selected=None
    if args.stage=='evaluation':
        lock=FAMILY/'artifacts'/args.selection_dir/'selection-lock.json'
        selected=json.loads(lock.read_text())['selected_bidirectional_candidate']
    save(out/'started.json',{'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'stage':args.stage,
        'contract_sha256':sha(FAMILY/'specs/research-contract-p1-20260908.md'),
        'input_manifest_sha256':sha(INPUT/'frame-manifest.json'),
        'source_sha256':{p.name:sha(p) for p in (FAMILY/'scripts').glob('*.py')},'selected':selected})
    btc=btc_reference(manifest);rows=[];trades=[];recent=[];beg=time.time();count=0
    for symbol in sorted(manifest):
        fold=int.from_bytes(hashlib.sha256(symbol.encode()).digest()[:8],'big')%100;cls=universe[symbol]
        if args.stage=='development' and (fold>=60 or cls!='COIN'):continue
        gs=groups(symbol,manifest,btc)
        for label,f,start,full in windows(gs,args.stage,fold):
            common={'symbol':symbol,'asset_class':cls,'asset_fold':fold,'window':label,
                'segment_id':str(f.research_segment_id.iloc[0]),'first':str(f.ts.iloc[start]),'last':str(f.ts.iloc[-1]),
                'n_bars':len(f)-start,'full_requested_window':full,
                'run_id':f'{symbol}|{label}|{f.ts.iloc[start].date()}|{f.ts.iloc[-1].date()}',
                'ended_before_cutoff':f.ts.iloc[-1]<pd.Timestamp('2026-09-04',tz='UTC')}
            paths={}
            for candidate in CANDIDATES:
                row,tt,r=run_one(f,start,common,candidate);rows.append(row);trades.extend(tt)
                if label=='main':
                    paths[candidate]=r
                    for days in [1,7,30,90,180,365]:
                        end=len(f)-1;j=max(start-1,end-days);anchor=r['nav'][j]
                        recent.append({**common,'candidate':candidate,'requested_days':days,'actual_days':end-j,
                            'return_pct':100*(r['nav'][-1]/anchor-1) if anchor>0 else None,
                            'exits':sum(t['exit_idx']>j for t in r['trades'])})
            if paths:
                compressed(out/'main-paths'/f'{symbol.split("/")[0]}.json.gz',{'common':common,
                    'bars':f[['ts','open','high','low','close','ma7','atr14','quote_volume']].to_dict('records'),'runs':paths})
        count+=1
        if count%25==0:print(args.stage,count,'symbols',len(rows),'replays',round(time.time()-beg),'seconds',flush=True)
    df=pd.DataFrame(rows);df.to_csv(out/'results.csv',index=False)
    pd.DataFrame(trades).to_csv(out/'trades.csv.gz',index=False,compression='gzip')
    pd.DataFrame(recent).to_csv(out/'recent-slices.csv',index=False)
    summaries=[]
    for keys,g in df.groupby(['asset_class','window','candidate']):
        summaries.append(dict(zip(['asset_class','window','candidate'],keys),n=len(g),positive=int((g.return_pct>0).sum()),
            strict=int(g.strict.sum()),positive_fraction=float((g.return_pct>0).mean()),strict_fraction=float(g.strict.mean()),
            median_return_pct=float(g.return_pct.median()),median_mdd_pct=float(g.mdd_pct.median()),mean_trades=float(g.n_trades.mean())))
    summary=pd.DataFrame(summaries);summary.to_csv(out/'summary.csv',index=False)
    if args.stage=='development':
        eligible=summary[summary.candidate.isin(['B2','B3','C0','C1','C2','C3','C4','C5'])].sort_values(
            ['strict_fraction','positive_fraction','median_return_pct','mean_trades','candidate'],ascending=[False,False,False,True,True])
        assert len(eligible)==8 and eligible.n.nunique()==1
        chosen=eligible.iloc[0].candidate
        save(out/'selection-lock.json',{'locked_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'selected_bidirectional_candidate':chosen,'reason':'predeclared lexicographic development ranking',
            'ranking':eligible.to_dict('records'),'result_sha256':sha(out/'results.csv'),
            'contract_sha256':sha(FAMILY/'specs/research-contract-p1-20260908.md'),
            'disclosure_scope':'development lock for this replay; prior runs and historical results may already be revealed; never assume blind validation',
            'historical_status':'ITERATIVE_REUSED_DIAGNOSTIC; no claim of blind OOS'})
        print('LOCKED',chosen,flush=True)
    save(out/'completed.json',{'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'seconds':time.time()-beg,
        'symbols_processed':count,'replay_rows':len(df),'trade_rows':len(trades),'status':'COMPLETED_RESEARCH_REPLAYS_NOT_PROMOTION',
        'results_sha256':sha(out/'results.csv'),'trades_sha256':sha(out/'trades.csv.gz')})
    print('DONE',out,flush=True)

if __name__=='__main__':main()
