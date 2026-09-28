#!/usr/bin/env python3
"""Independent arithmetic from delivered CSV; does not import the research engine."""
from pathlib import Path
import csv,json,math,argparse
parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(Path(__file__).resolve().parents[1]/'artifacts/results'));args=parser.parse_args();R=Path(args.output)
def rows(n):return list(csv.DictReader((R/n).open()))
def f(r,k):return float(r[k] or 0)
checks=[]
for a in ['BTC','ETH']:
    fund=rows(a.lower()+'_funding_events.csv');value=sum(float(x['quantity'])*float(x['funding_mark_open_proxy'])*float(x['realized_rate']) for x in fund)
    reported=next(x for x in rows('perpetual_comparison.csv') if x['asset']==a and x['variant']=='cost1_delay0h')
    assert math.isclose(value,f(reported,'funding_received_usdt_proxy'),abs_tol=1e-8)
    od=[x for x in rows('orders.csv') if x['asset']==a and x.get('structure')!='inverse_expiry'];sb=next(x for x in od if x['leg']=='spot' and x['side']=='buy');ss=next(x for x in od if x['leg']=='spot' and x['side']=='sell');do=next(x for x in od if x['leg']=='linear_perpetual' and x['side']=='sell');dc=next(x for x in od if x['leg']=='linear_perpetual' and x['side']=='buy')
    account=10000+f(sb,'quote_cash_delta')+f(ss,'quote_cash_delta')+f(do,'base_qty')*(f(do,'price')-f(dc,'price'))-f(do,'quote_fee')-f(dc,'quote_fee')+value
    assert math.isclose(account,f(reported,'final_equity_usd'),abs_tol=1e-8)
    errors=[]
    for row in rows(a.lower()+'_account_hourly.csv'):
        eq=f(row,'cash_usdt')+f(row,'spot_value_usdt')+f(row,'isolated_wallet_usdt')+f(row,'derivative_unrealized_usdt');errors.append(abs(eq-f(row,'equity_usd')))
    assert max(errors)<1e-8
    od=[x for x in rows('orders.csv') if x['asset']==a and x.get('structure')=='inverse_expiry'];sb=next(x for x in od if x['leg']=='spot' and x['side']=='buy');ss=next(x for x in od if x['leg']=='spot' and x['side']=='sell');do=next(x for x in od if x['leg']=='inverse_expiry' and x['side']=='sell');dc=next(x for x in od if x['leg']=='inverse_expiry' and x['side']=='buy')
    pnl=f(do,'usd_face_notional')*(1/f(dc,'price')-1/f(do,'price'));sellqty=f(sb,'net_base_qty')-f(do,'fee_base')+pnl-f(dc,'fee_base');cash=10000+f(sb,'quote_cash_delta')+sellqty*f(ss,'price')-f(ss,'quote_fee');erows=rows(a.lower()+'_expiry_account.csv');assert math.isclose(sellqty,f(ss,'gross_base_qty'),abs_tol=1e-10);assert math.isclose(cash,f(erows[-1],'equity_usd'),abs_tol=1e-8)
    inverseerrors=[]
    for row in erows:
        eq=f(row,'cash_usdt')+(f(row,'spot_qty_before_pnl')-f(row,'entry_fee_coin')+f(row,'inverse_pnl_coin'))*f(row,'spot_open');inverseerrors.append(abs(eq-f(row,'equity_usd')))
    assert max(inverseerrors)<1e-8
    checks.append({'asset':a,'funding_rows':len(fund),'funding_received_usdt_rebuilt':value,'perpetual_final_equity_rebuilt':account,'perpetual_all_row_accounting_max_abs_error':max(errors),'expiry_final_equity_rebuilt':cash,'expiry_all_row_accounting_max_abs_error':max(inverseerrors),'expiry_closed_quantity':f(erows[-1],'spot_qty_before_pnl'),'expiry_closed_notional':f(erows[-1],'face_notional_usd')})
(R/'independent_arithmetic.json').write_text(json.dumps({'implementation_independence':'CSV-only arithmetic, no engine imports','checks':checks,'status':'PASS_FOR_ARITHMETIC_ONLY'},indent=2)+'\n');print(json.dumps(checks,indent=2))
