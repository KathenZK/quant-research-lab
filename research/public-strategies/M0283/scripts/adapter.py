# SPDX-License-Identifier: GPL-3.0-or-later
"""Literal crossover variant; fixed -50/100 and no invented volume filter."""

FEATURES = ["macd", "macdsignal", "macdhist", "cci"]


def rules(a):
    ent = (
        (a["macd"] > a["macdsignal"])
        & (a["macd"].shift() <= a["macdsignal"].shift())
        & (a["cci"] <= -50)
    )
    ext = (
        (a["macd"] < a["macdsignal"])
        & (a["macd"].shift() >= a["macdsignal"].shift())
        & (a["cci"] >= 100)
    )
    return ent, ext
