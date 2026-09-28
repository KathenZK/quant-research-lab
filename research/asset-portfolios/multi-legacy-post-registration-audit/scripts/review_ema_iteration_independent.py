"""Independent read-only acceptance of EMA comparison artifacts and source rules.

Does not call the comparison's trade/replay/account functions. Recomputes
indicator definitions and ledger arithmetic from frozen inputs and saved fills.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import compare_ema_versions as e

ROOT=e.ROOT
BASE=e.OUT.parent
OUT=BASE/'acceptance_ema_independent.json'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def near(a,b,tol=1e-10):
    a,b=np.asarray(a,float),np.asarray(b,float)
    assert np.allclose(a,b,rtol=1e-11,atol=tol,equal_nan=True),float(np.nanmax(np.abs(a-b)))


def main():
    checks=[];warnings=[];errors=[]
    rows=json.loads((e.OUT/'results.json').read_text())
    plan=json.loads((e.OUT/'cases_plan.json').read_text())
    wanted={(c['family'],c['version'],s['name']) for c in plan['cases'] for s in plan['scenarios']}
    assert len(rows)==27 and {(r['family'],r['version'],r['scenario']) for r in rows}==wanted
    sources=json.loads((e.OUT/'sources_manifest.json').read_text())
    assert all(sha(ROOT/p)==d for p,d in sources.items())
    execution=json.loads((e.OUT/'source_execution_sha256.json').read_text())
    assert execution['script']==sha(Path(e.__file__))
    assert execution['plan']==sha(e.OUT/'cases_plan.json')
    checks.append(dict(name='frozen_nine_versions_three_scenarios_and_source_hashes',status='PASS',sources=len(sources)))

    f=e.legacy.frame_with_index(e.inputs.load_prices('HYPE','15m'))
    events=e.inputs.load_funding('HYPE')
    events.ts=pd.to_datetime(events.ts,utc=True)
    assert events.event_unambiguous.all() and not events.ts.duplicated().any()
    assert f.index[-1]+e.STEP==e.END
    mods=e.imports()
    tf=mods['tb'].build_features(f,mods['tb'].V35Config())
    close=f.close
    tr=pd.concat([f.high-f.low,(f.high-close.shift()).abs(),(f.low-close.shift()).abs()],axis=1).max(axis=1)
    near(tf.atr,tr.rolling(672,min_periods=672).mean())
    near(tf.ema_fast,close.ewm(span=96,adjust=False,min_periods=96).mean())
    near(tf.ema_slow,close.ewm(span=384,adjust=False,min_periods=384).mean())
    near(tf.volume_surge,f.volume/f.volume.rolling(192,min_periods=192).mean()-1)
    # Verify higher-timeframe alignment at an incomplete hour, not only midnight.
    cutoff=pd.Timestamp('2026-08-08T07:30Z')
    tprefix=mods['tb'].build_features(f.loc[f.index<cutoff],mods['tb'].V35Config())
    for col in ['h1_adx','h1_plus_di','h1_minus_di','h1_ema_spread','adx','plus_di','minus_di']:
        near(tprefix[col],tf.loc[tprefix.index,col])
    h1=f.resample('1h',label='left',closed='left').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    hspread=(h1.close.ewm(span=24,adjust=False,min_periods=24).mean()/h1.close.ewm(span=96,adjust=False,min_periods=96).mean()-1).shift().reindex(f.index,method='ffill')
    near(hspread,tf.h1_ema_spread)
    context=e.legacy.mii_context(f)
    mf=context.features.set_index('ts')
    delta=close.diff();gain=delta.clip(lower=0).ewm(alpha=1/7,adjust=False,min_periods=7).mean();loss=(-delta.clip(upper=0)).ewm(alpha=1/7,adjust=False,min_periods=7).mean()
    rsi=100-100/(1+gain/loss)
    near(mf.rsi7,rsi)
    macd=close.ewm(span=12,adjust=False,min_periods=12).mean()-close.ewm(span=26,adjust=False,min_periods=26).mean()
    hist=macd-macd.ewm(span=9,adjust=False,min_periods=9).mean()
    near(mf.macd_12_26_9_hist,hist)
    near(mf.atr_pct96,tr.rolling(96,min_periods=96).mean()/close)
    near(mf.rvol96,f.volume/f.volume.rolling(96,min_periods=96).mean())
    cfg=json.loads((e.OUT/'effective_original_configs.json').read_text())
    assert cfg['tb_v35']==e.asdict(mods['tb'].V35Config())
    assert cfg['tb_v41_delta']=={'cooldown_bars':1,'short_use_h1_ema':False}
    v18=cfg['x_v18'];v12=v18['spec']['v12']
    assert (v18['signal']['hq_min_score'],v18['signal']['lq_min_score'],v18['signal']['lq_max_score'])==(7,5,6)
    assert (v18['hq_scale'],v18['lq_scale'])==(1.1,1.)
    assert (v12['stop_atr'],v12['min_mfe_atr'],v12['entry_max_regime_age'],v12['entry_max_dist_ema96'])==(8.,4.,128,.08)
    assert (v12['hard_exit_mode'],v12['confirm_mode'],v12['warning_exit_min_capture'])==('swing96','ema21',.35)
    assert (v18['spec']['late_max_age'],v18['spec']['late_dist_ema96'],v18['spec']['cooldown_bars'],v18['spec']['min_prev_pnl'],v18['spec']['min_prev_mfe_atr'])==(384,.075,12,-.03,3.)
    assert cfg['mii_v1']['signal']['low']==30 and cfg['mii_v1']['signal']['high']==60
    assert cfg['mii_v1']['exit']=={'kind':'fixed','stop_pct':.028,'max_hold_bars':16,'take_profit_pct':.009,'activation_pct':None,'trail_pct':None}
    assert cfg['mii_v14a_entry_filter']['min_atr_pct96']==.0075 and cfg['mii_v14a_entry_filter']['max_atr_pct96']==.028
    assert cfg['mii_v14a_entry_filter']['min_rvol96']==.85
    assert cfg['mii_atr_bracket_v14a']=={'atr_window':96,'tp_atr_mult':1.4,'sl_atr_mult':3.,'max_hold_bars':24,'exposure':2.5}
    assert (cfg['ens_early']['trend'],cfg['ens_early']['mii'])==('V35','V1.3')
    assert (cfg['ens_v2']['trend'],cfg['ens_v2']['mii'])==('V39','V1.4')
    checks.append(dict(name='independent_EMA_ATR_RSI_MACD_RVOL_formulas_closed_H1_and_spec_configs',status='PASS'))

    reviewed_paths=[]
    for r in rows:
        t=pd.read_csv(ROOT/r['trades_path'])
        cv=pd.read_csv(ROOT/r['equity_path'])
        mo=pd.read_csv(ROOT/r['monthly_path'])
        for col in ('entry_ts','exit_ts','exit_effective_ts','signal_ts'):t[col]=pd.to_datetime(t[col],utc=True)
        cv.valuation_ts=pd.to_datetime(cv.valuation_ts,utc=True)
        assert len(t)==r['trades'] and t.entry_ts.ge(e.START).all() and t.signal_ts.ge(e.START).all()
        assert t.entry_ts.lt(e.END).all() and t.exit_effective_ts.le(e.END).all()
        assert t.entry_ts.iloc[1:].reset_index(drop=True).ge(t.exit_effective_ts.iloc[:-1].reset_index(drop=True)).all()
        fee=.001;slip=.0008 if r['scenario']=='unit_slip8bps' else .0004
        near(t.entry_fill,t.entry_price*(1+t.direction*slip));near(t.exit_fill,t.exit_price*(1-t.direction*slip))
        near(t.quantity*t.entry_fill,t.entry_equity*t.allocation)
        if r['scenario']!='original_sizing':near(t.allocation,1.)
        near(t.entry_fee,t.quantity*t.entry_fill*fee);near(t.exit_fee,t.quantity*t.exit_fill*fee)
        near(t.gross_pnl,t.direction*t.quantity*(t.exit_price-t.entry_price))
        near(t.entry_slippage_cost,t.quantity*abs(t.entry_fill-t.entry_price))
        near(t.exit_slippage_cost,t.quantity*abs(t.exit_fill-t.exit_price))
        near(t.net_pnl,t.direction*t.quantity*(t.exit_fill-t.entry_fill)-t.entry_fee-t.exit_fee+t.observed_funding_estimate)
        near(t.exit_equity,t.entry_equity+t.net_pnl)
        near(t.entry_equity.iloc[1:],t.exit_equity.iloc[:-1])
        near(t.entry_equity.iloc[0],1.)
        near(1+t.net_pnl.sum(),cv.equity_funding_estimate.iloc[-1])
        near((cv.equity_funding_estimate.iloc[-1]-1)*100,r['return_pct'])
        near((cv.equity_excluding_funding.iloc[-1]-1)*100,r['return_excluding_funding_pct'])
        valret=cv.equity_funding_estimate/cv.equity_funding_estimate.shift().fillna(1)-1
        near(cv['return'],valret)
        near(cv.drawdown,cv.equity_funding_estimate/cv.equity_funding_estimate.cummax().clip(lower=1)-1)
        near(cv.drawdown.min()*100,r['max_drawdown_pct'])
        mm=valret.groupby((cv.valuation_ts-pd.Timedelta(nanoseconds=1)).dt.strftime('%Y-%m')).apply(lambda x:(1+x).prod()-1)
        near(mo.return_pct,mm.to_numpy()*100)
        near((1+mo.return_pct/100).prod(),cv.equity_funding_estimate.iloc[-1])
        # Independently recalculate event inclusion and every funding payment.
        fpaid=[]
        ex_cash=1.
        for trd in t.itertuples():
            fcut=trd.exit_ts+e.STEP if trd.exit_timing=='intrabar' else trd.exit_ts
            obs=events.loc[events.ts.ge(trd.entry_ts)&events.ts.lt(fcut)&events.ts.lt(e.END)]
            payment=sum(-trd.direction*trd.quantity*float(f.open.loc[event.ts.floor('15min')])*event.funding_rate for event in obs.itertuples())
            fpaid.append(payment)
            q=ex_cash*trd.allocation/trd.entry_fill
            ex_cash+=trd.direction*q*(trd.exit_fill-trd.entry_fill)-fee*q*(trd.entry_fill+trd.exit_fill)
            near(trd.entry_price,f.open.loc[trd.entry_ts])
            if trd.exit_reason=='terminal_mark':
                assert trd.exit_ts==e.END
                near(trd.exit_price,f.close.iloc[-1]);assert trd.exit_fee>0 and trd.exit_slippage_cost>0
        near(fpaid,t.observed_funding_estimate)
        near(ex_cash,cv.equity_excluding_funding.iloc[-1])
        # Accepted entries must satisfy independently reconstructed source predicates.
        if r['scenario']=='unit':
            for trd in t.itertuples():
                s=trd.signal_ts;d=trd.direction
                delay=2 if (r['family']=='EMA-TB' and r['version']!='V2P') or (r['family']=='ENS' and trd.leg!='mii') else 1
                assert trd.entry_ts-s==delay*e.STEP
                if r['family']=='MII':
                    low=30 if r['version']=='V1' else 40
                    assert (rsi.loc[s]>low and rsi.loc[s-e.STEP]<=low) if d==1 else (rsi.loc[s]<60 and rsi.loc[s-e.STEP]>=60)
                    assert d*hist.loc[s]>=-1e-14
                    av=(tr.rolling(96,min_periods=96).mean()/close).loc[s]
                    assert (.006 if r['version']=='V1' else .0075)<=av<=.028
                    if r['version']!='V1':assert mf.rvol96.loc[s]>=.85
                if r['family']=='EMA-TB' and r['version'] in ('V35','V41'):
                    x=tf.loc[s]
                    if d==1:assert x.ema_spread>0 and x.adx>=28 and x.volume_surge>=.25 and x.h1_adx>18 and x.h1_plus_di>x.h1_minus_di
                    else:assert x.ema_spread<0 and x.adx>=36 and x.volume_surge>=.5 and (r['version']=='V41' or x.h1_ema_spread<0)
                    near(trd.entry_atr,tf.atr.loc[trd.entry_ts-e.STEP])
        checks.append(dict(name='ledger_fills_fees_funding_months_and_entry_rules',family=r['family'],version=r['version'],scenario=r['scenario'],status='PASS',trades=len(t)))
        reviewed_paths += [ROOT/r['trades_path'],ROOT/r['equity_path'],ROOT/r['monthly_path']]

    pairs=json.loads((BASE/'paired_results.json').read_text())
    expected={'EMA-X':('V1','V18'),'EMA-TB':('V35','V41'),'MII':('V1','V1.4A'),'ENS':('V35+MII1.3','V2')}
    for fam,(early,final) in expected.items():
        p=next(x for x in pairs if x['family']==fam)
        assert (p['early_version'],p['final_version'])==(early,final)
        for role,version in [('early',early),('final',final)]:
            r=next(x for x in rows if x['family']==fam and x['version']==version and x['scenario']=='unit')
            near(p[f'{role}_return'],r['return_pct']/100)
            near(p[f'{role}_return_ex_funding'],r['return_excluding_funding_pct']/100)
            assert p[f'{role}_trades']==r['trades']
        near(p['increment'],p['final_return']-p['early_return'])
    checks.append(dict(name='root_pairs_predeclared_ends_not_best_result_selection',status='PASS',pairs=expected))
    prefix=json.loads((e.OUT/'verification.json').read_text())
    assert prefix['status']=='PASS' and len(prefix['checks'])==9 and all(x['prefix_equity_max_abs_diff']==0 for x in prefix['checks'])
    checks.append(dict(name='existing_nine_full_path_prefix_reports',status='PASS',independently_rerun=False))
    warnings=[
        'EMA-X V1 is a predeclared bare EMA96/384 cross_only/opposite_cross reconstruction, not a preserved complete unique historical V1 exit spec; retain this qualifier in primary table narrative.',
        'EMA-TB primary V35->V41 compares the earliest retained complete causal engine against final; V2P is a separately labelled causal recovery and must not silently replace V35 after viewing results.',
        'ENS early V35+MII1.3 was a frozen diagnostic combination, never a registered V1.',
        'Fee/slip scenarios revalue fixed reference trade paths. They do not rerun protective thresholds against slippage-shifted entries; differs from CC and is explicitly diagnostic.',
        'Funding exact-boundary order assumes opening executions before funding; milliseconds retained. Intrabar exit-bar settlements assumed before exit; 15m bars cannot prove that ordering, and all settlements use trade-open proxy mark.',
        'Drawdown uses sampled valuation timestamps. Boundary exits and entry fees use the documented adapter accounting stages; no high-frequency intrabar maximum drawdown claim is accepted.',
        'Source rules and executable parameter mapping reviewed; old full-training-sample profit figures and historical original-code parity are not independently reproduced in this acceptance.'
    ]
    reviewed_paths += [Path(e.__file__),e.OUT/'results.json',e.OUT/'cases_plan.json',e.OUT/'sources_manifest.json',e.OUT/'effective_original_configs.json',e.OUT/'verification.json',e.OUT/'report.md',BASE/'paired_results.json']
    obj=dict(status='PASS_WITH_DECLARED_LIMITATIONS',reviewer='compare_cc_versions independent agent',scope='EMA27 saved scenarios and four frozen root pairs; no strategy/account replay rerun',checks=checks,warnings=warnings,errors=errors,
             artifacts_sha256={str(p.relative_to(ROOT)):sha(p) for p in reviewed_paths})
    OUT.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':obj['status'],'checks':len(checks),'warnings':len(warnings),'report':str(OUT),'report_sha256':sha(OUT)},ensure_ascii=False))


if __name__=='__main__':main()
