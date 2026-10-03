# SPDX-License-Identifier: GPL-3.0-or-later
# Independently written Boolean adapter; original indicators and source equality are separately checked.
FEATURES = ['rsi', 'emarsi', 'macd', 'adx', 'bb_lowerband', 'bb_middleband', 'bb_upperband', 'ema100']
def rules(d):
    entry = (d["close"] < d["ema100"]) & (d["close"] < 0.985 * d["bb_lowerband"]) & (d["volume"] < d["volume"].rolling(30).mean().shift(1) * 20)
    return entry, d["close"] > d["bb_middleband"]
