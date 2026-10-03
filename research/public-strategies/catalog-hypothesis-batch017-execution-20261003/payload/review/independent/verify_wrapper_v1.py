"""Independent wrapper serialization and supplied account verifier on invented data."""
import csv, hashlib, importlib.util, json, os, sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'source'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_kernel_v2 as qa
import run_v1 as wrapper

def audit(event,args):
    if event.startswith('socket.'):raise RuntimeError('Network forbidden in independent synthetic QA')
sys.addaudithook(audit)
def read(p):
    with p.open(newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    kernel=wrapper.load_kernel(ROOT/'kernel/v1');kernel.environment(ROOT/'frozen/runtime-v1.json')
    independent=qa.load('target_account_verifier','kernel/v1/verify_account.py')
    results=[]
    for sid in ['M1346','M1270']:
        r=qa.rows()
        if sid=='M1346':
            for i,b in enumerate(r):b['open']=str(90+(i*7)%65);b['close']=str(80+(i*13)%90)
        rules=json.loads((ROOT/f'frozen/{sid}-root-frozen-rules.json').read_text())
        paths=[]
        for replicate in [1,2]:
            out=ROOT/f'review/independent/synthetic-wrapper-v1/{sid}/replica{replicate}'
            top=wrapper.produce(sid,r,rules,out,kernel);paths.append(out)
            expected=[dict(entry=bool(f['raw_entry']),exit=bool(f['raw_exit'])) for f in qa.own_flags(sid,r)]
            verified=independent.verify_account(r,out,dict(cases=rules['cost_cases']),expected)
            assert verified['status']=='PASS'
            assert top['strategy_configurations']==4 and top['new_controls']==0 and top['strict_reproductions']==0
            for case in rules['cost_cases']:
                name=case['name'];nav=read(out/f'{name}-nav.csv');dec=read(out/f'{name}-decisions.csv');events=read(out/f'{name}-pending.csv');fills=read(out/f'{name}-fills.csv');complete=read(out/f'{name}-fills-complete.csv');intent=read(out/f'{name}-intent-audit.csv')
                assert (out/f'{name}-nav.csv').read_bytes()==(out/f'{name}-daily-nav.csv').read_bytes()
                assert len(intent)==len(nav)==731 and len(complete)==len(fills)
                for j,a in enumerate(intent):
                    before=nav[j-1] if j>0 and nav[j-1]['pending_side'] and int(nav[j-1]['pending_due_index'])>j else None
                    assert a['pending_before_side']==('' if before is None else before['pending_side'])
                    assert a['pending_before_signal_index']==('' if before is None else before['pending_signal_index'])
                    assert a['pending_before_due_index']==('' if before is None else before['pending_due_index'])
                    for audit_key,nav_key in [('pending_after_side','pending_side'),('pending_after_signal_index','pending_signal_index'),('pending_after_due_index','pending_due_index')]:assert a[audit_key]==nav[j][nav_key]
                    assert a['close_events']==';'.join(e['event'] for e in events if e['eval_index']==str(j) and e['phase']=='CLOSE')
                    for key in ['eval_index','input_index','effective_time','raw_entry','raw_exit','held']:assert a[key]==dec[j][key]
                    assert a['ready'] in ['0','1']
                for f,full in zip(fills,complete):
                    assert {k:full[k] for k in f}==f
                    availability=kernel.iso(int(r[int(f['signal_index'])+31]['open_time'])+86400000)
                    assert full['signal_effective_time']==full['signal_available_time']==availability
                    assert full['signal_available_time']<=full['effective_time']
                for record in read(out/'features.csv'):
                    assert record['ready'] in ['0','1'] and record['raw_entry'] in ['0','1'] and record['raw_exit'] in ['0','1']
                # Exact immutable JSON/CSV conventions, including headers for zero-fill cases.
                for p in out.glob('*.csv'):
                    b=p.read_bytes();assert b'\r\n' in b and b.replace(b'\r\n',b'').find(b'\n')==-1
            results.append(dict(id=sid,replicate=replicate,account_verifier=verified,source_signal_actual='Independent direct Decimal50 close/lag strict comparison or UTC calendar; stock verifier label Fraction is not applicable',manifest_sha256=sha(out/'manifest.json'),file_count=len(list(out.iterdir()))))
        left={p.name:sha(p) for p in paths[0].iterdir()};right={p.name:sha(p) for p in paths[1].iterdir()};assert left==right
    try:wrapper.features('M1349',qa.rows())
    except ValueError:pass
    else:raise AssertionError('M1349 must remain gated in v1')
    report={'schema':'batch017-independent-wrapper-QA/v1','status':'PASS','historical_strategy_runs':0,'new_controls':0,'replicas_byte_exact':True,'socket_audit_guard':'Active, no socket operations attempted','runtime_lock_asserted':True,'results':results,'evidence_sha256':{p:sha(ROOT/p) for p in ['source/run_v1.py','source/daily_three_signals.py','source/timed_run.py','frozen/runtime-v1.json','kernel/v1/engine.py','kernel/v1/verify_account.py','kernel/v1/manifest.json','review/independent/verify_wrapper_v1.py']},'remaining_gate':'Literal root sell-fee operation versus accepted kernel Decimal exponent serialization must be explicitly reconciled before history'}
    dest=ROOT/'review/independent/wrapper-independent-v1.json'
    with dest.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(report))
if __name__=='__main__':main()
