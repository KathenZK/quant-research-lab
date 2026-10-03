"""Independent input-only audit. Does not import any strategy or compute returns."""
import csv
import datetime as dt
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[2]
def sha(b): return hashlib.sha256(b).hexdigest()
def main():
    frozen=ROOT/'frozen';raw=ROOT/'input'
    protocol_bytes=(frozen/'M1258-protocol-v1.json').read_bytes()
    assert sha(protocol_bytes)=='67a6ed575916a180678d16699aedbf082fa92c48af78e7776f4836a25d17b12a'
    records=json.loads(protocol_bytes)['input']['raw_files']
    assert len(records)==50 and len({r['name'] for r in records})==50
    checked=[];rows=[];months=[]
    for record in records:
        payload=(raw/record['name']).read_bytes()
        assert len(payload)==record['bytes'],record['name']
        assert sha(payload)==record['sha256'],record['name']
        checked.append(dict(name=record['name'],bytes=len(payload),sha256=sha(payload)))
        if not record['name'].endswith('.zip'):continue
        check=(raw/(record['name']+'.CHECKSUM')).read_text().split()
        assert check[0]==sha(payload) and check[-1]==record['name'],record['name']
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            assert archive.testzip() is None
            assert archive.namelist()==[record['name'][:-4]+'.csv']
            contents=archive.read(archive.namelist()[0]).decode('utf-8')
        chunk=list(csv.reader(io.StringIO(contents,newline='')))
        year,month=map(int,record['name'][-11:-4].split('-'))
        next_month=dt.date(year+(month==12),1 if month==12 else month+1,1)
        assert len(chunk)==(next_month-dt.date(year,month,1)).days
        assert all(len(row)==12 for row in chunk)
        assert all(dt.datetime.fromtimestamp(int(row[0])/1000,dt.timezone.utc).strftime('%Y-%m')==f'{year}-{month:02}' for row in chunk)
        rows.extend(chunk);months.append(f'{year}-{month:02}')
    assert len(months)==25 and months==sorted(set(months))
    columns=['open_time','open','high','low','close','volume','close_time','quote_volume','trade_count','taker_base','taker_quote','ignore']
    rebuilt=io.StringIO(newline='');writer=csv.writer(rebuilt);writer.writerow(columns);writer.writerows(rows);canonical=rebuilt.getvalue().encode('utf-8')
    assert len(canonical)==128196 and sha(canonical)=='48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5'
    assert canonical==(raw/'input.csv').read_bytes()==(raw/'offline-rebuilt-input.csv').read_bytes()
    assert len(rows)==762
    start=dt.datetime(2022,12,1,tzinfo=dt.timezone.utc);eval_start=dt.datetime(2023,1,1,tzinfo=dt.timezone.utc);end=dt.datetime(2025,1,1,tzinfo=dt.timezone.utc)
    start_ms=int(start.timestamp())*1000;eval_ms=int(eval_start.timestamp())*1000;end_ms=int(end.timestamp())*1000
    warmup=eval_rows=zero_volume=0;eval_months=set();seen=set()
    for i,row in enumerate(rows):
        ts=int(row[0]);assert ts==start_ms+i*86400000 and ts not in seen;seen.add(ts)
        assert int(row[6])==ts+86399999 and int(row[6])<end_ms
        o,h,l,c=(Decimal(row[j]) for j in [1,2,3,4])
        assert all(v.is_finite() and v>0 for v in (o,h,l,c))
        assert l<=o<=h and l<=c<=h and l<=h
        for j in [5,7,9,10]:
            v=Decimal(row[j]);assert v.is_finite() and v>=0
        n=Decimal(row[8]);assert n.is_finite() and n>=0 and n==n.to_integral_value()
        zero_volume+=Decimal(row[5])==0
        if ts<eval_ms:warmup+=1
        else:
            eval_rows+=1;eval_months.add(dt.datetime.fromtimestamp(ts/1000,dt.timezone.utc).strftime('%Y-%m'))
    assert warmup==31 and eval_rows==731 and len(eval_months)==24
    assert int(rows[-1][0])+86400000==end_ms
    acquisition=json.loads((ROOT/'review/input-acquisition-v1.json').read_text())
    assert acquisition['status']=='PASS_EXACT_NATIVE_DAILY_RECONSTRUCTION'
    assert acquisition['dataset_terms_unchanged_from_approved'] is True
    assert sha((frozen/'binance-public-data-TERMS_AND_CONDITIONS.md').read_bytes())==acquisition['dataset_terms_sha256']
    assert len(acquisition['attempts'])==50 and all(x['status']==200 and x['result']=='PASS' and x['url']==x['url_received'] for x in acquisition['attempts'])
    assert all(x['url'].startswith('https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/') for x in acquisition['attempts'])
    reserve=shutil.disk_usage(ROOT).free;assert reserve>5*1024**3
    receipt={'schema':'batch017-independent-input-QA/v1','status':'PASS','method':'Independent standard-library archive rebuild and Decimal row QA; no strategy imports, indicators or returns','raw_objects':checked,'ZIP_checksum_CRC_pairs':25,'canonical_bytes':len(canonical),'canonical_sha256':sha(canonical),'canonical_matches_both_worker_copies':True,'rows':762,'warmup_rows':warmup,'evaluation_rows':eval_rows,'evaluation_months':sorted(eval_months),'UTC_grid_duplicates_gaps_close_time':'PASS','finite_positive_OHLC_bounds':'PASS','finite_nonnegative_volume_trades':'PASS','zero_volume_rows':zero_volume,'all_source_attempts_status_200_same_exact_URL':True,'terms_bytes_match_recorded_approval':True,'data_modified':False,'historical_strategy_executions':0,'new_controls':0,'quality_status':'DIAGNOSTIC_ONLY','trusted':False,'PIT':'NOT_PROVEN','disk_free_bytes':reserve,'script_sha256':sha(Path(__file__).read_bytes()),'evidence_sha256':{name:sha((ROOT/name).read_bytes()) for name in ['review/input-QA-v1.json','review/input-acquisition-v1.json','frozen/M1258-protocol-v1.json']}}
    dest=ROOT/'review/independent/input-QA-independent-v1.json'
    with dest.open('x') as f:json.dump(receipt,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'status':'PASS','raw_objects':50,'CRC_pairs':25,'canonical_sha256':sha(canonical),'rows':762,'returns_computed':False,'receipt':str(dest),'receipt_sha256':sha(dest.read_bytes())}))
if __name__=='__main__':main()
