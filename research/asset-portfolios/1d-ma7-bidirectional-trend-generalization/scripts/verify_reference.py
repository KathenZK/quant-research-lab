"""在新的可信返回帧上精确复现冻结244币四方向基线。"""
from pathlib import Path
import json
import argparse
import pandas as pd
from engine import Config,features,replay
from run_research import FAMILY,INPUT,read_frame,sha,save

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='reference-parity-20260908-r1');args=parser.parse_args()
    out=FAMILY/'artifacts'/args.run_id;assert not out.exists();out.mkdir()
    prior=Path('/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/1d-ma7-atr14-long-short-audit/artifacts/20260908-r1/main-symbol-results.csv')
    old=pd.read_csv(prior);old=old[old.asset_class.eq('COIN')&old.full_requested_window]
    assert old.symbol.nunique()==244
    manifest=json.loads((INPUT/'frame-manifest.json').read_text());rows=[]
    variants={'long':'B0','short':'B1','both':'B2','reverse':'B3'}
    for symbol,g in old.groupby('symbol'):
        f=read_frame(symbol,manifest);f=f[(f.ts>=pd.Timestamp('2024-12-05',tz='UTC'))&(f.ts<pd.Timestamp('2026-09-05',tz='UTC'))]
        assert len(f)==639 and f.eligible.all() and f.research_segment_id.nunique()==1
        f=features(f)
        for row in g.to_dict('records'):
            for scenario,fee,slip,col in [('default',.001,.0004,'return_pct'),('gross',0,0,'gross_return_pct'),('stress',.001,.0008,'stress_return_pct')]:
                r=replay(f,Config(variants[row['variant']],fee=fee,slip=slip),start_idx=0,warmup=15)
                error=abs(r['metrics']['return_pct']-row[col]);assert error<=1e-8,(symbol,scenario,error)
                if scenario=='default':
                    assert r['metrics']['n_trades']==row['n_trades']
                    assert abs(r['metrics']['mdd_pct']-row['mdd_pct'])<=1e-8
                rows.append({'symbol':symbol,'candidate':variants[row['variant']],'scenario':scenario,
                             'return_pct':r['metrics']['return_pct'],'reference_return_pct':row[col],'absolute_error':error})
    df=pd.DataFrame(rows);df.to_csv(out/'parity.csv',index=False)
    save(out/'report.json',{'status':'PASS','symbols':244,'comparisons':len(rows),'max_abs_return_error':df.absolute_error.max(),
        'reference_path':str(prior),'reference_sha256':sha(prior),'script_sha256':sha(Path(__file__)),
        'claim':'numeric reproduction of frozen price diagnosis; no funding certification'})
    print((out/'report.json').read_text())

if __name__=='__main__':main()
