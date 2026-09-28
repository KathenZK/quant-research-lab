"""Read exact retained raw partitions for explicitly untrusted diagnostics."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import exchange_calendars as xc
from continue_public100_data import ROOT,F,ART,sha

def raw_files(files):
    frames=[]
    for rec in files:
        p=ROOT/rec['path'];assert sha(p)==rec['sha256'];d=pd.read_parquet(p);assert len(d)==rec['rows'];frames.append(d)
    df=pd.concat(frames,ignore_index=True).sort_values('ts').set_index('ts');df.index=df.index.as_unit('ns');assert not df.index.has_duplicates
    return df

def payload(r):
    p=ROOT/r['path'];assert sha(p)==r['sha256'];assert r['http_status']=='200'
    return p

def yahoo(interval,symbol):
    m=json.loads((ART/('yahoo-2m-manifest.json' if interval=='2m' else 'yahoo-manifest.json')).read_text())
    r=next(r for r in m['records'] if (r.get('symbol')==symbol if interval=='2m' else r['request']['symbol']==symbol and r['request']['interval']==interval))
    payload(r['payload']);return raw_files(r['files'])

def coinbase(gran):
    name='coinbase-manifest.json' if gran==900 else 'coinbase-gap-probes.json';m=json.loads((ART/name).read_text())
    for r in m['records']:
        if gran==900 or r['granularity']==gran:payload(r['payload'])
    return raw_files(m['files'] if gran==900 else m['files'][str(gran)])

def validate(d):
    x=d[['open','high','low','close','volume']]
    assert x.notna().all().all() and np.isfinite(x).all().all()
    assert (x[['open','high','low','close','volume']]>0).all().all()
    assert (x.high>=x[['low','open','close']].max(axis=1)).all() and (x.low<=x[['high','open','close']].min(axis=1)).all()

def calendar(start,end):
    return xc.get_calendar('XNYS',start='2007-01-01',end='2027-01-01').schedule.loc[start:end]

def session(d,row,minutes):
    grid=pd.date_range(row.open,row.close,freq=f'{minutes}min',inclusive='left')
    block=d.loc[(d.index>=row.open)&(d.index<row.close)]
    assert block.index.equals(grid),('session missing',row.name,len(block),len(grid))
    validate(block);return block

def basic_metric(eq,annualize=True):
    total=float(eq.iloc[-1]-1);years=(eq.index[-1]-eq.index[0]).total_seconds()/86400/365.25
    return {'total_return':total,'cagr':float((1+total)**(1/years)-1) if annualize else None,'mdd':float((eq/eq.cummax()-1).min())}
