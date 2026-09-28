"""全历史网格扫描、官方 API/Vision 补洞、不可变 V3 发布与验收。"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
from urllib.error import HTTPError
import zipfile

import pandas as pd

from strategy_lab.data.catalog import (
    DatasetRecord, DatasetScope, DatasetStatus, FullMarketCoverageSpec,
    load_trusted_dataset, register_derived_dataset, require_passing_trusted,
)
from strategy_lab.data.fs import atomic_write_path
from strategy_lab.data.manifest import (
    inventory_fingerprint, manifest_content_fingerprint, parquet_inventory,
    sha256_file, write_canonical_json,
)
from strategy_lab.data.models import DatasetKind, MarketType
from strategy_lab.data.resample import SourceUnionPolicy, publish_staging_dataset

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / 'research/platform/data-lake-governance'
ART = FAMILY / 'artifacts/binance_15m_history_v3_20260906'
PREVIOUS = FAMILY / 'artifacts/binance_15m_refresh_v2_20260905'
HELPER = FAMILY / 'scripts/refresh_binance_15m_v2.py'
HELPER_SHA = '93b481cb85e25d0dd819b4c684c47688545d61c66757b1657895389e47513804'
spec = importlib.util.spec_from_file_location('frozen_refresh_v2', HELPER)
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)
RUN = 'history_v3_20260906'
BASE_ID = 'binance.perp.ohlcv.15m.refreshed.v2'
DATASET = 'binance.perp.ohlcv.15m.history.v3'
SLUG = 'binance_perp_15m_history_v3'
VISION = 'https://data.binance.vision/data/futures/um'
STEP = v2.STEP
MONTHLY = 'binance_vision_kline_monthly'
DAILY = 'binance_vision_kline_daily_gap_repair'
API = v2.SOURCE
COLS = v2.NORMAL_COLUMNS


def setup():
    if sha256_file(HELPER) != HELPER_SHA:
        raise ValueError('frozen V2 helper changed')
    ART.mkdir(parents=True, exist_ok=True)
    v2.RUN = RUN  # isolated imported module; published V2 file is never edited
    v2.disk_guard()


def prepare():
    setup()
    saved = ART / 'prepared.json'
    if saved.exists():
        return json.loads(saved.read_text())
    cutoff = json.loads((PREVIOUS / 'config.json').read_text())['cutoff_exclusive_utc']
    v2.log('verify full V2 input before scanning all historical gaps')
    loaded = load_trusted_dataset(BASE_ID, layout=v2.layout(), requested_scope=DatasetScope.FULL_MARKET,
        end=cutoff, purpose='governance_audit', gap_policy='report_only', max_materialize_rows=0)
    require_passing_trusted(loaded)
    files = [str(p) for p in loaded.verified_parquet_files]
    con = v2.connect()
    con.from_parquet(files, hive_partitioning=False).create_view('base')
    gaps = con.execute(v2.gaps_query('base')).fetch_df()
    gaps.insert(0, 'gap_id', range(len(gaps)))
    gaps.to_csv(ART / 'input_gaps.csv', index=False)
    spans = con.execute('SELECT symbol,min(ts) AS first_ts,max(ts) AS last_ts,count(*) AS rows FROM base GROUP BY symbol ORDER BY symbol').fetch_df()
    spans.to_csv(ART / 'input_spans.csv', index=False)
    con.close()
    cfg = {'dataset_id': DATASET, 'base_id': BASE_ID, 'cutoff_exclusive_utc': cutoff,
        'cutoff_ms': v2.as_ms(cutoff), 'prepared_at': v2.now_iso(),
        'contract_sha256': sha256_file(FAMILY / 'specs/binance-15m-history-v3-contract-2026-09-06.md'),
        'helper_sha256': HELPER_SHA, 'input_gap_sha256': sha256_file(ART / 'input_gaps.csv'),
        'no_interpolation': True, 'no_existing_key_replacement': True}
    result = {'config': cfg, 'files': files, 'identity': loaded.verified_identity,
        'audit': loaded.audit, 'initial_disk_free': shutil.disk_usage(ROOT).free}
    write_canonical_json(ART / 'config.json', cfg)
    write_canonical_json(saved, result)
    v2.log(f'prepared gaps={len(gaps)} missing={gaps.missing_bars.sum()}')
    return result


def archive_rows(payload, filename, start_ms, end_ms):
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP CRC failure')
        names = z.namelist()
        if names != [filename.removesuffix('.zip') + '.csv']:
            raise ValueError(f'archive identity/member mismatch: {names}')
        rows = list(csv.reader(io.StringIO(z.read(names[0]).decode('utf-8-sig'))))
    if rows and rows[0][0] == 'open_time':
        expected = ['open_time','open','high','low','close','volume','close_time',
                    'quote_volume','count','taker_buy_volume','taker_buy_quote_volume','ignore']
        if rows[0] != expected:
            raise ValueError('unrecognized archive header')
        rows = rows[1:]
    if any(len(r) != 12 for r in rows):
        raise ValueError('archive row width')
    if any(not start_ms <= int(r[0]) < end_ms for r in rows):
        raise ValueError('archive time range mismatch')
    return rows


def archive_bounds(kind, date):
    start = pd.Timestamp(date, tz='UTC')
    end = start + (pd.offsets.MonthBegin(1) if kind == 'monthly' else pd.Timedelta(days=1))
    return v2.as_ms(start), v2.as_ms(end)


def fetch_archive(c, kind, date, cutoff):
    filename = f'{c}-15m-{date}.zip'
    url = f'{VISION}/{kind}/klines/{c}/15m/{filename}'
    directory = v2.layout().raw_dir / '_archives/binance/futures/um/vision' / RUN / c / kind
    directory.mkdir(parents=True, exist_ok=True)
    receipt_path = directory / (filename + '.receipt.json')
    path = directory / filename
    checksum_path = directory / (filename + '.CHECKSUM')
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt['url'] != url:
            raise ValueError('archive cache identity mismatch')
        if receipt['status'] == 'NOT_FOUND':
            return receipt, []
        payload = path.read_bytes()
        checksum = checksum_path.read_text()
        if sha256_file(path) != receipt['sha256'] or sha256_file(checksum_path) != receipt['checksum_sha256']:
            raise ValueError('archive cache hash mismatch')
    else:
        receipt = {'symbol': c, 'kind': kind, 'date': date, 'url': url, 'fetched_at': v2.now_iso()}
        try:
            payload = v2.request(url)
        except HTTPError as e:
            if e.code != 404:
                raise
            receipt.update(status='NOT_FOUND', http_status=404, response_text=e.read().decode())
            write_canonical_json(receipt_path, receipt)
            return receipt, []
        checksum = v2.request(url + '.CHECKSUM').decode()
        # Save only integrity-checked objects. A transport failure is never source absence.
        fields = checksum.strip().split()
        if len(fields) != 2 or fields[1].lstrip('*') != filename or fields[0].lower() != hashlib.sha256(payload).hexdigest():
            raise ValueError('archive CHECKSUM mismatch')
        v2.disk_guard()
        atomic_write_path(path, lambda p: p.write_bytes(payload))
        atomic_write_path(checksum_path, lambda p: p.write_text(checksum))
        receipt.update(status='VERIFIED', sha256=sha256_file(path), checksum_sha256=sha256_file(checksum_path),
            path=str(path.relative_to(ROOT)), checksum_path=str(checksum_path.relative_to(ROOT)))
        write_canonical_json(receipt_path, receipt)
    if checksum.strip().split()[0].lower() != hashlib.sha256(payload).hexdigest():
        raise ValueError('archive CHECKSUM mismatch')
    start, end = archive_bounds(kind, date)
    rows = archive_rows(payload, filename, start, end)
    # Validate the entire closed archive, not merely the subset filling a gap.
    v2.frame_from_rows(rows, c, cutoff)
    return receipt, rows


def monthly_jobs(gaps):
    out = set()
    for g in gaps:
        start = pd.Timestamp(g['prev_ts']) + pd.Timedelta(minutes=15)
        end = pd.Timestamp(g['next_ts']) - pd.Timedelta(minutes=15)
        for month in pd.period_range(start.tz_localize(None), end.tz_localize(None), freq='M'):
            out.add((v2.code(g['symbol']), 'monthly', str(month)))
    return sorted(out)


def run_parallel(jobs, fn, label, workers):
    out = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fn, job) for job in jobs]
        for i, future in enumerate(as_completed(futures), 1):
            out.append(future.result())
            if i % 25 == 0 or i == len(jobs):
                v2.log(f'{label} {i}/{len(jobs)}')
    return out


def parse_api_record(record, cutoff):
    for page in record['pages']:
        if hashlib.sha256(page['response_text'].encode()).hexdigest() != page['response_sha256']:
            raise ValueError('API receipt SHA mismatch')
    rows = v2.rows_of(record)
    if any(not record['start_ms'] <= int(r[0]) < record['end_ms'] for r in rows):
        raise ValueError('API cache request range mismatch')
    v2.frame_from_rows(rows, record['symbol'], cutoff)
    if record['status'] == 'API_UNAVAILABLE':
        try:
            error_code = json.loads(record['error'])['code']
        except (KeyError, ValueError):
            raise ValueError('unclassified API failure') from None
        if error_code not in (-1121, -1122):
            raise ValueError(f'API failure is not symbol unavailability: {record["error"]}')
    elif record['status'] != 'OK':
        raise ValueError(f'uncompleted API request: {record["status"]}')
    return rows


def alias_jobs(gaps):
    jobs = []
    for g in gaps:
        c, start, end = v2.code(g['symbol']), v2.as_ms(g['prev_ts']), v2.as_ms(g['next_ts'])+STEP
        if c == 'BNXUSDT' and start < v2.as_ms('2023-02-11T04:00:00Z'):
            alias = 'BNXUSDTSETTLED'
            end = min(end, v2.as_ms('2023-02-11T04:00:00Z'))
        elif c == 'LITUSDT' and end <= v2.as_ms('2023-01-01T00:00:00Z'):
            alias = 'LITUSDTSETTLED'
        else:
            continue
        jobs.append({'symbol': alias, 'canonical_code': c, 'start_ms': start, 'end_ms': end, 'gap_id': g['gap_id']})
    return jobs


def fetch_alias(job, cutoff):
    record = v2.fetch_window(job, f'alias_gap{job["gap_id"]}', cutoff)
    rows = parse_api_record(record, cutoff)
    path = v2.layout().raw_dir / '_archives/binance/futures/um/api/klines' / RUN / job['symbol'] / f'alias_gap{job["gap_id"]}_{job["start_ms"]}_{job["end_ms"]}.json.gz'
    return {'job': job, 'path': str(path.relative_to(ROOT)), 'sha256': sha256_file(path),
            'status': record['status'], 'returned_rows': len(rows)}, rows


def fetch(prepared, workers):
    cutoff = prepared['config']['cutoff_ms']
    gaps = pd.read_csv(ART / 'input_gaps.csv').to_dict('records')
    def api_job(g):
        job = {'symbol': v2.code(g['symbol']), 'start_ms': v2.as_ms(g['prev_ts']),
               'end_ms': v2.as_ms(g['next_ts']) + STEP}
        record = v2.fetch_window(job, f'gap{g["gap_id"]}', cutoff)
        rows = parse_api_record(record, cutoff)
        return g['gap_id'], record, rows
    apis = run_parallel(gaps, api_job, 'API gap windows', workers)
    archives = run_parallel(monthly_jobs(gaps), lambda j: fetch_archive(*j, cutoff), 'monthly ZIP + CHECKSUM', workers)
    covered = {}
    for _, r, rows in apis:
        covered.setdefault(r['symbol'], set()).update(int(x[0]) for x in rows)
    for r, rows in archives:
        covered.setdefault(r['symbol'], set()).update(int(x[0]) for x in rows)
    aliases = run_parallel(alias_jobs(gaps), lambda j: fetch_alias(j, cutoff), 'verified historical alias probes', workers)
    for receipt, rows in aliases:
        covered.setdefault(receipt['job']['canonical_code'], set()).update(int(x[0]) for x in rows)
    daily_jobs = set()
    for g in gaps:
        c = v2.code(g['symbol'])
        missing = set(range(v2.as_ms(g['prev_ts'])+STEP, v2.as_ms(g['next_ts']), STEP)) - covered.get(c, set())
        daily_jobs.update((c, 'daily', v2.iso(t)[:10]) for t in missing)
    daily = run_parallel(sorted(daily_jobs), lambda j: fetch_archive(*j, cutoff), 'daily fallback ZIP + CHECKSUM', workers)
    for r, rows in daily:
        covered.setdefault(r['symbol'], set()).update(int(x[0]) for x in rows)
    adjudications = []
    for g in gaps:
        expected = set(range(v2.as_ms(g['prev_ts'])+STEP, v2.as_ms(g['next_ts']), STEP))
        remaining = expected - covered.get(v2.code(g['symbol']), set())
        adjudications.append({**g, 'recovered_bars': len(expected)-len(remaining), 'remaining_bars': len(remaining),
            'resolution': 'RECOVERED' if not remaining else 'SOURCE_UNAVAILABLE',
            'trading_calendar_verified': False, 'research_action': 'normal_gap_gate' if not remaining else 'reject_or_split_never_fill'})
    pd.DataFrame(adjudications).to_csv(ART / 'gap_adjudication.csv', index=False)
    result = {'api_gap_ids': sorted(x[0] for x in apis), 'monthly': [r for r, _ in archives],
        'aliases': [r for r, _ in aliases], 'daily': [r for r, _ in daily], 'gaps': adjudications, 'completed_at': v2.now_iso()}
    write_canonical_json(ART / 'fetch_complete.json', result)
    v2.log(f'fetch completed recovered={sum(x["recovered_bars"] for x in adjudications)} remaining={sum(x["remaining_bars"] for x in adjudications)}')


def load_incoming(prepared):
    completed = json.loads((ART / 'fetch_complete.json').read_text())
    gaps = pd.read_csv(ART / 'input_gaps.csv')
    if completed['api_gap_ids'] != gaps.gap_id.tolist():
        raise ValueError('gap request ledger incomplete')
    cutoff = prepared['config']['cutoff_ms']
    frames, receipts = [], []
    raw_api = v2.layout().raw_dir / '_archives/binance/futures/um/api/klines' / RUN
    api_paths = sorted(raw_api.rglob('*.json.gz'))
    aliases = {str((ROOT / r['path']).resolve()): r for r in completed.get('aliases', [])}
    if len(api_paths) != len(gaps) + len(aliases):
        raise ValueError('API raw receipt count mismatch')
    for path in api_paths:
        with gzip.open(path, 'rt') as f:
            r = json.load(f)
        alias = aliases.get(str(path.resolve()))
        canonical = r['symbol'] if alias is None else alias['job']['canonical_code']
        if alias is not None and (sha256_file(path) != alias['sha256'] or r['symbol'] != alias['job']['symbol']):
            raise ValueError('alias receipt identity mismatch')
        frame = v2.frame_from_rows(parse_api_record(r, cutoff), canonical, cutoff)
        if not frame.empty:
            frames.append(frame)
        receipts.append({'path': str(path.relative_to(ROOT)), 'sha256': sha256_file(path), 'rows': len(frame), 'alias': alias})
    for r in completed['monthly'] + completed['daily']:
        actual, rows = fetch_archive(r['symbol'], r['kind'], r['date'], cutoff)
        if actual != r:
            raise ValueError('archive ledger mismatch')
        frame = v2.frame_from_rows(rows, r['symbol'], cutoff)
        if not frame.empty:
            frame['source'] = MONTHLY if r['kind'] == 'monthly' else DAILY
            frame['closure_provenance'] = 'vision_explicit_close_time_and_fixed_cutoff'
            frames.append(frame)
    write_canonical_json(ART / 'raw_receipts.json', {'api': receipts, 'vision': completed['monthly'] + completed['daily']})
    if not frames:
        raise ValueError('no recovery or overlap records')
    return pd.concat(frames, ignore_index=True), completed


def reconcile(con):
    # Exact same-source disagreement is not safely deduplicable.
    bad = con.execute('SELECT count(*) FROM (SELECT symbol,ts,source FROM incoming GROUP BY ALL HAVING count(DISTINCT (open,high,low,close,volume,quote_volume,trade_count))>1)').fetchone()[0]
    if bad:
        raise ValueError(f'same-source contradictory rows: {bad}')
    con.execute('CREATE TEMP TABLE candidates AS SELECT * FROM incoming QUALIFY row_number() OVER(PARTITION BY symbol,ts,source ORDER BY close_time)=1')
    conflicts = con.execute(f'SELECT DISTINCT a.symbol,a.ts,a.source,b.source other_source FROM candidates a JOIN candidates b USING(symbol,ts) WHERE a.source<b.source AND {v2.numeric_mismatch(con,"a","b")}').fetch_df()
    conflicts.to_csv(ART / 'cross_source_conflicts.csv', index=False)
    if len(conflicts):
        raise ValueError(f'cross-source discrepancies: {len(conflicts)}')
    con.execute(f"CREATE TEMP TABLE delta AS SELECT * FROM candidates QUALIFY row_number() OVER(PARTITION BY symbol,ts ORDER BY CASE source WHEN '{MONTHLY}' THEN 0 WHEN '{DAILY}' THEN 1 ELSE 2 END)=1")
    changes = con.execute(f'SELECT b.symbol,b.ts,b.source base_source,d.source fresh_source FROM base b JOIN delta d USING(symbol,ts) WHERE {v2.numeric_mismatch(con,"b","d")}').fetch_df()
    changes.to_csv(ART / 'base_overlap_conflicts.csv', index=False)
    if len(changes):
        raise ValueError(f'base overlap discrepancies: {len(changes)}')
    cols = ','.join(COLS)
    con.execute(f'CREATE TEMP TABLE merged AS SELECT {cols} FROM base UNION ALL SELECT {",".join("d."+x for x in COLS)} FROM delta d ANTI JOIN base b USING(symbol,ts)')


def record_for(prepared):
    return DatasetRecord(dataset_id=DATASET, layer='derived', kind=DatasetKind.OHLCV,
        status=DatasetStatus.TRUSTED_DERIVED, declared_scope=DatasetScope.FULL_MARKET,
        exchange='binance', market_type=MarketType.PERP, timeframe='15m',
        relative_root=f'derived/datasets/{SLUG}', source_adjudication='V2 keys preserved; checksum-verified Vision and API add missing keys',
        priority_union_version='binance_history_repair_v3', rebuildable=True, is_standard_ohlcv=True,
        cutoff_exclusive_utc=prepared['config']['cutoff_exclusive_utc'], input_dataset_id=BASE_ID,
        builder=str(Path(__file__).relative_to(ROOT)), coverage_spec=FullMarketCoverageSpec(),
        source_union=SourceUnionPolicy(version='already_adjudicated_v3', priority=(), passthrough=True))


def build(prepared):
    lake = v2.layout()
    published, staging = lake.derived_datasets_dir / SLUG, lake.derived_staging_dir / SLUG
    if published.exists() or staging.exists():
        raise FileExistsError('V3 target exists; never overwrite published or unexplained staging')
    incoming, completed = load_incoming(prepared)
    con = v2.connect()
    con.register('incoming_frame', incoming)
    con.execute('CREATE TEMP TABLE incoming AS SELECT * FROM incoming_frame')
    con.from_parquet(prepared['files'], hive_partitioning=False).create_view('base')
    # Every alias must match an observed old endpoint, not merely resemble a symbol name.
    for receipt in completed.get('aliases', []):
        job = receipt['job']
        with gzip.open(ROOT / receipt['path'], 'rt') as f:
            alias_record = json.load(f)
        alias_frame = v2.frame_from_rows(parse_api_record(alias_record, prepared['config']['cutoff_ms']), job['canonical_code'], prepared['config']['cutoff_ms'])
        con.register('alias_check_frame', alias_frame)
        matches = con.execute('SELECT count(*) FROM alias_check_frame i JOIN base b USING(symbol,ts) WHERE NOT '+v2.numeric_mismatch(con,'b','i')).fetchone()[0]
        if not matches:
            raise ValueError(f'alias lacks matching base endpoint: {job}')
    reconcile(con)
    audit = v2.audit_table(con, 'merged')
    gaps = con.execute(v2.gaps_query('merged')).fetch_df()
    gaps.to_csv(ART / 'remaining_gaps.csv', index=False)
    expected_remaining = sum(r['remaining_bars'] for r in completed['gaps'])
    if audit['internal_missing_bars'] != expected_remaining:
        raise ValueError('unexpected new gaps or coverage accounting failure')
    cols = ','.join(COLS)
    lost = con.execute(f'SELECT count(*) FROM (SELECT {cols} FROM base EXCEPT ALL SELECT {cols} FROM merged)').fetchone()[0]
    if lost:
        raise ValueError('old base rows lost or changed')
    # Preserve all source alternatives and API native fields; roundtrip exact comparison.
    raw_root = lake.raw_dir / 'ohlcv/exchange=binance/market_type=perp/timeframe=15m'
    raw_root.mkdir(parents=True, exist_ok=True)
    raw_files = sorted(raw_root.glob(f'source=*/date=*/{RUN}_*.parquet'))
    if not raw_files:
        con.execute(f"COPY (SELECT *,strftime(ts,'%Y-%m-%d') date FROM candidates) TO '{raw_root}' (FORMAT PARQUET,COMPRESSION ZSTD,PARTITION_BY(source,date),FILENAME_PATTERN '{RUN}_{{i}}',WRITE_PARTITION_COLUMNS true,OVERWRITE_OR_IGNORE)")
        raw_files = sorted(raw_root.glob(f'source=*/date=*/{RUN}_*.parquet'))
    con.from_parquet([str(p) for p in raw_files], hive_partitioning=False).create_view('raw_roundtrip')
    raw_cols = ','.join(dict.fromkeys([*v2.RAW_COLUMNS,*COLS,'closure_provenance','closure_as_of']))
    unequal = con.execute(f'SELECT count(*) FROM ((SELECT {raw_cols} FROM candidates EXCEPT ALL SELECT {raw_cols} FROM raw_roundtrip) UNION ALL (SELECT {raw_cols} FROM raw_roundtrip EXCEPT ALL SELECT {raw_cols} FROM candidates))').fetchone()[0]
    if unequal:
        raise ValueError('raw normalization roundtrip mismatch')
    write_canonical_json(ART / 'raw_alignment.json', {'status': 'PASS', 'unequal_rows': unequal,
        'files': [{'path': str(p.relative_to(ROOT)), 'sha256': sha256_file(p)} for p in raw_files]})
    extra_checks = con.execute('SELECT count(*) FILTER(WHERE volume=0) zero_volume_rows,count(*) FILTER(WHERE volume=0 AND quote_volume<>0) zero_volume_quote_error,count(*) FILTER(WHERE abs(vwap-CASE WHEN volume=0 THEN close ELSE quote_volume/volume END)>1e-9+1e-10*abs(vwap)) vwap_error FROM merged').fetch_df().iloc[0].to_dict()
    if extra_checks['zero_volume_quote_error'] or extra_checks['vwap_error']:
        raise ValueError(f'whole-history numeric consistency failure: {extra_checks}')
    fresh = pd.read_csv(PREVIOUS / 'symbol_freshness.csv')
    ends = dict(con.execute('SELECT symbol,max(epoch_ms(ts)) FROM merged GROUP BY symbol').fetchall())
    stale = [r['archive_symbol'] for r in fresh.to_dict('records') if r['required_latest_crypto'] and ends.get(v2.symbol(r['archive_symbol'])) != prepared['config']['cutoff_ms']-STEP]
    if stale:
        raise ValueError(f'active crypto freshness failure: {stale}')
    summary = {'dataset_id': DATASET, 'cutoff_exclusive_utc': prepared['config']['cutoff_exclusive_utc'],
        'audit': audit, 'new_rows': audit['rows']-prepared['audit']['rows'],
        'old_rows_lost_or_changed': lost, 'raw_alignment_unequal_rows': unequal,
        'required_active_crypto_symbols': int(fresh.required_latest_crypto.sum()), 'stale_active_symbols': stale,
        'extra_checks': {k: int(v) for k,v in extra_checks.items()},
        'gap_disposition': 'ALL_RECOVERED' if not len(gaps) else 'SOURCE_UNAVAILABLE_RETAINED_WITH_BLOCKERS'}
    write_canonical_json(ART / 'build_audit.json', summary)
    staging.mkdir(parents=True)
    v2.log('write independently versioned full-history V3 snapshot')
    con.execute(f"COPY (SELECT *,strftime(ts,'%Y-%m-%d') date FROM merged ORDER BY ts,symbol) TO '{staging / 'ohlcv'}' (FORMAT PARQUET,COMPRESSION ZSTD,PARTITION_BY(date))")
    inventory = parquet_inventory(staging)
    manifest = {'schema_version': '1.0', 'dataset_id': DATASET, 'layer': 'derived', 'status': 'TRUSTED_DERIVED',
        'declared_scope': 'FULL_MARKET', 'exchange': 'binance', 'market_type': 'perp', 'timeframe': '15m',
        'physical_root': str(published.resolve()), 'source_adjudication': record_for(prepared).source_adjudication,
        'priority_union_version': 'binance_history_repair_v3', 'aggregation_formula_version': 'ohlcv_15m_identity_union_history_v3',
        'input_dataset_id': BASE_ID, 'input_manifest_sha256': prepared['identity']['manifest_sha256'],
        'builder_path': str(Path(__file__).relative_to(ROOT)), 'builder_sha256': sha256_file(Path(__file__)),
        'helper_sha256': HELPER_SHA, 'generated_at': v2.now_iso(),
        'alias_evidence_sha256': sha256_file(FAMILY / 'specs/binance-15m-history-v3-alias-evidence-2026-09-06.md'),
        'cutoff_exclusive_utc': prepared['config']['cutoff_exclusive_utc'], 'start_utc': audit['start_utc'], 'end_utc': audit['end_utc'],
        'file_count': len(inventory), 'bytes': sum(r['size'] for r in inventory), 'rows': audit['rows'],
        'distinct_business_keys': audit['rows'], 'duplicate_key_rows': 0, 'symbol_count': audit['symbol_count'],
        'rebuildable': True, 'rebuild_command': f'.venv/bin/python {Path(__file__).relative_to(ROOT)} --phase all',
        'quality_status': 'TRUSTED_DERIVED', 'parquet_inventory_fingerprint': inventory_fingerprint(inventory),
        'config_sha256': sha256_file(ART / 'config.json'), 'raw_receipts_sha256': sha256_file(ART / 'raw_receipts.json'),
        'gap_adjudication_sha256': sha256_file(ART / 'gap_adjudication.csv'),
        'null_fill_policy': 'no interpolation, no generated zero bars; unresolved gaps fail research reject',
        'internal_missing_bars': audit['internal_missing_bars'],
        'known_limits': ['not a full historical remote redownload/checksum revalidation', 'observed symbol span is not listing proof',
            'current metadata is not PIT', 'official zero-volume bars are not proof of tradability', 'unavailable gaps remain coverage blockers'],
        'audit_artifact': str((ART / 'build_audit.json').relative_to(ROOT))}
    manifest['content_fingerprint'] = manifest_content_fingerprint(manifest)
    before = prepared['identity']['parquet_inventory_fingerprint']
    after = inventory_fingerprint(parquet_inventory(Path(prepared['identity']['manifest_path']).parent))
    if before != after:
        raise ValueError('protected V2 input changed')
    write_canonical_json(ART / 'protected_v2.json', {'before': before, 'after': after, 'unchanged': True})
    v2.log(publish_staging_dataset(staging_root=staging, published_root=published, manifest=manifest))
    register_derived_dataset(lake, record_for(prepared))
    con.close()


def verify(prepared):
    loaded = load_trusted_dataset(DATASET, layout=v2.layout(), requested_scope=DatasetScope.FULL_MARKET,
        end=prepared['config']['cutoff_exclusive_utc'], purpose='governance_audit', gap_policy='report_only', max_materialize_rows=0)
    require_passing_trusted(loaded)
    write_canonical_json(ART / 'acceptance.json', {'audit': loaded.audit, 'identity': loaded.verified_identity,
        'verified_files': len(loaded.verified_parquet_files), 'accepted_at': v2.now_iso(), 'disk_free_after': shutil.disk_usage(ROOT).free})
    v2.log(f'accepted V3 rows={loaded.audit["rows"]} missing={loaded.audit["internal_missing_bars"]}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase', choices=['prepare','fetch','build','verify','all'], default='prepare')
    p.add_argument('--workers', type=int, default=8)
    args = p.parse_args()
    prepared = prepare()
    if args.phase in ('fetch','all'):
        fetch(prepared, args.workers)
    if args.phase in ('build','all'):
        build(prepared)
    if args.phase in ('verify','all'):
        verify(prepared)


if __name__ == '__main__':
    main()
