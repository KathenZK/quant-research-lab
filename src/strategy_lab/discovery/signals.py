"""Reviewed implementations of selected Graph hypotheses; no expression evaluation.

Source indicator facts are separate from the BTC/EUR/cash transfer assumptions.
All windows include the current CLOSED bar; execution is next open in frozen v2.
"""

import numpy as np
import pandas as pd

# One selected record per structural template; no parameter search.
METHODS = {
    "EV3-M0233-BTC-EUR": ("mean_reversion", "zscore_reversion"),
    "EV3-M0234-BTC-EUR": ("trend_filter", "price_sma"),
    "EV3-M0256-BTC-EUR": ("trend_filter", "ema_cross"),
    "M4692": ("monthly_trend", "monthly_sma"),
    "M4815": ("monthly_trend", "monthly_momentum"),
    "M5242": ("breakout", "monthly_channel"),
    "M5582": ("trend_filter", "sma_ribbon"),
    "M5625": ("directional_range", "vortex"),
    "M5669": ("price_oscillator", "cci"),
    "M5673": ("price_oscillator", "rsi"),
    "M5676": ("range_position", "williams"),
    "M5678": ("range_position", "ultimate"),
    "M5685": ("directional_range", "aroon"),
    "M5688": ("volatility_state", "mass_index"),
    "M5714": ("drawdown_state", "ulcer"),
    "M5725": ("price_oscillator", "bollinger_percent_b"),
    "M5732": ("price_oscillator", "cmo"),
    "M5749": ("volatility_state", "realized_volatility"),
    "M5772": ("trend_filter", "trix"),
    "M5779": ("volatility_state", "atr_compression"),
}


def smooth(x, n, alpha=None):
    """SMA seed followed by recursive smoothing; leading NaNs remain unobserved."""
    n = int(n)
    alpha = 2 / (n + 1) if alpha is None else alpha
    a = x.to_numpy(dtype=float)
    out = np.full(len(a), np.nan)
    first = next(
        (i for i in range(n - 1, len(a)) if np.isfinite(a[i - n + 1 : i + 1]).all()),
        None,
    )
    if first is not None:
        out[first] = a[first - n + 1 : first + 1].mean()
        for i in range(first + 1, len(a)):
            out[i] = alpha * a[i] + (1 - alpha) * out[i - 1]
    return pd.Series(out, index=x.index)


def rsi(c, n=14):
    d = c.diff()
    up = smooth(d.clip(lower=0), n, 1 / n)
    dn = smooth((-d).clip(lower=0), n, 1 / n)
    return (100 * up / (up + dn)).where(up + dn != 0, 0)


