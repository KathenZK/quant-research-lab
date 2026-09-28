"""Generate synthetic TA-Lib comparison fixture; optional maintenance dependency."""

from pathlib import Path
import json
import numpy as np
import talib

n = 480
rng = np.random.default_rng(928)
c = 100 + np.cumsum(rng.normal(0.03, 1, n))
o = np.r_[c[0], c[:-1]]
h = np.maximum(o, c) + rng.uniform(0.1, 2, n)
low = np.minimum(o, c) - rng.uniform(0.1, 2, n)
expected = {
    "rsi": talib.RSI(c, 14),
    "cci": talib.CCI(h, low, c, 20),
    "williams": talib.WILLR(h, low, c, 14),
    "ultimate": talib.ULTOSC(h, low, c, 7, 14, 28),
    "aroon": talib.AROON(h, low, 25)[1],
    "trix": talib.TRIX(c, 12),
    "atr_compression": talib.ATR(h, low, c, 14) - talib.ATR(h, low, c, 100),
    "ema_cross": talib.EMA(c, 8) - talib.EMA(c, 21),
}
a, b, d = talib.BBANDS(c, 20, 2, 2, 0)
expected["bollinger_percent_b"] = (c - d) / (a - d)
out = {
    "reference": {
        "library": "TA-Lib",
        "version": talib.__version__,
        "native_version": str(talib.__ta_version__),
        "source": "https://github.com/TA-Lib/ta-lib",
        "synthetic": True,
    },
    "input": {k: v.tolist() for k, v in dict(open=o, high=h, low=low, close=c).items()},
    "expected": {
        k: [float(v) if np.isfinite(v) else None for v in a]
        for k, a in expected.items()
    },
}
Path(__file__).resolve().parents[4].joinpath(
    "tests/fixtures/discovery/indicators.json"
).write_text(json.dumps(out, indent=2) + "\n")
