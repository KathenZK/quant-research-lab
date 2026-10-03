# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual source buy/sell params -48/687, not constructor -50/100."""

FEATURES = ["macd", "macdsignal", "macdhist", "cci"]


def rules(a):
    ent = (a["macd"] > a["macdsignal"]) & (a["cci"] <= -48) & (a["volume"] > 0)
    ext = (a["macd"] < a["macdsignal"]) & (a["cci"] >= 687) & (a["volume"] > 0)
    return ent, ext
