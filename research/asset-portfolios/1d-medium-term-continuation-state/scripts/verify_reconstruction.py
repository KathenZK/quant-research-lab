"""真实产物复现与截断因果检查；不改变研究估计或搜寻新规则。"""
from pathlib import Path
import datetime as dt
import json
import time

import numpy as np
import pandas as pd

from engine import GROUPS, DAY, build_panel, load_verified_frames, sha

FAMILY = Path(__file__).resolve().parents[1]


def main():
    started = time.time()
    out = FAMILY/'artifacts/reconstruction-audit.json'
    if out.exists():
        raise FileExistsError(out)
    source = FAMILY/'artifacts/p1-research'
    manifest = json.loads((source/'panel-manifest.json').read_text())
    assert sha(source/'panel.pkl.gz') == manifest['sha256']
    assert all(sha(FAMILY/p)==h for p,h in manifest['pins'].items())
    panel = pd.read_pickle(source/'panel.pkl.gz',compression='gzip')
    stored = dict(tuple(panel.groupby('symbol',sort=False)))
    cutoff = pd.Timestamp(json.loads((FAMILY/'specs/input-request.json').read_text())['end'])
    feature_cols = ['symbol','ts','signal_time','feature_valid','atr14','sma7',
                    'prior20_delta','prior5_delta','momentum20_delta',*GROUPS]
    receipt=[]; independent_rows=0; prefix_cases=[]
    for k,(symbol,frame) in enumerate(load_verified_frames(FAMILY/'artifacts/p0-inputs'),1):
        rebuilt=build_panel(frame,cutoff)
        old=stored[symbol].reset_index(drop=True)
        pd.testing.assert_frame_equal(rebuilt,old,check_exact=True)
        # Direct price/index arithmetic on first/middle/last valid event per segment.
        for _,segment in old.loc[old.eligible].groupby('research_segment_id',sort=False):
            indices=segment.index[segment.valid20].to_numpy()
            if not len(indices):
                continue
            chosen=np.unique(indices[[0,len(indices)//2,-1]])
            for i in chosen:
                row=old.iloc[i]
                e=float(old.iloc[i+1].open)
                x=float(old.iloc[i+20].close)
                q=(x-e)/float(row.atr14)
                late=(x-float(old.iloc[i+5].close))/float(row.atr14)
                np.testing.assert_allclose([row.q20,row.l20,row.ret20],[q,late,x/e-1],rtol=1e-13,atol=1e-13)
                closes=old.close.to_numpy()
                ma=float(np.mean(closes[i-6:i+1])); prevma=float(np.mean(closes[i-7:i]))
                for side,d in [('LONG',1),('SHORT',-1)]:
                    m=d*(closes[i]-ma)>0 and d*(closes[i-1]-prevma)<0
                    assert bool(row['M_'+side])==m
                    assert bool(row['U_'+side])==(d*(closes[i]-closes[i-20])>0)
                independent_rows+=1
        # Chosen by asset identity and coverage position, never by returns.
        if symbol in ('BTC/USDT:USDT','ETH/USDT:USDT','HYPE/USDT:USDT') or k in (1,324,648):
            for stop in sorted(set([max(60,len(frame)//2),max(60,len(frame)-20)])):
                if stop>=len(frame):
                    continue
                f=frame.iloc[:stop].copy()
                prefix=build_panel(f,f.ts.iloc[-1]+DAY)
                pd.testing.assert_frame_equal(prefix[feature_cols],old.iloc[:stop][feature_cols],check_exact=True)
                mature=prefix.valid20.to_numpy()
                pd.testing.assert_frame_equal(prefix.loc[mature,['q20','l20','ret20']],old.iloc[:stop].loc[mature,['q20','l20','ret20']],check_exact=True)
                prefix_cases.append({'symbol':symbol,'rows':stop,'last_close':str(f.ts.iloc[-1]+DAY),'signals_unchanged':True,'mature_labels_unchanged':True})
        receipt.append({'symbol':symbol,'rows':len(old),'all_columns_exact':True})
        if k%100==0:
            print(f'RECONSTRUCTION {k}/648 elapsed={time.time()-started:.1f}s',flush=True)
    assert len(receipt)==manifest['symbols'] and sum(r['rows'] for r in receipt)==manifest['rows']
    assert all(sha(FAMILY/p)==h for p,h in manifest['pins'].items())
    result={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'PASS',
            'panel_sha256':manifest['sha256'],'script_sha256':sha(Path(__file__)),
            'all_panel_rows':len(panel),'all_symbols':len(receipt),'all_columns_exact':True,
            'direct_arithmetic_rows':independent_rows,'prefix_cases':prefix_cases,
            'scope':'all-frame deterministic reproduction plus selected direct arithmetic and past-only prefix checks; no new economic evidence',
            'seconds':time.time()-started,'symbols':receipt}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('symbols','prefix_cases')},indent=2),flush=True)


if __name__=='__main__':
    main()
