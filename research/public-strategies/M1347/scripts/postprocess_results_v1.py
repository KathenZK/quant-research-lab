"""Append-only public derived results: no execution, new data, or parameter changes."""
import argparse
import csv
import hashlib
import json
from decimal import Decimal as D, localcontext
from pathlib import Path

FAMILY = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = '5ccadf192dfc6381721058d28887cd9bc435a20c'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p, value):
    with p.open('x') as f: json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False); f.write('\n')
def read(p):
    with p.open(newline='') as f: return list(csv.DictReader(f))

def main(runtime, output):
    spec = json.loads((FAMILY / 'specs/protocol-v1.json').read_text())
    source = json.loads((FAMILY / 'source/catalog-public-fields.json').read_text())
    raw = runtime / 'results'
    manifest = json.loads((raw / 'manifest.json').read_text())
    for item in manifest:
        p = raw / item['path']; assert p.stat().st_size == item['bytes'] and sha(p) == item['sha256']
    summary = json.loads((raw / 'summary.json').read_text()); cases = {x['case']: x for x in summary['cases']}
    assert list(cases) == ['base', 'fee0', 'fee20', 'delay2'] and summary['new_controls'] == 0
    control = json.loads((FAMILY / 'specs/control-reference.json').read_text())
    output.mkdir(parents=True, exist_ok=False)
    copies = [(raw / 'summary.json', 'summary.json'), (raw / 'manifest.json', 'private-output-manifest.json'),
              (runtime / 'account-validation.json', 'account-validation.safe.json'),
              (runtime / 'causality-validation.json', 'causality-validation.safe.json'),
              (runtime / 'fresh-restore/restoration-receipt.json', 'local-recovery.safe.json'),
              (runtime / 'execution-end.json', 'execution.safe.json'),
              (runtime / 'derived-failure-scenarios.json', 'failure-scenarios.json'),
              (runtime / 'control-readonly-validation.json', 'control-validation.safe.json')]
    copies += [(raw / f'{name}-monthly.csv', f'{name}-monthly.csv') for name in cases]
    for src, name in copies:
        with (output / name).open('xb') as f: f.write(src.read_bytes())
    nav = read(raw / 'base-nav.csv'); assert len(nav) == 731
    curve = []; peak = D(100000)
    with localcontext() as ctx:
        ctx.prec = 50
        for i, row in enumerate(nav):
            equity = D(row['equity']); peak = max(peak, equity)
            if i == 0 or i == len(nav) - 1 or row['open_time'][:7] != nav[i + 1]['open_time'][:7]:
                curve.append(dict(date=row['open_time'][:10], equity=float(equity / D(100000)), drawdown=float(equity / peak - 1)))
    assert len(curve) == 25 and curve[0]['equity'] == 1
    dump(output / 'base-nav-sampled.json', curve)
    def metrics(case):
        values = {k: case[k] for k in ['total_return', 'cagr', 'max_drawdown', 'sharpe_zero_cash', 'observations', 'final_equity']}
        return dict(values, sharpe=case['sharpe_zero_cash'], start='2023-01-01', end='2024-12-31', annualization=365,
                    status='CATALOG_HYPOTHESIS_DIAGNOSTIC')
    family = 'catalog-daily-monthturn-fullcash'; run = 'm1347-catalog-daily-20261003-v1'; variant = 'M1347-catalog-daily-v1-base'
    audit = dict(source_verification_status='CATALOG_ONLY_ORIGINAL_WEBPAGE_UNVERIFIED',
                 source_rule_attribution_status='USER_AUTHORIZED_CATALOG_HYPOTHESIS', strict_reproductions=0,
                 input_quality='DIAGNOSTIC_ONLY', PIT='NOT_PROVEN', original_runtime_equivalence=False,
                 economic_conclusion='All four predetermined configurations lost money; no support for this hypothesis in this exposed window')
    record = dict(id='M1347', name='BTC月末倒数第三日到次月第三日：目录假设', status='tested_proxy_only',
                  reason='1规则实现4固定策略配置；0新增控制；全部亏损；strict0', tested_variants=1, families=[family],
                  audit=audit, implementations=[dict(variant_id=variant, family=family, origin_run_id=run, fidelity_class='HYPOTHESIS')],
                  configuration_runs=4, new_control_runs=0, research_classification='HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED')
    assumptions = [spec['classification'], spec['capital_provenance'], spec['calendar_execution']['interpretation'],
                   spec['entry'], spec['exit'], spec['calendar_execution']['lag1'], spec['calendar_execution']['lag2'],
                   spec['cold_start'], spec['evaluation'], spec['precision'], spec['valuation'],
                   '初始100000USDT，100%买入含费；base双边8bps费+2bps滑点；fee0/20保留双边2bps滑点；delay2为8bps且延迟两根。',
                   '已验M1258同窗100%含费base成本买持只作引用，0新控制；各费用变体没有新增成本匹配对照。',
                   '来源是优化表选窗，作者网页未验证；市场PIT和可成交性未证明；非未触碰OOS。']
    detail = dict(id='M1347', run_id=run, origin_run_id=run, variant_id=variant, name=record['name'], family=family,
        fidelity_class='HYPOTHESIS', fidelity_reason='目录假设与UTC月历/满仓/下一开盘执行改编，非作者严格复现',
        research_classification='HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED', execution_class='ADAPTED_EXECUTION_PROXY',
        metrics=dict(periods={'full': metrics(cases['base']), '2023-2024': metrics(cases['base'])},
            same_instrument_benchmark={'2023-2024': metrics(control['metrics'])},
            additional_native_bar_lag={'2023-2024': metrics(cases['delay2'])},
            cost_sensitivity={name: {'2023-2024': metrics(cases[name])} for name in ['fee0', 'fee20']},
            implementation_fidelity='ADAPTED_EXECUTION_PROXY', capital_state=dict(initial_cash_usdt=100000,
            final_equity_usdt=cases['base']['final_equity'], final_position_open=True, terminal_pending=cases['base']['terminal_pending'])),
        spec=dict(source_url=source['fields']['source_url'], assumptions=assumptions,
            rule_excerpt=source['rule_original_operational_excerpt'],
            params=dict(timeframe='1d', calendar='UTC_24_7', entry='day=month_length-2 at close', exit='day=3 at close',
                        fraction='1', entry_fee_inclusive=True, fee_bps=8, slippage_bps=2, lag_bars=1)),
        audit=audit, deep_validation=dict(account='PASS pinned independent Decimal serialized full ledgers; external review tracked separately',
            causality='PASS 16 actual feature prefixes+16 future mutations; prehistory60 account prefix/future pairs',
            recovery='PASS 31files byte-exact fresh local; remote core for thisID pending coordinator'),
        curve=curve, curve_meta=dict(observations=731, total_observations=731, returned_points=25,
            sampling='first barclose+24UTCmonthend closes; UTC bar-open date labels', equity_unit='initial_capital_multiple',
            drawdown_unit='fraction', drawdown_source='full731dailyseries+initial100000anchor; not sampled curve recomputation',
            benchmark_curve_available=False),
        lineage=dict(source_commit=SOURCE_COMMIT, C0_sha256=sha(FAMILY / 'specs/C0-v1.json'), input_sha256=spec['input']['sha256'],
            result_manifest_sha256=sha(raw / 'manifest.json'), control_reference_sha256=sha(FAMILY / 'specs/control-reference.json'),
            control_remote_commit=spec['benchmark']['original_remote_core_commit'], new_control_runs=0),
        limitations=['Strict0;notpromoted', 'Prior-exposed2023–2024nonOOS;optimization-selectedcatalogwindow',
            'No partial fills, tick/lot limits, market impact, orderbook or actual available_at model',
            'All 4 tested configurations negative; zero-fee case still negative',
            'Private fullNAV/raw and internalcuration excluded from public projection'])
    dump(output / 'graph-record.json', record); dump(output / 'graph-detail.json', detail)
    dump(output / 'derivation-receipt.json', dict(status='DERIVED_ONLY_NO_NEW_RUNS', source_commit=SOURCE_COMMIT,
         script_sha256=sha(Path(__file__)), original_result_manifest_sha256=sha(raw / 'manifest.json'),
         source_base_nav_sha256=sha(raw / 'base-nav.csv'), curve_points=25, metric_observations=731,
         initial_capital_division_count=1, private_fullNAV_in_public=False,
         private_result_manifest_kind='HASH_ONLY_FULL_RESULT_INVENTORY; not a Graph public display manifest',
         new_strategy_configurations=0, new_controls=0, source_original_graph_flags_changed=False))

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--runtime', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); main(a.runtime, a.output)
