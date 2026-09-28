import importlib.util
import gzip
import hashlib
import io
import json
from pathlib import Path
from urllib.error import HTTPError
import zipfile

import pandas as pd
import pytest

from strategy_lab.data.research_inputs import (
    IdentityWindow, complete_window_mask, require_funding_window, segment_research_bars,
)

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    p=ROOT/'research/platform/data-lake-governance/scripts'/f'{name}.py'
    s=importlib.util.spec_from_file_location(name,p)
    m=importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def bars(n=8):
    return pd.DataFrame([dict(ts=t,symbol='BTC/USDT:USDT',exchange='binance',market_type='perp',
        timeframe='15m',open=2.,high=3.,low=1.,close=2.,volume=10.,quote_volume=20.,trade_count=5,
        vwap=2.,is_closed=True,source='binance_vision_kline_daily_gap_repair')
        for t in pd.date_range('2026-09-05T00:00:00Z',periods=n,freq='15min')])


def diagnostic(frame):
    return segment_research_bars(frame,'15m',identity_policy='observed_diagnostic')


def test_unknown_identity_denied_by_default():
    f=segment_research_bars(bars(),'15m')
    assert f.observed_valid.all()
    assert not f.eligible.any()


@pytest.mark.parametrize('unit',['s','ms','us','ns'])
def test_timestamp_resolution_does_not_change_grid(unit):
    f=bars()
    f['ts']=f.ts.dt.as_unit(unit)
    assert diagnostic(f).eligible.all()


def test_gap_blocks_returns_and_future_windows():
    f=diagnostic(bars().drop(index=3))
    assert f.research_segment_id.nunique()==2
    returns=f.groupby('research_segment_id').close.pct_change(fill_method=None)
    assert returns.isna().sum()==2
    assert complete_window_mask(f,backward=2,forward=1).sum()==3


def test_zero_trade_resets_both_sides():
    raw=bars()
    raw.loc[3,['volume','quote_volume','trade_count']]=0
    f=diagnostic(raw)
    assert not f.loc[3,'eligible']
    assert f.research_segment_id.nunique()==2
    assert not complete_window_mask(f,forward=1).iloc[2]
    assert not complete_window_mask(f,backward=2).iloc[4]


@pytest.mark.parametrize('bad',['unordered','duplicate','naive','off_grid','mixed','closure_string'])
def test_bad_input_refused(bad):
    f=bars()
    if bad=='unordered':
        f=f.iloc[::-1]
    elif bad=='duplicate':
        f=pd.concat([f,f.iloc[[0]]])
    elif bad=='naive':
        f['ts']=f.ts.dt.tz_localize(None)
    elif bad=='off_grid':
        f['ts']=f.ts+pd.Timedelta(seconds=1)
    elif bad=='mixed':
        f.loc[0,'timeframe']='1h'
    else:
        f['is_closed']='true'
    with pytest.raises(ValueError):
        diagnostic(f)


def test_identity_windows_need_full_bar_and_reset():
    windows=[IdentityWindow('BTC/USDT:USDT','2026-09-05T00:00:00Z','2026-09-05T01:00:00Z','evidence A'),
             IdentityWindow('BTC/USDT:USDT','2026-09-05T01:00:00Z','2026-09-05T02:00:00Z','evidence B')]
    f=segment_research_bars(bars(),'15m',identity_windows=windows)
    assert f.eligible.all()
    assert f.research_segment_id.nunique()==2
    assert not complete_window_mask(f,forward=1).iloc[3]


@pytest.mark.parametrize('tf,n',[('1h',4),('4h',16),('1d',96)])
def test_aggregate_complete_bucket_and_daily_source(tf,n):
    m=module('build_binance_v3_research_inputs')
    raw=bars(n)
    if tf=='1d':
        raw['ts']=raw.ts-pd.Timedelta(days=1)
    c=m.connect()
    c.register('bars',raw)
    out=c.execute(m.aggregate_sql(tf)).df()
    assert len(out)==1
    assert out.source.iloc[0]=='binance_vision_kline_daily_gap_repair'
    assert out.volume.iloc[0]==10*n
    c.unregister('bars')
    c.register('bars',raw.iloc[:-1])
    assert c.execute(m.aggregate_sql(tf)).df().empty
    c.close()


