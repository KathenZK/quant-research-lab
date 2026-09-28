#!/usr/bin/env python3
"""Independent arithmetic on exported ledgers; no candidate search or mutation."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/"artifacts"
def dump(name,x):
    (ART/name).write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
summary=json.loads((ART/'summary.json').read_text())
syms=summary['coverage']['symbols']
checks=[]
for m in summary['variant_metrics']:
    p=ART/m['variant']
    a=pd.read_csv(p/'account.csv').set_index('date')
    o=pd.read_csv(p/'orders.csv')
    pnl=pd.read_csv(p/'asset-pnl.csv')
    marketvalue=sum(a['shares_'+s]*a['close_'+s] for s in syms)
    diff=(a.equity-a.settled_cash-a.unsettled_sale_proceeds-a.dividend_receivable-marketvalue).abs().max()
    pdiff=abs(pnl.net_pnl_usd.sum()-(a.equity.iloc[-1]-10000))
    assert diff<1e-6 and pdiff<1e-6
    holdings={s:0 for s in syms}
    for d,row in a.iterrows():
        for _,r in o[(o.date==d)&o.status.eq('FILLED_OPEN_PROXY')].iterrows():
            holdings[r.symbol]+=int(r.quantity)*(1 if r.side=='BUY' else -1)
            assert r.quantity==int(r.quantity) and r.quantity>0
            assert r.signal_date<r.date and r.quantity_decision_date<r.date
            assert abs(r.notional_usd-r.quantity*r.fill_price)<1e-6
            assert abs(r.fee_usd-max(1,.005*r.quantity)-.00005*r.notional_usd)<1e-8
        for s in syms:
            assert holdings[s]==row['shares_'+s]
    checks.append({'variant':m['variant'],'max_nav_component_residual_usd':float(diff),'asset_pnl_residual_usd':float(pdiff),
                   'fee_total_residual_usd':float(abs(o.fee_usd.sum()-m['fees_usd'])),'holdings_replay':'PASS','prior_date_decisions':'PASS'})
dump('exported-ledger-arithmetic-audit.json',{'status':'PASS','checks':checks,'scope':'Independent exported CSV arithmetic, not independent market-data authentication or broker-fill evidence.'})

# A mathematically fully invested SPY total-return reference requested by task;
# uses explicit distribution index, fractional immediate reinvestment and zero broker cost.
spy=pd.read_csv(ART/'bars-SPY.csv').set_index('date')
main=pd.read_csv(ART/'trend_12m_risk10/account.csv').set_index('date')
dates=main.index
nav=10000*spy.loc[dates,'tr_index']/spy.loc[dates[0],'tr_index']
r=nav.pct_change(fill_method=None).dropna()
years=(pd.Timestamp(dates[-1])-pd.Timestamp(dates[0])).days/365.25
ref={'label':'FULLY_INVESTED_SPY_TOTAL_RETURN_OPPORTUNITY_REFERENCE_NON_EXECUTABLE',
     'start':dates[0],'end':dates[-1],'final_equity_usd':float(nav.iloc[-1]),'total_return':float(nav.iloc[-1]/10000-1),
     'cagr':float((nav.iloc[-1]/10000)**(1/years)-1),'max_drawdown':float((nav/nav.cummax()-1).min()),
     'annual_volatility':float(r.std()*np.sqrt(252)),
     'limitations':'100% mathematical exposure, immediate fractional dividend reinvestment, zero broker costs; distinct from integer-share SPY cash account and not a selection gate.'}
nav.to_csv(ART/'spy-fully-invested-reference.csv',header=['equity'])
dump('spy-fully-invested-reference.json',ref)
summary['opportunity_reference']=ref
summary['coverage'].update({'account_trading_sessions':len(main)-1,'account_rows_including_seed':len(main),
                           'original_window_status':'DATA_STARTUP_FAILED; PDBC 33 zero-volume warmup rows; admissibility frozen before results'})

orders=pd.read_csv(ART/'trend_12m_risk10/orders.csv')
real=[]
for idx in [orders.index[0],orders[orders.side.eq('SELL')].index[0]]:
    row=orders.loc[idx]
    q=int(row.quantity);raw=float(row.raw_open);adverse=raw*(1.0005 if row.side=='BUY' else .9995)
    expected_fee=max(1,.005*q)+q*adverse*.00005
    real.append({'case':str(row.date)+' '+row.side+' '+row.symbol,'quantity':q,'raw_open':raw,'calculated_fill':adverse,
                 'calculated_notional':q*adverse,'calculated_fee':expected_fee,'signal_date':row.signal_date,
                 'quantity_decision_date':row.quantity_decision_date,'settlement_date':row.settlement_date,
                 'fee_matches':bool(abs(expected_fee-row.fee_usd)<1e-8)})
dist=pd.read_csv(ART/'distribution-events.csv')
cash=pd.read_csv(ART/'trend_12m_risk10/cash-events.csv')
divrow=cash[cash.type.eq('dividend_entitlement')].sort_values('gross_usd',ascending=False).iloc[0]
ex=divrow.date;s=divrow.symbol
before=main.loc[main.index<ex].iloc[-1]
per=float(dist[(dist.symbol==s)&(dist.ex_date==ex)].amount_per_share.sum())
expected=before['shares_'+s]*per
real.append({'case':'largest distribution entitlement','symbol':s,'ex_date':ex,'shares_before_ex':int(before['shares_'+s]),
             'distribution_per_share':per,'expected_entitlement_usd':float(expected),'recorded_entitlement_usd':float(divrow.gross_usd),
             'diagnostic_payment_floor':divrow.due_date_floor,'no_double_count':bool(abs(expected-divrow.gross_usd)<1e-8)})
issuer_samples=[]
for d,amount,pay in [('2026-08-03',.317549,'2026-08-06'),('2026-09-01',.332044,'2026-09-04')]:
    vendor=float(dist[(dist.symbol=='IEF')&(dist.ex_date==d)].amount_per_share.iloc[0])
    issuer_samples.append({'symbol':'IEF','ex_date':d,'issuer_amount':amount,'vendor_amount':vendor,'difference_per_share':vendor-amount,
                           'issuer_pay_date':pay,'source':'https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf',
                           'finding':'vendor rounds to 3 decimals; issuer cash arrives earlier than 60-day diagnostic assumption; sample only'})
dump('real-trade-and-distribution-checks.json',{'real_examples':real,'issuer_samples':issuer_samples,
     'full_issuer_reconciliation':False,'fee_schedule_is_assumption':True})

latest=[]
for s in syms:
    b=pd.read_csv(ART/f'bars-{s}.csv').iloc[-1]
    price=float(b.close)
    latest.append({'symbol':s,'date':b.date,'close_usd':price,'one_share_fraction_of_10000':price/10000,
                   'shares_affordable_at_equal_weight_98pct_buffer':int(10000/7*.98/price),
                   'volume_shares':float(b.volume),'close_times_volume_usd':price*float(b.volume),
                   'one_share_minimum_fee_fraction':(1+price*.00005)/price,
                   'is_current_executable_quote':False})
pd.DataFrame(latest).to_csv(ART/'small-account-lot-check.csv',index=False)
summary['artifacts'].update({'exported_arithmetic_audit':'artifacts/exported-ledger-arithmetic-audit.json',
                            'full_spy_reference':'artifacts/spy-fully-invested-reference.json',
                            'real_examples':'artifacts/real-trade-and-distribution-checks.json'})
dump('summary.json',summary)

# Original family/context sources remain read-only and are pinned only for lineage.
base=Path('/Users/ZK/OpenCode/quant-strategy-lab')
paths=['AGENTS.md','.cursor/rules/data-quality-first.mdc','.cursor/rules/research-report-storage.mdc','docs/data-lake-spec.md',
       'research/platform/research-program-review/diagnostics/research-program-review-2026-09-08.md',
       'research/asset-portfolios/1d-ewmac-universal-trend/README.md',
       'research/asset-portfolios/1d-classic-ewmac-replication/README.md',
       'research/asset-portfolios/1d-tradfi-futures-tsmom/tf-1d-fut-tsmom-core-ledger.md']
if not (ART/'prior-context-source-manifest.json').exists():
    source_manifest=[{'source_path':str(base/p),'sha256':hashlib.sha256((base/p).read_bytes()).hexdigest(),'role':'read-only prior context; not inherited performance','source_read_date':'2026-09-08'} for p in paths]
    dump('prior-context-source-manifest.json',source_manifest)
hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name!='hashes.json' and '__pycache__' not in p.parts}
dump('hashes.json',hashes)
print(json.dumps({'exported_arithmetic':'PASS','variants':len(checks),'reference_spy':ref},ensure_ascii=False))
