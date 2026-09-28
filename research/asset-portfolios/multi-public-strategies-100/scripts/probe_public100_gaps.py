"""Separate raw source queries for missing intervals; never overwrite first capture."""
import concurrent.futures,json
import pandas as pd
from continue_public100_data import F,ROOT,ART,fetch,put_json,partitions,bar_audit,sha

def yahoo_day(task):
    sym,interval,day=task;a=pd.Timestamp(day,tz='UTC');b=a+pd.Timedelta(days=1)
    p,r=fetch(f'https://query2.finance.yahoo.com/v8/finance/chart/{sym}?period1={int(a.timestamp())}&period2={int(b.timestamp())}&interval={interval}&includePrePost=false','yahoo_finance_requery',f'{sym}-{interval}-{day}.json')
    rec={'symbol':sym,'interval':interval,'day':day,'payload':r}
    if r['http_status']!='200':return rec
    obj=json.loads(p.read_text())['chart']['result'][0]
    d=pd.DataFrame(obj['indicators']['quote'][0]);d['ts']=pd.to_datetime(obj['timestamp'],unit='s',utc=True);d=d[(d.ts>=a)&(d.ts<b)].reset_index(drop=True);d['payload_sha256']=r['sha256']
    rec['audit']=bar_audit(d);rec['files']=partitions(d,'nyse_arca','equity','1h' if interval=='60m' else interval,'yahoo_finance_requery',sym)
    return rec

def cb(task):
    a,b,gran=task
    p,r=fetch(f'https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity={gran}&start={a.isoformat()}&end={b.isoformat()}','coinbase_exchange_requery',f'BTC-USD-{gran}-{a.strftime("%Y%m%d")}.json')
    rec={'start':str(a),'end':str(b),'granularity':gran,'payload':r}
    if r['http_status']!='200':return rec,None
    d=pd.DataFrame(json.loads(p.read_text()),columns=['time','low','high','open','close','volume']);d['ts']=pd.to_datetime(d.time,unit='s',utc=True);d=d[(d.ts>=a)&(d.ts<b)].sort_values('ts').reset_index(drop=True);d['payload_sha256']=r['sha256'];rec['audit']=bar_audit(d)
    return rec,d

def main():
    tasks=[('SPY','60m',day) for day in ['2024-11-29','2024-12-24','2025-07-03','2025-11-28','2025-12-24','2026-01-30','2026-02-02']]+[('IWM','5m',day) for day in ['2026-08-05','2026-08-06','2026-08-13','2026-08-25']]
    with concurrent.futures.ThreadPoolExecutor(4) as ex:rows=list(ex.map(yahoo_day,tasks))
    put_json(ART/'yahoo-gap-probes.json',{'records':rows});print('Yahoo probes',[(r['symbol'],r['day'],r.get('audit')) for r in rows],flush=True)
    missing=pd.to_datetime(json.loads((ART/'coinbase-missing-times.json').read_text()),utc=True);tasks=[(d,d+pd.Timedelta(days=1),900) for d in missing.normalize().unique()]
    a=pd.Timestamp('2017-01-01',tz='UTC');end=pd.Timestamp('2026-09-01',tz='UTC')
    while a<end:
        b=min(a+pd.Timedelta(days=300),end);tasks.append((a,b,86400));a=b
    rows=[];frames={900:[],86400:[]}
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        for rec,d in ex.map(cb,tasks):
            rows.append(rec)
            if d is not None:frames[rec['granularity']].append(d)
    files={}
    for gran,fs in frames.items():
        d=pd.concat(fs,ignore_index=True).sort_values('ts').reset_index(drop=True)
        assert not d.ts.duplicated().any()
        files[str(gran)]=partitions(d,'coinbase','spot','15m' if gran==900 else '1d','coinbase_exchange_requery','BTC-USD')
        print('Coinbase requery',gran,bar_audit(d),flush=True)
    put_json(ART/'coinbase-gap-probes.json',{'records':rows,'files':files})

if __name__=='__main__':main()
