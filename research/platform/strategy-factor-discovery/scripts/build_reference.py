"""Maintenance-only golden generation from reviewed/pinned Qlib and TA-Lib.

Requires optional SciPy in an isolated environment; never runs in worker.
Source byte hashes below are allowlisted, not supplied by a request.
"""

import ast
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import linregress

ROOT = Path(__file__).resolve().parents[4]
REF = ROOT / "research/platform/strategy-factor-discovery/artifacts/local/reference"
OLD = ROOT / "research/platform/factor-research-loop/artifacts/local/reference"
PINS = {
    "qlib-ops.py": "6f648355725a85a9f17528d864281fc065f8a4f887261a9909f7495d5db42760",
    "qlib-rolling.pyx": "58b2e418a78558135cb1ecad88bfcff68cae98b2bb2695d8d2fade8b30c5dbf1",
}
for name, sha in PINS.items():
    assert hashlib.sha256((OLD / name).read_bytes()).hexdigest() == sha


class Expression:
    def __init__(self, value):
        self.value = value

    def load(self, *args):
        return self.value


# Only manually reviewed upstream operator classes, no imported source execution.
classes = {"Rolling", "Mean", "Sum", "IdxMax", "Quantile"}
module = ast.parse((OLD / "qlib-ops.py").read_text())
module.body = [
    n for n in module.body if isinstance(n, ast.ClassDef) and n.name in classes
]
ns = {"Expression": Expression, "ExpressionOps": object, "np": np, "pd": pd}
exec(compile(module, "<pinned reviewed Qlib operators>", "exec"), ns)
fpath = ROOT / "tests/fixtures/factor_study/qlib-golden.json"
golden = json.loads(fpath.read_text())
f = pd.DataFrame(golden["input"], dtype=float)
c = f.close


def op(name, value, *args):
    return ns[name](Expression(value), *args)._load_internal("fixture", 0, len(f) - 1)


reg = []
for i in range(len(c)):
    yy = c.iloc[max(0, i - 4) : i + 1].to_numpy()
    xx = np.arange(1.0, len(yy) + 1)
    valid = np.isfinite(yy)
    fit = linregress(xx[valid], yy[valid]) if valid.sum() > 1 else None
    reg.append(
        (fit.slope, yy[-1] - (fit.intercept + fit.slope * xx[-1]), fit.rvalue**2)
        if fit
        else (np.nan, np.nan, np.nan)
    )
r2 = pd.Series([x[2] for x in reg])
r2.loc[np.isclose(c.rolling(5, min_periods=1).std(), 0, atol=2e-5)] = np.nan
d = c - c.shift()
values = {
    "KMID2": (c - f.open) / (f.high - f.low + 1e-12),
    "BETA5": np.array([x[0] for x in reg]) / c,
    "RESI5": np.array([x[1] for x in reg]) / c,
    "RSQR5": r2,
    "QTLU5": op("Quantile", c, 5, 0.8) / c,
    "IMAX5": op("IdxMax", f.high, 5) / 5,
    "CNTP5": op("Mean", c > c.shift(), 5),
    "SUMP5": op("Sum", np.maximum(d, 0), 5) / (op("Sum", abs(d), 5) + 1e-12),
}
out = {
    "reference": {
        "revision": "be725493eb1a6bbb42bf11b37aa7669f59610ff1",
        "pins": PINS,
        "method": "SciPy linregress oracle matching reviewed pinned Qlib Cython mathematics (native compilation unavailable: Xcode license not accepted); reviewed upstream Rolling/Mean/Sum/IdxMax/Quantile classes; explicit loader arithmetic",
        "license": "MIT; Copyright Microsoft Corporation",
    },
    "input": golden["input"],
    "expected": {
        n: [float(x) if np.isfinite(x) else None for x in a] for n, a in values.items()
    },
}
fpath.with_name("qlib-golden-extended.json").write_text(
    json.dumps(out, indent=2) + "\n"
)
