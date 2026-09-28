"""Causal applicability features and hash-checked joins to retained trades."""
from pathlib import Path
import datetime as dt, gzip, hashlib, json, sys, time
import numpy as np
import pandas as pd
import baseline_engine
from run_audit import bars_from_frame, save

ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT.parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from strategy_lab.data.research_bundle import require_research_startup
from strategy_lab.data.research_inputs import complete_window_mask
OUT=ROOT/'artifacts/applicability-20260908'
PARENT=ROOT/'artifacts/20260908-r1'
CONTRACT=ROOT/'specs/applicability-contract-20260908.json'


def features(bars,quotes):
    close=pd.Series([b['close'] for b in bars],dtype=float)
    ma,atr,_,_=baseline_engine.indicators(bars)
    ma=pd.Series(ma,dtype=float);atr=pd.Series(atr,dtype=float)
    log=np.log(close);ma60=close.rolling(60).mean()
    bullish=(close>ma60)&(ma60>ma60.shift(20))
    bearish=(close<ma60)&(ma60<ma60.shift(20))
    state=pd.Series(np.where(bullish,1,np.where(bearish,-1,0)),dtype=float).where(ma60.shift(20).notna())
    flips=((close>ma)!=(close.shift(1)>ma.shift(1))).astype(float).where(ma.notna()&ma.shift(1).notna())
    atrpct=atr/close*100;q=pd.Series(quotes,dtype=float)
    return pd.DataFrame(dict(trend_state=state,momentum30=close/close.shift(30)-1,
        efficiency30=(log-log.shift(30)).abs()/log.diff().abs().rolling(30).sum(),
        chop30=flips.rolling(30).sum(),atr_pct=atrpct,liquidity30=q.rolling(30).median(),
        atr90=atrpct.rolling(90).median(),liquidity90=q.rolling(90).median()))


def load_inputs(request):
    return require_research_startup(request,project_root=PROJECT)


def batches(symbols,base,label):
    request=dict(base,symbols=symbols);save(OUT/'startup-requests'/f'{label}.json',request)
    try:inp=load_inputs(request)
    except (ValueError,AssertionError) as e:
        save(OUT/'startup-failures'/f'{label}.json',dict(error=str(e),symbols=symbols))
        if len(symbols)==1:raise
        k=len(symbols)//2
        yield from batches(symbols[:k],base,label+'L');yield from batches(symbols[k:],base,label+'R');return
    save(OUT/'startup-reports'/f'{label}.json',inp.report)
    yield from inp.prices.items()


