"""只读交叉审计：未检索费率范围是否与 V3 的实际成交观测重合。"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from strategy_lab.data.catalog import DatasetScope, load_trusted_dataset, require_passing_trusted
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import FingerprintMode, sha256_file, utc_now_iso, write_canonical_json
from strategy_lab.data.settings import default_settings

ROOT=Path(__file__).resolve().parents[4]
ART=ROOT/'research/platform/data-lake-governance/artifacts/binance_funding_v3_inputs_v2_20260907'


def main():
    coverage=ART/'query_evidence_coverage.csv'
    ranges=[]
    for r in pd.read_csv(coverage).to_dict('records'):
        for n,(a,b) in enumerate(json.loads(r['uncovered_ranges_json'])):
            ranges.append({'job_id':r['job_id'],'symbol':r['symbol'],'asset_class':r['asset_class'],
                'range_id':f'{r["job_id"]}:{n}',
                'start':pd.Timestamp(a,unit='ms',tz='UTC'),'end':pd.Timestamp(b,unit='ms',tz='UTC')})
    intervals=pd.DataFrame(ranges)
    loaded=require_passing_trusted(load_trusted_dataset('binance.perp.ohlcv.15m.history.v3',
        layout=DataLakeLayout.from_settings(default_settings()),requested_scope=DatasetScope.FULL_MARKET,
        end=pd.Timestamp('2026-09-05T15:45:00Z'),purpose='governance_audit',
        gap_policy='report_only',max_materialize_rows=0,fingerprint_mode=FingerprintMode.STRICT_CONTENT))
    c=duckdb.connect()
    c.execute("SET TimeZone='UTC'")
    c.execute('SET threads=2')
    c.execute("SET memory_limit='2GB'")
    c.register('ranges',intervals)
    c.read_parquet([str(p) for p in loaded.verified_parquet_files],hive_partitioning=False).create_view('bars')
    result=c.execute('''SELECT r.*,count(b.ts) AS observed_bars,
        count(b.ts) FILTER(WHERE b.trade_count>0 OR b.volume>0 OR b.quote_volume>0) AS any_activity_bars,
        count(b.ts) FILTER(WHERE b.is_closed AND b.trade_count>0 AND b.volume>0 AND b.quote_volume>0) AS positive_closed_bars,
        count(b.ts) FILTER(WHERE b.trade_count=0 AND b.volume=0 AND b.quote_volume=0) AS all_zero_activity_bars,
        min(b.ts) FILTER(WHERE b.trade_count>0 OR b.volume>0 OR b.quote_volume>0) AS first_activity,
        max(b.ts) FILTER(WHERE b.trade_count>0 OR b.volume>0 OR b.quote_volume>0) AS last_activity
        FROM ranges r LEFT JOIN bars b ON b.symbol=r.symbol AND b.ts<=r."end"
        AND b.ts+INTERVAL '15 minutes'>r.start GROUP BY ALL ORDER BY symbol,start''').df()
    c.close()
    result['classification']='POSITIVE_OR_UNCERTAIN_ACTIVITY_REQUIRES_FUNDING_EVIDENCE'
    result.loc[result.observed_bars.eq(0),'classification']='NO_PRICE_OBSERVATIONS_NOT_ABSENCE_PROOF'
    result.loc[result.observed_bars.gt(0)&result.observed_bars.eq(result.all_zero_activity_bars),
        'classification']='ZERO_ACTIVITY_PRICE_EXCLUDED_NOT_ZERO_FUNDING'
    result.to_csv(ART/'uncovered_price_activity.csv',index=False)
    summary={'checked_at':utc_now_iso(),'input_query_coverage_sha256':sha256_file(coverage),
        'verified_price_identity':loaded.verified_identity,'range_count':len(result),
        'query_jobs':result.job_id.nunique(),'symbols':result.symbol.nunique(),
        'classifications':result.classification.value_counts().to_dict(),
        'positive_closed_bars':int(result.positive_closed_bars.sum()),
        'any_activity_bars':int(result.any_activity_bars.sum()),
        'absence_proven':False,'funding_zero_imputation_allowed':False,
        'note':'Overlap uses the full 15m bar interval; zero activity is price exclusion, not delisting or funding absence proof.'}
    write_canonical_json(ART/'uncovered_price_activity.json',summary)
    print(json.dumps(summary,ensure_ascii=False,default=str),flush=True)


if __name__=='__main__':
    main()
