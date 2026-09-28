"""Fetch an outcome-blind, exact-hour official correction inventory; no publication."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import pandas as pd
from strategy_lab.data.catalog import DatasetScope, load_trusted_dataset, require_passing_trusted, list_registered_datasets
from strategy_lab.data.research_bundle import read_bundle_contract, verify_bundle_files
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.settings import default_settings

LAB = Path(__file__).resolve().parents[4]
FAMILY = LAB / 'research/asset-portfolios/1d-ma7-cross-atr-generalization'
OUT = FAMILY / 'artifacts/state_machine_20260910/official_hour_repair'
HELPER = LAB / 'research/platform/data-lake-governance/scripts/refresh_binance_15m_v2.py'
sp = importlib.util.spec_from_file_location('original_repair_fetch_validation', HELPER)
helper = importlib.util.module_from_spec(sp)
sp.loader.exec_module(helper)
NIDX = [1, 2, 3, 4, 5, 7, 8]


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=str, allow_nan=False)
        f.write('\n')


def now():
    return datetime.now(timezone.utc).isoformat()


def fetch(url, stem, cfg):
    req = {'url': url, 'requested_utc': now()}
    save(stem.with_suffix('.request.json'), req)
    attempts = []
    for k in range(cfg['max_attempts']):
        time.sleep(cfg['request_spacing_per_worker_seconds'])
        status, error, body = None, None, b''
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'QuantStrategyLabDataQuality/1.0'}), timeout=cfg['timeout_seconds']) as r:
                status, body = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read()
        except Exception as e:
            error = f'{type(e).__name__}: {e}'
        p = Path(str(stem) + f'.attempt{k}.bin')
        p.write_bytes(body)
        attempts.append({'attempt': k, 'http_status': status, 'error': error, 'response_path': str(p.relative_to(OUT)), 'response_sha256': sha(p), 'bytes': len(body)})
        if status == 200 or status in (400, 403, 404, 451):
            break
    receipt = {'request': req, 'attempts': attempts, 'http_status': status, 'error': error}
    save(stem.with_suffix('.receipt.json'), receipt)
    return receipt, body


def validate_target(rows, code, start, end, cutoff):
    frame = helper.frame_from_rows(rows, code, cutoff)
    expected = list(range(start, end, 900000))
    if [int(r[0]) for r in rows] != expected:
        raise ValueError('Expected exactly the four ordered target quarter-hours')
    assert len(frame) == 4 and frame.is_closed.all()
    return frame


def inspect_symbol(symbol, cfg, contract):
    code = symbol.replace('/USDT:USDT', 'USDT')
    folder = OUT / 'official_responses' / code
    folder.mkdir(parents=True, exist_ok=False)
    start = int(pd.Timestamp(contract['target_start']).timestamp() * 1000)
    end = int(pd.Timestamp(contract['target_end']).timestamp() * 1000)
    cutoff = int(pd.Timestamp('2026-09-05T15:45:00Z').timestamp() * 1000)
    url = 'https://fapi.binance.com/fapi/v1/klines?' + urllib.parse.urlencode({'symbol':code,'interval':'15m','startTime':start,'endTime':end-1,'limit':4})
    ar, ab = fetch(url, folder/'api', cfg)
    api_rows, archive_rows, issues = None, None, []
    if ar['http_status'] == 200:
        try:
            parsed = json.loads(ab)
            validate_target(parsed, code, start, end, cutoff)
            api_rows = parsed
        except Exception as e:
            issues.append({'source':'api','error':f'{type(e).__name__}: {e}'})
    else:
        issues.append({'source':'api','status':ar['http_status'],'error_body':ab.decode(errors='replace')})
    fname = f'{code}-15m-2024-10-28.zip'
    vurl = f'https://data.binance.vision/data/futures/um/daily/klines/{code}/15m/{fname}'
    vr, vb = fetch(vurl, folder/'vision', cfg)
    checksum_receipt = None
    if vr['http_status'] == 200:
        cr, cb = fetch(vurl+'.CHECKSUM', folder/'vision_checksum', cfg)
        checksum_receipt = cr
        try:
            if cr['http_status'] != 200:
                raise ValueError('Official archive CHECKSUM unavailable')
            pieces = cb.decode().strip().split()
            if len(pieces) != 2 or pieces[1].lstrip('*') != fname or pieces[0].lower() != hashlib.sha256(vb).hexdigest():
                raise ValueError('Official archive checksum mismatch')
            with zipfile.ZipFile(io.BytesIO(vb)) as z:
                if z.testzip() is not None or z.namelist() != [fname.removesuffix('.zip')+'.csv']:
                    raise ValueError('ZIP CRC/member identity mismatch')
                rows = list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode('utf-8-sig'))))
            if rows and rows[0][0] == 'open_time':
                if rows[0] != ['open_time','open','high','low','close','volume','close_time','quote_volume','count','taker_buy_volume','taker_buy_quote_volume','ignore']:
                    raise ValueError('Unexpected official archive header')
                rows = rows[1:]
            day0 = int(pd.Timestamp('2024-10-28T00:00:00Z').timestamp()*1000)
            if any(not day0 <= int(r[0]) < day0+86400000 for r in rows):
                raise ValueError('Archive rows escaped named UTC day')
            helper.frame_from_rows(rows, code, cutoff)
            selected = [r for r in rows if start <= int(r[0]) < end]
            validate_target(selected, code, start, end, cutoff)
            archive_rows = selected
        except Exception as e:
            issues.append({'source':'vision','error':f'{type(e).__name__}: {e}'})
    else:
        issues.append({'source':'vision','status':vr['http_status'],'error_body':vb.decode(errors='replace')})
    disagreement = []
    if api_rows is not None and archive_rows is not None:
        for a,v in zip(api_rows,archive_rows):
            for k in NIDX:
                if Decimal(str(a[k])) != Decimal(str(v[k])):
                    disagreement.append({'open_time':int(a[0]),'field_index':k,'api_value':str(a[k]),'archive_value':str(v[k])})
    accepted = None
    if disagreement:
        status = 'OFFICIAL_SOURCES_CONFLICT_BASE_PRESERVED'
    elif archive_rows is not None:
        accepted = archive_rows
        status = 'BOTH_OFFICIAL_SOURCES_AGREE' if api_rows is not None else 'CHECKSUM_ARCHIVE_ONLY'
    elif api_rows is not None:
        accepted = api_rows
        status = 'VALIDATED_API_ONLY'
    else:
        status = 'NO_VALID_OFFICIAL_HOUR_BASE_PRESERVED'
    result = {'symbol':symbol,'code':code,'status':status,'issues':issues,'official_source_disagreements':disagreement,
              'api_available_valid':api_rows is not None,'archive_available_valid':archive_rows is not None,
              'accepted_source':None if accepted is None else ('binance_vision' if archive_rows is not None else 'binance_futures_kline_api'),
              'accepted_rows':accepted,'completed_utc':now()}
    save(folder/'disposition.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    contract_path=OUT/'repair_contract.json'
    contract=json.loads(contract_path.read_text())
    for p,digest in contract['protected_sources'].items():
        assert sha(LAB/p)==digest, 'Protected source changed: '+p
    save(OUT/'fetch_execution_pin.json', {'started_utc':now(),'script_sha256':sha(Path(__file__)),'helper_sha256':sha(HELPER),'contract_sha256':sha(contract_path)})
    lake=DataLakeLayout.from_settings(default_settings())
    bundle,pin=read_bundle_contract(LAB,pin=contract['base_bundle_pin'])
    verified=verify_bundle_files(bundle,data_root=lake.root_dir)
    catalog=list_registered_datasets(layout=lake)
    assert not set(contract['new_dataset_ids'].values()) & {r['dataset_id'] for r in catalog}
    save(OUT/'catalog_before.json',catalog)
    loaded=require_passing_trusted(load_trusted_dataset(contract['base_dataset_id'],layout=lake,requested_scope=DatasetScope.FULL_MARKET,
        start=contract['target_start'],end=contract['target_end'],purpose='governance_audit',gap_policy='report_only',max_materialize_rows=10000))
    assert loaded.materialized
    base=loaded.frame.sort_values(['symbol','ts']).reset_index(drop=True)
    target=OUT/'frozen_target_15m.parquet';base.to_parquet(target,index=False)
    pd.testing.assert_frame_equal(base,pd.read_parquet(target),check_exact=True)
    symbols=sorted(base.symbol.unique())
    counts=base.groupby('symbol').size()
    assert counts.eq(4).all(), 'Frozen target hour lacks four represented 15m keys; review before fetching'
    save(OUT/'frozen_target_inventory.json',{'symbols':symbols,'symbol_count':len(symbols),'rows':len(base),'target_sha256':sha(target),
         'load_audit':loaded.audit,'verified_identity':loaded.verified_identity,'verified_bundle':verified,'frozen_bundle_pin':pin})
    print(f'FROZEN TARGET {len(symbols)} symbols / {len(base)} quarter-hours',flush=True)
    began=time.monotonic();results=[]
    with ThreadPoolExecutor(max_workers=contract['network']['workers']) as pool:
        jobs={pool.submit(inspect_symbol,s,contract['network'],contract):s for s in symbols}
        for task in as_completed(jobs):
            r=task.result();results.append(r)
            if len(results)%25==0 or len(results)==len(symbols):
                print(f'FETCHED {len(results)}/{len(symbols)}; seconds={time.monotonic()-began:.1f}',flush=True)
    results.sort(key=lambda r:r['symbol'])
    assert [r['symbol'] for r in results]==symbols
    save(OUT/'official_hour_dispositions.json',{'contract_sha256':sha(contract_path),'results':results})
    for p,digest in contract['protected_sources'].items():
        assert sha(LAB/p)==digest, 'Protected source changed: '+p
    stats=pd.Series([r['status'] for r in results]).value_counts().to_dict()
    summary={'complete':True,'completed_utc':now(),'elapsed_fetch_seconds':time.monotonic()-began,'symbols':len(symbols),'status_counts':stats,
        'unresolved_symbols':[r['symbol'] for r in results if r['accepted_rows'] is None],
        'old_inputs_changed':False,'accounts_run':False,'dispositions_sha256':sha(OUT/'official_hour_dispositions.json')}
    save(OUT/'fetch_completion.json',summary)
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    main()
