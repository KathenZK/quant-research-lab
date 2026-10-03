#!/usr/bin/env python3
"""Independent local-only official daily/monthly row cross-check; no prices output."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile


def main():
    p=argparse.ArgumentParser()
    for x in ['daily-zip','daily-checksum','monthly-csv','out']:p.add_argument('--'+x,required=True)
    a=p.parse_args();z=Path(a.daily_zip).read_bytes();c=Path(a.daily_checksum).read_bytes()
    sha=lambda b:hashlib.sha256(b).hexdigest()
    h,n=c.decode().strip().split()
    assert h==sha(z) and n.lstrip('*')==Path(a.daily_zip).name
    with zipfile.ZipFile(io.BytesIO(z)) as f:
        assert f.namelist()==['BTCUSDT-1h-2023-03-24.csv'] and f.testzip() is None
        b=f.read(f.namelist()[0])
    d=list(csv.reader(io.StringIO(b.decode())));mbytes=Path(a.monthly_csv).read_bytes()
    m=[r for r in csv.reader(io.StringIO(mbytes.decode())) if 1679616000000<=int(r[0])<1679702400000]
    assert m==d
    expected={1679616000000+i*3600000 for i in range(24)}
    missing=sorted(expected-{int(r[0]) for r in d})
    assert missing==[1679662800000]
    row=next(r for r in d if int(r[0])==1679659200000)
    assert int(row[6])==1679661581646 and float(row[5])==0 and int(row[8])==0
    result={'status':'DATA_BLOCKED_CONFIRMED','crosscheck':'independent local checksum/CRC and all-native-field comparison',
            'daily_rows':len(d),'expected_daily_rows':24,'monthly_same_day_rows':len(m),'native_rows_equal':True,
            'missing_open_utc':['2023-03-24T13:00:00Z'],'partial_bar_open_utc':'2023-03-24T12:00:00Z',
            'partial_bar_native_close_utc':'2023-03-24T12:39:41.646Z','partial_bar_volume_zero':True,'partial_bar_trades_zero':True,
            'daily_zip_sha256':sha(z),'daily_zip_bytes':len(z),'daily_checksum_sha256':sha(c),'daily_checksum_bytes':len(c),
            'daily_csv_sha256':sha(b),'daily_csv_bytes':len(b),'monthly_csv_sha256':sha(mbytes),
            'repair_performed':False,'market_runs':0,'attribution':'Binance Vision','license':'CC BY-NC-SA 4.0 plus Binance Dataset Terms'}
    with open(a.out,'x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print('CONFIRMED daily23/24 identical to monthly day; no returns computed')
if __name__=='__main__':main()
