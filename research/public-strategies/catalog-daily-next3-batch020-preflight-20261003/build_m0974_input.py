"""M0974 data only: native spot1d QA and deterministic offline rebuild.

Derived from the frozen M1266 builder ad17927645d7e8cbf82b1e3f01a95f9238a3e6f122f05d3a4d6cbf8ec3cc31c5.
No indicator, signal, return, account, lake registration, or network code.
"""
import argparse, calendar, csv, datetime as dt, hashlib, io, json, re, shutil, zipfile
from decimal import Decimal as D
from pathlib import Path

COLS=['open_time','open','high','low','close','volume','close_time','quote_volume','trade_count','taker_base','taker_quote','ignore']
DAY=86400000
BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/'
OLDHASH='48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5'
TERMS='dcf358e9d18f598a7a635fac80f6e643fa24a0e111a4d39bda47f1e246b31eb1'
MONTHS=['2020-12']+[f'{y}-{m:02d}' for y in range(2021,2025) for m in range(1,13)]
sha=lambda b:hashlib.sha256(b).hexdigest()
def js(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def ms(y,m,d=1):return int(dt.datetime(y,m,d,tzinfo=dt.timezone.utc).timestamp()*1000)
def encode(rows):
    s=io.StringIO(newline='');w=csv.writer(s);w.writerow(COLS);w.writerows(rows);return s.getvalue().encode()
def reserve(p):
    free=shutil.disk_usage(p).free
    assert free>5*1024**3+20*1024**2, 'DISK_RESERVE_5GiB'
    return free
def check_month(raw,month):
    name=f'BTCUSDT-1d-{month}.zip';data=(raw/name).read_bytes();ch=(raw/(name+'.CHECKSUM')).read_bytes()
    checksum=ch.decode('ascii').strip().split();assert len(checksum)==2 and re.fullmatch('[0-9a-f]{64}',checksum[0])
    assert checksum[1].lstrip('*')==name and sha(data)==checksum[0]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.namelist()==[name[:-4]+'.csv'] and z.testzip() is None
        zi=z.infolist()[0];assert zi.file_size<1024**2 and not zi.is_dir()
        native=z.read(zi);rows=list(csv.reader(io.StringIO(native.decode('utf-8'))))
    y,m=map(int,month.split('-'));assert len(rows)==calendar.monthrange(y,m)[1]
    zeros={k:0 for k in ['volume','quote_volume','trade_count']}
    for j,x in enumerate(rows):
        assert len(x)==12 and all(x), 'NATIVE12_REQUIRED'
        assert x[0].isdigit() and x[6].isdigit() and x[8].isdigit()
        assert int(x[0])==ms(y,m)+j*DAY and int(x[6])==int(x[0])+DAY-1
        v=list(map(D,x));assert all(a.is_finite() for a in v)
        assert all(v[k]>0 for k in [1,2,3,4])
        assert all(v[k]>=0 for k in [5,7,8,9,10]) and v[8]==int(v[8]) and v[11]==0
        assert v[3]<=min(v[1],v[4])<=max(v[1],v[4])<=v[2]
        assert v[9]<=v[5] and v[10]<=v[7], 'TAKER_BOUNDS'
        for k in zeros:zeros[k]+=int(v[COLS.index(k)]==0)
    objects=[dict(name=n,bytes=len(b),sha256=sha(b),url=BASE+n) for n,b in [(name,data),(name+'.CHECKSUM',ch)]]
    audit=dict(month=month,rows=len(rows),native_csv_bytes=len(native),native_csv_sha256=sha(native),zip_CRC=f'{zi.CRC:08x}',provider_checksum='PASS',ZIP_CRC='PASS',grid='PASS',OHLCV='PASS',zero_counts=zeros)
    return rows,objects,audit
def build(raw,out,expected=None):
    reserve(out.parent);assert not out.exists();rows=[];objects=[];monthly=[]
    for mo in MONTHS:
        r,o,q=check_month(raw,mo);rows+=r;objects+=o;monthly.append(q)
    assert len(rows)==1492 and [int(x[0]) for x in rows]==list(range(ms(2020,12),ms(2025,1),DAY))
    selected=rows[26:];assert len(selected)==1466 and int(selected[0][0])==ms(2020,12,27)
    assert sum(int(x[0])<ms(2023,1) for x in selected)==735
    assert int(selected[734][0])==ms(2022,12,31) and int(selected[735][0])==ms(2023,1)
    assert int(selected[-1][0])==ms(2024,12,31) and int(selected[-1][6])+1==ms(2025,1)
    old=encode(selected[704:]);assert len(selected[704:])==762 and sha(old)==OLDHASH
    body=encode(selected)
    if expected: assert sha(body)==expected
    report=dict(dataset_id='binance.spot.BTCUSDT.native1d.20201227-20241231.M0974-input-v1',identity=dict(exchange='binance',market_type='spot',symbol='BTCUSDT',timeframe='UTC1d',source='BinanceVision monthly native trade-price klines',session_policy='continuous_24_7'),
      rows=1466,warmup_rows=735,evaluation_rows=731,input_bytes=len(body),input_sha256=sha(body),columns=COLS,
      raw_source_rows=1492,excluded_early_source_rows=26,input_start='2020-12-27T00:00:00Z',warmup_last='2022-12-31T00:00:00Z',evaluation_start='2023-01-01T00:00:00Z',cutoff_exclusive='2025-01-01T00:00:00Z',
      old762_slice_offset=704,old762_exact_sha256=OLDHASH,old762_rebuild_hash_equal=True,old762_bytes=len(old),monthly_QA=monthly,objects=objects,
      duplicate_rows=0,missing_bars=0,unexpected_intervals=0,zero_counts={k:sum(m['zero_counts'][k] for m in monthly) for k in monthly[0]['zero_counts']},
      native_decimal_strings_preserved=True,serialization='Python csv.writer default excel dialect; UTF-8; CRLF; native12 field order; no numeric rewriting',
      scope='EXPLICIT_DIAGNOSTIC',layer='cache',registered_status='UNACCEPTED',quality='DIAGNOSTIC_ONLY',PIT=False,finality=False,tradability=False,closed_bar_authority_proven=False,
      license='CC-BY-NC-SA-4.0 plus BinanceVisionDatasetTerms',terms_sha256=TERMS,
      warmup_selection='Coordinator prior decision: 735 closes; RSI50 seed residual weight only, not RSI value/crossover-error guarantee; no RSI computed here',
      caveats=['No is_closed flag fabricated; close_time/grid/checksum do not prove PIT or finality','Native daily aggregates do not prove intraday continuous tradability; known 2023-03-24 intraday exchange halt remains','Earlier26 raw December2020 rows are excluded from canonical view; do not feed them to future indicators','No trusted lake status or perpetual identity borrowed'],
      strategy_features_computed=False,indicator_values_computed=False,history_runs=0,controls=0)
    out.mkdir();(out/'input.csv').write_bytes(body);(out/'manifest.json').write_bytes(js(report));return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--expected');a=p.parse_args()
    r=build(a.raw,a.output,a.expected);print(json.dumps({k:r[k] for k in ['rows','warmup_rows','evaluation_rows','input_bytes','input_sha256']}))
