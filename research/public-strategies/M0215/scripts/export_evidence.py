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
    config = json.loads((FAMILY/'specs/M0215-first-replay.json').read_text())
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
    protocol = hashlib.sha256((FAMILY/'specs/M0215-first-replay.json').read_bytes()).hexdigest()
    reason = '仅原表五币列表中的BTC单腿；Wilder种子、仓位、执行成本和市场选择是明确研究假设；X出处403未复核全文。'
    detail = dict(id='M0215',name='RSI2超跌反弹：BTC单腿',run_id='M0215-20261003-first-replay',origin_run_id='M0215-20261003-first-replay',variant_id=config['variant_id'],family=config['family'],fidelity_class='HYPOTHESIS',fidelity_reason=reason,
                  metrics=dict(**detailmetrics['base'],periods={'full':detailmetrics['base']},same_instrument_benchmark={'full':detailmetrics['buyhold']},cost_sensitivity={k:{'full':detailmetrics[k]} for k in ['fee0','fee20']},additional_native_bar_lag={'full':detailmetrics['lag2']}),
                  spec={'entry':config['entry'],'exit':config['exit'],'assumptions':config['assumptions'],'costs':'8bps fee + 2bps adverse slippage per side','position':config['position']},
                  limitations=['不是全五币篮子','历史窗口已经被其他研究曝光，不是未看样本外','历史归档不证明PIT、实际成交或容量','X原帖未重新读取；原表规则由协调者核实','无熊市覆盖，未晋级'],
                  equity_curve=[dict(date=r.date,equity=float(r.equity)) for r in nav.itertuples()],trades=pd.read_csv(ROOT/'results/base-trades.csv').to_dict('records'),sources=[config['source_url'],'https://data.binance.vision/'])
    write('graph-detail-local.json',detail)
    record = dict(id='M0215',name=detail['name'],status='tested_hypothesis_only',reason='BTC单腿真实行情假设回测及独立校验完成，回报大幅落后买入持有；严格复现0。',tested_variants=1,families=[config['family']],audit={'source_verification_status':'catalog_read_public_source_403','source_rule_attribution_status':'catalog_anchored_hypothesis'},implementations=[{'variant_id':config['variant_id'],'family':config['family'],'origin_run_id':detail['run_id'],'fidelity_class':'HYPOTHESIS'}],related_results=[{'origin_run_id':detail['run_id'],'variant_id':config['variant_id'],'fidelity_class':'HYPOTHESIS','protocol_sha256':protocol}])
    write('graph-record.json',record)
    ownnav = nav[['date','equity']].copy()
    ownnav['cumulative_return'] = ownnav.equity/100000-1
    with (ROOT/'base-nav-light.csv').open('x') as handle:
        ownnav.to_csv(handle,index=False,float_format='%.12g')
    write('input-reference.json',dict(input_sha256=config['input_sha256'],rows=762,start='2022-12-01',end='2024-12-31',qa='upstream official archive checksum + 0 missing/duplicates; local hash and contiguous millisecond times rechecked',manifest_relative='../../../1d-m0216-sma-cross/artifacts/20261003-first-replay/input-manifest.json',attribution='Binance Vision',license='CC BY-NC-SA 4.0',pit_proven=False,tradability_proven=False,market='spot BTCUSDT 1d UTC'))
    files = [p for p in ROOT.rglob('*') if p.is_file()]
    files += list((FAMILY/'scripts').glob('*.py'))+[FAMILY/'specs/M0215-first-replay.json']
    write('result-manifest.json',dict(created_at=datetime.now(timezone.utc).isoformat(),strategy_ids=1,strategy_configs=4,benchmark_configs=1,strict_reproductions=0,files={str(p.relative_to(FAMILY)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},scope='local frozen evidence; manifest is not an upload or remote backup receipt'))


if __name__ == '__main__':
    main()
