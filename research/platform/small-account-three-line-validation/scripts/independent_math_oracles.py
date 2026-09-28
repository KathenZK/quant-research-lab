"""Small accounting oracles independent of all three research engines."""
from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path
import json


def check_oracles() -> dict:
    examples = []
    # Fully funded ETF cash, receivable and settlement accounting.
    initial, quantity, buy, sell = D('10000'), D('10'), D('100'), D('110')
    cash = initial - quantity * buy - D('1')
    receivable = quantity * D('2')
    nav_ex = cash + quantity * D('98') + receivable
    assert nav_ex == D('9999')  # Price drops by dividend; no free wealth.
    cash += receivable
    receivable = D('0')
    assert cash + quantity * D('98') == nav_ex
    proceeds_unsettled = quantity * sell - D('1')
    nav_sold = cash + proceeds_unsettled
    assert nav_sold == D('10118')
    examples.append({'case': 'ETF dividend receivable then sale settlement',
                     'expected_after_ex_date': float(nav_ex),
                     'expected_terminal': float(nav_sold),
                     'sale_proceeds_unsettled': float(proceeds_unsettled)})
    # Linear collateral is not spent notional and is not counted twice.
    q, e, x = D('2'), D('100'), D('110')
    fee = q * (e+x) * D('0.001')
    funding = q * D('105') * D('0.0001')
    long_net = q*(x-e)-fee-funding
    short_net = q*(e-x)-fee+funding
    assert long_net == D('19.5590') and short_net == D('-20.3990')
    assert long_net + short_net == -2*fee
    examples.append({'case': 'linear long/short positive funding at mark 105',
                     'long_pnl': float(long_net), 'short_pnl': float(short_net),
                     'funding_long_pays_short_receives': float(funding)})
    # A constant-quantity same-venue linear basis hedge cancels spot moves,
    # but does not make the basis itself or isolated margin immune to stress.
    for terminal in [D('50'), D('100'), D('200')]:
        spot_pnl = D('1')*(terminal-D('100'))
        future_pnl = D('1')*(D('102')-terminal)
        assert spot_pnl+future_pnl == D('2')
    examples.append({'case': 'linear expiry hedge at spot100/future102',
                     'gross_locked_pnl_if_terminal_basis_zero': 2.0})
    # Inverse hedge terminal identity; the purchased coin is also collateral.
    face, entry = D('5100'), D('102')
    q_inverse = face/entry
    terminals = []
    for terminal in [D('50'), D('100'), D('200')]:
        coin_pnl = face*(1/terminal-1/entry)
        usd = (q_inverse+coin_pnl)*terminal
        assert abs(usd-face) < D('1e-20')
        terminals.append({'settlement':float(terminal),'terminal_usd':float(usd)})
    examples.append({'case':'inverse expiry exact hedge q=N/F0',
                     'base_quantity':float(q_inverse),'terminal_scenarios':terminals})
    return {'status':'ORACLE_IDENTITIES_PASS_NOT_STRATEGY_APPROVAL',
            'independence':'No strategy modules imported; decimal hand-computable identities.',
            'examples':examples}


if __name__ == '__main__':
    output = Path(__file__).resolve().parents[1] / 'artifacts/independent-math-oracles.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    result = check_oracles()
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
