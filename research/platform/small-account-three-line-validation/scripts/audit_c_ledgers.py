"""Reconcile carry outputs directly to raw events and exported orders."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[4]
F=ROOT/'research/asset-portfolios/8h-btceth-small-account-carry'
R=F/'artifacts/results'
RAW=F/'artifacts/raw/capture_curl_20260908'
OUT=Path(__file__).resolve().parents[1]/'artifacts/independent-c-ledger-audit.json'


def book_price(levels,amount,inverse=False):
    remaining=amount; total=0.
    for row in levels:
        price,size=float(row[0]),float(row[1]);take=min(size,remaining)
        total+=take/price if inverse else take*price
        remaining-=take
        if remaining<1e-9:break
    assert remaining<1e-9
    return amount/total if inverse else total/amount


def audit():
    result={'method':'Independent raw funding-rate/mark-price joins, order cash flows, inverse coin equations and book depth. No research engine imported.','assets':{}}
    summary=json.loads((R/'summary.json').read_text())
    orders=pd.read_csv(R/'orders.csv')
    quotes=pd.read_csv(R/'quotes_and_economics.csv')
    for asset in ['BTC','ETH']:
        funding=pd.read_csv(R/f'{asset.lower()}_funding_events.csv')
        eq=pd.read_csv(R/f'{asset.lower()}_account_hourly.csv')
        rates={}
        for path in sorted(RAW.glob(f'funding_{asset}_[0-9][0-9].json')):
            for row in json.loads(path.read_text())['data']:
                ts=int(row['fundingTime']);rate=float(row['realizedRate'])
                assert ts not in rates or rates[ts]==rate
                rates[ts]=rate
        marks={}
        for path in sorted(RAW.glob(f'mark_{asset}_[0-9][0-9].json')):
            for row in json.loads(path.read_text())['data']:
                if row[-1]=='1': marks[int(row[0])]=float(row[1])
        direct=np.array([r.quantity*rates[int(r.ts)]*marks[int(r.ts)] for r in funding.itertuples()])
        assert np.max(np.abs(direct-funding.funding_received_usdt))<1e-9
        assert np.max(np.abs(np.cumsum(direct)-funding.cumulative_funding))<1e-9
        linear=orders[(orders.asset==asset)&orders.structure.isna()]
        pnl=linear.quote_cash_delta.sum()+linear.quote_pnl.sum()-linear.quote_fee[linear.leg=='linear_perpetual'].sum()+direct.sum()
        equity_direct=eq.cash_usdt+eq.spot_value_usdt+eq.isolated_wallet_usdt+eq.derivative_unrealized_usdt
        assert np.max(np.abs(equity_direct-eq.equity_usd))<1e-7
        assert abs(10000+pnl-eq.equity_usd.iloc[-1])<1e-7
        metric=summary['assets'][asset]['perpetual_history_base']
        assert abs(pnl-metric['net_pnl_usd_proxy'])<1e-7
        v=np.r_[10000,eq.equity_usd.values];mdd=float((v/np.maximum.accumulate(v)-1).min())
        assert abs(mdd*100-metric['hourly_mdd_pct'])<1e-9
        inverse=orders[(orders.asset==asset)&orders.structure.eq('inverse_expiry')]
        buy=inverse[(inverse.leg=='spot')&(inverse.side=='buy')].iloc[0]
        sell=inverse[(inverse.leg=='spot')&(inverse.side=='sell')].iloc[0]
        short=inverse[(inverse.leg=='inverse_expiry')&(inverse.side=='sell')].iloc[0]
        cover=inverse[(inverse.leg=='inverse_expiry')&(inverse.side=='buy')].iloc[0]
        coin_pnl=short.usd_face_notional*(1/cover.price-1/short.price)
        terminal_coin=buy.net_base_qty+coin_pnl-short.fee_base-cover.fee_base
        assert abs(coin_pnl-cover.pnl_base)<1e-10
        assert abs(terminal_coin-sell.gross_base_qty)<1e-10
        inverse_pnl=buy.quote_cash_delta+terminal_coin*sell.price*(1-.001)
        ie=pd.read_csv(R/f'{asset.lower()}_expiry_account.csv')
        direct_ie=ie.cash_usdt+(ie.spot_qty_before_pnl-ie.entry_fee_coin+ie.inverse_pnl_coin)*ie.spot_open
        assert np.max(np.abs(direct_ie-ie.equity_usd))<1e-7
        assert abs(10000+inverse_pnl-ie.equity_usd.iloc[-1])<1e-7
        quote_errors=[]
        for q in quotes[quotes.asset.eq(asset)&quotes.structure.eq('inverse_expiry')].itertuples():
            sp=json.loads((RAW/f'book_r{q.round}_{asset}-USDT.json').read_text())['data'][0]
            de=json.loads((RAW/f'book_r{q.round}_{q.instrument}.json').read_text())['data'][0]
            slip=.0002*q.cost_multiplier; sf=.001*q.cost_multiplier; df=.0005*q.cost_multiplier
            S=book_price(sp['asks'],q.spot_gross_qty)*(1+slip)
            P=book_price(de['bids'],q.contracts,True)*(1-slip)
            assert abs(S-q.spot_entry_vwap)<1e-7 and abs(P-q.futures_entry_harmonic_vwap)<1e-7
            terminal=(float(sp['asks'][0][0])+float(sp['bids'][0][0]))/2
            coin=q.spot_gross_qty*(1-sf)-q.face_notional_usd/P*df+q.face_notional_usd*(1/terminal-1/P)-q.face_notional_usd/terminal*.0001*q.cost_multiplier
            pnl_quote=10000-q.spot_gross_qty*S+coin*terminal*(1-sf)*(1-slip)-10000
            error=abs(pnl_quote-q.conditional_flat_terminal_net_usd)
            assert error<1e-7
            quote_errors.append(error)
        result['assets'][asset]={'funding_events_raw_joined':len(direct),'negative_funding_events':int((funding.realized_rate<0).sum()),
            'funding_received_usdt_proxy':float(direct.sum()),'first_event_hand_check':funding.iloc[0].to_dict(),
            'perpetual_final_equity':float(10000+pnl),'perpetual_mdd':mdd,'inverse_history_final_equity':float(10000+inverse_pnl),
            'inverse_real_coin_pnl':float(coin_pnl),'quote_depth_reconstructions':len(quote_errors),'quote_max_error_usd':max(quote_errors)}
    qv=pd.read_csv(R/'quote_validation.csv')
    assert qv.valid.all() and (qv.pair_skew_ms<=2000).all() and (qv.absolute_age_vs_clock_ms<=10000).all()
    result['valid_quote_pairs']=len(qv)
    result['scope']='Conditional accounting reconciles; fee tier/access, actual fills, exact funding mark and historical interval proof, final index/spot hedge remain unverified. Current quotes mean captured 2026-09-08 ~13:00 UTC only.'
    result['sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [F/'scripts/reproduce.py',R/'summary.json',R/'orders.csv',R/'quotes_and_economics.csv']}
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':audit()
