#!/usr/bin/env python3
"""Write immutable pre-return code/spec/input/exposure registration.
Only run after user-authorized input retrieval and QA; never overwrite a freeze.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True);p.add_argument('--input-manifest',required=True);p.add_argument('--qa',required=True)
    p.add_argument('--frozen-at-utc',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[1]
    if Path(a.out).exists():raise SystemExit('Refusing to overwrite registration')
    # Caller attests to actual data permission. This never grants new authority.
    qa=json.loads(Path(a.qa).read_text())
    if any(tag in json.dumps(qa) for tag in ['FAIL','DATA_BLOCKED','REJECTED']):
        raise SystemExit('QA records a failing or blocked state; resolve before freeze')
    manifest=json.loads(Path(a.input_manifest).read_text())
    if manifest.get('row_quality') not in ['PASS','PASS_WITH_NATIVE_ZERO_VOLUME']:
        raise SystemExit('No full scoped canonical row-quality pass')
    if manifest.get('canonical_csv',{}).get('sha256')!=sha(a.input):
        raise SystemExit('Input does not match canonical manifest hash')
    if manifest.get('canonical_csv',{}).get('rows')!=18288:
        raise SystemExit('Full fixed hourly input grid is incomplete')
    if manifest.get('timeframe')!='1h':raise SystemExit('Wrong timeframe')
    if manifest.get('start_utc')!='2022-12-01T00:00:00Z' or manifest.get('end_exclusive_utc')!='2025-01-01T00:00:00Z':
        raise SystemExit('Changed fixed input window')
    if manifest.get('builder_sha256')!=sha(root/'scripts/rebuild_official_bars.py'):
        raise SystemExit('Data builder code differs from source manifest')
    files=[p for base in ['scripts','specs','sources'] for p in (root/base).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    payload={'id':'M0259','status':'FROZEN_BEFORE_RETURNS','frozen_at_utc':a.frozen_at_utc,
        'input_sha256':sha(a.input),'input_bytes':Path(a.input).stat().st_size,
        'input_manifest_sha256':sha(a.input_manifest),'input_qa_sha256':sha(a.qa),
        'input_path_at_registration':str(Path(a.input).resolve()),'path_migration':'caller supplies identical bytes via --input; original path is provenance only',
        'code_and_spec_sha256':{str(p.relative_to(root)):sha(p) for p in sorted(files)},
        'exposure':{'evaluation':'2023-2024, already historically exposed','old_search_count':'UNKNOWN','new_strategy_configurations':1,
                    'base_cases':1,'execution_sensitivity_cases':3,'buyhold_controls':1,'hyperparameter_searches':0,'oos_claim':False},
        'mutation_policy':'no overwrite; any post-result correction keeps original freeze/results and registers a separate attempt',
        'data_status':'DIAGNOSTIC_ONLY unless full pinned governance evidence separately proves all checks; not trusted via this freeze',
        'model_identity':'parent must report actual executed setting; not inferred from requested future model'}
    with open(a.out,'x') as f:f.write(json.dumps(payload,indent=2)+'\n')
    print('FROZEN_BEFORE_RETURNS',sha(a.out))
if __name__=='__main__':main()
