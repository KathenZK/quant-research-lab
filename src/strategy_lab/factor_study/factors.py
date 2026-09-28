"""Registered, reviewed Qlib definitions. Never execute a submitted expression."""

from pathlib import Path
import hashlib
import numpy as np
from strategy_lab.data.factors.base import FactorMetadata, FactorRegistry, PandasFactor

FORMULAS = {
    "KMID": "($close-$open)/$open",
    "KLEN": "($high-$low)/$open",
    "KUP": "($high-Greater($open, $close))/$open",
    "KLOW": "(Less($open, $close)-$low)/$open",
    "KSFT": "(2*$close-$high-$low)/$open",
    "ROC5": "Ref($close, 5)/$close",
    "MA5": "Mean($close, 5)/$close",
    "STD5": "Std($close, 5)/$close",
    "MAX5": "Max($high, 5)/$close",
    "MIN5": "Min($low, 5)/$close",
    "RANK5": "Rank($close, 5)",
    "RSV5": "($close-Min($low, 5))/(Max($high, 5)-Min($low, 5)+1e-12)",
    "KMID2": "($close-$open)/($high-$low+1e-12)",
    "BETA5": "Slope($close, 5)/$close",
    "RSQR5": "Rsquare($close, 5)",
    "RESI5": "Resi($close, 5)/$close",
    "QTLU5": "Quantile($close, 5, 0.8)/$close",
    "IMAX5": "IdxMax($high, 5)/5",
    "CNTP5": "Mean($close>Ref($close, 1), 5)",
    "SUMP5": "Sum(Greater($close-Ref($close, 1), 0), 5)/(Sum(Abs($close-Ref($close, 1)), 5)+1e-12)",
}
FIELDS = {
    "KMID": ("close", "open"),
    "KLEN": ("high", "low", "open"),
    "KUP": ("high", "open", "close"),
    "KLOW": ("low", "open", "close"),
    "KSFT": ("close", "high", "low", "open"),
    "ROC5": ("close",),
    "MA5": ("close",),
    "STD5": ("close",),
    "MAX5": ("high", "close"),
    "MIN5": ("low", "close"),
    "RANK5": ("close",),
    "RSV5": ("close", "low", "high"),
    "KMID2": ("close", "open", "high", "low"),
    "BETA5": ("close",),
    "RSQR5": ("close",),
    "RESI5": ("close",),
    "QTLU5": ("close",),
    "IMAX5": ("high",),
    "CNTP5": ("close",),
    "SUMP5": ("close",),
}
SEMANTICS = {
    "missing_values": "Qlib operator semantics: skip NaN in rolling reductions; no fill. Study excludes incomplete input windows and nonfinite output.",
    "warmup": "Raw operator min_periods=1 (std needs 2); research mask requires full structural input span. ROC5 needs 6 bars.",
    "ties": "RANK5 average tied rank / count of nonmissing window values; TIME_SERIES only.",
    "window": "5 observations including current bar [t-4,t]; no centered windows. Point formulas use current bar.",
    "adjustment": "Study must bind explicit adjustment; first study UNADJUSTED spot, no equity corporate-action claim.",
    "available_at": "Only after current bar close; historical received_at unknown, not proven real-time availability.",
    "delay": "Ref(close,5) is close[t-5]; ROC5 is inverse price ratio, NOT pct_change(5). Label starts at current close.",
    "volume_unit": "Not consumed. Volume factors excluded pending native unit review.",
    "universe": "Compute separately per market identity and continuous segment; no cross-sectional rank or industry neutralization.",
    "ddof": "STD5 sample price standard deviation ddof=1, divided by current close; not return volatility.",
    "rsi": "Not implemented. SMA, Wilder and EMA RSI are not interchangeable.",
    "regression": "OLS price on observation positions with intercept; preserve positions across NaN. RESI is current endpoint residual. RSQR masks sample std close to zero with atol=2e-5, rtol=1e-5, matching pinned Qlib.",
    "argmax_quantile": "IMAX first tied maximum, 1-based position within truncated window /5; numpy argmax NaN behavior matches Qlib. QTLU linear interpolation at q=.8.",
    "changes": "CNTP compares current and prior close (NaN comparison is false); SUMP positive changes divided by absolute changes plus 1e-12. Research requires 6 complete inputs.",
}


