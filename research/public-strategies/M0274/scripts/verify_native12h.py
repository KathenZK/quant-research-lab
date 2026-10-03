#!/usr/bin/env python3
"""Independent offline integrity/grid reconstruction, no builder import.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse, calendar, csv, hashlib, io, json, zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,o):
    with Path(p).open('x') as f:json.dump(o,f,indent=2,sort_keys=True);f.write('\n')
def audit(snapshot):
    p=Path(snapshot); m=json.loads((p/'manifest.json').read_text()); assert m['timeframe']=='12h'
    assert len(m['archives'])==25
    rows=[]; objects=[]; last=None
    for arc in m['archives']:
        for kind in ['zip','checksum','csv']:
            entry=arc[kind];b=(p/entry['path']).read_bytes()
            assert sha(b)==entry['sha256'] and len(b)==entry['bytes']
            objects.append({'month':arc['month'],'kind':kind,'sha256':sha(b),'bytes':len(b)})
        z=(p/arc['zip']['path']).read_bytes(); cs=(p/arc['checksum']['path']).read_text().split()
        assert cs[0]==sha(z) and cs[1].lstrip('*')==Path(arc['zip']['path']).name
        with zipfile.ZipFile(io.BytesIO(z)) as zipf:
            assert len(zipf.namelist())==1 and zipf.testzip() is None
            data=zipf.read(zipf.namelist()[0]);assert data==(p/arc['csv']['path']).read_bytes()
        native=list(csv.reader(io.StringIO(data.decode())))
        year,month=map(int,arc['month'].split('-'));assert len(native)==calendar.monthrange(year,month)[1]*2
        start=int(datetime(year,month,1,tzinfo=timezone.utc).timestamp()*1000)
        for i,row in enumerate(native):
            assert len(row)==12
            o=int(row[0]);c=int(row[6]);assert len(row[0])==13 and len(row[6])==13
            assert o==start+i*43200000 and c==o+43200000-1
            if last is not None:assert o-last==43200000
            last=o
            op,hi,lo,cl,vol=map(Decimal,row[1:6]); assert all(v.is_finite() for v in [op,hi,lo,cl,vol])
            assert 0<lo<=op<=hi and lo<=cl<=hi and vol>0 and int(row[8])>0
            rows.append(row)
    assert len(rows)==1524
    canonical=(p/m['canonical_csv']['path']).read_bytes();assert sha(canonical)==m['canonical_csv']['sha256']
    parsed=list(csv.reader(io.StringIO(canonical.decode())))
    assert parsed[0]==m['schema'] and len(parsed)==1525
    for raw,canon in zip(rows,parsed[1:]):
        assert raw==canon[:12]
        assert canon[13:19]==['binance','spot','12h','BTC/USDT','BTCUSDT','binance_vision']
        assert canon[12]==datetime.fromtimestamp(int(raw[0])/1000,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        assert canon[19]==datetime.fromtimestamp(int(raw[6])/1000,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.999Z')
    return {'schema':'native12h-independent-qa/v1','completed_at_utc':datetime.now(timezone.utc).isoformat(),'script_sha256':sha(Path(__file__).read_bytes()),'input_manifest_sha256':sha((p/'manifest.json').read_bytes()),'canonical_sha256':sha(canonical),'row_quality':'PASS','rows':1524,'evaluation_rows':1462,'months':25,'checked_native_objects':len(objects),'missing_grid_bars':0,'duplicate_bars':0,'out_of_order_bars':0,'native_timestamp_units':['milliseconds'],'unit_change_in_window':False,'unit_policy':'Reject unexpected timestamp digit counts or grid mismatch; official switch to microseconds starts 2025-01-01, outside end-exclusive window','native12_fields_preserved':True,'zip_sha256_crc_checksum':'PASS','native12h_not_resampled':True,'is_closed_authoritative':False,'strict_current_finality':'NOT_ESTABLISHED','quality_status':'DIAGNOSTIC_ONLY','registered_status':'UNACCEPTED','scope':'EXPLICIT_DIAGNOSTIC','objects':objects}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    r=audit(a.snapshot);write(a.out,r);print(json.dumps({k:v for k,v in r.items() if k!='objects'},indent=2))
