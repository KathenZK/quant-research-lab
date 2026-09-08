"""Full-market causal direction/reversal audit through the frozen startup API."""
from pathlib import Path
import argparse, datetime as dt, gzip, hashlib, json, math, sys, time
import numpy as np
import pandas as pd
import baseline_engine as baseline
from engine import execute, gross_oracle, VARIANTS, drawdown

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from strategy_lab.data.research_bundle import require_research_startup
from strategy_lab.data.research_inputs import complete_window_mask
CONTRACT=ROOT/'specs/contract-20260908.json'
OUT=ROOT/'artifacts/20260908'
DAY=86400000


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def compressed(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,'wt',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def load_inputs(request):
    return require_research_startup(request,project_root=PROJECT)


def batches(symbols,base,label):
    request=dict(base,symbols=symbols)
    save(OUT/'startup-requests'/f'{label}.json',request)
    try:
        inputs=load_inputs(request)
    except (ValueError,AssertionError) as exc:
        save(OUT/'startup-failures'/f'{label}.json',dict(symbols=symbols,error=str(exc),no_fallback=True))
        if len(symbols)==1:
            yield symbols[0],None,str(exc)
        else:
            m=len(symbols)//2
            yield from batches(symbols[:m],base,label+'L')
            yield from batches(symbols[m:],base,label+'R')
        return
    save(OUT/'startup-reports'/f'{label}.json',inputs.report)
    for symbol,f in inputs.prices.items():
        yield symbol,f,None


def bars_from_frame(f):
    return [dict(ts=int(r.ts.value//1000000),end_ts=int(r.ts.value//1000000)+DAY-1,
        open=float(r.open),high=float(r.high),low=float(r.low),close=float(r.close)) for r in f.itertuples()]


def verify_run(bars,r,mask):
    assert len(r['nav'])==len(bars)
    assert all(e['i']==e['signal_idx']+1 and mask[e['signal_idx']] for e in r['events'] if e['action']=='entry')
    assert math.isclose(math.prod(t['equity_after']/t['equity_before'] for t in r['trades']),r['nav'][-1],abs_tol=1e-10,rel_tol=1e-12)
    assert all(t['entry_idx']<=t['exit_idx'] for t in r['trades'])
    if r['metrics']['bankrupt']:
        z=next(i for i,x in enumerate(r['nav']) if x==0)
        assert all(x==0 for x in r['nav'][z:])
    for t in r['trades']:
        assert math.isclose(t['entry_fee'],t['units']*t['entry_price']*r['fee'],rel_tol=1e-12,abs_tol=1e-12)
        st=r['active_stops'][t['entry_idx']:t['exit_idx']]
        assert all(t['side']*(y-x)>=-1e-12 for x,y in zip(st,st[1:]))


def run_segment(symbol,cls,window,f,a,b,c,prior,deep):
    f=f.reset_index(drop=True)
    assert f.eligible.all() and f.ts.diff().dropna().eq(pd.Timedelta(days=1)).all()
    bars=bars_from_frame(f);ma,atr,tr,slope=baseline.indicators(bars)
    mask=(complete_window_mask(f,backward=15,forward=0)&f.research_window_valid).tolist()
    ident='|'.join([window,symbol,baseline.iso(bars[0]['ts']),baseline.iso(bars[-1]['ts'])])
    close=np.array([x['close'] for x in bars]);rat=close[1:]/close[:-1]
    flags=bool(((rat>4)|(rat<.25)).any() or any(x['high']/x['low']>10 for x in bars) or np.nanmax(np.array(atr,dtype=float)/close)>.5)
    common=dict(run_id=ident,symbol=symbol,coin=symbol.split('/')[0],asset_class=cls,window=window,
        start=baseline.iso(bars[0]['ts']),end=baseline.iso(bars[-1]['ts']),n_bars=len(bars),
        full_requested_window=f.ts.iloc[0]==a and f.ts.iloc[-1]+pd.Timedelta(days=1)==b,
        reaches_global_cutoff=f.ts.iloc[-1]==pd.Timestamp('2026-09-04',tz='UTC'),
        economic_flag=flags,buyhold_return_pct=(close[-1]/close[0]-1)*100,
        buyhold_mdd_pct=drawdown([x/close[0] for x in close]),representative=False)
    if common['full_requested_window']:cohort='full'
    elif not common['reaches_global_cutoff']:cohort='ended'
    elif len(bars)>=180:cohort='partial_180plus'
    else:cohort='short_30_179'
    common['cohort']=cohort
    rows=[];default={};all_trades=[];max_err=0.
    for variant in VARIANTS:
        scenarios={}
        for name,cost in c['costs'].items():
            r=execute(bars,variant,fee=cost['fee'],slip=cost['slip'],valid_mask=mask,indicator_override=(ma,atr,tr,slope))
            r['fee']=cost['fee'];r['slip']=cost['slip'];verify_run(bars,r,mask)
            if variant=='long':
                old=baseline.execute(bars,mode='causal',fee=cost['fee'],slip=cost['slip'],indicator_override=(ma,atr,tr,slope))
                err=max(abs(x-y) for x,y in zip(old['nav'],r['nav']));max_err=max(max_err,err)
                assert err<=1e-10,(ident,name,err)
                assert [(t['entry_idx'],t['exit_idx'],t['entry_price'],t['exit_price']) for t in old['trades']]==[(t['entry_idx'],t['exit_idx'],t['entry_price'],t['exit_price']) for t in r['trades']]
                col={'gross':'gross_return_pct','default':'cost_return_pct','stress':'stress_return_pct'}[name]
                assert abs(r['metrics']['return_pct']-prior[ident][col])<1e-8,(ident,name,'previous result drift')
            if deep and name=='gross':
                tape,nav=gross_oracle(bars,variant)
                actual=[(t['entry_idx'],t['exit_idx'],t['side'],t['entry_price'],t['exit_price']) for t in r['trades']]
                assert len(actual)==len(tape),(ident,variant,'oracle trade count')
                assert all(x[:3]==y[:3] for x,y in zip(actual,tape)),(ident,variant,'oracle timing/side')
                assert all(abs(x[k]-y[k])<=1e-10 for x,y in zip(actual,tape) for k in [3,4]),(ident,variant,'oracle fill')
                assert np.allclose(nav,r['nav'],rtol=1e-12,atol=1e-10)
                live=execute(bars,variant,force_end=False)
                for k in sorted(set([min(30,len(bars)-1),len(bars)//2,len(bars)-1])):
                    p=execute(bars[:k],variant,force_end=False)
                    assert p['nav']==live['nav'][:k]
                    assert p['events']==[e for e in live['events'] if e['i']<k]
            scenarios[name]=r
        default[variant]=scenarios['default']
        row=dict(common,variant=variant,**scenarios['default']['metrics'])
        for name in ['gross','stress']:
            row.update({f'{name}_{k}':v for k,v in scenarios[name]['metrics'].items() if k in ['return_pct','mdd_pct','bankrupt','n_trades']})
        rows.append(row)
        for t in default[variant]['trades']:
            all_trades.append(dict(run_id=ident,symbol=symbol,asset_class=cls,window=window,variant=variant,economic_flag=flags,**t))
    chart=dict(common=common,bars=bars,ma=ma,atr=atr,valid_mask=mask,runs=default)
    return rows,all_trades,chart,max_err


def main():
    global OUT
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='20260908');args=parser.parse_args()
    assert args.run_id and '/' not in args.run_id and '..' not in args.run_id
    OUT=ROOT/'artifacts'/args.run_id
    assert not (OUT/'summary.json').exists() and not (OUT/'run-started.json').exists(),'Retained run exists; use a new --run-id'
    c=json.loads(CONTRACT.read_text())
    hashes=json.loads((ROOT/'specs/baseline-reference-hashes.json').read_text())
    for p,sha in hashes.items():assert hashlib.sha256((PROJECT/p).read_bytes()).hexdigest()==sha
    assert hashlib.sha256((ROOT/'scripts/baseline_engine.py').read_bytes()).hexdigest()==c['baseline_engine_sha256']
    prior_path=PROJECT/'research/asset-portfolios/1d-ma7-atr14-long-transfer/artifacts/full-market-20260908/all-window-results.csv'
    prior={r['run_id']:r for r in pd.read_csv(prior_path).to_dict('records')}
    started=time.time();save(OUT/'run-started.json',dict(time_utc=dt.datetime.now(dt.timezone.utc).isoformat(),contract_sha256=hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),scripts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'scripts').glob('*.py')}))
    windows={k:(pd.Timestamp(a,tz='UTC'),pd.Timestamp(b,tz='UTC')) for k,(a,b) in c['windows'].items()}
    symbols=c['requested_symbols'];rows=[];history_trades=[];main_trades=[];inventory=[];checks=[];recent=[];counter=0
    for offset in range(0,len(symbols),48):
        print('START batch',offset//48+1,flush=True)
        for symbol,f,error in batches(symbols[offset:offset+48],c['request_base'],f'b{offset//48+1:02d}'):
            counter+=1;cls=c['universe_inventory'][symbol];coin=symbol.split('/')[0]
            if f is None:
                inventory.append(dict(symbol=symbol,asset_class=cls,status='STARTUP_FAILED',error=error));continue
            inv=dict(symbol=symbol,asset_class=cls,status='INPUT_VERIFIED',observed_rows=len(f),eligible_bars=int(f.eligible.sum()),ineligible_rows=int((~f.eligible).sum()),valid_segments=0,main_available=False,
                     validated_frame_pandas_hash=hashlib.sha256(pd.util.hash_pandas_object(f,index=True).values.tobytes()).hexdigest())
            deep=False;count=0;err=0.;full_paths=[]
            for window,(a,b) in windows.items():
                cut=f.loc[f.ts.ge(a)&f.ts.lt(b)];valid=[]
                for segment,g in cut.groupby('research_segment_id',sort=False):
                    if len(g)<30:continue
                    rr,tt,chart,e=run_segment(symbol,cls,window,g,a,b,c,prior,not deep)
                    deep=True;count+=1;err=max(err,e);valid.append((rr,tt,chart));rows.extend(rr)
                    if window=='full_history':
                        inv['valid_segments']+=1;history_trades.extend(tt)
                        full_paths.append(chart)
                if valid:
                    rr,tt,chart=valid[-1]
                    for row in rr:row['representative']=True
                    chart['common']['representative']=True
                    if window=='main':
                        inv['main_available']=True;compressed(OUT/'main-replays'/f'{coin}.json.gz',chart);main_trades.extend(tt)
                        for variant,r in chart['runs'].items():
                            for days in [1,7,30,90,180,365]:
                                j=max(0,len(chart['bars'])-1-days);anchor=r['nav'][j]
                                recent.append(dict(symbol=symbol,asset_class=cls,variant=variant,requested_days=days,actual_days=len(chart['bars'])-1-j,
                                    start=baseline.iso(chart['bars'][j]['ts']),end=chart['common']['end'],reaches_global_cutoff=chart['common']['reaches_global_cutoff'],
                                    return_pct=(r['nav'][-1]/anchor-1)*100 if anchor>0 else None,
                                    status='ALREADY_BANKRUPT' if anchor==0 else 'OK',entries=sum(e['action']=='entry' and e['i']>j for e in r['events']),exits=sum(t['exit_idx']>j for t in r['trades'])))
            if not deep:inv['status']='INSUFFICIENT_30_BAR_SEGMENT'
            if full_paths:compressed(OUT/'full-history-replays'/f'{coin}.json.gz',full_paths)
            inventory.append(inv);checks.append(dict(symbol=symbol,segment_windows=count,long_baseline_max_nav_error=err,all_four_independent_gross_oracles_and_prefix=deep))
            if counter%24==0:print('PROGRESS',counter,'/',len(symbols),'rows',len(rows),'seconds',round(time.time()-started),flush=True)
        save(OUT/'progress.json',dict(processed=counter,rows=len(rows),seconds=time.time()-started))
    pd.DataFrame(rows).to_csv(OUT/'all-window-results.csv.gz',index=False,compression='gzip')
    pd.DataFrame(history_trades).to_csv(OUT/'full-history-trades.csv.gz',index=False,compression='gzip')
    pd.DataFrame(main_trades).to_csv(OUT/'main-window-trades.csv.gz',index=False,compression='gzip')
    pd.DataFrame(recent).to_csv(OUT/'recent-slices.csv.gz',index=False,compression='gzip')
    pd.DataFrame(inventory).to_csv(OUT/'coverage-ledger.csv',index=False)
    save(OUT/'validation.json',dict(checks=checks,baseline_reference_files_unchanged=True,original_input_readers_unchanged=True))
    assert len(rows)//4==len(prior),(len(rows),len(prior))
    save(OUT/'summary.json',dict(status='COMPLETED_PRICE_DIAGNOSTIC',requested_symbols=len(symbols),input_verified=sum(x['status']!='STARTUP_FAILED' for x in inventory),usable_symbols=sum(x['status']=='INPUT_VERIFIED' for x in inventory),main_symbols=sum(x.get('main_available',False) for x in inventory),variant_window_rows=len(rows),cost_scenario_replays=len(rows)*3,full_history_trades=len(history_trades),elapsed_seconds=time.time()-started,
        max_baseline_nav_error=max(x['long_baseline_max_nav_error'] for x in checks),variants=list(VARIANTS),funding_included=False))
    manifest={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file()}
    save(OUT/'run-manifest.json',manifest)
    print('DONE',len(rows),'variant windows',len(history_trades),'full-history trades',flush=True)


if __name__=='__main__':main()
