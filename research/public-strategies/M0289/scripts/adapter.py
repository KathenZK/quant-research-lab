# SPDX-License-Identifier: GPL-3.0-or-later
# Independent Boolean adapter; native source feature bridge checked separately.
FEATURES = []
def rules(d):
    c = d.close
    entry = (c > c.shift(2) ** 3.849) & (c.shift(1) > c.shift(3) ** 3.849) & (c.shift(2) > c.shift(4) ** 3.849)
    exit = (c < c.shift(2) ** 3.798) | (c.shift(1) < c.shift(3) ** 3.798) | (c.shift(2) < c.shift(4) ** 3.798)
    return entry, exit
