"""Consumer-specific M1349 full synthetic serialization/ledger QA; no market reads."""
import csv,datetime as dt,hashlib,importlib.util,json,sys
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'source'));sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_m1349_v2 as wrapper
import test_m1349_kernel_v2 as qa
import verify_history_v1 as literal_qa

def guard(event,args):
    if event.startswith('socket.'):raise RuntimeError('No network in M1349 synthetic QA')
sys.addaudithook(guard)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with p.open(newline='') as f:return list(csv.DictReader(f))
def independent_features(r):
    rows=[];expected=[]
    with localcontext() as c:
        c.prec=50;c.rounding=ROUND_HALF_EVEN
        for i,b in enumerate(r):
            close=D(b['close']);lag=D(r[i-25]['close']) if i>=25 else None;roc=close/lag-1 if lag is not None else None;ready=i>=25;entry=roc<D('-0.10') if ready else False;ms=int(b['open_time']);stamp=dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc)
            expected.append(dict(entry=entry,exit=False))
            rows.append(dict(index=str(i),open_time=str(ms),bar_date=stamp.date().isoformat(),signal_available_ms=str(ms+86400000),weekday=str(stamp.weekday()),ready=str(int(ready)),close=str(close),lag25_close='' if lag is None else str(lag),roc25='' if roc is None else str(roc),raw_entry=str(int(entry)),price_or_calendar_exit='0',raw_exit='0'))
    return rows,expected

def audit_supplemental(out,rows,feature_rows,kernel,cases):
    literal=[];lifecycle_rows=0
    for case in cases:
        name=case['name'];nav=read(out/f'{name}-nav.csv');dec=read(out/f'{name}-decisions.csv');events=read(out/f'{name}-pending.csv');fills=read(out/f'{name}-fills.csv');complete=read(out/f'{name}-fills-complete.csv');audit=read(out/f'{name}-intent-audit.csv')
        assert (out/f'{name}-nav.csv').read_bytes()==(out/f'{name}-daily-nav.csv').read_bytes()
        assert len(nav)==len(dec)==len(audit)==731 and len(fills)==len(complete)
        buy_at=None;by_day={int(f['eval_index']):f for f in fills};assert len(by_day)==len(fills)
        for j,(n,d,a) in enumerate(zip(nav,dec,audit)):
            if j in by_day:buy_at=j if by_day[j]['side']=='BUY' else None
            held=j-buy_at+1 if buy_at is not None else 0;trigger=buy_at+24 if held>=25 else None
            assert n['held_completed_bars']==str(held) and n['mandatory_exit_latched']==str(int(held>=25)) and n['mandatory_exit_trigger_index']==('' if trigger is None else str(trigger))
            for key in ['eval_index','input_index','effective_time','raw_entry','raw_exit','held','held_completed_bars','mandatory_exit_latched','mandatory_exit_trigger_index','effective_entry','effective_exit']:assert a[key]==d[key]
            prior=nav[j-1] if j>0 and nav[j-1]['pending_side'] and int(nav[j-1]['pending_due_index'])>j else None
            for suffix,key in [('side','pending_side'),('signal_index','pending_signal_index'),('due_index','pending_due_index')]:
                assert a['pending_before_'+suffix]==('' if prior is None else prior[key]);assert a['pending_after_'+suffix]==n[key]
            assert a['close_events']==';'.join(e['event'] for e in events if e['eval_index']==str(j) and e['phase']=='CLOSE')
            assert a['reason']==('time25' if held>=25 else 'roc25_below_minus10' if d['raw_entry']=='1' else 'no_event')
            assert a['ready']==feature_rows[j+31]['ready'];lifecycle_rows+=1
        for f,e in zip(fills,complete):
            assert {k:e[k] for k in f}==f
            availability=kernel.iso(int(rows[31+int(f['signal_index'])]['open_time'])+86400000)
            assert e['signal_effective_time']==e['signal_available_time']==availability and availability<=e['effective_time']
            assert e['entry_or_exit_reason']==('time25' if f['side']=='SELL' else 'roc25_below_minus10')
            if f['side']=='SELL':
                trigger=dec[int(f['signal_index'])];assert trigger['mandatory_exit_latched']=='1' and trigger['held_completed_bars']=='25' and trigger['raw_exit']=='0'
        literal.append(dict(case=name,**literal_qa.literal_values(out,case)))
    return dict(lifecycle_rows=lifecycle_rows,literal_decimal_audits=literal)

def main():
    kernel=wrapper.load_kernel(ROOT/'kernel/v2');kernel.environment(ROOT/'frozen/runtime-v1.json');rules=json.loads((ROOT/'frozen/M1349-root-frozen-rules.json').read_text())
    spec=importlib.util.spec_from_file_location('v2_independent_account',ROOT/'kernel/v2/verify_account.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    r=qa.persistent(762);expected_rows,flags=independent_features(r);receipts=[];replicas=[]
    for replicate in [1,2]:
        out=ROOT/f'review/independent/synthetic-M1349-wrapper-v2/replica{replicate}';top=wrapper.produce(r,rules,out,kernel);assert top['execution_policy']=={'max_completed_closes':25}
        assert read(out/'features.csv')==expected_rows
        result=v.verify_account(r,out,dict(cases=rules['cost_cases']),flags,execution_policy=wrapper.POLICY)
        result['source_signal']='Independent exact Decimal50 ROC25 from invented closes; raw_exit always zero, no shadow position state'
        extra=audit_supplemental(out,r,expected_rows,kernel,rules['cost_cases'])
        for f in out.glob('*.csv'):
            b=f.read_bytes();assert b'\r\n' in b and b.replace(b'\r\n',b'').find(b'\n')==-1
        replicas.append({f.name:sha(f) for f in out.iterdir()});receipts.append(dict(replicate=replicate,file_count=len(list(out.iterdir())),manifest_sha256=sha(out/'manifest.json'),account_verifier=result,**extra))
    assert replicas[0]==replicas[1]
    report=dict(schema='M1349-independent-consumer-v2-synthetic/v1',status='PASS',M1349_historical_runs=0,new_controls=0,byte_exact_replicas=True,runtime_lock_asserted=True,network='Python socket audit guard; no socket attempts',results=receipts,pins={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'source/run_m1349_v2.py',ROOT/'source/daily_three_signals.py',ROOT/'kernel/v2/engine.py',ROOT/'kernel/v2/verify_account.py',ROOT/'kernel/v2/manifest.json',ROOT/'frozen/runtime-v1.json',Path(__file__)]})
    dest=ROOT/'review/independent/M1349-wrapper-v2-v1.json'
    with dest.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(status='PASS',replicas=2,source_rows_checked=1524,account_lifecycle_rows_checked=5848,monthly_rows=192,files_each=43,report_sha256=sha(dest))))
if __name__=='__main__':main()
