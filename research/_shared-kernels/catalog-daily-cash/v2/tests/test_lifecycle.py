"""Synthetic-only v2 lifecycle and byte-compatible default regression suite."""
import argparse
import csv
import io
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]

def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

engine=module(HERE/'engine.py','cash_v2_engine')
v1=module(HERE.parent/'v1/engine.py','cash_v1_engine')
verify=module(HERE/'verify_account.py','cash_v2_verifier')
POLICY={'max_completed_closes':25}
CASES=[dict(name=name,fee_bps_each_side=fee,slippage_bps_each_side=2,delay_bars=delay) for name,fee,delay in [('base',8,1),('fee0',0,1),('fee20',20,1),('delay2',8,2)]]

def bars(n,constant=False):
    return [dict(open_time=str(1669852800000+i*86400000),close_time=str(1669852800000+(i+1)*86400000-1),open=str(100 if constant else 100+i%9),high=str(110),low=str(90),close=str(100 if constant else 101+i%7)) for i in range(n)]

def flags(n,buys=(),sells=()):
    return [dict(raw_entry=int(i in buys),raw_exit=int(i in sells)) for i in range(n)]

def expect_error(fn):
    try:fn()
    except (ValueError,AssertionError,KeyError):return
    raise AssertionError('Invalid policy unexpectedly accepted')

def save(out,result,cases_summary=None,prefix=None):
    for name in ['nav','fills','pending','decisions','monthly','roundtrips']:
        engine.csvout(out/f'{prefix}-{name}.csv',result[name],engine.output_columns(name,POLICY))
    engine.dump(out/f'{prefix}-summary.json',result['summary'])


