from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory
from strategy_lab.data.catalog import DatasetScope, load_trusted_dataset

PATH = Path(__file__).resolve().parents[1] / 'research/platform/data-lake-governance/scripts/refresh_binance_15m_v2.py'
spec = importlib.util.spec_from_file_location('refresh_v2', PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
START = m.as_ms('2026-09-05T00:00:00Z')


def bars(n=4):
    return [[START+i*m.STEP, '100', '110', '90', '101', '10',
             START+(i+1)*m.STEP-1, '1000', 5, '4', '400', '0'] for i in range(n)]


def test_explicit_close_and_fixed_cutoff():
    frame = m.frame_from_rows(bars(), 'BTCUSDT', START+4*m.STEP)
    assert frame.is_closed.all()
    assert str(frame.ts.dt.tz) == 'UTC'
    assert (frame.vwap == 100).all()
    with pytest.raises(ValueError, match='cutoff'):
        m.frame_from_rows(bars(), 'BTCUSDT', START+3*m.STEP)
    bad = bars()
    bad[0][6] -= 1
    with pytest.raises(ValueError, match='close_time'):
        m.frame_from_rows(bad, 'BTCUSDT', START+4*m.STEP)


@pytest.mark.parametrize('kind', ['duplicate','reversed','off_grid','nan','bad_ohlc','fractional_count'])
def test_invalid_inputs_fail_closed(kind):
    rows = bars()
    if kind == 'duplicate':
        rows.append(rows[-1])
    elif kind == 'reversed':
        rows = rows[::-1]
    elif kind == 'off_grid':
        rows[0][0] += 1
    elif kind == 'nan':
        rows[0][1] = 'nan'
    elif kind == 'bad_ohlc':
        rows[0][2] = '99'
    elif kind == 'fractional_count':
        rows[0][8] = 1.5
    with pytest.raises(ValueError):
        m.frame_from_rows(rows, 'BTCUSDT', START+4*m.STEP)


def test_pagination_and_original_response_sha(tmp_path, monkeypatch):
    lake = DataLakeLayout(root_dir=tmp_path,raw_dir=tmp_path/'raw',normalized_dir=tmp_path/'normalized',
                         features_dir=tmp_path/'features',cache_dir=tmp_path/'cache',derived_dir=tmp_path/'derived')
    monkeypatch.setattr(m,'layout',lambda:lake)
    monkeypatch.setattr(m,'disk_guard',lambda:None)
    rows = bars(1002)
    pages = [json.dumps(rows[:1000]).encode(),json.dumps(rows[1000:]).encode()]
    urls = []
    def fake(url):
        urls.append(url)
        return pages.pop(0)
    monkeypatch.setattr(m,'request',fake)
    job = {'symbol':'BTCUSDT','start_ms':START,'end_ms':START+1002*m.STEP}
    result = m.fetch_window(job,'tail',job['end_ms'])
    assert result['rows'] == 1002
    assert f'startTime={START+1000*m.STEP}' in urls[1]
    assert len(urls) == 2
    assert m.fetch_window(job,'tail',job['end_ms']) == result
    page = result['pages'][0]
    assert hashlib.sha256(page['response_text'].encode()).hexdigest() == page['response_sha256']


def test_snapshot_preserves_base_fills_absent_keys_and_catalog_reads(tmp_path,monkeypatch):
    lake = DataLakeLayout(root_dir=tmp_path/'data',raw_dir=tmp_path/'data/raw',normalized_dir=tmp_path/'data/normalized',
                         features_dir=tmp_path/'data/features',cache_dir=tmp_path/'data/cache',derived_dir=tmp_path/'data/derived')
    art = tmp_path/'artifacts'
    art.mkdir()
    monkeypatch.setattr(m,'ROOT',tmp_path)
    monkeypatch.setattr(m,'ART',art)
    monkeypatch.setattr(m,'layout',lambda:lake)
    monkeypatch.setattr(m,'disk_guard',lambda:None)
    script = tmp_path/'builder.py'
    script.write_text('# test fixture\n')
    monkeypatch.setattr(m,'__file__',str(script))
    base_root = lake.normalized_dir/'ohlcv/exchange=binance/market_type=perp/timeframe=15m'
    base_root.mkdir(parents=True)
    base = m.frame_from_rows(bars(2),'BTCUSDT',START+4*m.STEP)
    base_path = base_root/'base.parquet'
    base.to_parquet(base_path,index=False)
    original = base_path.read_bytes()
    fingerprint = inventory_fingerprint(parquet_inventory(base_root))
    incoming = bars()[1:]
    incoming[0][4] = '102'  # overlapping OHLC conflict must not replace accepted base.
    raw_text = json.dumps(incoming)
    record = {'symbol':'BTCUSDT','pages':[{'response_text':raw_text,'response_sha256':hashlib.sha256(raw_text.encode()).hexdigest()}],
              'status':'OK'}
    raw_root = lake.raw_dir/'_archives/binance/futures/um/api/klines'/m.RUN
    raw_root.mkdir(parents=True)
    with gzip.open(raw_root/'test.json.gz','wt') as out:
        json.dump(record,out)
    config = {'cutoff_ms':START+4*m.STEP,'cutoff_exclusive_utc':m.iso(START+4*m.STEP)}
    (art/'config.json').write_text(json.dumps(config))
    prepared = {'config':config,'files':[str(base_path)],'base_fingerprint':fingerprint,'base_rows':2,
                'base_end_ms':START+m.STEP,'jobs':[{'symbol':'BTCUSDT','metadata':{'status':'TRADING','underlyingType':'COIN','onboardDate':START}}]}
    (art/'tail_outcomes.json').write_text(json.dumps({'outcomes':[{'symbol':'BTCUSDT'}]}))
    (art/'gap_outcomes.json').write_text(json.dumps({'outcomes':[]}))
    pd.DataFrame(columns=['symbol','prev_ts','next_ts','missing_bars']).to_csv(art/'base_gaps.csv',index=False)
    m.build(prepared)
    assert base_path.read_bytes() == original
    summary = json.loads((art/'build_audit.json').read_text())
    assert summary['new_rows'] == 2
    assert summary['overlap_conflicting_rows_preserved_base'] == 1
    result = load_trusted_dataset(m.DATASET,layout=lake,requested_scope=DatasetScope.SINGLE_SYMBOL,
        symbol='BTC/USDT:USDT',end=config['cutoff_exclusive_utc'],purpose='research',gap_policy='reject')
    assert len(result.frame) == 4
    assert result.frame.loc[result.frame.ts == pd.Timestamp(START+m.STEP,unit='ms',tz='UTC'),'close'].iloc[0] == 101
    assert result.audit['quality_status'] == 'PASS'
    with pytest.raises(FileExistsError):
        m.build(prepared)
