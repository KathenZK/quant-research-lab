"""Only generated fixtures. Production API retains original immutable price hashes."""
if not __debug__:
    raise RuntimeError('M3710 rejects Python -O')
import argparse
import copy
import csv
import dataclasses
import hashlib
import io
import json
from decimal import Decimal as D,localcontext,ROUND_HALF_EVEN
from pathlib import Path
import dependencies
from gates import protocol,disk_reserve
from signals import features
from oracle import verify_features
from run_replay import write_results
from verify_replay import verify_view

DAY=86400000
START=1663891200000


def fixture_rows(prices):
    rows=[]
    for i,p in enumerate(prices):
        price=str(p);ms=START+i*DAY
        rows.append(dict(zip(['open_time','open','high','low','close','volume','close_time',
            'quote_volume','trade_count','taker_base','taker_quote','ignore'],
            [str(ms),price,price,price,price,'1',str(ms+DAY-1),price,'1','0','0','0'])))
    return rows


def encode(rows,cols):
    s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=cols);w.writeheader();w.writerows(rows)
    return s.getvalue().encode()


def artificial_view(a,rows):
    body=encode(rows,a.COLS);view=encode(rows[69:],a.COLS)
    p=dataclasses.replace(a.PROFILES['warmup100'],size=len(body),sha256=hashlib.sha256(body).hexdigest(),
        view_size=len(view),view_sha256=hashlib.sha256(view).hexdigest())
    # Only this synthetic test calls the structural helper with explicitly synthetic byte pins.
    # Production load_input accepts only its original fixed canonical hashes.
    return a._validate_input(body,p)


