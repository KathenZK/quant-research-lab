"""Independent verification of every matched and fixed MA30 episode label."""
import argparse,json,time,traceback
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
import pandas as pd
import audit_ma30_states_20260911 as audit
from audit_ma30_states_20260911 import equal,money,DAY,HOUR,audit_stop_path,read_frame,sha,read_json,write_json
LAB,FAMILY,ROUND=audit.LAB,audit.FAMILY,audit.ROUND
OLD=FAMILY/'artifacts/adaptation_20260911'
EXIT_ARMS=['C_DEFENSE','C_EXTENSION','M_DEFEND','M_EXTEND','M_MANAGE']
def audit_fixed_trade(trade, base, records, daily, hourly, cfg, global_end):
    for name in ("entry_time", "entry_reference", "entry_price", "entry_equity", "entry_fee", "qty", "side", "initial_stop"):
        equal(getattr(trade, name), getattr(base, name), "Fixed entry changed: " + name)
    equal(trade.source_trade_id, base.trade_id, "source entry identifier")
    equal(trade.trade_id, 1, "independent episode trade identifier")
    side, fee, slip = int(trade.side), float(cfg["fee"]), float(cfg["slip"])
    assert trade.entry_time <= trade.exit_time <= global_end
    sig = daily.loc[trade.entry_time - DAY]
    assert bool(sig.ready) and int(sig.cross) == side and side * sig.slope > cfg["slope"]
    equal(trade.signal_day, sig.timestamp, "fixed signal close")
    equal(trade.entry_reference, hourly.loc[trade.entry_time, "open"], "fixed open price")
    equal(trade.entry_price, trade.entry_reference * (1 + side * slip), "fixed entry slippage")
    equal(trade.exit_price, trade.exit_reference * (1 - side * slip), "fixed exit slippage")
    money.audit_quantity(trade, cfg, float(base.entry_equity))
    equal(trade.entry_fee, trade.qty * trade.entry_price * fee, "fixed entry fee")
    equal(trade.exit_fee, trade.qty * trade.exit_price * fee, "fixed exit fee")
    equal(trade.carry_paid, 0., "fixed carry")
    equal(trade.funding_paid, 0., "fixed funding not imputed")
    gross = side * trade.qty * (trade.exit_price - trade.entry_price)
    net = gross - trade.entry_fee - trade.exit_fee
    equal(trade.gross_pnl, gross, "fixed gross")
    equal(trade.net_pnl, net, "fixed net")
    equal(trade.end_equity, trade.entry_equity + net, "fixed end equity")
    money.audit_account_return(trade.return_on_entry_equity, trade.entry_equity, trade.end_equity, net,
                               trade.entry_fee, trade.exit_fee, gross, [])
    summary = {**cfg, "start": str(trade.entry_time), "end_exclusive": str(global_end)}
    audit_stop_path(trade, records, daily, summary)
    held = hourly.loc[(hourly.index >= trade.entry_time) & (hourly.index < trade.exit_time)]
    which = np.searchsorted(records.timestamp.astype("int64"), held.index.asi8, side="right") - 1
    assert (which >= 0).all()
    lines = records.new_stop.to_numpy()[which]
    adverse = held.low.to_numpy() if side == 1 else held.high.to_numpy()
    assert (side * (adverse - lines) > 0).all(), "Fixed earlier stop ignored"
    if trade.exit_reason == "sample_end":
        equal(trade.exit_time, global_end, "fixed censor boundary")
        equal(trade.exit_reference, hourly.loc[global_end - HOUR, "close"], "fixed censor close")
    else:
        bar = hourly.loc[trade.exit_time]
        if trade.exit_reason == "stop_gap":
            assert side * (bar.open - trade.stop) <= 0
            equal(trade.exit_reference, bar.open, "fixed gap reference")
        elif trade.exit_reason == "stop_intrahour":
            assert side * (bar.open - trade.stop) > 0
            assert bar.low <= trade.stop if side == 1 else bar.high >= trade.stop
            equal(trade.exit_reference, trade.stop, "fixed stop reference")
        else:
            assert side == -1 and cfg["short_exit"] == "accel1_rsi30" and trade.exit_reason == "accel1_rsi30"
            signal = daily.loc[trade.exit_time - DAY]
            assert signal.rsi <= 30 and signal.accel1
            assert side * (bar.open - trade.stop) > 0, "Fixed RSI exit displaced a gap stop"
            equal(trade.exit_reference, bar.open, "fixed RSI reference")
    equal(trade.exit_interval_end, trade.exit_time + (HOUR if trade.exit_reason == "stop_intrahour" else pd.Timedelta(0)), "fixed exit interval")
    for record in records.iloc[1:].itertuples(index=False):
        day = daily.loc[record.signal_day]
        fill = float(day.close) * (1 - side * slip)
        profit = side * trade.qty * (fill - trade.entry_price) - trade.entry_fee - trade.qty * fill * fee
        equal(record.expected_profit_at_close, profit, "fixed close-profit snapshot")
        equal(record.favorable_move_atr, side * (float(day.close) - trade.entry_price) / trade.entry_atr, "fixed favorable move")
        equal(record.profit_eligible, profit > 0 and side * (day.close - trade.entry_price) >= 0, "fixed profit eligibility")
        if (side == -1 and cfg["short_exit"] != "none" and day.rsi <= 30 and day.accel1 and profit > 0
                and not (cfg.get("ma30_mode", "none") != "none" and getattr(record,"m30_suppress_short_tp",False))):
            assert trade.exit_time == record.timestamp and trade.exit_reason in {"stop_gap", "accel1_rsi30"}
    for name, target in {"baseline_exit_time": base.exit_time, "baseline_exit_reason": base.exit_reason,
                         "baseline_net_pnl": base.net_pnl, "baseline_return": base.return_on_entry_equity,
                         "delta_net_pnl": net - base.net_pnl,
                         "delta_return": trade.return_on_entry_equity - base.return_on_entry_equity,
                         "either_terminal": trade.exit_reason == "sample_end" or base.exit_reason == "sample_end"}.items():
        if name == "delta_net_pnl":
            # Subtracting two independently CSV-rounded cash PnLs needs their
            # absolute roundoff scale, even when the resulting difference is zero.
            tolerance = 8 * np.finfo(float).eps * (abs(net) + abs(base.net_pnl) + abs(base.entry_equity))
            assert abs(float(getattr(trade,name)) - target) <= tolerance, "Paired cash delta exceeds propagated float roundoff"
        else:
            equal(getattr(trade, name), target, "fixed pair " + name)

