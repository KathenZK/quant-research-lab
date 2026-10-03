"""Exact offline native Binance 1d rebuild. No strategy imports or returns."""
import argparse
import csv
import datetime as dt
from decimal import Decimal, localcontext
import hashlib
import io
import json
from pathlib import Path
import zipfile

COLS = ['open_time','open','high','low','close','volume','close_time','quote_volume','trade_count','taker_base','taker_quote','ignore']
SHA = '48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5'
PROTOCOL_SHA = '67a6ed575916a180678d16699aedbf082fa92c48af78e7776f4836a25d17b12a'
def digest(b): return hashlib.sha256(b).hexdigest()

def reconstruct(raw, pinned_protocol):
    protocol_bytes=pinned_protocol.read_bytes()
    assert digest(protocol_bytes)==PROTOCOL_SHA
    objects=json.loads(protocol_bytes)['input']['raw_files']
    assert len(objects)==50
    rows=[]
    for record in objects:
        b=(raw/record['name']).read_bytes()
        assert len(b)==record['bytes'] and digest(b)==record['sha256'],record['name']
        if record['name'].endswith('.zip'):
            assert (raw/(record['name']+'.CHECKSUM')).read_bytes().decode().split()[0]==digest(b)
            with zipfile.ZipFile(io.BytesIO(b)) as z:
                assert z.testzip() is None and z.namelist()==[record['name'][:-4]+'.csv']
                rr=list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
            assert all(len(r)==12 for r in rr)
            rows.extend(rr)
    out=io.StringIO(newline='');w=csv.writer(out);w.writerow(COLS);w.writerows(rows);payload=out.getvalue().encode()
    assert digest(payload)==SHA and len(payload)==128196 and len(rows)==762
    qa=validate(payload)
    return payload,dict(status='PASS',raw_objects=50,provider_checksums=25,ZIP_CRCs=25,input_sha256=SHA,input_bytes=len(payload),**qa)

def validate(payload):
    assert digest(payload)==SHA and len(payload)==128196
    rows=list(csv.DictReader(io.StringIO(payload.decode(),newline='')))
    assert len(rows)==762
    start=int(dt.datetime(2022,12,1,tzinfo=dt.timezone.utc).timestamp()*1000)
    zero_volume=[]
    with localcontext() as ctx:
        ctx.prec=50
        for i,r in enumerate(rows):
            ts=int(r['open_time']);assert ts==start+i*86400000
            assert int(r['close_time'])==ts+86399999
            o,h,l,c=[Decimal(r[k]) for k in ['open','high','low','close']]
            assert all(x.is_finite() and x>0 for x in [o,h,l,c])
            assert l<=min(o,c)<=max(o,c)<=h
            for k in ['volume','quote_volume','taker_base','taker_quote']:
                d=Decimal(r[k]);assert d.is_finite() and d>=0
            trades=Decimal(r['trade_count']);assert trades.is_finite() and trades>=0 and trades==int(trades)
            if Decimal(r['volume'])==0:zero_volume.append(ts)
    assert int(rows[-1]['open_time'])==1735603200000
    return dict(rows=762,warmup_rows=31,evaluation_rows=731,duplicate_rows=0,missing_rows=0,OHLCV_bounds='PASS',native_close_time_duration_ms=86399999,zero_volume_rows=len(zero_volume),modifications=[],quality_status='DIAGNOSTIC_ONLY',trusted=False,PIT='NOT_PROVEN',source='Binance Vision native spot BTCUSDT 1d',known_halt='2023-03-24 intraday; no midnight override and no continuous liquidity claim',features_or_returns_computed=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    payload,result=reconstruct(a.raw,a.protocol)
    with a.output.open('xb') as f:f.write(payload)
    with a.receipt.open('x') as f:f.write(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(result))
