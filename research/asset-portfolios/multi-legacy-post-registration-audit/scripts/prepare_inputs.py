"""Capture this audit's API-returned prices and separately labelled observed funding."""
from pathlib import Path
import json
import hashlib
import pandas as pd
from strategy_lab.data.research_bundle import require_research_startup, read_json
from strategy_lab.data.funding_v2 import load_funding_v2

ROOT = Path(__file__).resolve().parents[4]
FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / 'artifacts/inputs'
ASSETS = ['HYPE', 'BTC', 'ETH', 'SOL', 'BNB', 'TRX']
START = '2025-05-30T10:30:00Z'
END = '2026-09-05T15:00:00Z'

def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str)+'\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load_prices(request):
    return require_research_startup(request, project_root=ROOT, data_root=ROOT/'data')

def load_observed_funding(bundle):
    c = bundle['components']['funding']
    return load_funding_v2(ROOT/'data'/c['root'], expected_manifest_sha256=c['manifest_sha256'])

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = read_json(ROOT/'research/platform/data-lake-governance/specs/research-startup-price-example-v2.json')
    files = {}
    for tf in ['15m', '1h']:
        req = dict(base, timeframe=tf, symbols=[a+'/USDT:USDT' for a in ASSETS],
                   start=START if tf=='15m' else '2025-05-30T11:00:00Z', end=END, backward_bars=1, forward_bars=0)
        save_json(FAMILY/f'specs/price_request_{tf}.json', req)
        print('STARTUP', tf, flush=True)
        inputs = load_prices(req)
        save_json(OUT/f'startup_{tf}.json', inputs.report)
        for asset in ASSETS:
            frame = inputs.prices[asset+'/USDT:USDT'].copy()
            # Schema conversion preserves every value and validity flag.
            for col in frame.columns:
                if isinstance(frame[col].dtype, pd.ArrowDtype):
                    if col == 'ts':
                        frame[col] = pd.to_datetime(frame[col].tolist(), utc=True)
                    elif pd.api.types.is_numeric_dtype(frame[col].dtype):
                        frame[col] = frame[col].astype('float64')
            if not frame.research_window_valid.all() or frame.research_segment_id.nunique()!=1:
                raise ValueError(f'Invalid or fragmented input {asset} {tf}')
            path=OUT/f'{asset}_{tf}.parquet'
            frame.to_parquet(path, index=False)
            files[path.name]={'sha256':sha(path),'rows':len(frame),'first':str(frame.ts.min()),'last':str(frame.ts.max())}
        print('PRICES_SAVED', tf, flush=True)
    bundle=read_json(ROOT/base['bundle_path'])
    f=load_observed_funding(bundle)
    audits={}
    for asset in ASSETS:
        symbol=asset+'/USDT:USDT'
        e=f.events[f.events.symbol.eq(symbol)&f.events.ts.gt(pd.Timestamp(START))&f.events.ts.le(pd.Timestamp(END))].copy()
        s=f.segments[f.segments.symbol.eq(symbol)].copy()
        x=f.expected[f.expected.symbol.eq(symbol)].copy()
        for suffix,frame in [('funding_observed',e),('funding_segments',s),('funding_expected',x)]:
            path=OUT/f'{asset}_{suffix}.parquet';frame.to_parquet(path,index=False)
            files[path.name]={'sha256':sha(path),'rows':len(frame)}
        mark=pd.to_numeric(e.mark_price,errors='coerce')
        audits[asset]={'events':len(e),'first':str(e.ts.min()),'last':str(e.ts.max()),
            'unambiguous':bool(e.event_unambiguous.all()),'duplicate_ts':int(e.ts.duplicated().sum()),
            'missing_mark':int((mark.isna()|mark.le(0)).sum()),
            'whole_window_covered':bool((s.start.le(pd.Timestamp(START))&s.end.ge(pd.Timestamp(END))).any()),
            'funding_window_verified':False,'identity_verified':False,
            'interpretation':'Observed events only. Any funding-adjusted result is an estimate, never verified full net return.'}
    manifest={'start':START,'end_exclusive':END,'files':files,'funding_audit':audits,
        'bundle_path':base['bundle_path'],'bundle_sha256':base['bundle_sha256'],
        'funding_window_verified':False,'strategy_approved':False}
    save_json(OUT/'manifest.json',manifest)
    print(json.dumps(audits,ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
