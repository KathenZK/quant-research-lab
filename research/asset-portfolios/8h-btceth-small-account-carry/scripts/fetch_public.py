#!/usr/bin/env python3
"""Public OKX capture only. New captures require an unused output directory."""
from pathlib import Path
import argparse, concurrent.futures, datetime as dt, hashlib, json, time, urllib.request, urllib.parse
ROOT=Path(__file__).resolve().parents[1]
def iso(t=None): return dt.datetime.fromtimestamp(time.time() if t is None else t,dt.timezone.utc).isoformat()
def fetch(out,name,path):
    import subprocess
    url='https://www.okx.com'+path
    t0=time.time();tmp=out/(name+'.body.tmp');hdr=out/(name+'.headers.tmp')
    cp=subprocess.run(['curl','--fail','--silent','--show-error','--retry','2','--retry-all-errors','--retry-delay','1','--max-time','25','--dump-header',str(hdr),'--output',str(tmp),url],capture_output=True,text=True)
    if cp.returncode:
        (out/(name+'.error.json')).write_text(json.dumps({'url':url,'error':cp.stderr,'utc':iso()}));raise RuntimeError(cp.stderr)
    b=tmp.read_bytes();j=json.loads(b)
    if j.get('code')!='0':raise ValueError(j)
    m={'url':url,'local_start_utc':iso(t0),'local_end_utc':iso(),'headers_raw':hdr.read_text(),'sha256':hashlib.sha256(b).hexdigest(),'transport':'curl TLS validation default'}
    (out/(name+'.json')).write_bytes(b);(out/(name+'.meta.json')).write_text(json.dumps(m,indent=2));tmp.unlink();hdr.unlink();return j

def pages(out,name,path,target_start,key='fundingTime',maxpages=50):
    after=None; allrows=[]
    for p in range(maxpages):
        u=path+('&after='+str(after) if after is not None else '')
        j=fetch(out,name+f'_{p:02d}',u);rows=j['data']
        if not rows:break
        ts=[int(x[key]) if isinstance(x,dict) else int(x[0]) for x in rows]
        if after is not None and min(ts)>=after: raise ValueError('nonadvancing pagination')
        allrows.extend(rows);after=min(ts)
        if after<=target_start:break
        time.sleep(.13)
    else:raise ValueError('pagination budget exhausted')
    print(name,len(allrows),flush=True)
    return allrows

def main():
    a=argparse.ArgumentParser();a.add_argument('--output',required=True);args=a.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    timej=fetch(out,'server_time_start','/api/v5/public/time');server=int(timej['data'][0]['ts']);end=server//86400000*86400000;start=end-90*86400000
    src=ROOT/'artifacts/raw';inst=json.loads((src/'futures_instruments.json').read_text())['data'];selected={}
    for asset in ['BTC','ETH']:
        opts=[x for x in inst if x['instId'].startswith(asset+'-USD-') and x['ctType']=='inverse' and x['state']=='live' and 30<=(int(x['expTime'])-server)/86400000<=120]
        selected[asset]=min(opts,key=lambda x:int(x['expTime']))
    (out/'selection.json').write_text(json.dumps({'server_ts':server,'history_start':start,'history_end':end,'selected':selected},indent=2))
    ids=[a+'-USDT' for a in selected]+[a+'-USDT-SWAP' for a in selected]+[x['instId'] for x in selected.values()]
    for roundno in range(3):
        jobs=[(out,f'book_r{roundno}_{i}','/api/v5/market/books?'+urllib.parse.urlencode({'instId':i,'sz':100})) for i in ids]+[(out,f'book_r{roundno}_clock','/api/v5/public/time')]
        with concurrent.futures.ThreadPoolExecutor(7) as pool:
            list(pool.map(lambda p:fetch(*p),jobs))
        time.sleep(.5)
    jobs=[]
    for asset in ['BTC','ETH']:
        jobs.append((out,'funding_'+asset,'/api/v5/public/funding-rate-history?'+urllib.parse.urlencode({'instId':asset+'-USDT-SWAP','limit':100}),start,'fundingTime',5))
        for typ,instid in [('spot',asset+'-USDT'),('swap',asset+'-USDT-SWAP'),('expiry',selected[asset]['instId'])]:
            endpoint='history-candles';pstart=start
            if typ=='expiry':pstart=max(start,int(selected[asset]['listTime'])//3600000*3600000)
            jobs.append((out,typ+'_'+asset,'/api/v5/market/'+endpoint+'?'+urllib.parse.urlencode({'instId':instid,'bar':'1H','limit':300,'before':pstart-1}),pstart,'ts',35))
        jobs.append((out,'mark_'+asset,'/api/v5/market/history-mark-price-candles?'+urllib.parse.urlencode({'instId':asset+'-USDT-SWAP','bar':'1H','limit':100,'before':start-1}),start,'ts',35))
    errors=[]
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        futs={pool.submit(pages,*job):job[1] for job in jobs}
        for f in concurrent.futures.as_completed(futs):
            try:f.result()
            except Exception as e:errors.append({'dataset':futs[f],'error':repr(e)})
    for asset in ['BTC','ETH']:
        for name,path in [('current_funding_'+asset,'/api/v5/public/funding-rate?instId='+asset+'-USDT-SWAP'),('swap_tiers_'+asset,'/api/v5/public/position-tiers?instType=SWAP&tdMode=isolated&instFamily='+asset+'-USDT'),('expiry_tiers_'+asset,'/api/v5/public/position-tiers?instType=FUTURES&tdMode=isolated&instFamily='+asset+'-USD')]:
            try:fetch(out,name,path)
            except Exception as e:errors.append({'dataset':name,'error':repr(e)})
    fetch(out,'server_time_end','/api/v5/public/time');(out/'fetch_errors.json').write_text(json.dumps(errors,indent=2));print('errors',errors)
if __name__=='__main__':main()
