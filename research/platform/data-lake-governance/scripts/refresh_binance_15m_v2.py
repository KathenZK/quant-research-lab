"""增量刷新 Binance 15m；旧数据只读，新版本审计后发布。"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

import duckdb
import numpy as np
import pandas as pd

from strategy_lab.data.catalog import (
    BINANCE_PERP_15M_NORMALIZED_V1, DatasetRecord, DatasetScope,
    DatasetStatus, FullMarketCoverageSpec, load_trusted_dataset,
    register_derived_dataset, require_passing_trusted,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import (
    inventory_fingerprint, manifest_content_fingerprint, parquet_inventory,
    sha256_file, write_canonical_json,
)
from strategy_lab.data.models import DatasetKind, MarketType
from strategy_lab.data.resample import (
    DEFAULT_SOURCE_UNION, SourceUnionPolicy, publish_staging_dataset,
    source_priority_sql,
)
from strategy_lab.data.settings import default_settings
from strategy_lab.data.sql_audit import audit_selected_sql

ROOT = Path(__file__).resolve().parents[4]
FAMILY = ROOT / 'research/platform/data-lake-governance'
ART = FAMILY / 'artifacts/binance_15m_refresh_v2_20260905'
RUN = 'refresh_v2_20260905'
DATASET = 'binance.perp.ohlcv.15m.refreshed.v2'
SLUG = 'binance_perp_15m_refreshed_v2'
FAPI = 'https://fapi.binance.com'
S3 = 'https://s3-ap-northeast-1.amazonaws.com/data.binance.vision'
SOURCE = 'binance_futures_kline_api'
STEP = 900000
RAW_COLUMNS = ['open_time', 'open', 'high', 'low', 'close', 'volume',
               'close_time', 'quote_volume', 'trade_count', 'taker_buy_volume',
               'taker_buy_quote_volume', 'ignore']
NUMERIC = ['open', 'high', 'low', 'close', 'volume', 'quote_volume',
           'trade_count', 'taker_buy_volume', 'taker_buy_quote_volume']
NORMAL_COLUMNS = ['ts', 'exchange', 'symbol', 'market_type', 'timeframe',
                  'open', 'high', 'low', 'close', 'volume', 'quote_volume',
                  'trade_count', 'vwap', 'is_closed', 'source']
LOCK = threading.Lock()
NEXT_REQUEST = 0.0


def log(message):
    print(message, flush=True)


def layout():
    return DataLakeLayout.from_settings(default_settings())


def connect():
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    con.execute("SET threads=4")
    con.execute("SET memory_limit='4GB'")
    con.execute('SET enable_progress_bar=false')
    return con


def disk_guard():
    if shutil.disk_usage(ROOT).free < 30 * 1024**3:
        raise RuntimeError('磁盘剩余小于 30 GiB，停止')


def request(url):
    global NEXT_REQUEST
    for attempt in range(5):
        with LOCK:
            delay = max(0, NEXT_REQUEST - time.monotonic())
            NEXT_REQUEST = max(NEXT_REQUEST, time.monotonic()) + 0.4
        time.sleep(delay)
        try:
            with urlopen(Request(url, headers={'User-Agent': 'strategy-lab-15m-refresh-v2'}), timeout=25) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 4:
                raise
            retry = max(float(exc.headers.get('Retry-After', '0')), min(20, 2**attempt))
            with LOCK:
                NEXT_REQUEST = max(NEXT_REQUEST, time.monotonic() + retry)
            time.sleep(min(retry, 30))
        except (TimeoutError, OSError):
            if attempt == 4:
                raise
            time.sleep(min(8, 2**attempt))
    raise RuntimeError('request retry exhausted')


def now_iso():
    return pd.Timestamp.now(tz='UTC').isoformat()


def iso(ms):
    return pd.Timestamp(ms, unit='ms', tz='UTC').isoformat()


def as_ms(value):
    return int(pd.Timestamp(value).value // 1000000)


def code(symbol):
    return symbol.split('/')[0] + 'USDT'


def symbol(code_):
    return code_[:-4] + '/USDT:USDT'


def frame_from_rows(rows, code_, cutoff):
    """Strict API schema, numeric, grid and explicit closure provenance validation."""
    if not rows:
        return pd.DataFrame(columns=NORMAL_COLUMNS)
    if any(len(row) != 12 for row in rows):
        raise ValueError('unexpected API kline width')
    raw = pd.DataFrame(rows, columns=RAW_COLUMNS)
    opens = pd.to_numeric(raw.open_time, errors='raise')
    closes = pd.to_numeric(raw.close_time, errors='raise')
    if ((opens % STEP) != 0).any() or (closes != opens + STEP - 1).any():
        raise ValueError('off-grid open or invalid close_time')
    if opens.duplicated().any() or not opens.is_monotonic_increasing:
        raise ValueError('duplicate/non-monotonic API bars')
    if (opens + STEP > cutoff).any():
        raise ValueError('open candle exceeds frozen cutoff')
    for col in NUMERIC:
        raw[col] = pd.to_numeric(raw[col], errors='raise')
    if not np.isfinite(raw[NUMERIC].to_numpy(dtype=float)).all():
        raise ValueError('non-finite API field')
    if (raw[['open', 'high', 'low', 'close']] <= 0).any().any():
        raise ValueError('nonpositive OHLC')
    if (raw.high < raw[['open', 'close', 'low']].max(axis=1)).any() or (raw.low > raw[['open', 'close', 'high']].min(axis=1)).any():
        raise ValueError('illegal OHLC')
    if (raw[['volume', 'quote_volume', 'trade_count', 'taker_buy_volume', 'taker_buy_quote_volume']] < 0).any().any():
        raise ValueError('negative volume/count')
    if (raw.trade_count != np.floor(raw.trade_count)).any():
        raise ValueError('fractional trade_count')
    if ((raw.volume == 0) & (raw.quote_volume != 0)).any():
        raise ValueError('zero base volume with nonzero quote volume')
    raw['ts'] = pd.to_datetime(opens, unit='ms', utc=True)
    raw['exchange'], raw['symbol'], raw['market_type'], raw['timeframe'] = 'binance', symbol(code_), 'perp', '15m'
    raw['vwap'] = raw.quote_volume / raw.volume.replace(0, np.nan)
    raw['vwap'] = raw.vwap.fillna(raw.close)
    raw['is_closed'] = (closes < cutoff) & (opens + STEP <= cutoff)
    raw['source'] = SOURCE
    raw['closure_provenance'] = 'fapi_close_time_plus_fixed_server_cutoff'
    raw['closure_as_of'] = iso(cutoff)
    return raw


def gaps_query(table):
    return f"""WITH ordered AS (
      SELECT symbol, ts, lag(ts) OVER (PARTITION BY symbol ORDER BY ts) AS prev_ts FROM {table}
    ) SELECT symbol, prev_ts, ts AS next_ts,
      CAST((epoch_ms(ts)-epoch_ms(prev_ts))/{STEP}-1 AS BIGINT) AS missing_bars
    FROM ordered WHERE epoch_ms(ts)-epoch_ms(prev_ts)>{STEP} ORDER BY symbol,prev_ts"""


def archive_symbols():
    token = None
    out = []
    while True:
        params = {'list-type': '2', 'delimiter': '/', 'prefix': 'data/futures/um/monthly/klines/', 'max-keys': 1000}
        if token:
            params['continuation-token'] = token
        xml = ET.fromstring(request(S3 + '?' + urlencode(params)))
        ns = {'s': 'http://s3.amazonaws.com/doc/2006-03-01/'}
        out.extend(e.text.rstrip('/').split('/')[-1] for e in xml.findall('s:CommonPrefixes/s:Prefix', ns))
        if xml.findtext('s:IsTruncated', namespaces=ns) != 'true':
            return sorted(x for x in out if x.endswith('USDT') and '_' not in x)
        token = xml.findtext('s:NextContinuationToken', namespaces=ns)
        if not token:
            raise ValueError('missing S3 continuation token')


def prepare():
    disk_guard()
    ART.mkdir(parents=True, exist_ok=True)
    if (ART / 'prepared.json').exists():
        return json.loads((ART / 'prepared.json').read_text())
    if (ART / 'config.json').exists():
        config = json.loads((ART / 'config.json').read_text())
        meta = json.loads((ART / 'exchange_info.json').read_text())
    else:
        server = json.loads(request(FAPI + '/fapi/v1/time'))
        cutoff = int(server['serverTime']) // STEP * STEP
        meta = json.loads(request(FAPI + '/fapi/v1/exchangeInfo'))
        config = {'dataset_id': DATASET, 'run_id': RUN, 'cutoff_ms': cutoff,
                  'cutoff_exclusive_utc': iso(cutoff), 'server_time': server,
                  'prepared_at': now_iso(), 'base_id': BINANCE_PERP_15M_NORMALIZED_V1,
                  'overlap_days': 1, 'requests_per_second': 2.5,
                  'existing_keys': 'preserve_accepted_base_and_report_conflicts',
                  'script_sha256': sha256_file(Path(__file__)),
                  'contract_sha256': sha256_file(FAMILY / 'specs/binance-15m-refresh-v2-contract-2026-09-05.md')}
        write_canonical_json(ART / 'exchange_info.json', meta)
        write_canonical_json(ART / 'config.json', config)
    log('verify base strict content and full SQL')
    loaded = load_trusted_dataset(BINANCE_PERP_15M_NORMALIZED_V1, layout=layout(),
        requested_scope=DatasetScope.FULL_MARKET, purpose='governance_audit',
        gap_policy='report_only', max_materialize_rows=0)
    require_passing_trusted(loaded)
    files = [str(x) for x in loaded.verified_parquet_files]
    write_canonical_json(ART / 'base_audit.json', loaded.audit)
    con = connect()
    union_sql, params = source_priority_sql(DEFAULT_SOURCE_UNION)
    con.execute(f"CREATE TEMP TABLE base AS WITH raw AS (SELECT * FROM read_parquet(?, hive_partitioning=false, union_by_name=true)) {union_sql}", [files, *params])
    spans = con.execute('SELECT symbol, min(ts) AS first_ts,max(ts) AS last_ts,count(*) AS rows FROM base GROUP BY symbol ORDER BY symbol').fetch_df()
    gaps = con.execute(gaps_query('base')).fetch_df()
    spans.to_csv(ART / 'base_spans.csv', index=False)
    gaps.to_csv(ART / 'base_gaps.csv', index=False)
    old = {code(r['symbol']): r for r in spans.to_dict('records')}
    members = {x['symbol']: x for x in meta['symbols'] if x.get('quoteAsset') == 'USDT' and x.get('contractType') in ('PERPETUAL','TRADIFI_PERPETUAL')}
    archived = archive_symbols()
    write_canonical_json(ART / 'archive_symbol_inventory.json', {'symbols': archived, 'queried_at': now_iso(), 'scope': 'directory_names_not_listing_evidence'})
    last_global = as_ms(spans.last_ts.max())
    jobs = []
    for c in sorted(set(old) | set(members) | set(archived)):
        m = members.get(c, {})
        start = last_global - 86400000
        if c in old:
            recent_last = as_ms(old[c]['last_ts'])
            if m.get('status') == 'TRADING':
                start = max(as_ms(old[c]['first_ts']), recent_last - 86400000)
        elif m.get('onboardDate'):
            start = max(as_ms('2019-09-01T00:00:00Z'), int(m['onboardDate']) // STEP * STEP)
        jobs.append({'symbol': c, 'start_ms': start, 'end_ms': config['cutoff_ms'],
                     'metadata': m, 'existing': c in old, 'archive_present': c in archived})
    prepared = {'config': config, 'files': files, 'base_fingerprint': loaded.manifest['parquet_inventory_fingerprint'],
                'base_rows': loaded.audit['rows'], 'base_end_ms': last_global,
                'jobs': jobs, 'initial_disk_free': shutil.disk_usage(ROOT).free}
    write_canonical_json(ART / 'prepared.json', prepared)
    con.close()
    log(f"prepared jobs={len(jobs)} cutoff={config['cutoff_exclusive_utc']} gaps={len(gaps)}")
    return prepared


def fetch_window(job, tag, cutoff):
    c, cursor, end = job['symbol'], int(job['start_ms']), int(job['end_ms'])
    path = layout().raw_dir / '_archives/binance/futures/um/api/klines' / RUN / c / f'{tag}_{cursor}_{end}.json.gz'
    if path.exists():
        with gzip.open(path, 'rt') as handle:
            record = json.load(handle)
        if record['symbol'] != c or record['cutoff_ms'] != cutoff:
            raise ValueError('raw cache identity mismatch')
        for page in record['pages']:
            if hashlib.sha256(page['response_text'].encode()).hexdigest() != page['response_sha256']:
                raise ValueError('raw response SHA256 mismatch')
        return record
    record = {'symbol': c, 'start_ms': cursor, 'end_ms': end, 'cutoff_ms': cutoff,
              'tag': tag, 'pages': [], 'status': 'OK', 'rows': 0, 'fetched_at': now_iso()}
    if cursor >= end:
        record['status'] = 'NOT_YET_IN_WINDOW'
    while cursor < end:
        params = {'symbol': c, 'interval': '15m', 'startTime': cursor, 'endTime': end - 1, 'limit': 1000}
        url = FAPI + '/fapi/v1/klines?' + urlencode(params)
        try:
            payload = request(url)
        except HTTPError as exc:
            body = exc.read().decode(errors='replace')
            record.update(status='API_UNAVAILABLE', http_status=exc.code, error=body)
            break
        parsed = json.loads(payload)
        if not isinstance(parsed, list):
            raise ValueError(f'API returned non-list: {parsed}')
        frame_from_rows(parsed, c, cutoff)
        if any(int(r[0]) < cursor or int(r[0]) >= end for r in parsed):
            raise ValueError('API returned bars outside requested range')
        record['pages'].append({'url': url, 'fetched_at': now_iso(), 'response_text': payload.decode(),
                                'response_sha256': hashlib.sha256(payload).hexdigest()})
        record['rows'] += len(parsed)
        if not parsed:
            break
        next_cursor = int(parsed[-1][0]) + STEP
        if next_cursor <= cursor:
            raise ValueError('pagination did not advance')
        cursor = next_cursor
        if len(parsed) < 1000:
            break
    disk_guard()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    with gzip.open(temp, 'wt', encoding='utf-8') as handle:
        json.dump(record, handle)
    os.replace(temp, path)
    return record


def rows_of(record):
    return [row for page in record['pages'] for row in json.loads(page['response_text'])]


def fetch_all(prepared, workers):
    config = prepared['config']
    jobs = prepared['jobs']
    outcomes = []
    def worker(job):
        r = fetch_window(job, 'tail', config['cutoff_ms'])
        frame = frame_from_rows(rows_of(r), job['symbol'], config['cutoff_ms'])
        last = None if frame.empty else as_ms(frame.ts.max())
        return {**job, 'fetch_status': r['status'], 'rows_fetched': len(frame), 'last_ms': last,
                'error': r.get('error')}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(worker, job): job['symbol'] for job in jobs}
        for i, future in enumerate(as_completed(futures), 1):
            outcomes.append(future.result())
            if i % 50 == 0 or i == len(jobs):
                log(f'tail fetched {i}/{len(jobs)} rows={sum(x["rows_fetched"] for x in outcomes)}')
                write_canonical_json(ART / 'tail_progress.json', {'completed': i, 'total': len(jobs)})
    write_canonical_json(ART / 'tail_outcomes.json', {'outcomes': sorted(outcomes, key=lambda x:x['symbol'])})
    gaps = pd.read_csv(ART / 'base_gaps.csv')
    gap_outcomes = []
    def gap_worker(pair):
        i, row = pair
        job = {'symbol': code(row['symbol']), 'start_ms': as_ms(row['prev_ts']) + STEP, 'end_ms': as_ms(row['next_ts'])}
        record = fetch_window(job, f'gap{i}', config['cutoff_ms'])
        return {**job, 'gap_index': i, 'expected_missing': int(row['missing_bars']), 'returned_rows': record['rows'], 'status': record['status']}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, item in enumerate(pool.map(gap_worker, enumerate(gaps.to_dict('records'))), 1):
            gap_outcomes.append(item)
            if i % 25 == 0 or i == len(gaps):
                log(f'gap probes {i}/{len(gaps)} recovered={sum(x["returned_rows"] for x in gap_outcomes)}')
    write_canonical_json(ART / 'gap_outcomes.json', {'outcomes': gap_outcomes})


def numeric_mismatch(con, left, right):
    parts = [f'{left}.{c} IS DISTINCT FROM {right}.{c}' for c in ('open','high','low','close','trade_count')]
    for c, atol, rtol in [('volume',1e-9,1e-12),('quote_volume',1e-6,1e-10)]:
        parts.append(f'abs({left}.{c}-{right}.{c}) > {atol}+{rtol}*abs({left}.{c})')
    return '(' + ' OR '.join(parts) + ')'


def audit_table(con, table):
    columns = [r[0] for r in con.execute(f'DESCRIBE {table}').fetchall()]
    result = audit_selected_sql(con, selected_cte=f'selected AS (SELECT * FROM {table})',
        params=[], timeframe='15m', columns=columns, require_closed=True,
        expected_exchange='binance', expected_market_type='perp')
    if result['quality_status'] != 'PASS':
        raise ValueError(f'row audit FAIL: {result}')
    return result


def record_for(cutoff):
    return DatasetRecord(dataset_id=DATASET, layer='derived', kind=DatasetKind.OHLCV,
        status=DatasetStatus.TRUSTED_DERIVED, declared_scope=DatasetScope.FULL_MARKET,
        exchange='binance', market_type=MarketType.PERP, timeframe='15m',
        relative_root=f'derived/datasets/{SLUG}', source_adjudication='accepted v1 keys preserved; verified official API fills absent keys',
        priority_union_version='binance_15m_refresh_preserve_v1_v2', rebuildable=True,
        is_standard_ohlcv=True, cutoff_exclusive_utc=iso(cutoff),
        input_dataset_id=BINANCE_PERP_15M_NORMALIZED_V1,
        builder=str(Path(__file__).relative_to(ROOT)), coverage_spec=FullMarketCoverageSpec(),
        source_union=SourceUnionPolicy(version='already_adjudicated_v2',priority=(),passthrough=True))


def build(prepared):
    cutoff = prepared['config']['cutoff_ms']
    lake = layout()
    published, staging = lake.derived_datasets_dir / SLUG, lake.derived_staging_dir / SLUG
    if published.exists():
        raise FileExistsError('v2 already published; use verify, never overwrite')
    if staging.exists():
        raise FileExistsError(f'staging already exists; inspect partial build before reuse: {staging}')
    tail = json.loads((ART/'tail_outcomes.json').read_text())['outcomes']
    if len(tail) != len(prepared['jobs']) or {r['symbol'] for r in tail} != {j['symbol'] for j in prepared['jobs']}:
        raise ValueError('tail download job ledger incomplete')
    gap_results = json.loads((ART/'gap_outcomes.json').read_text())['outcomes']
    if len(gap_results) != len(pd.read_csv(ART/'base_gaps.csv')):
        raise ValueError('historical gap probe ledger incomplete')
    disk_guard()
    raw_root = lake.raw_dir / '_archives/binance/futures/um/api/klines' / RUN
    frames, receipts = [], []
    for path in sorted(raw_root.rglob('*.json.gz')):
        with gzip.open(path, 'rt') as handle:
            r = json.load(handle)
        for page in r['pages']:
            if hashlib.sha256(page['response_text'].encode()).hexdigest() != page['response_sha256']:
                raise ValueError('raw page SHA mismatch')
        frame = frame_from_rows(rows_of(r), r['symbol'], cutoff)
        if not frame.empty:
            frames.append(frame)
        receipts.append({'path': str(path.relative_to(ROOT)), 'sha256': sha256_file(path), 'rows': len(frame), 'status': r['status']})
    if not frames:
        raise ValueError('no fetched rows')
    delta = pd.concat(frames, ignore_index=True)
    con = connect()
    con.register('incoming_frame', delta)
    con.execute('CREATE TEMP TABLE incoming AS SELECT * FROM incoming_frame')
    # Repeated requests may overlap only with identical numeric values.
    conflicts = con.execute('SELECT count(*) FROM (SELECT symbol,ts FROM incoming GROUP BY symbol,ts HAVING count(DISTINCT (open,high,low,close,volume,quote_volume,trade_count))>1)').fetchone()[0]
    if conflicts:
        raise ValueError(f'contradictory fetched bars: {conflicts}')
    con.execute('CREATE TEMP TABLE delta AS SELECT * FROM incoming QUALIFY row_number() OVER(PARTITION BY symbol,ts ORDER BY close_time)=1')
    audit = audit_table(con, 'delta')
    write_canonical_json(ART / 'delta_audit.json', audit)
    write_canonical_json(ART / 'raw_receipts.json', {'files': receipts})
    # Raw API fields remain alongside normalized identity, in a date-partitioned raw dataset.
    raw_parquet = lake.raw_dir / f'ohlcv/exchange=binance/market_type=perp/timeframe=15m/source={SOURCE}'
    if not list(raw_parquet.glob(f'date=*/{RUN}_*.parquet')):
        raw_parquet.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY (SELECT *,strftime(ts,'%Y-%m-%d') AS date FROM delta) TO '{raw_parquet}' (FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY(date), FILENAME_PATTERN '{RUN}_{{i}}', OVERWRITE_OR_IGNORE)")
    raw_files = sorted(raw_parquet.glob(f'date=*/{RUN}_*.parquet'))
    con.from_parquet([str(p) for p in raw_files], hive_partitioning=False, union_by_name=True).create_view('persisted_raw')
    raw_cols = ','.join(dict.fromkeys([*RAW_COLUMNS,*NORMAL_COLUMNS,'closure_provenance','closure_as_of']))
    missing_raw = con.execute(f'SELECT count(*) FROM (SELECT {raw_cols} FROM delta EXCEPT ALL SELECT {raw_cols} FROM persisted_raw)').fetchone()[0]
    extra_raw = con.execute(f'SELECT count(*) FROM (SELECT {raw_cols} FROM persisted_raw EXCEPT ALL SELECT {raw_cols} FROM delta)').fetchone()[0]
    if missing_raw or extra_raw:
        raise ValueError(f'raw roundtrip mismatch: missing={missing_raw} extra={extra_raw}')
    write_canonical_json(ART/'raw_normalized_alignment.json',{
        'missing_rows':missing_raw,'extra_rows':extra_raw,'status':'PASS',
        'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha256_file(p)} for p in raw_files]})
    log('materialize accepted base for reconciliation')
    union_sql, params = source_priority_sql(DEFAULT_SOURCE_UNION)
    con.execute(f"CREATE TEMP TABLE base AS WITH raw AS (SELECT * FROM read_parquet(?,hive_partitioning=false,union_by_name=true)) {union_sql}", [prepared['files'], *params])
    mismatch = numeric_mismatch(con, 'b', 'd')
    changes = con.execute(f'SELECT b.symbol,b.ts,b.source AS base_source,{",".join(f"b.{c} AS base_{c},d.{c} AS fresh_{c}" for c in ["open","high","low","close","volume","quote_volume","trade_count"])} FROM base b JOIN delta d USING(symbol,ts) WHERE {mismatch} ORDER BY b.symbol,b.ts').fetch_df()
    changes.to_csv(ART / 'overlap_conflicts.csv', index=False)
    overlap = con.execute('SELECT count(*) FROM base JOIN delta USING(symbol,ts)').fetchone()[0]
    cols = ','.join(NORMAL_COLUMNS)
    con.execute(f'CREATE TEMP TABLE merged AS SELECT {cols} FROM base UNION ALL SELECT {",".join("d."+x for x in NORMAL_COLUMNS)} FROM delta d ANTI JOIN base b USING(symbol,ts)')
    merged_audit = audit_table(con, 'merged')
    gaps = con.execute(gaps_query('merged')).fetch_df()
    gaps.to_csv(ART / 'remaining_gaps.csv',index=False)
    spans = con.execute('SELECT symbol,min(ts) AS first_ts,max(ts) AS last_ts,count(*) AS rows FROM merged GROUP BY symbol ORDER BY symbol').fetch_df()
    spans_map = {code(r['symbol']):r for r in spans.to_dict('records')}
    freshness = []
    for job in prepared['jobs']:
        m, actual = job['metadata'], spans_map.get(job['symbol'])
        last = None if actual is None else as_ms(actual['last_ts'])
        expected = m.get('status') == 'TRADING' and m.get('underlyingType') in ('COIN','INDEX') and int(m.get('onboardDate',0)) < cutoff
        freshness.append({'archive_symbol':job['symbol'], 'underlying_type': m.get('underlyingType','UNKNOWN'),
            'contract_type':m.get('contractType','UNKNOWN'), 'status':m.get('status','UNKNOWN'),
            'required_latest_crypto': expected, 'last_bar_open':None if last is None else iso(last),
            'latest_closed_bar_present':last == cutoff-STEP, 'rows':0 if actual is None else int(actual['rows'])})
    fresh = pd.DataFrame(freshness)
    fresh.to_csv(ART / 'symbol_freshness.csv',index=False)
    stale = fresh[fresh.required_latest_crypto & ~fresh.latest_closed_bar_present]
    fresh_crypto_symbols = {symbol(r['archive_symbol']) for r in freshness if r['required_latest_crypto']}
    recent_gaps = gaps[(gaps.symbol.isin(fresh_crypto_symbols)) & (pd.to_datetime(gaps.next_ts,utc=True) > pd.Timestamp(prepared['base_end_ms']+STEP,unit='ms',tz='UTC'))]
    recent_gaps.to_csv(ART / 'recent_crypto_gaps.csv',index=False)
    summary = {'dataset_id':DATASET,'cutoff_exclusive_utc':iso(cutoff),'base_rows':prepared['base_rows'],
        'base_fingerprint':prepared['base_fingerprint'],'new_rows':merged_audit['rows']-prepared['base_rows'],
        'overlap_rows':overlap,'overlap_conflicting_rows_preserved_base':len(changes),
        'remaining_gaps':len(gaps),'recent_crypto_gap_transitions':len(recent_gaps),
        'required_latest_crypto_symbols':int(fresh.required_latest_crypto.sum()),
        'stale_crypto_symbols':stale.archive_symbol.tolist(), 'audit':merged_audit,
        'schema_preserves_original_api_fields_in_raw':True, 'all_history_redownloaded':False}
    write_canonical_json(ART / 'build_audit.json',summary)
    if not stale.empty:
        raise ValueError(f'active crypto tail incomplete: {stale.archive_symbol.tolist()}')
    # Conflicts remain explicit; they never overwrite the accepted old keys.
    staging.mkdir(parents=True)
    con.execute(f"COPY (SELECT *,strftime(ts,'%Y-%m-%d') AS date FROM merged ORDER BY ts,symbol) TO '{staging / 'ohlcv'}' (FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY(date))")
    inventory = parquet_inventory(staging)
    manifest = {'schema_version':'1.0','dataset_id':DATASET,'layer':'derived','status':'TRUSTED_DERIVED',
        'declared_scope':'FULL_MARKET','exchange':'binance','market_type':'perp','timeframe':'15m',
        'physical_root':str(published.resolve()),'source_adjudication':'accepted v1 preserved; verified official API fills absent keys',
        'priority_union_version':'binance_15m_refresh_preserve_v1_v2','aggregation_formula_version':'ohlcv_15m_identity_union_refresh_v2',
        'input_dataset_id':BINANCE_PERP_15M_NORMALIZED_V1,'input_manifest_sha256':prepared['base_fingerprint'],
        'builder_path':str(Path(__file__).relative_to(ROOT)),'builder_sha256':sha256_file(Path(__file__)),
        'generated_at':now_iso(),'cutoff_exclusive_utc':iso(cutoff),'start_utc':merged_audit['start_utc'],'end_utc':merged_audit['end_utc'],
        'file_count':len(inventory),'bytes':sum(r['size'] for r in inventory),'rows':merged_audit['rows'],
        'distinct_business_keys':merged_audit['rows'],'duplicate_key_rows':0,'symbol_count':merged_audit['symbol_count'],
        'rebuildable':True,'rebuild_command':f'.venv/bin/python {Path(__file__).relative_to(ROOT)} --phase all',
        'quality_status':'TRUSTED_DERIVED','parquet_inventory_fingerprint':inventory_fingerprint(inventory),
        'config_sha256':sha256_file(ART/'config.json'),'raw_receipts_sha256':sha256_file(ART/'raw_receipts.json'),
        'raw_alignment_sha256':sha256_file(ART/'raw_normalized_alignment.json'),
        'null_fill_policy':'no interpolation/no forward fill; retain missing intervals',
        'internal_missing_bars':merged_audit['internal_missing_bars'],
        'known_limits':['not a full historical redownload','legacy symbol classes may be unknown','historical gaps retained and enumerated','metadata is current, not PIT'],
        'audit_artifact':str((ART/'build_audit.json').relative_to(ROOT))}
    manifest['content_fingerprint'] = manifest_content_fingerprint(manifest)
    base_now = inventory_fingerprint(parquet_inventory(lake.normalized_dir / 'ohlcv/exchange=binance/market_type=perp/timeframe=15m'))
    if base_now != prepared['base_fingerprint']:
        raise ValueError('base changed during refresh')
    write_canonical_json(ART/'old_base_protected.json',{'before':prepared['base_fingerprint'],'after':base_now,'unchanged':True})
    log(publish_staging_dataset(staging_root=staging,published_root=published,manifest=manifest))
    register_derived_dataset(lake,record_for(cutoff))
    con.close()


def verify(prepared):
    loaded = load_trusted_dataset(DATASET,layout=layout(),requested_scope=DatasetScope.FULL_MARKET,
        end=prepared['config']['cutoff_exclusive_utc'],purpose='governance_audit',gap_policy='report_only',max_materialize_rows=0)
    require_passing_trusted(loaded)
    result = {'dataset_id':DATASET,'cutoff_exclusive_utc':prepared['config']['cutoff_exclusive_utc'],
        'audit':loaded.audit,'verified_identity':loaded.verified_identity,
        'verified_files':len(loaded.verified_parquet_files),'disk_free_after':shutil.disk_usage(ROOT).free}
    write_canonical_json(ART/'acceptance.json',result)
    log(f"accepted rows={loaded.audit['rows']} symbols={loaded.audit['symbol_count']} missing={loaded.audit['internal_missing_bars']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['prepare','fetch','build','verify','all'],default='prepare')
    parser.add_argument('--workers',type=int,default=8)
    args = parser.parse_args()
    prepared = prepare()
    if args.phase in ('fetch','all'):
        fetch_all(prepared,args.workers)
    if args.phase in ('build','all'):
        build(prepared)
    if args.phase in ('verify','all'):
        verify(prepared)


if __name__ == '__main__':
    main()
