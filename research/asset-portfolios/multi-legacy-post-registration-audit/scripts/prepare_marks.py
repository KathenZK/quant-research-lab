"""Capture auxiliary Binance mark-price OHLC with exact raw REST receipts."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import urllib.request, urllib.parse
import hashlib,json,time
import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parents[1]/'artifacts/inputs/marks'
START=pd.Timestamp('2026-07-16T00:00:00Z');END=pd.Timestamp('2026-09-05T15:00:00Z')
ASSETS=('HYPE','BTC','ETH','SOL','BNB','TRX')

def one(asset):
    out=OUT/asset;out.mkdir(parents=True,exist_ok=True)
    cursor=int(START.timestamp()*1000);stop=int(END.timestamp()*1000);rows=[];receipts=[]
    while cursor<stop:
        params={'symbol':asset+'USDT','interval':'15m','startTime':cursor,'endTime':stop-1,'limit':1500}
        url='https://fapi.binance.com/fapi/v1/markPriceKlines?'+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,headers={'User-Agent':'quant-strategy-lab audit'})
        with urllib.request.urlopen(req,timeout=30) as response:raw=response.read()
        batch=json.loads(raw)
        if not isinstance(batch,list) or not batch:raise ValueError(f'Incomplete response {asset} at {cursor}')
        path=out/f'{cursor}.json';path.write_bytes(raw)
        receipts.append({'path':str(path.relative_to(OUT)),'sha256':hashlib.sha256(raw).hexdigest(),'url':url,'rows':len(batch)})
        rows.extend(batch);next_cursor=int(batch[-1][0])+900000
        if next_cursor<=cursor:raise ValueError('Nonadvancing pagination')
        cursor=next_cursor
    f=pd.DataFrame(rows,columns=['open_ms','open','high','low','close','unused_volume','close_ms','unused_qv','unused_count','unused_buy','unused_buyquote','ignore'])
    f['ts']=pd.to_datetime(f.open_ms,unit='ms',utc=True)
    f=f[(f.ts>=START)&(f.ts<END)].copy()
    for c in ('open','high','low','close'):f[c]=pd.to_numeric(f[c])
    grid=pd.date_range(START,END,freq='15min',inclusive='left')
    if f.ts.duplicated().any() or not pd.DatetimeIndex(f.ts).equals(grid):raise ValueError(f'{asset} mark grid mismatch')
    x=f[['open','high','low','close']]
    if not np.isfinite(x).all().all() or x.le(0).any().any() or f.high.lt(f[['open','low','close']].max(axis=1)).any() or f.low.gt(f[['open','high','close']].min(axis=1)).any():raise ValueError('Invalid mark OHLC')
    if not (f.close_ms.astype('int64')==f.open_ms.astype('int64')+899999).all():raise ValueError('Unclosed mark kline')
    path=OUT/f'{asset}_15m.parquet';f[['ts','open','high','low','close']].to_parquet(path,index=False)
    result={'asset':asset,'path':str(path),'rows':len(f),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
       'start':str(START),'end_exclusive':str(END),'duplicates':0,'missing_bars':0,'invalid_ohlc':0,
       'classification':'AUXILIARY_OFFICIAL_REST_MARK_SNAPSHOT; not registered OHLCV catalog', 'receipts':receipts}
    (out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(asset,len(f),'VERIFIED',flush=True);return result

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:result=list(pool.map(one,ASSETS))
    (OUT/'manifest.json').write_text(json.dumps({'status':'OBSERVED_OFFICIAL_MARK_INPUTS_CHECKED','assets':result},indent=2)+'\n')
