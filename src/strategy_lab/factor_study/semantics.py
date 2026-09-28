"""Independent NumPy oracle and hand arithmetic; synthetic tests are never research."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .factors import QlibPriceFactor


def reference(frame, name):
    """Scalar-loop reference, independent of pandas rolling implementation."""
    values = []
    for i, row in frame.reset_index(drop=True).iterrows():
        w = frame.iloc[max(0, i - 4):i + 1]
        o, h, low, c = (row.get(k, np.nan) for k in ['open', 'high', 'low', 'close'])
        x = w.close.dropna().to_numpy()
        hi, lo = w.high.max(), w.low.min()
        with np.errstate(divide='ignore', invalid='ignore'):
            if name == 'KMID':
                v = np.divide(c - o, o)
            elif name == 'KLEN':
                v = np.divide(h - low, o)
            elif name == 'KUP':
                v = np.divide(h - np.maximum(o, c), o)
            elif name == 'KLOW':
                v = np.divide(np.minimum(o, c) - low, o)
            elif name == 'KSFT':
                v = np.divide(2 * c - h - low, o)
            elif name == 'ROC5':
                v = np.divide(frame.close.iloc[i - 5], c) if i >= 5 else np.nan
            elif name == 'MA5':
                v = np.divide(np.mean(x), c) if len(x) else np.nan
            elif name == 'STD5':
                v = np.divide(np.std(x, ddof=1), c) if len(x) >= 2 else np.nan
            elif name == 'MAX5':
                v = np.divide(hi, c)
            elif name == 'MIN5':
                v = np.divide(lo, c)
            elif name == 'RANK5':
                v = (np.sum(x < c) + (np.sum(x == c) + 1) / 2) / len(x) if len(x) and pd.notna(c) else np.nan
            elif name == 'RSV5':
                v = np.divide(c - lo, hi - lo + 1e-12)
            else:
                raise ValueError(name)
        values.append(v)
    return np.array(values, dtype=float)


def hand_check(name):
    f = pd.DataFrame({'open': [2., 2., 2., 2., 2., 2.], 'close': [1., 2., 2., 4., 5., 8.],
                      'high': [3., 3., 3., 5., 6., 9.], 'low': [.5, 1., 1., 1., 1., 1.]})
    # Window on row 5 is [2,2,4,5,8], mean=4.2, squared deviations sum=24.8.
    expected = {'KMID': 3., 'KLEN': 4., 'KUP': .5, 'KLOW': .5, 'KSFT': 3.,
                'ROC5': 1 / 8, 'MA5': 4.2 / 8, 'STD5': np.sqrt(24.8 / 4) / 8,
                'MAX5': 9 / 8, 'MIN5': 1 / 8, 'RANK5': 1., 'RSV5': 7 / (8 + 1e-12)}
    np.testing.assert_allclose(QlibPriceFactor(name).compute(f).iloc[-1], expected[name], rtol=1e-12)
    # Average tie: at row 2, [1,2,2] -> rank 2.5 / 3.
    np.testing.assert_allclose(QlibPriceFactor('RANK5').compute(f).iloc[2], 2.5 / 3)


def validate_semantics(name, frame, fixture):
    hand_check(name)
    golden = json.loads(Path(fixture).read_text())
    small = pd.DataFrame(golden['input'], dtype=float)
    impl = QlibPriceFactor(name)
    np.testing.assert_allclose(impl.compute(small), np.array(golden['expected'][name], dtype=float),
                               rtol=1e-10, atol=1e-12, equal_nan=True)
    raw = impl.compute(frame)
    np.testing.assert_allclose(raw, reference(frame, name), rtol=1e-9, atol=1e-12, equal_nan=True)
    prefix = max(1, len(frame) - 7)
    np.testing.assert_allclose(impl.compute(frame.iloc[:prefix]), raw.iloc[:prefix],
                               rtol=1e-12, atol=1e-12, equal_nan=True)
    return {'hand_calculated': 'PASS', 'reference_parity': 'PASS', 'real_market_boundaries': 'PASS',
            'official_reference': golden['reference'], 'rows': len(frame),
            'real_numpy_reference': True, 'prefix_invariance': True,
            'raw_nan': int(raw.isna().sum()), 'raw_infinite': int(np.isinf(raw).sum())}
