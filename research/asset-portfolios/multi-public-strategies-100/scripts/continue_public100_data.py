"""R2 public source capture. Raw-only, hash-pinned, resumable diagnostic inputs."""
from pathlib import Path
import argparse, concurrent.futures, datetime, hashlib, io, json, subprocess, time, zipfile
import numpy as np
import pandas as pd
from strategy_lab.data.fs import atomic_write_path

ROOT = Path(__file__).resolve().parents[4]
F = Path(__file__).resolve().parents[1]
SPEC = F / 'specs/continuation-data-request-20260909.json'
C = json.loads(SPEC.read_text())
SNAP = 'public100_r2_20260909'
ART = F / 'artifacts/continuation-r2'
ART.mkdir(exist_ok=True)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def put_json(p, obj):
    atomic_write_path(p, lambda q: q.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n'))

def fetch(url, source, name):
    p = ROOT / 'data/raw/source_payloads' / f'source={source}' / 'date=2026-09-09' / SNAP / name
    p.parent.mkdir(parents=True, exist_ok=True)
    receipt = p.with_name(p.name + '.receipt.json')
    if p.exists() and receipt.exists():
        r = json.loads(receipt.read_text())
        if r['sha256'] == sha(p) and r['http_status'] == '200':
            return p, r
    tmp = p.with_name(p.name + '.download')
    run = subprocess.run(['curl','-sS','-L','--retry','2','--retry-delay','1','--connect-timeout','12','--max-time','45','-A','PUBLIC100-public-research/2.0','-o',str(tmp),'-w','%{http_code}',url], capture_output=True, text=True)
    if not tmp.exists():
        tmp.write_bytes(b'')
    tmp.replace(p)
    r = {'url':url, 'path':str(p.relative_to(ROOT)), 'http_status':run.stdout, 'curl_returncode':run.returncode, 'error':run.stderr, 'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'sha256':sha(p), 'bytes':p.stat().st_size}
    put_json(receipt,r)
    return p,r

def partitions(df, venue, market, timeframe, source, symbol):
    df = df.copy()
    for k,v in {'exchange':venue,'market_type':market,'timeframe':timeframe,'source':source,'symbol':symbol,'acceptance_status':'raw_unaccepted','source_dataset_id':f'{source}.{SNAP}.{timeframe}'}.items():
        df[k]=v
    paths=[]
    for day,g in df.groupby(df.ts.dt.strftime('%Y-%m-%d')):
        p=ROOT/f'data/raw/ohlcv/exchange={venue}/market_type={market}/timeframe={timeframe}/source={source}/date={day}/symbol={symbol.replace("/", "_")}__{SNAP}.parquet'
        if not p.exists(): atomic_write_path(p,lambda q,g=g:g.to_parquet(q,index=False))
        else:
            existing=pd.read_parquet(p)
            assert existing.equals(g.reset_index(drop=True)) or existing.equals(g), f'Immutable partition differs: {p}'
        paths.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'rows':len(g)})
    return paths

def bar_audit(df, expected=None):
    cols=['open','high','low','close','volume']
    bad=df[cols].isna().any(axis=1)|~np.isfinite(df[cols]).all(axis=1)|(df[['open','high','low','close']]<=0).any(axis=1)|(df.volume<0)|(df.high<df[['open','close','low']].max(axis=1))|(df.low>df[['open','close','high']].min(axis=1))
    return {'rows':len(df),'duplicates':int(df.ts.duplicated().sum()),'invalid_rows':int(bad.sum()),'zero_volume_rows':int((df.volume==0).sum()),'missing_bars':None if expected is None else len(expected.difference(df.ts)), 'first':str(df.ts.min()), 'last':str(df.ts.max())}

