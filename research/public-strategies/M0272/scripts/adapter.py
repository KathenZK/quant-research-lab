# SPDX-License-Identifier: GPL-3.0-or-later
# Independently written Boolean adapter; original indicators and source equality are separately checked.
FEATURES = ['ema_5', 'ema_12', 'ema_21', 'bb_lowerband', 'bb_middleband', 'bb_upperband', 'min', 'max']
def rules(d):
    volume_ok = d["volume"] < d["volume"].rolling(30).mean().shift(1) * 20
    entry = volume_ok & (d["close"] < d["ema_5"]) & (d["close"] < d["ema_12"]) & (d["close"] == d['min']) & (d["close"] <= d["bb_lowerband"])
    leave = (d["close"] > d["ema_5"]) & (d["close"] > d["ema_12"]) & (d["close"] >= d['max']) & (d["close"] >= d["bb_upperband"])
    return entry, leave
