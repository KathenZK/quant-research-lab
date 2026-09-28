"""Retain the original AR-MAE V1 sleeve-candidate and blocking semantics."""
from pathlib import Path
from dataclasses import asdict
import hashlib
import json
import re
import sys
import numpy as np
import pandas as pd
import audit_common as common
import other_assets_replay as single

ROOT=Path(__file__).resolve().parents[4]
FAMILY=Path(__file__).resolve().parents[1]
OUT=FAMILY/'artifacts/ensemble'
SPEC=ROOT/'research/asset-portfolios/1h-adaptive-regime-multi-asset-ensemble/specs/binance-1h-ar-mae-v1-full-reproduction-spec-2026-07-07.md'
START=pd.Timestamp('2026-07-08T00:00:00Z')
END=common.END
PRIORITY={'HYPE':22.8128,'TRX':5.686,'BTC':5.27,'ETH':3.3084,'BNB':2.94,'SOL':2.07}

def hype_sleeve(slippage):
    module=single.load_module(ROOT/'research/hype/1h-adaptive-regime/scripts/audit_hype_1h_ar_v4_pressure_optimization.py','ensemble_hype_original')
    engine=module.base
    raw=common.load_prices('HYPE','1h').reset_index(drop=True)
    funding=common.load_funding('HYPE')
    raw=raw[raw.ts>=funding.ts.min().ceil('h')].reset_index(drop=True)
    frame=module.v3ab.ensure_extra_macd_features(engine.add_features(raw,funding))
    blocks=[json.loads(s) for s in re.findall(r'```json\s*(.*?)```',SPEC.read_text(),re.S)]
    cfgs=[engine.StrategyConfig(**b) for b in blocks if isinstance(b,dict) and b.get('name','').startswith('HYPE_1H_AR_V4_')]
    assert len(cfgs)==2
    terminal=frame.iloc[-1:].copy();terminal['ts']=END
    for c in ('open','high','low','close'):terminal[c]=raw.close.iloc[-1]
    allframe=pd.concat([frame,terminal],ignore_index=True)
    ft,fc=engine.funding_prefix(funding);engine.FEE_PER_FILL=.001;engine.SLIPPAGE_PER_FILL=slippage
    legs=[]
    for cfg in cfgs:
        sig=engine.build_signal(frame,cfg)
        entry=frame.ts+pd.Timedelta(hours=cfg.entry_delay_bars)
        sig[((frame.ts+pd.Timedelta(hours=1)<START)|(entry<START)|(entry>=END)).to_numpy()]=0
        ts=engine.simulate_trades(allframe,np.r_[sig,0],cfg,ft,fc)
        for t in ts:
            if t.exit_ts==END:t.exit_reason='audit_terminal_close'
        legs.append(ts)
    trades=engine.merge_trade_sets(*legs,1.,0.)
    return {'asset':'HYPE','trades':trades,'frame':raw,'funding':funding,'engine':engine,'configs':cfgs}

def run(slippage,label):
    sleeves={}
    for asset in ('BTC','ETH','SOL','BNB','TRX'):
        sleeves[asset]=single.replay_asset(asset,START,version_override={'ETH':'V3','SOL':'V2'}.get(asset),slippage=slippage)
    sleeves['HYPE']=hype_sleeve(slippage)
    tagged=[(a,t) for a,s in sleeves.items() for t in s['trades']]
    tagged.sort(key=lambda at:(at[1].entry_ts,-PRIORITY[at[0]],at[1].exit_ts))
    selected=[];blocked=None
    for asset,t in tagged:
        if blocked is not None and t.entry_ts<=blocked:continue
        selected.append((asset,t));blocked=t.exit_ts
    balance=1.;cursor=0;rows=[{'ts':START,'equity':1.}]
    indexed={a:s['frame'].set_index('ts') for a,s in sleeves.items()}
    for now in pd.date_range(START,END,freq='1h',inclusive='left'):
        # All intrabar fills in the exit bar are booked at that bar's close.
        while cursor<len(selected) and selected[cursor][1].exit_ts<=now:
            balance*=1+selected[cursor][1].equity_ret;cursor+=1
        marked=balance
        if cursor<len(selected):
            a,t=selected[cursor]
            if t.entry_ts<=now<t.exit_ts:
                px=float(indexed[a].loc[now,'close']);f=sleeves[a]['funding']
                fund=f[(f.ts>=t.entry_ts)&(f.ts<now+pd.Timedelta(hours=1))].funding_rate.sum()
                marked=balance*(1+t.exposure*(t.side*(px/t.entry_price-1)-.001-t.side*fund))
        rows.append({'ts':now+pd.Timedelta(hours=1),'equity':marked})
    while cursor<len(selected):balance*=1+selected[cursor][1].equity_ret;cursor+=1
    rows[-1]['equity']=balance
    curve=pd.DataFrame(rows);curve['drawdown']=curve.equity/curve.equity.cummax()-1
    returns=np.array([t.equity_ret for _,t in selected]);positive=returns[returns>0].sum();negative=-returns[returns<0].sum()
    summary={'family':'BIN-1H-AR-MAE','version':'V1','scenario':label,'start':START,'end':END,
       'return':balance-1,'max_drawdown':float(curve.drawdown.min()),'trades':len(selected),
       'win_rate':float((returns>0).mean()) if len(returns) else None,
       'profit_factor':float(positive/negative) if negative else None,
       'candidate_trades':len(tagged),'skipped_blocked':len(tagged)-len(selected),
       'per_asset_selected':{a:sum(x==a for x,_ in selected) for a in sleeves},
       'max_exposure':max([t.exposure for _,t in selected],default=0),
       'fee_per_fill':.001,'slippage_per_fill':slippage,
       'funding_status':'OBSERVED_EVENT_ESTIMATE_NOT_VERIFIED_FULL_NET',
       'mechanism_limitation':'Original V1 independently simulates sleeves, then blocks candidates. Rejected sleeve trades still affect its virtual cooldown; this is the archived spec behavior, not a causal joint production account.',
       'terminal_policy':'Final available close liquidation with fees and slippage',
       'spec_path':str(SPEC.relative_to(ROOT)),'spec_sha256':hashlib.sha256(SPEC.read_bytes()).hexdigest(),
       'frozen_sleeves':{a:[asdict(c) for c in s['configs']] for a,s in sleeves.items()}}
    out=OUT/label;out.mkdir(parents=True,exist_ok=True)
    curve.to_csv(out/'equity.csv',index=False)
    pd.DataFrame([{'asset':a,**asdict(t)} for a,t in selected]).to_csv(out/'trades.csv',index=False)
    marked=curve.set_index('ts').equity
    marked.index=marked.index-pd.Timedelta(nanoseconds=1)
    months=marked.resample('ME').last();ret=months.pct_change();ret.iloc[0]=months.iloc[0]-1
    ret.rename('return').to_csv(out/'monthly.csv')
    (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False,default=str)+'\n')
    print(json.dumps({k:summary[k] for k in ('scenario','return','max_drawdown','trades','candidate_trades','max_exposure')},default=str),flush=True)

if __name__=='__main__':
    for slip,label in ((.0004,'base'),(.0008,'slippage_8bps')):run(slip,label)
