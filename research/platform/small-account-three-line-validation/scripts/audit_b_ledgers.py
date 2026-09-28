"""Independent reconstruction of B account exports; no engine imports."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
F = ROOT / 'research/asset-portfolios/1d-tpsa-long-account'
OUT = Path(__file__).resolve().parents[1] / 'artifacts/independent-b-ledger-audit.json'


def audit():
    variants = json.loads((F/'artifacts/variant_metrics.json').read_text())
    result = {'method':'Rebuild wallet from trades, fees and assumed charges; value positions independently. No strategy module imported.', 'variants': []}
    for metric in variants:
        d = F/'artifacts'/metric['variant']
        q = pd.read_csv(d/'account_equity.csv')
        orders = pd.read_csv(d/'orders.csv')
        trades = pd.read_csv(d/'trades.csv')
        positions = pd.read_csv(d/'positions.csv')
        for frame, cols in [(q,['bar_open']), (orders,['time','decision_time']), (trades,['entry_time','exit_time','signal_date']), (positions,['bar_open'])]:
            for col in cols: frame[col] = pd.to_datetime(frame[col], utc=True)
        gross = trades.qty*(trades.exit_price-trades.entry_price)
        net = gross-trades.entry_fee-trades.exit_fee
        errors = {'trade_gross_pnl':float(np.max(np.abs(gross-trades.gross_pnl))),
                  'trade_price_fee_pnl':float(np.max(np.abs(net-trades.price_fee_pnl))),
                  'order_notional':float(np.max(np.abs(orders.qty*orders.fill_price-orders.notional_usd)))}
        charges = positions.groupby('bar_open').assumed_holding_charge_usd.sum()
        fees = orders.groupby('time').fee_usd.sum()
        gains = gross.groupby(trades.exit_time).sum()
        wallet = []
        for date in q.bar_open:
            wallet.append(10000 + gains[gains.index<=date].sum() - fees[fees.index<=date].sum() - charges[charges.index<=date].sum())
        wallet = np.array(wallet)
        errors['wallet'] = float(np.max(np.abs(wallet-q.wallet_balance)))
        markpnl = positions.qty*(positions.mark_close-positions.entry_price)
        marked = markpnl.groupby(positions.bar_open).sum().reindex(q.bar_open,fill_value=0).to_numpy()
        errors['position_pnl'] = float(np.max(np.abs(markpnl-positions.unrealized_pnl)))
        errors['equity'] = float(np.max(np.abs(wallet+marked-q.equity_ex_actual_funding)))
        errors['collateral_identity'] = float(np.max(np.abs(q.free_cash+q.reserved_collateral-q.wallet_balance)))
        v = np.r_[10000,q.equity_ex_actual_funding.to_numpy()]
        dd = float((v/np.maximum.accumulate(v)-1).min())
        assert max(errors.values()) < 1e-7, errors
        assert abs(dd-metric['max_drawdown_ex_actual_funding']) < 1e-12
        assert abs(v[-1]-metric['final_equity_ex_actual_funding']) < 1e-7
        assert len(trades) == metric['closed_trades']
        assert q.positions.max() <= 4 and q.free_cash.min() >= -1e-7
        assert not positions.duplicated(['bar_open','symbol']).any()
        assert (orders.time>=orders.decision_time).all()
        assert (trades.entry_time>=trades.signal_date+pd.Timedelta(days=1)).all()
        result['variants'].append({'variant':metric['variant'],'status':'CONDITIONAL_LEDGER_RECONCILED_NOT_NET_APPROVED',
            'equity':float(v[-1]),'mdd':dd,'closed_trades':len(trades),'max_errors_usd':errors,
            'actual_funding_all_missing':bool(orders.actual_funding_usd.isna().all()),
            'fill_equals_decision_boundary_count':int(orders.time.eq(orders.decision_time).sum()),
            'duplicate_valuation_timestamp_count':int(q.time.duplicated().sum()),
            'account_complete':metric['account_complete']})
    prices = pd.read_parquet(F/'artifacts/verified_price_frames.parquet',columns=['symbol','ts','open'])
    trades = pd.read_csv(F/'artifacts/ML_p040/trades.csv')
    samples = trades.iloc[[0,int(trades.price_fee_pnl.idxmax()),int(trades.price_fee_pnl.idxmin())]]
    result['real_trade_examples'] = []
    for _, t in samples.iterrows():
        enter = prices[(prices.symbol==t.symbol)&(prices.ts==pd.Timestamp(t.entry_time))].iloc[0]
        leave = prices[(prices.symbol==t.symbol)&(prices.ts==pd.Timestamp(t.exit_time))].iloc[0]
        ep = float(enter.open)*1.0004; xp = float(leave.open)*0.9996
        expected = t.qty*(xp-ep)-t.qty*(ep+xp)*0.001
        assert abs(expected-t.price_fee_pnl)<1e-7
        result['real_trade_examples'].append({'event_id':t.event_id,'qty':t.qty,'entry_native_open':float(enter.open),
            'exit_native_open':float(leave.open),'calculated_price_fee_pnl':expected,'saved_price_fee_pnl':t.price_fee_pnl,
            'formula':'q * (exit_open*0.9996 - entry_open*1.0004) - 0.001*q*(entry_open*1.0004+exit_open*0.9996)'})
    result['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [F/'scripts/run_account.py',F/'artifacts/variant_metrics.json',F/'specs/frozen-config.json']}
    result['verdict']='Arithmetic matches conditional account exports. Identity, funding, historical lot filters, source event consistency and boundary-price execution remain separate gates.'
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'audited_variants':len(result['variants']),'main':result['variants'][0],'examples':result['real_trade_examples']},indent=2))


if __name__=='__main__': audit()
