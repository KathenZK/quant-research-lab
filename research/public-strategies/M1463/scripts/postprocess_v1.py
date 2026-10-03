"""Post-return publication shaping only; no execution, tuning or data requests."""
import csv,hashlib,json
from pathlib import Path
from decimal import Decimal as D,localcontext
FAMILY=Path(__file__).resolve().parents[1];ART=FAMILY/'artifacts/20261003-catalog-v1'

def read(p):
    with p.open(newline='') as f:return list(csv.DictReader(f))
def dump(p,value):
    with p.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    spec=json.loads((FAMILY/'specs/protocol-v1.json').read_text());ident=spec['id'];source=json.loads((FAMILY/'source/catalog-original-fields.json').read_text())['fields']
    raw=ART/'private-results';summary=json.loads((raw/'summary.json').read_text());cases={c['case']:c for c in summary['cases']}
    control=json.loads((FAMILY/'recovery/control-release-v1/control-reference.json').read_text())
    for old,new in [(raw/'summary.json',ART/'summary.json'),(raw/'manifest.json',ART/'private-output-manifest.json'),(ART/'private-fresh-restore/restoration-receipt.json',ART/'local-recovery.json')]:
        with new.open('xb') as f:f.write(old.read_bytes())
    def metrics(c):
        keys=['total_return','cagr','max_drawdown','sharpe_zero_cash','observations','final_equity']
        m={k:c[k] for k in keys};m.update(sharpe=c['sharpe_zero_cash'],start='2023-01-01',end='2024-12-31',annualization=365,status='CATALOG_HYPOTHESIS_DIAGNOSTIC');return m
    nav=read(raw/'base-nav.csv');peak=D(100000);curve=[]
    with localcontext() as ctx:
        ctx.prec=50
        for i,row in enumerate(nav):
            equity=D(row['equity']);peak=max(peak,equity)
            if i==0 or i==len(nav)-1 or row['open_time'][:7]!=nav[i+1]['open_time'][:7]:curve.append(dict(date=row['open_time'][:10],equity=float(equity/D(100000)),drawdown=float(equity/peak-1)))
    assert len(curve)==25
    assumptions=[spec['classification'],spec['capital_provenance'],spec['cold_start'],spec['evaluation'],spec['precision'],spec['valuation'],'base8bps/2bps each side; fee0 and fee20 retain2bps slippage; delay2 extra dailybar','No author runtime equivalence, PIT/tradability not proven; no untouched OOS','M1258 accepted existing fullcash100%control, no newcontrol']
    if ident=='M1396':assumptions += [spec['hl2_SMA4'],spec['calendar_execution'],'Original2012–2018 filter explicitly overridden2023–2024 before returns']
    else:assumptions += [spec['bollinger']['variance'],spec['entry'],spec['exit'],'No membership content or internal catalog curation published']
    family='catalog-daily-weekday-hl2-fullcash' if ident=='M1396' else 'catalog-daily-bollinger20x2-fullcash'
    name='BTC周二hl2过滤/周六退出：目录假设' if ident=='M1396' else 'BTC布林20/2上破/中轨退出：目录假设'
    run=ident.lower()+'-catalog-daily-20261003-v1';variant=ident+'-catalog-daily-v1-base'
    record=dict(id=ident,name=name,status='tested_proxy_only',reason='CATALOG_HYPOTHESIS / ADAPTED_EXECUTION_PROXY;1规则实现4固定策略配置0新control;strict0',tested_variants=1,families=[family],audit=dict(source_verification_status='CATALOG_ONLY_ORIGINAL_WEBPAGE_UNVERIFIED',source_rule_attribution_status='USER_AUTHORIZED_CATALOG_HYPOTHESIS',strict_reproductions=0,input_quality='DIAGNOSTIC_ONLY',PIT='NOT_PROVEN',original_runtime_equivalence=False),implementations=[dict(variant_id=variant,family=family,origin_run_id=run,fidelity_class='HYPOTHESIS')],configuration_runs=4,new_control_runs=0)
    dump(ART/'graph-record.json',record)
    detail=dict(id=ident,run_id=run,origin_run_id=run,variant_id=variant,name=name,family=family,fidelity_class='HYPOTHESIS',fidelity_reason='目录规则锚定的显式日线假设与全现金成交代理，非原作者严格复现',metrics=dict(periods={'full':metrics(cases['base']),'2023-2024':metrics(cases['base'])},same_instrument_benchmark={'2023-2024':metrics(control['metrics'])},additional_native_bar_lag={'2023-2024':metrics(cases['delay2'])},cost_sensitivity={n:{'2023-2024':metrics(cases[n])} for n in ['fee0','fee20']},implementation_fidelity='ADAPTED_EXECUTION_PROXY',capital_state=dict(initial_cash_usdt=100000,final_equity_usdt=cases['base']['final_equity'],final_position_open=D(cases['base']['final_quantity'])>0,terminal_pending=cases['base']['terminal_pending'])),spec=dict(source_url=source['source_url'],assumptions=assumptions,rule_excerpt=source['规则'],params=dict(timeframe='1d',fraction='1',fee_bps=8,slippage_bps=2,lag_bars=1)),audit=record['audit'],deep_validation=dict(account='PASS independent Decimal serialized state/fills/months',causality='PASS 24prefix/future checks',recovery='31files byte-exact fresh local; thisID remote core pending coordinator'),curve=curve,curve_meta=dict(observations=731,total_observations=731,returned_points=25,sampling='first barclose+24UTCmonthend closes;bar-open date label',equity_unit='initial_capital_multiple',drawdown_unit='fraction',benchmark_curve_available=False),lineage=dict(source_commit='56c7cae289700d73d0e2f4df582ea044c2363b0c',C0_sha256=sha(FAMILY/'specs/C0-v1.json'),input_sha256=spec['input']['sha256'],result_manifest_sha256=sha(raw/'manifest.json'),control_reference_sha256=sha(FAMILY/'recovery/control-release-v1/control-reference.json'),control_remote_commit='2a2e33e0de2b4897d6ccb460e72dcb5e73aa4153',new_control_runs=0),limitations=['Strict0;notpromoted','Prior-exposed2023–2024nonOOS','Partial fills, lot constraints, market impact and true publication timing not proved','Private fullNAV/raw excluded from public core'])
    dump(ART/'graph-detail.json',detail)
    private=dict(detail);private['curve']=[dict(date=r['open_time'][:10],equity=float(D(r['equity'])/D(100000))) for r in nav];private['curve_meta']=dict(detail['curve_meta'],returned_points=731,sampling='none')
    dump(ART/'private-graph-detail.full.json',private)
if __name__=='__main__':main()
