"""等待本轮已有下载完成，再串联资金费率发布、独立验收和定向测试。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from strategy_lab.data.manifest import sha256_file, utc_now_iso, write_canonical_json

ROOT=Path(__file__).resolve().parents[4]
FAMILY=ROOT/'research/platform/data-lake-governance'
ART=FAMILY/'artifacts/binance_v3_research_inputs_v1_20260907'


def run(command,name):
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,check=False)
    write_canonical_json(ART/f'{name}_execution.json',{'command':command,'returncode':result.returncode,
        'stdout':result.stdout,'stderr':result.stderr,'finished_at':utc_now_iso()})
    print(result.stdout[-2000:],flush=True)
    if result.returncode:
        raise RuntimeError(f'{name} failed; see retained execution log')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--allow-partial',action='store_true')
    args=parser.parse_args()
    f=ART/'funding'
    deadline=time.monotonic()+3600
    required=len(json.loads((f/'plan.json').read_text())['jobs'])
    while True:
        complete=len(list((f/'receipts').glob('*.json')))==required
        archive=json.loads((f/'archive_summary.json').read_text()) if (f/'archive_summary.json').exists() else {}
        if archive.get('errors'):
            unresolved=[]
            for error in archive['errors']:
                job=error['job']
                receipt=f/'archive_receipts'/f'{job["code"]}_{job["month"]}.json'
                if not receipt.exists():
                    unresolved.append(error)
            if unresolved:
                raise RuntimeError('archive failures must be reviewed before closeout')
            write_canonical_json(ART/'archive_retry_resolution.json',{'original_errors':archive['errors'],
                'unresolved':0,'resolved_by_retained_receipts':True,'checked_at':utc_now_iso()})
        if (complete or args.allow_partial) and archive:
            break
        if time.monotonic()>deadline:
            write_canonical_json(ART/'closeout_wait_timeout.json',{'status':'PENDING_DOWNLOAD_OR_ACCESS',
                'funding_receipts':len(list((f/'receipts').glob('*.json'))),'expected':required,'at':utc_now_iso()})
            raise TimeoutError('downloads incomplete; existing artifacts preserved; no completion claim')
        time.sleep(10)
    funding_out=ROOT/'data/derived/datasets/binance_perp_funding_v3_inputs_v1'
    if not funding_out.exists():
        command=[sys.executable,str(FAMILY/'scripts/govern_binance_v3_funding.py'),'--phase','build']
        if args.allow_partial:
            command.append('--allow-partial')
        run(command,'funding_build')
    if not (f/'acceptance.json').exists():
        raise RuntimeError('funding exists without independent acceptance; inspect before continuing')
    run([sys.executable,str(FAMILY/'scripts/verify_binance_v3_research_inputs.py')],'final_verification')
    run([sys.executable,'-m','pytest','-q','tests/test_v3_research_inputs.py',
        'tests/test_binance_15m_history_closeout.py','tests/test_binance_15m_history_v3.py',
        'tests/test_binance_15m_refresh_v2.py','tests/test_ohlcv_round3_governance.py'],'targeted_tests')
    from strategy_lab.data.research_inputs import load_verified_funding_snapshot
    events=load_verified_funding_snapshot(funding_out)
    funding=json.loads((f/'acceptance.json').read_text())
    write_canonical_json(ART/'execution_closeout.json',{
        'completed_at':utc_now_iso(),'status':('PARTIAL_BLOCKED_FUNDING_ACCESS' if funding.get('pending_query_jobs') else 'GOVERNED_WITH_EXPLICIT_RESEARCH_LIMITS'),
        'price_publications_verified':True,'funding_verified_rows':len(events),
        'funding_status':funding['status'],'funding_calendar_fully_verified':False,
        'full_historical_identity_verified':False,'legacy_consumers_migrated':False,
        'bundle_sha256':sha256_file(ART/'research_input_bundle.json'),
        'test_execution_sha256':sha256_file(ART/'targeted_tests_execution.json')})
    print('V3 research inputs execution closeout written; explicit research limitations remain',flush=True)


if __name__=='__main__':
    main()
