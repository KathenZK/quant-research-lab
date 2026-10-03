"""Freeze M0233 local Graph detail and lightweight lineage, once."""
import csv
import hashlib
import json
import platform
import sys
from pathlib import Path

FAMILY = Path(__file__).resolve().parents[1]
ART = FAMILY/'artifacts/20261003-first-replay'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(name,data):
    with (ART/name).open('x') as f:
        json.dump(data,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.write('\n')


def main():
    spec_path = FAMILY/'specs/M0233-first-replay.json'
    spec = json.loads(spec_path.read_text())
    summary = json.loads((ART/'results/summary.json').read_text())
    write('input-reference.json',dict(dataset_id='binance.spot.BTCUSDT.1d.M0216.20261003',input_sha256=spec['input_sha256'],source_manifest='../../../M0216/artifacts/20261003-first-replay/input-manifest.json',rows=762,warmup_rows=31,evaluation_rows=731,start='2022-12-01',end='2024-12-31',missing_bars=0,duplicate_rows=0,pit_proven=False,tradability_proven=False,profile=spec['data_profile']))
    write('environment.json',dict(python=sys.version,platform=platform.platform(),dependencies='stdlib; pandas for independent upstream validation; strategy_lab.research.exposure; repo uv.lock',model='unknown',reasoning_effort='unknown'))
    paths = list(FAMILY.glob('scripts/*.py'))+list((ART/'results').glob('*'))+[spec_path,ART/'validation.json',ART/'source-validation.json',ART/'source-manifest.json']
    write('result-manifest.json',dict(record_id='M0233',files={str(p.relative_to(FAMILY)):sha(p) for p in sorted(paths)},input_sha256=spec['input_sha256'],protocol_sha256=sha(spec_path),strategy_configurations=4,benchmark_configurations=1,strict_reproductions=0,overwrite_policy='frozen; never overwrite'))
    lineage = dict(input_sha256=spec['input_sha256'],protocol_sha256=sha(spec_path),manifest_sha256=sha(ART/'result-manifest.json'),license='CC BY-NC-SA 4.0',attribution='Binance Vision',source_commit=spec['source_commit'])
    run_id = 'M0233-20261003-first-replay'
    record = dict(id='M0233',name='单资产z分数回撤',status='tested_adaptation_only',reason='源码信号核验通过；BTC现货仅多改编，非原多空策略，表现弱且时序敏感',tested_variants=1,families=[spec['family']],audit=dict(source_verification_status='readable',source_rule_attribution_status='source_verified_long_only_adaptation'),implementations=[dict(variant_id=spec['variant_id'],family=spec['family'],origin_run_id=run_id,fidelity_class='ADAPTATION')],related_results=[dict(origin_run_id=run_id,variant_id=spec['variant_id'],fidelity_class='ADAPTATION',protocol_sha256=lineage['protocol_sha256'],manifest_sha256=lineage['manifest_sha256'])])
    write('graph-record.json',record)
    full = dict(summary['base']['full'],sharpe=summary['base']['full']['sharpe_zero_cash'],start='2023-01-01',end='2024-12-31')
    curves = {}
    for name in ('base','buy_hold'):
        with (ART/f'results/{name}-nav.csv').open() as f:
            curves[name] = [dict(date=r['date'],equity=float(r['equity']),drawdown=float(r['drawdown'])) for r in csv.DictReader(f)]
    write('graph-detail.json',dict(run_id=run_id,origin_run_id=run_id,id='M0233',name=record['name'],family=spec['family'],variant_id=spec['variant_id'],fidelity_class='ADAPTATION',fidelity_reason='原源码包含做空；本次负仓位映射空仓，采用下一开盘及95%现金记账，因此不是严格复现',spec=spec,metrics=dict(full,periods=dict(full=full)),benchmark=dict(name='BTCUSDT 95% buy-and-hold',metrics=summary['buy_hold']['full']),sensitivity={k:summary[k]['full'] for k in ('fee0','fee20','lag2')},equity_curve=curves['base'],benchmark_curve=curves['buy_hold'],lineage=lineage,limitations=spec['assumptions']+['2023–2024 already exposed; not untouched OOS','Source z_exit does not persist positions; no silent hysteresis repair','Archived data publication timing and execution capacity unproven'],curve_meta=dict(observations=731,total_observations=731,returned_points=731,sampling='none',benchmark_curve_available=True)))


if __name__ == '__main__':
    main()