def check():
    tests=[]
    def passed(name):tests.append(name)
    for wrong in [{},{'unknown':25},{'max_completed_closes':0},{'max_completed_closes':-1},{'max_completed_closes':True},{'max_completed_closes':25.0},{'max_completed_closes':'25'},[],{'max_completed_closes':25,'extra':1}]:
        expect_error(lambda:engine.simulate(bars(5),flags(5),CASES[0],start=0,execution_policy=wrong))
    passed('9 malformed execution policies rejected before execution')
    for c in CASES:
        for pattern in [flags(90),flags(90,[0]),flags(90,range(90)),flags(90,range(0,90,3),range(1,90,5)),flags(90,[0,1,2,6],[1,5,6])]:
            rows=bars(90);before=json.dumps(pattern);a=v1.simulate(rows,pattern,c,start=0);b=engine.simulate(rows,pattern,c,start=0)
            assert json.dumps(a,separators=(',',':'))==json.dumps(b,separators=(',',':'))
            assert json.dumps(pattern)==before
            for name,columns in [('nav',v1.NAV),('fills',v1.FILL),('pending',v1.EVENT),('decisions',v1.DEC),('monthly',v1.MONTH),('roundtrips',v1.TRIP)]:
                assert engine.output_columns(name)==columns
                buffers=[]
                for result in [a,b]:
                    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader();writer.writerows(result[name]);buffers.append(stream.getvalue().encode())
                assert buffers[0]==buffers[1]
        passed('Default v1 JSON+6CSV+metrics byte equality '+c['name'])
    for lag in [1,2]:
        c=dict(CASES[0],delay_bars=lag)
        a=engine.simulate(bars(65),flags(65,[0]),c,start=0,execution_policy=POLICY)
        buy,sell=a['fills'];e=lag
        assert buy['eval_index']==e and sell['eval_index']==e+24+lag
        assert a['nav'][e]['held_completed_bars']==1 and a['nav'][e+23]['held_completed_bars']==24
        assert a['nav'][e+24]['held_completed_bars']==25 and a['nav'][e+24]['mandatory_exit_latched']==1
        assert a['nav'][e+24]['mandatory_exit_trigger_index']==e+24
        assert a['decisions'][e+24]['raw_exit']==0 and a['decisions'][e+24]['effective_exit']==1 and a['decisions'][e+24]['exit_reason']=='time25'
        assert a['nav'][sell['eval_index']]['held_completed_bars']==0 and not a['nav'][sell['eval_index']]['mandatory_exit_latched']
        assert a['roundtrips'][0]['holding_bars']==24+lag
        passed('Actual entrybar close1 trigger25 fill e+'+str(24+lag))
        a=engine.simulate(bars(65),flags(65,range(65)),c,start=0,execution_policy=POLICY)
        firstbuy,firstsell,nextbuy=a['fills'][:3]
        assert firstbuy['eval_index']==e and firstsell['eval_index']==e+24+lag
        assert nextbuy['eval_index']==firstsell['eval_index']+lag
        assert a['nav'][nextbuy['eval_index']]['held_completed_bars']==1
        assert a['decisions'][e+24]['raw_entry']==1 and a['decisions'][e+24]['effective_entry']==0
        assert all(x['event']!='CANCELLED_OPPOSITE' for x in a['pending'] if e+24<=x['eval_index']<=e+24+lag)
        assert len({x['eval_index'] for x in a['fills']})==len(a['fills'])
        passed('Oversold level never resets clock, cannot cancel sell, nextclose reentry lag'+str(lag))
        for last in [e+23,e+24,e+24+lag-1]:
            a=engine.simulate(bars(last+1),flags(last+1,[0]),c,start=0,execution_policy=POLICY)
            assert len(a['fills'])==1 and a['summary']['final_quantity']!='0'
            assert a['summary']['terminal_held_completed_bars']==last-e+1
            if last<e+24:assert a['summary']['terminal_pending'] is None and not a['summary']['terminal_mandatory_exit_latched']
            else:assert a['summary']['terminal_pending']['due_index']==e+24+lag and a['summary']['terminal_mandatory_exit_latched']
        passed('No out-of-window liquidation before trigger or pendingdue lag'+str(lag))
    # Lag2 buy persists when its raw oversold condition disappears; no shadow clock.
    a=engine.simulate(bars(40),flags(40,[0]),CASES[-1],start=0,execution_policy=POLICY)
    assert a['nav'][0]['held_completed_bars']==a['nav'][1]['held_completed_bars']==0
    assert a['fills'][0]['eval_index']==2 and a['nav'][2]['held_completed_bars']==1
    assert a['nav'][27]['held_completed_bars']==26 and a['nav'][27]['mandatory_exit_trigger_index']==26
    assert a['nav'][27]['pending_due_index']==28
    passed('Pending buy does not start clock; absent rawentry retains buy; latch due retained')
    a=engine.simulate(bars(40),flags(40,[0],[1]),CASES[-1],start=0,execution_policy=POLICY)
    assert not a['fills'] and all(r['held_completed_bars']==0 for r in a['nav'])
    passed('Cancelled unfilled buy never starts timer')
    a=engine.simulate(bars(70),flags(70,[0,7],[5]),CASES[0],start=0,execution_policy=POLICY)
    assert [(x['side'],x['eval_index']) for x in a['fills']]==[('BUY',1),('SELL',6),('BUY',8),('SELL',33)]
    passed('Optional earlier raw exit resets actual lifecycle for next actual buy')
    a=engine.simulate(bars(35),flags(35,[30,31]),CASES[0],execution_policy=POLICY)
    assert a['fills'][0]['eval_index']==1 and a['nav'][0]['held_completed_bars']==0
    passed('Warmup signals cannot initialize holdings or count')
    a=engine.simulate(bars(10),flags(10,[0]),CASES[-1],start=0,execution_policy={'max_completed_closes':1})
    assert [(x['side'],x['eval_index']) for x in a['fills']]==[('BUY',2),('SELL',4)]
    passed('Explicit positive limit1 boundary counts actual buy close')
    for c in CASES:
        rows=bars(762);f=flags(762,range(762));full=engine.simulate(rows,f,c,execution_policy=POLICY)
        for cut in [33,55,56,57,58,62,100,365,761]:
            prefix=engine.simulate(rows[:cut],f[:cut],c,execution_policy=POLICY);n=cut-31
            for key in ['nav','decisions']:assert prefix[key]==full[key][:n]
            for key in ['fills','pending']:assert prefix[key]==[r for r in full[key] if r['eval_index']<n]
            mutated=[dict(r) for r in rows]
            for row in mutated[cut:]:row.update(open='999',close='999')
            alt=engine.simulate(mutated,f,c,execution_policy=POLICY)
            assert alt['nav'][:n]==full['nav'][:n] and alt['decisions'][:n]==full['decisions'][:n]
        passed('Lifecycle prefix/future independence nine cuts '+c['name'])
    # Exact 731day account/metadata/statistics cross-check; no real price data.
    with tempfile.TemporaryDirectory(prefix='cash-v2-synthetic-') as tmp:
        out=Path(tmp);rows=bars(762);f=flags(762,range(762));summaries=[]
        for c in CASES:
            a=engine.simulate(rows,f,c,execution_policy=POLICY);save(out,a,prefix=c['name']);summaries.append(a['summary'])
        engine.dump(out/'summary.json',dict(cases=summaries,strategy_configurations=4,new_controls=0,strict_reproductions=0))
        engine.dump(out/'manifest.json',[dict(path=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(out.iterdir())])
        expected=[dict(entry=True,exit=False) for _ in rows]
        qa=verify.verify_account(rows,out,dict(cases=CASES),expected,execution_policy=POLICY)
        assert qa['nav_rows']==2924 and qa['fill_rows']>0
        passed('Independent verifier exact all states/decisions/events/roundtrips/months/metrics')
        # Tamper only the lifecycle column. Independent verifier must reject.
        path=out/'base-nav.csv';content=path.read_bytes();lines=content.splitlines(keepends=True);index=lines[0].decode().strip().split(',').index('held_completed_bars')
        cells=lines[2].decode().strip().split(',');cells[index]='999';lines[2]=(','.join(cells)+'\r\n').encode();path.write_bytes(b''.join(lines))
        expect_error(lambda:verify.verify_account(rows,out,dict(cases=CASES),expected,execution_policy=POLICY))
        passed('Independent verifier detects corrupted timer serialization')
    return dict(status='PASS',checks=len(tests),tests=tests,independent_full_account=qa,historical_runs=0,market_requests=0,new_strategy_trials=0,new_controls=0,policy=POLICY,v1_default_byte_equivalence_cases=20)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=check()
    with a.output.open('x') as h:json.dump(r,h,ensure_ascii=False,indent=2);h.write('\n')
    print(json.dumps(r))
