# SPDX-License-Identifier: GPL-3.0-or-later
# Independently written Boolean adapter; original indicators and source equality are separately checked.
FEATURES = ['lower', 'bbdelta', 'closedelta', 'tail', 'bb_lowerband', 'bb_middleband', 'ema_slow', 'volume_mean_slow']
def rules(d):
    bin_branch = (d["lower"].shift(1) > 0) & (d["bbdelta"] > d["close"] * 0.008) & (d["closedelta"] > d["close"] * 0.0175) & (d["tail"] < d["bbdelta"] * 0.25) & (d["close"] < d["lower"].shift(1)) & (d["close"] <= d["close"].shift(1))
    cluc_branch = (d["close"] < d["ema_slow"]) & (d["close"] < 0.985 * d["bb_lowerband"]) & (d["volume"] < d["volume_mean_slow"].shift(1) * 20)
    return bin_branch | cluc_branch, d["close"] > d["bb_middleband"]
