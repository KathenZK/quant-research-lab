import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from strategy_lab.data.funding_v2 import (
    DATASET_ID, VerifiedFundingV2, adjudicate_event_hour, archive_interval_segments, load_funding_v2, require_funding_v2_window,
)
from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory, sha256_file


def events(offsets=(0,2),rates=(.0001,.0001),types=('Unspecified','Regular')):
    return pd.DataFrame([{'symbol':'BTC/USDT:USDT','ts':pd.Timestamp('2026-08-01T00:00:00Z')+pd.Timedelta(milliseconds=o),
        'funding_rate':r,'rate_type':t,'raw_receipt_sha256':'a'*64,'event_unambiguous':False}
        for o,r,t in zip(offsets,rates,types)])


def test_close_equal_without_native_authority_remains_ambiguous():
    f,m,status=adjudicate_event_hour(events(),None)
    assert len(f)==2 and not f.event_unambiguous.any() and not m


def test_native_evidence_resolves_alias_but_retains_millisecond():
    raw=events()
    f,m,status=adjudicate_event_hour(raw,raw.iloc[[1]])
    assert len(f)==1 and f.event_unambiguous.all() and len(m)==2
    assert f.ts.iloc[0].microsecond==2000


def test_native_two_events_are_not_merged():
    raw=events((0,1000),(.0001,.002),('Regular','Special'))
    f,m,status=adjudicate_event_hour(raw,raw)
    assert len(f)==2 and f.event_unambiguous.all()


def test_explicit_special_at_exact_same_timestamp_is_retained():
    raw=events((0,0),(.0001,.002),('Regular','Special'))
    f,m,status=adjudicate_event_hour(raw,raw)
    assert len(f)==2 and f.event_unambiguous.all()


def test_equal_rate_special_is_not_collapsed_to_untyped_archive():
    raw=events((0,1000),(.0001,.0001),('Regular','Special'))
    authority=raw.iloc[[0]].copy()
    authority['rate_type']='Unspecified'
    f,m,status=adjudicate_event_hour(raw,authority)
    assert len(f)==2 and not f.event_unambiguous.any()


def test_native_untyped_double_remains_unresolved():
    raw=events((0,1000),(.0001,.002),('Unspecified','Unspecified'))
    f,m,status=adjudicate_event_hour(raw,raw)
    assert len(f)==2 and not f.event_unambiguous.any()


@pytest.mark.parametrize('offset,rates',[(3000,(.0001,.0001)),(2,(.0001,.0002))])
def test_amount_or_offset_mismatch_not_rescued(offset,rates):
    raw=events((0,offset),rates)
    f,m,status=adjudicate_event_hour(raw,raw.iloc[[1]])
    assert len(f)==2 and not f.event_unambiguous.any() and not m


def interval_data():
    ts=pd.date_range('2026-08-01T00:00:00Z',periods=5,freq='8h')
    return pd.DataFrame({'symbol':['BTC/USDT:USDT']*5,'ts':ts,'funding_rate':[.0001]*5,
        'rate_type':['Regular']*5,'event_unambiguous':[True]*5,'archive_interval_hours':[8.]*5,
        'archive_evidence_sha256':['a'*64]*5,'asset_class':['COIN']*5,'event_id':[f'e{i}' for i in range(5)]})


def test_archive_interval_window_and_net_guard():
    e=interval_data()
    s,x=archive_interval_segments(e)
    assert len(s)==1 and len(x)==4
    data=VerifiedFundingV2(e,s,x,{'cutoff_utc':'2026-09-05T15:45:00Z'})
    kw=dict(symbol='BTC/USDT:USDT',start='2026-08-01T01:00:00Z',end='2026-08-01T17:00:00Z',identity_evidence='dated instrument evidence')
    assert len(require_funding_v2_window(data,**kw))==2
    for bad in [e.drop(index=1),e.assign(event_unambiguous=False),e.assign(funding_rate=.001)]:
        with pytest.raises(ValueError):
            require_funding_v2_window(VerifiedFundingV2(bad,s,x,data.manifest),**kw)
    with pytest.raises(ValueError):
        require_funding_v2_window(data,**{**kw,'start':'2026-07-31T23:00:00Z'})
    with pytest.raises(ValueError):
        require_funding_v2_window(data,**{**kw,'identity_evidence':''})
    with pytest.raises(ValueError):
        require_funding_v2_window(data,**{**kw,'end':'2026-08-01T17:00:00'})


