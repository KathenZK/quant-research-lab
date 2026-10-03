#!/usr/bin/env python3
"""Future perturbation checks, does import the frozen primary implementation.
Independent indicator/ledger validation lives in validate_independent.py instead.
GPL-3.0-or-later; authored 2026-10-03.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from replay import load_data,load_qtp,indicators,simulate,CASES

CUTS=['2023-01-02T00:00:00Z','2023-03-15T13:00:00Z','2023-06-04T23:00:00Z',
      '2023-12-31T23:00:00Z','2024-01-01T00:00:00Z','2024-06-12T11:00:00Z',
      '2024-09-02T00:00:00Z','2024-12-31T13:00:00Z']

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--qtpylib',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    d=load_data(a.input);q=load_qtp(a.qtpylib);s=indicators(d,q)
    base={name:simulate(d,s,fee,lag,bh) for name,fee,lag,bh in CASES}
    checks=[]
    for cut in CUTS:
        z=d.copy();mask=z.ts>=cut;n=int(mask.sum())
        scale=1.7+np.arange(n)%19*.017
        for c in ['open','high','low','close']:z.loc[mask,c]=z.loc[mask,c].to_numpy()*scale
        z.loc[mask,'volume']=z.loc[mask,'volume']*3.14159+1
        altered=indicators(z,q);prefix=d.ts<cut
        pd.testing.assert_frame_equal(s.loc[prefix],altered.loc[prefix],check_exact=True)
        for name,fee,lag,bh in CASES:
            got=simulate(z,altered,fee,lag,bh)
            for idx in [0,1,2]:
                x,y=base[name][idx],got[idx]
                col='exit_ts' if idx==1 else 'ts'
                if x.empty and y.empty:continue
                px=x.loc[x[col]<cut].reset_index(drop=True) if not x.empty else x
                py=y.loc[y[col]<cut].reset_index(drop=True) if not y.empty else y
                if px.empty and py.empty:continue
                pd.testing.assert_frame_equal(px,py,check_exact=True)
        checks.append({'cutoff':cut,'unchanged_signal_prefix_rows':int(prefix.sum()),
                       'future_rows_perturbed':n,'cases':5,'status':'PASS',
                       'boundary':'Monday UTC week boundary' if pd.Timestamp(cut).weekday()==0 and pd.Timestamp(cut).hour==0 else 'intraday / Sunday / year boundary'})
    Path(a.out).write_text(json.dumps({'status':'PASS','method':'replace all future OHLC and volume without changing earlier rows; exact prefix indicator, hourly NAV, fill and closed-trade equality','cuts':checks,'limitations':'A causality test of this implementation; does not prove PIT archive availability or intrabar path'},indent=2)+'\n')
    print('PASS 8 future cuts x 5 cases')
if __name__=='__main__':main()
