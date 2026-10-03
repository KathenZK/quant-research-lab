# SPDX-License-Identifier: GPL-3.0-or-later
# Independently written Boolean adapter; original indicators and source equality are separately checked.
FEATURES = ['macd', 'macdsignal', 'macdhist']
def rules(d):
    return (d["macd"] > 0) & (d["macd"] > d["macdsignal"]), d["macd"] < d["macdsignal"]