@pytest.mark.parametrize('bad',['missing','frequency_change','no_evidence','equity','ambiguous'])
def test_calendar_boundaries_not_bridged(bad):
    e=interval_data()
    if bad=='missing':
        e=e.drop(index=2)
    elif bad=='frequency_change':
        e.loc[2,'archive_interval_hours']=4.
    elif bad=='no_evidence':
        e.loc[2,'archive_evidence_sha256']=''
    elif bad=='equity':
        e['asset_class']='EQUITY'
    else:
        e.loc[2,'event_unambiguous']=False
    s,x=archive_interval_segments(e)
    assert len(x)<4
    assert not ((s.start<=pd.Timestamp('2026-08-01T01:00:00Z')) & (s.end>=pd.Timestamp('2026-08-02T01:00:00Z'))).any()


def fetch_module():
    path=Path(__file__).resolve().parents[1]/'research/platform/data-lake-governance/scripts/fetch_binance_funding_v2.py'
    spec=importlib.util.spec_from_file_location('funding_fetch_v2',path)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_reconciliation_pipeline_roundtrip(tmp_path,monkeypatch):
    path=Path(__file__).resolve().parents[1]/'research/platform/data-lake-governance/scripts/build_binance_funding_v2.py'
    spec=importlib.util.spec_from_file_location('funding_builder_v2',path)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m,'ART',tmp_path)
    base=events().assign(mark_price=100.,source='binance_futures_funding_rate_api')
    api=base.iloc[[1]].copy().assign(authority_kind='API',archive_interval_hours=float('nan'),receipt_path='api')
    archive=api.copy().assign(authority_kind='ARCHIVE',source='binance_vision_funding_monthly',
        rate_type='Unspecified',archive_interval_hours=8.,receipt_path='archive')
    native=pd.concat([api,archive],ignore_index=True)
    result,stats=m.reconcile(base,native,{'BTC/USDT:USDT':'COIN'})
    assert len(result)==1 and result.event_unambiguous.all()
    assert result.ts.iloc[0].microsecond==2000
    assert result.archive_interval_hours.iloc[0]==8.
    assert result.event_id.str.len().eq(64).all()
    assert stats['resolved_candidate_hours']==1
    m.value_lineage_audit(base,native,result,{'BTC/USDT:USDT':'COIN'})
    native.loc[0,'funding_rate']=.001
    with pytest.raises(ValueError,match='conflicts'):
        m.reconcile(base,native,{'BTC/USDT:USDT':'COIN'})


def test_verified_loader_rejects_changed_file_or_manifest(tmp_path):
    e=interval_data()
    s,x=archive_interval_segments(e)
    (tmp_path/'events').mkdir()
    (tmp_path/'coverage').mkdir()
    e.to_parquet(tmp_path/'events/part.parquet',index=False)
    s.to_parquet(tmp_path/'coverage/segments.parquet',index=False)
    x.to_parquet(tmp_path/'coverage/expected_events.parquet',index=False)
    m={'dataset_id':DATASET_ID,'row_quality':'PASS','rows':len(e),'verified_segments':len(s),
       'verified_expected_events':len(x),'parquet_inventory_fingerprint':inventory_fingerprint(parquet_inventory(tmp_path))}
    (tmp_path/'_MANIFEST.json').write_text(json.dumps(m))
    fingerprint=sha256_file(tmp_path/'_MANIFEST.json')
    assert len(load_funding_v2(tmp_path,expected_manifest_sha256=fingerprint).events)==5
    with pytest.raises(ValueError,match='manifest'):
        load_funding_v2(tmp_path,expected_manifest_sha256='wrong')
    e.assign(funding_rate=.009).to_parquet(tmp_path/'events/part.parquet',index=False)
    with pytest.raises(ValueError,match='files changed'):
        load_funding_v2(tmp_path,expected_manifest_sha256=fingerprint)


def test_page_validation_preserves_special_at_same_timestamp():
    m=fetch_module()
    rows=[{'symbol':'BTCUSDT','fundingTime':1000,'fundingRate':'.0001','rateType':t} for t in ['Regular','Special']]
    m.validate(rows,{'symbol':'BTC/USDT:USDT','end_ms':2000},1000)
    rows[0]['symbol']='ETHUSDT'
    with pytest.raises(ValueError):
        m.validate(rows,{'symbol':'BTC/USDT:USDT','end_ms':2000},1000)


def test_bounded_month_writer_preserves_native_times_and_types(tmp_path):
    path=Path(__file__).resolve().parents[1]/'research/platform/data-lake-governance/scripts/build_binance_funding_v2.py'
    spec=importlib.util.spec_from_file_location('funding_writer_v2',path)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    raw=events((0,0,2),(.0001,.002,.003),('Regular','Special','Regular'))
    raw.loc[2,'ts']=pd.Timestamp('2026-09-01T00:00:00.002Z')
    m.write_event_partitions(raw,tmp_path)
    files=sorted((tmp_path/'events').rglob('*.parquet'))
    assert len(files)==2
    restored=pd.concat([pd.read_parquet(p) for p in files],ignore_index=True)
    pd.testing.assert_frame_equal(restored,raw)
