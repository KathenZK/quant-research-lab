"""固定 V3 研究输入与保守有效性规则；不替换任何旧数据集默认值。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence
import json

import numpy as np
import pandas as pd

from strategy_lab.data.catalog import (
    DatasetScope, load_trusted_research_dataset, require_passing_trusted,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory
from strategy_lab.data.windows import require_aware_utc

V3_PRICE_IDS = {
    '15m': 'binance.perp.ohlcv.15m.history.v3',
    '1h': 'binance.perp.ohlcv.1h.from_15m.v2',
    '4h': 'binance.perp.ohlcv.4h.from_15m.v2',
    '1d': 'binance.perp.ohlcv.1d.from_15m.v2',
}
STEP = {'15m': pd.Timedelta(minutes=15), '1h': pd.Timedelta(hours=1),
        '4h': pd.Timedelta(hours=4), '1d': pd.Timedelta(days=1)}
V3_CUTOFF = pd.Timestamp('2026-09-05T15:45:00Z')


@dataclass(frozen=True)
class IdentityWindow:
    """调用方有独立证据的身份有效期；不能从当前活跃状态回填。"""
    symbol: str
    start: str
    end: str
    evidence: str


def segment_research_bars(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    identity_windows: Sequence[IdentityWindow] = (),
    identity_policy: Literal['require_verified', 'observed_diagnostic'] = 'require_verified',
) -> pd.DataFrame:
    """先拒绝乱序/重复，再分段；零成交也中断特征和标签链。

    observed_valid 只表示已观测价格/成交记录有效，不是订单可成交证明。
    默认 eligibility 还要求完整 bar 落入显式身份有效期。
    """
    if timeframe not in STEP or identity_policy not in ('require_verified', 'observed_diagnostic'):
        raise ValueError('unknown timeframe or identity policy')
    out = frame.copy().reset_index(drop=True)
    required = {'symbol', 'ts', 'timeframe', 'is_closed', 'volume', 'quote_volume',
                'trade_count', 'open', 'high', 'low', 'close'}
    if required-set(out):
        raise ValueError(f'missing columns {required-set(out)}')
    if out.symbol.isna().any() or out.ts.isna().any():
        raise ValueError('null symbol/timestamp')
    # Explicitly reject naive inputs: pd.to_datetime(..., utc=True) alone would guess.
    for value in out.ts:
        require_aware_utc(value, field='ts')
    out['ts'] = pd.to_datetime(out.ts, utc=True)
    if not out.timeframe.eq(timeframe).all():
        raise ValueError('mixed timeframe')
    step = STEP[timeframe]
    if (out.ts.dt.as_unit('ns').astype('int64') % step.value != 0).any():
        raise ValueError('off-grid timestamps')
    if out.duplicated(['symbol', 'ts']).any():
        raise ValueError('duplicate business keys')
    delta = out.groupby('symbol', sort=False).ts.diff()
    if (delta.dropna() <= pd.Timedelta(0)).any():
        raise ValueError('nonmonotonic input; do not sort away a data error')
    if not pd.api.types.is_bool_dtype(out.is_closed.dtype):
        raise ValueError('closure must be explicit boolean')
    cols = ['open','high','low','close','volume','quote_volume','trade_count']
    numbers = out[cols].to_numpy(dtype=float)
    finite = np.isfinite(numbers).all(axis=1)
    legal = (out[['open','high','low','close']]>0).all(axis=1)
    legal &= out.high.ge(out[['open','close','low']].max(axis=1))
    legal &= out.low.le(out[['open','close','high']].min(axis=1))
    out['observed_valid'] = finite & legal & out.is_closed.fillna(False) & out.volume.gt(0) & out.quote_volume.gt(0) & out.trade_count.gt(0)
    out['identity_verified'] = False
    identity_tags = pd.Series('', index=out.index, dtype='string')
    windows = []
    for i,w in enumerate(identity_windows):
        start = require_aware_utc(w.start,field='identity start')
        end = require_aware_utc(w.end,field='identity end')
        if start >= end or not w.evidence.strip():
            raise ValueError('identity window needs range and evidence')
        if any(s==w.symbol and start < b and end > a for s,a,b in windows):
            raise ValueError('overlapping identity windows')
        windows.append((w.symbol,start,end))
        mask = out.symbol.eq(w.symbol) & out.ts.ge(start) & (out.ts+step).le(end)
        out.loc[mask,'identity_verified'] = True
        identity_tags.loc[mask] = f'identity#{i}'
    out['eligible'] = out.observed_valid & (out.identity_verified if identity_policy=='require_verified' else True)
    prev_valid = out.groupby('symbol',sort=False).eligible.shift(fill_value=False)
    prev_tag = identity_tags.groupby(out.symbol,sort=False).shift(fill_value='')
    resets = delta.ne(step) | ~out.eligible | ~prev_valid | identity_tags.ne(prev_tag)
    ids = resets.groupby(out.symbol,sort=False).cumsum().astype('int64')
    out['research_segment_id'] = (out.symbol.astype('string')+'#'+ids.astype('string')).where(out.eligible)
    out.attrs.update(frame.attrs)
    out.attrs['identity_policy'] = identity_policy
    out.attrs['pit_universe_proven'] = False
    out.attrs['tradability_proven'] = False
    return out


def complete_window_mask(frame: pd.DataFrame, *, backward: int = 1, forward: int = 0) -> pd.Series:
    """整个特征回看和标签未来必须在同一有效段；包含当前 bar。"""
    if backward<1 or forward<0:
        raise ValueError('invalid window size')
    if 'research_segment_id' not in frame or 'eligible' not in frame:
        raise ValueError('must segment before computing windows')
    group = frame.groupby('research_segment_id',sort=False)
    prior = group.cumcount()+1
    following = group.cumcount(ascending=False)
    return frame.eligible & prior.ge(backward) & following.ge(forward)


def load_v3_research_ohlcv(
    *, layout: DataLakeLayout, timeframe: str, symbol: str,
    start: str, end: str,
    identity_windows: Sequence[IdentityWindow] = (),
    identity_policy: Literal['require_verified','observed_diagnostic'] = 'require_verified',
) -> pd.DataFrame:
    """固定版本单标的入口；拒绝超范围而不静默回退旧缓存。"""
    if timeframe not in V3_PRICE_IDS:
        raise ValueError('unsupported timeframe')
    a,b = require_aware_utc(start,field='start'),require_aware_utc(end,field='end')
    step=STEP[timeframe]
    if a>=b or a.value%step.value or b.value%step.value:
        raise ValueError('window must be ordered and aligned to timeframe')
    last_close=pd.Timestamp((V3_CUTOFF.value//step.value)*step.value,tz='UTC')
    if b>last_close:
        raise ValueError('requested window exceeds V3 frozen complete bars')
    loaded=require_passing_trusted(load_trusted_research_dataset(
        V3_PRICE_IDS[timeframe],layout=layout,requested_scope=DatasetScope.SINGLE_SYMBOL,
        symbol=symbol,start=a,end=b,gap_policy='contiguous_segments'))
    if not loaded.materialized:
        raise ValueError('requested frame exceeds materialization limit; use verified-file batch API')
    result=segment_research_bars(loaded.frame,timeframe,identity_windows=identity_windows,identity_policy=identity_policy)
    result.attrs['dataset_id']=loaded.record.dataset_id
    result.attrs['verified_identity']=loaded.verified_identity
    return result


def load_verified_funding_snapshot(root: Path) -> pd.DataFrame:
    """资金事件读取不承诺时间覆盖；净收益必须另外走完整日历门禁。"""
    manifest=json.loads((root/'_MANIFEST.json').read_text())
    if manifest.get('dataset_id')!='binance.perp.funding.v3_inputs.v1' or manifest.get('row_quality')!='PASS':
        raise ValueError('unaccepted funding snapshot')
    actual=inventory_fingerprint(parquet_inventory(root))
    if actual!=manifest.get('parquet_inventory_fingerprint'):
        raise ValueError('funding fingerprint mismatch')
    import duckdb
    c=duckdb.connect()
    try:
        f=c.read_parquet([str(p) for p in sorted(root.rglob('*.parquet'))],hive_partitioning=False).df()
    finally:
        c.close()
    if f.duplicated(['symbol','ts']).any() or not np.isfinite(f.funding_rate).all() or len(f)!=manifest['rows']:
        raise ValueError('funding row audit failed')
    f.attrs['funding_manifest']=manifest
    return f


def require_funding_window(
    events: pd.DataFrame, *, symbol: str, start: str, end: str,
    expected_event_times: Sequence[str] | None, calendar_evidence: str,
) -> pd.DataFrame:
    """净收益用 (start,end] 结算事件；没有独立期望日历绝不自动填 0。

    expected_event_times 必须来自冻结的历史结算证据，而不是由 events 自身推导。
    本函数只能验证传入证据对应的时间集合；不替调用方认证证据真伪。
    """
    a,b=require_aware_utc(start,field='funding start'),require_aware_utc(end,field='funding end')
    if a>=b or expected_event_times is None or not calendar_evidence.strip():
        raise ValueError('net funding requires explicit historical calendar evidence')
    expected=pd.DatetimeIndex([require_aware_utc(t,field='expected funding time') for t in expected_event_times],tz='UTC')
    if expected.has_duplicates or any((expected<=a)|(expected>b)):
        raise ValueError('invalid expected settlement timestamps')
    if events.ts.isna().any() or events.symbol.isna().any():
        raise ValueError('null funding timestamp/symbol')
    if not isinstance(events.ts.dtype,pd.DatetimeTZDtype):
        for value in events.ts:
            require_aware_utc(value,field='funding event time')
    ts=pd.to_datetime(events.ts,utc=True)
    out=events.loc[events.symbol.eq(symbol)&ts.gt(a)&ts.le(b)].copy()
    actual=pd.DatetimeIndex(pd.to_datetime(out.ts,utc=True))
    if ('event_unambiguous' not in out or not pd.api.types.is_bool_dtype(out.event_unambiguous.dtype)
            or out.event_unambiguous.isna().any()):
        raise ValueError('funding ambiguity flag must be explicit boolean')
    manifest=events.attrs.get('funding_manifest',{})
    if manifest.get('cutoff_exclusive_utc') and b>require_aware_utc(manifest['cutoff_exclusive_utc'],field='funding cutoff'):
        raise ValueError('funding request exceeds frozen snapshot cutoff')
    if actual.has_duplicates or set(actual)!=set(expected) or not out.event_unambiguous.all():
        raise ValueError('missing, unexpected, or ambiguous funding settlement; net invalid')
    if not np.isfinite(out.funding_rate).all():
        raise ValueError('nonfinite funding rate')
    return out.sort_values('ts')
