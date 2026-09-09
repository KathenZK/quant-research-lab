"""按独立逐窗口公式复核新面板，不调用主引擎重建函数作为参考。"""
from __future__ import annotations

import datetime as dt
import json
import time

import numpy as np
import pandas as pd

from family_common import FAMILY, load_panel, save_json, sha, verify_lock
from engine import GROUPS, build_panel, load_verified_frames


def main():
    identity = verify_lock()
    panel, panel_id = load_panel()
    out = FAMILY / 'artifacts/p1-independent-verification.json'
    if out.exists():
        raise FileExistsError(out)
    indexed = {s: g.reset_index(drop=True) for s, g in panel.groupby('symbol', sort=False)}
    cutoff = pd.Timestamp(json.loads((FAMILY / 'specs/input-request.json').read_text())['end'])
    checked_rows = checked_states = checked_labels = prefix_rows = 0
    errors, maximum = [], {'strength': 0., 'ATR': 0., 'Q': 0.}
    started = time.time()
    for number, (symbol, f) in enumerate(load_verified_frames(FAMILY / 'artifacts/p0-inputs'), 1):
        f = f.reset_index(drop=True)
        p = indexed[symbol]
        if len(p) != len(f) or not p.ts.equals(f.ts):
            raise ValueError(f'{symbol}: source row alignment differs')
        for col in ('open', 'high', 'low', 'close', 'volume', 'eligible', 'research_segment_id'):
            try:
                pd.testing.assert_series_equal(p[col], f[col], check_dtype=False,
                                               check_names=False, check_exact=True)
            except AssertionError as exc:
                raise ValueError(f'{symbol}: source {col} differs') from exc
        checked_rows += len(p)
        invalid = ~p.feature_valid
        for horizon in (1, 5, 10, 20, 40):
            if (p.loc[invalid, f'valid{horizon}'].any()
                    or not p.loc[invalid, f'q{horizon}'].isna().all()
                    or not p.loc[invalid, f'label{horizon}_status'].eq('PAST_INELIGIBLE').all()):
                errors.append(f'{symbol}:invalid features leaked labels')
        for _, segment in f.loc[f.eligible].groupby('research_segment_id', sort=False):
            ix = segment.index.to_numpy()
            c, h, low, o = (segment[col].to_numpy(float) for col in ('close', 'high', 'low', 'open'))
            n = len(c)
            atr = np.full(n, np.nan)
            tr = np.array([max(h[j] - low[j], abs(h[j] - c[j-1]), abs(low[j] - c[j-1]))
                           if j else h[j] - low[j] for j in range(n)])
            if n >= 14:
                atr[13] = sum(tr[:14]) / 14
                for j in range(14, n):
                    atr[j] = (13 * atr[j-1] + tr[j]) / 14
            ma = np.array([np.mean(c[j-6:j+1]) if j >= 6 else np.nan for j in range(n)])
            for j, row_i in enumerate(ix):
                row = p.iloc[row_i]
                if not f.research_window_valid.iloc[row_i]:
                    if row.feature_valid or any(bool(row[g]) for g in GROUPS):
                        errors.append(f'{symbol}:{j}:past eligibility')
                    continue
                s = j - 6
                r = np.log(c[s-19:s+1] / c[s-20:s])
                sigma = np.std(r, ddof=1)
                raw_x = np.log(c[s] / c[s-20]) / (sigma * np.sqrt(20)) if sigma > 0 else np.nan
                a = atr[j-1]
                expected_valid = np.isfinite(raw_x) and np.isfinite(a) and a > 0
                if bool(row.feature_valid) != expected_valid:
                    errors.append(f'{symbol}:{j}:feature validity')
                if not expected_valid:
                    continue
                maximum['strength'] = max(maximum['strength'], abs(row.strength_LONG - raw_x))
                maximum['ATR'] = max(maximum['ATR'], abs(row.atr14_lag - a))
                if not np.isclose(row.strength_LONG, raw_x, rtol=1e-9, atol=1e-9):
                    errors.append(f'{symbol}:{j}:strength value')
                if not np.isclose(row.strength_SHORT, -raw_x, rtol=1e-9, atol=1e-9):
                    errors.append(f'{symbol}:{j}:short strength value')
                if not np.isclose(row.atr14_lag, a, rtol=1e-10, atol=1e-10):
                    errors.append(f'{symbol}:{j}:ATR value')
                if row.anchor_time != f.ts.iloc[ix[s]]:
                    errors.append(f'{symbol}:{j}:anchor timestamp')
                if j+1 < n and row.entry_open != o[j+1]:
                    errors.append(f'{symbol}:{j}:entry open')
                for side, d in (('LONG', 1), ('SHORT', -1)):
                    x = d * raw_x
                    band = 0 if x <= 0 else 1 if x <= 1 else 2 if x <= 2 else 3
                    z = d * (c - ma)
                    adverse = [k for k in range(s+1, j) if z[k] < 0]
                    u = adverse[0] if adverse else None
                    pp = bool(z[s] > 0 and u is not None and
                              d * c[u] < max(d * c[s:u]) and
                              not any(z[k] > 0 for k in range(u+1, j)) and
                              z[j-1] < 0 and d * (c[j-1] - c[s]) < 0)
                    mm = bool(z[j] > 0 and z[j-1] < 0)
                    expected = {f'strength_bin_{side}': band,
                                f'P_{side}': pp, f'M_{side}': mm,
                                f'ALL_{side}': band > 0, f'HIGH_{side}': band == 3,
                                f'HIGH_P_{side}': band == 3 and pp,
                                f'HIGH_PM_{side}': band == 3 and pp and mm}
                    expected.update({f'p1_anchor_favorable_{side}': z[s] > 0,
                                     f'p2_has_adverse_{side}': u is not None,
                                     f'p3_actual_pullback_{side}': u is not None and d*c[u] < max(d*c[s:u]),
                                     f'p4_no_favorable_after_u_{side}': u is not None and not any(z[k] > 0 for k in range(u+1, j)),
                                     f'p4_prev_adverse_{side}': z[j-1] < 0,
                                     f'p5_net_pullback_{side}': d*(c[j-1]-c[s]) < 0,
                                     f'pullback_index_{side}': int(ix[u]) if u is not None else -1,
                                     'anchor_index': int(ix[s])})
                    for col, value in expected.items():
                        if row[col] != value:
                            errors.append(f'{symbol}:{j}:{col}')
                    if u is not None:
                        if row[f'pullback_time_{side}'] != f.ts.iloc[ix[u]]:
                            errors.append(f'{symbol}:{j}:u timestamp')
                        if row[f'prior_extreme_at_u_{side}'] != d*max(d*c[s:u]):
                            errors.append(f'{symbol}:{j}:causal extreme')
                    checked_states += 1
                for horizon in (1, 5, 10, 20, 40):
                    valid = j + horizon < n
                    if bool(row[f'valid{horizon}']) != valid:
                        errors.append(f'{symbol}:{j}:valid{horizon}')
                    expected_end = f.ts.iloc[row_i] + (horizon+1)*pd.Timedelta(days=1)
                    segment_end = segment.ts.iloc[-1] + pd.Timedelta(days=1)
                    interrupted = segment_end < expected_end and segment_end < cutoff
                    immature = not interrupted and expected_end > cutoff
                    censored = not valid and not immature
                    status = 'COMPLETE_CONTIGUOUS' if valid else 'ADMINISTRATIVE_UNMATURED' if immature else 'CENSORED_GAP_OR_IDENTITY_BOUNDARY'
                    for col, value in {f'known_interruption{horizon}': interrupted,
                                       f'administrative_unmatured{horizon}': immature,
                                       f'censored{horizon}': censored,
                                       f'label{horizon}_status': status}.items():
                        if row[col] != value:
                            errors.append(f'{symbol}:{j}:{col}')
                    if not valid and not pd.isna(row[f'q{horizon}']):
                        errors.append(f'{symbol}:{j}:invalid label not missing')
                    if valid:
                        q = (c[j+horizon] - o[j+1]) / a
                        maximum['Q'] = max(maximum['Q'], abs(row[f'q{horizon}'] - q))
                        if not np.isclose(row[f'q{horizon}'], q, rtol=1e-10, atol=1e-10):
                            errors.append(f'{symbol}:{j}:q{horizon}')
                        if not np.isclose(row[f'ret{horizon}'], c[j+horizon]/o[j+1]-1,
                                          rtol=1e-10, atol=1e-10):
                            errors.append(f'{symbol}:{j}:ret{horizon}')
                        checked_labels += 1
                        if horizon == 20:
                            late = (c[j+20] - c[j+5]) / a
                            if not np.isclose(row.l20, late, rtol=1e-10, atol=1e-10):
                                errors.append(f'{symbol}:{j}:late')
                            if row.exit_close20 != c[j+20]:
                                errors.append(f'{symbol}:{j}:exit close20')
                            extremes = {'mfe20_long': (max(h[j+1:j+21])-o[j+1])/a,
                                        'mae20_long': (o[j+1]-min(low[j+1:j+21]))/a,
                                        'mfe20_short': (o[j+1]-min(low[j+1:j+21]))/a,
                                        'mae20_short': (max(h[j+1:j+21])-o[j+1])/a,
                                        'peak20_long_day': int(np.argmax(h[j+1:j+21]))+1,
                                        'peak20_short_day': int(np.argmin(low[j+1:j+21]))+1}
                            for col, value in extremes.items():
                                if not np.isclose(row[col], value, rtol=1e-10, atol=1e-10):
                                    errors.append(f'{symbol}:{j}:{col}')
                            for side, d in (('long', 1), ('short', -1)):
                                if not np.isclose(row[f'giveback20_{side}'], extremes[f'mfe20_{side}']-d*q,
                                                  rtol=1e-10, atol=1e-10):
                                    errors.append(f'{symbol}:{j}:giveback {side}')
                if len(errors) > 100:
                    break
            if len(errors) > 100:
                break
        # 截断的是未来帧，过去状态列应逐字不变；不比较截尾标签状态。
        if number % 50 == 1 and len(f) > 100:
            end = len(f) - 23
            prefix = f.iloc[:end].copy()
            q = build_panel(prefix, prefix.ts.iloc[-1] + pd.Timedelta(days=1))
            cols = ['feature_valid', *GROUPS, 'strength_bin_LONG', 'strength_bin_SHORT',
                    'P_LONG', 'P_SHORT', 'M_LONG', 'M_SHORT']
            for col in cols:
                if not np.array_equal(q[col].to_numpy(), p[col].iloc[:end].to_numpy()):
                    errors.append(f'{symbol}:prefix:{col}')
            prefix_rows += len(q)
        if number % 50 == 0:
            print(f'INDEPENDENT {number} symbols, {checked_states} states, {len(errors)} errors', flush=True)
        if len(errors) > 100:
            break
    verify_lock()
    if checked_rows != len(panel):
        errors.append('input/panel total row coverage differs')
    result = {'status': 'PASS' if not errors else 'RECONSTRUCTION_FAILED',
              'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'source_rows': checked_rows, 'direction_states': checked_states,
              'direct_labels': checked_labels, 'prefix_rows': prefix_rows,
              'maximum_absolute_differences': maximum, 'errors': errors,
              'seconds': time.time() - started, 'script_sha256': sha(__file__),
              'independent_reference': 'separate explicit windows, first-adverse search and price formulas',
              **panel_id, 'computation_lock_sha256': identity['computation_lock_sha256']}
    save_json(out, result)
    print(result, flush=True)
    if errors:
        raise ValueError('Independent reconstruction failed; evidence retained')


if __name__ == '__main__':
    main()
