"""Causality and independent chain checks for the fixed HYPE replay."""
from __future__ import annotations
import importlib
import json
from dataclasses import replace
import numpy as np
import pandas as pd
import hype_legacy_replay as replay
from audit_common import load_prices,load_funding


def x_features(frame):
    h=importlib.import_module("research_hype_v17_hybrid_ablation")
    return h.add_v17_indicators(h.add_structure_features(h.add_oscillator_features(h.add_volume_features(h.build_features(frame.reset_index()))))).set_index("ts")


def main():
    frame=replay.frame_with_index(load_prices("HYPE","15m"))
    tb=importlib.import_module("research_hype_ema_tb_v35_profit_floor")
    ab=importlib.import_module("research_hype_ema_tb_v35_full_ablation_recent_tune")
    ens=importlib.import_module("research_hype_15m_tb_mii_ensemble_backtest")
    v12=ens.mii12
    cc=importlib.import_module("research_hype_cc_v35_maker_entry_audit")
    checks=[]
    for name,builder in (
        ("ema_x",x_features),
        ("ema_tb",lambda f:ab.build_signals(tb.build_features(f,tb.V35Config()),tb.V35Config(),ab.SignalFlags(short_use_h1_ema=False))),
        ("mii",lambda f:v12.evolution.add_rsi_features(v12.evolution.add_features(f.reset_index(),[])).set_index("ts")),
        ("cc",cc.build_features),
    ):
        full=builder(frame)
        for date in ("2026-07-10T09:45:00Z","2026-08-01T16:15:00Z","2026-09-04T22:30:00Z"):
            prefix=builder(frame.loc[:date])
            numeric=prefix.select_dtypes(include=[np.number,bool]).columns
            a=prefix[numeric].tail(16).to_numpy(float)
            b=full.loc[prefix.index[-16:],numeric].to_numpy(float)
            good=bool(np.allclose(a,b,rtol=1e-11,atol=1e-11,equal_nan=True))
            checks.append({"family":name,"cutoff":date,"feature_columns":len(numeric),"compared_rows":16,"passed":good})
            assert good,(name,date)
    start=pd.Timestamp(replay.REGISTRATIONS["HYPE-15M-MII-V1.4A"]["start"])
    context=replay.mii_context(frame)
    candidates=replay.mii_candidates(frame,context,start,1.4,3.0)
    config=replace(tb.V35Config(),warmup_bars=int(frame.index.searchsorted(start)))
    features=replay.post_features(ab.build_signals(tb.build_features(frame,config),config,ab.SignalFlags()),start)
    run=ens.run_account("mii_chain_check",frame,pd.Series(0.0,index=frame.index),features,config,candidates,enable_v35=False,enable_mii=True,mii_label="mii")
    gate=ens.mii_chain_gate(run,list(candidates.values()),config.warmup_bars,replace(v12.BASE_CONFIG.filter,min_rvol96=0.85))
    summary=json.loads((replay.OUT/"summary.json").read_text())
    artifact_checks=[]
    for row in summary:
        equity=pd.read_csv(replay.ROOT/row["equity_file"])
        reconstructed=float((1+equity["return"]).prod())
        expected=1+row["return_pct"]/100
        assert abs(reconstructed-expected)<1e-10
        monthly=np.prod([1+v/100 for v in row["monthly_return_pct"].values()])
        assert abs(monthly-expected)<1e-10
        artifact_checks.append({"strategy":row["strategy"],"variant":row["variant"],"bars":len(equity),"return_chain_abs_difference":abs(reconstructed-expected),"monthly_chain_abs_difference":abs(monthly-expected),"passed":True})
    funding=load_funding("HYPE")
    windows=[]
    for key,registration in replay.REGISTRATIONS.items():
        data=funding.loc[funding.ts.ge(pd.Timestamp(registration["start"])) & funding.ts.lt(frame.index[-1]+pd.Timedelta(minutes=15))]
        windows.append({"strategy":key,"observed_events":len(data),"first_observed_event":data.ts.min(),"last_observed_event":data.ts.max(),"max_observed_interval_hours":float(data.ts.diff().dt.total_seconds().max()/3600),"missing_mark_price":int(data.mark_price.isna().sum()) if "mark_price" in data else None,"coverage_verified":False})
    replay.write_json(replay.OUT/"verification.json",{"feature_prefix_checks":checks,"mii_canonical_chain_gate":gate,"artifact_checks":artifact_checks,"funding_observation_windows":windows,"passed":True})
    old=json.loads((replay.OUT/"source_sha256.json").read_text())
    replay.write_json(replay.OUT/"source_sha256.json",{**old,**replay.source_hashes()})
    print(json.dumps({"feature_checks":len(checks),"mii_chain_gate":gate,"artifact_checks":len(artifact_checks),"passed":True},indent=2))


if __name__=="__main__":
    main()
