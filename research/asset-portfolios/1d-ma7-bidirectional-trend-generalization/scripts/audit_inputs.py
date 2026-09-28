"""P0：可信启动、返回帧留证与结果前资格审计，不计算候选收益。"""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import sys
import time

FAMILY = Path(__file__).resolve().parents[1]
LAB = Path('/Users/ZK/OpenCode/quant-strategy-lab')
sys.path.insert(0, str(LAB / 'src'))
import pandas as pd
from strategy_lab.data.research_bundle import require_research_startup

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str)+'\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load_inputs(request):
    return require_research_startup(request, project_root=LAB, data_root=LAB/'data')

def load_batch(request, out, label):
    save(out/'requests'/f'{label}.json', request)
    try:
        inputs = load_inputs(request)
    except ValueError as exc:
        save(out/'failures'/f'{label}.json', {'error': str(exc), 'symbols': request['symbols'], 'no_fallback': True})
        print('SPLIT/FAIL', label, str(exc), flush=True)
        if len(request['symbols']) == 1:
            yield request['symbols'][0], None, str(exc)
        else:
            n = len(request['symbols'])//2
            for suffix, symbols in [('L', request['symbols'][:n]), ('R', request['symbols'][n:])]:
                yield from load_batch(dict(request, symbols=symbols), out, label+suffix)
        return
    save(out/'startup-reports'/f'{label}.json', inputs.report)
    for symbol, frame in inputs.prices.items():
        yield symbol, frame, None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', default='p0-inputs-20260908')
    args = parser.parse_args()
    out = FAMILY/'artifacts'/args.run_id
    assert not out.exists(), 'Retained run exists; use new run-id'
    request = json.loads((FAMILY/'specs/input-request-20260908.json').read_text())
    universe = json.loads((FAMILY/'specs/observed-universe-20260908.json').read_text())
    pins = json.loads((FAMILY/'specs/source-pins-20260908.json').read_text())
    for p,h in pins['files'].items():
        if p.startswith('src/'):
            assert sha(LAB/p)==h, f'Pinned source changed: {p}'
    versions = {}
    for x in ['numpy','pandas','duckdb','pyarrow','scipy','pytest','statsmodels']:
        try: versions[x]=importlib.metadata.version(x)
        except importlib.metadata.PackageNotFoundError: versions[x]='unavailable'
    save(out/'started.json', {'utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'python':sys.version,
                              'dependencies':versions,'source_pins_sha256':sha(FAMILY/'specs/source-pins-20260908.json'),
                              'contract_sha256':sha(FAMILY/'specs/research-contract-p1-20260908.md'),
                              'script_sha256':sha(Path(__file__)), 'purpose':'coverage only; no strategy returns'})
    rows=[];segments=[];frames={}; start=time.time()
    a=pd.Timestamp('2024-12-05',tz='UTC');b=pd.Timestamp('2026-09-05',tz='UTC')
    for offset in range(0,len(request['symbols']),128):
        req=dict(request,symbols=request['symbols'][offset:offset+128])
        print('BATCH',offset,flush=True)
        for symbol,f,error in load_batch(req,out,f'b{offset:04d}'):
            common={'symbol':symbol,'asset_class':universe[symbol],
                    'asset_fold':int.from_bytes(hashlib.sha256(symbol.encode()).digest()[:8],'big')%100}
            if f is None:
                rows.append(dict(common,status='STARTUP_FAILED',error=error));continue
            coin=symbol.split('/')[0];fp=out/'returned-frames'/f'{coin}.pkl.gz';fp.parent.mkdir(exist_ok=True)
            f.to_pickle(fp,compression='gzip');frames[symbol]={'path':str(fp.relative_to(out)),'sha256':sha(fp),
                'dataframe_hash':hashlib.sha256(pd.util.hash_pandas_object(f,index=True).values.tobytes()).hexdigest()}
            groups=[g for _,g in f.loc[f.eligible].groupby('research_segment_id',sort=False)]
            main=[g for g in groups if g.ts.min()<=a-pd.Timedelta(days=121) and g.ts.max()+pd.Timedelta(days=1)>=b]
            for g in groups:
                segments.append(dict(common,segment_id=str(g.research_segment_id.iloc[0]),bars=len(g),
                    first=g.ts.iloc[0],last=g.ts.iloc[-1],reaches_end=g.ts.iloc[-1]+pd.Timedelta(days=1)==b))
            rows.append(dict(common,status='PRICE_DIAGNOSTIC_INPUTS_VERIFIED',rows=len(f),
                eligible_bars=int(f.eligible.sum()),max_segment_bars=max(map(len,groups),default=0),
                first_open=f.ts.min(),last_open=f.ts.max(),segments=len(groups),
                main_639_with_121_warmup=bool(main),long_history_180=any(len(g)>=180 for g in groups)))
            if len(rows)%50==0:print('SYMBOLS',len(rows),'seconds',round(time.time()-start),flush=True)
    pd.DataFrame(rows).to_csv(out/'coverage.csv',index=False)
    pd.DataFrame(segments).to_csv(out/'segments.csv',index=False)
    save(out/'frame-manifest.json',frames)
    save(out/'summary.json',{'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'seconds':time.time()-start,
        'symbols':len(rows),'frames':len(frames),'failures':sum(r['status']=='STARTUP_FAILED' for r in rows),
        'classes':{c:{'observed':sum(r['asset_class']==c for r in rows),
                    'main_eligible':sum(r['asset_class']==c and r.get('main_639_with_121_warmup',False) for r in rows),
                    'min180':sum(r['asset_class']==c and r.get('long_history_180',False) for r in rows)} for c in sorted(set(universe.values()))},
        'candidate_results_computed':False,'funding_window_verified':False})
    print((out/'summary.json').read_text(),flush=True)

if __name__=='__main__':main()