def one_coin(slug,items):
    pairs=ROUND/'pairs';cases=read_frame(pairs/'parts'/(slug+'.parquet'))
    if not len(cases):return {'slug':slug,'cases':0,'reused':0,'fixed':0}
    proof=read_frame(pairs/'proof'/(slug+'.csv'));assert len(proof)==len(cases)*5
    lookup=proof.set_index(['case_id','arm']);counts={'slug':slug,'cases':len(cases),'reused':0,'fixed':0};cache={}
    for key,info in items:
        group=cases[cases.run_key.eq(key)]
        if not len(group):continue
        baseline=read_frame(OLD/'results/runs'/key/'U_READY/full/trades.csv').set_index('trade_id',drop=False)
        d=read_frame(OLD/'cases/daily_features'/(key+'.parquet'));d=audit.previous.add_causal_audit_features(d)
        d.timestamp=pd.to_datetime(d.timestamp,utc=True).dt.as_unit('ns');d=d.set_index('timestamp',drop=False)
        hp=LAB/info['hourly_path']
        if hp not in cache:
            assert sha(hp)==info['hourly_sha256'];h=read_frame(hp).rename(columns={'ts':'timestamp'});h.timestamp=pd.to_datetime(h.timestamp,utc=True).dt.as_unit('ns');cache[hp]=h.set_index('timestamp',drop=False)
        h=cache[hp]
        naturals={a:read_frame(ROUND/'results/runs'/key/a/'full/trades.csv') for a in EXIT_ARMS}
        fixed={a:read_frame(pairs/'fixed'/key/a/'trades.csv') for a in EXIT_ARMS}
        stops={a:read_frame(pairs/'fixed'/key/a/'stops.csv') for a in EXIT_ARMS}
        summaries={a:read_json(ROUND/'results/runs'/key/a/'full/summary.json') for a in EXIT_ARMS}
        for row in group.itertuples(index=False):
            base=baseline.loc[row.source_trade_id];side=int(base.side);signal=d.loc[base.signal_day]
            q=side*(signal.ma30-signal.prev_ma30)/signal.atr;x=side*(signal.close-signal.ma30)/signal.atr
            equal(row.q,q,'entry Q');equal(row.x,x,'entry X');equal(row.entry_time,base.entry_time,'case entry')
            equal(row.u_U_READY,base.return_on_entry_equity,'baseline label')
            for a in EXIT_ARMS:
                p=lookup.loc[(row.case_id,a)]
                if bool(p.reused):
                    match=naturals[a].loc[naturals[a].trade_id.eq(p.candidate_trade_id)];assert len(match)==1
                    t=next(match.itertuples(index=False));counts['reused']+=1
                    for field in ['entry_time','side','entry_reference','entry_price','initial_stop','initial_stop_fill','initial_stop_unit_risk','entry_atr']:
                        equal(getattr(t,field),base[field],'matched entry '+field)
                    for field in ['qty','entry_fee','initial_planned_risk']:
                        equal(getattr(t,field)/t.entry_equity,base[field]/base.entry_equity,'matched scale '+field)
                else:
                    match=fixed[a].loc[fixed[a].source_trade_id.eq(base.trade_id)];assert len(match)==1;t=next(match.itertuples(index=False))
                    st=stops[a].loc[stops[a].source_trade_id.eq(base.trade_id)].reset_index(drop=True)
                    cfg={**summaries[a],'short_exit':'none' if a=='C_EXTENSION' else 'accel1_rsi30'}
                    audit_fixed_trade(t,SimpleNamespace(**base.to_dict()),st,d,h,cfg,pd.Timestamp(info['end']));counts['fixed']+=1
                for name,target in [('u',t.return_on_entry_equity),('exit',t.exit_time),('exit_interval_end',t.exit_interval_end),('reason',t.exit_reason),('terminal',t.exit_reason=='sample_end')]:
                    equal(getattr(row,name+'_'+a),target,'saved label '+name)
            previous_day=d.loc[base.signal_day-DAY]
            prev_q=side*(previous_day.ma30-previous_day.prev_ma30)/previous_day.atr
            conflict=q<=-.05;repair=conflict and q>prev_q and x>0
            btc=signal['long_btc_return60' if side==1 else 'short_btc_return60']
            for a,allowed,source in [('M_SKIP',not conflict,'U_READY'),('M_FULL',not conflict,'M_MANAGE'),
                ('M_REPAIR',not conflict or repair,'M_MANAGE'),('M_BTC',not conflict and np.isfinite(btc) and btc>=0,'M_MANAGE')]:
                assert bool(getattr(row,'allow_'+a))==allowed
                equal(getattr(row,'u_'+a),getattr(row,'u_'+source) if allowed else 0.,'fixed gate payoff')
    return counts

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=3);args=ap.parse_args();out=ROUND/'pair_audit';out.mkdir(exist_ok=True)
    source=read_json(OLD/'cases/sources.json');by={}
    for key,info in source.items():by.setdefault(info['slug'],[]).append((key,info))
    r=[];errors=[];begin=time.monotonic();(out/'source_script.py.txt').write_bytes(Path(__file__).read_bytes())
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs={pool.submit(one_coin,k,v):k for k,v in by.items()}
        for n,f in enumerate(as_completed(jobs),1):
            try:r.append(f.result())
            except Exception as exc:errors.append({'slug':jobs[f],'error':repr(exc),'trace':traceback.format_exc()});write_json(out/'errors.json',errors);print('ERROR',jobs[f],repr(exc),flush=True)
            if n%40==0 or n==len(jobs):print(f'Pair audit {n}/{len(jobs)}, errors {len(errors)}, {time.monotonic()-begin:.1f}s',flush=True)
    totals={k:sum(x[k] for x in r) for k in ['cases','reused','fixed']}
    write_json(out/'final.json',{'status':'PASS' if not errors else 'FAIL','totals':totals,'errors':errors,'elapsed_seconds':time.monotonic()-begin,'pairs_manifest_sha256':sha(ROUND/'pairs/artifact_checksums.json')});assert not errors

if __name__=='__main__':main()