def check(destination):
    disk_reserve(destination);assert not destination.exists();destination.mkdir(parents=True)
    a=dependencies.adapter();e=dependencies.engine();e.environment(dependencies.FAMILY/'specs/environment-lock.json')
    spec=protocol();checks=[]
    def passed(text):checks.append(text)
    prices=[str(100+i) for i in range(100)]+['210','211','50','49']
    prices += [str(120+(i%40 if (i//40)%2==0 else 40-i%40)) for i in range(727)]
    assert len(prices)==831
    rows=fixture_rows(prices);iv=artificial_view(a,rows)
    try:a.load_input(encode(rows,a.COLS),'warmup100')
    except ValueError:passed('production immutable input hash rejects artificial data')
    else:raise AssertionError('production input accepted synthetic fixture')
    full=features(iv.full_rows);expected=verify_features(iv.full_rows,full)
    aligned=a.align_features(iv,full,required_ready_fields=('sma20',))
    assert [dict(x) for x in aligned.view_features]==full[69:]
    assert full[100]['raw_entry']==full[99]['raw_entry']==1
    assert a.map_index('warmup100',31,'view')==dict(canonical_index=100,view_index=31,eval_index=0)
    passed('full831 then slice69 / firsteval100 == view31 / state not crossing')
    for constant in ['0.1','0.3','10','100']:
        c_iv=artificial_view(a,fixture_rows([constant]*831))
        c_f=a.align_features(c_iv,features(c_iv.full_rows),required_ready_fields=('sma20',))
        for case in spec['cases']:
            result=e.simulate(c_iv.view_rows,c_f.view_features,case)
            assert not result['fills'] and all(D(x['equity'])==100000 for x in result['nav'])
            assert result['summary']['sharpe_zero_cash'] is None and result['summary']['terminal_pending'] is None
        passed('constant'+constant+' equality/cash/zero trades/null Sharpe in4cases')
    cuts=[101,102,103,104,105,120,200,400,830]
    for case in spec['cases']:
        result=e.simulate(iv.view_rows,aligned.view_features,case)
        lag=case['delay_bars']
        assert result['fills'][0]['signal_index']==0 and result['fills'][0]['eval_index']==lag
        assert result['fills'][0]['input_index']==31+lag
        assert all(D(x['quantity'])==0 for x in result['nav'][:lag])
        assert len(result['nav'])==731 and len(result['monthly'])==24
        assert result['summary']['observations']==731
        passed(case['name']+' coldflat/firststate lag/whole731/24months')
        for cut in cuts:
            pf=features(rows[:cut]);assert pf==full[:cut]
            short=e.simulate(rows[69:cut],pf[69:],case)
            future=copy.deepcopy(rows)
            for r in future[cut:]:
                for field in ['open','high','low','close']:r[field]='999'
            ff=features(future);assert ff[:cut]==full[:cut]
            changed=e.simulate(future[69:],ff[69:],case)
            n=cut-100
            for key in ['nav','decisions']:
                assert short[key]==result[key][:n]==changed[key][:n]
            for key in ['fills','pending','roundtrips']:
                idx='exit_index' if key=='roundtrips' else 'eval_index'
                assert short[key]==[x for x in result[key] if x[idx]<n]==[x for x in changed[key] if x[idx]<n]
            passed(case['name']+' account prefix/future '+str(cut))
        terminal=e.simulate(rows[69:101],features(rows[:101])[69:],case)
        assert not terminal['fills'] and terminal['summary']['terminal_pending']==dict(side='BUY',signal_index=0,due_index=lag)
        passed(case['name']+' terminal signal retained/no unobserved fill')
    # Direct immutable pending-state boundary checks, not new strategy configurations.
    p=dict(side='BUY',signal_index=0,due_index=2)
    assert e.reconcile(p,True,False,False,1,2)[0]==p
    assert e.reconcile(p,False,False,False,1,2)==(p,[])
    assert e.reconcile(p,False,True,False,1,2)[0] is None
    sell=dict(side='SELL',signal_index=0,due_index=2)
    assert e.reconcile(sell,True,False,True,1,2)[0] is None
    assert e.reconcile(p,True,True,False,1,2)[0] is None
    passed('lag2 duplicate earliest/absent holds/opposite before position/both exit priority')
    for initial in [D('100000'),D('1e-100'),D('1e-400')]:
        for fee in [0,8,20]:
            cash,qty,fill=e.fill_order(initial,D(0),'103.1','BUY',fee,2)
            with localcontext() as ctx:
                ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
                assert cash==0 and D(fill['notional'])+D(fill['fee'])==initial
                assert D(fill['quantity_after'])==D(fill['notional'])/D(fill['fill_price'])>0
            passed('exact feeinclusive no epsilon '+str(initial)+' fee'+str(fee))
    result_dir=destination/'artificial-results'
    write_results(iv,result_dir,spec,synthetic_only=True)
    receipt=verify_view(iv,result_dir,spec)
    assert receipt['nav_rows']==2924 and receipt['monthly_rows']==96
    passed('37 payload serializer + independent Fraction/Decimal/metrics/maps complete')
    # A second deterministic directory for synthetic-only serialization reproducibility.
    second=destination/'artificial-results-second'
    write_results(iv,second,spec,synthetic_only=True)
    assert {p.name for p in second.iterdir()}=={p.name for p in result_dir.iterdir()}
    for p in result_dir.iterdir():assert p.read_bytes()==(second/p.name).read_bytes()
    passed('synthetic sameimplementation all38files exact bytes')
    return dict(id='M3710',status='PASS',checks=len(checks),tests=checks,synthetic_only=True,
        historical_input_read=False,historical_features=0,historical_strategy_configurations=0,
        new_controls=0,market_requests=0,independent_account=receipt,
        disclosure='Synthetic account fixtures are validation only, not research trials. Onebar prefix metrics may emit frozen numpy ddof1 warnings; no kernel modification.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fixture-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--synthetic-dependency-root',type=Path,help='Explicit read-only pinned dependency tree for artificial tests only; never a production override')
    a=p.parse_args()
    if a.synthetic_dependency_root is not None:dependencies.ROOT=a.synthetic_dependency_root.resolve()
    r=check(a.fixture_dir)
    with a.output.open('x') as h:json.dump(r,h,ensure_ascii=False,indent=2,allow_nan=False);h.write('\n')
    print(json.dumps(dict(status=r['status'],checks=r['checks'],synthetic_only=True)))
