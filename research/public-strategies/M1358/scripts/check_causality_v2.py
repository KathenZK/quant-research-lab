"""Post-C0 prefix/future perturbation QA; not new parameter trials."""
import argparse,json
from pathlib import Path
from run_replay_v2 import FAMILY,load_input,features,run,CASES

def verify(path):
    f=load_input(path,json.loads((FAMILY/'specs/protocol-v1.json').read_text()));fs=features(f);checks=[]
    for name,fee,lag in CASES:
        whole=run(f,fee,lag,name)
        for cut in (47,48,49,150,500,730):
            prefix=run(f.iloc[:cut],fee,lag,name)
            for key in ('nav','decisions'):
                assert prefix[key]==whole[key][:cut],(name,cut,key)
            assert prefix['fills']==[r for r in whole['fills'] if r['bar_index']<cut]
            assert prefix['pending']==[r for r in whole['pending'] if r['event_bar_index']<cut]
            assert features(f.iloc[:cut])==fs[:cut]
            checks.append({'case':name,'cut':cut,'status':'PASS'})
        changed=f.copy();changed.loc[500:,'close']*=3;changed.loc[500:,'open']*=4;changed.loc[500:,'close_decimal']=[str(x) for x in changed.loc[500:,'close']]
        future=run(changed,fee,lag,name)
        assert future['nav'][:500]==whole['nav'][:500]
        checks.append({'case':name,'future_perturbation_after':500,'status':'PASS'})
    return {'status':'PASS','checks':checks,'new_parameter_trials':0,'purpose':'causal QA of already frozen configurations'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    with a.report.open('x') as h:h.write(json.dumps(verify(a.input),indent=2)+'\n')
    print('causal prefix/future perturbation PASS')
