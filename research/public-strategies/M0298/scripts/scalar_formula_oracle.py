#!/usr/bin/env python3
"""Independent, synthetic-only batch004 formula audit. Never loads market data.

Original strategy files are AST-parsed, never imported or executed. Independent
scalar recurrences are checked against installed TA-Lib and pandas operations.
No execution engine, order fills or historical performance is claimed here.
"""
import argparse
import ast
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import talib



def nan(n):
    return np.full(n, np.nan)


def rsi(c, period):
    out = nan(len(c))
    if len(c) <= period:
        return out
    moves = np.diff(c[:period + 1])
    gain = sum(max(float(x), 0) for x in moves) / period
    loss = sum(max(-float(x), 0) for x in moves) / period
    for i in range(period, len(c)):
        if i > period:
            d = c[i] - c[i - 1]
            gain = (gain * (period - 1) + max(d, 0)) / period
            loss = (loss * (period - 1) + max(-d, 0)) / period
        out[i] = 100 * gain / (gain + loss) if gain + loss else 0
    return out


def macd(c):
    m, s, hist = nan(len(c)), nan(len(c)), nan(len(c))
    if len(c) < 34:
        return m, s, hist
    # TA-Lib aligns the fast EMA seed with the first slow EMA at index 25.
    slow = sum(c[:26]) / 26
    fast = sum(c[14:26]) / 12
    intermediate = {25: fast - slow}
    for i in range(26, len(c)):
        fast += 2 / 13 * (c[i] - fast)
        slow += 2 / 27 * (c[i] - slow)
        intermediate[i] = fast - slow
    signal = sum(intermediate[i] for i in range(25, 34)) / 9
    for i in range(33, len(c)):
        if i > 33:
            signal += 0.2 * (intermediate[i] - signal)
        m[i], s[i] = intermediate[i], signal
        hist[i] = m[i] - s[i]
    return m, s, hist


def bb(c, period):
    mid, low, high = nan(len(c)), nan(len(c)), nan(len(c))
    for i in range(len(c)):
        w = c[max(0, i - period + 1):i + 1]
        mid[i] = sum(w) / len(w)
        if len(w) > 1:
            dev = (sum((v - mid[i]) ** 2 for v in w) / (len(w) - 1)) ** 0.5
            low[i], high[i] = mid[i] - 2 * dev, mid[i] + 2 * dev
    return mid, low, high


def stoch(h, l, c):
    raw, k, d = nan(len(c)), nan(len(c)), nan(len(c))
    for i in range(4, len(c)):
        lo, hi = min(l[i - 4:i + 1]), max(h[i - 4:i + 1])
        raw[i] = 100 * (c[i] - lo) / (hi - lo) if hi != lo else 0
    for i in range(6, len(c)):
        k[i] = sum(raw[i - 2:i + 1]) / 3
    for i in range(8, len(c)):
        d[i] = sum(k[i - 2:i + 1]) / 3
    k[:8] = np.nan
    return k, d


def sar(h, l):
    out = nan(len(h))
    if len(h) < 2:
        return out
    down, up = l[0] - l[1], h[1] - h[0]
    is_long = not (down > 0 and down > up)
    acceleration = .02
    extreme, value = (h[1], l[0]) if is_long else (l[1], h[0])
    previous_h, previous_l = h[1], l[1]
    for i in range(1, len(h)):
        hi, lo = h[i], l[i]
        if is_long:
            if lo <= value:
                is_long = False
                value = max(extreme, previous_h, hi)
                out[i] = value
                acceleration, extreme = .02, lo
                value = max(value + acceleration * (extreme - value), previous_h, hi)
            else:
                out[i] = value
                if hi > extreme:
                    extreme, acceleration = hi, min(.2, acceleration + .02)
                value = min(value + acceleration * (extreme - value), previous_l, lo)
        else:
            if hi >= value:
                is_long = True
                value = min(extreme, previous_l, lo)
                out[i] = value
                acceleration, extreme = .02, hi
                value = min(value + acceleration * (extreme - value), previous_l, lo)
            else:
                out[i] = value
                if lo < extreme:
                    extreme, acceleration = lo, min(.2, acceleration + .02)
                value = max(value + acceleration * (extreme - value), previous_h, hi)
        previous_h, previous_l = hi, lo
    return out


