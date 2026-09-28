"""Archive public rule evidence only. Never execute downloaded code."""
from pathlib import Path
import re,json,hashlib,subprocess,concurrent.futures,datetime,shutil
ROOT=Path(__file__).resolve().parents[4]
F=Path(__file__).resolve().parents[1]; OUT=F/'artifacts/sources'; OUT.mkdir(parents=True,exist_ok=True)
QC=OUT/'QuantConnect__Tutorials/04 Strategy Library'
M=[1,5,9,10,11,12,13,136,14,16,18,19,15,21,22,23,24,25,28,33,31,35,34,40,36,39,37,38,91,152,102,229,114,155,199,113,61,58,66,83,77,125,162,207,78,92,353,211,354,269,355,271,1025,1028,1026,1023,1030,1027,1036,1033]
src=Path('/Users/ZK/Downloads/quant-strategies-100-zh.md')
shutil.copy2(src,F/'specs/original-list-20260908.md')
rows=[];prev=''
for line in src.read_text().splitlines():
 if not re.match(r'\| [A-E]\d+ \|',line):continue
 vals=[x.strip() for x in line.strip('|').split('|')]
 sid,name,rule,market,rating,url=vals
 if url.startswith('http'):prev=url
 else:url=prev
 r=dict(id=sid,name=name,rule=rule,market=market,original_rating=rating,source_url=url)
 if sid.startswith('A'):
  d=next(d for d in QC.iterdir() if int(d.name.split(' ')[0])==M[int(sid[1:])-1])
  r['source_directory']=str(d.relative_to(F))
  r['source_url']='https://github.com/QuantConnect/Tutorials/tree/master/04%20Strategy%20Library/'+d.name.replace(' ','%20')
  r['evidence_files']=[{'path':str(p.relative_to(F)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(d.glob('*.html'))]
 rows.append(r)
assert len(rows)==100 and len({r['id'] for r in rows})==100
(F/'specs/inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
urls={r['source_url'] for r in rows if not r['id'].startswith('A')}
for r in rows:
 if r['id'].startswith('A'):
  for p in (F/r['source_directory']).glob('*Algorithm.html'):
   urls.update(re.findall(r'src="(https://www.quantconnect.com/terminal/[^"]+)"',p.read_text()))
urls.update(['https://raw.githubusercontent.com/QuantConnect/Lean/master/Algorithm.Framework/Alphas/BasePairsTradingAlphaModel.py','https://raw.githubusercontent.com/QuantConnect/Lean/master/Algorithm.Framework/Alphas/PearsonCorrelationPairsTradingAlphaModel.py','https://www.alphavantage.co/support/#api-key','https://docs.data.nasdaq.com/docs/in-depth-api-guide','https://www.sec.gov/search-filings/edgar-application-programming-interfaces','https://data.binance.vision/','https://stooq.com/db/h/','https://www.cboe.com/us/indices/dashboard/vix/'])
def fetch(url):
 key=hashlib.sha256(url.encode()).hexdigest()[:20];out=OUT/'pages'/f'{key}.html';out.parent.mkdir(exist_ok=True)
 if out.exists():return dict(url=url,path=str(out.relative_to(F)),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),status='cached')
 p=subprocess.run(['curl','-sS','-L','--retry','1','--max-time','30','-A','Mozilla/5.0','-o',str(out)+'.tmp','-w','%{http_code}',url],capture_output=True,text=True)
 temp=Path(str(out)+'.tmp');status=p.stdout
 r=dict(url=url,http_status=status,error=p.stderr[:200],fetched_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
 if p.returncode==0 and status=='200' and temp.exists():temp.replace(out);r.update(path=str(out.relative_to(F)),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),bytes=out.stat().st_size)
 elif temp.exists():temp.unlink()
 return r
results=list(concurrent.futures.ThreadPoolExecutor(8).map(fetch,sorted(urls)))
(OUT/'pages-manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps({'inventory':len(rows),'urls':len(results),'fetched':sum('path'in r for r in results)},ensure_ascii=False))
