"""Frozen early/latest comparisons. Never invoke original search/load entrypoints.

The prepare phase imports fixed configurations and hashes their source material;
run is dispatched after root confirms the public input freeze. All outputs stay in this
comparison's directory. Original families and the previous audit are read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FAMILY = HERE.parent
OUT = FAMILY / "artifacts/iteration_comparison_20260911/ar_mmtf"
START = pd.Timestamp("2026-07-23T00:00:00Z")
END = pd.Timestamp("2026-09-05T15:00:00Z")
PREFIX_END = pd.Timestamp("2026-08-15T00:00:00Z")
FEE = .001
SCENARIOS = {"fixed_1x": (True, .0004), "original_sizing": (False, .0004), "fixed_1x_slippage_8bps": (True, .0008)}
sys.path.insert(0, str(HERE))
import audit_common as common
import iteration_common  # binds the same verified helper to this run's new API snapshots
import other_assets_replay as other
import hype_other_replay as hype


def js(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    return other.load_module(ROOT / path, name)


SOURCES: set[Path] = set()


def source(path):
    p = ROOT / path
    if not p.is_file():
        raise FileNotFoundError(p)
    SOURCES.add(p)
    return p


def ar_configs(asset, version):
    base = f"research/{asset.lower()}/1h-adaptive-regime"
    engine = load("research/_shared-kernels/1h-adaptive-regime-search/v1/engine.py", "comparison_ar_shared")
    special = None
    priorities = None
    if asset == "HYPE":
        m = load(base + "/scripts/audit_hype_1h_ar_v4_pressure_optimization.py", "comparison_hype_ar")
        if version == "V1":
            cfgs = (m.v2.di_to_base(m.v2.DICleanConfig(), "HYPE_1H_AR_V1_DI"), m.v2.stoch_to_base(m.v2.StochCleanConfig(), "HYPE_1H_AR_V1_STOCH"))
        else:
            cfgs = m.v4_engine_configs()
        cfgs = tuple(engine.StrategyConfig(**asdict(c)) for c in cfgs)
        special = m
        priorities = (1., 0.)
    elif version == "V1" and asset == "BNB":
        text = source(base + "/specs/bnb-1h-ar-v1-parameter-spec-2026-07-06.md").read_text()
        cfgs = tuple(engine.StrategyConfig(**json.loads(b)) for b in re.findall(r"```json\n(.*?)\n```", text, re.S))
        priorities = (2.1431344645719372, 1.8729418183646944)
    elif version == "V1":
        m = load(base + f"/scripts/{asset.lower()}_1h_ar_v1.py", f"comparison_{asset}_v1")
        cfgs = m.v1_configs(engine)
    else:
        cfgs, priorities, special = other.frozen_configs(asset, engine)
    return engine, cfgs, priorities, special


def mmtf_configs(tf, version):
    base = f"research/hype/{tf}-multi-mechanism-trend-following"
    e = hype.mod(base + "/scripts/mmtf_engine.py", "mmtf_engine")
    if version == "V1":
        p = source(base + f"/artifacts/hype_{tf}_mmtf_v1_search_2026-07-22.json")
        frozen = json.loads(p.read_text())
        cfg = e.config_from_dict(frozen["config"])
        assert e.config_sha256(cfg) == frozen["config_sha256"]
    else:
        a = hype.mod(base + "/scripts/mmtf_v2.py", "mmtf_v2")
        p = source(base + f"/artifacts/hype_{tf}_mmtf_v2_clean_tune_2026-07-22.json")
        frozen = json.loads(p.read_text())["v3_tuned_freeze"]
        cfg = a.to_engine_config(a.clean_from_dict(frozen["config"]))
        assert e.config_sha256(cfg) == frozen["engine_config_sha256"]
    return e, cfg


def keltner_module():
    return hype.mod("research/hype/30m-keltner-trend-breakout/scripts/audit_hype_30m_keltner_v3_latest.py", "comparison_keltner")


def plans():
    result = []
    dates = {"BTC": ("2026-07-02", "2026-07-07"), "ETH": ("2026-07-03", "2026-07-13"), "SOL": ("2026-07-03", "2026-07-13"), "BNB": ("2026-07-06", "2026-07-07"), "TRX": ("2026-07-05", "2026-07-06"), "HYPE": ("2026-07-02", "2026-07-07")}
    latest = {"BTC":"V4", "ETH":"V4", "SOL":"V3", "BNB":"V3", "TRX":"V3", "HYPE":"V4"}
    changes = {"BTC":"Keltner/CCI filters, target, cooldown and sizing changed; V4 is V3's clean equivalent.", "ETH":"BB/RSI thresholds and sizing changed; V4 narrows the high-win configuration.", "SOL":"V1 Donchian+BB-reversion replaced by Donchian+VWAP arm-confirm-expire in V3; mechanism and sizing both changed.", "BNB":"Same EMA-pullback+wick-reject components, thresholds/exits/sizing tuned.", "TRX":"MACD+Stoch retained, active thresholds/exits/sizing tuned; V2 only cleans V1.", "HYPE":"DI/Stoch entry filters, stop/holding/cooldown changed; original 3x/2x component sizing retained."}
    for asset in dates:
        base = f"research/{asset.lower()}/1h-adaptive-regime"
        source(base + f"/{asset.lower()}-1h-ar-core-ledger.md")
        if asset == "SOL": early_spec = base + "/scripts/sol_1h_ar_v1.py"
        elif asset == "BNB": early_spec = base + "/specs/bnb-1h-ar-v1-parameter-spec-2026-07-06.md"
        else: early_spec = base + f"/specs/{asset.lower()}-1h-ar-v1-baseline-spec.md"
        if asset == "HYPE": late_spec = base + "/specs/hype-1h-ar-v4-pruned-tuned-baseline-spec.md"
        else: late_spec = base + "/" + other.REGISTERED[asset][2]
        for version, date, spec in (("V1", dates[asset][0], early_spec), (latest[asset], dates[asset][1], late_spec)):
            source(spec)
            e, cfgs, priorities, _ = ar_configs(asset, version)
            result.append({"family":f"{asset}_1h_AR", "asset":asset, "kind":"ar", "timeframe":"1h", "version":version, "role":"early" if version == "V1" else "latest", "registration_date":date, "spec":spec, "spec_sha256":sha(ROOT/spec), "configs":[asdict(c) for c in cfgs], "priorities":priorities, "missing_priority_policy":"both orders must produce identical requested-period trade path, otherwise fail", "change_description":changes[asset], "source_recovery":"HYPE V1 active fields recovered from complete spec and original clean-equivalent converters; other V1 values from literal frozen dictionaries/spec, no random search"})
    for tf in ("1h", "15m"):
        base = f"research/hype/{tf}-multi-mechanism-trend-following"
        source(base + "/decision-log.md")
        source(base + f"/specs/hype-{tf}-mmtf-v2-clean-equivalent-spec.md")
        for version in ("V1", "V3"):
            spec = base + f"/specs/hype-{tf}-mmtf-{'v1-original-baseline' if version=='V1' else 'v3-tuned'}-spec.md"
            source(spec)
            e,cfg = mmtf_configs(tf,version)
            result.append({"family":f"HYPE_{tf}_MMTF", "asset":"HYPE", "kind":"mmtf", "timeframe":tf, "version":version, "role":"early" if version=="V1" else "latest", "registration_date":"2026-07-22", "spec":spec, "spec_sha256":sha(ROOT/spec), "config":asdict(cfg), "config_sha256":e.config_sha256(cfg), "v2_policy":"clean-equivalent V2 not independently searched or counted", "change_description":"1h changes slow EMA/target/trailing/cooldown and leverage; 15m changes hard stop 6 to 8 ATR and leverage 2x to 3x, retaining entry rules", "corrections":["15m RVOL uses 96 bars per original engine/spec; previous audit helper incorrectly used 48", "fees use actual fill notional, unlike legacy fixed-entry-notional exit fee"]})
    base = "research/hype/30m-keltner-trend-breakout"
    source(base + "/hype-30m-keltner-trend-breakout-core-ledger.md")
    m = keltner_module()
    for version, date in (("V2.1", "2026-07-10"), ("V3", "2026-07-13")):
        spec = base + f"/specs/hype-30m-keltner-trend-breakout-{'v2-1' if version=='V2.1' else 'v3'}-spec.md"
        source(spec)
        result.append({"family":"HYPE_30m_Keltner", "asset":"HYPE", "kind":"keltner", "timeframe":"30m", "version":version, "role":"early" if version=="V2.1" else "latest", "registration_date":date, "spec":spec, "spec_sha256":sha(ROOT/spec), "config":asdict(m.dynamic.v21_config()), "filters":[] if version=="V2.1" else ["ATR84/entry<=0.0125", "directional close location>=0.65"], "change_description":"V3 adds volatility cap and directional close-location filters; original sizing/exits unchanged", "early_selection":"V2.1 is first repository registered version; external V2.0 is an observation only"})
    return result


def prepare():
    cases = plans()
    for module in list(sys.modules.values()):
        p = getattr(module, "__file__", None)
        if p and str(p).startswith(str(ROOT / "research")) and str(p).endswith(".py"):
            SOURCES.add(Path(p).resolve())
    SOURCES.add(common.INPUTS / "manifest.json")
    SOURCES.discard(Path(__file__).resolve())
    js(OUT / "sources_manifest.json", {"files":{str(p.relative_to(ROOT)):sha(p) for p in sorted(SOURCES)}, "inputs":"Previous audit API-derived snapshots; each read verifies the input manifest SHA."})
    js(OUT / "cases_plan.json", {"frozen_at":pd.Timestamp.now(tz="UTC"), "start":START,"end":END,"cases":cases,"scenarios":SCENARIOS,"fee_per_fill":FEE,"initial_state":"flat; no signal timestamp before start; numerical indicators use full verified warmup", "funding":"Observed events applied to fixed entry notional estimate, separately reported excluding funding; not verified full net", "ar_execution":"Exact one-net-position across components; rejected occupied signals do not create phantom component cooldown", "holding_exposure":"Each entry fixed to 1x entry equity; quantity is held fixed thereafter; no rebalance to chase mark-to-market exposure", "prefix_check":PREFIX_END,"no_retuning":True})
    print(json.dumps({"prepared_cases":len(cases),"families":len({x['family'] for x in cases}),"sources":len(SOURCES)}),flush=True)


def verify_sources():
    for rel, digest in json.loads((OUT / "sources_manifest.json").read_text())["files"].items():
        if sha(ROOT / rel) != digest:
            raise RuntimeError(f"Frozen source drift: {rel}")


def canonical_book(e, frame, funding, tf):
    book = hype.build_book(e, frame, funding, "1h" if tf == "1h" else "15min")
    window = 48 if tf == "1h" else 96
    expected = frame.volume / frame.volume.shift(1).rolling(window, min_periods=window).median()
    book.rvol = expected.to_numpy(float)
    engine_text = Path(e.__file__).read_text()
    assert f"rolling({window}, min_periods={window})" in engine_text
    assert np.allclose(book.rvol, expected, equal_nan=True)
    return book


def ar_signal(e, frame, cfg, case, leg, special):
    if case["asset"] == "SOL" and case["version"] == "V3" and leg == 1:
        # Numerical features have full history; arm/expiry trade state starts flat.
        dev = frame[f"vwap_dev_atr{cfg.indicator_window}"].to_numpy(float)
        events = np.zeros(len(frame), dtype=np.int8)
        if cfg.side_mode in ("long", "both"): events[e.crossed_up(dev, -cfg.band_k)] = 1
        if cfg.side_mode in ("short", "both"): events[e.crossed_down(dev, cfg.band_k)] = -1
        events = e.apply_filters(frame, events, cfg)
        events[frame.ts.lt(START)] = 0
        positive = special.confirmation_mask(frame, 1, "roc6_macd")
        negative = special.confirmation_mask(frame, -1, "roc6_macd")
        valid_positive = e.apply_filters(frame, np.ones(len(frame), dtype=np.int8), cfg)
        valid_negative = e.apply_filters(frame, -np.ones(len(frame), dtype=np.int8), cfg)
        signal = np.zeros(len(frame), dtype=np.int8)
        side = 0; arm = -1
        for i in range(int(frame.ts.searchsorted(START)), len(frame)):
            if events[i]: side, arm = int(events[i]), i
            if i > arm + 3: side = 0
            if side and i > arm and bool((positive if side > 0 else negative)[i]) and (valid_positive if side > 0 else valid_negative)[i]:
                signal[i] = side; side = 0
    else:
        signal = e.build_signal(frame, cfg)
    signal[frame.ts.lt(START).to_numpy()] = 0
    return signal


def exact_merge(tagged, cfgs, priorities):
    tagged = sorted(tagged, key=lambda x: (x[0].entry_i, -priorities[x[1]], x[0].signal_i))
    blocked = -1; cooldown = [-1] * len(cfgs); result = []
    for trade, leg in tagged:
        if trade.entry_i <= blocked or trade.entry_i <= cooldown[leg]: continue
        result.append((trade, leg)); blocked = trade.exit_i
        cooldown[leg] = trade.exit_i + cfgs[leg].cooldown_bars
    return result


def raw_ar(case, fixed, slip, end):
    e, configs, priorities, special = ar_configs(case["asset"], case["version"])
    assert [asdict(c) for c in configs] == case["configs"]
    configs = tuple(replace(c, sizing_kind="fixed", fixed_leverage=1., max_leverage=1.) if fixed else c for c in configs)
    assert all(c.entry_delay_bars >= 1 for c in configs)
    raw = common.load_prices(case["asset"], "1h").reset_index(drop=True)
    raw = raw.loc[raw.ts < end].reset_index(drop=True)
    funding = common.load_funding(case["asset"])
    raw = raw.loc[raw.ts >= funding.ts.min().ceil("h")].reset_index(drop=True)
    full = e.add_features(raw, funding)
    if case["asset"] == "HYPE": full = special.v3ab.ensure_extra_macd_features(full)
    assert full.loc[full.ts.ge(START), "last_funding_rate"].notna().all()
    signals = [ar_signal(e,full,c,case,j,special) for j,c in enumerate(configs)]
    nstart = int(full.ts.searchsorted(START))
    frame = full.iloc[nstart:].reset_index(drop=True)
    signals = [s[nstart:] for s in signals]
    sentinel = frame.iloc[-1:].copy(); sentinel["ts"] = end
    for key in ("open", "high", "low", "close"): sentinel[key] = float(frame.close.iloc[-1])
    terminal = pd.concat([frame,sentinel],ignore_index=True)
    ft,fc = e.funding_prefix(funding)
    e.FEE_PER_FILL, e.SLIPPAGE_PER_FILL = FEE, slip
    tagged = []
    for leg,(cfg,sig) in enumerate(zip(configs,signals)):
        for i in np.flatnonzero(sig):
            if i + cfg.entry_delay_bars >= len(frame): continue
            one = np.zeros(len(terminal),dtype=np.int8); one[i] = sig[i]
            values = e.simulate_trades(terminal,one,cfg,ft,fc)
            if values: tagged.append((values[0],leg))
    merged = exact_merge(tagged,configs,priorities or (1.,0.))
    reverse = exact_merge(tagged,configs,(0.,1.))
    signature = lambda xs: [(x.entry_i,x.exit_i,x.side,x.entry_price,x.exit_price,x.config) for x,_ in xs]
    equivalent = signature(merged) == signature(reverse)
    if priorities is None and not equivalent: raise RuntimeError(f"Missing frozen priority changes {case['family']} {case['version']} path")
    trades = []
    for native,leg in merged:
        d = asdict(native)
        terminal_close = native.exit_ts == end
        open_exit = native.exit_reason in ("timeout_open","stop_gap_open","target_gap_or_open")
        valuation = native.exit_ts if open_exit or terminal_close else native.exit_ts + pd.Timedelta(hours=1)
        raw_entry = native.entry_price / (1 + native.side * slip)
        raw_exit = native.exit_price / (1 - native.side * slip)
        trades.append({"signal_ts":native.signal_ts,"entry_ts":native.entry_ts,"entry_delay_bars":configs[leg].entry_delay_bars,"exit_ts":valuation,"exit_bar_open":native.exit_ts,"funding_until":native.exit_ts,"side":native.side,"entry_price":native.entry_price,"exit_price":native.exit_price,"raw_entry":raw_entry,"raw_exit":raw_exit,"leverage":native.exposure,"exit_reason":"terminal" if terminal_close else native.exit_reason,"component":str(leg),"native":d})
    # Retain exact versus old independent-leg merge path evidence, without choosing by PnL.
    independent = []
    for leg,(cfg,sig) in enumerate(zip(configs,signals)):
        independent.append(e.simulate_trades(terminal,np.r_[sig,0],cfg,ft,fc))
    old = e.merge_trade_sets(*independent,*(priorities or (1.,0.)))
    details = {"priority_orders_path_equal":equivalent,"fixed_priorities":priorities,"raw_event_count":len(tagged),"exact_joint_count":len(trades),"independent_merge_count":len(old),"independent_merge_same_path":signature(merged)==signature([(t,0) for t in old]),"frozen_entry_delays":[c.entry_delay_bars for c in configs],"feature_assertions":{"closed_signal_then_frozen_delay_open":True,"configs_match_frozen_plan":True,"known_funding_at_active_bars":True}}
    return trades,raw,funding,details


def raw_mmtf(case,fixed,slip,end):
    e,cfg = mmtf_configs(case["timeframe"],case["version"])
    assert asdict(cfg)==case["config"]
    if fixed: cfg=replace(cfg,leverage=1.)
    raw=common.load_prices("HYPE",case["timeframe"]).reset_index(drop=True)
    raw=raw.loc[raw.ts<end].reset_index(drop=True); funding=common.load_funding("HYPE")
    book=canonical_book(e,raw,funding,case["timeframe"])
    r=e.run_backtest(book,cfg,start_ts=START,end_ts=end,slippage_per_fill=slip,detailed=True)
    duration=pd.Timedelta(hours=1) if case["timeframe"]=="1h" else pd.Timedelta(minutes=15)
    trades=[]
    for d in r.trades:
        exitbar=pd.Timestamp(d["exit_ts"]); terminal=d["exit_reason"]=="terminal"
        open_exit=d["exit_reason"] in ("timeout","trend_exit","stop_gap_open","take_profit_gap")
        valuation=end if terminal else exitbar if open_exit else exitbar+duration
        side=int(d["side"])
        trades.append({"signal_ts":pd.Timestamp(d["signal_ts"]),"entry_ts":pd.Timestamp(d["entry_ts"]),"exit_ts":valuation,"exit_bar_open":exitbar,"funding_until":end if terminal else exitbar,"side":side,"entry_price":d["entry_price"],"exit_price":d["exit_price"],"raw_entry":d["entry_price"]/(1+side*slip),"raw_exit":d["exit_price"]/(1-side*slip),"leverage":d["leverage"],"exit_reason":d["exit_reason"],"component":"0","native":d})
    details={"native_metrics":r.metrics,"feature_assertions":{"rvol_window":48 if case["timeframe"]=="1h" else 96,"rvol_formula_matches_spec_and_engine":True,"config_sha_verified":True},"native_execution_limitations":"Original raw-entry ATR brackets retained; gap target paid at target, same-bar stop-first; exit-bar funding excluded for unknown intrabar event order."}
    return trades,raw,funding,details


def raw_keltner(case,fixed,slip,end):
    m=keltner_module(); raw15=common.load_prices("HYPE","15m")
    raw15=raw15.loc[raw15.ts<end].reset_index(drop=True);funding=common.load_funding("HYPE")
    b30,q30=m.base.aggregate_ohlcv(raw15,freq="30min",phase_min=0,expected_rows=2)
    h1,q1=m.base.aggregate_ohlcv(raw15,freq="60min",phase_min=0,expected_rows=4)
    cfg=m.dynamic.v21_config();assert asdict(cfg)==case["config"]
    assert (cfg.leverage_atr,cfg.h1_ema_slow,cfg.h1_slope_lag)==(84,44,5)
    f=m.dynamic.v21_features(b30,h1,cfg)
    if case["version"]=="V3":
        before=f.copy(); f=m.regime.add_features(f)
        spec=m.regime.FilterSpec("combo","pair",(),(m.regime.FilterSpec("volatility","atr_pct",(0.,.0125)),m.regime.FilterSpec("quality","close_location",(.65,))))
        f=m.regime.apply_filter(f,spec)
    if fixed:cfg=replace(cfg,min_leverage=1.,max_leverage=1.)
    execution=m.strict.ExecutionConfig(fee_rate=FEE,slippage_rate=slip)
    r=m.strict.simulate(case["version"],f,funding,cfg,execution,start_ts=START,end_ts=end)
    trades=[]
    for d in r.trades.to_dict("records"):
        side=1 if d["direction"]=="long" else -1
        bar=pd.Timestamp(d["exit_ts"]);terminal=d["exit_reason"]=="window_end"
        open_exit=d["exit_reason"] in ("stop_gap_open","target_gap_open")
        timeclose=d["exit_reason"]=="time_close"
        valuation=end if terminal else bar if open_exit else bar+pd.Timedelta(minutes=30)
        trades.append({"signal_ts":pd.Timestamp(d["entry_ts"])-pd.Timedelta(minutes=30),"entry_ts":pd.Timestamp(d["entry_ts"]),"exit_ts":valuation,"exit_bar_open":bar,"funding_until":valuation if terminal or timeclose else bar,"side":side,"entry_price":d["entry_fill"],"exit_price":d["exit_fill"],"raw_entry":d["raw_entry_price"],"raw_exit":d["raw_exit_price"],"leverage":d["leverage"],"exit_reason":"terminal" if terminal else d["exit_reason"],"component":"0","native":d})
    raw=f.reset_index().rename(columns={f.index.name or "index":"ts"})
    details={"native_metrics":r.metrics,"aggregation":{"30m":q30,"1h":q1},"feature_assertions":{"atr_sizing_window":cfg.leverage_atr,"h1_slow_ema":cfg.h1_ema_slow,"h1_slope_lag":cfg.h1_slope_lag,"filters":case["filters"],"complete_30m_from_two_15m":True},"funding_bridge":"Native Keltner mark/notional estimate is retained in native metrics; comparison uses common fixed-entry-notional event estimate."}
    return trades,raw,funding,details


def account(trades,raw,funding,tf,end):
    duration=pd.Timedelta(minutes={"1h":60,"15m":15,"30m":30}[tf])
    curve=pd.DataFrame({"ts":[START,*list(raw.loc[(raw.ts>=START)&(raw.ts<end),"ts"]+duration)]})
    curve=curve.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    assert curve.ts.iloc[-1]==end
    curve["equity"]=1.;curve["equity_excluding_funding"]=1.;curve["position_qty"]=0.;curve["entry_leverage"]=0.
    curve["entry_notional"]=0.;curve["unrealized_pnl"]=0.
    closes=raw.set_index("ts").close
    eq=ex=1.;rows=[]
    for number,t in enumerate(trades,1):
        side=t["side"];entry=t["entry_price"];exit_=t["exit_price"];lev=t["leverage"]
        assert t["signal_ts"]>=START and t["entry_ts"]==t["signal_ts"]+duration*t.get("entry_delay_bars",1)
        assert t["entry_ts"]<end and t["exit_ts"]<=end
        if rows:assert t["entry_ts"]>=pd.Timestamp(rows[-1]["exit_ts"])
        entryeq=eq;entryex=ex;notional=entryeq*lev;qty=notional/entry
        rates=funding.loc[(funding.ts>=t["entry_ts"])&(funding.ts<t["funding_until"]),"funding_rate"]
        funding_rate=float(rates.sum());funding_amount=-side*notional*funding_rate
        entryfee=notional*FEE;exitfee=qty*exit_*FEE
        gross=side*qty*(exit_-entry)
        price_raw=side*qty*(t["raw_exit"]-t["raw_entry"])
        slip_amount=price_raw-gross
        eq=entryeq+gross-entryfee-exitfee+funding_amount
        return_ex=lev*(side*(exit_/entry-1)-FEE*(1+exit_/entry))
        ex=entryex*(1+return_ex)
        if eq<=0 or ex<=0:raise RuntimeError("Account insolvency requires explicit liquidation path")
        active=(curve.ts>t["entry_ts"])&(curve.ts<t["exit_ts"])
        for idx in np.flatnonzero(active):
            ts=curve.ts.iloc[idx];price=float(closes.loc[ts-duration])
            rate=float(funding.loc[(funding.ts>=t["entry_ts"])&(funding.ts<min(ts,t["funding_until"])),"funding_rate"].sum())
            unrealized=side*qty*(price-entry)
            curve.loc[idx,["equity","equity_excluding_funding","position_qty","entry_leverage","entry_notional","unrealized_pnl"]]=[entryeq-entryfee+unrealized-side*notional*rate,entryex*(1+lev*(side*(price/entry-1)-FEE)),side*qty,lev,notional,unrealized]
        after=curve.ts>=t["exit_ts"]
        curve.loc[after,["equity","equity_excluding_funding"]]=[eq,ex]
        row={k:v for k,v in t.items() if k!="native"}
        row.update({"trade_id":number,"entry_equity":entryeq,"exit_equity":eq,"entry_notional":notional,"quantity":qty,"entry_fee":entryfee,"exit_fee":exitfee,"slippage_cost":slip_amount,"raw_price_pnl":price_raw,"price_pnl_after_slippage":gross,"funding_estimate":funding_amount,"funding_event_count":len(rates),"return":eq/entryeq-1,"return_excluding_funding":return_ex})
        rows.append(row)
    curve["drawdown"]=curve.equity/curve.equity.cummax()-1
    monthly=[];prev=prevex=1.
    for month,g in curve.iloc[1:].groupby((curve.ts.iloc[1:]-pd.Timedelta(nanoseconds=1)).dt.strftime("%Y-%m")):
        value=float(g.equity.iloc[-1]);valueex=float(g.equity_excluding_funding.iloc[-1])
        monthly.append({"month":month,"return":value/prev-1,"return_excluding_funding":valueex/prevex-1,"ending_equity":value})
        prev,prevex=value,valueex
    totals={k:sum(r[k] for r in rows) for k in ("entry_fee","exit_fee","slippage_cost","raw_price_pnl","price_pnl_after_slippage","funding_estimate")}
    directions={}
    for side in (1,-1):
        selected=[r for r in rows if r["side"]==side]
        directions["long" if side==1 else "short"]={"trades":len(selected),"win_rate":float(np.mean([r["return"]>0 for r in selected])) if selected else None,"account_pnl_contribution":sum(r["exit_equity"]-r["entry_equity"] for r in selected),"geometric_return_of_selected_trade_returns":float(np.prod([1+r["return"] for r in selected])-1)}
    monthly_product=float(np.prod([1+m["return"] for m in monthly]))
    assert abs(monthly_product-eq)<1e-10
    assert abs(eq-(1+totals["price_pnl_after_slippage"]-totals["entry_fee"]-totals["exit_fee"]+totals["funding_estimate"]))<1e-10
    assert abs(curve.equity.iloc[-1]-eq)<1e-10
    assert curve.ts.is_unique and curve.equity.notna().all()
    summary={"return":eq-1,"return_excluding_funding":ex-1,"final_equity":eq,"max_drawdown":float(curve.drawdown.min()),"trades":len(rows),"win_rate":float(np.mean([r["return"]>0 for r in rows])) if rows else None,"max_entry_leverage":max([r["leverage"] for r in rows],default=0.),"terminal_closes":sum(r["exit_reason"]=="terminal" for r in rows),"cost_totals":totals,"directions":directions,"funding_status":"OBSERVED_EVENT_FIXED_ENTRY_NOTIONAL_ESTIMATE_NOT_VERIFIED_FULL_NET","checks":{"terminal_equity_reconciles":True,"cash_flows_reconcile":True,"monthly_compounding_reconciles":True,"nonoverlapping_positions":True,"closed_signals_next_open":True}}
    trades_frame=pd.DataFrame(rows) if rows else pd.DataFrame(columns=["trade_id","signal_ts","entry_ts","exit_ts","side","quantity","leverage","entry_fee","exit_fee","funding_estimate","return","return_excluding_funding"])
    return trades_frame,curve,pd.DataFrame(monthly),summary


def execute(case,scenario,end=END):
    fixed,slip=SCENARIOS[scenario]
    fn={"ar":raw_ar,"mmtf":raw_mmtf,"keltner":raw_keltner}[case["kind"]]
    trades,raw,funding,details=fn(case,fixed,slip,end)
    tt,curve,monthly,summary=account(trades,raw,funding,case["timeframe"],end)
    if fixed:assert summary["max_entry_leverage"]<=1.+1e-12
    summary.update({"family":case["family"],"version":case["version"],"role":case["role"],"scenario":scenario,"start":START,"end":end,"details":details,"return_ex_funding":summary["return_excluding_funding"],"return_estimated_funding":summary["return"],"drawdown_type":"closed-bar marked equity, not maximum intrabar adverse excursion","funding_event_order_limitation":"Exact native timestamps are retained. Intrabar exit time is unknown: events from the exit bar are excluded; explicit close/terminal exits include events before the actual close. Missing events/marks prevent full net claims."})
    return tt,curve,monthly,summary,trades


def run_case(case):
    for scenario in SCENARIOS:
        tt,curve,monthly,summary,native=execute(case,scenario)
        dest=OUT/case["family"]/case["version"]/scenario;dest.mkdir(parents=True,exist_ok=True)
        summary.update({"equity_path":str((dest/"equity.csv").relative_to(ROOT)),"trades_path":str((dest/"trades.csv").relative_to(ROOT)),"monthly_path":str((dest/"monthly.csv").relative_to(ROOT))})
        tt.to_csv(dest/"trades.csv",index=False);curve.to_csv(dest/"equity.csv",index=False);monthly.to_csv(dest/"monthly.csv",index=False)
        js(dest/"native_trades.json",native)
        if scenario=="fixed_1x":
            pt,pc,pm,ps,pn=execute(case,scenario,PREFIX_END)
            a=curve.loc[curve.ts<PREFIX_END,["ts","equity"]].reset_index(drop=True)
            b=pc.loc[pc.ts<PREFIX_END,["ts","equity"]].reset_index(drop=True)
            assert a.ts.equals(b.ts)
            error=float(np.max(np.abs(a.equity-b.equity)))
            assert error<1e-10,(case["family"],case["version"],error)
            closed=lambda xs:[(str(x["entry_ts"]),str(x["exit_ts"]),x["side"],x["exit_price"]) for x in xs if x["exit_ts"]<PREFIX_END and x["exit_reason"]!="terminal"]
            assert closed(native)==closed(pn)
            summary["checks"].update({"prefix_causal_equity":True,"prefix_equity_max_error":error,"prefix_closed_trade_signature":True})
            pc.to_csv(dest/"prefix_equity.csv",index=False)
        js(dest/"summary.json",summary)
        print(json.dumps({k:summary[k] for k in ("family","version","scenario","return","max_drawdown","trades")}),flush=True)


def legacy_rvol_correction():
    e,cfg=mmtf_configs("15m","V3");raw=common.load_prices("HYPE","15m").reset_index(drop=True);funding=common.load_funding("HYPE")
    book=canonical_book(e,raw,funding,"15m")
    results={}
    for label,window in (("correct_spec_rvol96",96),("previous_helper_rvol48",48)):
        book.rvol=(raw.volume/raw.volume.shift(1).rolling(window,min_periods=window).median()).to_numpy(float)
        r=e.run_backtest(book,cfg,start_ts=START,end_ts=END,detailed=True)
        dest=OUT/"legacy_rvol_correction"/label;dest.mkdir(parents=True,exist_ok=True)
        pd.DataFrame(r.trades).to_csv(dest/"trades.csv",index=False)
        pd.DataFrame(r.equity_path).to_csv(dest/"native_equity.csv",index=False)
        js(dest/"summary.json",{"rvol_window":window,"config":asdict(cfg),"start":START,"end":END,"cost_model":"unchanged native MMTF 0.001 per entry-notional on each fill plus .0004 adverse slippage; original 3x leverage","metrics":r.metrics})
        results[label]=r.metrics
    js(OUT/"legacy_rvol_correction/comparison.json",{"previous_report_return":-.142191,"corrected_native_return":results["correct_spec_rvol96"]["total_return"],"reproduced_wrong_helper_return":results["previous_helper_rvol48"]["total_return"],"results":results,"cause":"previous shared helper hardcoded RVOL48; original 15m spec and engine require prior rolling median96. 1h uses48 correctly.","original_files_modified":False})
    print(json.dumps({"legacy_rvol_correction":results},default=str),flush=True)


def aggregate():
    rows=[]
    for p in sorted(OUT.glob("*/*/*/summary.json")):
        d=json.loads(p.read_text())
        if "family" in d:rows.append(d)
    js(OUT/"results.json",rows)
    pd.json_normalize(rows).to_csv(OUT/"results.csv",index=False)
    pairs=[]
    for family in sorted({x["family"] for x in rows}):
        for scenario in SCENARIOS:
            selected=[x for x in rows if x["family"]==family and x["scenario"]==scenario]
            if len(selected)!=2:continue
            early=next(x for x in selected if x["role"]=="early");late=next(x for x in selected if x["role"]=="latest")
            pairs.append({"family":family,"scenario":scenario,"early_version":early["version"],"latest_version":late["version"],"early_return":early["return"],"latest_return":late["return"],"latest_minus_early":late["return"]-early["return"],"early_drawdown":early["max_drawdown"],"latest_drawdown":late["max_drawdown"],"early_trades":early["trades"],"latest_trades":late["trades"]})
    js(OUT/"paired_results.json",pairs)
    pd.DataFrame(pairs).to_csv(OUT/"paired_results.csv",index=False)
    readback=[]
    for row in rows:
        trade=pd.read_csv(ROOT/row["trades_path"]);curve=pd.read_csv(ROOT/row["equity_path"]);monthly=pd.read_csv(ROOT/row["monthly_path"])
        assert len(trade)==row["trades"]
        assert abs(curve.equity.iloc[-1]-1-row["return"])<1e-10
        assert abs(float((1+monthly["return"]).prod())-curve.equity.iloc[-1])<1e-10
        if len(trade):
            assert np.allclose(trade.quantity*trade.entry_price,trade.entry_equity*trade.leverage,rtol=0,atol=1e-10)
            assert np.allclose(trade.entry_fee,trade.quantity*trade.entry_price*FEE,rtol=0,atol=1e-10)
            assert np.allclose(trade.exit_fee,trade.quantity*trade.exit_price*FEE,rtol=0,atol=1e-10)
            assert int((trade.side==1).sum())==row["directions"]["long"]["trades"]
            assert int((trade.side==-1).sum())==row["directions"]["short"]["trades"]
            if row["scenario"].startswith("fixed_1x"):assert np.allclose(trade.leverage,1.)
        readback.append({"family":row["family"],"version":row["version"],"scenario":row["scenario"],"saved_files_arithmetic_notional_counts":"PASS"})
    js(OUT/"verification_readback.json",readback)
    js(OUT/"verification.json",{"status":"PASS" if len(rows)==54 and len(pairs)==27 else "PARTIAL","case_scenarios":len(rows),"paired_scenarios":len(pairs),"saved_file_checks":len(readback),"checks_passed":all(all(v for k,v in x["checks"].items() if isinstance(v,bool)) for x in rows)})


def v2_equivalence():
    plan=[]
    for tf in ("1h","15m"):
        e,v1=mmtf_configs(tf,"V1")
        a=hype.mod(f"research/hype/{tf}-multi-mechanism-trend-following/scripts/mmtf_v2.py","mmtf_v2")
        v2=a.to_engine_config(a.v2_baseline())
        plan.append({"timeframe":tf,"v1":asdict(v1),"v2":asdict(v2),"v2_sha256":e.config_sha256(v2)})
    path=OUT/"mmtf_v2_equivalence_plan.json"
    if path.exists():
        assert json.loads(path.read_text())["plan"]==plan
    else:js(path,{"frozen_at":pd.Timestamp.now(tz="UTC"),"plan":plan,"decision":"check equality only; no candidate selection or tuning"})
    results=[]
    for p in plan:
        tf=p["timeframe"];e,_=mmtf_configs(tf,"V1")
        raw=common.load_prices("HYPE",tf).reset_index(drop=True);funding=common.load_funding("HYPE")
        book=canonical_book(e,raw,funding,tf)
        for lev in (1.,2.):
            one=e.run_backtest(book,replace(e.Config(**p["v1"]),leverage=lev),start_ts=START,end_ts=END,detailed=True)
            two=e.run_backtest(book,replace(e.Config(**p["v2"]),leverage=lev),start_ts=START,end_ts=END,detailed=True)
            results.append({"timeframe":tf,"leverage":lev,"trade_signature_equal":e.trade_signature(one)==e.trade_signature(two),"v1_metrics":one.metrics,"v2_metrics":two.metrics})
    js(OUT/"mmtf_v2_equivalence.json",results)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=("prepare","run","correction","aggregate","equivalence"))
    parser.add_argument("--family")
    args=parser.parse_args()
    if args.mode=="prepare":prepare()
    elif args.mode=="aggregate":aggregate()
    else:
        verify_sources()
        if args.mode=="correction":legacy_rvol_correction()
        elif args.mode=="equivalence":v2_equivalence()
        else:
            for case in json.loads((OUT/"cases_plan.json").read_text())["cases"]:
                if not args.family or case["family"]==args.family:run_case(case)
            aggregate()