def test_unclosed_last_day_excluded():
    m=module('build_binance_v3_research_inputs')
    c=m.connect()
    c.register('bars',bars(96))
    assert c.execute(m.aggregate_sql('1d')).df().empty
    c.close()


def funding():
    return pd.DataFrame(dict(symbol=['BTC/USDT:USDT']*2,
        ts=pd.to_datetime(['2026-09-05T00:00:00Z','2026-09-05T08:00:00.002Z'],utc=True,format='mixed'),
        funding_rate=[.0001,.0002],event_unambiguous=[True,True]))


def test_funding_missing_and_ambiguous_are_not_zero():
    kw=dict(symbol='BTC/USDT:USDT',start='2026-09-04T23:00:00Z',end='2026-09-05T09:00:00Z',calendar_evidence='frozen evidence')
    with pytest.raises(ValueError):
        require_funding_window(funding(),expected_event_times=None,**kw)
    times=['2026-09-05T00:00:00Z','2026-09-05T08:00:00.002Z']
    assert len(require_funding_window(funding(),expected_event_times=times,**kw))==2
    with pytest.raises(ValueError):
        require_funding_window(funding().iloc[:1],expected_event_times=times,**kw)
    f=funding()
    f.loc[0,'event_unambiguous']=False
    with pytest.raises(ValueError):
        require_funding_window(f,expected_event_times=times,**kw)


def test_funding_preserves_milliseconds_and_rejects_wrong_symbol():
    m=module('govern_binance_v3_funding')
    job={'symbol':'BTC/USDT:USDT','end_ms':2000}
    rows=[{'symbol':'BTCUSDT','fundingTime':1002,'fundingRate':'.0001'}]
    m.validate_page(rows,job,1000)
    assert rows[0]['fundingTime']==1002
    rows[0]['symbol']='ETHUSDT'
    with pytest.raises(ValueError):
        m.validate_page(rows,job,1000)


def test_funding_unknown_event_type_and_future_cutoff_refused():
    m=module('govern_binance_v3_funding')
    with pytest.raises(ValueError):
        m.validate_page([{'symbol':'BTCUSDT','fundingTime':1002,'fundingRate':'.0001','rateType':'unknown'}],
                        {'symbol':'BTC/USDT:USDT','end_ms':2000},1000)
    f=funding()
    f.attrs['funding_manifest']={'cutoff_exclusive_utc':'2026-09-05T08:30:00Z'}
    with pytest.raises(ValueError,match='cutoff'):
        require_funding_window(f,symbol='BTC/USDT:USDT',start='2026-09-05T08:45:00Z',end='2026-09-05T09:00:00Z',
                               expected_event_times=[],calendar_evidence='frozen evidence')


@pytest.mark.parametrize('bad',['naive','null'])
def test_funding_bad_event_timestamp_refused(bad):
    f=funding()
    if bad=='naive':
        f['ts']=f.ts.dt.tz_localize(None)
    else:
        f.loc[0,'ts']=pd.NaT
    with pytest.raises(ValueError):
        require_funding_window(f,symbol='BTC/USDT:USDT',start='2026-09-04T23:00:00Z',end='2026-09-05T09:00:00Z',
                               expected_event_times=['2026-09-05T00:00:00Z','2026-09-05T08:00:00.002Z'],calendar_evidence='frozen evidence')


