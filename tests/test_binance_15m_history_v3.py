from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from strategy_lab.data.catalog import DatasetScope, load_trusted_dataset
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory

PATH = Path(__file__).resolve().parents[1] / 'research/platform/data-lake-governance/scripts/govern_binance_15m_history_v3.py'
spec = importlib.util.spec_from_file_location('history_v3', PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
START = m.v2.as_ms('2026-08-01T00:00:00Z')


def bars(n=4):
    return [[START+i*m.STEP, '100', '110', '90', '101', '10', START+(i+1)*m.STEP-1,
             '1000', 5, '4', '400', '0'] for i in range(n)]


def zipped(rows, filename='BTCUSDT-15m-2026-08.csv', header=False):
    out = io.BytesIO()
    text = '\n'.join(','.join(map(str, r)) for r in rows)
    if header:
        text = 'open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n' + text
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr(filename, text)
    return out.getvalue()


@pytest.mark.parametrize('header', [False, True])
def test_archive_identity_range_and_headers(header):
    data = zipped(bars(), header=header)
    parsed = m.archive_rows(data, 'BTCUSDT-15m-2026-08.zip', START, START+4*m.STEP)
    assert len(parsed) == 4
    with pytest.raises(ValueError, match='range'):
        m.archive_rows(data, 'BTCUSDT-15m-2026-08.zip', START+m.STEP, START+4*m.STEP)
    with pytest.raises(ValueError, match='member'):
        m.archive_rows(data, 'ETHUSDT-15m-2026-08.zip', START, START+4*m.STEP)


def test_archive_checksum_and_resume_corruption(tmp_path, monkeypatch):
    lake = DataLakeLayout(root_dir=tmp_path, raw_dir=tmp_path/'raw', normalized_dir=tmp_path/'normalized',
        features_dir=tmp_path/'features', cache_dir=tmp_path/'cache', derived_dir=tmp_path/'derived')
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    monkeypatch.setattr(m.v2, 'layout', lambda: lake)
    monkeypatch.setattr(m.v2, 'disk_guard', lambda: None)
    data = zipped(bars())
    responses = [data, (hashlib.sha256(data).hexdigest()+'  BTCUSDT-15m-2026-08.zip').encode()]
    monkeypatch.setattr(m.v2, 'request', lambda u: responses.pop(0))
    receipt, rows = m.fetch_archive('BTCUSDT','monthly','2026-08',START+40*86400000)
    assert receipt['status'] == 'VERIFIED' and len(rows) == 4
    assert m.fetch_archive('BTCUSDT','monthly','2026-08',START+40*86400000)[0] == receipt
    (tmp_path/receipt['path']).write_bytes(b'corruption')
    with pytest.raises(ValueError, match='hash'):
        m.fetch_archive('BTCUSDT','monthly','2026-08',START+40*86400000)


@pytest.mark.parametrize('error', [-1003, -1000, -2015])
def test_transport_or_authorization_errors_are_not_source_absence(error):
    with pytest.raises(ValueError, match='not symbol unavailability'):
        m.parse_api_record({'status':'API_UNAVAILABLE','error':json.dumps({'code':error}),
            'pages':[], 'start_ms':START,'end_ms':START+m.STEP,'symbol':'BTCUSDT'},START+4*m.STEP)


def test_monthly_jobs_include_each_gap_month():
    jobs = m.monthly_jobs([{'symbol':'BTC/USDT:USDT','prev_ts':'2026-07-31T23:30:00Z','next_ts':'2026-09-01T00:15:00Z'}])
    assert jobs == [('BTCUSDT','monthly','2026-07'),('BTCUSDT','monthly','2026-08'),('BTCUSDT','monthly','2026-09')]


def test_cross_source_disagreement_stops_merge(tmp_path, monkeypatch):
    monkeypatch.setattr(m,'ART',tmp_path)
    a = m.v2.frame_from_rows(bars(), 'BTCUSDT', START+4*m.STEP)
    b = a.copy()
    b['source'] = m.MONTHLY
    b.loc[0,'close'] = 102
    con = m.v2.connect()
    con.register('incoming',pd.concat([a,b],ignore_index=True))
    with pytest.raises(ValueError, match='cross-source'):
        m.reconcile(con)
    con.close()


def test_publish_roundtrip_and_research_gap_guards(tmp_path, monkeypatch):
    lake = DataLakeLayout(root_dir=tmp_path/'data',raw_dir=tmp_path/'data/raw',normalized_dir=tmp_path/'data/normalized',
        features_dir=tmp_path/'data/features',cache_dir=tmp_path/'data/cache',derived_dir=tmp_path/'data/derived')
    art = tmp_path/'artifacts'
    art.mkdir()
    monkeypatch.setattr(m,'ROOT',tmp_path)
    monkeypatch.setattr(m,'ART',art)
    monkeypatch.setattr(m,'PREVIOUS',art)
    monkeypatch.setattr(m.v2,'layout',lambda:lake)
    monkeypatch.setattr(m.v2,'disk_guard',lambda:None)
    builder = tmp_path/'builder.py'
    builder.write_text('# fixture\n')
    monkeypatch.setattr(m,'__file__',str(builder))
    old_root = tmp_path/'v2'
    old_root.mkdir()
    base = m.v2.frame_from_rows([bars()[0],bars()[3]],'BTCUSDT',START+4*m.STEP)[m.COLS]
    old_file = old_root/'data.parquet'
    base.to_parquet(old_file,index=False)
    (old_root/'_MANIFEST.json').write_text('{}')
    old_bytes = old_file.read_bytes()
    incoming = m.v2.frame_from_rows([bars()[0],bars()[1],bars()[3]],'BTCUSDT',START+4*m.STEP)
    monkeypatch.setattr(m,'load_incoming',lambda p:(incoming,{'gaps':[{'remaining_bars':1}]}))
    for f in ['config.json','raw_receipts.json']:
        (art/f).write_text('{}')
    pd.DataFrame([{'gap_id':0}]).to_csv(art/'gap_adjudication.csv',index=False)
    pd.DataFrame([{'archive_symbol':'BTCUSDT','required_latest_crypto':True}]).to_csv(art/'symbol_freshness.csv',index=False)
    config = {'cutoff_ms':START+4*m.STEP,'cutoff_exclusive_utc':m.v2.iso(START+4*m.STEP)}
    prepared = {'config':config,'files':[str(old_file)],'audit':{'rows':2},
        'identity':{'manifest_sha256':'a'*64,'manifest_path':str(old_root/'_MANIFEST.json'),
            'parquet_inventory_fingerprint':inventory_fingerprint(parquet_inventory(old_root))}}
    m.build(prepared)
    assert old_file.read_bytes() == old_bytes
    audit = json.loads((art/'build_audit.json').read_text())
    assert audit['new_rows'] == 1 and audit['old_rows_lost_or_changed'] == 0
    kwargs = dict(layout=lake, requested_scope=DatasetScope.SINGLE_SYMBOL,symbol='BTC/USDT:USDT',
        end=config['cutoff_exclusive_utc'],purpose='research')
    with pytest.raises(ValueError, match='missing_bars'):
        load_trusted_dataset(m.DATASET, **kwargs, gap_policy='reject')
    loaded = load_trusted_dataset(m.DATASET, **kwargs, gap_policy='contiguous_segments')
    assert len(loaded.frame) == 3
    assert loaded.audit['internal_missing_bars'] == 1
    with pytest.raises(FileExistsError):
        m.build(prepared)
