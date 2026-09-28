"""Checksum-verified native Binance spot 15m monthly archives; raw-only release.
The current governed Binance research bundle covers perp, not these spot inputs.
Raw is intentionally UNACCEPTED; native Freqtrade runs are diagnostic only.
"""
from pathlib import Path
import json,subprocess,hashlib,io,zipfile,concurrent.futures
import pandas as pd
import numpy as np
from strategy_lab.data.fs import atomic_write_path
ROOT=Path(__file__).resolve().parents[4];F=Path(__file__).resolve().parents[1]
C=json.loads((F/'specs/run-contract-v1.json').read_text());SNAP='public100_spot_v1'
PAY=ROOT/'data/raw/source_payloads/exchange=binance/market_type=spot/source=binance_vision_kline_monthly'/SNAP
PAY.mkdir(parents=True,exist_ok=True)
COLS=['open_time','open','high','low','close','volume','close_time','quote_volume','trade_count','taker_buy_base_volume','taker_buy_quote_volume','ignore']
def download(url,out):
 if out.exists():return True
 p=subprocess.run(['curl','-sS','-L','--retry','2','--max-time','40','-o',str(out)+'.tmp','-w','%{http_code}',url],capture_output=True,text=True)
 if p.returncode or p.stdout!='200':return False
 Path(str(out)+'.tmp').replace(out);return True
months=pd.date_range(C['crypto_raw_start'],pd.Timestamp(C['cutoff']).tz_localize(None)-pd.Timedelta(days=1),freq='MS').strftime('%Y-%m').tolist()
def fetch(task):
 sym,month=task;slug=sym.replace('/','');filename=f'{slug}-15m-{month}.zip';url=f'https://data.binance.vision/data/spot/monthly/klines/{slug}/15m/{filename}'
 p=PAY/filename;chk=PAY/(filename+'.CHECKSUM');rec=dict(symbol=sym,month=month,url=url)
 if not download(url,p) or not download(url+'.CHECKSUM',chk):return rec|{'error':'archive or checksum unavailable'}
 digest=hashlib.sha256(p.read_bytes()).hexdigest()
 if chk.read_text().split()[0]!=digest:return rec|{'error':'CHECKSUM_MISMATCH'}
 z=zipfile.ZipFile(p);df=pd.read_csv(z.open(z.namelist()[0]),header=None,names=COLS)
 unit='us' if int(df.open_time.iloc[0])>10**14 else 'ms'
 df['ts']=pd.to_datetime(df.open_time,unit=unit,utc=True);df['native_close_ts']=pd.to_datetime(df.close_time,unit=unit,utc=True)
 df['symbol']=sym;df['exchange']='binance';df['market_type']='spot';df['timeframe']='15m';df['source']='binance_vision_kline_monthly';df['acceptance_status']='raw_unaccepted';df['source_dataset_id']='binance.spot.ohlcv.15m.public100.raw.v1';df['archive_sha256']=digest;df['native_timestamp_unit']=unit
 expected=pd.date_range(pd.Timestamp(month,tz='UTC'),pd.Timestamp(month,tz='UTC')+pd.offsets.MonthBegin(1),freq='15min',inclusive='left')
 numeric=['open','high','low','close','volume','quote_volume','trade_count']
 bad=(df[numeric].isna().any(axis=1)|~np.isfinite(df[numeric]).all(axis=1)|(df[['open','high','low','close']]<=0).any(axis=1)|(df.volume<0)|(df.high<df[['open','close','low']].max(axis=1))|(df.low>df[['open','close','high']].min(axis=1)))
 errors=dict(duplicates=int(df.ts.duplicated().sum()),invalid_rows=int(bad.sum()),missing_bars=len(expected.difference(df.ts)),out_of_grid=len(pd.DatetimeIndex(df.ts).difference(expected)),closure_mismatch=int((df.native_close_ts!=df.ts+pd.Timedelta(minutes=15)-pd.Timedelta(1,unit=unit)).sum()),zero_volume_rows=int((df.volume==0).sum()))
 files=[]
 for day,g in df.groupby(df.ts.dt.strftime('%Y-%m-%d')):
  path=ROOT/f'data/raw/ohlcv/exchange=binance/market_type=spot/timeframe=15m/source=binance_vision_kline_monthly/date={day}/symbol={slug}__{SNAP}.parquet'
  if not path.exists():atomic_write_path(path,lambda tmp,g=g:g.to_parquet(tmp,index=False))
  files.append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 return rec|dict(rows=len(df),sha256=digest,checksum_path=str(chk.relative_to(ROOT)),archive_path=str(p.relative_to(ROOT)),audit=errors,files=files)
results=[]
with concurrent.futures.ThreadPoolExecutor(8) as ex:
 for r in ex.map(fetch,[(s,m) for s in C['crypto_pairs_source_order'] for m in months]):
  results.append(r)
  if 'error' in r or len(results)%14==0:print('archives',len(results),r['symbol'],r['month'],r.get('error','OK'),flush=True)
(F/'artifacts/spot-raw-manifest.json').write_text(json.dumps({'dataset_id':'binance.spot.ohlcv.15m.public100.raw.v1','status':'UNACCEPTED','scope':'EXPLICIT_DIAGNOSTIC','reason':'spot is outside pinned perp startup bundle; no normalized admission claimed','cutoff':C['cutoff'],'records':results},indent=2))
