#!/usr/bin/env python3
"""Verify retained partial native 12h archive evidence; never publishes a full input.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse, calendar, csv, hashlib, io, json, zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

def h(b):return hashlib.sha256(b).hexdigest()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--partial',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 root=Path(a.partial);records=[];rows=[];prev=None;outages=[]
 for folder in sorted((root/'archives').iterdir()):
  zipped=folder/f'BTCUSDT-12h-{folder.name}.zip';checksum=zipped.with_suffix('.zip.CHECKSUM')
  rec={'month':folder.name,'zip_present':zipped.exists(),'checksum_present':checksum.exists(),'objects':{}}
  if checksum.exists():
   b=checksum.read_bytes();rec['objects']['checksum']={'path':str(checksum.relative_to(root)),'bytes':len(b),'sha256':h(b)}
  if not zipped.exists():records.append(rec);continue
  b=zipped.read_bytes();cs=checksum.read_text().split();assert cs[0]==h(b) and cs[1].lstrip('*')==zipped.name
  rec['objects']['zip']={'path':str(zipped.relative_to(root)),'bytes':len(b),'sha256':h(b)}
  with zipfile.ZipFile(io.BytesIO(b)) as z:
   assert len(z.namelist())==1 and z.testzip() is None
   csvname=z.namelist()[0];data=z.read(csvname);assert data==(folder/csvname).read_bytes()
  rec['objects']['csv']={'path':str((folder/csvname).relative_to(root)),'bytes':len(data),'sha256':h(data)}
  native=list(csv.reader(io.StringIO(data.decode())));year,month=map(int,folder.name.split('-'))
  assert len(native)==calendar.monthrange(year,month)[1]*2
  start=int(datetime(year,month,1,tzinfo=timezone.utc).timestamp()*1000)
  for i,row in enumerate(native):
   assert len(row)==12 and all(v!='' for v in row)
   t=int(row[0]);assert len(row[0])==13 and len(row[6])==13 and t==start+i*43200000 and int(row[6])==t+43200000-1
   if prev is not None:assert t-prev==43200000
   prev=t
   op,hi,lo,cl,vol=map(Decimal,row[1:6]);q,tb,tq=map(Decimal,[row[7],row[9],row[10]])
   assert all(v.is_finite() for v in [op,hi,lo,cl,vol,q,tb,tq])
   assert 0<lo<=op<=hi and lo<=cl<=hi and vol>0 and int(row[8])>0 and 0<=tb<=vol and 0<=tq<=q
   assert lo*vol-Decimal('0.00000001')<=q<=hi*vol+Decimal('0.00000001')
   assert lo*tb-Decimal('0.00000001')<=tq<=hi*tb+Decimal('0.00000001')
   rows.append(row)
  rec['row_quality']='PASS_FOR_RETAINED_MONTH_ONLY';rec['rows']=len(native);records.append(rec)
 complete=[x for x in records if x['zip_present']]
 result={'schema':'native12h-partial-independent-audit/v1','id':'M0274','completed_at_utc':datetime.now(timezone.utc).isoformat(),'script_sha256':h(Path(__file__).read_bytes()),'expected_months':25,'complete_months':len(complete),'checksum_only_months':[x['month'] for x in records if not x['zip_present']],'verified_rows':len(rows),'expected_rows':1524,'remaining_unverified_rows':1524-len(rows),'complete_month_range':[complete[0]['month'],complete[-1]['month']],'requested_window':['2022-12-01T00:00:00Z','2025-01-01T00:00:00Z'],'retained_coverage_end_exclusive':'2024-02-01T00:00:00Z','archive_checksums_crc_native12_utc_grid_ohlcv_for_retained_months':'PASS','duplicates_missing_or_out_of_order_within_retained_coverage':0,'observed_timestamp_unit':'milliseconds','unit_change_in_requested_window':'NOT_FULLY_TESTED_DUE_INCOMPLETE_INPUT','canonical_full_input':'NOT_CREATED','complete_window_qa':'INCOMPLETE_BLOCKED','second_network_capture':'NOT_RUN','independent_offline_partial_verification':'PASS','strategy_backtest_executed':False,'quality_status':'DIAGNOSTIC_ONLY','registered_status':'UNACCEPTED','records':records,'failure_receipt_sha256':h((root/'failure.json').read_bytes()),'no_sort_dedup_fill_resample':True}
 with Path(a.out).open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
 print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
