"""冻结的 v1 未完成查询续补；新原文/回执，不触碰已发布 v1。"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from strategy_lab.data.fs import atomic_write_path
from strategy_lab.data.manifest import sha256_file, utc_now_iso, write_canonical_json

ROOT=Path(__file__).resolve().parents[4]
FAMILY=ROOT/'research/platform/data-lake-governance'
OLD=FAMILY/'artifacts/binance_v3_research_inputs_v1_20260907'
ART=FAMILY/'artifacts/binance_funding_v3_inputs_v2_20260907'
RAW=ROOT/'data/raw/funding_rates/exchange=binance/market_type=perp/source=binance_futures_funding_rate_api/run=v3_inputs_v2_20260907'
SPEC=FAMILY/'specs/binance-funding-v3-inputs-v2-2026-09-07.md'
NEXT=0.0


def freeze_plan():
    ART.mkdir(parents=True,exist_ok=True)
    RAW.mkdir(parents=True,exist_ok=True)
    (ART/'receipts').mkdir(exist_ok=True)
    p=OLD/'funding/plan.json'
    inventory=OLD/'identity_inventory.csv'
    kind=pd.read_csv(inventory).set_index('symbol').snapshot_underlying_type.to_dict()
    consumed=json.loads((OLD/'funding/published_input_receipts.json').read_text())
    completed=set()
    for r in consumed['receipts']:
        path=ROOT/r['path']
        if sha256_file(path)!=r['sha256']:
            raise ValueError('published v1 evidence changed')
        if path.parent.name=='receipts':
            completed.add(path.stem)
    jobs=[{**j,'asset_class':kind.get(j['symbol'],'UNKNOWN')} for j in json.loads(p.read_text())['jobs'] if j['job_id'] not in completed]
    jobs.sort(key=lambda j:(j['asset_class']!='COIN',j['symbol'],j['start_ms']))
    plan={'contract_sha256':sha256_file(SPEC),'parent_plan_sha256':sha256_file(p),
          'parent_manifest_sha256':sha256_file(ROOT/'data/derived/datasets/binance_perp_funding_v3_inputs_v1/_MANIFEST.json'),
          'identity_inventory_sha256':sha256_file(inventory),'jobs':jobs,
          'request_interval_seconds':2.0,'single_worker':True}
    path=ART/'plan.json'
    if path.exists() and json.loads(path.read_text())!=plan:
        raise ValueError('frozen v2 plan changed')
    write_canonical_json(path,plan)
    return plan


def request(url):
    global NEXT
    for attempt in range(3):
        time.sleep(max(0,NEXT-time.monotonic()))
        NEXT=time.monotonic()+2.0
        try:
            with urlopen(Request(url,headers={'User-Agent':'strategy-lab-funding-v2'}),timeout=25) as r:
                return r.read()
        except HTTPError as e:
            if e.code not in (500,502,503,504) or attempt==2:
                raise
        except (URLError,TimeoutError,OSError):
            if attempt==2:
                raise
        time.sleep(2**attempt)
    raise RuntimeError('request attempts exhausted')


def validate(rows,job,cursor):
    if not isinstance(rows,list):
        raise ValueError('non-list funding response')
    previous=cursor
    for x in rows:
        t=x.get('fundingTime')
        if not isinstance(t,int) or t<previous or not cursor<=t<=job['end_ms']:
            raise ValueError('funding timestamp/order/range invalid')
        if x.get('symbol')!=job['symbol'].split('/')[0]+'USDT':
            raise ValueError('wrong funding symbol')
        if not math.isfinite(float(x['fundingRate'])) or x.get('rateType') not in ('Regular','Special',None):
            raise ValueError('unknown or invalid funding value/type')
        previous=t


def fetch_job(job):
    done=ART/'receipts'/f'{job["job_id"]}.json'
    if done.exists():
        r=json.loads(done.read_text())
        if any(r[k]!=job[k] for k in ('symbol','start_ms','end_ms','job_id')):
            raise ValueError('receipt query identity changed')
        for page in r['pages']:
            if sha256_file(ROOT/page['path'])!=page['sha256']:
                raise ValueError('receipt content changed')
        return r
    cursor=job['start_ms']
    pages=[]
    for _ in range(100):
        if shutil.disk_usage(ROOT).free<30*2**30:
            raise RuntimeError('disk guard')
        url='https://fapi.binance.com/fapi/v1/fundingRate?'+urlencode({
            'symbol':job['symbol'].split('/')[0]+'USDT','startTime':cursor,'endTime':job['end_ms'],'limit':1000})
        path=RAW/f'{job["job_id"]}_{cursor}.json.gz'
        meta=path.with_suffix('.meta.json')
        if path.exists() and meta.exists():
            page=json.loads(meta.read_text())
            if page['url']!=url or sha256_file(path)!=page['sha256']:
                raise ValueError('cached response changed')
            blob=gzip.decompress(path.read_bytes())
        else:
            blob=request(url)
            validate(json.loads(blob),job,cursor)
            atomic_write_path(path,lambda p:p.write_bytes(gzip.compress(blob,mtime=0)))
            page={'path':str(path.relative_to(ROOT)),'url':url,'sha256':sha256_file(path),
                  'raw_sha256':hashlib.sha256(blob).hexdigest(),'retrieved_at':utc_now_iso()}
            write_canonical_json(meta,page)
        rows=json.loads(blob)
        validate(rows,job,cursor)
        pages.append({**page,'rows':len(rows),'cursor':cursor})
        if len(rows)<1000:
            break
        # Inclusive overlap avoids dropping another event at the final millisecond.
        next_cursor=rows[-1]['fundingTime']
        if next_cursor<=cursor:
            raise ValueError('funding pagination makes no progress')
        cursor=next_cursor
    else:
        raise ValueError('funding pagination exceeded bound')
    r={**job,'pages':pages,'rows_with_page_overlap':sum(p['rows'] for p in pages),
       'full_pagination':True,'status':'API_RETURNED_EVENTS' if any(p['rows'] for p in pages) else 'API_EMPTY_NOT_ABSENCE_PROOF',
       'completed_at':utc_now_iso()}
    write_canonical_json(done,r)
    return r


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['prepare','fetch'],default='fetch')
    parser.add_argument('--group',choices=['coin','other','all'],default='all')
    parser.add_argument('--max-jobs',type=int)
    args=parser.parse_args()
    plan=freeze_plan()
    tasks=[j for j in plan['jobs'] if args.group=='all' or (j['asset_class']=='COIN')==(args.group=='coin')]
    if args.max_jobs:
        tasks=tasks[:args.max_jobs]
    print(f'v2 planned {len(plan["jobs"])}; selected {len(tasks)}; single worker 2 sec',flush=True)
    if args.phase=='prepare':
        return
    errors=[]
    attempted=0
    for j in tasks:
        try:
            fetch_job(j)
            attempted+=1
        except Exception as e:
            record={'job':j,'type':type(e).__name__,'error':str(e),'at':utc_now_iso()}
            if isinstance(e,HTTPError):
                record.update(http_status=e.code,response=e.read(4000).decode(errors='replace'),retry_after=e.headers.get('Retry-After'))
            errors.append(record)
            write_canonical_json(ART/'fetch_error_latest.json',record)
            print(f'v2 STOP: {j["symbol"]}: {type(e).__name__}',flush=True)
            break
        if attempted%20==0 or attempted==len(tasks):
            print(f'v2 receipts {attempted}/{len(tasks)} ({j["asset_class"]})',flush=True)
        write_canonical_json(ART/'fetch_progress.json',{'attempted':attempted,'selected':len(tasks),
            'total_receipts':len(list((ART/'receipts').glob('*.json'))),'last_symbol':j['symbol'],'updated_at':utc_now_iso()})
    write_canonical_json(ART/'fetch_summary.json',{'selected':len(tasks),'completed_selected':attempted,
        'total_receipts':len(list((ART/'receipts').glob('*.json'))),'errors':errors,'finished_at':utc_now_iso()})
    if errors:
        raise RuntimeError('query stopped; successful raw evidence retained, no automatic bypass')


if __name__=='__main__':
    main()