def hammer(o, h, l, c):
    out = np.zeros(len(c), dtype=int)
    body, extent = abs(c - o), h - l
    for i in range(11, len(c)):
        small = body[i] < sum(body[i - 10:i]) / 10
        long_lower = min(o[i], c[i]) - l[i] > body[i]
        short_upper = h[i] - max(o[i], c[i]) < .1 * sum(extent[i - 10:i]) / 10
        near = min(o[i], c[i]) <= l[i - 1] + .2 * sum(extent[i - 6:i - 1]) / 5
        out[i] = 100 if small and long_lower and short_upper and near else 0
    return out


def features(x, independent):
    o, h, l, c = (x[k] for k in ('open', 'high', 'low', 'close'))
    m, s, hist = macd(c) if independent else talib.MACD(c)
    r7 = rsi(c, 7) if independent else talib.RSI(c, 7)
    r14 = rsi(c, 14) if independent else talib.RSI(c, 14)
    def bands(a, n):
        if independent:
            return bb(a, n)
        p = pd.Series(a).rolling(n, min_periods=1)
        return p.mean().to_numpy(), (p.mean() - 2 * p.std()).to_numpy(), (p.mean() + 2 * p.std()).to_numpy()
    b12 = bands(c, 12)
    b20 = bands((h + l + c) / 3, 20)
    k, d = stoch(h, l, c) if independent else talib.STOCH(h, l, c)
    sr = sar(h, l) if independent else talib.SAR(h, l)
    hm = hammer(o, h, l, c) if independent else talib.CDLHAMMER(o, h, l, c)
    fisher = np.tanh(.1 * (r14 - 50)) if independent else (np.exp(.2 * (r14 - 50)) - 1) / (np.exp(.2 * (r14 - 50)) + 1)
    prev_upper = np.r_[np.nan, b12[2][:-1]]
    e298 = (m > 0) & (m > s) & (b12[2] > prev_upper) & (r7 > 70)
    x298 = r7 > 80
    e304 = (r14 < 30) & (k < 20) & (b20[1] > c) & (hm == 100)
    x304 = (sr > c) & (fisher > .3)
    return dict(macd=m, macdsignal=s, macdhist=hist, rsi7=r7, rsi14=r14,
                bb12_mid=b12[0], bb12_low=b12[1], bb12_high=b12[2], bb20_low=b20[1],
                slowk=k, slowd=d, sar=sr, CDLHAMMER=hm, fisher_rsi=fisher,
                M0298_entry=e298, M0298_exit=x298, M0304_entry=e304, M0304_exit=x304)


def synthetic(n=6000):
    rng = np.random.default_rng(202610034)
    c = 100 * np.exp(np.cumsum(rng.normal(.00008, .009, n)))
    o = c * np.exp(rng.normal(0, .002, n))
    h = np.maximum(o, c) + c * rng.uniform(.0001, .015, n)
    l = np.minimum(o, c) - c * rng.uniform(.0001, .015, n)
    # Deliberate oversold hammer fixtures make Strategy002 entry checks non-vacuous.
    for end in range(120, n, 180):
        start = end - 20
        p = c[start - 1]
        for i in range(start, end):
            o[i], c[i] = p, p * .99
            h[i], l[i] = p * 1.001, c[i] * .999
            p = c[i]
        o[end], c[end] = p * .94, p * .94005
        h[end], l[end] = c[end] * 1.00001, o[end] * .995
    return dict(open=o, high=h, low=l, close=c)


def compare(left, right, context):
    checks = {}
    for k in left:
        a, b = left[k], right[k]
        if a.dtype.kind in 'biu':
            assert np.array_equal(a, b), (context, k, 'discrete mismatch')
            checks[k] = 0
        else:
            assert np.array_equal(np.isnan(a), np.isnan(b)), (context, k, 'NaN mismatch')
            diff = np.nanmax(abs(a - b))
            assert np.allclose(a, b, rtol=2e-10, atol=2e-10, equal_nan=True), (context, k, diff)
            checks[k] = float(diff)
    return checks


