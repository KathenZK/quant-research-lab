#!/usr/bin/env python3
"""Read-only independent audit of the exact failed hourly archive.
Does not repair, canonicalize, compute indicators or calculate returns.
"""
import argparse
import calendar
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
from datetime import datetime,timezone


def sha(b):return hashlib.sha256(b).hexdigest()
def utc(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
def audit(zip_path,checksum_path,month):
    z=Path(zip_path).read_bytes();c=Path(checksum_path).read_bytes();parts=c.decode().strip().split()
    if len(parts)!=2 or parts[0]!=sha(z) or parts[1].lstrip('*')!=Path(zip_path).name:raise ValueError('CHECKSUM MISMATCH')
    with zipfile.ZipFile(io.BytesIO(z)) as a:
        if a.testzip() is not None:raise ValueError('ZIP CRC failure')
        names=a.namelist()
        if len(names)!=1 or names[0]!=Path(zip_path).name.replace('.zip','.csv'):raise ValueError('Unexpected members')
        b=a.read(names[0])
    rows=list(csv.reader(io.StringIO(b.decode())))
    y,m=map(int,month.split('-'));start=int(datetime(y,m,1,tzinfo=timezone.utc).timestamp()*1000)
    expected=calendar.monthrange(y,m)[1]*24
    grid={start+i*3600000 for i in range(expected)}
    opened=[int(r[0]) for r in rows]
    bad_closes=[{'open_utc':utc(int(r[0])),'actual_close_utc':utc(int(r[6])),
                 'expected_close_utc':utc(int(r[0])+3599999),'volume_zero':float(r[5])==0,'trades_zero':int(r[8])==0} for r in rows if int(r[6])!=int(r[0])+3599999]
    missing=sorted(grid-set(opened));extras=sorted(set(opened)-grid)
    status='DATA_BLOCKED' if len(rows)!=expected or missing or extras or bad_closes or len(set(opened))!=len(opened) else 'ROW_GRID_PASS_ONLY'
    return {'id':'M0259','status':status,'month':month,'timeframe':'1h','observed_rows':len(rows),'expected_rows':expected,
            'missing_open_utc':[utc(t) for t in missing],'extra_open_utc':[utc(t) for t in extras],
            'duplicate_opens':len(opened)-len(set(opened)),'original_order_strictly_increasing':all(a<b for a,b in zip(opened,opened[1:])),
            'nonconforming_native_close_times':bad_closes,'zero_volume_rows':sum(float(r[5])==0 for r in rows),
            'archive':{'filename':Path(zip_path).name,'sha256':sha(z),'bytes':len(z),'official_checksum':'PASS','zip_crc':'PASS',
                       'checksum_sha256':sha(c),'checksum_bytes':len(c),'csv_sha256':sha(b),'csv_bytes':len(b)},
            'scope':'row/clock-grid metadata only; no indicator or return calculation; no repairs',
            'market_runs':0,'normalized_input_published':False,
            'attribution':'Binance Vision','license':'CC BY-NC-SA 4.0 and Binance Dataset Terms',
            'additional_terms':'https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md'}

def main():
    p=argparse.ArgumentParser()
    for x in ['zip','checksum','month','out']:p.add_argument('--'+x,required=True)
    a=p.parse_args();r=audit(a.zip,a.checksum,a.month)
    with open(a.out,'x') as f:f.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps({'status':r['status'],'observed_rows':r['observed_rows'],'expected_rows':r['expected_rows'],'missing':r['missing_open_utc']}))
if __name__=='__main__':main()
