# SPDX-License-Identifier: GPL-3.0-or-later
"""Literal original-rule Boolean adapter; indicators from pinned source. No fills here."""

FEATURES = ["ema20", "ema50", "ema100", "ha_open", "ha_close"]


def rules(a):
    ent = (
        (a["ema20"] > a["ema50"])
        & (a["ema20"].shift() <= a["ema50"].shift())
        & (a["ha_close"] > a["ema20"])
        & (a["ha_open"] < a["ha_close"])
    )
    ext = (
        (a["ema50"] > a["ema100"])
        & (a["ema50"].shift() <= a["ema100"].shift())
        & (a["ha_close"] < a["ema20"])
        & (a["ha_open"] > a["ha_close"])
    )
    return ent, ext
