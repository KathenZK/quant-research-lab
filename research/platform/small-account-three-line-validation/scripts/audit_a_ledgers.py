"""Independent ETF share/cash/receivable reconstruction from retained files."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[4]
F=ROOT/'research/asset-portfolios/1d-small-account-slow-trend'
A=F/'artifacts'
OUT=Path(__file__).resolve().parents[1]/'artifacts/independent-a-ledger-audit.json'
SYMS=['SPY','EFA','VNQ','IEF','TLT','GLD','PDBC']


def audit():
    summary=json.loads((A/'summary.json').read_text())
    result={'method':'No strategy engine imports. Rebuild integer shares, settled cash, sale and dividend receivables, mark values, distribution entitlements, costs and monthly trend decisions.',
            'export_tolerance_usd':1e-5,'tolerance_reason':'Account/order CSVs use 12 significant digits; original full precision metrics are checked against rounded retained ledgers.','variants':[]}
    bars={s:pd.read_csv(A/f'bars-{s}.csv').set_index('date') for s in SYMS}
    for m in summary['variant_metrics']:
        name=m['variant'];path=A/name
        q=pd.read_csv(path/'account.csv').set_index('date');o=pd.read_csv(path/'orders.csv');c=pd.read_csv(path/'cash-events.csv')
        fills=o[o.status.eq('FILLED_OPEN_PROXY')].copy()
        assert (fills.quantity%1==0).all() and (fills.quantity>0).all()
        assert (fills.date>fills.signal_date).all() and (fills.date>fills.quantity_decision_date).all()
        values=q[[f'shares_{s}' for s in SYMS]].to_numpy()*q[[f'close_{s}' for s in SYMS]].to_numpy()
        errors={'nav':float(np.max(np.abs(q.settled_cash+q.unsettled_sale_proceeds+q.dividend_receivable+values.sum(axis=1)-q.equity)))}
        signed=np.where(fills.side.eq('BUY'),1,-1)*fills.quantity
        shares= fills.assign(delta=signed).pivot_table(index='date',columns='symbol',values='delta',aggfunc='sum').reindex(index=q.index,columns=SYMS).fillna(0).cumsum()
        errors['share_reconstruction']=float(np.max(np.abs(shares.to_numpy()-q[[f'shares_{s}' for s in SYMS]].to_numpy())))
        buys=fills[fills.side.eq('BUY')];sells=fills[fills.side.eq('SELL')]
        buyout=(buys.notional_usd+buys.fee_usd).groupby(buys.date).sum().reindex(q.index,fill_value=0).cumsum()
        paid=c[c.type.isin(['sale_settlement','dividend_payment'])].groupby('date').amount_usd.sum().reindex(q.index,fill_value=0).cumsum()
        cash=10000-buyout+paid
        errors['settled_cash']=float(np.max(np.abs(cash-q.settled_cash)))
        sale_claim=(sells.notional_usd-sells.fee_usd).groupby(sells.date).sum().reindex(q.index,fill_value=0).cumsum()
        sale_paid=c[c.type.eq('sale_settlement')].groupby('date').amount_usd.sum().reindex(q.index,fill_value=0).cumsum()
        errors['sale_receivables']=float(np.max(np.abs(sale_claim-sale_paid-q.unsettled_sale_proceeds)))
        dividend=c[c.type.eq('dividend_entitlement')]
        div_claim=dividend.groupby('date').amount_usd.sum().reindex(q.index,fill_value=0).cumsum()
        div_paid=c[c.type.eq('dividend_payment')].groupby('date').amount_usd.sum().reindex(q.index,fill_value=0).cumsum()
        errors['dividend_receivables']=float(np.max(np.abs(div_claim-div_paid-q.dividend_receivable)))
        div_err=[]
        for row in dividend.itertuples():
            idx=q.index.get_loc(row.date)
            expected=q.iloc[idx-1][f'shares_{row.symbol}']*bars[row.symbol].loc[row.date,'distribution']
            div_err.append(abs(expected-row.gross_usd))
        errors['prior_share_dividend_entitlement']=max(div_err,default=0.)
        cost=np.maximum(1,.005*fills.quantity)+.00005*fills.notional_usd
        errors['commissions']=float(np.max(np.abs(cost-fills.fee_usd)))
        errors['turnover']=abs(float(fills.notional_usd.sum())-float(q.one_way_notional_cumulative.iloc[-1]))
        errors['fee_total']=abs(float(fills.fee_usd.sum())-m['fees_usd'])
        pp=pd.read_csv(path/'asset-pnl.csv')
        errors['pnl_sum']=abs(float(pp.net_pnl_usd.sum())-(float(q.equity.iloc[-1])-10000))
        errors['daily_pnl']=float(np.max(np.abs(pp.groupby('date').net_pnl_usd.sum().reindex(q.index).to_numpy()-q.equity.diff().fillna(0).to_numpy())))
        # Fill prices cross-check against the retained raw opening prints.
        raw_error=[]
        for row in fills.itertuples():raw_error.append(abs(row.raw_open-bars[row.symbol].loc[row.date,'open']))
        errors['raw_open']=max(raw_error,default=0.)
        assert max(errors.values())<1e-5,(name,errors)
        v=q.equity.to_numpy();dd=float((v/np.maximum.accumulate(v)-1).min())
        days=(pd.Timestamp(q.index[-1])-pd.Timestamp(q.index[0])).days
        cagr=(v[-1]/10000)**(365.25/days)-1
        assert abs(dd-m['max_drawdown'])<1e-9 and abs(cagr-m['cagr'])<1e-9
        assert (shares.to_numpy()>=0).all() and q.settled_cash.min()>=0
        result['variants'].append({'variant':name,'status':'CONDITIONAL_LEDGER_RECONCILED','final_equity':float(v[-1]),'cagr':float(cagr),'mdd':dd,'fills':len(fills),'rows_including_seed':len(q),'max_errors_usd':errors})
    q=pd.read_csv(A/'trend_12m_risk10/account.csv').set_index('date')
    c=pd.read_csv(A/'trend_12m_risk10/cash-events.csv')
    sample=c[c.type.eq('dividend_entitlement')].iloc[0]
    o=pd.read_csv(A/'trend_12m_risk10/orders.csv').iloc[0]
    result['real_examples']={'first_order':o.to_dict(),'first_dividend':sample.to_dict(),
      'first_order_cash_outflow':float(o.quantity*o.fill_price+o.fee_usd),
      'dividend_equation':'Prior close 5 SPY shares * $1.033 = $5.165 receivable on 2017-03-17; cash only released later.'}
    decisions=pd.read_csv(A/'trend_12m_risk10/decisions.csv')
    tri=pd.DataFrame({s:bars[s].tr_index for s in SYMS});dates=pd.to_datetime(tri.index)
    months=pd.Series(tri.index,index=dates).groupby(dates.to_period('M')).last().tolist()
    diffs=[]
    for row in decisions.itertuples():
        i=months.index(row.signal_date);momentum=tri.loc[row.signal_date,row.symbol]/tri.loc[months[i-12],row.symbol]-1
        diffs.append(abs(momentum-row.momentum))
        assert (row.target_weight>0)==(momentum>0)
    result['monthly_momentum_max_difference']=max(diffs)
    assert max(diffs)<1e-8
    result['scope']='Correct conditional cash/share accounting does not establish complete issuer pay dates, broker-specific entitlements, historical actual fills, out-of-sample alpha, or future drawdown bounds.'
    result['sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [F/'scripts/run_research.py',A/'summary.json',A/'metrics.csv']}
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'variants':len(result['variants']),'main':result['variants'][0],'real_examples':result['real_examples'],'monthly_momentum_max_difference':max(diffs)},indent=2))


if __name__=='__main__':audit()
