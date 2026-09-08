"""Run the frozen seven-asset transfer using the Lab verified input bundle only."""
from pathlib import Path
import argparse,ast,csv,datetime as dt,hashlib,json,math,re,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from strategy_lab.data.research_bundle import require_research_startup
from strategy_lab.data.research_inputs import complete_window_mask
import frozen_engine as engine
OUT=ROOT/'artifacts/20260907'
DAY=86400000
MODES={'literal':('literal',0,0),'causal':('causal',0,0),'causal_hype_cost':('causal',.0005,.0005),'causal_binance_cost':('causal',.001,.0004)}

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def load_inputs(request):
    verified=require_research_startup(request,project_root=PROJECT)
    save(OUT/'startup-report.json',verified.report)
    return verified.prices

def prepare():
    contract=json.loads((ROOT/'specs/frozen-contract-20260907.json').read_text())
    assert hashlib.sha256((ROOT/'scripts/frozen_engine.py').read_bytes()).hexdigest()==contract['engine_sha256']
    assert hashlib.sha256((ROOT/'scripts/source/hype_backtest.py').read_bytes()).hexdigest()==contract['original_source_sha256']
    request=contract['request']
    print('Verifying immutable Lab bundle and requested price windows...',flush=True)
    frames=load_inputs(request)
    selected={};bounds={};end=pd.Timestamp(request['end'])-pd.Timedelta(days=1)
    for symbol,f in frames.items():
        assert f.ts.iloc[-1]==end and bool(f.eligible.iloc[-1]),f'{symbol}: final bar missing/invalid'
        seg=f.research_segment_id.iloc[-1]
        tail=f.loc[f.research_segment_id.eq(seg)].copy().reset_index(drop=True)
        assert tail.eligible.all() and tail.ts.diff().dropna().eq(pd.Timedelta(days=1)).all()
        assert tail.research_window_valid.iloc[14:].all() and not tail.research_window_valid.iloc[:14].any()
        assert len(tail)>=30, f'{symbol}: insufficient continuous tail'
        selected[symbol.split('/')[0]]=tail
        bounds[symbol]={'first_open':tail.ts.iloc[0].isoformat(),'last_open':tail.ts.iloc[-1].isoformat(),'rows':len(tail),'all_observed_rows':len(f),'excluded_older_or_ineligible_rows':len(f)-len(tail),'observed_segments':[{'id':str(s),'first':g.ts.iloc[0].isoformat(),'last':g.ts.iloc[-1].isoformat(),'rows':len(g)} for s,g in f.groupby('research_segment_id',sort=False)]}
    common=max(f.ts.iloc[0] for f in selected.values())
    save(OUT/'resolved-windows.json',{'resolved_before_returns_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'common_start':common.isoformat(),'end_exclusive':request['end'],'symbols':bounds})
    print('Input verification passed; window bounds frozen:',json.dumps(bounds,ensure_ascii=False),flush=True)
    return selected,common

def bars_from_frame(f):
    return [{'ts':int(r.ts.value//1000000),'end_ts':int(r.ts.value//1000000)+DAY-1,'open':float(r.open),'high':float(r.high),'low':float(r.low),'close':float(r.close)} for r in f.itertuples()]

def oracle(bars):
    ma,atr,_,slope=engine.indicators(bars)
    equity,entry,entry_i,stop=1.,None,None,None;tape=[];curve=[]
    for i,b in enumerate(bars):
        if entry is None and i>=15:
            j=i-1
            if bars[j-1]['close']<ma[j-1] and bars[j]['close']>ma[j] and slope[j]>0:
                entry,entry_i,stop=b['open'],i,ma[j]-1.5*atr[j]
        if entry is not None:
            fill=b['open'] if b['open']<=stop else stop if b['low']<=stop else None
            if fill is None and i==len(bars)-1:fill=b['close']
            if fill is not None:
                equity*=fill/entry;tape.append((entry_i,i,entry,fill));entry,entry_i,stop=None,None,None
            else:stop=max(stop,ma[i]-1.5*atr[i])
        curve.append(equity if entry is None else equity*b['close']/entry)
    return tape,curve

def verify(coin,window,bars,runs,mask):
    literal,causal=runs['literal'],runs['causal']
    ma,atr,_,_=engine.indicators(bars)
    source=ast.parse((ROOT/'scripts/source/hype_backtest.py').read_text())
    fn=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='backtest')
    env={'bars':bars,'n':len(bars),'closes':[b['close'] for b in bars],'ma7':ma,'atr':atr}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<reviewed-original-function>','exec'),env)
    original=env['backtest'](0.)
    tuples=lambda r:[(t['entry_idx'],t['exit_idx'],t['entry_price'],t['exit_price']) for t in r['trades']]
    assert tuples(literal)==original['trades']
    literal_error=max(abs(a-b) for a,b in zip(literal['nav'],original['nav']));assert literal_error<1e-10
    tape,curve=oracle(bars);assert tuples(causal)==tape
    causal_error=max(abs(a-b) for a,b in zip(causal['nav'],curve));assert causal_error<1e-10
    live=engine.execute(bars,mode='causal',force_end=False)
    for k in sorted(set([30,len(bars)//2,len(bars)-1])):
        p=engine.execute(bars[:k],mode='causal',force_end=False)
        assert p['nav']==live['nav'][:k] and p['events']==[e for e in live['events'] if e['i']<k]
    for name,r in runs.items():
        assert all(mask[e['signal_idx']] for e in r['events'] if e['action']=='entry')
        assert abs(math.prod(1+t['ret_pct']/100 for t in r['trades'])-r['nav'][-1])<1e-10
        if name.startswith('causal'):
            assert all(e['i']==e['signal_idx']+1 for e in r['events'] if e['action']=='entry')
            _,fee,slip=MODES[name]
            expected=causal['nav'][-1]*((1-fee)/(1+fee)*(1-slip)/(1+slip))**len(causal['trades'])
            assert abs(expected-r['nav'][-1])<1e-10
            assert [(t['entry_idx'],t['exit_idx']) for t in r['trades']]==[(t['entry_idx'],t['exit_idx']) for t in causal['trades']]
    return {'coin':coin,'window':window,'status':'PASS','literal_nav_max_error':literal_error,'causal_oracle_nav_max_error':causal_error,'prefix_invariance':True,'signal_masks_consumed':True,'cost_identity':True}

def dd(values):
    peak=1.;worst=0.
    for x in values:peak=max(peak,x);worst=max(worst,1-x/peak)
    return worst*100

def write_csv(path,rows,empty_fields=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else empty_fields);w.writeheader();w.writerows(rows)

def main():
    assert not (OUT/'summary.json').exists(),'Use a new run directory for a new replay, do not overwrite results'
    selected,common=prepare()
    summaries=[];checks=[];chart={};slices=[]
    for coin,frame in selected.items():
        chart[coin]={}
        for window in ['available','common']:
            f=frame.copy() if window=='available' else frame.loc[frame.ts.ge(common)].copy().reset_index(drop=True)
            mask=complete_window_mask(f,backward=15,forward=0)
            assert (mask<=f.research_window_valid).all()
            bars=bars_from_frame(f)
            runs={name:engine.execute(bars,mode=mode,fee=fee,slip=slip) for name,(mode,fee,slip) in MODES.items()}
            checks.append(verify(coin,window,bars,runs,mask.tolist()))
            ma,atr,_,_=engine.indicators(bars)
            chart[coin][window]={'bars':bars,'ma':ma,'atr':atr,'runs':runs,'valid_signal_mask':mask.tolist()}
            save(OUT/'inputs'/window/(coin+'.json'),{'source':'verified startup returned frame; bounded eligible segment','bars':bars,'research_window_valid':mask.tolist(),'research_segment_id':f.research_segment_id.tolist()})
            for mode,r in runs.items():
                m=r['metrics'];m['buyhold_max_drawdown_pct']=dd([b['close']/bars[0]['close'] for b in bars]);m['final_valuation_exits']=sum(t['reason']=='end_of_test' for t in r['trades'])
                summaries.append({'coin':coin,'window':window,'mode':mode,**m})
                folder=OUT/'results'/window/coin/mode
                save(folder/'result.json',r)
                write_csv(folder/'trades.csv',r['trades'],['entry_date','exit_date','ret_pct','reason'])
                write_csv(folder/'nav.csv',[{'date_utc':engine.iso(b['ts']),'close':b['close'],'nav':r['nav'][i],'drawdown_pct':r['drawdowns'][i]*100} for i,b in enumerate(bars)])
                if window=='available' and mode in ['causal','causal_binance_cost']:
                    for days in [1,7,30,90,180,365]:
                        j=max(0,len(bars)-1-days);v=r['nav'][j:];anchor=v[0]
                        slices.append({'coin':coin,'mode':mode,'requested_days':days,'actual_days':len(bars)-1-j,'short_history':len(bars)-1<days,'first_close_date':engine.iso(bars[j]['ts']),'last_close_date':engine.iso(bars[-1]['ts']),'return_pct':(v[-1]/anchor-1)*100,'close_mtm_drawdown_pct':dd([x/anchor for x in v]),'entries':sum(e['action']=='entry' and e['i']>j for e in r['events']),'exits':sum(t['exit_idx']>j for t in r['trades']),'window_treatment':'slice ongoing NAV; inherit position and indicators; final valuation applies'})
            print(coin,window,'causal',round(runs['causal']['metrics']['total_return_pct'],4),'default-cost',round(runs['causal_binance_cost']['metrics']['total_return_pct'],4),flush=True)
    save(OUT/'summary.json',summaries);write_csv(OUT/'summary.csv',summaries)
    save(OUT/'recent-slices.json',slices);write_csv(OUT/'recent-slices.csv',slices)
    save(OUT/'validation.json',{'status':'PASS','checks':checks,'independent_account_per_coin':True,'no_optimization':True,'funding_verified':False})
    save(OUT/'chart-data.json',chart)
    print('PASS: seven assets x two frozen windows x four execution/cost views.',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',default='20260907',help='New artifacts child directory for replay; existing results are never overwritten')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.run_id):parser.error('run-id must contain only letters, numbers, hyphens and underscores')
    OUT=ROOT/'artifacts'/args.run_id
    if (OUT/'summary.json').exists():parser.error('Result directory already exists; choose a new run-id')
    try:main()
    except Exception as e:
        save(OUT/'run-failure.json',{'error':str(e),'type':type(e).__name__,'no_fallback':True});raise
