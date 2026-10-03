"""Immutable compact research exports; full Graph detail remains local."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY/'artifacts/20261003-first-replay'


def write(name, data):
    with (ROOT/name).open('x') as handle:
        handle.write(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def main():
    config = json.loads((FAMILY/'specs/M0220-first-replay.json').read_text())
    summary = json.loads((ROOT/'results/summary.json').read_text())
    nav = pd.read_csv(ROOT/'results/base-nav.csv')
    allmetrics = {}
    for name,result in summary.items():
        metric = dict(result['metrics'])
        metric['sharpe'] = metric.pop('sharpe_zero_cash')
        allmetrics[name] = metric
    write('validation.json',dict(independent_decimal=json.loads((ROOT/'independent-validation.json').read_text()),causality=json.loads((ROOT/'causality-validation.json').read_text())))
    reason = '作者源码已正常核实且保留与catalog差异；UTC已完成周映射、EMA种子和费用预算是显式假设，平台等价未证。'
    detail = dict(id='M0220',name='周20EMA与低点跟踪止损',run_id='M0220-20261003-first-replay',origin_run_id='M0220-20261003-first-replay',variant_id=config['variant_id'],family=config['family'],fidelity_class='HYPOTHESIS',fidelity_reason=reason,
                  metrics=dict(**allmetrics['base'],periods={'full':allmetrics['base']},same_instrument_benchmark={'full':allmetrics['buyhold']},cost_sensitivity={k:{'full':allmetrics[k]} for k in ['fee0','fee20']},additional_native_bar_lag={'full':allmetrics['lag2']}),
                  spec=dict(entry=config['entry'],exit=config['exit'],trail=config['trail'],assumptions=config['assumptions'],costs='10bps commission + adverse2bps slippage per side',position=config['allocation'],catalog_discrepancies=config['catalog_discrepancies']),
                  limitations=['不是TradingView原环境严格复现','EMA初始化历史有限；20周不消除种子影响','已曝光历史窗口，无未看样本外','回溯行情PIT/可成交性/容量未证','close触发市价退出，非盘中止损保障'],
                  equity_curve=[dict(date=r.date,equity=float(r.equity)) for r in nav.itertuples()],trades=pd.read_csv(ROOT/'results/base-trades.csv').to_dict('records'),sources=[config['source_url'],'https://data.binance.vision/'])
    write('graph-detail-local.json',detail)
    protocol = hashlib.sha256((FAMILY/'specs/M0220-first-replay.json').read_bytes()).hexdigest()
    write('graph-record.json',dict(id='M0220',name=detail['name'],status='tested_hypothesis_only',reason='源代码锚定假设真实回测，收益与回撤均劣于同成本持有；严格0。',tested_variants=1,families=[config['family']],audit=dict(source_verification_status='author_source_readable',source_rule_attribution_status='public_source_anchored_hypothesis'),implementations=[dict(variant_id=config['variant_id'],family=config['family'],origin_run_id=detail['run_id'],fidelity_class='HYPOTHESIS')],related_results=[dict(origin_run_id=detail['run_id'],variant_id=config['variant_id'],fidelity_class='HYPOTHESIS',protocol_sha256=protocol)]))
    ownnav = nav[['date','equity']].copy()
    ownnav['cumulative_return'] = ownnav.equity/10000-1
    with (ROOT/'base-nav-light.csv').open('x') as handle:
        ownnav.to_csv(handle,index=False,float_format='%.12g')
    write('input-reference.json',dict(input_sha256=config['input_sha256'],rows=762,start='2022-12-01',end='2024-12-31',evaluation_start='2023-04-25',evaluation_days=617,qa='upstream official archive checksums + no missing/duplicates; local exact hash and contiguous daily millisecond times rechecked',manifest_relative='../../../M0216/artifacts/20261003-first-replay/input-manifest.json',attribution='Binance Vision',license='CC BY-NC-SA 4.0',pit_proven=False,tradability_proven=False,market='spot BTCUSDT 1d UTC'))
    files = [p for p in ROOT.rglob('*') if p.is_file()]
    files += list((FAMILY/'scripts').glob('*.py'))+[FAMILY/'specs/M0220-first-replay.json',FAMILY/'artifacts/20261003-source-preflight/source-provenance.json']
    write('result-manifest.json',dict(created_at=datetime.now(timezone.utc).isoformat(),strategy_ids=1,strategy_configs=4,benchmark_configs=1,strict_reproductions=0,files={str(p.relative_to(FAMILY)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},scope='frozen local evidence, not remote snapshot backup receipt'))


if __name__ == '__main__':
    main()
