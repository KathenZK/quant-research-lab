"""Synthetic prehistory, or authorized later historical, causal-prefix verification."""
import argparse,json
from pathlib import Path
from kernel_loader import FAMILY,load
from signals import features
from oracle import verify_features
engine=load('engine');account_qa=load('verify_account')

def synthetic_rows():
    prices=[str(150 if i%30==20 else 80 if i%30==21 else 100) for i in range(762)]
    return [dict(open_time=str(1669852800000+i*86400000),close_time=str(1669852800000+(i+1)*86400000-1),open=p,high=p,low=p,close=p,volume='0',trade_count='0') for i,p in enumerate(prices)]

def check(rows,fixture_dir):
    spec=json.loads((FAMILY/'specs/protocol-v1.json').read_text());feat=features(rows);expected=verify_features(rows,feat);checks=[]
    assert not fixture_dir.exists();fixture_dir.mkdir(parents=True)
    engine.csvout(fixture_dir/'features.csv',feat,list(feat[0]));summaries=[]
    for case in spec['cases']:
        baseline=engine.simulate(rows,feat,case);summaries.append(baseline['summary'])
        for name,columns in [('nav',engine.NAV),('fills',engine.FILL),('pending',engine.EVENT),('decisions',engine.DEC),('monthly',engine.MONTH),('roundtrips',engine.TRIP)]:engine.csvout(fixture_dir/f"{case['name']}-{name}.csv",baseline[name],columns)
        engine.dump(fixture_dir/f"{case['name']}-summary.json",baseline['summary'])
        for cut in [32,40,65,366,600,761]:
            prefix=engine.simulate(rows[:cut],features(rows[:cut]),case)
            limit=cut-31
            for key in ['nav','decisions']:
                assert prefix[key]==baseline[key][:limit]
            for key in ['fills','pending']:
                assert prefix[key]==[r for r in baseline[key] if r['eval_index']<limit]
            assert prefix['roundtrips']==[r for r in baseline['roundtrips'] if r['exit_index']<limit]
            changed=[dict(r) for r in rows]
            for r in changed[cut:]:
                for field in ['open','high','low','close']:r[field]='321'
            future=engine.simulate(changed,features(changed),case)
            for key in ['nav','decisions']:
                assert future[key][:limit]==baseline[key][:limit]
            for key in ['fills','pending']:
                assert [r for r in future[key] if r['eval_index']<limit]==[r for r in baseline[key] if r['eval_index']<limit]
            checks.append(case['name']+' prefix+future@'+str(cut))
    engine.dump(fixture_dir/'summary.json',dict(cases=summaries,strategy_configurations=4,new_controls=0,strict_reproductions=0))
    engine.dump(fixture_dir/'manifest.json',[dict(path=p.name,bytes=p.stat().st_size,sha256=engine.sha(p)) for p in sorted(fixture_dir.iterdir())])
    receipt=account_qa.verify_account(rows,fixture_dir,spec,expected)
    assert receipt['fill_rows']>0,'Trade fixture must exercise fills'
    return dict(status='PASS',checks=len(checks),tests=checks,independent_account=receipt,no_results_used_for_selection=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--synthetic',action='store_true');p.add_argument('--input',type=Path);p.add_argument('--root-gate',type=Path);p.add_argument('--fixture-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    engine.environment(FAMILY/'specs/environment-lock.json')
    assert a.synthetic != (a.input is not None)
    if a.synthetic:rows=synthetic_rows()
    else:
        from run_replay import check_gate
        check_gate(a.root_gate);rows=engine.load_input(a.input,json.loads((FAMILY/'specs/protocol-v1.json').read_text()))
    r=check(rows,a.fixture_dir);r['synthetic_only']=a.synthetic;r['new_history_strategy_configurations']=0;r['new_controls']=0
    engine.dump(a.output,r);print(json.dumps(r))
