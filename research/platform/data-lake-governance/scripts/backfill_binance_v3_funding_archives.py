"""独立公开月度归档补齐，不重试已拒绝访问的 FAPI。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
import io
import json
from pathlib import Path
import threading
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

import pandas as pd

from strategy_lab.data.fs import atomic_write_path
from strategy_lab.data.manifest import sha256_file, utc_now_iso, write_canonical_json

ROOT=Path(__file__).resolve().parents[4]
ART=ROOT/'research/platform/data-lake-governance/artifacts/binance_v3_research_inputs_v1_20260907/funding'
RAW=ROOT/'data/raw/_archives/binance_funding_v3_inputs_20260907'
HOST='https://data.binance.vision/data/futures/um/monthly/fundingRate'
STOP=threading.Event()


def request(url):
    for attempt in range(3):
        if STOP.is_set():
            raise RuntimeError('archive access stopped')
        try:
            with urlopen(Request(url,headers={'User-Agent':'strategy-lab-funding-archives'}),timeout=20) as r:
                return r.read()
        except HTTPError as e:
            if e.code in (403,418,429):
                STOP.set()
            if e.code not in (500,502,503,504) or attempt==2:
                raise
        except (TimeoutError,OSError):
            if attempt==2:
                raise
        time.sleep(2**attempt)
    raise RuntimeError('archive retry exhausted')


def fetch(job):
    code,month,symbol=job['code'],job['month'],job['symbol']
    name=f'{code}-fundingRate-{month}.zip'
    zip_path=RAW/name
    receipt_path=ART/'archive_receipts'/f'{code}_{month}.json'
    if receipt_path.exists():
        receipt=json.loads(receipt_path.read_text())
        if receipt['status']=='OFFICIAL_404':
            return receipt
        if sha256_file(zip_path)!=receipt['sha256']:
            raise ValueError('archive changed')
        return receipt
    url=f'{HOST}/{quote(code,safe="")}/{quote(name,safe="")}'
    try:
        checksum=request(url+'.CHECKSUM')
        payload=request(url)
    except HTTPError as e:
        if e.code!=404:
            raise
        r={**job,'url':url,'status':'OFFICIAL_404','retrieved_at':utc_now_iso()}
        write_canonical_json(receipt_path,r)
        return r
    expected=checksum.decode().split()[0]
    actual=hashlib.sha256(payload).hexdigest()
    if expected!=actual:
        raise ValueError('archive SHA256 mismatch')
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        if z.testzip() is not None or len(z.namelist())!=1 or not z.namelist()[0].endswith('.csv'):
            raise ValueError('invalid funding ZIP')
        f=pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    required={'calc_time','funding_interval_hours','last_funding_rate'}
    if not required.issubset(f):
        raise ValueError(f'unknown funding archive schema {list(f)}')
    ts=pd.to_datetime(f.calc_time,unit='ms',utc=True)
    a=pd.Timestamp(month+'-01',tz='UTC')
    b=a+pd.offsets.MonthBegin(1)
    if ts.isna().any() or not ts.is_monotonic_increasing or ts.duplicated().any() or not ((ts>=a)&(ts<b)).all():
        raise ValueError('archive timestamp/month mismatch')
    for col in required:
        f[col]=pd.to_numeric(f[col],errors='raise')
    import numpy as np
    if not np.isfinite(f[list(required)].to_numpy(dtype=float)).all() or not f.funding_interval_hours.gt(0).all():
        raise ValueError('archive nonfinite or invalid interval')
    atomic_write_path(zip_path,lambda p:p.write_bytes(payload))
    atomic_write_path(zip_path.with_suffix('.zip.CHECKSUM'),lambda p:p.write_bytes(checksum))
    records=[{'symbol':symbol,'ts':t.isoformat(),'funding_rate':float(rate),
        'mark_price':None,'source':'binance_vision_funding_monthly','rate_type':'UNSPECIFIED_ARCHIVE',
        'raw_receipt_sha256':actual,'archive_interval_hours':float(interval)}
        for t,rate,interval in zip(ts,f.last_funding_rate,f.funding_interval_hours)]
    events=ART/'archive_events'/f'{code}_{month}.json.gz'
    blob=gzip.compress(json.dumps(records).encode(),mtime=0)
    atomic_write_path(events,lambda p:p.write_bytes(blob))
    r={**job,'url':url,'status':'CHECKSUM_AND_CRC_PASS','sha256':actual,'rows':len(f),
       'events_path':str(events.relative_to(ROOT)),'events_sha256':sha256_file(events),'retrieved_at':utc_now_iso()}
    write_canonical_json(receipt_path,r)
    return r


def main():
    RAW.mkdir(parents=True,exist_ok=True)
    (ART/'archive_receipts').mkdir(exist_ok=True)
    (ART/'archive_events').mkdir(exist_ok=True)
    plan=json.loads((ART/'plan.json').read_text())
    jobs={}
    for j in plan['jobs']:
        if (ART/'receipts'/f'{j["job_id"]}.json').exists():
            continue
        a=pd.Timestamp(j['start_ms'],unit='ms',tz='UTC')
        b=min(pd.Timestamp(j['end_ms'],unit='ms',tz='UTC'),pd.Timestamp('2026-09-01T00:00:00Z')-pd.Timedelta(milliseconds=1))
        if a>b:
            continue
        for d in pd.date_range(a.strftime('%Y-%m-01'),b.strftime('%Y-%m-01'),freq='MS'):
            code=j['symbol'].split('/')[0]+'USDT'
            month=d.strftime('%Y-%m')
            jobs[(code,month)]={'code':code,'month':month,'symbol':j['symbol']}
    plan_path=ART/'archive_plan.json'
    if plan_path.exists():
        tasks=json.loads(plan_path.read_text())['jobs']
    else:
        tasks=list(jobs.values())
        write_canonical_json(plan_path,{'jobs':tasks})
    print(f'archive jobs {len(tasks)}',flush=True)
    results=[]
    errors=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(fetch,j):j for j in tasks}
        for i,f in enumerate(as_completed(futures),1):
            try:
                results.append(f.result())
            except Exception as e:
                errors.append({'job':futures[f],'error':str(e),'type':type(e).__name__})
                write_canonical_json(ART/'archive_errors.json',{'errors':errors})
            if i%100==0 or i==len(tasks):
                print(f'archives {i}/{len(tasks)}; errors {len(errors)}',flush=True)
    write_canonical_json(ART/'archive_summary.json',{'jobs':len(tasks),'completed':len(results),'errors':errors,
        'verified':sum(x['status']=='CHECKSUM_AND_CRC_PASS' for x in results),
        'official_404':sum(x['status']=='OFFICIAL_404' for x in results),'finished_at':utc_now_iso()})
    if errors:
        raise RuntimeError('archive jobs failed; receipts preserved, not absence proof')


if __name__=='__main__':
    main()
