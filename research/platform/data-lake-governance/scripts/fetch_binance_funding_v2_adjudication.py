"""有界股票双事件类型查询，以及近期全市场分页的逐币交叉核验。"""
import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError

import pandas as pd

from strategy_lab.data.manifest import sha256_file, utc_now_iso, write_canonical_json

ROOT=Path(__file__).resolve().parents[4]
FAMILY=ROOT/'research/platform/data-lake-governance'
ART=FAMILY/'artifacts/binance_funding_v3_inputs_v2_20260907'
OLD=FAMILY/'artifacts/binance_v3_research_inputs_v1_20260907'


def main():
    if (ROOT/'data/derived/datasets/binance_perp_funding_v3_inputs_v2').exists():
        raise FileExistsError('v2 already published; use a new run')
    helper=FAMILY/'scripts/fetch_binance_funding_v2.py'
    spec=importlib.util.spec_from_file_location('v2_funding_request',helper)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.ART=ART/'adjudication_evidence'
    m.RAW=ROOT/'data/raw/funding_rates/exchange=binance/market_type=perp/source=binance_futures_funding_rate_api/run=v3_inputs_v2_adjudication_20260907'
    (m.ART/'receipts').mkdir(parents=True,exist_ok=True)
    m.RAW.mkdir(parents=True,exist_ok=True)
    ambiguous=pd.read_csv(OLD/'funding/ambiguous_event_hours.csv')
    jobs=[]
    for r in ambiguous[ambiguous.hi.sub(ambiguous.lo).abs().gt(1e-12)].to_dict('records'):
        a=pd.Timestamp(r['event_hour'])
        b=a+pd.Timedelta(hours=1)-pd.Timedelta(milliseconds=1)
        jobs.append({'symbol':r['symbol'],'kind':'special_type_evidence','asset_class':'STOCK_DIAGNOSTIC',
            'start_ms':int(a.value//1_000_000),'end_ms':int(b.value//1_000_000)})
    for symbol in ['BTC','ETH','SOL','HYPE','TRX','IR','ZEC']:
        jobs.append({'symbol':symbol+'/USDT:USDT','kind':'global_tail_independent_check','asset_class':'COIN_DIAGNOSTIC',
            'start_ms':int(pd.Timestamp('2026-09-01T00:00:00Z').value//1_000_000),
            'end_ms':int(pd.Timestamp('2026-09-05T15:45:00Z').value//1_000_000)})
    for j in jobs:
        j['job_id']=hashlib.sha256(f'{j["kind"]}|{j["symbol"]}|{j["start_ms"]}|{j["end_ms"]}'.encode()).hexdigest()[:24]
    plan={'jobs':jobs,'helper_sha256':sha256_file(helper),
        'source_ambiguities_sha256':sha256_file(OLD/'funding/ambiguous_event_hours.csv')}
    path=ART/'adjudication_plan.json'
    if path.exists() and json.loads(path.read_text())!=plan:
        raise ValueError('adjudication plan changed')
    write_canonical_json(path,plan)
    completed=[]
    for j in jobs:
        try:
            r=m.fetch_job(j)
        except Exception as e:
            failure={'job':j,'error':str(e),'type':type(e).__name__,'at':utc_now_iso()}
            if isinstance(e,HTTPError):
                failure.update(http_status=e.code,response=e.read(4000).decode(errors='replace'))
            write_canonical_json(ART/'adjudication_fetch_summary.json',{'planned':len(jobs),'completed':len(completed),'error':failure})
            raise
        completed.append(r)
        print(f'adjudication query {len(completed)}/{len(jobs)}: {j["symbol"]} {j["kind"]}',flush=True)
    write_canonical_json(ART/'adjudication_fetch_summary.json',{'planned':len(jobs),'completed':len(completed),'error':None,'finished_at':utc_now_iso()})


if __name__=='__main__':
    main()
