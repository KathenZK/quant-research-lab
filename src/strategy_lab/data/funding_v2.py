"""显式资金事件裁决与证据窗口读取；不改写旧 v1 入口。"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory, sha256_file
from strategy_lab.data.windows import require_aware_utc

DATASET_ID='binance.perp.funding.v3_inputs.v2'
KNOWN_TYPES={'Regular','Special'}


def adjudicate_event_hour(observed: pd.DataFrame, authority: pd.DataFrame | None):
    """仅按有完整小时覆盖的原生证据匹配；相近时间本身不足以去重。

    调用方须先核验 authority 原文、范围与完整性。返回事件、逐行映射、裁决状态。
    """
    out=observed.copy()
    if out.empty:
        raise ValueError('empty event group')
    out['ts']=pd.to_datetime(out.ts,utc=True)
    if out.symbol.nunique()!=1 or out.ts.dt.floor('h').nunique()!=1:
        raise ValueError('adjudication must contain one symbol/hour')
    if not np.isfinite(out.funding_rate).all():
        raise ValueError('nonfinite funding')
    if authority is not None and not authority.empty:
        auth=authority.copy()
        auth['ts']=pd.to_datetime(auth.ts,utc=True)
        if (auth.symbol.nunique()!=1 or auth.symbol.iloc[0]!=out.symbol.iloc[0]
            or not auth.ts.dt.floor('h').eq(out.ts.iloc[0].floor('h')).all()
            or auth.duplicated(['ts','rate_type']).any()
            or not np.isfinite(auth.funding_rate).all()):
            raise ValueError('invalid authority group')
        mapped=[]
        for r in out.to_dict('records'):
            hit=auth[(auth.funding_rate-r['funding_rate']).abs().le(1e-12)
                &(auth.ts-r['ts']).abs().le(pd.Timedelta(seconds=2))]
            if r['rate_type'] in KNOWN_TYPES:
                hit=hit[hit.rate_type.eq(r['rate_type'])|~hit.rate_type.isin(KNOWN_TYPES)]
            exact=hit[hit.ts.eq(r['ts'])]
            if len(exact)==1:
                hit=exact
            if len(hit)!=1:
                mapped=[]
                break
            a=hit.iloc[0]
            mapped.append({'symbol':r['symbol'],'old_ts':r['ts'],'old_type':r['rate_type'],
                'canonical_ts':a.ts,'canonical_type':a.rate_type,'funding_rate':r['funding_rate'],
                'authority_sha256':a['raw_receipt_sha256'],
                'changed_key':r['ts']!=a.ts or r['rate_type']!=a.rate_type})
        if len(mapped)==len(out):
            # Never collapse explicitly distinct economic event types into one
            # untyped archive row, even when their rates happen to be identical.
            identities={}
            for r in mapped:
                if r['old_type'] in KNOWN_TYPES:
                    identities.setdefault((r['canonical_ts'],r['canonical_type']),set()).add(r['old_type'])
            if any(len(v)>1 for v in identities.values()):
                out['event_unambiguous']=False
                return out,[],'UNRESOLVED_EXPLICIT_EVENT_TYPES'
            for idx,r in auth.iterrows():
                known=identities.get((r.ts,r.rate_type),set())
                if r.rate_type not in KNOWN_TYPES and len(known)==1:
                    auth.loc[idx,'rate_type']=next(iter(known))
            for r in mapped:
                match=auth[auth.ts.eq(r['canonical_ts'])]
                if len(match)==1:
                    r['canonical_type']=match.rate_type.iloc[0]
                    r['changed_key']=r['old_ts']!=r['canonical_ts'] or r['old_type']!=r['canonical_type']
            # The native source may itself list multiple economic events.
            clear=len(auth)==1 or (len(auth)==2 and set(auth.rate_type)==KNOWN_TYPES)
            auth['event_unambiguous']=clear
            return auth,mapped,('NATIVE_AUTHORITY_MATCH' if clear else 'NATIVE_MULTI_EVENT_UNTYPED')
    unique=out.drop_duplicates(['ts','rate_type','funding_rate'])
    clear=len(unique)==1 or (len(unique)==2 and set(unique.rate_type)==KNOWN_TYPES)
    unique=unique.copy()
    unique['event_unambiguous']=clear
    return unique,[],('OBSERVED_SINGLE_OR_TYPED_PAIR' if clear else 'UNRESOLVED_SOURCE_MAPPING')


def archive_interval_segments(events: pd.DataFrame):
    """用原生月档频率字段验证相邻区间；不外推首尾或频率切换。

    输入应包括所有已裁决事件；多事件小时、缺证据行均中断连续覆盖。
    快照 COIN 分类只用于本轮范围路由，消费还须独立资产身份确认。
    """
    f=events.copy().sort_values(['symbol','ts']).reset_index(drop=True)
    f['ts']=pd.to_datetime(f.ts,utc=True)
    if f.duplicated(['symbol','event_id']).any():
        raise ValueError('duplicate funding event identity')
    n=f.groupby([f.symbol,f.ts.dt.floor('h')]).ts.transform('size')
    interval=pd.to_numeric(f.archive_interval_hours,errors='coerce')
    valid=(f.event_unambiguous & f.asset_class.eq('COIN') & n.eq(1)
        & interval.isin([1.,2.,4.,8.]) & f.archive_evidence_sha256.fillna('').str.len().eq(64)
        & f.rate_type.ne('Special'))
    prev_ts=f.groupby('symbol',sort=False).ts.shift()
    prev_interval=interval.groupby(f.symbol,sort=False).shift()
    prev_valid=valid.groupby(f.symbol,sort=False).shift(fill_value=False)
    nominal=interval*3600
    observed=(f.ts-prev_ts).dt.total_seconds()
    link=valid & prev_valid & interval.eq(prev_interval) & (observed-nominal).abs().le(2)
    # Each unproved interval is a boundary, even if its endpoint values look normal.
    f['_segment']=(~link).groupby(f.symbol,sort=False).cumsum()
    segments=[]
    expected=[]
    for (symbol,group),g in f.groupby(['symbol','_segment'],sort=False):
        indices=g.index
        proven=link.loc[indices]
        if not proven.any():
            continue
        linked=g.loc[proven]
        a=prev_ts.loc[linked.index[0]]
        b=linked.ts.iloc[-1]
        key=f'{symbol}|{int(group)}'
        segments.append({'symbol':symbol,'segment_id':key,'start':a,'end':b,
            'proof':'NATIVE_ARCHIVE_INTERVAL_AND_EVENT_MATCH','expected_events':len(linked)})
        for r in linked.to_dict('records'):
            expected.append({'symbol':symbol,'segment_id':key,'ts':r['ts'],'event_id':r['event_id'],
                'funding_rate':r['funding_rate'],'rate_type':r['rate_type'],
                'evidence_sha256':r['archive_evidence_sha256']})
    return (pd.DataFrame(segments,columns=['symbol','segment_id','start','end','proof','expected_events']),
            pd.DataFrame(expected,columns=['symbol','segment_id','ts','event_id','funding_rate','rate_type','evidence_sha256']))


@dataclass(frozen=True)
class VerifiedFundingV2:
    events: pd.DataFrame
    segments: pd.DataFrame
    expected: pd.DataFrame
    manifest: dict


def load_funding_v2(root: Path, *, expected_manifest_sha256: str) -> VerifiedFundingV2:
    """显式固定 manifest；验证事件、历史频率证据和覆盖文件的全部内容哈希。"""
    if sha256_file(root/'_MANIFEST.json')!=expected_manifest_sha256:
        raise ValueError('funding manifest identity mismatch')
    m=json.loads((root/'_MANIFEST.json').read_text())
    if m.get('dataset_id')!=DATASET_ID or m.get('row_quality')!='PASS':
        raise ValueError('unaccepted funding v2')
    if inventory_fingerprint(parquet_inventory(root))!=m['parquet_inventory_fingerprint']:
        raise ValueError('funding files changed')
    import duckdb
    c=duckdb.connect()
    c.execute("SET TimeZone='UTC'")
    try:
        e=c.read_parquet([str(p) for p in sorted((root/'events').rglob('*.parquet'))],hive_partitioning=False).df()
        e['ts']=pd.to_datetime(e.ts,utc=True)
        s=pd.read_parquet(root/'coverage/segments.parquet')
        x=pd.read_parquet(root/'coverage/expected_events.parquet')
    finally:
        c.close()
    if (len(e)!=m['rows'] or e.event_id.duplicated().any()
        or not np.isfinite(e.funding_rate).all() or e.ts.isna().any()
        or not isinstance(e.ts.dtype,pd.DatetimeTZDtype)
        or not pd.api.types.is_bool_dtype(e.event_unambiguous.dtype)
        or e.event_unambiguous.isna().any()):
        raise ValueError('funding event validation failed')
    if s.segment_id.duplicated().any() or x.event_id.duplicated().any():
        raise ValueError('funding coverage identity duplicate')
    if len(s)!=m['verified_segments'] or len(x)!=m['verified_expected_events']:
        raise ValueError('funding coverage count mismatch')
    return VerifiedFundingV2(e,s,x,m)


def require_funding_v2_window(data: VerifiedFundingV2, *, symbol: str, start: str, end: str,
                              identity_evidence: str) -> pd.DataFrame:
    """净收益窗口 (start,end]；无证据、跨缺段或未识别事件拒绝，不自动填零。"""
    a=require_aware_utc(start,field='funding start')
    b=require_aware_utc(end,field='funding end')
    if a>=b or not identity_evidence.strip():
        raise ValueError('funding net window needs range and independently verified asset identity')
    if b>require_aware_utc(data.manifest['cutoff_utc'],field='cutoff'):
        raise ValueError('funding window exceeds frozen cutoff')
    s=data.segments
    hit=s[s.symbol.eq(symbol)&s.start.le(a)&s.end.ge(b)]
    if len(hit)!=1:
        raise ValueError('historical funding coverage not proven for this full window')
    e=data.events
    actual=e[e.symbol.eq(symbol)&e.ts.gt(a)&e.ts.le(b)].copy()
    x=data.expected
    expected=x[x.segment_id.eq(hit.segment_id.iloc[0])&x.ts.gt(a)&x.ts.le(b)]
    if (not actual.event_unambiguous.all() or actual.event_id.duplicated().any()
        or set(actual.event_id)!=set(expected.event_id)):
        raise ValueError('missing, extra or ambiguous funding event; net invalid')
    joined=actual.merge(expected,on='event_id',suffixes=('_actual','_expected'),validate='one_to_one')
    if (not joined.ts_actual.eq(joined.ts_expected).all()
        or not joined.rate_type_actual.eq(joined.rate_type_expected).all()
        or not np.allclose(joined.funding_rate_actual,joined.funding_rate_expected,atol=1e-12,rtol=0)):
        raise ValueError('funding values differ from frozen evidence')
    actual.attrs['identity_evidence']=identity_evidence
    actual.attrs['coverage_segment_id']=hit.segment_id.iloc[0]
    return actual.sort_values('ts')
