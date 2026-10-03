#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse,json,pathlib,hashlib
import pandas as pd,numpy as np
from run_replay import replay,features,load_input,ROOT,write,sha
p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--work',required=True);p.add_argument('--output',required=True);a=p.parse_args();s=json.loads((ROOT/'specs/protocol.json').read_text());d=load_input(a.input,s);w=pathlib.Path(a.work);results=[]
for case in s['cases']:
    full=pd.read_csv(w/(case['name']+'-nav.csv'))
    ft=pd.read_csv(w/(case['name']+'-trades.csv'))
    for cut in [300,678,679,680,1000,2000,3000,4000,4571]:
        n,_,t,_,_=replay(features(d.iloc[:cut].copy()),s,case);ref=full[full.bar_index<cut]
        assert np.allclose(n[['cash','quantity','equity']],ref[['cash','quantity','equity']],rtol=0,atol=1e-8)
        assert len(t)==len(ft[ft.bar_index<cut]);results.append({'case':case['name'],'cut':cut,'rows':len(n),'fill_events':len(t)})
write(a.output,{'status':'PASS_PREFIX_REPLAY','checks':results,'protocol_sha256':sha(ROOT/'specs/protocol.json'),'real_historical_prefix_replays':len(results),'new_parameter_searches':0,'same_frozen_cases':True})
