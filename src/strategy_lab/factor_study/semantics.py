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
        w = frame.iloc[max(0, i - 4) : i + 1]
        o, h, low, c = (row.get(k, np.nan) for k in ["open", "high", "low", "close"])
        x = w.close.dropna().to_numpy()
        hi, lo = w.high.max(), w.low.min()
        with np.errstate(divide="ignore", invalid="ignore"):
            if name == "KMID":
                v = np.divide(c - o, o)
            elif name == "KLEN":
                v = np.divide(h - low, o)
            elif name == "KUP":
                v = np.divide(h - np.maximum(o, c), o)
            elif name == "KLOW":
                v = np.divide(np.minimum(o, c) - low, o)
            elif name == "KSFT":
                v = np.divide(2 * c - h - low, o)
            elif name == "KMID2":
                v = np.divide(c - o, h - low + 1e-12)
            elif name in {"BETA5", "RSQR5", "RESI5"}:
                yy = w.close.to_numpy()
                xx = np.arange(1.0, len(yy) + 1)
                valid = np.isfinite(yy)
                if valid.sum() < 2:
                    v = np.nan
                else:
                    beta = np.linalg.lstsq(
                        np.c_[np.ones(valid.sum()), xx[valid]], yy[valid], rcond=None
                    )[0]
                    if name == "BETA5":
                        v = beta[1] / c
                    elif name == "RESI5":
                        v = (c - beta @ [1, xx[-1]]) / c
                    else:
                        v = (
                            np.corrcoef(xx[valid], yy[valid])[0, 1] ** 2
                            if not np.isclose(np.std(yy[valid], ddof=1), 0, atol=2e-5)
                            else np.nan
                        )
            elif name == "QTLU5":
                v = np.quantile(x, 0.8) / c if len(x) else np.nan
            elif name == "IMAX5":
                v = (
                    (np.argmax(w.high.to_numpy()) + 1) / 5
                    if w.high.notna().any()
                    else np.nan
                )
            elif name in {"CNTP5", "SUMP5"}:
                deltas = frame.close.diff().iloc[max(0, i - 4) : i + 1].to_numpy()
                if name == "CNTP5":
                    v = np.mean(deltas > 0)
                else:
                    finite = deltas[np.isfinite(deltas)]
                    v = (
                        np.sum(finite[finite > 0]) / (np.sum(np.abs(finite)) + 1e-12)
                        if len(finite)
                        else np.nan
                    )
            elif name == "ROC5":
                v = np.divide(frame.close.iloc[i - 5], c) if i >= 5 else np.nan
            elif name == "MA5":
                v = np.divide(np.mean(x), c) if len(x) else np.nan
            elif name == "STD5":
                v = np.divide(np.std(x, ddof=1), c) if len(x) >= 2 else np.nan
            elif name == "MAX5":
                v = np.divide(hi, c)
            elif name == "MIN5":
                v = np.divide(lo, c)
            elif name == "RANK5":
                v = (
                    (np.sum(x < c) + (np.sum(x == c) + 1) / 2) / len(x)
                    if len(x) and pd.notna(c)
                    else np.nan
                )
            elif name == "RSV5":
                v = np.divide(c - lo, hi - lo + 1e-12)
            else:
                raise ValueError(name)
        values.append(v)
    return np.array(values, dtype=float)


def hand_check(name):
    f = pd.DataFrame(
        {
            "open": [2.0, 2.0, 2.0, 2.0, 2.0, 2.0],
            "close": [1.0, 2.0, 2.0, 4.0, 5.0, 8.0],
            "high": [3.0, 3.0, 3.0, 5.0, 6.0, 9.0],
            "low": [0.5, 1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    # Window on row 5 is [2,2,4,5,8], mean=4.2, squared deviations sum=24.8.
    expected = {
        "KMID": 3.0,
        "KLEN": 4.0,
        "KUP": 0.5,
        "KLOW": 0.5,
        "KSFT": 3.0,
        "ROC5": 1 / 8,
        "MA5": 4.2 / 8,
        "STD5": np.sqrt(24.8 / 4) / 8,
        "MAX5": 9 / 8,
        "MIN5": 1 / 8,
        "RANK5": 1.0,
        "RSV5": 7 / (8 + 1e-12),
    }
    expected.update(
        KMID2=6 / (8 + 1e-12),
        BETA5=1.5 / 8,
        RSQR5=225 / 248,
        RESI5=0.8 / 8,
        QTLU5=5.6 / 8,
        IMAX5=1.0,
        CNTP5=0.8,
        SUMP5=7 / (7 + 1e-12),
    )
    np.testing.assert_allclose(
        QlibPriceFactor(name).compute(f).iloc[-1], expected[name], rtol=1e-12
    )
    # Average tie: at row 2, [1,2,2] -> rank 2.5 / 3.
    np.testing.assert_allclose(QlibPriceFactor("RANK5").compute(f).iloc[2], 2.5 / 3)


def validate_semantics(name, frame, fixture):
    hand_check(name)
    golden = json.loads(Path(fixture).read_text())
    if name not in golden["expected"]:
        golden = json.loads(
            Path(fixture).with_name("qlib-golden-extended.json").read_text()
        )
    small = pd.DataFrame(golden["input"], dtype=float)
    impl = QlibPriceFactor(name)
    np.testing.assert_allclose(
        impl.compute(small),
        np.array(golden["expected"][name], dtype=float),
        rtol=1e-10,
        atol=1e-12,
        equal_nan=True,
    )
    raw = impl.compute(frame)
    np.testing.assert_allclose(
        raw, reference(frame, name), rtol=1e-9, atol=1e-12, equal_nan=True
    )
    prefix = max(1, len(frame) - 7)
    np.testing.assert_allclose(
        impl.compute(frame.iloc[:prefix]),
        raw.iloc[:prefix],
        rtol=1e-12,
        atol=1e-12,
        equal_nan=True,
    )
    return {
        "hand_calculated": "PASS",
        "reference_parity": "PASS",
        "real_market_boundaries": "PASS",
        "official_reference": golden["reference"],
        "rows": len(frame),
        "real_numpy_reference": True,
        "prefix_invariance": True,
        "raw_nan": int(raw.isna().sum()),
        "raw_infinite": int(np.isinf(raw).sum()),
    }
