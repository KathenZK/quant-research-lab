"""Post-C0 independent historical validation; replay calls are fixed-case QA only."""
import csv,datetime as dt,hashlib,importlib.util,json,math,sys
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'source'))
import run_v1 as wrapper

def network_guard(event,args):
    if event.startswith('socket.'):raise RuntimeError('Offline independent historical QA')
sys.addaudithook(network_guard)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with p.open(newline='') as f:return list(csv.DictReader(f))
def canonical(records):return [{k:str(v) for k,v in row.items()} for row in records]
def expected_features(sid,rows):
    result=[];flags=[]
    with localcontext() as c:
        c.prec=50;c.rounding=ROUND_HALF_EVEN
        for i,row in enumerate(rows):
            ms=int(row['open_time']);stamp=dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc);close=D(row['close']);lag=D(rows[i-25]['close']) if sid=='M1346' and i>=25 else None
            ready=sid=='M1270' or i>=25
            entry=close>lag if sid=='M1346' and ready else stamp.weekday()==6 if sid=='M1270' else False
            exit_=close<lag if sid=='M1346' and ready else stamp.weekday()==0 if sid=='M1270' else False
            result.append(dict(index=str(i),open_time=str(ms),bar_date=stamp.date().isoformat(),signal_available_ms=str(ms+86400000),weekday=str(stamp.weekday()),ready=str(int(ready)),close=str(close),lag25_close='' if lag is None else str(lag),roc25='',raw_entry=str(int(entry)),price_or_calendar_exit=str(int(exit_)),raw_exit=str(int(exit_))))
            flags.append(dict(entry=entry,exit=exit_))
    return result,flags

def literal_values(out,case):
    nav=read(out/f"{case['name']}-nav.csv");fills=read(out/f"{case['name']}-fills.csv");cash=D(100000);qty=D(0);fees=[];fields=0;representation_only=0
    with localcontext() as c:
        c.prec=50;c.rounding=ROUND_HALF_EVEN
        for j,n in enumerate(nav):
            for f in (f for f in fills if int(f['eval_index'])==j):
                cb,qb=cash,qty;rate=D(case['fee_bps_each_side']);slip=D(case['slippage_bps_each_side'])
                if f['side']=='BUY':
                    price=D(f['raw_open'])*(1+slip/10000);principal=cash/(1+rate/10000);fee=cash-principal;qty=principal/price;cash=D(0)
                else:
                    price=D(f['raw_open'])*(1-slip/10000);principal=qty*price;fee=principal*rate/10000;cash=cash+principal-fee;qty=D(0)
                for k,v in dict(fill_price=price,notional=principal,fee=fee,cash_before=cb,quantity_before=qb,cash_after=cash,quantity_after=qty).items():
                    assert D(f[k])==v,(case['name'],j,k);fields+=1;representation_only+=f[k]!=str(v)
                fees.append(fee)
            for k,v in dict(cash=cash,quantity=qty,equity=cash+qty*D(n['raw_close'])).items():
                assert D(n[k])==v,(case['name'],j,k);fields+=1;representation_only+=n[k]!=str(v)
        summary=json.loads((out/f"{case['name']}-summary.json").read_text());assert D(summary['total_fees'])==sum(fees,D(0));fields+=1
    return dict(exact_decimal_fields=fields,numerical_errors=0,representation_only_differences=representation_only)

