"""Return-series diagnostics; no data fetching, position logic or promotion.

DSR: Bailey and Lopez de Prado (2014), equations 1-3; unannualized SR.
CSCV: Bailey et al., The Probability of Backtest Overfitting, section 2.
"""
from itertools import combinations
from math import e, sqrt
from statistics import NormalDist
import numpy as np


def finite(values, ndim=1):
    x = np.asarray(values, dtype=float)
    if x.ndim != ndim or not np.isfinite(x).all():
        raise ValueError('Finite data with the expected dimensions required')
    return x


def sharpe(x):
    sd = np.std(x, axis=0, ddof=1)
    if np.any(sd <= 0):
        raise ValueError('Zero variance; Sharpe is undefined')
    return np.mean(x, axis=0) / sd


def performance(returns, periods_per_year=252):
    r = finite(returns)
    if len(r) < 3 or (r <= -1).any() or periods_per_year <= 0:
        raise ValueError('At least three returns above -100% required')
    equity = np.r_[1.0, np.cumprod(1 + r)]
    drawdown = equity / np.maximum.accumulate(equity) - 1
    cagr = equity[-1] ** (periods_per_year / len(r)) - 1
    downside = np.sqrt(np.mean(np.minimum(r, 0) ** 2))
    sd = r.std(ddof=1)
    mdd = float(-drawdown.min())
    return {'observations': len(r), 'total_return': float(equity[-1] - 1), 'cagr': float(cagr),
            'max_drawdown': mdd, 'sharpe': float(r.mean() / sd * sqrt(periods_per_year)) if sd else None,
            'sortino': float(r.mean() / downside * sqrt(periods_per_year)) if downside else None,
            'calmar': float(cagr / mdd) if mdd else None}


def deflated_sharpe(returns, *, trial_sharpes, effective_trials):
    r, trials = finite(returns), finite(trial_sharpes)
    if len(r) < 4 or len(trials) < 2 or not 2 <= effective_trials <= len(trials):
        raise ValueError('DSR requires >=4 observations, >=2 trial SRs and declared effective trials')
    sr = float(sharpe(r))
    z = (r - r.mean()) / r.std(ddof=0)
    skew, kurt = float(np.mean(z ** 3)), float(np.mean(z ** 4))
    normal, gamma = NormalDist(), 0.5772156649015329
    threshold = trials.std(ddof=1) * ((1 - gamma) * normal.inv_cdf(1 - 1 / effective_trials)
                                    + gamma * normal.inv_cdf(1 - 1 / (effective_trials * e)))
    variance = 1 - skew * sr + (kurt - 1) * sr * sr / 4
    if variance <= 0:
        raise ValueError('Invalid Sharpe sampling variance')
    return {'value': normal.cdf((sr - threshold) * sqrt(len(r) - 1) / sqrt(variance)),
            'benchmark_sr': float(threshold), 'unannualized_sr': sr,
            'effective_trials': effective_trials, 'observed_trials': len(trials),
            'assumption': 'IID returns approximation; effective trial count supplied, not inferred'}


def pbo(returns_by_trial, *, blocks=8):
    x = finite(returns_by_trial, 2)
    if x.shape[1] < 2 or not 4 <= blocks <= 12 or blocks % 2 or x.shape[0] % blocks or x.shape[0] // blocks < 2:
        raise ValueError('CSCV requires >=2 trials, 4..12 even equal blocks and >=2 observations/block')
    pieces = np.split(np.arange(x.shape[0]), blocks)
    logits = []
    for chosen in combinations(range(blocks), blocks // 2):
        other = [i for i in range(blocks) if i not in chosen]
        train = x[np.concatenate([pieces[i] for i in chosen])]
        test = x[np.concatenate([pieces[i] for i in other])]
        train_sr = sharpe(train)
        # Include all tied in-sample winners; do not favor an arbitrary column.
        winners = np.flatnonzero(train_sr == train_sr.max())
        test_sr = sharpe(test)
        for winner in winners:
            rank = 1 + np.sum(test_sr < test_sr[winner]) + (np.sum(test_sr == test_sr[winner]) - 1) / 2
            percentile = rank / (x.shape[1] + 1)
            logits.append((float(np.log(percentile / (1 - percentile))), 1 / len(winners)))
    total_weight = sum(w for _, w in logits)
    return {'value': sum(w for v, w in logits if v <= 0) / total_weight,
            'splits': int(total_weight), 'blocks': blocks, 'trial_count': x.shape[1],
            'tie_policy': 'midrank; average all tied IS winners', 'purged': False}


def plateau(scores, *, relative_tolerance=0.1):
    x = finite(scores)
    if len(x) < 3 or not 0 <= relative_tolerance < 1:
        raise ValueError('An ordered grid with >=3 scores and a tolerance in [0,1) is required')
    peak = int(np.argmax(x))
    floor = x[peak] - max(abs(x[peak]), 1e-12) * relative_tolerance
    left = right = peak
    while left > 0 and x[left - 1] >= floor:
        left -= 1
    while right + 1 < len(x) and x[right + 1] >= floor:
        right += 1
    return {'peak_index': peak, 'contiguous_width': right - left + 1,
            'grid_size': len(x), 'relative_tolerance': relative_tolerance}
