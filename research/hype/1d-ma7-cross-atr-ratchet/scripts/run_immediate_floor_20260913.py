"""HYPE-only, fixed four-account test of the user's instantaneous 0.5 ATR stop."""
from pathlib import Path
from dataclasses import asdict
import importlib.util
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parents[1]
MARKET=ROOT/'research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts'
sys.path.insert(0,str(MARKET))
from common import sha,write_json
from v3_no_extra_warmup_20260913 import load_new,R as NATURAL
from v3_opportunity_study_20260913 import engine as parent_engine
from run_market import save_result
from run_exit_state_machine_20260910 import stats
from v3_opportunity_inputs_20260913 import table
from build_v3_opportunity_report_20260913 import trade_stats
from audit_immediate_floor_20260913 import audit_run

R=BASE/'artifacts/v3_immediate_floor_20260913'
PIN=BASE/'specs/v3-immediate-floor-engine-pin-20260913.json'
CONTRACT=BASE/'specs/v3-immediate-floor-20260913.md'
NAMES={'B':'当前V3 · 原逐日收紧','A':'仅反向超0.2ATR一步到0.5','S':'仅四日停滞一步到0.5','AS':'用户方案 · 双触发一步到0.5'}

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def engine():
    pin=json.loads(PIN.read_text());assert sha(ROOT/pin['engine_path'])==pin['engine_sha256']
    return module('hype_immediate_floor_v7',ROOT/pin['engine_path'])
def configs(e):
    common=dict(reverse=False,progress_days=4,fee=.001,slip=.0004)
    return {'B':e.Config(**common),'A':e.Config(**common,adverse_ma_floor_atr=.2),
            'S':e.Config(**common,stagnation_floor=True),'AS':e.Config(**common,adverse_ma_floor_atr=.2,stagnation_floor=True)}

def tests(e):
    fixture=module('floor_fixture',ROOT/'tests/test_ma7_car_admission_routing.py');checks=[]
    raw,h=fixture.random_market();old=parent_engine();d=old.features(raw)
    a=old.simulate(h,d,old.Config(reverse=False,progress_days=4,fee=.001,slip=.0004))
    b=e.simulate(h,d,configs(e)['B']);fixture.assert_old_fields_equal(a,b);checks.append('disabled_exact_old_fields')
    for side in [-1,1]:
        for distance in [.19,.2,.21]:
            d,h=fixture.path(side=side,closes=(-distance*5,1.,1.,1.),ma=0.,atr=5.)
            z=e.simulate(h,d,configs(e)['AS']);s=z[3];first=s[s.timestamp.eq(fixture.ZERO+pd.Timedelta(days=2))].iloc[0]
            assert bool(first.jump_to_floor)==(distance>.2)
            assert first.new_mult==(.5 if distance>.2 else 1.5)
            assert first.signal_day==fixture.ZERO+pd.Timedelta(days=1)
            assert s.timestamp.min()==fixture.ZERO+pd.Timedelta(days=1)
            if distance>.2:assert s[s.timestamp>=first.timestamp].new_mult.eq(.5).all()
            checks.append(f'adverse_boundary_side{side}_{distance}')
        # Higher closes cannot reset the high/low counter when highs/lows stay fixed.
        d,h=fixture.path(side=side,closes=(1.,2.,2.1,2.2,2.3,2.4,2.5),favorable=10.,ma=0.,atr=10.)
        z=e.simulate(h,d,configs(e)['S']);j=z[3][z[3].jump_to_floor]
        assert len(j)==1 and j.iloc[0].no_new_extreme_days==4
        assert j.iloc[0].signal_day==fixture.ZERO+pd.Timedelta(days=5)
        assert j.iloc[0].timestamp==fixture.ZERO+pd.Timedelta(days=6)
        assert j.iloc[0].old_mult==1.5 and j.iloc[0].new_mult==.5
        assert z[3].new_mult.diff().fillna(0).le(1e-12).all()
        assert (z[3].new_stop.diff().fillna(0)*side).ge(-1e-10).all()
        checks.append(f'four_high_low_stagnation_days_side{side}')
    # Future hourly and daily mutations cannot alter decisions already closed.
    raw,h=fixture.random_market();d=e.features(raw);cut=fixture.ZERO+pd.Timedelta(days=75)
    for arm in ['A','S','AS']:
        cfg=configs(e)[arm];full=e.simulate(h,d,cfg);prefix=e.simulate(h[h.timestamp<cut],d[d.timestamp<cut],cfg,end=cut)
        for i,timecol in [(1,'exit_time'),(3,'timestamp')]:
            left=full[i][full[i][timecol]<cut].copy();right=prefix[i][prefix[i][timecol]<cut].copy()
            if i==1:right=right[right.exit_reason.ne('sample_end')]
            pd.testing.assert_frame_equal(left.reset_index(drop=True),right.reset_index(drop=True),check_exact=True)
        checks.append('future_prefix_'+arm)
    return checks

