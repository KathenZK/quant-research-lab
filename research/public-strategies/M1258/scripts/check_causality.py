"""Read frozen actual input only after C0: prefix/future mutation; no new configurations."""
import argparse,copy,json
from pathlib import Path
from run_replay import FAMILY,load_input,features,simulate,dump,environment

def check(path):
    environment();p=json.loads((FAMILY/'specs/protocol-v1.json').read_text());rows=load_input(path,p);full=features(rows);tested=[]
    for cut in [31,32,36,100,365,700,761]:
        assert features(rows[:cut])==full[:cut]
        changed=copy.deepcopy(rows)
        for row in changed[cut:]:row['close']='12345.6789'
        assert features(changed)[:cut]==full[:cut];tested.append(cut)
    for case in p['cases']:
        complete=simulate(rows,full,case)
        for cut in [36,100,365,700,761]:
            prefix=simulate(rows[:cut],full[:cut],case)
            n=cut-31
            for key in ['nav','decisions']:assert prefix[key]==complete[key][:n]
            for key in ['fills','pending']:assert prefix[key]==[x for x in complete[key] if x['eval_index']<n]
    return dict(status='PASS',feature_prefixes=tested,account_prefixes=[36,100,365,700,761],existing_configurations=4,new_trials=0,new_controls=0,future_mutation=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=check(a.input);dump(a.output,r);print(json.dumps(r))