def yahoo():
    def one(q):
        sym=q['symbol']; interval=q['interval'];a=int(pd.Timestamp(q['start']).timestamp());b=int(pd.Timestamp(q['end']).timestamp())
        url=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={a}&period2={b}&interval={interval}&includePrePost=false&events=div%2Csplits'
        p,r=fetch(url,'yahoo_finance',f'{sym}-{interval}.json')
        if r['http_status']!='200':return {'request':q,'payload':r,'error':'HTTP request failed'}
        try:
            obj=json.loads(p.read_text())['chart']['result'][0];meta=obj['meta']
            venue={'PCX':'nyse_arca','NMS':'nasdaq','NGM':'nasdaq','NCM':'nasdaq','NYQ':'nyse','BTS':'cboe_bzx'}[meta['exchangeName']]
            df=pd.DataFrame(obj['indicators']['quote'][0]);df['ts']=pd.to_datetime(obj['timestamp'],unit='s',utc=True)
            df=df[(df.ts>=pd.Timestamp(q['start']))&(df.ts<pd.Timestamp(q['end']))].reset_index(drop=True)
            df['native_timezone']=meta['exchangeTimezoneName'];df['payload_sha256']=r['sha256']
            return {'request':q,'payload':r,'native_metadata':meta,'audit':bar_audit(df),'files':partitions(df,venue,'equity','1h' if interval=='60m' else interval,'yahoo_finance',sym)}
        except Exception as e:return {'request':q,'payload':r,'error':repr(e)}
    with concurrent.futures.ThreadPoolExecutor(4) as ex: rows=list(ex.map(one,C['yahoo']))
    put_json(ART/'yahoo-manifest.json',{'spec_sha256':sha(SPEC),'status':'raw_unaccepted','records':rows})
    for r in rows:print(r['request'],r.get('audit',r.get('error')),flush=True)

def coinbase():
    q=C['coinbase'];start=pd.Timestamp(q['start']);end=pd.Timestamp(q['end']);step=pd.Timedelta(seconds=q['granularity']*q['max_candles_per_request'])
    tasks=[];a=start
    while a<end:
        b=min(a+step,end);tasks.append((a,b));a=b
    def one(pair):
        a,b=pair;url=f'https://api.exchange.coinbase.com/products/{q["product"]}/candles?granularity={q["granularity"]}&start={a.isoformat()}&end={b.isoformat()}'
        p,r=fetch(url,'coinbase_exchange',f'BTC-USD-15m-{a.strftime("%Y%m%dT%H%M")}.json')
        time.sleep(.35)
        if r['http_status']!='200':return {'payload':r,'error':'HTTP request failed'},None
        try:
            data=json.loads(p.read_text());df=pd.DataFrame(data,columns=['time','low','high','open','close','volume']);df['ts']=pd.to_datetime(df.time,unit='s',utc=True)
            df=df[(df.ts>=a)&(df.ts<b)].sort_values('ts').reset_index(drop=True);df['payload_sha256']=r['sha256']
            return {'start':a.isoformat(),'end':b.isoformat(),'payload':r,'rows':len(df)},df
        except Exception as e:return {'payload':r,'error':repr(e)},None
    rows=[];frames=[]
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        for rec,df in ex.map(one,tasks):
            rows.append(rec)
            if df is not None:frames.append(df)
            if len(rows)%40==0:
                put_json(ART/'coinbase-progress.json',{'requests_done':len(rows),'requests_total':len(tasks),'errors':sum('error' in r for r in rows)})
                print('Coinbase',len(rows),'/',len(tasks),'errors',sum('error' in r for r in rows),flush=True)
    manifest={'spec_sha256':sha(SPEC),'status':'raw_unaccepted','records':rows}
    if frames:
        df=pd.concat(frames,ignore_index=True).sort_values('ts').reset_index(drop=True)
        expected=pd.date_range(start,end,freq='15min',inclusive='left');manifest['audit']=bar_audit(df,expected)
        manifest['files']=partitions(df,'coinbase','spot','15m','coinbase_exchange','BTC-USD')
    put_json(ART/'coinbase-manifest.json',manifest);print('Coinbase final',manifest.get('audit'),flush=True)

