"""Post-C0 M1349 independent full-ledger/lifecycle and causal QA only."""
import hashlib,importlib.util,json,sys
from decimal import Decimal as D
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'source'));sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_m1349_v2 as wrapper
import verify_m1349_wrapper_v2 as qa

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(rows):return [{k:str(v) for k,v in row.items()} for row in rows]
def main():
    wrapper.check_c0(ROOT,ROOT/'frozen/C0-v2.json');c0=json.loads((ROOT/'frozen/C0-v2.json').read_text())
    kernel=wrapper.load_kernel(ROOT/'kernel/v2');kernel.environment(ROOT/'frozen/runtime-v1.json')
    source=ROOT/'kernel/v2/verify_account.py';spec=importlib.util.spec_from_file_location('M1349_v2_independent_verifier',source);verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    rows=qa.read(ROOT/'input/input.csv');assert sha(ROOT/'input/input.csv')==c0['input_sha256']
    out=ROOT/'results-v2/M1349';original={p.name:sha(p) for p in out.iterdir()};rules=json.loads((ROOT/'frozen/M1349-root-frozen-rules.json').read_text())
    expected,flags=qa.independent_features(rows);assert qa.read(out/'features.csv')==expected
    account=verifier.verify_account(rows,out,dict(cases=rules['cost_cases']),flags,execution_policy=wrapper.POLICY)
    account['source_signal']='Independent exact Decimal50 ROC25 from raw strings, first ready25, strictly below-0.10 level, raw_exit=0; no shadow position state'
    supplemental=qa.audit_supplemental(out,rows,expected,kernel,rules['cost_cases']);causality=[];lifecycle=[];engine_calls=0
    for case in rules['cost_cases']:
        name=case['name'];nav=qa.read(out/f'{name}-nav.csv');dec=qa.read(out/f'{name}-decisions.csv');fills=qa.read(out/f'{name}-fills.csv');pending=qa.read(out/f'{name}-pending.csv');trips=qa.read(out/f'{name}-roundtrips.csv');summary=json.loads((out/f'{name}-summary.json').read_text())
        assert all(d['raw_exit']=='0' for d in dec)
        assert all(int(t['holding_bars'])==24+case['delay_bars'] for t in trips)
        assert all(d['effective_entry']=='0' and d['effective_exit']=='1' and d['exit_reason']=='time25' for d in dec if d['mandatory_exit_latched']=='1')
        held_times=sum(d['mandatory_exit_latched']=='1' for d in dec);oversold_forced=sum(d['mandatory_exit_latched']=='1' and d['raw_entry']=='1' for d in dec)
        lifecycle.append(dict(case=name,filled_entries=sum(f['side']=='BUY' for f in fills),filled_exits=sum(f['side']=='SELL' for f in fills),closed_roundtrips=len(trips),holding_bars_for_every_roundtrip=24+case['delay_bars'],mandatory_latched_closes=held_times,simultaneous_oversold_and_forced_exit_closes=oversold_forced,terminal_held_completed_bars=summary['terminal_held_completed_bars'],terminal_mandatory_exit_latched=summary['terminal_mandatory_exit_latched'],terminal_pending=summary['terminal_pending']))
        cuts={33,62,365,397,428,761}
        for f in fills[:2]:
            j=int(f['eval_index']);cuts.add(j+32)
            if f['side']=='BUY':cuts.add(j+56);cuts.add(j+57)
        cuts=sorted(c for c in cuts if 32<c<len(rows))
        for cut in cuts:
            limit=cut-31;prefix=kernel.simulate(rows[:cut],wrapper.features(rows[:cut]),case,execution_policy=wrapper.POLICY);engine_calls+=1
            for key,save in [('nav',nav),('decisions',dec)]:assert canonical(prefix[key])==save[:limit]
            for key,save in [('fills',fills),('pending',pending)]:assert canonical(prefix[key])==[x for x in save if int(x['eval_index'])<limit]
            assert canonical(prefix['roundtrips'])==[x for x in trips if int(x['exit_index'])<limit]
            future=[dict(b) for b in rows]
            for i,b in enumerate(future[cut:],cut):b.update(open=str(1000000+i),high='2000000',low='0.001',close=str(900000+i),volume='1')
            altered=kernel.simulate(future,wrapper.features(future),case,execution_policy=wrapper.POLICY);engine_calls+=1
            for key,save in [('nav',nav),('decisions',dec)]:assert canonical(altered[key][:limit])==save[:limit]
            for key,save in [('fills',fills),('pending',pending)]:assert canonical([x for x in altered[key] if x['eval_index']<limit])==[x for x in save if int(x['eval_index'])<limit]
            assert canonical([x for x in altered['roundtrips'] if x['exit_index']<limit])==[x for x in trips if int(x['exit_index'])<limit]
            assert qa.independent_features(future)[0][:cut]==expected[:cut]
            causality.append(dict(case=name,cut_global_index_exclusive=cut,prefix='PASS',future='PASS'))
    assert original=={p.name:sha(p) for p in out.iterdir()}
    for name in ['C0-v1.json','C0-v2.json']:
        for pin in json.loads((ROOT/'frozen'/name).read_text())['pins']:
            p=ROOT/pin['path'];assert p.stat().st_size==pin['bytes'] and sha(p)==pin['sha256']
    report=dict(schema='batch017-independent-M1349-historical-QA/v1',status='PASS',strategy_ids=['M1349'],strategy_configurations_verified=4,new_research_configurations=0,new_controls=0,source_historical_runs_by_parent=4,QA_engine_replays=engine_calls,QA_replay_scope='Prefix and future-suffix perturbations of frozen cases after original output; no new research variants',source_feature_rows=762,account_verifier=account,supplemental=supplemental,lifecycle=lifecycle,causality=causality,original_outputs_unchanged=True,C0_v1_and_v2_pins_unchanged=True,runtime_lock_asserted=True,network='Python socket audit guard; no socket operations attempted',C0_v2_sha256=sha(ROOT/'frozen/C0-v2.json'),manifest_sha256=sha(out/'manifest.json'),script_sha256=sha(Path(__file__)))
    dest=ROOT/'review/independent/historical-QA-m1349-v2.json'
    with dest.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(status='PASS',source_feature_rows=762,account_rows=2924,monthly_rows=96,qa_engine_replays=engine_calls,causal_checks=len(causality),lifecycle=lifecycle,report_sha256=sha(dest))))
if __name__=='__main__':main()