def rolling_regression(values, kind):
    def calculate(y):
        x = np.arange(1.0, len(y) + 1)
        valid = np.isfinite(y)
        xx, yy = x[valid], y[valid]
        if len(yy) < 2:
            return np.nan
        dx, dy = xx - xx.mean(), yy - yy.mean()
        slope = np.dot(dx, dy) / np.dot(dx, dx)
        if kind == "BETA5":
            return slope
        if kind == "RESI5":
            return y[-1] - (yy.mean() + slope * (x[-1] - xx.mean()))
        if np.isclose(np.std(yy, ddof=1), 0, atol=2e-5):
            return np.nan
        return np.dot(dx, dy) ** 2 / (np.dot(dx, dx) * np.dot(dy, dy))

    return values.rolling(5, min_periods=1).apply(calculate, raw=True)


def code_hash():
    # Include helpers/constants, unlike the legacy compute-method-only hash.
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class QlibPriceFactor(PandasFactor):
    def __init__(self, name):
        if name not in FORMULAS:
            raise ValueError("Unregistered definition: " + name)
        self.name = name
        self.metadata = FactorMetadata(
            name=name,
            category="public_qlib_price",
            frequency="1d",
            lookback=6
            if name in {"ROC5", "CNTP5", "SUMP5"}
            else 5
            if name.endswith("5")
            else 1,
            inputs=FIELDS[name],
            market_types=("spot",),
            description="Pinned Qlib source formula; market transfer requires explicit study.",
            formula=FORMULAS[name],
        )

    @classmethod
    def _compute_source_hash(cls):
        return code_hash()

    def compute(self, frame):
        # compute_factor_frame groups assets; callers split other identities/segments.
        c = frame["close"] if "close" in frame else None
        name = self.name
        if name == "KMID":
            return (c - frame.open) / frame.open
        if name == "KLEN":
            return (frame.high - frame.low) / frame.open
        if name == "KUP":
            return (frame.high - np.maximum(frame.open, c)) / frame.open
        if name == "KLOW":
            return (np.minimum(frame.open, c) - frame.low) / frame.open
        if name == "KSFT":
            return (2 * c - frame.high - frame.low) / frame.open
        if name == "KMID2":
            return (c - frame.open) / (frame.high - frame.low + 1e-12)
        if name in {"BETA5", "RSQR5", "RESI5"}:
            value = rolling_regression(c, name)
            return value if name == "RSQR5" else value / c
        if name == "QTLU5":
            return c.rolling(5, min_periods=1).quantile(0.8) / c
        if name == "IMAX5":
            return (
                frame.high.rolling(5, min_periods=1).apply(
                    lambda x: x.argmax() + 1, raw=True
                )
                / 5
            )
        if name == "CNTP5":
            return (c > c.shift()).rolling(5, min_periods=1).mean()
        if name == "SUMP5":
            delta = c - c.shift()
            return np.maximum(delta, 0).rolling(5, min_periods=1).sum() / (
                delta.abs().rolling(5, min_periods=1).sum() + 1e-12
            )
        if name == "ROC5":
            return c.shift(5) / c
        if name == "MA5":
            return c.rolling(5, min_periods=1).mean() / c
        if name == "STD5":
            return c.rolling(5, min_periods=1).std(ddof=1) / c
        if name == "MAX5":
            return frame.high.rolling(5, min_periods=1).max() / c
        if name == "MIN5":
            return frame.low.rolling(5, min_periods=1).min() / c
        if name == "RANK5":
            return c.rolling(5, min_periods=1).rank(method="average", pct=True)
        lo = frame.low.rolling(5, min_periods=1).min()
        hi = frame.high.rolling(5, min_periods=1).max()
        return (c - lo) / (hi - lo + 1e-12)


def registry(names):
    out = FactorRegistry()
    for name in names:
        out.register(QlibPriceFactor(name))
    return out


def definition_name(v):
    names = [n for n in FORMULAS if "Alpha158:" + n in v["source_native_ids"]]
    if len(names) != 1:
        raise ValueError("Ambiguous or unsupported native definition")
    return names[0]


def validate_definition(v):
    name = definition_name(v)
    if (
        name not in FORMULAS
        or v["raw_formula"] != FORMULAS[name]
        or v["source_revision"] != "be725493eb1a6bbb42bf11b37aa7669f59610ff1"
        or v["source_sha256"]
        != "814b7f7ab3d418ae3c87ce352220080b239eba2670eac9e38376b794be4075cb"
        or v["dialect"] != "qlib"
        or v["source_id"] != "qlib"
        or set(v["required_fields"]) != set(FIELDS[name])
        or v["commercial_use"] != "ALLOWED"
    ):
        raise ValueError(
            "Definition is not the reviewed registered implementation: " + name
        )
    return QlibPriceFactor(name)
