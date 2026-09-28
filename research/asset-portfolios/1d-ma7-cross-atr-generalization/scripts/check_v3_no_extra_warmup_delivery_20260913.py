"""Read-only independent checks of exported numbers and the user's missed signal."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from common import ROOT,BASE,sha,write_json
from v3_opportunity_inputs_20260913 import table

R=BASE/'artifacts/v3_no_extra_warmup_20260913'

def payload(path):return json.JSONDecoder().raw_decode(path.read_text().split('const DATA=',1)[1])[0]
def values(frame,columns):
    return json.loads(frame.reindex(columns=columns).to_json(orient='values',date_format='epoch',date_unit='ms',double_precision=15))

def main():
    assert json.loads((R/'results/completion.json').read_text())['complete']
    assert json.loads((R/'audit/completion.json').read_text())['complete']
    assert json.loads((R/'html/completion.json').read_text())['complete']
    c=json.loads((R/'inputs/catalog.json').read_text());tally=dict(pages=0,accounts=0,trades=0,stops=0)
    details=['trade_id','timestamp','signal_day','old_mult','new_mult','tightened','no_new_extreme_days','new_armed',
             'old_stop','new_stop','extreme_price','tp_protect_active','tp_protect_candidate','expected_profit_at_close','full_holding_day']
    for p in sorted((R/'html/coins').glob('*.html')):
        d=payload(p);tally['pages']+=1
        for key,seg in d['segments'].items():
            for arm in ['V3','E_STATE','TP_PROTECT']:
                run=R/'accounts'/key/arm
                if not run.exists():
                    assert not seg['trades'][arm] and seg['starts'][arm] is None
                    continue
                s=json.loads((run/'summary.json').read_text());ts=table(run/'trades.csv');ss=table(run/'stops.csv')
                assert seg['summaries'][arm]=={k:s[k] for k in ['return_pct','max_drawdown_pct','trades']}
                assert seg['starts'][arm]==pd.Timestamp(s['start']).value//10**6
                assert seg['trades'][arm]==values(ts,['trade_id','entry_time','exit_time','side','entry_price','exit_price','net_pnl','return_on_entry_equity','exit_reason'])
                if 'tp_protect_active' not in ss:ss['tp_protect_active']=False
                assert seg['stopDetails'][arm]==values(ss,details)
                for trade in seg['trades'][arm]:assert trade[1]>=seg['starts'][arm]
                if len(ss):
                    assert ss.timestamp.ge(ss.signal_day+pd.Timedelta(days=1)).all()
                    for _,g in ss.groupby('trade_id'):
                        assert g.new_mult.between(.5,1.5).all() and g.new_mult.diff().fillna(0).le(1e-10).all()
                        assert (g.new_stop.diff().fillna(0)*g.side).ge(-1e-9).all()
                tally['accounts']+=1;tally['trades']+=len(ts);tally['stops']+=len(ss)
    assert tally['pages']==680 and tally['accounts']==2937
    all_rows=pd.read_csv(R/'analysis/comparison.csv');sums=pd.read_csv(R/'analysis/paired_period_summary.csv')
    for row in sums.itertuples():
        g=all_rows[(all_rows.block==row.block)&(all_rows.case_id==row.case_id)&(all_rows.status=='COMPLETE')&(all_rows.old_status=='COMPLETE')]
        assert len(g)==row.paired_coins and g.slug.nunique()==len(g)
        for field,col in [('old_median_return_pct','old_return_pct'),('new_median_return_pct','return_pct')]:
            assert np.isclose(getattr(row,field),g[col].median(),atol=1e-10)
        assert row.old_profitable==int(g.old_return_pct.gt(1e-10).sum()) and row.new_profitable==int(g.return_pct.gt(1e-10).sum())
    index=payload(R/'html/index.html')
    assert len(index['rows'])==len(all_rows)
    for a,b in zip(index['rows'],json.loads(all_rows.to_json(orient='records',double_precision=15))):assert a==b
    h=table(R/'accounts/HYPE__seg001/V3/trades.csv').iloc[0]
    assert h.entry_time==pd.Timestamp('2025-06-18',tz='UTC') and h.side==-1
    assert h.signal_day==pd.Timestamp('2025-06-17',tz='UTC')
    assert h.exit_time==pd.Timestamp('2025-06-29 14:00',tz='UTC')
    for rel,digest in json.loads((R/'html/artifact_checksums.json').read_text()).items():assert sha(R/'html'/rel)==digest
    previous=BASE/'artifacts/v3_opportunity_20260913/html_stoplines'
    assert sha(previous/'artifact_checksums.json')=='fc9495b78f186bed91656d188c771621f7fda45607640ad7f3ad141becac0467'
    for rel,digest in json.loads((previous/'artifact_checksums.json').read_text()).items():assert sha(previous/rel)==digest
    result={'complete':True,'counts':tally,'hype_requested_signal_filled':True,'new_account_projection_exact':True,
        'new_stop_projection_exact':True,'next_day_and_one_way_stops':True,'paired_summaries_recomputed':True,
        'html_index_matches_comparison':True,'old_html_preserved':True,'browser_layout_verified':False,'audit_script_sha256':sha(Path(__file__))}
    write_json(R/'delivery/data_check.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
