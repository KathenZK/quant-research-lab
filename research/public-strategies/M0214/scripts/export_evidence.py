"""Export immutable own research summaries; full Graph detail stays local."""
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
    config = json.loads((FAMILY/'specs/M0214-first-replay.json').read_text())
    summary = json.loads((ROOT/'results/summary.json').read_text())
    nav = pd.read_csv(ROOT/'results/base-nav.csv')
    detailmetrics = {}
    for name,result in summary.items():
        m = dict(result['metrics'])
        m['sharpe'] = m.pop('sharpe_zero_cash')
        m.update(start='2023-01-01',end='2024-12-31')
        detailmetrics[name] = m
    validation = dict(independent_decimal=json.loads((ROOT/'independent-validation.json').read_text()),causality=json.loads((ROOT/'causality-validation.json').read_text()))
    write('validation.json',validation)
    protocol = hashlib.sha256((FAMILY/'specs/M0214-first-replay.json').read_bytes()).hexdigest()
    reason = '原表双向加密策略改为BTC现货只多；价格上穿与HA转绿冻结为同日条件，HA只作信号；来源原文未重新读取。'
    detail = dict(id='M0214',name='10/20均线与平均K：BTC只多改编',run_id='M0214-20261003-first-replay',origin_run_id='M0214-20261003-first-replay',variant_id=config['variant_id'],family=config['family'],fidelity_class='ADAPTATION',fidelity_reason=reason,
                  metrics=dict(**detailmetrics['base'],periods={'full':detailmetrics['base']},same_instrument_benchmark={'full':detailmetrics['buyhold']},cost_sensitivity={k:{'full':detailmetrics[k]} for k in ['fee0','fee20']},additional_native_bar_lag={'full':detailmetrics['lag2']}),
                  spec={'entry':config['entry'],'exit':config['exit'],'assumptions':config['ambiguity']+' '+config['source_scope'],'costs':'8bps fee + 2bps adverse slippage per side','position':'95% available cash notional; long only; no pyramiding'},
                  limitations=['只多改编，不复现原双向策略','fresh cross与above语义有歧义，固定同时性解释','历史窗口已曝光，无未看样本外','回溯归档PIT/可成交性未证','X正文空白，TradingView受限，未绕过','未测试Bend10，未晋级'],
                  equity_curve=[dict(date=r.date,equity=float(r.equity)) for r in nav.itertuples()],trades=pd.read_csv(ROOT/'results/base-trades.csv').to_dict('records'),sources=config['source_urls']+['https://data.binance.vision/'])
    write('graph-detail-local.json',detail)
    record = dict(id='M0214',name=detail['name'],status='tested_adaptation_only',reason='BTC现货只多改编真实回测及独立校验完成，收益落后持有；严格复现0。',tested_variants=1,families=[config['family']],audit={'source_verification_status':'catalog_read_original_unavailable','source_rule_attribution_status':'catalog_anchored_adaptation'},implementations=[{'variant_id':config['variant_id'],'family':config['family'],'origin_run_id':detail['run_id'],'fidelity_class':'ADAPTATION'}],related_results=[{'origin_run_id':detail['run_id'],'variant_id':config['variant_id'],'fidelity_class':'ADAPTATION','protocol_sha256':protocol}])
    write('graph-record.json',record)
    ownnav = nav[['date','equity']].copy()
    ownnav['cumulative_return'] = ownnav.equity/100000-1
    with (ROOT/'base-nav-light.csv').open('x') as handle:
        ownnav.to_csv(handle,index=False,float_format='%.12g')
    write('input-reference.json',dict(input_sha256=config['input_sha256'],rows=762,start='2022-12-01',end='2024-12-31',qa='upstream official archive checksum + 0 missing/duplicates; local hash and contiguous millisecond times rechecked',manifest_relative='../../../M0216/artifacts/20261003-first-replay/input-manifest.json',attribution='Binance Vision',license='CC BY-NC-SA 4.0',pit_proven=False,tradability_proven=False,market='spot BTCUSDT 1d UTC'))
    files = [p for p in ROOT.rglob('*') if p.is_file()]
    files += list((FAMILY/'scripts').glob('*.py'))+[FAMILY/'specs/M0214-first-replay.json']
    write('result-manifest.json',dict(created_at=datetime.now(timezone.utc).isoformat(),strategy_ids=1,strategy_configs=4,benchmark_configs=1,strict_reproductions=0,files={str(p.relative_to(FAMILY)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},scope='local frozen evidence; manifest is not an upload or remote backup receipt'))


if __name__ == '__main__':
    main()