def main():
    c0=wrapper.check_c0(ROOT,ROOT/'frozen/C0-v1.json')
    kernel=wrapper.load_kernel(ROOT/'kernel/v1');kernel.environment(ROOT/'frozen/runtime-v1.json')
    spec=importlib.util.spec_from_file_location('immutable_independent_verifier',ROOT/'kernel/v1/verify_account.py');verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    rows=read(ROOT/'input/input.csv');assert len(rows)==762 and sha(ROOT/'input/input.csv')==c0['input_sha256']
    results=[];causal=[];qa_engine_calls=0
    for sid in ['M1346','M1270']:
        out=ROOT/'results-v1'/sid;rules=json.loads((ROOT/f'frozen/{sid}-root-frozen-rules.json').read_text());expected,flags=expected_features(sid,rows)
        assert read(out/'features.csv')==expected
        verified=verifier.verify_account(rows,out,dict(cases=rules['cost_cases']),flags)
        verified['source_signal']='Independent exact Decimal50 strict close-vs-lag25 comparisons and UTC bar-open calendar, including ready mask; no kernel/adapter used for expected flags'
        original_manifests={p.name:sha(p) for p in out.iterdir()}
        feature_count=len(expected);literal=[]
        for case in rules['cost_cases']:
            name=case['name'];literal.append(dict(case=name,**literal_values(out,case)))
            nav=read(out/f'{name}-nav.csv');dec=read(out/f'{name}-decisions.csv');pending=read(out/f'{name}-pending.csv');fills=read(out/f'{name}-fills.csv');trips=read(out/f'{name}-roundtrips.csv');monthly=read(out/f'{name}-monthly.csv');audit=read(out/f'{name}-intent-audit.csv');enriched=read(out/f'{name}-fills-complete.csv');summary=json.loads((out/f'{name}-summary.json').read_text())
            assert (out/f'{name}-daily-nav.csv').read_bytes()==(out/f'{name}-nav.csv').read_bytes()
            assert len(audit)==731 and len(enriched)==len(fills)
            for j,a in enumerate(audit):
                prior=nav[j-1] if j>0 and nav[j-1]['pending_side'] and int(nav[j-1]['pending_due_index'])>j else None
                for suffix,navkey in [('side','pending_side'),('signal_index','pending_signal_index'),('due_index','pending_due_index')]:
                    assert a['pending_before_'+suffix]==('' if prior is None else prior[navkey]);assert a['pending_after_'+suffix]==nav[j][navkey]
                assert a['close_events']==';'.join(e['event'] for e in pending if e['eval_index']==str(j) and e['phase']=='CLOSE')
                for k in ['eval_index','input_index','effective_time','raw_entry','raw_exit','held']:assert a[k]==dec[j][k]
                assert a['ready']==expected[j+31]['ready']
            for f,e in zip(fills,enriched):
                assert {k:e[k] for k in f}==f
                available=kernel.iso(int(rows[31+int(f['signal_index'])]['open_time'])+86400000)
                assert e['signal_effective_time']==e['signal_available_time']==available and available<=e['effective_time']
            if sid=='M1270':
                if name=='delay2':
                    assert summary['fills']==summary['closed_roundtrips']==summary['exposure_fraction']==0 and summary['final_equity']==100000 and summary['total_return']==0 and summary['max_drawdown']==0 and summary['sharpe_zero_cash'] is None and summary['win_rate'] is None
                    assert summary['cancelled_intents']==summary['queued_intents']==105 and all(D(n['equity'])==100000 and D(n['quantity'])==0 for n in nav)
                    assert len(monthly)==24 and all(D(m['return'])==0 and m['buy_fills']==m['sell_fills']==m['days_long']=='0' for m in monthly)
                else:
                    assert summary['fills']==210 and summary['closed_roundtrips']==105 and summary['exposure_fraction']==105/731
                    assert all(dt.datetime.fromisoformat(f['effective_time'].replace('Z','+00:00')).weekday()==(0 if f['side']=='BUY' else 1) for f in fills)
            # Independent prefix/future replay of already-frozen cases; never a new research configuration.
            for cut in [33,56,62,365,397,428,761]:
                limit=cut-31;prefix=kernel.simulate(rows[:cut],wrapper.features(sid,rows[:cut]),case);qa_engine_calls+=1
                for key,save in [('nav',nav),('decisions',dec)]:assert canonical(prefix[key])==save[:limit]
                for key,save in [('fills',fills),('pending',pending)]:assert canonical(prefix[key])==[x for x in save if int(x['eval_index'])<limit]
                assert canonical(prefix['roundtrips'])==[x for x in trips if int(x['exit_index'])<limit]
                future=[dict(r) for r in rows]
                for i,bar in enumerate(future[cut:],cut):bar.update(open=str(1000000+i),high='2000000',low='0.001',close=str(900000+i),volume='1')
                changed=kernel.simulate(future,wrapper.features(sid,future),case);qa_engine_calls+=1
                for key,save in [('nav',nav),('decisions',dec)]:assert canonical(changed[key][:limit])==save[:limit]
                for key,save in [('fills',fills),('pending',pending)]:assert canonical([x for x in changed[key] if x['eval_index']<limit])==[x for x in save if int(x['eval_index'])<limit]
                assert canonical([x for x in changed['roundtrips'] if x['exit_index']<limit])==[x for x in trips if int(x['exit_index'])<limit]
                assert expected_features(sid,future)[0][:cut]==expected[:cut]
                causal.append(dict(id=sid,case=name,cut_global_index_exclusive=cut,prefix='PASS',future='PASS'))
        assert original_manifests=={p.name:sha(p) for p in out.iterdir()}
        results.append(dict(id=sid,source_feature_rows=feature_count,account_verifier=verified,literal_decimal_audits=literal,manifest_sha256=sha(out/'manifest.json'),all_results_unchanged=True))
    report=dict(schema='batch017-independent-historical-QA/v1',status='PASS',strategy_ids=['M1346','M1270'],strategy_configurations_verified=8,new_research_configurations=0,new_controls=0,source_historical_runs_by_parent=8,qa_engine_replays=qa_engine_calls,qa_replay_scope='Causal prefix and future-suffix perturbations of already frozen cases, not new research trials',causality=causal,results=results,C0_sha256=sha(ROOT/'frozen/C0-v1.json'),script_sha256=sha(Path(__file__)),runtime_lock_asserted=True,socket_audit_guard='active; no socket operations attempted',M1349_status='Not executed, pending v2')
    dest=ROOT/'review/independent/historical-QA-v1.json'
    with dest.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(status='PASS',strategy_ids=report['strategy_ids'],feature_rows=1524,account_rows=5848,monthly_rows=192,qa_engine_replays=qa_engine_calls,causal_checks=len(causal),report_sha256=sha(dest))))
if __name__=='__main__':main()
