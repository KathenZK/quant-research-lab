"""Independent Decimal indicators; original reviewer function AST preserved."""
from decimal import Decimal as D,getcontext
getcontext().prec=45

def ema(a, n):
    out = [None] * len(a)
    x = sum(a[:n]) / n
    out[n - 1] = x
    k = D(2) / (n + 1)
    for i in range(n, len(a)):
        x += (a[i] - x) * k
        out[i] = x
    return out

def sma(a, n):
    return [None if i < n - 1 else sum(a[i + 1 - n:i + 1]) / n for i in range(len(a))]

def rsi(a, n):
    out = [None] * len(a)
    ups = [max(a[i] - a[i - 1], D(0)) for i in range(1, len(a))]
    dns = [max(a[i - 1] - a[i], D(0)) for i in range(1, len(a))]
    u = sum(ups[:n]) / n
    d = sum(dns[:n]) / n
    for i in range(n, len(a)):
        if i > n:
            u = (u * (n - 1) + ups[i - 1]) / n
            d = (d * (n - 1) + dns[i - 1]) / n
        out[i] = D(100) * u / (u + d) if u + d else D(0)
    return out

def adx(h, l, c, n):
    out = [None] * len(c)
    tr = []
    pu = []
    mi = []
    for i in range(1, len(c)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
        dh = h[i] - h[i - 1]
        dl = l[i - 1] - l[i]
        pu.append(dh if dh > dl and dh > 0 else D(0))
        mi.append(dl if dl > dh and dl > 0 else D(0))
    t = sum(tr[:n - 1])
    p = sum(pu[:n - 1])
    m = sum(mi[:n - 1])
    dxs = []
    a = None
    for i in range(n, len(c)):
        t = t - t / n + tr[i - 1]
        p = p - p / n + pu[i - 1]
        m = m - m / n + mi[i - 1]
        dx = D(100) * abs(p - m) / (p + m) if p + m else D(0)
        dxs.append(dx)
        if i == 2 * n - 1:
            a = sum(dxs) / n
        elif i > 2 * n - 1:
            a = (a * (n - 1) + dx) / n
        if a is not None:
            out[i] = a
    return out

def features(rows):
    o, h, l, c, v = [[D(r[k]) for r in rows] for k in ['open', 'high', 'low', 'close', 'volume']]
    feats = {'hl2': [(x + y) / 2 for x, y in zip(o, c)], 'ema5': ema(c, 5), 'ema10': ema(c, 10), 'adx': adx(h, l, c, 14)}
    feats['rsi'] = rsi(feats['hl2'], 10)
    for n in [7, 14, 28]:
        feats['sma' + str(n)] = sma(c, n)
    en = []
    ex = []
    me = []
    mx = []
    for i in range(len(rows)):
        valid = i > 0 and all((feats[k][i] is not None and feats[k][i - 1] is not None for k in ['ema5', 'ema10', 'adx', 'rsi']))
        en.append(bool(valid and feats['rsi'][i] > 50 and (feats['rsi'][i - 1] <= 50) and (feats['ema5'][i] > feats['ema10'][i]) and (feats['ema5'][i - 1] <= feats['ema10'][i - 1]) and (feats['adx'][i] > 25) and (v[i] > 0)))
        ex.append(bool(valid and feats['rsi'][i] < 50 and (feats['rsi'][i - 1] >= 50) and (feats['ema5'][i] < feats['ema10'][i]) and (feats['ema5'][i - 1] >= feats['ema10'][i - 1]) and (feats['adx'][i] > 25) and (v[i] > 0)))
        valid = feats['sma28'][i] is not None
        me.append(bool(valid and D('.2950') < feats['sma7'][i] / feats['sma14'][i] < D('2.2545') and (D('.2950') < feats['sma14'][i] / feats['sma28'][i] < D('2.2545'))))
        mx.append(bool(valid and D('2.8144') < feats['sma14'][i] / feats['sma7'][i] < D('1.5459') and (D('2.8144') < feats['sma28'][i] / feats['sma14'][i] < D('1.5459'))))
    feats.update(hlhb_entry=en, hlhb_exit=ex, mab_entry=me, mab_exit=mx)
    return feats
