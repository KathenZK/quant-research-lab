"""MTCS固定信号和完整路径标签；只消费本家族可信返回帧，不读取数据湖。"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import pandas as pd

LAB = Path('/Users/ZK/OpenCode/quant-strategy-lab')
sys.path.insert(0, str(LAB / 'src'))
from strategy_lab.data.research_inputs import complete_window_mask

GROUPS = ('U_LONG','U_SHORT','M_LONG','M_SHORT','S1_LONG','S1_SHORT',
          'S2_LONG','S2_SHORT','S3_LONG','S3_SHORT')
DAY = pd.Timedelta(days=1)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_verified_frames(input_dir: Path):
    """内部证据回放：同时验证API收据、序列化帧和内容，不重新扫湖。"""
    summary = json.loads((input_dir/'summary.json').read_text())
    if not summary.get('source_pins_unchanged') or summary.get('changed_family_files'):
        raise ValueError('input source/contract changed during trusted loading')
    manifest_path = input_dir/'frame-manifest.json'
    if sha(manifest_path) != summary['frame_manifest_sha256']:
        raise ValueError('input frame manifest changed')
    manifest = json.loads(manifest_path.read_text())
    for symbol, entry in sorted(manifest.items()):
        path = (input_dir/entry['path']).resolve()
        if not path.is_relative_to(input_dir.resolve()) or sha(path) != entry['sha256']:
            raise ValueError(f'{symbol}: saved frame changed or escaped')
        for key in ('request','startup_report'):
            proof = input_dir/entry[f'{key}_path']
            if sha(proof) != entry[f'{key}_sha256']:
                raise ValueError(f'{symbol}: {key} receipt changed')
        request = json.loads((input_dir/entry['request_path']).read_text())
        receipt = json.loads((input_dir/entry['startup_report_path']).read_text())
        if receipt['request'] != request or receipt['status'] != 'PRICE_DIAGNOSTIC_INPUTS_VERIFIED':
            raise ValueError(f'{symbol}: receipt/request mismatch')
        if request['backward_bars'] != 60 or request['forward_bars'] != 0:
            raise ValueError(f'{symbol}: not a past-only 60-bar verified input')
        frame = pd.read_pickle(path, compression='gzip')
        digest = hashlib.sha256(pd.util.hash_pandas_object(frame,index=True).values.tobytes()).hexdigest()
        if digest != entry['dataframe_hash'] or not frame.symbol.eq(symbol).all():
            raise ValueError(f'{symbol}: dataframe identity/content mismatch')
        yield symbol, frame


def wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int=14):
    tr = np.maximum(high-low, np.maximum(np.abs(high-np.r_[close[0],close[:-1]]),
                                        np.abs(low-np.r_[close[0],close[:-1]])))
    atr = np.full(len(close),np.nan)
    if len(close) >= period:
        atr[period-1] = tr[:period].mean()
        for i in range(period,len(close)):
            atr[i] = ((period-1)*atr[i-1]+tr[i])/period
    return atr


def build_panel(frame: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """一行=一次日线观察；信号不依赖未来mask，标签不跨连续段。"""
    if frame.empty or frame.symbol.nunique()!=1:
        raise ValueError('single nonempty symbol required')
    f = frame.reset_index(drop=True).copy()
    if not f.ts.is_monotonic_increasing or f.ts.duplicated().any():
        raise ValueError('unordered or duplicate timestamps')
    if f.ts.dt.tz is None or cutoff.tz is None or (f.ts+DAY>cutoff).any():
        raise ValueError('timezone/closed-bar boundary invalid')
    official_past = complete_window_mask(f,backward=60,forward=0).to_numpy(bool)
    if not np.array_equal(official_past,f.research_window_valid.to_numpy(bool)):
        raise ValueError('past mask differs from verified API frame')
    p = f[['symbol','ts','open','high','low','close','volume','research_segment_id','eligible']].copy()
    p['signal_time'] = p.ts+DAY
    p['atr14'] = np.nan
    p['sma7'] = np.nan
    p['prior20_delta'] = np.nan
    p['prior5_delta'] = np.nan
    p['momentum20_delta'] = np.nan
    for group in GROUPS:
        p[group] = False
    for h in (1,5,10,20,40):
        p[f'valid{h}'] = complete_window_mask(f,backward=60,forward=h).to_numpy(bool)
        p[f'q{h}'] = np.nan
        p[f'ret{h}'] = np.nan
    p['entry_open'] = np.nan
    p['exit_close20'] = np.nan
    for col in ('mfe20_long','mae20_long','mfe20_short','mae20_short',
                'peak20_long_day','peak20_short_day'):
        p[col] = np.nan
    for _,g in f.loc[f.eligible].groupby('research_segment_id',sort=False):
        idx = g.index.to_numpy()
        if (g.ts.diff().dropna()!=DAY).any() or not np.all(np.diff(idx)==1):
            raise ValueError('eligible segment not contiguous')
        c,h,l,o = (g[col].to_numpy(float) for col in ('close','high','low','open'))
        n = len(g)
        atr = wilder_atr(h,l,c)
        ma = np.full(n,np.nan)
        if n>=7:
            ma[6:] = np.lib.stride_tricks.sliding_window_view(c,7).mean(axis=1)
        mom = np.full(n,np.nan); pre20=mom.copy(); pre5=mom.copy()
        if n>20:
            mom[20:] = c[20:]-c[:-20]
        if n>21:
            pre20[21:] = c[20:-1]-c[:-21]
        if n>6:
            pre5[6:] = c[5:-1]-c[:-6]
        p.loc[idx,['atr14','sma7','prior20_delta','prior5_delta','momentum20_delta']] = np.column_stack((atr,ma,pre20,pre5,mom))
        delta = c-ma
        previous = np.r_[np.nan,delta[:-1]]
        past = official_past[idx] & np.isfinite(atr) & (atr>0)
        for side,d in (('LONG',1),('SHORT',-1)):
            u = past & (d*mom>0)
            m = past & (d*delta>0) & (d*previous<0)
            p.loc[idx,f'U_{side}'] = u
            p.loc[idx,f'M_{side}'] = m
            p.loc[idx,f'S1_{side}'] = m & (d*pre20>0) & (d*pre5>0)
            p.loc[idx,f'S2_{side}'] = m & (d*pre20<=0)
            p.loc[idx,f'S3_{side}'] = m & (d*pre20>0) & (d*pre5<=0)
        if n>1:
            p.loc[idx[:-1],'entry_open'] = o[1:]
        for horizon in (1,5,10,20,40):
            if n<=horizon:
                continue
            positions = idx[:-horizon]
            mask = p.loc[positions,f'valid{horizon}'].to_numpy(bool) & past[:-horizon]
            accepted = positions[mask]
            entry = o[1:n-horizon+1][mask]
            exit_price = c[horizon:][mask]
            p.loc[accepted,f'q{horizon}'] = (exit_price-entry)/atr[:-horizon][mask]
            p.loc[accepted,f'ret{horizon}'] = exit_price/entry-1
            if horizon==20:
                p.loc[accepted,'exit_close20'] = exit_price
                highs = np.lib.stride_tricks.sliding_window_view(h[1:],20)[mask]
                lows = np.lib.stride_tricks.sliding_window_view(l[1:],20)[mask]
                max_price,min_price = highs.max(axis=1),lows.min(axis=1)
                a = atr[:-horizon][mask]
                p.loc[accepted,'mfe20_long'] = (max_price-entry)/a
                p.loc[accepted,'mae20_long'] = (entry-min_price)/a
                p.loc[accepted,'mfe20_short'] = (entry-min_price)/a
                p.loc[accepted,'mae20_short'] = (max_price-entry)/a
                p.loc[accepted,'peak20_long_day'] = highs.argmax(axis=1)+1
                p.loc[accepted,'peak20_short_day'] = lows.argmin(axis=1)+1
    p['feature_valid'] = official_past & p.atr14.gt(0) & np.isfinite(p.atr14)
    for h in (1,5,10,20,40):
        expected = p[f'valid{h}'] & p.feature_valid
        if (~np.isfinite(p.loc[expected,f'q{h}'])).any():
            raise ValueError(f'nonfinite label in a complete valid {h}-day window')
        p[f'valid{h}'] &= p.feature_valid & np.isfinite(p[f'q{h}'])
    p['l20'] = p.q20-p.q5
    # Evaluation-only interruption evidence takes precedence over administrative
    # immaturity. None of these future masks changes the past-only signals.
    last_segment_close = f.groupby('research_segment_id',sort=False).ts.transform('max')+DAY
    p['known_interruption20'] = p.feature_valid & (last_segment_close<p.signal_time+20*DAY) & (last_segment_close<cutoff)
    p['administrative_unmatured20'] = p.feature_valid & ~p.known_interruption20 & (p.signal_time+20*DAY>cutoff)
    p['censored20'] = p.feature_valid & ~p.valid20 & ~p.administrative_unmatured20
    p['label20_status'] = np.select(
        [~p.feature_valid,p.valid20,p.administrative_unmatured20],
        ['PAST_INELIGIBLE','COMPLETE_CONTIGUOUS','ADMINISTRATIVE_UNMATURED'],
        default='CENSORED_GAP_OR_IDENTITY_BOUNDARY')
    for side in ('LONG','SHORT'):
        counts = p[[f'S1_{side}',f'S2_{side}',f'S3_{side}']].sum(axis=1)
        if not counts.eq(p[f'M_{side}'].astype(int)).all():
            raise ValueError('MA7 state partition failed')
    if p.loc[~p.feature_valid,list(GROUPS)].to_numpy().any():
        raise ValueError('signal escaped past eligibility')
    return p


def event_probe(panel: pd.DataFrame, group: str, slippage: float=.0004, fee: float=.001):
    """每事件固定入场名义额的成本探针，不把重叠事件当账户。"""
    if group not in GROUPS:
        raise ValueError('unknown fixed group')
    d = 1 if group.endswith('LONG') else -1
    rows = panel.loc[panel[group] & panel.valid20].copy()
    a = rows.entry_open*(1+d*slippage)
    b = rows.exit_close20*(1-d*slippage)
    rows['direction'] = d
    rows['gross_return'] = d*rows.ret20
    rows['return_after_fee_slippage'] = d*(b-a)/a-fee*(1+b/a)
    rows['fees_fraction_entry_notional'] = fee*(1+b/a)
    rows['funding_verified'] = False
    rows['group'] = group
    return rows
