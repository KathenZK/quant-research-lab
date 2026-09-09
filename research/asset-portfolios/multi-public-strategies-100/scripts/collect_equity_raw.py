"""Yahoo native daily snapshots, UNACCEPTED, for explicitly untrusted diagnostics.
No fabricated trade_count/vwap/closure, no normalized promotion.
"""
from pathlib import Path
import json,subprocess,hashlib,datetime,concurrent.futures
import pandas as pd
from strategy_lab.data.fs import atomic_write_path
ROOT=Path(__file__).resolve().parents[4]; F=Path(__file__).resolve().parents[1]
C=json.loads((F/'specs/run-contract-v1.json').read_text())
START=int(pd.Timestamp(C['equity_raw_start'],tz='UTC').timestamp());END=int(pd.Timestamp(C['cutoff']).timestamp())
SOURCE='yahoo_finance';SNAP='public100_20260908_v1'
def fetch(sym):
 url=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={START}&period2={END}&interval=1d&events=div%2Csplits'
 payloadroot=ROOT/'data/raw/source_payloads/source=yahoo_finance/date=2026-09-08'/SNAP;payloadroot.mkdir(parents=True,exist_ok=True)
 p=payloadroot/f'{sym}.json'
 if not p.exists():
  run=subprocess.run(['curl','-sS','-L','--retry','2','--max-time','40','-A','Mozilla/5.0','-o',str(p)+'.tmp','-w','%{http_code}',url],capture_output=True,text=True)
  if run.returncode or run.stdout!='200':return dict(symbol=sym,error=run.stderr,http_status=run.stdout)
  Path(str(p)+'.tmp').replace(p)
 try:
  obj=json.loads(p.read_text())['chart']['result'][0];meta=obj['meta'];native=obj['indicators']['quote'][0]
  venues={'PCX':'nyse_arca','NMS':'nasdaq','NGM':'nasdaq','NCM':'nasdaq','NYQ':'nyse','BTS':'cboe_bzx'}
  venue=venues[meta['exchangeName']]
  df=pd.DataFrame(native);df['ts']=pd.to_datetime(obj['timestamp'],unit='s',utc=True)
  df['adjclose']=obj['indicators']['adjclose'][0]['adjclose'];df['symbol']=sym;df['exchange']=venue
  df['market_type']='equity';df['timeframe']='1d';df['source']=SOURCE;df['acceptance_status']='raw_unaccepted'
  df['source_dataset_id']=f'{SOURCE}.equity.1d.{SNAP}';df['timestamp_semantics']='provider daily session open timestamp';df['session_policy']='US primary venue regular session';df['adjustment_policy']='native quote OHLC and provider adjclose retained separately; see payload dividends/splits'
  df=df[df.ts<pd.Timestamp(C['cutoff'])].copy();files=[]
  for day,g in df.groupby(df.ts.dt.strftime('%Y-%m-%d')):
   out=ROOT/f'data/raw/ohlcv/exchange={venue}/market_type=equity/timeframe=1d/source={SOURCE}/date={day}/symbol={sym}__{SNAP}.parquet'
   if not out.exists():atomic_write_path(out,lambda tmp,g=g:g.to_parquet(tmp,index=False))
   files.append({'path':str(out.relative_to(ROOT)),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
  return dict(symbol=sym,rows=len(df),url=url,payload_path=str(p.relative_to(ROOT)),payload_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),first=str(df.ts.min()),last=str(df.ts.max()),venue=venue,acceptance_status='raw_unaccepted',blockers=['native trade_count unavailable','native quote_volume/vwap unavailable','session closure provenance not accepted'],files=files)
 except Exception as e:return dict(symbol=sym,error=str(e),payload_path=str(p.relative_to(ROOT)))
results=[]
with concurrent.futures.ThreadPoolExecutor(5) as ex:
 for r in ex.map(fetch,C['equity_symbols']):
  results.append(r);print(r['symbol'],r.get('rows'),r.get('error',''),flush=True)
(F/'artifacts/equity-raw-manifest.json').write_text(json.dumps({'dataset_id':f'{SOURCE}.equity.1d.{SNAP}','status':'UNACCEPTED','scope':'EXPLICIT_DIAGNOSTIC','cutoff':C['cutoff'],'records':results},indent=2))
