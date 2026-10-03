# SPDX-License-Identifier: GPL-3.0-or-later
# Independent Boolean adapter; native source feature bridge checked separately.
FEATURES = ['sma5', 'sma200', 'rsi', 'resample_10_rsi', 'resample_40_rsi']
def rules(d):
    return (d['sma5'] >= d['sma200']) & (d['rsi'] < d['resample_40_rsi'] - 20), (d['rsi'] > d['resample_10_rsi']) & (d['rsi'] > d['resample_40_rsi'])