@pytest.mark.parametrize('case',['valid','bad_checksum','bad_month','bad_interval','official_404','unicode_symbol'])
def test_archive_validation_and_receipts(tmp_path,monkeypatch,case):
    m=module('backfill_binance_v3_funding_archives')
    monkeypatch.setattr(m,'ROOT',tmp_path)
    monkeypatch.setattr(m,'ART',tmp_path/'artifacts')
    monkeypatch.setattr(m,'RAW',tmp_path/'raw')
    m.RAW.mkdir()
    (m.ART/'archive_receipts').mkdir(parents=True)
    (m.ART/'archive_events').mkdir()
    ts=int(pd.Timestamp('2026-08-01T00:00:00Z').value//1_000_000)
    if case=='bad_month':
        ts+=32*86400000
    interval=0 if case=='bad_interval' else 8
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        z.writestr('BTCUSDT-fundingRate-2026-08.csv',f'calc_time,funding_interval_hours,last_funding_rate\n{ts},{interval},0.0001\n')
    blob=buf.getvalue()
    checksum=hashlib.sha256(blob).hexdigest()
    if case=='bad_checksum':
        checksum='0'*64
    def fake_request(url):
        if case=='unicode_symbol':
            assert url.isascii() and '%E5%B8%81' in url
        if case=='official_404':
            raise HTTPError(url,404,'not found',{},None)
        return checksum.encode()+b'  archive.zip\n' if url.endswith('.CHECKSUM') else blob
    monkeypatch.setattr(m,'request',fake_request)
    job={'code':'BTCUSDT','symbol':'BTC/USDT:USDT','month':'2026-08'}
    if case=='unicode_symbol':
        job.update(code='币安人生USDT',symbol='币安人生/USDT:USDT')
    if case in ('bad_checksum','bad_month','bad_interval'):
        with pytest.raises(ValueError):
            m.fetch(job)
    else:
        result=m.fetch(job)
        assert result['status']==('OFFICIAL_404' if case=='official_404' else 'CHECKSUM_AND_CRC_PASS')
        assert m.fetch(job)==result


def test_funding_partial_publication_roundtrip(tmp_path,monkeypatch):
    m=module('govern_binance_v3_funding')
    for key,value in {'ROOT':tmp_path,'ART':tmp_path/'artifacts','BASE':tmp_path/'base',
                      'OUT':tmp_path/'data/derived/datasets/funding'}.items():
        monkeypatch.setattr(m,key,value)
    m.ART.mkdir()
    m.BASE.mkdir()
    m.OUT.parent.mkdir(parents=True)
    (tmp_path/'data/derived/_staging').mkdir()
    (m.ART/'receipts').mkdir()
    script=tmp_path/'fixture_builder.py'
    script.write_text('# isolated test builder identity\n')
    monkeypatch.setattr(m,'__file__',str(script))
    base=pd.DataFrame({'symbol':['BTC/USDT:USDT'],'ts':[pd.Timestamp('2026-08-01T00:00:00Z')],
                       'funding_rate':[0.0001],'mark_price':[100.], 'source':['binance_vision_funding_monthly']})
    base.to_parquet(m.BASE/'base.parquet',index=False)
    job={'symbol':'BTC/USDT:USDT','kind':'tail','start_ms':m.ms('2026-08-01T00:00:00Z'),
         'end_ms':m.ms('2026-08-01T08:00:00Z'),'job_id':'btc'}
    missing={**job,'symbol':'ETH/USDT:USDT','job_id':'eth'}
    raw=tmp_path/'raw.json.gz'
    raw.write_bytes(gzip.compress(json.dumps([{'symbol':'BTCUSDT','fundingTime':job['end_ms'],
                                             'fundingRate':'.0002','markPrice':'101','rateType':'Regular'}]).encode()))
    receipt={**job,'rows':1,'status':'API_RETURNED_EVENTS','pages':[{'path':'raw.json.gz','sha256':m.sha256_file(raw)}]}
    (m.ART/'receipts/btc.json').write_text(json.dumps(receipt))
    plan={'jobs':[job,missing],'base_fingerprint':m.inventory_fingerprint(m.parquet_inventory(m.BASE)),
          'base_rows':1,'base_exact_unique_rows':1}
    (m.ART/'plan.json').write_text(json.dumps(plan))
    with pytest.raises(ValueError,match='uncompleted'):
        m.build(plan)
    assert not m.OUT.exists()
    m.build(plan,allow_partial=True)
    accepted=json.loads((m.ART/'acceptance.json').read_text())
    assert accepted['rows']==2 and accepted['new_exact_keys']==1
    assert accepted['pending_query_jobs']==1 and accepted['status']=='PARTIAL_COVERAGE'
    assert accepted['published_verification']=='PASS' and accepted['legacy_funding_unchanged']
    from strategy_lab.data.research_inputs import load_verified_funding_snapshot
    assert len(load_verified_funding_snapshot(m.OUT))==2