def main():
    assert not R.exists(),'Do not overwrite completed HYPE evidence'
    R.mkdir(parents=True);e=engine();pin=json.loads(PIN.read_text());old_manifest=NATURAL/'delivery/artifact_checksums.json'
    paths=[Path(__file__),Path(__file__).with_name('audit_immediate_floor_20260913.py'),PIN,CONTRACT,ROOT/pin['engine_path'],
           MARKET/'v3_no_extra_warmup_20260913.py',MARKET/'v3_opportunity_inputs_20260913.py',MARKET/'audit_v3_opportunity_20260913.py',old_manifest]
    pins={str(p.relative_to(ROOT)):sha(p) for p in paths}
    write_json(R/'started.json',{'created_before_results_utc':str(pd.Timestamp.now(tz='UTC')),'scope':['HYPE/USDT:USDT'],
        'pins':pins,'configs':{k:asdict(v) for k,v in configs(e).items()},'fixed_arms':NAMES,'extra_fixed_warmup_removed':True})
    check=tests(e);write_json(R/'tests.json',{'complete':True,'checks':check,'count':len(check)})
    d,h,meta=load_new('HYPE__seg001');assert d.symbol.eq('HYPE/USDT:USDT').all()
    write_json(R/'input.json',meta);rows=[];audits=[];results={};comparisons=[];jump_rows=[]
    for arm,cfg in configs(e).items():
        events=[];res=e.simulate(h,d,cfg,pd.Timestamp(meta['new_start']),pd.Timestamp(meta['end']),entry_events=events)
        res[0].update(stats(res[1]));p=R/'accounts'/arm;save_result(p,res)
        pd.DataFrame(events).reindex(columns=list(dict.fromkeys(e.ENTRY_EVENT_COLUMNS+e.CANDIDATE_EVENT_COLUMNS))).to_csv(p/'entry_events.csv',index=False)
        if arm=='B':
            oldp=NATURAL/'accounts/HYPE__seg001/V3';frozen=json.loads(old_manifest.read_text())
            for f in ['trades.csv','stops.csv','equity.parquet','summary.json']:
                assert sha(oldp/f)==frozen[str((oldp/f).relative_to(NATURAL))]
            old_t=table(oldp/'trades.csv')
            for col in ['entry_time','exit_time','side','entry_price','exit_price','net_pnl','return_on_entry_equity']:
                pd.testing.assert_series_equal(res[1][col],old_t[col],check_dtype=False,check_names=False,rtol=1e-12,atol=1e-10)
            old_s=json.loads((oldp/'summary.json').read_text());assert res[0]['return_pct']==old_s['return_pct'] and res[0]['max_drawdown_pct']==old_s['max_drawdown_pct']
        audit=audit_run(p,d.set_index('timestamp',drop=False),h.set_index('timestamp',drop=False));audits.append({'arm':arm,**audit})
        metrics=trade_stats(res[1],pd.Timestamp(meta['new_start']),pd.Timestamp(meta['end']),pd.Timestamp(meta['end']))
        rows.append({'arm':arm,'name':NAMES[arm],**res[0],**metrics});results[arm]=res
        z=res[3][res[3].jump_to_floor].copy();z['arm']=arm;jump_rows.extend(z.to_dict('records'))
        print(arm,round(res[0]['return_pct'],4),round(res[0]['max_drawdown_pct'],4),len(res[1]),'audit PASS',flush=True)
    original={(t.entry_time,int(t.side)):t for t in results['B'][1].itertuples()}
    for arm in ['A','S','AS']:
        new={(t.entry_time,int(t.side)):t for t in results[arm][1].itertuples()}
        for key in sorted(original.keys()|new.keys()):
            b,n=original.get(key),new.get(key)
            comparisons.append({'arm':arm,'entry_time':str(key[0]),'side':key[1],'relationship':'same_entry' if b and n else 'new_entry' if n else 'old_entry_missed',
                'baseline_id':b.trade_id if b else None,'new_id':n.trade_id if n else None,
                'baseline_exit':str(b.exit_time) if b else None,'new_exit':str(n.exit_time) if n else None,
                'baseline_return_pct':b.return_on_entry_equity*100 if b else None,'new_return_pct':n.return_on_entry_equity*100 if n else None,
                'baseline_winner':b.return_on_entry_equity>0 if b else None,
                'delta_pp':(n.return_on_entry_equity-b.return_on_entry_equity)*100 if b and n else None})
    pd.DataFrame(rows).to_csv(R/'comparison.csv',index=False);pd.DataFrame(comparisons).to_csv(R/'trade_comparison.csv',index=False)
    pd.DataFrame(jump_rows).to_csv(R/'floor_triggers.csv',index=False);write_json(R/'audit.json',{'complete':True,'accounts':audits})
    write_json(R/'completion.json',{'complete':True,'scope':['HYPE'],'new_accounts':4,'baseline_exact':True,'audited_accounts':4,'tests_pass':len(check),'full_market_replayed':False,'funding_verified':False})

if __name__=='__main__':main()