def components(b):
    c, h, low = b.close, b.high, b.low
    prev = c.shift()
    tr = pd.concat([h - low, (h - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    tr.iloc[0] = np.nan
    return c, h, low, tr


def signal_arrays(bars, record_id, *, modification=None):
    """Return enter/leave/diagnostic. Unknown identifiers fail closed."""
    if record_id not in METHODS and record_id != "INTERNAL_BUY_HOLD":
        raise ValueError("Unregistered method")
    c, h, low, tr = components(bars)
    valid = pd.Series(True, index=c.index)
    monthly = False
    leave = None
    if record_id == "INTERNAL_BUY_HOLD":
        value = pd.Series(1.0, index=c.index)
        state = value > 0
    elif record_id == "EV3-M0233-BTC-EUR":
        value = (c - c.rolling(20).mean()) / c.rolling(20).std(ddof=1)
        state = value < -1.5
    elif record_id == "EV3-M0234-BTC-EUR":
        value = c / c.rolling(50).mean() - 1
        state = value > 0
    elif record_id == "EV3-M0256-BTC-EUR":
        value = smooth(c, 8) - smooth(c, 21)
        prior = value.shift()
        state = (value > 0) & (prior <= 0) & (bars.volume > 0)
        leave = (value <= 0) & (prior > 0) & (bars.volume > 0)
        valid = prior.notna()
    elif record_id in {"M4692", "M4815"}:
        # Resample only for available month-end observations; never backfill a month.
        mask = bars.ts.dt.is_month_end
        monthly_close = pd.Series(c[mask].to_numpy(), index=bars.ts[mask])
        v = (
            monthly_close / monthly_close.rolling(10).mean() - 1
            if record_id == "M4692"
            else monthly_close / monthly_close.shift(12) - 1
        )
        value = pd.Series(bars.ts.map(v).to_numpy(), index=c.index)
        state = value > 0
        monthly = True
    elif record_id == "M5242":
        value = c - c.rolling(100).max()
        state = value >= 0
        monthly = True
    elif record_id == "M5582":
        averages = [c.rolling(n).mean() for n in (10, 20, 50, 100, 200)]
        value = pd.concat([a - b for a, b in zip(averages, averages[1:])], axis=1).min(
            axis=1, skipna=False
        )
        state = value > 0
    elif record_id == "M5625":
        value = (
            (h - low.shift()).abs().rolling(14).sum()
            - (low - h.shift()).abs().rolling(14).sum()
        ) / tr.rolling(14).sum()
        state = value > 0
    elif record_id == "M5669":
        tp = (h + low + c) / 3
        mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        value = (tp - tp.rolling(20).mean()) / (0.015 * mad)
        state = value > 100
    elif record_id == "M5673":
        value = rsi(c)
        state = value > 60
    elif record_id == "M5676":
        hi = h.rolling(14).max()
        lo = low.rolling(14).min()
        value = -100 * (hi - c) / (hi - lo)
        state = value > -20
    elif record_id == "M5678":
        low = pd.concat([low, c.shift()], axis=1).min(axis=1)
        bp = c - low
        bp.iloc[0] = np.nan
        av = [bp.rolling(n).sum() / tr.rolling(n).sum() for n in (7, 14, 28)]
        value = 100 * (4 * av[0] + 2 * av[1] + av[2]) / 7
        state = value > 70
    elif record_id == "M5685":
        value = h.rolling(26).apply(
            lambda x: 100 * (25 - np.argmax(x[::-1])) / 25, raw=True
        )
        state = value > 50
    elif record_id == "M5688":
        single = smooth(h - low, 9)
        double = smooth(single, 9)
        value = (single / double).rolling(25).sum()
        state = value > 27
    elif record_id == "M5714":
        dd = 100 * (c / c.rolling(14).max() - 1)
        value = np.sqrt(dd.pow(2).rolling(14).mean())
        state = value < 10
    elif record_id == "M5725":
        mean = c.rolling(20).mean()
        sd = c.rolling(20).std(ddof=0)
        value = (c - mean + 2 * sd) / (4 * sd)
        state = value > 0.8
    elif record_id == "M5732":
        # Unsmoothed rolling CMO, explicitly unlike TA-Lib Wilder-smoothed CMO.
        d = c.diff()
        up = d.clip(lower=0).rolling(14).sum()
        dn = (-d).clip(lower=0).rolling(14).sum()
        value = 100 * (up - dn) / (up + dn)
        state = value > 20
    elif record_id == "M5749":
        value = np.log(c / c.shift()).rolling(21).std(ddof=1) * np.sqrt(365)
        state = value < 0.15
        monthly = True
    elif record_id == "M5772":
        triple = smooth(smooth(smooth(c, 12), 12), 12)
        value = 100 * (triple / triple.shift() - 1)
        state = value > 0
    elif record_id == "M5779":
        value = smooth(tr, 14, 1 / 14) - smooth(tr, 100, 1 / 100)
        state = value < 0
    valid &= np.isfinite(value)
    if monthly:
        valid &= bars.ts.dt.is_month_end
    enter = (state & valid).to_numpy()
    leave = ((~state if leave is None else leave) & valid).to_numpy()
    if modification is not None:
        if modification != "two_close_confirmation":
            raise ValueError("Unregistered modification")
        if monthly or record_id == "EV3-M0256-BTC-EUR":
            raise ValueError("Confirmation only for daily persistent states")
        enter = enter & np.r_[False, enter[:-1]]
        leave = leave & np.r_[False, leave[:-1]]
    return enter, leave, value
