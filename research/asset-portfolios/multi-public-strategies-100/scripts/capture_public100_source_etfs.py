"""Supplement only the two missing native ETF histories for the C1 source check."""
import concurrent.futures
import json
import pandas as pd
from continue_public100_data import F,ART,fetch,partitions,bar_audit,put_json,sha

CONTRACT=F/'specs/continuation-source-corrections-contract-20260909.json'

def main():
    c=json.loads(CONTRACT.read_text())
    _,source=fetch(c['C1_source_url'],'public100_strategy_sources','C1-GEM-original.html')
    def one(symbol):
        a,b=[int(pd.Timestamp(x).timestamp()) for x in c['raw_request']]
        url=f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={a}&period2={b}&interval=1d&includePrePost=false&events=div%2Csplits'
        p,r=fetch(url,'yahoo_finance',f'{symbol}-1d-source-correction.json')
        assert r['http_status']=='200'
        obj=json.loads(p.read_text())['chart']['result'][0];meta=obj['meta']
        assert meta['symbol']==symbol and meta['currency']=='USD' and meta['instrumentType']=='ETF'
        d=pd.DataFrame(obj['indicators']['quote'][0]);d['adjclose']=obj['indicators']['adjclose'][0]['adjclose']
        d['ts']=pd.to_datetime(obj['timestamp'],unit='s',utc=True)
        d=d[(d.ts>=pd.Timestamp(c['raw_request'][0]))&(d.ts<pd.Timestamp(c['raw_request'][1]))].reset_index(drop=True)
        d['payload_sha256']=r['sha256'];d['native_timezone']=meta['exchangeTimezoneName']
        venue={'PCX':'nyse_arca','BTS':'cboe_bzx'}[meta['exchangeName']]
        return {'symbol':symbol,'payload':r,'native_metadata':meta,'audit':bar_audit(d),'files':partitions(d,venue,'equity','1d','yahoo_finance',symbol)}
    with concurrent.futures.ThreadPoolExecutor(2) as ex:records=list(ex.map(one,c['new_symbols']))
    put_json(ART/'source-etfs-manifest.json',{'status':'raw_unaccepted','contract_sha256':sha(CONTRACT),'source':source,'records':records})
    for r in records:print(r['symbol'],r['audit'],flush=True)

if __name__=='__main__':main()
