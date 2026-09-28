"""官方可选 symbol 的全市场近期尾部；严格保留分页边界。"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode

import pandas as pd

from strategy_lab.data.fs import atomic_write_path
from strategy_lab.data.manifest import sha256_file, utc_now_iso, write_canonical_json

ROOT=Path(__file__).resolve().parents[4]
FAMILY=ROOT/'research/platform/data-lake-governance'
ART=FAMILY/'artifacts/binance_funding_v3_inputs_v2_20260907'
RAW=ROOT/'data/raw/funding_rates/exchange=binance/market_type=perp/source=binance_futures_funding_rate_api/run=v3_inputs_v2_global_20260907'
SPEC=FAMILY/'specs/binance-funding-v2-global-tail-supplement-2026-09-07.md'


def validate_global(rows,cursor,end):
    if not isinstance(rows,list):
        raise ValueError('global funding response must be list')
    previous=cursor
    for r in rows:
        t=r.get('fundingTime')
        if (not isinstance(t,int) or t<previous or not cursor<=t<=end
            or not isinstance(r.get('symbol'),str) or not r['symbol']
            or not math.isfinite(float(r['fundingRate']))
            or r.get('rateType') not in ('Regular','Special',None)):
            raise ValueError('global funding identity/value/order invalid')
        previous=t


def main():
    if (ROOT/'data/derived/datasets/binance_perp_funding_v3_inputs_v2').exists():
        raise FileExistsError('v2 published; new retrieval requires new run')
    helper=FAMILY/'scripts/fetch_binance_funding_v2.py'
    s=importlib.util.spec_from_file_location('v2_request_helper',helper)
    m=importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    RAW.mkdir(parents=True,exist_ok=True)
    (ART/'global_receipts').mkdir(exist_ok=True)
    start=pd.Timestamp('2026-09-01T00:00:00Z')
    end=pd.Timestamp('2026-09-05T15:45:00Z')
    jobs=[]
    for day in pd.date_range(start,end.floor('D'),freq='D'):
        a=int(day.value//1_000_000)
        b=int(min(day+pd.Timedelta(days=1)-pd.Timedelta(milliseconds=1),end).value//1_000_000)
        jobs.append({'job_id':day.strftime('global_%Y%m%d'),'query_scope':'ALL_USDM','start_ms':a,'end_ms':b})
    plan={'jobs':jobs,'contract_sha256':sha256_file(SPEC),'request_helper_sha256':sha256_file(helper)}
    path=ART/'global_plan.json'
    if path.exists() and json.loads(path.read_text())!=plan:
        raise ValueError('global frozen plan changed')
    write_canonical_json(path,plan)
    results=[]
    for job in jobs:
        done=ART/'global_receipts'/f'{job["job_id"]}.json'
        if done.exists():
            receipt=json.loads(done.read_text())
            for p in receipt['pages']:
                if sha256_file(ROOT/p['path'])!=p['sha256']:
                    raise ValueError('global native evidence changed')
            results.append(receipt)
            continue
        cursor=job['start_ms']
        pages=[]
        try:
            for i in range(100):
                url='https://fapi.binance.com/fapi/v1/fundingRate?'+urlencode({'startTime':cursor,'endTime':job['end_ms'],'limit':1000})
                p=RAW/f'{job["job_id"]}_{cursor}.json.gz'
                meta=p.with_suffix('.meta.json')
                if p.exists() and meta.exists():
                    info=json.loads(meta.read_text())
                    if info['url']!=url or sha256_file(p)!=info['sha256']:
                        raise ValueError('global page fingerprint/URL mismatch')
                    raw=gzip.decompress(p.read_bytes())
                else:
                    raw=m.request(url)
                    validate_global(json.loads(raw),cursor,job['end_ms'])
                    atomic_write_path(p,lambda f:f.write_bytes(gzip.compress(raw,mtime=0)))
                    info={'path':str(p.relative_to(ROOT)),'sha256':sha256_file(p),'raw_sha256':hashlib.sha256(raw).hexdigest(),
                        'url':url,'retrieved_at':utc_now_iso()}
                    write_canonical_json(meta,info)
                rows=json.loads(raw)
                validate_global(rows,cursor,job['end_ms'])
                pages.append({**info,'rows':len(rows),'cursor':cursor})
                if len(rows)<1000:
                    break
                nxt=rows[-1]['fundingTime']
                if nxt<=cursor:
                    raise ValueError('global timestamp tie exceeds page capacity; completeness not proven')
                cursor=nxt
            else:
                raise ValueError('global pagination exceeded bound')
        except Exception as e:
            r={'job':job,'error':str(e),'type':type(e).__name__,'at':utc_now_iso()}
            if isinstance(e,HTTPError):
                r.update(http_status=e.code,response=e.read(4000).decode(errors='replace'),retry_after=e.headers.get('Retry-After'))
            write_canonical_json(ART/'global_error.json',r)
            write_canonical_json(ART/'global_summary.json',{'completed_days':len(results),'planned_days':len(jobs),'error':r})
            raise
        receipt={**job,'pages':pages,'full_pagination':True,'rows_with_page_overlap':sum(p['rows'] for p in pages),'completed_at':utc_now_iso()}
        write_canonical_json(done,receipt)
        results.append(receipt)
        print(f'global funding {job["job_id"]}: {len(pages)} pages / {receipt["rows_with_page_overlap"]} rows with overlap',flush=True)
    write_canonical_json(ART/'global_summary.json',{'completed_days':len(results),'planned_days':len(jobs),
        'pages':sum(len(r['pages']) for r in results),'error':None,'finished_at':utc_now_iso()})


if __name__=='__main__':
    main()
