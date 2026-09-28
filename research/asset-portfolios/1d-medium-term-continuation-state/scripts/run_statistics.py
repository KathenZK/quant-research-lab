"""对本家族已哈希固定的panel执行统计合同，不改变信号和估计量。"""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import sys

import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel-run',default='p1-research')
    parser.add_argument('--run-id',default='p1-statistics')
    args=parser.parse_args()
    if any(Path(x).name!=x or x in ('.','..') for x in (args.panel_run,args.run_id)):
        raise ValueError('invalid run directory')
    inp=FAMILY/'artifacts'/args.panel_run
    metadata=json.loads((inp/'panel-manifest.json').read_text())
    path=inp/'panel.pkl.gz'
    if sha(path)!=metadata['sha256']:
        raise ValueError('panel bytes changed')
    for p,digest in metadata['pins'].items():
        if sha(FAMILY/p)!=digest:
            raise ValueError(f'panel computation identity changed: {p}')
    panel=pd.read_pickle(path,compression='gzip')
    if len(panel)!=metadata['rows']:
        raise ValueError('panel rows changed')
    module_path=FAMILY/'scripts/statistics.py'
    spec=importlib.util.spec_from_file_location('mtcs_statistics',module_path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    out=FAMILY/'artifacts'/args.run_id
    if out.exists():
        raise FileExistsError(out)
    pins={p:sha(FAMILY/p) for p in ('specs/research-contract.md','specs/statistics-contract.md',
                                   'scripts/statistics.py','scripts/run_statistics.py')}
    print(f'STATISTICS rows={len(panel)} bootstrap=1000000 per block',flush=True)
    report=module.analyze(panel,out,bootstrap_reps=1_000_000,seed=20260908)
    if any(sha(FAMILY/p)!=h for p,h in pins.items()):
        raise ValueError('statistical code/contract changed during run')
    (out/'execution-receipt.json').write_text(json.dumps({
        'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'pins':pins,
        'panel_manifest_sha256':sha(inp/'panel-manifest.json'),'panel_sha256':metadata['sha256'],
        'report_sha256':sha(out/'report.json'),'history_only':True},indent=2)+'\n')
    print(json.dumps({'status':report['inference_status'],'candidate':report['selected_historical_candidate'],
                      'units':[{k:r[k] for k in ('unit','status','primary_reliable','reasons')} for r in report['units']]},indent=2),flush=True)


if __name__=='__main__':
    main()
