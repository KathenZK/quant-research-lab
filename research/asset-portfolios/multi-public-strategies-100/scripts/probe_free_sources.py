"""Record actual access attempts; non-200 is not proof no free source exists."""
from pathlib import Path
import subprocess,json,hashlib,concurrent.futures,datetime
F=Path(__file__).resolve().parents[1];ROOT=F.parents[2]
P=ROOT/'data/raw/source_payloads'
PROVIDERS={'sec':'sec','stooq':'stooq','alphavantage':'alphavantage','alpaca':'alpaca','usno':'usno','source':'dropbox_usno_copy','binance_us':'binance_us','binance_oi':'binance_vision','yahoo':'yahoo_finance'}
def provider(key):
 return next(v for k,v in PROVIDERS.items() if key.startswith(k))
urls={
 'sec_companyfacts':'https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json',
 'sec_exchange_tickers':'https://www.sec.gov/files/company_tickers_exchange.json',
 'stooq_spy':'https://stooq.com/q/d/l/?s=spy.us&i=d&d1=20110101&d2=20260831',
 'alphavantage_demo':'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IBM&apikey=demo',
 'alpaca_unauthenticated':'https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Day&start=2024-01-01T00%3A00%3A00Z&limit=10',
 'usno_moon':'https://aa.usno.navy.mil/api/moon/phases/year?year=2025',
 'source_moon_csv':'https://www.dropbox.com/s/q9rt06tpfjlvymt/MoonPhase.csv?dl=1',
 'binance_us_universe':'https://api.binance.us/api/v3/exchangeInfo',
 'binance_oi_archive_sample':'https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2026-08-31.zip',
 'yahoo_delisted_UTX':'https://query1.finance.yahoo.com/v8/finance/chart/UTX?range=10y&interval=1d',
 'yahoo_delisted_ERUS':'https://query1.finance.yahoo.com/v8/finance/chart/ERUS?range=10y&interval=1d',
 'yahoo_delisted_GAF':'https://query1.finance.yahoo.com/v8/finance/chart/GAF?range=10y&interval=1d'
}
def fetch(item):
 key,u=item;source=provider(key);folder=P/f'source={source}/date=2026-09-08';folder.mkdir(parents=True,exist_ok=True);p=folder/('public100-probe-'+key+('.zip' if u.endswith('.zip') else '.response'));r=subprocess.run(['curl','-sSL','--retry','1','--max-time','30','-A','quant-strategy-lab public-data-research','-o',str(p),'-w','%{http_code}',u],capture_output=True,text=True)
 out={'id':key,'source':source,'url':u,'http_status':r.stdout,'error':r.stderr[:200],'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 if p.exists():out.update(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest());out['status']='raw_unaccepted'
 return out
r=list(concurrent.futures.ThreadPoolExecutor(4).map(fetch,urls.items()));(F/'artifacts/free-source-probes.json').write_text(json.dumps(r,indent=2));print([(x['id'],x['http_status'],x.get('bytes')) for x in r])
