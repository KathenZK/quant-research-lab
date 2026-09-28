"""独立 V3 全历史质量台账、边界排除和实际研究门禁验收。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

from strategy_lab.data.catalog import DatasetScope, load_trusted_dataset, require_passing_trusted
from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory, sha256_file, write_canonical_json

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / 'research/platform/data-lake-governance'
spec = importlib.util.spec_from_file_location('history_v3', FAMILY / 'scripts/govern_binance_15m_history_v3.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
BOUNDARIES = FAMILY / 'specs/binance-15m-history-v3-boundaries-2026-09-06.json'


def classify_boundaries(gaps, metadata, evidence):
    by_symbol = {r['symbol']: r for r in evidence['boundaries']}
    by_code = {r['symbol']: r for r in metadata['symbols']}
    out = []
    for g in gaps.to_dict('records'):
        e = by_symbol.get(g['symbol'])
        if e is None or pd.Timestamp(e['launch_utc']) != pd.Timestamp(g['next_ts']):
            raise ValueError(f'unclassified residual gap: {g}')
        if 'EXCHANGE_INFO' in e['evidence_kind']:
            official = by_code[m.v2.code(g['symbol'])]
            if int(official['onboardDate']) != m.v2.as_ms(e['launch_utc']):
                raise ValueError(f'official metadata boundary mismatch: {g["symbol"]}')
        out.append({**g, **e, 'resolution': 'EXCLUDED_LAUNCH_OR_RELAUNCH_BOUNDARY',
            'research_action': 'reject_crossing_window_or_split_segment',
            'full_historical_calendar_verified': False})
    return pd.DataFrame(out)


def make_segments(inventory, gaps):
    records = []
    for item in inventory.to_dict('records'):
        sym = item['symbol']
        start = pd.Timestamp(item['first_ts'])
        last = pd.Timestamp(item['last_ts'])
        local = gaps[gaps.symbol.eq(sym)].sort_values('prev_ts')
        spans = []
        for g in local.to_dict('records'):
            spans.append((start, pd.Timestamp(g['prev_ts'])))
            start = pd.Timestamp(g['next_ts'])
        spans.append((start, last))
        total = 0
        for i, (a,b) in enumerate(spans):
            n = int((b-a)/pd.Timedelta(minutes=15))+1
            if n < 1:
                raise ValueError('invalid segment boundary')
            total += n
            records.append({'symbol':sym,'history_segment_id':f'{sym}#{i}',
                'start_utc':a.isoformat(),'last_bar_open_utc':b.isoformat(),
                'end_exclusive_utc':(b+pd.Timedelta(minutes=15)).isoformat(),'rows':n,
                'tradability_proven':False})
        if total != int(item['rows']):
            raise ValueError(f'segment coverage mismatch for {sym}')
    return pd.DataFrame(records)


def assert_window_within_segment(segments, symbol, start, end):
    """Closed-bar [start,end) request must be wholly within one observed segment."""
    a,b = pd.Timestamp(start),pd.Timestamp(end)
    if a.tzinfo is None or b.tzinfo is None or a >= b:
        raise ValueError('window requires ordered aware UTC boundaries')
    if m.v2.as_ms(a) % m.STEP or m.v2.as_ms(b) % m.STEP:
        raise ValueError('window is off 15m grid')
    valid = segments[segments.symbol.eq(symbol)]
    valid = valid[(pd.to_datetime(valid.start_utc,utc=True) <= a) & (pd.to_datetime(valid.end_exclusive_utc,utc=True) >= b)]
    if len(valid) != 1:
        raise ValueError('window crosses or lies outside a verified history segment')
    return valid.iloc[0].history_segment_id


def main():
    prepared = m.prepare()
    cutoff = prepared['config']['cutoff_exclusive_utc']
    loaded = load_trusted_dataset(m.DATASET,layout=m.v2.layout(),requested_scope=DatasetScope.FULL_MARKET,
        end=cutoff,purpose='governance_audit',gap_policy='report_only',max_materialize_rows=0)
    require_passing_trusted(loaded)
    con = m.v2.connect()
    con.from_parquet([str(p) for p in loaded.verified_parquet_files],hive_partitioning=False).create_view('bars')
    gaps = con.execute(m.v2.gaps_query('bars')).fetch_df()
    inventory = con.execute('SELECT symbol,min(ts) AS first_ts,max(ts) AS last_ts,count(*) AS rows,count(*) FILTER(WHERE volume=0) AS zero_volume_rows,count(*) FILTER(WHERE trade_count=0) AS zero_trade_rows,count(*) FILTER(WHERE volume>0 AND trade_count>0) AS positive_trade_rows FROM bars GROUP BY symbol ORDER BY symbol').fetch_df()
    inventory.to_csv(m.ART/'symbol_quality_inventory.csv',index=False)
    evidence = json.loads(BOUNDARIES.read_text())
    metadata = json.loads((m.PREVIOUS/'exchange_info.json').read_text())
    dispositions = classify_boundaries(gaps,metadata,evidence)
    dispositions.to_csv(m.ART/'boundary_disposition.csv',index=False)
    segments = make_segments(inventory,gaps)
    segments.to_csv(m.ART/'history_segments.csv',index=False)
    checks = []
    for g in gaps.to_dict('records'):
        try:
            assert_window_within_segment(segments,g['symbol'],g['prev_ts'],pd.Timestamp(g['next_ts'])+pd.Timedelta(minutes=15))
        except ValueError:
            checks.append({'symbol':g['symbol'],'cross_boundary_rejected':True})
        else:
            raise ValueError('boundary gate failed open')
        assert_window_within_segment(segments,g['symbol'],g['next_ts'],pd.Timestamp(g['next_ts'])+pd.Timedelta(minutes=15))
    # Exercise actual catalog research reject as well, not only a standalone helper.
    catalog_reject = False
    try:
        load_trusted_dataset(m.DATASET,layout=m.v2.layout(),requested_scope=DatasetScope.SINGLE_SYMBOL,
            symbol='AIA/USDT:USDT',start='2026-01-19T23:45:00Z',end='2026-01-20T11:30:00Z',purpose='research',gap_policy='reject')
    except ValueError as e:
        if 'missing_bars' not in str(e):
            raise
        catalog_reject = True
    if not catalog_reject:
        raise ValueError('catalog research reject failed open')
    normalized_root = m.v2.layout().normalized_dir / 'ohlcv/exchange=binance/market_type=perp/timeframe=15m'
    old_expected = json.loads((m.PREVIOUS/'old_base_protected.json').read_text())['before']
    old_actual = inventory_fingerprint(parquet_inventory(normalized_root))
    if old_actual != old_expected:
        raise ValueError('original normalized V1 changed')
    result = {'scope':'All observed 15m history in V3 at the frozen V2 cutoff; not all remote archive revisions or full PIT',
        'status':'GOVERNED_WITH_EXPLICIT_BOUNDARY_EXCLUSIONS','row_quality':loaded.audit['row_quality'],
        'input_gap_count':len(pd.read_csv(m.ART/'input_gaps.csv')),'remaining_grid_positions':int(gaps.missing_bars.sum()),
        'classified_boundary_intervals':len(dispositions),'unclassified_residual_intervals':0,
        'raw_history_is_gapless':len(gaps)==0,'historical_trading_calendar_fully_verified':False,
        'segment_count':len(segments),'segment_rows':int(segments.rows.sum()),'dataset_rows':loaded.audit['rows'],
        'zero_volume_rows':int(inventory.zero_volume_rows.sum()),'zero_trade_rows':int(inventory.zero_trade_rows.sum()),
        'research_catalog_reject_pass':catalog_reject,'boundary_checks':checks,
        'manifest_sha256':loaded.verified_identity['manifest_sha256'],'boundary_spec_sha256':sha256_file(BOUNDARIES),
        'metadata_sha256':sha256_file(m.PREVIOUS/'exchange_info.json'),'script_sha256':sha256_file(Path(__file__)),
        'original_normalized_v1_unchanged':True,'original_normalized_v1_fingerprint':old_actual,
        'history_segments_sha256':sha256_file(m.ART/'history_segments.csv'),'completed_at':m.v2.now_iso()}
    write_canonical_json(m.ART/'history_governance_closeout.json',result)
    con.close()
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


if __name__ == '__main__':
    main()
