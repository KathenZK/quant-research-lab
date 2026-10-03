# SPDX-License-Identifier: GPL-3.0-or-later
"""Literal original-rule Boolean adapter; indicators from pinned source. No fills here."""

import pandas as pd

FEATURES = ["average", "bb_middleband", "cci", "rsi", "mfi", "mfi_rsi_cci_smooth"]


def rules(a):
    avg = a["average"]
    first = (
        (avg.shift(5) > avg.shift(4))
        & (avg.shift(4) > avg.shift(3))
        & (avg.shift(3) > avg.shift(2))
        & (avg.shift(2) > avg.shift())
        & (avg.shift() < avg)
        & (a["low"].shift() < a["bb_middleband"])
        & (a["cci"].shift() < -100)
        & (a["rsi"].shift() < 30)
    )
    second = (
        (a["low"] < a["bb_middleband"])
        & (a["cci"] < -200)
        & (a["rsi"] < 30)
        & (a["mfi"] < 30)
    )
    third = (a["mfi"] < 10) & (a["cci"] < -150) & (a["rsi"] < a["mfi"])
    s = a["mfi_rsi_cci_smooth"]
    peak = (
        (s > 100)
        & (s.shift() > s)
        & (s.shift(2) < s.shift())
        & (s.shift(3) < s.shift(2))
    )
    green = pd.concat(
        [a["open"].shift(i) < a["close"].shift(i) for i in range(9)], axis=1
    ).all(axis=1)
    return (first | second | third) & (
        a["close"] > a["close"].shift()
    ), peak | green | ((a["cci"] > 200) & (a["rsi"] > 70))
