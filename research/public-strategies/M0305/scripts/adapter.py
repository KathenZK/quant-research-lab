# SPDX-License-Identifier: GPL-3.0-or-later
"""Literal original-rule Boolean adapter; indicators from pinned source. No fills here."""

FEATURES = [
    "rsi",
    "sma",
    "fisher_rsi",
    "mfi",
    "ema5",
    "ema10",
    "ema50",
    "ema100",
    "fastd",
    "fastk",
    "sar",
]


def rules(a):
    ent = (
        (a["rsi"] < 28)
        & (a["rsi"] > 0)
        & (a["close"] < a["sma"])
        & (a["fisher_rsi"] < -0.94)
        & (a["mfi"] < 16)
        & (
            (a["ema50"] > a["ema100"])
            | ((a["ema5"] > a["ema10"]) & (a["ema5"].shift() <= a["ema10"].shift()))
        )
        & (a["fastd"] > a["fastk"])
        & (a["fastd"] > 0)
    )
    return ent, (a["sar"] > a["close"]) & (a["fisher_rsi"] > 0.3)
