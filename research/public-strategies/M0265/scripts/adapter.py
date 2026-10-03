# SPDX-License-Identifier: GPL-3.0-or-later
"""Loaded buy_fastx25, buy_adx25, sell_fastx75; literal original signals."""

FEATURES = ["fastk", "fastd", "ema_high", "ema_close", "ema_low", "adx"]


def rules(a):
    cross = (a["fastk"] > a["fastd"]) & (a["fastk"].shift() <= a["fastd"].shift())
    ent = (
        (a["open"] < a["ema_low"])
        & cross
        & (a["fastk"] < 25)
        & (a["fastd"] < 25)
        & (a["adx"] > 25)
    )
    kcross = (a["fastk"] > 75) & (a["fastk"].shift() <= 75)
    dcross = (a["fastd"] > 75) & (a["fastd"].shift() <= 75)
    return ent, (a["open"] >= a["ema_high"]) | kcross | dcross
