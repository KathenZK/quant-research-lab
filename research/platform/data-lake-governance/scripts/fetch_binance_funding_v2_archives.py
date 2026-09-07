"""仅补取当前歧义所需且 v1 未保存的官方月度原文。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
from pathlib import Path

import pandas as pd

from strategy_lab.data.manifest import sha256_file, utc_now_iso, write_canonical_json

ROOT=Path(__file__).resolve().parents[4]
FAMILY=ROOT/'research/platform/data-lake-governance'
ART=FAMILY/'artifacts/binance_funding_v3_inputs_v2_20260907'
OLD=FAMILY/'artifacts/binance_v3_research_inputs_v1_20260907/funding'


def main():
    helper=FAMILY/'scripts/backfill_binance_v3_funding_archives.py'
    spec=importlib.util.spec_from_file_location('frozen_archive_reader',helper)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.ART=ART
    m.RAW=ROOT/'data/raw/_archives/binance_funding_v3_inputs_v2_20260907'
    m.RAW.mkdir(parents=True,exist_ok=True)
    for name in ['archive_receipts','archive_events']:
        (ART/name).mkdir(parents=True,exist_ok=True)
    frame=pd.read_csv(OLD/'ambiguous_event_hours.csv')
    frame['month']=pd.to_datetime(frame.event_hour,utc=True).dt.strftime('%Y-%m')
    jobs=[]
    reuse=[]
    for r in frame[['symbol','month']].drop_duplicates().to_dict('records'):
        code=r['symbol'].split('/')[0]+'USDT'
        receipt=OLD/'archive_receipts'/f'{code}_{r["month"]}.json'
        if receipt.exists() and json.loads(receipt.read_text())['status']=='CHECKSUM_AND_CRC_PASS':
            reuse.append({'path':str(receipt.relative_to(ROOT)),'sha256':sha256_file(receipt)})
        else:
            jobs.append({**r,'code':code})
    plan={'jobs':jobs,'reused':reuse,'helper_sha256':sha256_file(helper),
          'ambiguities_sha256':sha256_file(OLD/'ambiguous_event_hours.csv')}
    p=ART/'archive_plan.json'
    if p.exists() and json.loads(p.read_text())!=plan:
        raise ValueError('archive plan changed')
    write_canonical_json(p,plan)
    errors=[]
    results=[]
    print(f'v2 additional archive jobs {len(jobs)}; reused {len(reuse)}',flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(m.fetch,j):j for j in jobs}
        for i,f in enumerate(as_completed(futures),1):
            try:
                results.append(f.result())
            except Exception as e:
                errors.append({'job':futures[f],'error':str(e),'type':type(e).__name__})
            if i%20==0 or i==len(jobs):
                print(f'v2 archives {i}/{len(jobs)}; errors {len(errors)}',flush=True)
    write_canonical_json(ART/'archive_summary.json',{'jobs':len(jobs),'completed':len(results),
        'verified':sum(r['status']=='CHECKSUM_AND_CRC_PASS' for r in results),
        'official_404':sum(r['status']=='OFFICIAL_404' for r in results),
        'errors':errors,'finished_at':utc_now_iso()})
    if errors:
        raise RuntimeError('archive evidence incomplete; no absence inference')


if __name__=='__main__':
    main()
