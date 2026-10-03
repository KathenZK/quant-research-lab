#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse,json,pathlib
import numpy as np,pandas as pd
from run_replay import features,load_input,replay,sha,write
ROOT=pathlib.Path(__file__).resolve().parents[1]
def check(input_path,spec_path):
    spec=json.loads(pathlib.Path(spec_path).read_text());d=load_input(input_path,spec);full=features(d)
    cuts=[300,500,680,682,683,684,1000,2000,3000,4000,4572];details={}
    for case in spec['cases']:
        n,dy,t,m,e=replay(full,spec,case)
        for cut in cuts:
            short=features(d.iloc[:cut].copy());nn,dd,tt,mm,ee=replay(short,spec,case)
            pd.testing.assert_frame_equal(nn.reset_index(drop=True),n.iloc[:len(nn)].reset_index(drop=True),check_exact=True)
            if len(tt):pd.testing.assert_frame_equal(tt.reset_index(drop=True),t[t.bar_index<cut].reset_index(drop=True),check_exact=True)
            else:assert not len(t[t.bar_index<cut])
        details[case['name']]={'prefixes':len(cuts),'nav_and_fills_exact':True}
    return {'status':'PASS','input_sha256':sha(input_path),'protocol_sha256':sha(spec_path),'cuts':cuts,'cases':details,'full_results_used_as_reference':True,'no_refitting_or_parameter_changes':True}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--spec',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=check(a.input,a.spec);write(a.output,r);print(json.dumps(r,indent=2))
