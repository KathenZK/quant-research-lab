"""从不可变 V3 发布配套高周期；冻结旧脚本不改写。"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from strategy_lab.data.catalog import (
    DatasetRecord, DatasetScope, DatasetStatus, FullMarketCoverageSpec,
    load_trusted_dataset, register_derived_dataset, require_passing_trusted,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import (
    inventory_fingerprint, manifest_content_fingerprint, parquet_inventory,
    sha256_file, utc_now_iso, write_canonical_json,
)
from strategy_lab.data.models import DatasetKind, MarketType
from strategy_lab.data.resample import SourceUnionPolicy, resample_cte_sql
from strategy_lab.data.settings import default_settings
from strategy_lab.data.sql_audit import audit_selected_sql

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / 'research/platform/data-lake-governance'
ART = FAMILY / 'artifacts/binance_v3_research_inputs_v1_20260907'
CONTRACT = FAMILY / 'specs/binance-v3-research-inputs-v1-2026-09-07.md'
INPUT_ID = 'binance.perp.ohlcv.15m.history.v3'
INPUT_SHA = 'e90fe921e03bccf78dea0b29675470a3661baa5cd38af8dadc2202bb0e475e8f'
CUTOFF = pd.Timestamp('2026-09-05T15:45:00Z')
UNION = 'v3_already_adjudicated_passthrough_v1'
COLS = ['ts', 'exchange', 'symbol', 'market_type', 'timeframe', 'open', 'high',
        'low', 'close', 'volume', 'quote_volume', 'trade_count', 'vwap', 'is_closed', 'source']
SECONDS = {'1h': 3600, '4h': 14400, '1d': 86400}


def layout():
    return DataLakeLayout.from_settings(default_settings())


def connect():
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    con.execute('SET threads=2')
    con.execute("SET memory_limit='3GB'")
    con.execute('SET preserve_insertion_order=false')
    return con


def record(tf):
    return DatasetRecord(
        dataset_id=f'binance.perp.ohlcv.{tf}.from_15m.v2', layer='derived',
        kind=DatasetKind.OHLCV, status=DatasetStatus.TRUSTED_DERIVED,
        declared_scope=DatasetScope.FULL_MARKET, exchange='binance',
        market_type=MarketType.PERP, timeframe=tf,
        relative_root=f'derived/datasets/binance_perp_{tf}_from_15m_v2',
        source_adjudication='V3 already adjudicated; complete UTC buckets; no source refilter',
        priority_union_version=UNION, rebuildable=True, is_standard_ohlcv=True,
        cutoff_exclusive_utc=CUTOFF.isoformat(), input_dataset_id=INPUT_ID,
        builder=str(Path(__file__).relative_to(ROOT)), coverage_spec=FullMarketCoverageSpec(),
        source_union=SourceUnionPolicy(version=UNION, priority=(), passthrough=True))


def aggregate_sql(tf):
    if tf not in SECONDS:
        raise ValueError('unsupported timeframe')
    return f"WITH {resample_cte_sql(tf, source_alias='bars')} SELECT {','.join(COLS)} FROM complete_bars WHERE ts+INTERVAL '{SECONDS[tf]} seconds' <= TIMESTAMPTZ '{CUTOFF.isoformat()}'"


def segments_sql(tf, table='output'):
    step = SECONDS[tf]
    return f"""WITH previous AS (
        SELECT symbol,ts,lag(ts) OVER(PARTITION BY symbol ORDER BY ts) prev FROM {table}
    ), numbered AS (
        SELECT *,sum(CASE WHEN prev IS NULL OR ts-prev != INTERVAL '{step} seconds' THEN 1 ELSE 0 END)
        OVER(PARTITION BY symbol ORDER BY ts) segment_id FROM previous
    ) SELECT symbol,segment_id,min(ts) start_utc,max(ts) last_bar_open_utc,
        max(ts)+INTERVAL '{step} seconds' end_exclusive_utc,count(*) n_rows
        FROM numbered GROUP BY symbol,segment_id ORDER BY symbol,segment_id"""


def verify(tf):
    rec = record(tf)
    root = rec.absolute_root(layout())
    m = json.loads((root / '_MANIFEST.json').read_text())
    if m['input_manifest_sha256'] != INPUT_SHA or m['builder_sha256'] != sha256_file(Path(__file__)):
        raise ValueError('published identity changed')
    loaded = require_passing_trusted(load_trusted_dataset(
        rec.dataset_id, layout=layout(), requested_scope=DatasetScope.FULL_MARKET,
        end=CUTOFF.floor(tf).isoformat(), purpose='governance_audit', gap_policy='report_only',
        max_materialize_rows=0))
    con = connect()
    con.read_parquet([str(p) for p in loaded.verified_parquet_files], hive_partitioning=False).create_view('output')
    segments = con.execute(segments_sql(tf)).fetch_df()
    if int(segments.n_rows.sum()) != loaded.audit['rows']:
        raise ValueError('segment row mismatch')
    segments.to_csv(ART / f'{tf}_segments.csv', index=False)
    result = {'dataset_id': rec.dataset_id, 'audit': loaded.audit,
              'manifest_sha256': sha256_file(root / '_MANIFEST.json'),
              'segment_count': len(segments), 'segments_sha256': sha256_file(ART / f'{tf}_segments.csv'),
              'verified_at': utc_now_iso()}
    write_canonical_json(ART / f'{tf}_acceptance.json', result)
    con.close()
    print(json.dumps({'verified': rec.dataset_id, 'rows': loaded.audit['rows'], 'segments': len(segments)}), flush=True)
    return result


def build(tf, input_files):
    rec = record(tf)
    out = rec.absolute_root(layout())
    if out.exists():
        register_derived_dataset(layout(), rec)
        return verify(tf)
    if shutil.disk_usage(ROOT).free < 30 * 2**30:
        raise RuntimeError('disk free below 30 GiB')
    staging_base = layout().derived_staging_dir
    staging_base.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f'v3_{tf}_', dir=staging_base))
    con = connect()
    # Month boundaries are UTC midnight, valid boundaries for all supported buckets.
    months = sorted({part[5:12] for p in input_files for part in p.parts if part.startswith('date=')})
    for month in months:
        files = [str(p) for p in input_files if f'date={month}-' in str(p)]
        if not files:
            continue
        con.read_parquet(files, hive_partitioning=False).create_view('bars', replace=True)
        query = aggregate_sql(tf)
        print(f'build {tf} {month}', flush=True)
        con.execute(f"COPY (SELECT *,strftime(ts,'%Y-%m-%d') AS date FROM ({query})) TO '{stage / 'ohlcv'}' (FORMAT PARQUET,COMPRESSION ZSTD,PARTITION_BY(date),OVERWRITE_OR_IGNORE)")
    files = sorted(stage.rglob('*.parquet'))
    con.read_parquet([str(p) for p in files], hive_partitioning=False).create_view('output')
    audit = audit_selected_sql(con, selected_cte='selected AS (SELECT * FROM output)', params=[],
        timeframe=tf, require_closed=True, columns=COLS, files=files,
        expected_exchange='binance', expected_market_type='perp')
    if audit['quality_status'] != 'PASS':
        raise ValueError(audit)
    write_canonical_json(ART / f'{tf}_build_audit.json', audit)
    inv = parquet_inventory(stage)
    upstream = layout().derived_datasets_dir / 'binance_perp_15m_history_v3'
    if sha256_file(upstream / '_MANIFEST.json') != INPUT_SHA:
        raise ValueError('upstream manifest changed')
    m = dict(schema_version='1.0', dataset_id=rec.dataset_id, layer='derived', status='TRUSTED_DERIVED',
        declared_scope='FULL_MARKET', exchange='binance', market_type='perp', timeframe=tf,
        physical_root=str(out), source_adjudication=rec.source_adjudication, priority_union_version=UNION,
        aggregation_formula_version='ohlcv_resample_from_15m_v1', input_dataset_id=INPUT_ID,
        input_manifest_sha256=INPUT_SHA, builder_path=str(Path(__file__).relative_to(ROOT)),
        builder_sha256=sha256_file(Path(__file__)), generated_at=utc_now_iso(),
        cutoff_exclusive_utc=CUTOFF.isoformat(), start_utc=audit['start_utc'], end_utc=audit['end_utc'],
        file_count=len(inv), bytes=sum(x['size'] for x in inv), rows=audit['rows'],
        distinct_business_keys=audit['rows'], duplicate_key_rows=0, symbol_count=audit['symbol_count'],
        rebuildable=True, rebuild_command=f'.venv/bin/python {Path(__file__).relative_to(ROOT)} --timeframe {tf}',
        quality_status='TRUSTED_DERIVED', parquet_inventory_fingerprint=inventory_fingerprint(inv),
        contract_sha256=sha256_file(CONTRACT), aggregation_impl_sha256=sha256_file(ROOT / 'src/strategy_lab/data/resample.py'),
        null_fill_policy='no fill; require 4/16/96 components; retain official zero volume',
        known_limits=['V3 boundary exclusions inherited', 'not PIT identity proof', 'zero volume not tradability',
                      'funding independent; old research not automatically migrated'],
        internal_missing_bars=audit['internal_missing_bars'])
    m['content_fingerprint'] = manifest_content_fingerprint(m)
    write_canonical_json(stage / '_MANIFEST.json', m)
    stage.rename(out)
    register_derived_dataset(layout(), rec)
    con.close()
    return verify(tf)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--timeframe', choices=['1h', '4h', '1d', 'all'], default='all')
    args = p.parse_args()
    ART.mkdir(parents=True, exist_ok=True)
    if sha256_file(layout().derived_datasets_dir / 'binance_perp_15m_history_v3/_MANIFEST.json') != INPUT_SHA:
        raise ValueError('wrong V3 input manifest')
    print('validate full V3 input', flush=True)
    loaded = require_passing_trusted(load_trusted_dataset(INPUT_ID, layout=layout(),
        requested_scope=DatasetScope.FULL_MARKET, end=CUTOFF, purpose='governance_audit',
        gap_policy='report_only', max_materialize_rows=0))
    before = loaded.verified_identity['parquet_inventory_fingerprint']
    write_canonical_json(ART / 'input_acceptance.json', {'audit': loaded.audit,
        'manifest_sha256': INPUT_SHA, 'parquet_inventory_fingerprint': before})
    for tf in SECONDS:
        if args.timeframe in ('all', tf):
            build(tf, list(loaded.verified_parquet_files))
    actual = inventory_fingerprint(parquet_inventory(layout().derived_datasets_dir / 'binance_perp_15m_history_v3'))
    if actual != before:
        raise ValueError('V3 content changed during build')
    write_canonical_json(ART / 'price_complete.json', {'completed_at': utc_now_iso(),
        'requested_timeframe': args.timeframe, 'v3_unchanged': True, 'input_fingerprint': before})


if __name__ == '__main__':
    main()