def source_receipt(record, path, expected_sha):
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected_sha
    tree = ast.parse(raw)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    attrs = {}
    for n in cls.body:
        if isinstance(n, ast.Assign):
            attrs[n.targets[0].id] = ast.literal_eval(n.value)
        elif isinstance(n, ast.AnnAssign):
            attrs[n.target.id] = ast.literal_eval(n.value)
    assert attrs['timeframe'] == '5m'
    return dict(record_id=record, sha256=expected_sha, bytes=len(raw), class_attributes=attrs,
                methods=[n.name for n in cls.body if isinstance(n, ast.FunctionDef)],
                original_code_executed=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--record-id', choices=['M0298','M0304'], required=True)
    parser.add_argument('--source', type=Path, help='Optional exact source for AST-only hash verification')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    x = synthetic()
    procedural, library = features(x, True), features(x, False)
    errors = compare(procedural, library, 'independent formulas vs installed reference')
    prefixes = []
    for end in (81, 750, 3000, 4999):
        for independent in (True, False):
            p = features({k:v[:end] for k,v in x.items()}, independent)
            full = procedural if independent else library
            compare(p, {k:v[:end] for k,v in full.items()}, 'prefix')
            changed = {k:v.copy() for k,v in x.items()}
            for k in changed:
                changed[k][end:] *= np.linspace(.2, 8, len(changed[k]) - end)
            f = features(changed, independent)
            compare({k:v[:end] for k,v in f.items()}, {k:v[:end] for k,v in full.items()}, 'future perturbation')
        prefixes.append(dict(prefix_bars=end, both_implementations_pass=True))
    counts = {k:int(v.sum()) for k,v in procedural.items() if k.endswith(('entry', 'exit'))}
    counts['M0298_collisions'] = int((procedural['M0298_entry'] & procedural['M0298_exit']).sum())
    assert all(v > 0 for v in counts.values()), counts
    source_hashes = {'M0298':'812a8d63b0e0ddff6b9bae582c4d573ab9a4ffec6dd0d1c5b8f8180f11db6d0b','M0304':'d1ca86a4ceb68ef828b35490ce1112330dad209cc3bb1e1b6c303c21ab3d8a90'}
    receipts = [source_receipt(args.record_id, args.source, source_hashes[args.record_id])] if args.source else []
    out = dict(schema='batch004-independent-synthetic-formula-audit/v1', status='PASS_SYNTHETIC_FORMULAS_ONLY',
               record_id=args.record_id, created_at_utc=datetime.now(timezone.utc).isoformat(), sources=receipts,
               source_check='PASS_AST_ONLY' if args.source else 'NOT_RUN_NO_SOURCE_SUPPLIED',
               synthetic_bars=6000, seed=202610034, max_abs_error=errors,
               prefixes_and_future_perturbations=prefixes, synthetic_signal_counts=counts,
               libraries=dict(python=sys.version, numpy=np.__version__, pandas=pd.__version__,
                              talib_python=talib.__version__, talib_core=talib.__ta_version__.decode()),
               observations=['Independent scalar RSI7/14, aligned-seed MACD, sample-std/min_periods1 BB12/20, STOCH5/3/3, SAR and CDLHAMMER recurrences compared against installed libraries.',
                             'Optional source is hash-verified and AST-read only when supplied; see source_check. Original external code is never executed.',
                             'Causality tests provide empirical finite-fixture evidence, not a universal proof.',
                             'No history was loaded, no C0 or input QA approval granted, no execution engine or ledger audit asserted.'],
               historical_strategy_runs=0, historical_control_runs=0, strict_reproductions=0,
               fidelity_ceiling='HYPOTHESIS', data_scope='DIAGNOSTIC_ONLY')
    destination = args.output
    if destination.exists():
        raise SystemExit('Refuse to overwrite existing audit output')
    destination.write_text(json.dumps(out, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(dict(status=out['status'], synthetic_signal_counts=counts, output=str(destination)), ensure_ascii=False))


if __name__ == '__main__':
    main()