def funding():
    q=C['funding'];months=pd.date_range(q['start'],pd.Timestamp(q['end'])-pd.Timedelta(days=1),freq='MS').strftime('%Y-%m')
    def archive(task):
        sym,month=task;filename=f'{sym}-fundingRate-{month}.zip';url=f'https://data.binance.vision/data/futures/um/monthly/fundingRate/{sym}/{filename}'
        p,r=fetch(url,'binance_vision_funding',filename);ch,cr=fetch(url+'.CHECKSUM','binance_vision_funding',filename+'.CHECKSUM')
        rec={'symbol':sym,'month':month,'payload':r,'checksum':cr}
        if r['http_status']!='200' or cr['http_status']!='200':return rec|{'error':'archive unavailable'},None
        if ch.read_text().split()[0]!=sha(p):return rec|{'error':'CHECKSUM_MISMATCH'},None
        z=zipfile.ZipFile(p);df=pd.read_csv(z.open(z.namelist()[0]));df['source_archive_sha256']=sha(p)
        return rec|{'rows':len(df)},df
    ars=[];afs={s:[] for s in q['symbols']}
    with concurrent.futures.ThreadPoolExecutor(6) as ex:
        for r,df in ex.map(archive,[(s,m) for s in q['symbols'] for m in months]):
            ars.append(r)
            if df is not None:afs[r['symbol']].append(df)
    records=[]
    for sym in q['symbols']:
        current=int(pd.Timestamp(q['start']).timestamp()*1000);end=int(pd.Timestamp(q['end']).timestamp()*1000);api_rows=[];receipts=[]
        while current<end:
            url=f'https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&startTime={current}&endTime={end-1}&limit=1000'
            p,r=fetch(url,'binance_funding_api',f'{sym}-{current}.json');receipts.append(r)
            if r['http_status']!='200':break
            data=json.loads(p.read_text())
            if not isinstance(data,list) or not data:break
            api_rows.extend([{**x,'source_payload_sha256':sha(p)} for x in data]);next_start=max(int(x['fundingTime']) for x in data)+1
            assert next_start>current;current=next_start
            if len(data)<1000:break
        rec={'symbol':sym,'api_receipts':receipts,'files':[],'archives':[r for r in ars if r['symbol']==sym]}
        if afs[sym]:
            a=pd.concat(afs[sym],ignore_index=True);a['fundingTime']=pd.to_numeric(a.calc_time);rec['archive_columns']=list(a.columns)
            if api_rows:
                b=pd.DataFrame(api_rows);b['fundingTime']=pd.to_numeric(b.fundingTime);b['fundingRate']=pd.to_numeric(b.fundingRate);b['markPrice']=pd.to_numeric(b.markPrice)
                merged=a.merge(b,on='fundingTime',how='outer',indicator=True,validate='one_to_one')
                rec['audit']={'archive_rows':len(a),'api_rows':len(b),'unmatched_rows':int((merged['_merge']!='both').sum()),'max_rate_difference':float((merged.last_funding_rate-merged.fundingRate).abs().max()),'invalid_mark_prices':int((~np.isfinite(merged.markPrice)|(merged.markPrice<=0)).sum()),'native_intervals_hours':sorted(a.funding_interval_hours.unique().tolist())}
                merged['ts']=pd.to_datetime(merged.fundingTime,unit='ms',utc=True);merged=merged.drop(columns='_merge')
                for day,g in merged.groupby(merged.ts.dt.strftime('%Y-%m-%d')):
                    path=ROOT/f'data/raw/funding/exchange=binance/market_type=perp/source=binance_vision_api_crosscheck/date={day}/symbol={sym}__{SNAP}.parquet'
                    for k,v in {'exchange':'binance','market_type':'perp','symbol':sym,'source':'binance_vision_api_crosscheck','acceptance_status':'raw_unaccepted'}.items():g=g.assign(**{k:v})
                    if not path.exists():atomic_write_path(path,lambda x,g=g:g.to_parquet(x,index=False))
                    rec['files'].append({'path':str(path.relative_to(ROOT)),'sha256':sha(path),'rows':len(g)})
            else:rec['error']='No API rows for mark-price and archive crosscheck'
        else:rec['error']='No archive rows'
        records.append(rec);print('Funding',sym,rec.get('audit',rec.get('error')),flush=True)
    put_json(ART/'funding-manifest.json',{'spec_sha256':sha(SPEC),'status':'raw_unaccepted','records':records})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--group',choices=['yahoo','coinbase','funding'],required=True);args=parser.parse_args();globals()[args.group]()
