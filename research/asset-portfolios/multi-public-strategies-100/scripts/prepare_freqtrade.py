"""Verified raw -> rebuildable Freqtrade adapter. Untrusted diagnostic only."""
from pathlib import Path
import json,hashlib,concurrent.futures
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];F=Path(__file__).resolve().parents[1]
C=json.loads((F/'specs/run-contract-v1.json').read_text());M=json.loads((F/'artifacts/spot-raw-manifest.json').read_text())
CACHE=ROOT/'data/cache/public100/freqtrade';CACHE.mkdir(parents=True,exist_ok=True)
def one(pair):
 rec=[r for r in M['records'] if r['symbol']==pair];frames=[]
 for r in rec:
  assert 'error' not in r,r
  assert not any(v for k,v in r['audit'].items() if k!='zero_volume_rows'),r['audit']
  for f in r['files']:
   p=ROOT/f['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256']
   frames.append(pd.read_parquet(p))
 d=pd.concat(frames).sort_values('ts').set_index('ts')
 assert not d.index.has_duplicates
 assert len(pd.date_range(d.index[0],d.index[-1],freq='15min').difference(d.index))==0
 outputs=[]
 for tf,n in [('15m',1),('30m',2),('1h',4),('4h',16)]:
  freq={'15m':'15min','30m':'30min','1h':'1h','4h':'4h'}[tf]
  q=d.resample(freq,origin='epoch',label='left',closed='left').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
  sizes=d.close.resample(freq,origin='epoch').size();assert (sizes==n).all()
  q=q.reset_index().rename(columns={'ts':'date'});q[['open','high','low','close','volume']]=q[['open','high','low','close','volume']].astype(float)
  out=CACHE/f'{pair.replace("/","_")}-{tf}.feather';q.to_feather(out);outputs.append(dict(path=str(out.relative_to(ROOT)),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),rows=len(q)))
 return dict(pair=pair,files=outputs,zero_volume_rows=int((d.volume==0).sum()))
results=list(concurrent.futures.ThreadPoolExecutor(4).map(one,C['crypto_pairs_source_order']))
(F/'artifacts/freqtrade-adapter-manifest.json').write_text(json.dumps({'status':'EXPLORE_UNTRUSTED','input_manifest_sha256':hashlib.sha256((F/'artifacts/spot-raw-manifest.json').read_bytes()).hexdigest(),'aggregation':'complete UTC 15m buckets only; no filling','files':results},indent=2))
config={'dry_run':True,'trading_mode':'spot','max_open_trades':1,'stake_currency':'USDT','stake_amount':12,'tradable_balance_ratio':0.99,'dry_run_wallet':25,'fiat_display_currency':'USD','cancel_open_orders_on_exit':False,'dataformat_ohlcv':'feather','exchange':{'name':'binance','key':'','secret':'','pair_whitelist':C['crypto_pairs_source_order'],'pair_blacklist':[]},'pairlists':[{'method':'StaticPairList'}],'entry_pricing':{'price_side':'same','use_order_book':False},'exit_pricing':{'price_side':'same','use_order_book':False},'unfilledtimeout':{'entry':10,'exit':10,'unit':'minutes'}}
(F/'specs/freqtrade-backtest-config.json').write_text(json.dumps(config,indent=2))
print(json.dumps(results))
