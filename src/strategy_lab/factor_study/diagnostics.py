"""Descriptive TS association, dependence-aware uncertainty and train-only baseline."""
import numpy as np
import pandas as pd


def label_frame(frame, horizon):
    out = frame[['ts', 'close']].copy()
    out['label'] = frame.close.shift(-horizon) / frame.close - 1
    out['label_end'] = frame.ts.shift(-horizon)
    return out


def correlation(x, y, method):
    if len(x) < 2 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    if method == 'spearman':
        x, y = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    value = float(np.corrcoef(x, y)[0, 1])
    return value if np.isfinite(value) else None


def association(x, y, *, block_bars, replications, seed, minimum_pairs=30):
    """Paired circular block bootstrap on the original time grid, preserving gaps."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    keep = np.isfinite(x) & np.isfinite(y)
    n = int(keep.sum())
    out = {'n': n, 'grid_rows': len(x), 'pearson': None, 'spearman': None,
           'ci95': {}, 'status': 'INSUFFICIENT_PAIRS', 'axis': 'TIME_SERIES'}
    if n < minimum_pairs:
        return out
    if np.ptp(x[keep]) == 0 or np.ptp(y[keep]) == 0:
        out['status'] = 'CONSTANT_FEATURE_OR_LABEL'
        return out
    out.update(status='DESCRIPTIVE', pearson=correlation(x[keep], y[keep], 'pearson'),
               spearman=correlation(x[keep], y[keep], 'spearman'))
    rng = np.random.default_rng(seed)
    draws = {'pearson': [], 'spearman': []}
    for _ in range(replications):
        starts = rng.integers(0, len(x), size=int(np.ceil(len(x) / block_bars)))
        idx = ((starts[:, None] + np.arange(block_bars)) % len(x)).ravel()[:len(x)]
        a, b = x[idx], y[idx]
        valid = np.isfinite(a) & np.isfinite(b)
        for method in draws:
            r = correlation(a[valid], b[valid], method)
            if r is not None:
                draws[method].append(r)
    for method, values in draws.items():
        out['ci95'][method] = np.quantile(values, [.025, .975]).tolist() if values else None
    out['bootstrap_valid_draws'] = {k: len(v) for k, v in draws.items()}
    return out


def incremental(frame, factor, horizon, split, evaluation_start):
    labels = label_frame(frame, horizon)
    data = pd.DataFrame({'factor': factor, 'baseline': frame.close.pct_change(fill_method=None),
                         'y': labels.label, 'ts': frame.ts, 'label_end': labels.label_end})
    finite = np.isfinite(data[['factor', 'baseline', 'y']]).all(axis=1)
    # Purge training labels which reach the evaluation interval.
    train = data[finite & (data.ts >= pd.Timestamp(evaluation_start)) & (data.ts < pd.Timestamp(split))
                 & (data.label_end < pd.Timestamp(split))]
    test = data[finite & (data.ts >= pd.Timestamp(split))]
    if len(train) < 30 or len(test) < 30:
        return {'status': 'INSUFFICIENT_PAIRS', 'train_n': len(train), 'late_n': len(test)}
    scores = {}
    for name, cols in [('baseline', ['baseline']), ('augmented', ['baseline', 'factor'])]:
        mean = train[cols].mean().to_numpy()
        std = train[cols].std(ddof=0).to_numpy(copy=True)
        std[std == 0] = 1
        x = np.column_stack([np.ones(len(train)), (train[cols].to_numpy() - mean) / std])
        z = np.column_stack([np.ones(len(test)), (test[cols].to_numpy() - mean) / std])
        beta = np.linalg.lstsq(x, train.y.to_numpy(), rcond=None)[0]
        scores[name] = float(np.mean((test.y.to_numpy() - z @ beta) ** 2))
    return {'status': 'DESCRIPTIVE_PREVIOUS_EXPOSURE_UNKNOWN', 'train_n': len(train), 'late_n': len(test),
            'mse': scores, 'mse_reduction': scores['baseline'] - scores['augmented'],
            'positive_means_lower_error': True, 'holdout_certified': False}
