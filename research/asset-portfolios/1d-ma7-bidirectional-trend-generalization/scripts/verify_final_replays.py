"""保留主样本的逐日独立账本、费用和真实路径前缀验证。"""
from pathlib import Path
import gzip,json,math,argparse
import numpy as np
import pandas as pd
from engine import Config,replay
from run_research import FAMILY,INPUT,sha,save,groups,btc_reference

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',default='final-replay-verification-20260908')
    p.add_argument('--evaluation-dir',default='p1-evaluation-20260908-r1');args=p.parse_args()
    out=FAMILY/'artifacts'/args.run_id;assert not out.exists();out.mkdir()
    ev=FAMILY/'artifacts'/args.evaluation_dir;manifest=json.loads((INPUT/'frame-manifest.json').read_text())
    btc=btc_reference(manifest);rows=[];prefix_checks=0;daily_points=0
    for path in sorted((ev/'main-paths').glob('*.json.gz')):
        with gzip.open(path,'rt') as h:data=json.load(h)
        symbol=data['common']['symbol'];prices=np.array([b['close'] for b in data['bars']]);n=len(prices)
        for candidate,r in data['runs'].items():
            ledger=np.ones(n);completed={};open_value={}
            for t in r['trades']:
                assert t['entry_idx']==t['signal_idx']+1 and t['signal_idx']>=120
                s=t['side'];u=t['units'];e=t['equity_before'];entry=t['entry_price'];exit=t['exit_price']
                assert math.isclose(t['entry_fee'],u*entry*.001,abs_tol=1e-12)
                assert math.isclose(t['exit_fee'],u*exit*.001,abs_tol=1e-12)
                expected=e-t['entry_fee']+s*u*(exit-entry)-t['exit_fee']
                assert math.isclose(expected,t['uncapped_equity_after'],abs_tol=1e-10,rel_tol=1e-12)
                assert math.isclose(max(0,expected),t['equity_after'],abs_tol=1e-10,rel_tol=1e-12)
                completed[t['exit_idx']]=t['equity_after']
                for i in range(t['entry_idx'],t['exit_idx']):
                    assert i not in open_value,'overlapping account positions'
                    open_value[i]=e-t['entry_fee']+s*u*(prices[i]-entry)
            cash=1.
            for i in range(n):
                if i in completed:cash=completed[i]
                ledger[i]=open_value.get(i,cash)
            err=float(np.max(np.abs(ledger-r['nav'])));assert err<=1e-10
            daily_points+=n
            rows.append({'symbol':symbol,'candidate':candidate,'daily_points':n,'trades':len(r['trades']),'max_daily_ledger_error':err})
        # Deterministic source reproduction and prefix checks on every main symbol,
        # including extreme successes/failures and potential exact-equality prices.
        gs=groups(symbol,manifest,btc);g=next(g for g in gs if str(g.research_segment_id.iloc[0])==data['common']['segment_id'])
        end=int(g.ts.searchsorted(pd.Timestamp('2026-09-05',tz='UTC')));g=g.iloc[:end]
        start=data['runs']['C3']['start_idx'];actual=replay(g,Config('C3'),start_idx=start)
        np.testing.assert_allclose(actual['nav'],data['runs']['C3']['nav'],atol=1e-10,rtol=1e-12)
        for candidate in ['C0','C1','C2','C3','C4','C5']:
            full=replay(g,Config(candidate),start_idx=start,force_end=False)
            cut=start+(len(g)-start)//2
            partial=replay(g.iloc[:cut],Config(candidate),start_idx=start,force_end=False)
            assert partial['nav']==full['nav'][:cut]
            assert partial['events']==[e for e in full['events'] if e['i']<cut]
            prefix_checks+=1
    pd.DataFrame(rows).to_csv(out/'daily-ledger-checks.csv',index=False)
    save(out/'report.json',{'status':'PASS','main_paths':len(list((ev/'main-paths').glob('*.json.gz'))),
        'candidate_ledgers':len(rows),'independently_accounted_daily_points':daily_points,
        'real_data_prefix_checks':prefix_checks,'C3_all_main_reproduced':True,'script_sha256':sha(Path(__file__)),
        'funding_not_imputed':True,'real_exchange_liquidation_certified':False})
    print((out/'report.json').read_text())

if __name__=='__main__':main()
