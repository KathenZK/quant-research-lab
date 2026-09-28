"""Independent readback of CC comparison: reconstruct signals, trades and cash.

No complete scenario replay and no search is invoked. Checks use original price
snapshots, source specs, observed native funding events and exported ledgers.
"""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parent))
import iteration_common as inputs
import compare_cc_versions as implementation

ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parents[1]/"artifacts/iteration_comparison_20260911"
CC=BASE/"cc"
OUTPUT=BASE/"acceptance_cc_independent.json"
STEP=pd.Timedelta(minutes=15)
checks=[]


def hashfile(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(name,**fields):checks.append({"check":name,"status":"PASS",**fields})


def close(a,b,tol=1e-7):
    assert np.allclose(a,b,atol=tol,rtol=0,equal_nan=True),(np.asarray(a),np.asarray(b))


def main():
    manifests=json.loads((CC/"sources_manifest.json").read_text())["sources"]
    for src in manifests:assert hashfile(ROOT/src["path"])==src["sha256"],src["path"]
    record("all_original_spec_and_engine_source_hashes",count=len(manifests))
    plan=json.loads((CC/"cases_plan.json").read_text())["plan"]
    cases={x["case_id"]:x for x in plan["cases"]}
    rows=json.loads((CC/"results.json").read_text())
    assert len(cases)==20 and len(rows)==40
    assert {x["config"]["version"] for x in cases.values()}=={"V10","V13","V18","V21","V35"}
    assert len({(r["case_id"],r["funding_mode"]) for r in rows})==40
    assert all(pd.Timestamp(x["start"])==pd.Timestamp("2026-07-23T00:00Z") if x["window"]=="common" else pd.Timestamp(x["start"])==pd.Timestamp("2026-06-08T03:45Z") for x in cases.values())
    assert all(pd.Timestamp(x["end"])==inputs.END and x["fee"]==.001 for x in cases.values())
    record("frozen_5_milestones_20_plans_40_cost_variants",strategy_count=5,scenario_plans=20,rows=40)
    mapping={"lookback":"lookback","min_count":"min_count","allocation_atr_window":"allocation_atr","stop_loss_atr_window":"stop_atr","take_profit_atr_window":"take_atr","take_profit_atr_multiplier":"take_multiplier","min_take_profit_pct":"min_take","max_take_profit_pct":"max_take","trend_block_pct":"trend_limit","target_atr_pct":"target_atr","min_risk_multiplier":"min_risk","stop_loss_atr_multiplier":"stop_multiplier","min_stop_loss_pct":"min_stop","max_stop_loss_pct":"max_stop","long_allocation":"max_allocation","short_allocation":"max_allocation","cooldown_bars":"cooldown","opposite_signal_gap_bars":"opposite_gap","stop_loss_risk_multiplier":"risk_decay"}
    for src in manifests:
        if "version" not in src:continue
        text=(ROOT/src["path"]).read_text();numeric={}
        for line in text.splitlines():
            pieces=[p.strip().replace("`","") for p in line.split("|")]
            if len(pieces)>3:
                try:numeric[pieces[1]]=float(pieces[2])
                except ValueError:pass
        cfg=cases[src["version"]+"__fixed1x"]["config"]
        for key,value in mapping.items():assert numeric[key]==cfg[value],(src["version"],key)
        assert numeric["trend_window_bars"]==96
        record("independent_source_spec_values",version=src["version"],fields=len(mapping)+1)
    raw=inputs.load_prices("HYPE","15m").set_index("ts")
    funds=inputs.load_funding("HYPE")
    receipt=json.loads((CC/"input_verification.json").read_text())
    assert hashfile(ROOT/receipt["price_manifest"])==receipt["price_manifest_sha256"]
    auxiliary=ROOT/receipt["supplemental_mark_snapshot"]
    assert hashfile(auxiliary)==receipt["supplemental_mark_sha256"]
    mark=pd.read_parquet(auxiliary)
    if "ts" in mark:mark=mark.set_index("ts")
    mark.index=pd.to_datetime(mark.index,utc=True)
    mark=mark.loc[raw.index]
    for col in ("open","high","low","close","volume"):close(raw[col],mark[col],1e-9)
    assert not receipt["mark_catalog_trusted"] and not receipt["funding_window_verified"]
    record("api_price_and_auxiliary_mark_receipt_alignment",bars=len(raw),native_mark_missing_common=receipt["missing_native_settlement_mark_common"])
    prices=raw[["open","high","low","close"]].to_numpy(float)
    bull=(prices[:,3]>prices[:,0]).astype(int);bear=(prices[:,3]<prices[:,0]).astype(int)
    bulls=np.convolve(bull,np.ones(10,dtype=int),mode="full")[:len(bull)]
    bears=np.convolve(bear,np.ones(10,dtype=int),mode="full")[:len(bear)]
    signal=np.where(bulls>=8,-1,np.where(bears>=8,1,0));signal[:9]=0
    previous=np.r_[prices[0,3],prices[:-1,3]]
    tr=np.maximum.reduce([prices[:,1]-prices[:,2],abs(prices[:,1]-previous),abs(prices[:,2]-previous)])
    atr={n:pd.Series(tr).rolling(n,min_periods=n).mean().to_numpy()/prices[:,3] for n in (96,192,288,672)}
    trend=np.r_[np.full(96,np.nan),prices[96:,3]/prices[:-96,3]-1]
    actual=implementation.features(raw)
    assert np.array_equal(signal,actual.signal.to_numpy())
    for n in atr:close(atr[n],actual[f"atr{n}"],1e-12)
    close(trend,actual.trend96,1e-12)
    for colors,expected in (([1,1,0,1,1,0,1,1,1,1],-1),([1,1,1,1,1,0,1,1,1,1],-1),([1,1,1,1,1,1,1,1,1,1],-1),([1,0,1,0,1,0,1,0,1,0],0)):
        tiny=pd.DataFrame({"open":np.ones(10),"close":np.where(colors,2.,.5),"high":np.full(10,2.),"low":np.full(10,.5)})
        assert implementation.features(tiny).signal.iloc[-1]==expected
    dummy={"bear":np.array([1,1,1,0]),"bull":np.array([0,0,0,1])}
    assert implementation.early_reason(dummy,implementation.CONFIGS[-1],0,2,1) is None
    assert implementation.early_reason(dummy,implementation.CONFIGS[-1],0,3,1) is None
    record("independent_full_input_features_and_nonconsecutive_8of10",atr_windows=list(atr),count_semantics="at least 8 of10; not consecutive; doji excluded")
    perrun=[]
    for r in rows:
        case=cases[r["case_id"]];cfg=case["config"];funded=r["funding_mode"]=="observed_funding_estimate"
        path=ROOT/r["trades_path"]
        t=pd.read_csv(path);eq=pd.read_csv(ROOT/r["equity_path"]);months=pd.read_csv(ROOT/r["monthly_path"])
        for col in ("entry_ts","exit_ts","signal_bar_open","signal_close_ts","exit_bar_open"):t[col]=pd.to_datetime(t[col],utc=True)
        eq["ts"]=pd.to_datetime(eq.ts,utc=True);eq["bar_open"]=pd.to_datetime(eq.bar_open,utc=True)
        fundpath=path.with_name(path.name.replace("_trades.csv","_funding.csv"))
        try:fr=pd.read_csv(fundpath)
        except pd.errors.EmptyDataError:fr=pd.DataFrame()
        if len(fr):fr["ts"]=pd.to_datetime(fr.ts,utc=True,format="mixed");fr["entry_ts"]=pd.to_datetime(fr.entry_ts,utc=True,format="mixed")
        assert len(t)==r["trades"] and int((t.direction==1).sum())==r["long_trades"] and int((t.direction==-1).sum())==r["short_trades"]
        assert eq.ts.is_unique and eq.ts.iloc[0]==pd.Timestamp(case["start"]) and eq.ts.iloc[-1]==inputs.END
        assert eq.direction.iloc[0]==0 and eq.quantity.iloc[0]==0 and eq.quantity.iloc[-1]==0
        close(eq.equity.iloc[0],10000.)
        close(eq.equity.iloc[-1],10000*(1+r["return_pct"]/100))
        close(10000+t.net_pnl.sum(),eq.equity.iloc[-1])
        close(t.entry_fee.sum()+t.exit_fee.sum(),r["fee_quote"])
        close(t.entry_slippage_quote.sum()+t.exit_slippage_quote.sum(),r["slippage_quote"])
        close(t.funding_pnl.sum(),r["funding_pnl_quote"])
        close(10000+t.gross_pnl_before_slippage.sum()-r["fee_quote"]-r["slippage_quote"]+r["funding_pnl_quote"],eq.equity.iloc[-1])
        close(t.quantity*t.entry_fill,t.entry_equity*t.allocation)
        close(t.entry_fee,t.quantity*t.entry_fill*case["fee"])
        close(t.exit_fee,t.quantity*t.exit_fill*case["fee"])
        close(t.entry_fill,t.entry_reference*(1+t.direction*case["slip"]))
        close(t.exit_fill,t.exit_reference*(1-t.direction*case["slip"]))
        close(t.net_pnl,t.direction*t.quantity*(t.exit_fill-t.entry_fill)-t.entry_fee-t.exit_fee+t.funding_pnl)
        close(t.entry_equity,np.r_[10000.,t.exit_equity.iloc[:-1]])
        risk=1.;cash_changes=pd.Series(0.,index=eq.ts)
        expected_quantity=np.zeros(len(eq));expected_direction=np.zeros(len(eq));expected_unreal=np.zeros(len(eq))
        represented=set()
        for j,row in t.iterrows():
            si=int(raw.index.get_loc(row.signal_bar_open));ei=int(raw.index.get_loc(row.entry_ts));xi=int(raw.index.get_loc(row.exit_bar_open));d=int(row.direction)
            assert row.entry_ts==row.signal_close_ts==row.signal_bar_open+STEP
            assert row.signal_bar_open>=pd.Timestamp(case["start"]) and signal[si]==d and signal[si-1]!=d
            assert -d not in signal[si-8:si] and d*trend[si]>=-cfg["trend_limit"]
            if j:assert si>int(raw.index.get_loc(t.exit_bar_open.iloc[j-1]))+cfg["cooldown"]
            sl=float(np.clip(atr[cfg["stop_atr"]][si]*cfg["stop_multiplier"],cfg["min_stop"],cfg["max_stop"]))
            tp=float(np.clip(atr[cfg["take_atr"]][si]*cfg["take_multiplier"],cfg["min_take"],cfg["max_take"]))
            base=min(cfg["max_allocation"],cfg["max_allocation"]*cfg["target_atr"]/atr[cfg["allocation_atr"]][si])
            close(row.stop_pct,sl,1e-12);close(row.take_pct,tp,1e-12)
            close(row.base_allocation,base,1e-10);close(row.risk_at_entry,risk,1e-12)
            close(row.allocation,1. if case["size"]=="fixed1x" else base*risk,1e-12)
            close(row.stop_price,row.entry_fill*(1-d*sl));close(row.take_price,row.entry_fill*(1+d*tp))
            close(row.entry_reference,prices[ei,0])
            # No earlier protection touch can have been ignored while this trade remained open.
            hh=mark.mark_high.to_numpy()[ei:xi];ll=mark.mark_low.to_numpy()[ei:xi]
            touched=(ll<=row.stop_price)|(hh>=row.take_price) if d==1 else (hh>=row.stop_price)|(ll<=row.take_price)
            assert not touched.any(),(r["case_id"],j,"earlier protective touch ignored")
            if row.exit_reason in ("stop","take"):
                stop=mark.mark_low.iloc[xi]<=row.stop_price if d==1 else mark.mark_high.iloc[xi]>=row.stop_price
                take=mark.mark_high.iloc[xi]>=row.take_price if d==1 else mark.mark_low.iloc[xi]<=row.take_price
                assert stop if row.exit_reason=="stop" else take and not stop
                ref=(min(row.stop_price,prices[xi,0]) if d==1 else max(row.stop_price,prices[xi,0])) if stop else row.take_price
                close(row.exit_reference,ref)
                assert row.exit_ts==row.exit_bar_open+STEP
            elif row.exit_reason.startswith("early"):
                assert cfg["early_three"] and row.exit_timing=="open" and row.exit_ts==row.exit_bar_open
                if row.exit_reason=="early_main":
                    assert xi==ei+4
                    assert int(sum((bear if d==1 else bull)[ei+1:ei+4]))==3
                else:
                    assert cfg["counter"] and xi==ei+13
                    color=(bear if d==1 else bull) if row.exit_reason=="early_counter_opposite" else (bull if d==1 else bear)
                    assert int(sum(color[ei+1:ei+13]))>=9
                close(row.exit_reference,prices[xi,0])
            elif row.exit_reason=="terminal":
                assert row.exit_ts==inputs.END and row.exit_timing=="close"
                close(row.exit_reference,prices[xi,3])
            else:raise AssertionError(row.exit_reason)
            if row.exit_reason=="stop":risk=max(cfg["min_risk"],risk*cfg["risk_decay"])
            elif row.exit_reason=="take":risk=1.
            # Funding set independently follows the declared settlement ordering.
            held=funds.loc[funds.ts.gt(row.entry_ts)]
            held=held.loc[held.ts.le(row.exit_ts)] if row.exit_timing=="open" else held.loc[held.ts.lt(row.exit_bar_open+STEP)]
            expected_funding=0.
            if funded:
                observed=fr.loc[fr.entry_ts==row.entry_ts]
                assert set(observed.event_id)==set(held.event_id),(r["case_id"],j,"funding event mismatch")
                for event in held.itertuples():
                    native=float(event.mark_price);stamp=event.ts.floor("15min")
                    price=native if np.isfinite(native) and native>0 else float(raw.loc[stamp,"open"])
                    payment=-d*row.quantity*price*event.funding_rate
                    recorded=observed.loc[observed.event_id==event.event_id]
                    assert len(recorded)==1
                    close(recorded.funding_pnl.iloc[0],payment)
                    assert pd.Timestamp(recorded.ts.iloc[0])==event.ts
                    close(recorded.settlement_mark.iloc[0],price)
                    assert bool(recorded.native_mark_available.iloc[0])==bool(np.isfinite(native) and native>0)
                    expected_funding+=payment;represented.add(event.event_id)
                    cash_changes.loc[stamp+STEP]+=payment
            close(row.funding_pnl,expected_funding)
            cash_changes.loc[row.entry_ts+STEP]-=row.entry_fee
            posting=row.exit_bar_open+STEP
            cash_changes.loc[posting]+=row.price_pnl_after_slippage-row.exit_fee
            mask=(eq.bar_open>=row.entry_ts)&(eq.bar_open<row.exit_bar_open)
            assert not np.any(expected_quantity[mask]>0)
            expected_quantity[mask]=row.quantity;expected_direction[mask]=d
            if mask.any():expected_unreal[mask]=d*row.quantity*(raw.loc[eq.loc[mask,"bar_open"],"close"].to_numpy()-row.entry_fill)
        close(eq.cash,10000+cash_changes.cumsum())
        close(eq.quantity,expected_quantity);close(eq.direction,expected_direction)
        close(eq.unrealized_pnl,expected_unreal)
        close(eq.equity,10000+cash_changes.cumsum()+expected_unreal)
        close(-float((eq.equity/eq.equity.cummax()-1).min())*100,r["max_drawdown_pct"])
        expected_month=[];previous_equity=10000.
        for month,g in eq.loc[eq.bar_open.notna()].groupby(eq.bar_open.dt.strftime("%Y-%m")):
            last=float(g.equity.iloc[-1]);expected_month.append((month,(last/previous_equity-1)*100));previous_equity=last
        assert list(months.month)==[x[0] for x in expected_month]
        close(months.return_pct,[x[1] for x in expected_month])
        close(float((1+months.return_pct/100).prod()*10000),eq.equity.iloc[-1])
        assert len(fr)==r["observed_settlement_events_held"]
        assert sum(t.exit_reason=="terminal")==r["terminal_trades"]
        perrun.append({"case_id":r["case_id"],"funding_mode":r["funding_mode"],"trades_checked":len(t),"equity_rows_reconstructed":len(eq),"funding_rows_checked":len(fr),"source_signal_ATR_sizing_exit_rules":"PASS","independent_cash_quantity_equity_months":"PASS"})
    record("all_saved_runs_independent_ledger_reconstruction",runs=len(perrun),trades_checked=sum(r["trades_checked"] for r in perrun),funding_rows_checked=sum(r["funding_rows_checked"] for r in perrun))
    limitations=["5 milestone versions, 20 predeclared scenario plans and 40 funding variants are not40 strategies.","Common next-open and fixed-quantity diagnostics differ from original close/implicit-rebalance models; V35 source writes current-close early exits.","Auxiliary mark high/low is receipt/hash aligned but not a trusted catalog feed; 15m bars cannot identify exact intrabar fill time.","Boundary settlements precede old-position open exits; milliseconds after open follow entry/exit. Intrabar protective evaluation after those events is an explicit unresolved ordering approximation.","Native settlement mark missing for135 common-window observations; trade-open proxy and missing settlement calendar prevent verified full-net claims.","Equal1x entry notional does not make stop risk equal; drawdown is15m closing account equity."]
    OUTPUT.write_text(json.dumps({"status":"PASS","reviewed_script_sha256":hashfile(implementation.__file__),"results_sha256":hashfile(CC/"results.json"),"cases_plan_sha256":hashfile(CC/"cases_plan.json"),"checks":checks,"runs":perrun,"limitations":limitations,"scope":"Read-only independent reconstruction from saved ledgers and frozen inputs; no complete scenario replay."},indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"status":"PASS","runs":len(perrun),"checks":len(checks)}))


if __name__=="__main__":
    try:main()
    except Exception as exc:
        OUTPUT.write_text(json.dumps({"status":"FAIL","checks_completed":checks,"error_type":type(exc).__name__,"error":str(exc)},indent=2,ensure_ascii=False)+"\n")
        raise
