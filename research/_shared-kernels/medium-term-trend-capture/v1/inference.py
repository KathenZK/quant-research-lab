"""共同日历配对机会均值的有限五维联合区间；不搜索参数。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def paired_statistics(paired, config):
    policies = ['A', 'B', 'C']
    values = paired[policies].to_numpy(float)
    count = len(values)
    if count < 2:
        raise ValueError('Fewer than two complete common opportunities')
    points = values.mean(axis=0)
    points = np.r_[points, points[1]-points[0], points[2]-points[1]]
    calendar = pd.date_range(config['start'], pd.Timestamp(config['end'])-pd.Timedelta(days=1), freq='D')
    frame = paired.copy()
    frame['count'] = 1.
    sums = frame.groupby('origin_ts')[policies+['count']].sum().reindex(calendar, fill_value=0.).to_numpy()
    n = len(calendar)
    output = []
    for length in config['bootstrap']['blocks']:
        rng = np.random.default_rng(config['bootstrap']['seed']+length)
        extended = np.vstack([sums, sums[:length]])
        prefix = np.vstack([np.zeros((1, 4)), np.cumsum(extended, axis=0)])
        full_count, remainder = divmod(n, length)
        draws = []
        for offset in range(0, config['bootstrap']['repetitions'], 250):
            size = min(250, config['bootstrap']['repetitions']-offset)
            starts = rng.integers(0, n, size=(size, full_count))
            aggregate = (prefix[starts+length]-prefix[starts]).sum(axis=1)
            if remainder:
                tail = rng.integers(0, n, size=size)
                aggregate += prefix[tail+remainder]-prefix[tail]
            if (aggregate[:, 3] <= 0).any():
                raise ValueError('Bootstrap replicate without opportunities')
            means = aggregate[:, :3]/aggregate[:, 3:4]
            draws.append(np.column_stack([means, means[:, 1]-means[:, 0], means[:, 2]-means[:, 1]]))
        draws = np.vstack(draws)
        standard_error = draws.std(axis=0, ddof=1)
        safe = np.where(standard_error > 0, standard_error, 1.)
        max_error = np.max(np.abs((draws-points)/safe), axis=1)
        critical = float(np.quantile(max_error, config['bootstrap']['confidence']))
        lower, upper = points-critical*standard_error, points+critical*standard_error
        output.append(dict(block_days=length, repetitions=len(draws), critical=critical,
                           standard_error=standard_error.tolist(), lower=lower.tolist(), upper=upper.tolist()))
    low = np.min([r['lower'] for r in output], axis=0)
    high = np.max([r['upper'] for r in output], axis=0)
    return dict(n=count, names=['A', 'B', 'C', 'B_minus_A', 'C_minus_B'], points=points.tolist(),
                lower=low.tolist(), upper=high.tolist(), blocks=output,
                calendar_days=n, nonempty_origin_days=int((sums[:, 3]>0).sum()))
