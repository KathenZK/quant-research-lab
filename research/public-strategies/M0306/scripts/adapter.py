# SPDX-License-Identifier: GPL-3.0-or-later
"""Literal original-rule Boolean adapter; indicators from pinned source. No fills here."""

FEATURES = [
    "adx",
    "slowadx",
    "cci",
    "fastk",
    "fastd",
    "slowfastk",
    "slowfastd",
    "ema5",
    "mean-volume",
]


def rules(a):
    ent = (
        ((a["adx"] > 50) | (a["slowadx"] > 26))
        & (a["cci"] < -100)
        & (a["fastk"].shift() < 20)
        & (a["fastd"].shift() < 20)
        & (a["slowfastk"].shift() < 30)
        & (a["slowfastd"].shift() < 30)
        & (a["fastk"].shift() < a["fastd"].shift())
        & (a["fastk"] > a["fastd"])
        & (a["volume"].rolling(12).mean() > 0.75)
        & (a["close"] > 0.000001)
    )
    ext = (
        (a["slowadx"] < 25)
        & ((a["fastk"] > 70) | (a["fastd"] > 70))
        & (a["fastk"].shift() < a["fastd"].shift())
        & (a["close"] > a["ema5"])
    )
    return ent, ext
