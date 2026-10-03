# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent Boolean transcription; original zero-seeded TA features preserved."""

FEATURES = [
    "rsi",
    "emarsi",
    "adx",
    "minusdi",
    "minusdiema",
    "plusdi",
    "plusdiema",
    "lowsma",
    "highsma",
    "fastsma",
    "slowsma",
    "bigup",
    "bigdown",
    "trend",
    "preparechangetrend",
    "preparechangetrendconfirm",
    "continueup",
    "delta",
    "slowingdown",
]


def rules(a):
    rising = a["continueup"]
    turn = a["preparechangetrend"]
    confirm = a["preparechangetrendconfirm"]
    down = a["bigdown"]
    up = a["bigup"]
    common = (
        (a["slowsma"] > 0)
        & (a["close"] < a["highsma"])
        & (a["close"] < a["lowsma"])
        & (a["minusdi"] > a["minusdiema"])
        & (a["rsi"] >= a["rsi"].shift())
    )
    e1 = (~turn) & (~rising) & (a["adx"] > 25) & down & (a["emarsi"] <= 20)
    e2 = (~turn) & rising & (a["adx"] > 30) & down & (a["emarsi"] <= 20)
    e3 = (~rising) & (a["adx"] > 35) & up & (a["emarsi"] <= 20)
    e4 = rising & (a["adx"] > 30) & up & (a["emarsi"] <= 25)
    x1 = (
        (~confirm)
        & (~rising)
        & ((a["close"] > a["lowsma"]) | (a["close"] > a["highsma"]))
        & (a["highsma"] > 0)
        & down
    )
    x2 = (
        (~confirm)
        & (~rising)
        & (a["close"] > a["highsma"])
        & (a["highsma"] > 0)
        & ((a["emarsi"] >= 75) | (a["close"] > a["slowsma"]))
        & down
    )
    x3 = (
        (~confirm)
        & (a["close"] > a["highsma"])
        & (a["highsma"] > 0)
        & (a["adx"] > 30)
        & (a["emarsi"] >= 80)
        & up
    )
    x4 = (
        confirm
        & (~rising)
        & a["slowingdown"]
        & (a["emarsi"] >= 75)
        & (a["slowsma"] > 0)
    )
    x5 = (
        confirm
        & (a["minusdi"] < a["plusdi"])
        & (a["close"] > a["lowsma"])
        & (a["slowsma"] > 0)
    )
    return common & (e1 | e2 | e3 | e4), x1 | x2 | x3 | x4 | x5
