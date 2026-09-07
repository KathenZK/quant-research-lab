"""独立复核高周期聚合、旧版本保护及标的身份边界；输出研究输入清单。"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory, sha256_file, utc_now_iso, write_canonical_json

ROOT=Path(__file__).resolve().parents[4]
FAMILY=ROOT/'research/platform/data-lake-governance'
ART=FAMILY/'artifacts/binance_v3_research_inputs_v1_20260907'
DATA=ROOT/'data/derived/datasets'
V3=DATA/'binance_perp_15m_history_v3'
SYMBOLS=['BTC/USDT:USDT','ETH/USDT:USDT','SOL/USDT:USDT','HYPE/USDT:USDT','BNX/USDT:USDT','AIA/USDT:USDT','LIT/USDT:USDT']


def independent_aggregation():
    c=duckdb.connect()
    c.execute("SET TimeZone='UTC'")
    c.execute('SET threads=2')
    c.execute("SET memory_limit='2GB'")
    results=[]
    c.read_parquet([str(p) for p in V3.rglob('*.parquet')],hive_partitioning=False).create_view('v3')
    for symbol in SYMBOLS:
        f=c.execute('SELECT * FROM v3 WHERE symbol=? ORDER BY ts',[symbol]).df()
        for tf,period,n in [('1h','1h',4),('4h','4h',16),('1d','1D',96)]:
            # Independent pandas grouping, not the production SQL resample helper.
            g=f.assign(bucket=f.ts.dt.floor(period)).groupby('bucket',sort=True)
            expected=g.agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),
                volume=('volume','sum'),quote_volume=('quote_volume','sum'),trade_count=('trade_count','sum'),
                count=('ts','size'),unique=('ts','nunique'),first=('ts','min'),last=('ts','max'))
            expected=expected[(expected['count']==n)&(expected['unique']==n)&(expected['first']==expected.index)
                &(expected['last']==expected.index+pd.Timedelta(minutes=15*(n-1)))
                &(expected.index+pd.Timedelta(minutes=15*n)<=pd.Timestamp('2026-09-05T15:45:00Z'))]
            expected['vwap']=np.where(expected.volume>0,expected.quote_volume/expected.volume,expected.close)
            files=[str(p) for p in (DATA/f'binance_perp_{tf}_from_15m_v2').rglob('*.parquet')]
            c.read_parquet(files,hive_partitioning=False).create_view('published',replace=True)
            actual=c.execute('SELECT * FROM published WHERE symbol=? ORDER BY ts',[symbol]).df().set_index('ts')
            if list(actual.index)!=list(expected.index):
                raise ValueError(f'{symbol}/{tf} independent keys differ')
            for col in ['open','high','low','close','volume','quote_volume','trade_count','vwap']:
                if not np.allclose(actual[col],expected[col],rtol=1e-12,atol=1e-8):
                    raise ValueError(f'{symbol}/{tf}/{col} independent values differ')
            results.append({'symbol':symbol,'timeframe':tf,'rows':len(actual),'keys_match':True,'values_match':True})
            print(f'independent pandas parity {symbol} {tf}: {len(actual)} rows',flush=True)
    c.close()
    write_canonical_json(ART/'independent_aggregation.json',{'comparisons':results,'scope':'7 symbols all observed history, 3 timeframes; full-market SQL audits separate'})


def identity_inventory():
    meta_path=FAMILY/'artifacts/binance_15m_refresh_v2_20260905/exchange_info.json'
    meta=json.loads(meta_path.read_text())
    by_code={x['symbol']:x for x in meta['symbols']}
    inventory=pd.read_csv(FAMILY/'artifacts/binance_15m_history_v3_20260906/symbol_quality_inventory.csv')
    rows=[]
    for x in inventory.to_dict('records'):
        m=by_code.get(x['symbol'].split('/')[0]+'USDT',{})
        rows.append({**x,'snapshot_underlying_type':m.get('underlyingType','UNKNOWN'),
            'snapshot_status':m.get('status','UNKNOWN'),
            'snapshot_onboard_ms':m.get('onboardDate'),
            'historical_identity_verified':False,'pit_universe_proven':False,
            'positive_observed_bars_available':int(x['positive_trade_rows'])>0,
            'policy':'historical identity requires independent dated evidence; no current-universe historical filtering'})
    pd.DataFrame(rows).to_csv(ART/'identity_inventory.csv',index=False)
    write_canonical_json(ART/'identity_policy.json',{
        'metadata_sha256':sha256_file(meta_path),'symbols':len(rows),
        'snapshot_class_counts':pd.DataFrame(rows).snapshot_underlying_type.value_counts().to_dict(),
        'default_identity_policy':'require_verified',
        'diagnostic_opt_in':'observed_diagnostic; not PIT or tradability proof',
        'zero_trade_policy':'invalidates bar and resets backward/forward segment',
        'coverage_policy':'only complete windows within one eligible segment',
        'implementation':'src/strategy_lab/data/research_inputs.py'})


def component_accounting():
    c=duckdb.connect()
    c.execute("SET TimeZone='UTC'")
    c.execute('SET threads=2')
    c.execute("SET memory_limit='2GB'")
    files=list(V3.rglob('*.parquet'))
    months=sorted({x[5:12] for p in files for x in p.parts if x.startswith('date=')})
    counts={'1h':0,'4h':0,'1d':0}
    for month in months:
        local=[str(p) for p in files if f'date={month}-' in str(p)]
        c.read_parquet(local,hive_partitioning=False).create_view('bars',replace=True)
        for tf,seconds in [('1h',3600),('4h',14400),('1d',86400)]:
            counts[tf]+=c.execute(f'SELECT count(DISTINCT(symbol,CAST(floor(epoch(ts)/{seconds}) AS BIGINT))) FROM bars').fetchone()[0]
    v3_rows=json.loads((V3/'_MANIFEST.json').read_text())['rows']
    result=[]
    for tf,n in [('1h',4),('4h',16),('1d',96)]:
        m=json.loads((DATA/f'binance_perp_{tf}_from_15m_v2/_MANIFEST.json').read_text())
        result.append({'timeframe':tf,'required_15m_components':n,'candidate_buckets':counts[tf],
            'complete_buckets':m['rows'],'excluded_incomplete_or_cutoff_buckets':counts[tf]-m['rows'],
            'input_rows':v3_rows,'used_component_rows':n*m['rows'],
            'excluded_component_rows':v3_rows-n*m['rows']})
    write_canonical_json(ART/'component_accounting.json',{'timeframes':result,
        'note':'Excluded buckets include observed span edges, V3 internal boundaries and frozen cutoff; never fabricated'})
    c.close()


def protected_versions():
    protected=[]
    for slug in ['binance_perp_15m_refreshed_v2','binance_perp_15m_history_v3',
                 'binance_perp_1h_from_15m_v1','binance_perp_4h_from_15m_v1','binance_perp_1d_from_15m_v1']:
        root=DATA/slug
        m=json.loads((root/'_MANIFEST.json').read_text())
        expected=m.get('parquet_inventory_fingerprint') or m.get('extra',{}).get('parquet_inventory_fingerprint')
        actual=inventory_fingerprint(parquet_inventory(root))
        if actual!=expected:
            raise ValueError(f'protected published content changed: {slug}')
        protected.append({'dataset_id':m['dataset_id'],'unchanged':True,'fingerprint':actual})
    old=ROOT/'data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m'
    actual=inventory_fingerprint(parquet_inventory(old))
    if actual!='c615a4c12cd8392fbf083ad2b0ffaa693d65837da19f797813e7f726d377475a':
        raise ValueError('original normalized changed')
    protected.append({'dataset_id':'binance.perp.ohlcv.15m.normalized.v1','unchanged':True,'fingerprint':actual})
    write_canonical_json(ART/'protected_versions.json',{'datasets':protected,'checked_at':utc_now_iso()})


def funding_price_scope():
    """资金旧库存可能含其他计价/命名；不能把库存代码数当作 V3 覆盖数。"""
    from strategy_lab.data.research_inputs import load_verified_funding_snapshot
    root=DATA/'binance_perp_funding_v3_inputs_v1'
    if not root.exists():
        return
    events=load_verified_funding_snapshot(root)
    price=pd.read_csv(ART/'identity_inventory.csv')[['symbol']]
    funding=events.groupby('symbol',sort=True).agg(funding_rows=('ts','size'),
        first_funding_ts=('ts','min'),last_funding_ts=('ts','max')).reset_index()
    joined=price.assign(in_v3_price_universe=True).merge(funding,how='outer',on='symbol')
    joined['in_v3_price_universe']=joined.in_v3_price_universe.eq(True)
    joined['has_funding_events']=joined.funding_rows.fillna(0).gt(0)
    joined['net_coverage_certified']=False
    joined.to_csv(ART/'funding/price_scope_inventory.csv',index=False)
    a,b=set(price.symbol),set(funding.symbol)
    write_canonical_json(ART/'funding/price_scope_audit.json',{
        'price_symbols':len(a),'funding_inventory_codes':len(b),'price_symbols_with_any_funding':len(a&b),
        'price_symbols_without_funding':sorted(a-b),'funding_codes_outside_v3_price_scope':sorted(b-a),
        'v3_manifest_sha256':sha256_file(V3/'_MANIFEST.json'),
        'funding_manifest_sha256':sha256_file(root/'_MANIFEST.json'),
        'inventory_sha256':sha256_file(ART/'funding/price_scope_inventory.csv'),
        'policy':'Outside-scope legacy codes retained for audit only; no alias or quote-currency conversion certified. Any events is not complete coverage.'})


def main():
    independent_aggregation()
    component_accounting()
    identity_inventory()
    protected_versions()
    funding_price_scope()
    datasets={}
    for tf in ['15m','1h','4h','1d']:
        root=V3 if tf=='15m' else DATA/f'binance_perp_{tf}_from_15m_v2'
        m=json.loads((root/'_MANIFEST.json').read_text())
        datasets[tf]={'dataset_id':m['dataset_id'],'manifest_sha256':sha256_file(root/'_MANIFEST.json'),
            'last_bar_open_utc':m['end_utc'],'rows':m['rows'],'symbols':m['symbol_count'],
            'last_bar_close_utc':(pd.Timestamp(m['end_utc'])+pd.Timedelta(minutes={'15m':15,'1h':60,'4h':240,'1d':1440}[tf])).isoformat()}
    funding_path=ART/'funding/acceptance.json'
    funding=json.loads(funding_path.read_text()) if funding_path.exists() else {'status':'BLOCKED_REMOTE_ACCESS_OR_PENDING','net_research_default':'REJECT'}
    write_canonical_json(ART/'research_input_bundle.json',{'bundle_id':'binance.v3.research_inputs.v1',
        'created_at':utc_now_iso(),'price_datasets':datasets,'funding':funding,
        'identity_status':'OBSERVED_VALIDITY_IMPLEMENTED_NOT_FULL_PIT',
        'old_consumers_migrated':False,'source_15m_remote_redownload':False,
        'reader_sha256':sha256_file(ROOT/'src/strategy_lab/data/research_inputs.py'),
        'independent_aggregation_sha256':sha256_file(ART/'independent_aggregation.json'),
        'identity_inventory_sha256':sha256_file(ART/'identity_inventory.csv'),
        'protected_versions_sha256':sha256_file(ART/'protected_versions.json')})
    print('price and identity bundle verification finished',flush=True)


if __name__=='__main__':
    main()