def main():
    assert not (OUT/'started.json').exists(),'Preserve completed/failed attempts'
    c=json.loads(CONTRACT.read_text());parent=json.loads((ROOT/'specs/contract-20260908.json').read_text())
    assert hashlib.sha256((PARENT/'run-manifest.json').read_bytes()).hexdigest()==c['parent_run_manifest_sha256']
    manifest=json.loads((PARENT/'run-manifest.json').read_text())
    for rel,sha in manifest.items():assert hashlib.sha256((PARENT/rel).read_bytes()).hexdigest()==sha,rel
    summary=pd.read_csv(PARENT/'all-window-results.csv.gz')
    annual=summary.loc[summary.window.isin([str(y) for y in range(2020,2027)])&summary.full_requested_window]
    annual_by_symbol={s:g.to_dict('records') for s,g in annual.groupby('symbol')}
    started=time.time();save(OUT/'started.json',dict(at=dt.datetime.now(dt.timezone.utc).isoformat(),contract_sha256=hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    trades=[];year_rows=[];coverage=[];checks=[];count=0
    for offset in range(0,len(c['requested_symbols']),48):
        print('START',offset//48+1,flush=True)
        for symbol,frame in batches(c['requested_symbols'][offset:offset+48],c['request_base'],f'b{offset//48+1:02d}'):
            count+=1;coin=symbol.split('/')[0];cls=parent['universe_inventory'][symbol]
            p=PARENT/'full-history-replays'/f'{coin}.json.gz'
            paths=json.loads(gzip.decompress(p.read_bytes())) if p.exists() else []
            expected={(x['common']['start'],x['common']['end']):x for x in paths}
            dates={};seen=set();trade_count=0;deep=False
            for _,f in frame.groupby('research_segment_id',sort=False):
                if len(f)<30:continue
                f=f.reset_index(drop=True);bars=bars_from_frame(f)
                key=(baseline_engine.iso(bars[0]['ts']),baseline_engine.iso(bars[-1]['ts']))
                assert key in expected,(symbol,key)
                x=expected[key];assert x['bars']==bars,(symbol,'OHLC/time mismatch')
                mask=(complete_window_mask(f,backward=15,forward=0)&f.research_window_valid).tolist()
                assert mask==x['valid_mask'];seen.add(key)
                feat=features(bars,f.quote_volume.tolist())
                mask90=(complete_window_mask(f,backward=90,forward=0)&f.research_window_valid).to_numpy()
                if not deep and len(f)>=105:
                    k=max(100,len(f)//2)
                    pd.testing.assert_frame_equal(feat.iloc[:k],features(bars[:k],f.quote_volume.tolist()[:k]))
                    altered=[dict(b) for b in bars];quotes=f.quote_volume.to_numpy().copy()
                    for b in altered[k:]:
                        for col in ['open','high','low','close']:b[col]*=10
                    quotes[k:]*=100
                    pd.testing.assert_frame_equal(feat.iloc[:k],features(altered,quotes).iloc[:k]);deep=True
                for i,ts in enumerate(f.ts):
                    if ts.month==12 and ts.day==31:
                        record=feat.iloc[i].to_dict()
                        dates[str(ts.year+1)]=dict(record,feature_date=ts.strftime('%Y-%m-%d'),prior_segment_bars=i+1,
                            features_valid=bool(mask90[i] and feat.iloc[i].notna().all()))
                for variant,r in x['runs'].items():
                    for t in r['trades']:
                        i=t['signal_idx'];values=feat.iloc[i].to_dict()
                        valid=bool(mask90[i] and feat.iloc[i][['trend_state','momentum30','efficiency30','chop30','atr_pct','liquidity30']].notna().all())
                        assert bars[t['entry_idx']]['ts']>bars[i]['ts']
                        trades.append(dict(run_id=x['common']['run_id'],symbol=symbol,coin=coin,asset_class=cls,
                            variant=variant,side=t['side'],trade_id=t['trade_id'],signal_date=t['signal_date'],entry_date=t['entry_date'],exit_date=t['exit_date'],
                            ret_pct=t['ret_pct'],equity_before=t['equity_before'],equity_after=t['equity_after'],
                            reason=t['reason'],bankrupt=t['economic_bankruptcy'],natural_exit=t['reason']!='end_of_test',
                            hold_days=t['hold_days'],economic_flag=x['common']['economic_flag'],feature_valid=valid,
                            signal_history_bars=i+1,**values))
                        trade_count+=1
            assert seen==set(expected),(symbol,'missing retained segments')
            for a in annual_by_symbol.get(symbol,[]):
                v=dates.get(a['window'],dict(features_valid=False,feature_date=None,prior_segment_bars=0))
                year_rows.append(dict(a,**v))
            coverage.append(dict(symbol=symbol,asset_class=cls,retained_segments=len(paths),trades=trade_count,
                available_year_anchors=len(dates),prefix_and_future_mutation_checked=deep))
            if count%48==0:print('PROGRESS',count,'trades',len(trades),'seconds',round(time.time()-started),flush=True)
    assert len(trades)==json.loads((PARENT/'summary.json').read_text())['full_history_trades']
    pd.DataFrame(trades).to_csv(OUT/'trade-features.csv.gz',index=False,compression='gzip')
    pd.DataFrame(year_rows).to_csv(OUT/'annual-asset-features.csv.gz',index=False,compression='gzip')
    pd.DataFrame(coverage).to_csv(OUT/'coverage.csv',index=False)
    save(OUT/'feature-summary.json',dict(symbols=count,full_history_trades=len(trades),annual_variant_rows=len(year_rows),
        parent_segments_and_masks_exact_match=True,parent_manifest_files_verified=len(manifest),
        prefix_future_mutation_symbols=sum(x['prefix_and_future_mutation_checked'] for x in coverage),elapsed_seconds=time.time()-started))
    save(OUT/'feature-manifest.json',{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file()})
    print('DONE',len(trades),len(year_rows),flush=True)


if __name__=='__main__':main()
