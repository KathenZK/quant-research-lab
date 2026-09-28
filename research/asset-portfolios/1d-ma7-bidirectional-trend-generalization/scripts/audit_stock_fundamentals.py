"""八只具有180日日线的真实股票：SEC发布时间与修订可用性审计，无收益选择。"""
from pathlib import Path
import argparse
import json
import hashlib
import pandas as pd

FAMILY=Path(__file__).resolve().parents[1]
SOURCE=FAMILY/'artifacts/official-source-review'
STOCKS=('AMZN','COIN','CRCL','HOOD','INTC','MSTR','PLTR','TSLA')
REVENUES=('RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','RevenueFromContractWithCustomerIncludingAssessedTax')

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',default='stock-fundamentals-availability-20260908');args=p.parse_args()
    out=FAMILY/'artifacts'/args.run_id;assert not out.exists();out.mkdir()
    coverage=pd.read_csv(FAMILY/'artifacts/p0-inputs-20260908/coverage.csv').set_index('symbol')
    rows=[];audit=[]
    for stock in STOCKS:
        subpath=SOURCE/f'sec-{stock.lower()}-submissions.json';factpath=SOURCE/f'sec-{stock.lower()}-companyfacts.json'
        sub=json.loads(subpath.read_text());facts=json.loads(factpath.read_text())
        assert stock in sub['tickers'] and int(sub['cik'])==int(facts['cik'])
        filings=pd.DataFrame(sub['filings']['recent'])
        filings['accepted']=pd.to_datetime(filings.acceptanceDateTime,utc=True)
        times=dict(zip(filings.accessionNumber,filings.accepted))
        financial=facts.get('facts',{}).get('us-gaap',{})
        source_facts=[]
        for metric,keys in [('profit',('NetIncomeLoss',)),('operating_cash',('NetCashProvidedByUsedInOperatingActivities',)),('revenue',REVENUES)]:
            for key in keys:
                for r in financial.get(key,{}).get('units',{}).get('USD',[]):
                    if r.get('form') not in ('10-K','10-K/A','10-Q','10-Q/A') or 'start' not in r:continue
                    a=pd.Timestamp(r['start']);b=pd.Timestamp(r['end'])
                    if not 330<=(b-a).days<=400:continue
                    accepted=times.get(r['accn'])
                    if accepted is None:continue
                    source_facts.append({**r,'metric':metric,'tag':key,'accepted':accepted})
        info=coverage.loc[f'{stock}/USDT:USDT'];start=pd.Timestamp(info.first_open)+pd.Timedelta(days=121);end=pd.Timestamp(info.last_open)
        days=pd.date_range(start,end,freq='D');chosen_keys=set();verified=0
        for opening in days:
            # Signal close becomes available only after a full UTC daily bar.
            decision=opening+pd.Timedelta(days=1)
            known=[x for x in source_facts if x['accepted']<=decision and pd.Timestamp(x['end'],tz='UTC')<decision]
            selected={}
            for metric in ('profit','operating_cash','revenue'):
                candidates=[x for x in known if x['metric']==metric]
                if candidates:
                    selected[metric]=sorted(candidates,key=lambda x:(x['end'],x['accepted'],x['tag']))[-1]
            row={'symbol':stock,'signal_close_utc':str(decision)}
            for metric,r in selected.items():
                row.update({metric:r['val'],metric+'_period_end':r['end'],metric+'_accn':r['accn'],metric+'_accepted_utc':str(r['accepted']),metric+'_tag':r['tag']})
                chosen_keys.add((metric,r['accn'],r['end']))
            rev=selected.get('revenue');profit=selected.get('profit');cash=selected.get('operating_cash')
            aligned=lambda r:bool(rev and r and rev['accn']==r['accn'] and rev['start']==r['start'] and rev['end']==r['end'] and rev['val']>0)
            row['profit_margin']=profit['val']/rev['val'] if aligned(profit) else None
            row['operating_cash_margin']=cash['val']/rev['val'] if aligned(cash) else None
            row['pit_annual_pair_available']=aligned(profit) and aligned(cash)
            verified+=row['pit_annual_pair_available'];rows.append(row)
        audit.append({'symbol':stock,'issuer':sub['name'],'cik':sub['cik'],'price_days':int(info.max_segment_bars),
            'post_warmup_days':len(days),'days_with_aligned_pit_annual_fields':verified,'unique_metric_accession_periods':len(chosen_keys),
            'submissions_sha256':hashlib.sha256(subpath.read_bytes()).hexdigest(),'facts_sha256':hashlib.sha256(factpath.read_bytes()).hexdigest(),
            'conclusion':'PIT_DATA_FEASIBLE_BUT_CONTRACT_SAMPLE_TOO_SHORT_FOR_CROSS_YEAR_GENERALIZATION'})
    pd.DataFrame(rows).to_csv(out/'daily-pit-availability.csv',index=False)
    pd.DataFrame(audit).to_csv(out/'issuer-coverage.csv',index=False)
    report={'stocks':len(STOCKS),'total_decision_days':len(rows),'annual_pairs_available':sum(r['pit_annual_pair_available'] for r in rows),
        'selection_or_return_regression_performed':False,'reason':'8 stocks, 86-98 post-warmup days each; no prior equity-perpetual market years or independent stock cohort of >=30 required by frozen applicability contract',
        'point_in_time_policy':'Require SEC accession acceptance timestamp <= closed-bar decision; only then take latest available period/revision; never backdate amendments. Require numerator and denominator same accession/period. Current ratios never used as historical substitutes.',
        'limitations':['companyfacts may omit nonstandard tags','recent submissions only; absent accession timestamps are missing, not inferred','daily financial availability is not stock contract executable net evidence']}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
