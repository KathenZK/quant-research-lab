"""资金费率 v2 独立回读、真实窗口拒绝检查、旧输入保护与测试留证。"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd

from strategy_lab.data.funding_v2 import VerifiedFundingV2, load_funding_v2, require_funding_v2_window
from strategy_lab.data.manifest import inventory_fingerprint, parquet_inventory, sha256_file, utc_now_iso, write_canonical_json

ROOT=Path(__file__).resolve().parents[4]
FAMILY=ROOT/'research/platform/data-lake-governance'
ART=FAMILY/'artifacts/binance_funding_v3_inputs_v2_20260907'
OUT=ROOT/'data/derived/datasets/binance_perp_funding_v3_inputs_v2'


def run(command,name,required=True):
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,check=False)
    write_canonical_json(ART/f'{name}_execution.json',{'command':command,'returncode':result.returncode,
        'stdout':result.stdout,'stderr':result.stderr,'finished_at':utc_now_iso()})
    print(result.stdout[-3000:],flush=True)
    if required and result.returncode:
        raise RuntimeError(f'{name} failed; inspect retained log')
    return result.returncode


def must_reject(data,kwargs):
    try:
        require_funding_v2_window(data,**kwargs)
    except ValueError as exc:
        return str(exc)
    raise AssertionError('invalid window was accepted')


def main():
    acceptance=json.loads((ART/'acceptance.json').read_text())
    data=load_funding_v2(OUT,expected_manifest_sha256=acceptance['manifest_sha256'])
    for key,path in [('reader_sha256',ROOT/'src/strategy_lab/data/funding_v2.py'),
                     ('builder_sha256',FAMILY/'scripts/build_binance_funding_v2.py')]:
        if sha256_file(path)!=data.manifest[key]:
            raise ValueError(f'frozen source changed: {key}')
    for key,filename in [('input_receipts_sha256','input_receipts.json'),
                         ('event_mapping_sha256','event_mapping.csv'),
                         ('hour_adjudication_sha256','hour_adjudication.csv'),
                         ('value_lineage_audit_sha256','value_lineage_audit.json'),
                         ('global_parity_sha256','global_parity.json'),
                         ('stock_event_types_sha256','stock_event_types.json'),
                         ('query_evidence_coverage_sha256','query_evidence_coverage.csv')]:
        if sha256_file(ART/filename)!=data.manifest[key]:
            raise ValueError(f'frozen evidence changed: {filename}')
    identity=pd.read_csv(FAMILY/'artifacts/binance_v3_research_inputs_v1_20260907/identity_inventory.csv')
    assert set(data.events.symbol)==set(identity.symbol)
    assert data.events.event_unambiguous.all()
    assert data.events.rate_type.eq('Special').sum()==34
    assert data.events.ts.max()<=pd.Timestamp(data.manifest['cutoff_utc'])
    s=data.segments[data.segments.symbol.eq('BTC/USDT:USDT')].sort_values('expected_events').iloc[-1]
    expected=data.expected[data.expected.segment_id.eq(s.segment_id)].sort_values('ts')
    kw={'symbol':s.symbol,'start':s.start.isoformat(),'end':expected.ts.iloc[2].isoformat(),
        'identity_evidence':'PLUMBING_TEST_ONLY: this string is not actual PIT certification'}
    good=require_funding_v2_window(data,**kw)
    assert len(good)==3
    small=data.events[data.events.symbol.eq(s.symbol)].copy()
    broken=VerifiedFundingV2(small[~small.event_id.eq(good.event_id.iloc[0])],data.segments,data.expected,data.manifest)
    missing=must_reject(broken,kw)
    recent=must_reject(data,{**kw,'start':'2026-09-01T00:00:00Z','end':'2026-09-02T00:00:00Z'})
    empty=require_funding_v2_window(data,**{**kw,'start':(s.start+pd.Timedelta(minutes=10)).isoformat(),
        'end':(s.start+pd.Timedelta(minutes=20)).isoformat()})
    assert empty.empty
    write_canonical_json(ART/'real_reader_smoke.json',{'status':'PASS','manifest_sha256':acceptance['manifest_sha256'],
        'verified_rows':len(data.events),'symbols':data.events.symbol.nunique(),'special_events':34,
        'accepted_plumbing_window':kw,'accepted_event_count':len(good),'missing_event_rejected':missing,
        'api_only_recent_calendar_rejected':recent,'proven_no_event_subwindow_empty':True,
        'identity_certified_by_this_test':False})
    old_manifest=json.loads((ROOT/'data/derived/datasets/binance_perp_funding_v3_inputs_v1/_MANIFEST.json').read_text())
    legacy=ROOT/'data/normalized/funding_rates/exchange=binance'
    actual=inventory_fingerprint(parquet_inventory(legacy))
    if actual!=old_manifest['base_fingerprint']:
        raise ValueError('legacy normalized funding changed')
    protection=json.loads((ART/'protected_inputs.json').read_text())
    for r in protection['datasets']:
        slug={'binance.perp.ohlcv.15m.history.v3':'binance_perp_15m_history_v3',
              'binance.perp.funding.v3_inputs.v1':'binance_perp_funding_v3_inputs_v1'}.get(r['dataset_id'])
        if slug is None:
            tf=r['dataset_id'].split('.')[3]
            slug=f'binance_perp_{tf}_from_15m_v2'
        root=ROOT/'data/derived/datasets'/slug
        if sha256_file(root/'_MANIFEST.json')!=r['manifest_sha256'] or inventory_fingerprint(parquet_inventory(root))!=r['fingerprint']:
            raise ValueError('protected publication changed during acceptance')
    write_canonical_json(ART/'closeout_protection.json',{'protected_publications':protection,
        'normalized_funding_fingerprint':actual,'normalized_funding_unchanged':True,'checked_at':utc_now_iso()})
    run([sys.executable,'-m','pytest','-q','tests/test_funding_v2.py','tests/test_v3_research_inputs.py',
         'tests/test_binance_15m_history_closeout.py','tests/test_binance_15m_history_v3.py',
         'tests/test_binance_15m_refresh_v2.py','tests/test_ohlcv_round3_governance.py'],'targeted_tests')
    scripts=[str(p.relative_to(ROOT)) for p in sorted((FAMILY/'scripts').glob('*binance_funding_v2*.py'))]
    run([sys.executable,'-m','ruff','check','src/strategy_lab/data/funding_v2.py','tests/test_funding_v2.py',*scripts],'ruff')
    consumer_status=run([sys.executable,'scripts/governance/check_trusted_consumers.py'],'consumer_gate',required=False)
    activity=json.loads((ART/'uncovered_price_activity.json').read_text())
    assert activity['input_query_coverage_sha256']==sha256_file(ART/'query_evidence_coverage.csv')
    write_canonical_json(ART/'execution_closeout.json',{
        'status':'PUBLISHED_PARTIAL_COVERAGE_WITH_EXPLICIT_DENY_GATES','completed_at':utc_now_iso(),
        'manifest_sha256':acceptance['manifest_sha256'],'reader_smoke':'PASS','protected_inputs_unchanged':True,
        'tests_execution_sha256':sha256_file(ART/'targeted_tests_execution.json'),
        'funding_calendar_fully_verified':False,'historical_identity_fully_verified':False,
        'legacy_consumers_migrated':False,'repository_consumer_gate_returncode':consumer_status,
        'uncovered_price_activity_sha256':sha256_file(ART/'uncovered_price_activity.json'),
        'free_disk_bytes':shutil.disk_usage(ROOT).free,'dataset_bytes':data.manifest['bytes']})
    print('funding v2 closeout complete; calendar and identity limits remain',flush=True)


if __name__=='__main__':
    main()
