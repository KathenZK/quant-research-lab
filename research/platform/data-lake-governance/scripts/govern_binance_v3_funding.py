"""V3 配套资金费率：来源对账、可续跑官方补齐、保守覆盖门禁。"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

import duckdb
import pandas as pd

from strategy_lab.data.fs import atomic_write_path
from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory, sha256_file, utc_now_iso, write_canonical_json

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / 'research/platform/data-lake-governance'
ART = FAMILY / 'artifacts/binance_v3_research_inputs_v1_20260907/funding'
BASE = ROOT / 'data/normalized/funding_rates/exchange=binance'
RAW = ROOT / 'data/raw/funding_rates/exchange=binance/market_type=perp/source=binance_futures_funding_rate_api/run=v3_inputs_20260907'
OUT = ROOT / 'data/derived/datasets/binance_perp_funding_v3_inputs_v1'
CUTOFF = pd.Timestamp('2026-09-05T15:45:00Z')
SOURCES = ('binance_vision_funding_monthly', 'binance_futures_funding_rate_api',
    'binance_fapi_funding_freeze_gap', 'binance_fapi_funding_prospective_oos',
    'binance_vision_funding_monthly_overlap_repair')
LOCK = threading.Lock()
NEXT_REQUEST = 0.0
HALT = threading.Event()


def connect():
    c = duckdb.connect()
    c.execute("SET TimeZone='UTC'")
    c.execute('SET threads=2')
    c.execute("SET memory_limit='2GB'")
    return c


def ms(x):
    return int(pd.Timestamp(x).value // 1_000_000)


def base_table(c):
    files = sorted(BASE.rglob('*.parquet'))
    c.read_parquet([str(p) for p in files], hive_partitioning=False, union_by_name=True).create_view('physical')
    c.execute("CREATE TEMP TABLE base AS SELECT symbol,ts,CAST(funding_rate AS DOUBLE) funding_rate,CAST(mark_price AS DOUBLE) mark_price,source FROM physical")
    bad = c.execute("SELECT count(*) FROM base WHERE ts IS NULL OR symbol IS NULL OR NOT isfinite(funding_rate) OR funding_rate IS NULL OR source NOT IN (SELECT unnest(?))", [list(SOURCES)]).fetchone()[0]
    conflicts = c.execute('SELECT symbol,ts,min(funding_rate) lo,max(funding_rate) hi FROM base GROUP BY symbol,ts HAVING hi-lo>1e-12').fetch_df()
    conflicts.to_csv(ART / 'base_exact_conflicts.csv', index=False)
    if bad or len(conflicts):
        raise ValueError(f'funding base invalid={bad}, conflicts={len(conflicts)}')
    c.execute('CREATE TEMP TABLE old AS SELECT * FROM base QUALIFY row_number() OVER(PARTITION BY symbol,ts ORDER BY source)=1')
    return files


def prepare():
    ART.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    c = connect()
    base_table(c)
    fp = inventory_fingerprint(parquet_inventory(BASE))
    spans = pd.read_csv(FAMILY / 'artifacts/binance_15m_history_v3_20260906/symbol_quality_inventory.csv')
    c.register('price_spans', spans)
    c.execute("CREATE TEMP TABLE universe AS SELECT symbol,CAST(first_ts AS TIMESTAMPTZ) start_ts,least(CAST(last_ts AS TIMESTAMPTZ)+INTERVAL '15 minutes',?) end_ts FROM price_spans", [CUTOFF.to_pydatetime()])
    jobs = c.execute("""WITH f AS (SELECT symbol,min(ts) first_ts,max(ts) last_ts FROM old GROUP BY symbol),
        prev AS (SELECT symbol,ts,lag(ts) OVER(PARTITION BY symbol ORDER BY ts) p FROM old),
        tasks AS (
            SELECT u.symbol,'tail' kind,greatest(u.start_ts,coalesce(f.last_ts-INTERVAL '24 hours',u.start_ts)) a,u.end_ts b FROM universe u LEFT JOIN f USING(symbol)
            UNION ALL SELECT u.symbol,'head',u.start_ts,least(f.first_ts+INTERVAL '1 seconds',u.end_ts) FROM universe u JOIN f USING(symbol) WHERE f.first_ts-u.start_ts>INTERVAL '8 hours 5 seconds'
            UNION ALL SELECT p.symbol,'internal',greatest(p.p-INTERVAL '1 seconds',u.start_ts),least(p.ts+INTERVAL '1 seconds',u.end_ts) FROM prev p JOIN universe u USING(symbol) WHERE p.ts-p.p>INTERVAL '8 hours 5 seconds'
        ) SELECT * FROM tasks WHERE a<b ORDER BY kind,symbol,a"""
    ).fetch_df()
    jobs['start_ms'] = jobs.a.map(ms)
    jobs['end_ms'] = jobs.b.map(ms)
    jobs['job_id'] = jobs.apply(lambda x: hashlib.sha256(f'{x.symbol}|{x.start_ms}|{x.end_ms}'.encode()).hexdigest()[:24], axis=1)
    path = ART / 'plan.json'
    plan = {'cutoff': CUTOFF.isoformat(), 'base_fingerprint': fp,
            'jobs': jobs[['symbol', 'kind', 'start_ms', 'end_ms', 'job_id']].drop_duplicates('job_id').to_dict('records'),
            'base_rows': c.execute('SELECT count(*) FROM base').fetchone()[0],
            'base_exact_unique_rows': c.execute('SELECT count(*) FROM old').fetchone()[0]}
    if path.exists() and json.loads(path.read_text()) != plan:
        raise ValueError('funding plan or input changed; require new run')
    write_canonical_json(path, plan)
    print(json.dumps({'jobs': len(plan['jobs']), 'kinds': jobs.kind.value_counts().to_dict(), 'old_unique':plan['base_exact_unique_rows']}), flush=True)
    c.close()
    return plan


def request(url):
    global NEXT_REQUEST
    for attempt in range(4):
        if HALT.is_set():
            raise RuntimeError('requests halted by rate limit')
        with LOCK:
            delay = max(0, NEXT_REQUEST-time.monotonic())
            NEXT_REQUEST = max(NEXT_REQUEST,time.monotonic()) + 1.5
        time.sleep(delay)
        try:
            with urlopen(Request(url,headers={'User-Agent':'strategy-lab-funding-governance'}),timeout=25) as r:
                return r.read()
        except HTTPError as e:
            if e.code in (403,418,429):
                HALT.set()
                raise
            if e.code not in (500,502,503,504) or attempt==3:
                raise
        except (TimeoutError,OSError):
            if attempt==3:
                raise
        time.sleep(2**attempt)
    raise RuntimeError('request exhausted')


def validate_page(rows, job, cursor):
    code = job['symbol'].split('/')[0]+'USDT'
    if not isinstance(rows,list):
        raise ValueError('API response is not list')
    last = cursor
    for x in rows:
        t = int(x['fundingTime'])
        if x['symbol'] != code or not cursor <= t <= job['end_ms'] or t < last:
            raise ValueError('funding API identity/order/range mismatch')
        if not math.isfinite(float(x['fundingRate'])):
            raise ValueError('nonfinite funding rate')
        if x.get('rateType','UNSPECIFIED_API') not in ('Regular','Special','UNSPECIFIED_API'):
            raise ValueError('unknown funding rateType; requires schema review')
        last=t


def fetch_job(job):
    done = ART / 'receipts' / (job['job_id']+'.json')
    if done.exists():
        result = json.loads(done.read_text())
        for p in result['pages']:
            if sha256_file(ROOT/p['path']) != p['sha256']:
                raise ValueError('raw funding receipt changed')
        return result
    cursor=job['start_ms']
    pages=[]
    n=0
    while cursor<=job['end_ms']:
        if shutil.disk_usage(ROOT).free<30*2**30:
            raise RuntimeError('disk guard')
        if n>=100:
            raise RuntimeError('unexpected >100 funding pages, requires inspection')
        params=dict(symbol=job['symbol'].split('/')[0]+'USDT',startTime=cursor,endTime=job['end_ms'],limit=1000)
        url='https://fapi.binance.com/fapi/v1/fundingRate?'+urlencode(params)
        file=RAW/f'{job["job_id"]}_{cursor}.json.gz'
        side=file.with_suffix('.meta.json')
        if file.exists() and side.exists():
            receipt=json.loads(side.read_text())
            if receipt['url']!=url or sha256_file(file)!=receipt['sha256']:
                raise ValueError('cached request mismatch')
            raw=gzip.decompress(file.read_bytes())
        else:
            raw=request(url)
            rows=json.loads(raw)
            validate_page(rows,job,cursor)
            blob=gzip.compress(raw,mtime=0)
            atomic_write_path(file,lambda p:p.write_bytes(blob))
            receipt={'url':url,'retrieved_at':utc_now_iso(),'path':str(file.relative_to(ROOT)),
                     'sha256':sha256_file(file),'raw_sha256':hashlib.sha256(raw).hexdigest()}
            write_canonical_json(side,receipt)
        rows=json.loads(raw)
        validate_page(rows,job,cursor)
        pages.append({**receipt,'rows':len(rows),'cursor':cursor})
        n+=1
        if len(rows)<1000:
            break
        cursor=int(rows[-1]['fundingTime'])+1
    result={**job,'pages':pages,'rows':sum(x['rows'] for x in pages),
            'status':'API_RETURNED_EVENTS' if any(x['rows'] for x in pages) else 'API_EMPTY_NOT_ABSENCE_PROOF',
            'full_pagination':True,'completed_at':utc_now_iso()}
    write_canonical_json(done,result)
    return result


def fetch(plan):
    (ART/'receipts').mkdir(exist_ok=True)
    errors=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(fetch_job,j):j for j in plan['jobs']}
        for i,f in enumerate(as_completed(futures),1):
            j=futures[f]
            try:
                f.result()
            except Exception as e:
                errors.append({'job':j,'error':str(e),'type':type(e).__name__})
                write_canonical_json(ART/'fetch_errors.json',{'errors':errors})
            if i%25==0 or i==len(futures):
                print(f'funding requests {i}/{len(futures)}, errors={len(errors)}',flush=True)
    write_canonical_json(ART/'fetch_errors.json',{'errors':errors})
    if errors:
        raise RuntimeError(f'{len(errors)} funding request failures; successful receipts preserved')


def build(plan, *, allow_partial=False):
    if OUT.exists():
        raise FileExistsError('funding output already published; use acceptance record')
    if inventory_fingerprint(parquet_inventory(BASE))!=plan['base_fingerprint']:
        raise ValueError('funding base changed')
    records=[]
    receipts=[]
    missing=[]
    for job in plan['jobs']:
        path=ART/'receipts'/f'{job["job_id"]}.json'
        if not path.exists():
            missing.append(job)
            continue
        r=json.loads(path.read_text())
        receipts.append(r)
        for page in r['pages']:
            file=ROOT/page['path']
            if sha256_file(file)!=page['sha256']:
                raise ValueError('funding raw mismatch')
            for x in json.loads(gzip.decompress(file.read_bytes())):
                records.append({'symbol':job['symbol'],'ts':pd.Timestamp(x['fundingTime'],unit='ms',tz='UTC'),
                    'funding_rate':float(x['fundingRate']),'mark_price':float(x.get('markPrice') or 'nan'),
                    'source':'binance_futures_funding_rate_api','rate_type':x.get('rateType','UNSPECIFIED_API'),
                    'raw_receipt_sha256':page['sha256']})
    archive_receipts=[]
    for path in sorted((ART/'archive_receipts').glob('*.json')):
        r=json.loads(path.read_text())
        archive_receipts.append(r)
        if r['status']!='CHECKSUM_AND_CRC_PASS':
            continue
        events_path=ROOT/r['events_path']
        if sha256_file(events_path)!=r['events_sha256']:
            raise ValueError('archive parsed events fingerprint mismatch')
        source_zip=ROOT/'data/raw/_archives/binance_funding_v3_inputs_20260907'/f'{r["code"]}-fundingRate-{r["month"]}.zip'
        if sha256_file(source_zip)!=r['sha256']:
            raise ValueError('raw archive fingerprint mismatch')
        parsed=json.loads(gzip.decompress(events_path.read_bytes()))
        with zipfile.ZipFile(io.BytesIO(source_zip.read_bytes())) as z:
            if len(z.namelist())!=1:
                raise ValueError('archive member count changed')
            raw_frame=pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
        if len(raw_frame)!=len(parsed):
            raise ValueError('archive raw/parsed row count mismatch')
        for x,raw_row in zip(parsed,raw_frame.to_dict('records')):
            if (ms(x['ts'])!=int(raw_row['calc_time'])
                or abs(x['funding_rate']-float(raw_row['last_funding_rate']))>1e-12
                or x['archive_interval_hours']!=float(raw_row['funding_interval_hours'])
                or x['symbol']!=r['symbol']):
                raise ValueError('archive raw/parsed numeric or identity mismatch')
            x['ts']=pd.Timestamp(x['ts'])
            records.append(x)
    if missing and not allow_partial:
        raise ValueError(f'{len(missing)} uncompleted funding requests; refuse full build')
    c=connect()
    base_table(c)
    incoming=pd.DataFrame(records,columns=['symbol','ts','funding_rate','mark_price','source','rate_type','raw_receipt_sha256','archive_interval_hours'])
    if incoming.empty:
        raise ValueError('no incoming funding; inspect before publish')
    c.register('incoming_frame',incoming)
    c.execute("CREATE TEMP TABLE combined AS SELECT *, 'UNSPECIFIED_LEGACY' rate_type,'' raw_receipt_sha256,CAST(NULL AS DOUBLE) archive_interval_hours FROM old UNION ALL SELECT * FROM incoming_frame")
    conflicts=c.execute("SELECT symbol,ts,min(funding_rate) lo,max(funding_rate) hi FROM combined GROUP BY symbol,ts HAVING hi-lo>1e-12").fetch_df()
    conflicts.to_csv(ART/'overlap_conflicts.csv',index=False)
    if len(conflicts):
        raise ValueError(f'{len(conflicts)} exact funding conflicts; source adjudication required')
    type_conflicts=c.execute("SELECT symbol,ts FROM combined WHERE rate_type IN ('Regular','Special') GROUP BY symbol,ts HAVING count(DISTINCT rate_type)>1").fetch_df()
    type_conflicts.to_csv(ART/'event_type_conflicts.csv',index=False)
    if len(type_conflicts):
        raise ValueError('multiple explicit funding event types at same timestamp; no silent merge')
    c.execute("""CREATE TEMP TABLE merged AS SELECT * FROM combined WHERE ts<=?
        QUALIFY row_number() OVER(PARTITION BY symbol,ts ORDER BY
        CASE WHEN rate_type IN ('Regular','Special') THEN 0 ELSE 1 END,
        CASE WHEN source='binance_futures_funding_rate_api' THEN 0 ELSE 1 END,
        raw_receipt_sha256 DESC,source)=1""",[CUTOFF.to_pydatetime()])
    # Do not round milliseconds or silently count multiple near-hour records as separate settlements.
    ambiguous=c.execute("SELECT symbol,date_trunc('hour',ts) event_hour,min(ts) min_ts,max(ts) max_ts,count(*) n_events,min(funding_rate) lo,max(funding_rate) hi FROM merged GROUP BY 1,2 HAVING count(*)>1").fetch_df()
    ambiguous.to_csv(ART/'ambiguous_event_hours.csv',index=False)
    c.register('ambiguities',ambiguous)
    c.execute("CREATE TEMP TABLE events AS SELECT m.*,a.symbol IS NULL event_unambiguous FROM merged m LEFT JOIN ambiguities a ON m.symbol=a.symbol AND date_trunc('hour',m.ts)=a.event_hour")
    c.execute("CREATE TEMP TABLE gaps AS SELECT * FROM (SELECT symbol,ts,lag(ts) OVER(PARTITION BY symbol ORDER BY ts) prev_ts FROM merged) WHERE ts-prev_ts>INTERVAL '8 hours 5 seconds'")
    gaps=c.execute('SELECT * FROM gaps').fetch_df()
    gaps.to_csv(ART/'remaining_long_intervals.csv',index=False)
    spans=c.execute('SELECT symbol,min(ts) first_ts,max(ts) last_ts,count(*) n_rows,count(*) FILTER(WHERE NOT event_unambiguous) ambiguous_rows FROM events GROUP BY symbol ORDER BY symbol').fetch_df()
    spans.to_csv(ART/'symbol_inventory.csv',index=False)
    coverage=pd.DataFrame([{k:r[k] for k in ['symbol','kind','start_ms','end_ms','rows','status','job_id']} for r in receipts]
        +[{**r,'rows':0,'status':'REQUEST_NOT_COMPLETED_NOT_ABSENCE_PROOF'} for r in missing])
    coverage.to_csv(ART/'query_coverage.csv',index=False)
    stage=Path(tempfile.mkdtemp(prefix='funding_v3_',dir=ROOT/'data/derived/_staging'))
    c.execute(f"COPY (SELECT *,strftime(ts,'%Y-%m') AS funding_month FROM events ORDER BY symbol,ts) TO '{stage/'funding'}' (FORMAT PARQUET,COMPRESSION ZSTD,PARTITION_BY(funding_month))")
    inv=parquet_inventory(stage)
    receipt_files=[ART/'receipts'/f'{r["job_id"]}.json' for r in receipts]
    receipt_files+=sorted((ART/'archive_receipts').glob('*.json'))
    input_index={'base_root':str(BASE.relative_to(ROOT)),'base_fingerprint':plan['base_fingerprint'],
        'receipts':[{'path':str(p.relative_to(ROOT)),'sha256':sha256_file(p)} for p in receipt_files],
        'note':'Frozen consumed evidence set; future downloads must not retroactively expand this snapshot'}
    index_path=ART/'published_input_receipts.json'
    if index_path.exists() and json.loads(index_path.read_text())!=input_index:
        raise ValueError('published evidence set changed; require a new snapshot/run')
    write_canonical_json(index_path,input_index)
    summary={'dataset_id':'binance.perp.funding.v3_inputs.v1','kind':'funding_rates','status':'PARTIAL_COVERAGE',
        'rows':int(spans.n_rows.sum()),'symbols':len(spans),'start_utc':str(spans.first_ts.min()),'end_utc':str(spans.last_ts.max()),
        'base_fingerprint':plan['base_fingerprint'],'cutoff_exclusive_utc':CUTOFF.isoformat(),
        'new_exact_keys':int(spans.n_rows.sum())-plan['base_exact_unique_rows'],
        'exact_conflicts':len(conflicts),'ambiguous_event_hours':len(ambiguous),'long_intervals_over_8h':len(gaps),
        'row_quality':'PASS','full_historical_funding_calendar_verified':False,
        'net_research_default':'REJECT_UNVERIFIED_COVERAGE_OR_AMBIGUOUS_EVENT_HOURS',
        'query_jobs':len(plan['jobs']),'completed_query_jobs':len(receipts),'pending_query_jobs':len(missing),
        'verified_archive_months':sum(r['status']=='CHECKSUM_AND_CRC_PASS' for r in archive_receipts),
        'archive_404_months':sum(r['status']=='OFFICIAL_404' for r in archive_receipts),
        'archive_raw_roundtrip':'PASS',
        'empty_queries':sum(r['rows']==0 for r in receipts),
        'parquet_inventory_fingerprint':inventory_fingerprint(inv),'file_count':len(inv),'bytes':sum(x['size'] for x in inv),
        'builder_path':str(Path(__file__).relative_to(ROOT)),'builder_sha256':sha256_file(Path(__file__)),
        'same_timestamp_adjudication':'require equal rates and no explicit type conflict; explicit API type then API source then deterministic receipt hash',
        'plan_sha256':sha256_file(ART/'plan.json'),'generated_at':utc_now_iso(),
        'input_receipts_index':str(index_path.relative_to(ROOT)),
        'input_receipts_index_sha256':sha256_file(index_path),
        'known_limits':['not OHLCV; separate funding loader required','timestamps not rounded',
            'API empty not absence proof','observed gaps not historical settlement calendar',
            'ambiguous event hours retained but denied for net accounting','legacy rate_type unspecified']}
    write_canonical_json(stage/'_MANIFEST.json',summary)
    stage.rename(OUT)
    c.close()
    # Independent readback of the published funding keys and values.
    check=connect()
    check.read_parquet([str(p) for p in OUT.rglob('*.parquet')],hive_partitioning=False).create_view('p')
    n,keys,bad=check.execute('SELECT count(*),count(DISTINCT(symbol,ts)),count(*) FILTER(WHERE funding_rate IS NULL OR NOT isfinite(funding_rate)) FROM p').fetchone()
    if n!=summary['rows'] or n!=keys or bad:
        raise ValueError('published funding verification failed')
    if inventory_fingerprint(parquet_inventory(BASE))!=plan['base_fingerprint']:
        raise ValueError('legacy funding changed')
    summary['published_verification']='PASS'
    summary['legacy_funding_unchanged']=True
    write_canonical_json(ART/'acceptance.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--phase',choices=['prepare','fetch','build','all'],default='all')
    p.add_argument('--allow-partial',action='store_true',help='Publish explicit PARTIAL_COVERAGE only; never imply completed funding')
    args=p.parse_args()
    plan=prepare()
    if args.phase in ('fetch','all'):
        fetch(plan)
    if args.phase in ('build','all'):
        build(plan,allow_partial=args.allow_partial)


if __name__=='__main__':
    main()
