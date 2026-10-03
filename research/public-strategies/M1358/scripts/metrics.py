"""Exact metrics function from pinned M0216 run_replay.py; no strategy execution."""
import numpy as np

def metrics(nav, initial):
    values = np.r_[initial, nav.equity.to_numpy()]
    returns = values[1:] / values[:-1] - 1
    return dict(
        total_return=float(values[-1] / initial - 1),
        cagr=float((values[-1] / initial) ** (365 / len(nav)) - 1),
        max_drawdown=float(np.min(values / np.maximum.accumulate(values) - 1)),
        sharpe_zero_cash=float(returns.mean() / returns.std(ddof=1) * np.sqrt(365))
        if returns.std(ddof=1) > 0
        else None,
        observations=len(nav),
        final_equity=float(values[-1]),
    )
