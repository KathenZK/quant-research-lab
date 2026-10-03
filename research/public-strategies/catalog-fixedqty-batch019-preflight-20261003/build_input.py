"""Bounded native spot daily raw capture or offline byte-preserving rebuild."""
import argparse,csv,datetime as dt,hashlib,io,json,shutil,urllib.request,urllib.error,zipfile,calendar
from decimal import Decimal as D
from pathlib import Path
COLS=['open_time','open','high','low','close','volume','close_time','quote_volume','trade_count','taker_base','taker_quote','ignore'];DAY=86400000
OLDHASH='48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5'
sha=lambda b:hashlib.sha256(b).hexdigest()
def encode(rows):
 s=io.StringIO(newline='');w=csv.writer(s);w.writerow(COLS);w.writerows(rows);return s.getvalue().encode()
def ms(y,m,d=1):return int(dt.datetime(y,m,d,tzinfo=dt.timezone.utc).timestamp()*1000)
def build(raw,out,expected=None):
 out.mkdir(exist_ok=False);rows=[];members=[];monthly=[]
 months=['2022-09','2022-10','2022-11','2022-12']+[f'{y}-{m:02d}' for y in [2023,2024] for m in range(1,13)]
 for month in months:
  name=f'BTCUSDT-1d-{month}.zip';p=raw/name;data=p.read_bytes();ch=(raw/(name+'.CHECKSUM')).read_bytes();assert sha(data)==ch.decode().split()[0]
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   assert z.namelist()==[name[:-4]+'.csv'] and z.testzip() is None;r=list(csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]))))
  y,m=map(int,month.split('-'));assert len(r)==calendar.monthrange(y,m)[1]
  for j,x in enumerate(r):
   assert len(x)==12 and int(x[0])==ms(y,m)+j*DAY and int(x[6])==int(x[0])+DAY-1
   v=list(map(D,x));assert all(a.is_finite() for a in v)
   assert all(v[k]>0 for k in [1,2,3,4,5,7]) and all(v[k]>=0 for k in [8,9,10]);assert v[8]==int(v[8])
   assert v[3]<=min(v[1],v[4])<=max(v[1],v[4])<=v[2]
  rows+=r;monthly.append(dict(month=month,rows=len(r),CRC='PASS',grid='PASS',OHLCV='PASS'))
  for name0,body in [(name,data),(name+'.CHECKSUM',ch)]:members.append(dict(name=name0,bytes=len(body),sha256=sha(body),url='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/'+name0))
 assert len(rows)==853 and [int(x[0]) for x in rows]==list(range(ms(2022,9),ms(2025,1),DAY))
 old=[x for x in rows if int(x[0])>=ms(2022,12)];assert len(old)==762 and sha(encode(old))==OLDHASH
 selected=[x for x in rows if int(x[0])>=ms(2022,9,23)];assert len(selected)==831;assert sum(int(x[0])<ms(2023,1) for x in selected)==100
 body=encode(selected)
 if expected:assert sha(body)==expected
 (out/'input.csv').write_bytes(body)
 report=dict(dataset_id='binance.spot.BTCUSDT.native1d.20220923-20241231.M1266-preflight-v1',identity=dict(exchange='binance',market_type='spot',symbol='BTCUSDT',timeframe='UTC1d',source='BinanceVision monthly trade-price klines'),rows=831,warmup_rows=100,evaluation_rows=731,input_bytes=len(body),input_sha256=sha(body),raw_source_rows=853,excluded_early_source_rows=22,input_start='2022-09-23T00:00:00Z',evaluation_start='2023-01-01T00:00:00Z',cutoff_exclusive='2025-01-01T00:00:00Z',old762_exact_sha256=OLDHASH,old762_rebuild_byte_hash_equal=True,monthly_QA=monthly,objects=members,license='CC-BY-NC-SA-4.0 plus BinanceVisionDatasetTerms',terms_sha256='dcf358e9d18f598a7a635fac80f6e643fa24a0e111a4d39bda47f1e246b31eb1',quality='DIAGNOSTIC_ONLY',PIT=False,finality=False,tradability=False,strategy_features_computed=False,history_runs=0)
 (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');return report
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**k):return None
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--acquire',action='store_true');p.add_argument('--old-raw',type=Path);p.add_argument('--expected');a=p.parse_args()
 if a.acquire:
  assert a.old_raw and shutil.disk_usage(a.raw.parent).free>5*1024**3+20*1024**2;a.raw.mkdir(exist_ok=False);receipt=[];used=0
  for old in sorted(a.old_raw.iterdir()):
   if old.name.startswith('BTCUSDT-1d-') and (old.name.endswith('.zip') or old.name.endswith('.CHECKSUM')):
    b=old.read_bytes();(a.raw/old.name).write_bytes(b)
  assert len(list(a.raw.iterdir()))==50
  try:
   for month in ['2022-09','2022-10','2022-11']:
    for suffix in ['.zip.CHECKSUM','.zip']:
     name=f'BTCUSDT-1d-{month}'+suffix;url='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/'+name
     assert shutil.disk_usage(a.raw).free>5*1024**3+20*1024**2
     with urllib.request.build_opener(NoRedirect).open(url,timeout=30) as r:
      assert r.status==200;cl=r.headers.get('Content-Length');assert cl is None or used+int(cl)<=20*1024**2;b=r.read(20*1024**2-used+1);assert used+len(b)<=20*1024**2
     temp=a.raw/(name+'.partial');temp.write_bytes(b);temp.rename(a.raw/name);used+=len(b);receipt.append(dict(url=url,bytes=len(b),sha256=sha(b),status=200,captured_utc=dt.datetime.now(dt.timezone.utc).isoformat()))
     (a.raw.parent/'fetch-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
  except Exception as e:
   receipt.append(dict(status='STOPPED',error=type(e).__name__+': '+str(e)));(a.raw.parent/'fetch-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');raise
 result=build(a.raw,a.output,a.expected);print(json.dumps({k:result[k] for k in ['rows','warmup_rows','evaluation_rows','input_sha256','input_bytes']}))
