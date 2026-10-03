# SPDX-License-Identifier: GPL-3.0-or-later
"""Literal original-rule Boolean adapter; indicators from pinned source. No fills here."""

FEATURES = ["rsi", "sma", "fastd", "fastk", "fisher_rsi_norma", "macd", "minus_di"]


def rules(a):
    ent = (
        (a["close"] > 0.000002)
        & (a["volume"] > a["volume"].rolling(150).mean() * 4)
        & (a["close"] < a["sma"])
        & (a["fastd"] > a["fastk"])
        & (a["rsi"] > 26)
        & (a["fastd"] > 1)
        & (a["fisher_rsi_norma"] < 5)
    )
    ext = (
        (a["rsi"] > 74)
        & (a["rsi"].shift() <= 74)
        & (a["macd"] < 0)
        & (a["minus_di"] > 4)
    )
    return ent, ext
