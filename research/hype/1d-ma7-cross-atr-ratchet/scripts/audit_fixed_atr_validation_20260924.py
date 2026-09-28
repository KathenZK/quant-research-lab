"""Fixed-ATR validation auditor revision: exact rolling gates and insolvent flat states.
Derived from preserved audit_v3_parameters_20260924.py; does not import simulator.
"""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parents[1]
MARKET=ROOT/'research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts'
sys.path.insert(0,str(MARKET))
import audit_v3_opportunity_20260913 as legacy
from common import write_json
read_frame=legacy.read_frame
read_json=lambda p:json.loads(Path(p).read_text())
equal=legacy.equal
audit_quantity=legacy.audit_quantity
audit_account_return=legacy.audit_account_return
DAY=pd.Timedelta(days=1);HOUR=pd.Timedelta(hours=1)
R=BASE/'artifacts/v3_parameter_stability_20260924'

def smooth(values,n):
    out=[];seed=[];last=None
    for value in values:
        if not np.isfinite(value):seed=[];last=None
        elif last is None:
            seed.append(float(value))
            if len(seed)==n:last=sum(seed)/n
        else:last=((n-1)*last+float(value))/n
        out.append(np.nan if last is None else last)
    return np.array(out)

def indicators(raw,s):
    d=raw.copy();c=d.close.to_numpy();delta=np.r_[np.nan,np.diff(c)]
    prior=np.r_[np.nan,c[:-1]]
    tr=np.maximum(d.high.to_numpy()-d.low.to_numpy(),np.maximum(abs(d.high.to_numpy()-prior),abs(d.low.to_numpy()-prior)))
    d['ma']=[np.nan if i+1<s['ma_period'] else sum(c[i+1-s['ma_period']:i+1])/s['ma_period'] for i in range(len(c))]
    exact_ma=d.close.rolling(s['ma_period']).mean()
    assert np.allclose(d.ma,exact_ma,rtol=2e-12,atol=1e-14,equal_nan=True), 'independent mean mismatch'
    # Crossing equality follows the declared frozen pandas rolling arithmetic.
    d['ma']=exact_ma
    d['atr']=smooth(tr,s['atr_period']);up=smooth(np.maximum(delta,0),s['rsi_period']);down=smooth(np.maximum(-delta,0),s['rsi_period'])
    with np.errstate(divide='ignore',invalid='ignore'):rsi=100-100/(1+up/down)
    rsi[(up==0)&(down==0)]=50;rsi[(up>0)&(down==0)]=100;d['rsi']=rsi
    d['slope']=d.ma.diff()/d.atr
    d['cross']=np.where((d.close.shift()<=d.ma.shift())&(d.close>d.ma),1,np.where((d.close.shift()>=d.ma.shift())&(d.close<d.ma),-1,0))
    drop=-delta;pdrops=np.r_[np.nan,drop[:-1]]
    size=drop>=s['accel_atr_mult']*d.atr.shift();grow=drop>s['accel_prev_mult']*np.maximum(pdrops,0)
    d['accel1']=(size if s['require_accel_size'] else drop>0)&(grow if s['require_accel_increase'] else drop>0)
    d['ready']=d[['eligible','observed_valid','is_closed','joint_eligible']].all(axis=1)&np.isfinite(d[['ma','atr','rsi','slope']]).all(axis=1)&d.atr.gt(0)
    return d.set_index('timestamp',drop=False)

def tp_eligible(t,day,s):
    if int(t.side)!=-1 or s['short_exit']=='none':return False
    fill=day.close*(1+s['slip']);net=t.qty*(t.entry_price-fill)-t.entry_fee-t.qty*fill*s['fee']
    return (not s['require_rsi'] or day.rsi<=s['rsi_threshold']) and (not s['require_tp_profit'] or net>0) and (s['short_exit']=='rsi30' or bool(day.accel1))

def audit_stop_path(t,records,daily,s):
    side=int(t.side);signal=daily.loc[t.signal_day];mult=s['initial_atr_mult'];floor=s['atr_floor']
    stop=float(signal.ma-side*mult*signal.atr)
    equal(t.initial_stop,stop,'initial stop');equal(t.entry_atr,signal.atr,'entry ATR')
    equal(t.entry_ma,signal.ma,'entry MA')
    dates=pd.date_range(t.entry_time.floor('D')+DAY,t.exit_time.floor('D'),freq='D');dates=dates[dates<pd.Timestamp(s['end_exclusive'])]
    assert records.timestamp.tolist()==[t.entry_time,*dates]
    initialized=False;armed=False;extreme=None;count=0;reductions=0;ever=False;arms=0;resets=0
    equal(records.iloc[0].new_stop,stop,'first stop');equal(records.iloc[0].new_mult,mult,'first multiple')
    for r in records.iloc[1:].itertuples():
        assert r.timestamp==r.signal_day+DAY
        d=daily.loc[r.signal_day];full=r.signal_day>=t.entry_time
        equal(r.old_stop,stop,'old stop');equal(r.old_mult,mult,'old multiplier')
        ma=d.ma if s['trail_ma'] else signal.ma;atr=d.atr if s['trail_atr'] else signal.atr
        equal(r.natural_candidate,ma-side*mult*atr,'MA/ATR anchor')
        tightened=False;new_extreme=False;was_armed=armed
        if s['progress_days']>0 and full:
            observed=float(d.close if s['progress_source']=='close' else d.high if side==1 else d.low)
            if not initialized:initialized=True;extreme=observed;new_extreme=True
            else:
                new_extreme=side*(observed-extreme)>0
                if new_extreme:
                    extreme=observed;count=0
                    if s['progress_policy']=='reset_on_new_extreme':
                        resets+=int(armed);armed=False
                else:count+=1
                if not armed and count>=s['progress_days']:armed=True
                tightened=armed and mult>floor
        if armed and not was_armed:arms+=1;ever=True
        if tightened:mult=max(floor,round(mult-s['tighten_step'],10));reductions+=1
        candidate=ma-side*mult*atr;stop=max(stop,candidate) if side==1 else min(stop,candidate)
        for k,v in {'new_stop':stop,'new_mult':mult,'new_armed':armed,'initialized':initialized,
             'extreme_price':extreme,'no_new_extreme_days':count,'tightened':tightened,
             'new_extreme':new_extreme,'full_holding_day':full,'ever_armed':ever,'arm_count':arms,'reset_count':resets}.items():equal(getattr(r,k),v,'independent stop '+k)
        assert side*(r.new_stop-r.old_stop)>=-1e-12
    for k,v in {'stop':stop,'stop_mult':mult,'tightening_days':reductions,'armed':armed,'initialized':initialized,'no_new_extreme_days':count,'ever_armed':ever,'arm_count':arms,'reset_count':resets}.items():equal(getattr(t,k),v,'final stop '+k)

def audit_entry_lifecycle(trades,daily,hourly,s,events):
    entered={t.entry_time:t for t in trades.itertuples()};alltr=list(entered.values());filled=events[events.status.eq('filled')]
    assert filled.timestamp.tolist()==trades.entry_time.tolist()
    for t in alltr:
        day=daily.loc[t.signal_day];side=int(t.side)
        assert bool(day.ready)
        assert s['entry_mode']=='no_slope' or side*day.slope>s['slope']
        assert s['direction_mode']=='both' or (side==1 and s['direction_mode']=='long') or (side==-1 and s['direction_mode']=='short')
        if t.entry_reason=='daily_cross':
            assert t.entry_time==t.signal_day+DAY
            expected=int(day.cross) if s['entry_trigger']=='cross' else int(np.sign(day.close-day.ma))
            assert side==expected
        else:
            assert t.entry_reason=='stop_reversal' and s['reverse']
            prior=[x for x in alltr if x.exit_time+HOUR==t.entry_time and x.exit_reason.startswith('stop_')]
            assert len(prior)==1 and prior[0].side==-side
            at_stop=daily.loc[:prior[0].exit_time.floor('D')-DAY].tail(5)
            at_stop=at_stop[(at_stop.timestamp+DAY>prior[0].entry_time)&at_stop.cross.ne(0)]
            assert len(at_stop) and int(at_stop.iloc[-1].cross)==side
            assert side*(day.close-day.ma)>0
    # No valid flat daily entry may be silently omitted. A carried position's exit
    # consumes the day's signal, including an exit at that exact midnight.
    for at in pd.date_range(pd.Timestamp(s['start']),pd.Timestamp(s['end_exclusive'])-DAY,freq='D'):
        if any(t.entry_time<at<=t.exit_time for t in alltr):continue
        # A short can exhaust cash in this price-only model; no later entries.
        settled_cash=10000.0+sum(t.net_pnl for t in alltr if t.exit_time<at)
        if settled_cash<=0:
            assert at not in entered, ('entry after insolvency', at)
            continue
        day=daily.loc[at-DAY];side=int(day.cross) if s['entry_trigger']=='cross' else int(np.sign(day.close-day.ma))
        valid=bool(day.ready) and side!=0 and (s['entry_mode']=='no_slope' or side*day.slope>s['slope'])
        valid=valid and (s['direction_mode']=='both' or side==1 and s['direction_mode']=='long' or side==-1 and s['direction_mode']=='short')
        valid=valid and side*(hourly.loc[at,'open']-(day.ma-side*s['initial_atr_mult']*day.atr))>0
        # A scheduled reversal consumes daily processing even if it fails recheck.
        if s['reverse'] and any(t.exit_reason.startswith('stop_') and t.exit_time+HOUR==at for t in alltr):continue
        if valid:assert at in entered,('missing eligible flat entry',at)
        elif at in entered:assert entered[at].entry_reason=='stop_reversal',('unexpected entry',at)
    return {'entries_verified':len(trades),'opportunity_events':len(events)}

def audit_run(directory, daily, hourly, carry_daily=0.0):
    """Rebuild all ledger fields/marks; input indices are UTC timestamps."""
    directory = Path(directory)
    daily, hourly = daily.copy(), hourly.copy()
    daily.index = pd.DatetimeIndex(daily.index).as_unit("ns")
    hourly.index = pd.DatetimeIndex(hourly.index).as_unit("ns")
    summary = read_json(directory / "summary.json")
    trades, stops, marks = (read_frame(directory / name)
                            for name in ("trades.csv", "stops.csv", "equity.parquet"))
    start, end = pd.Timestamp(summary["start"]), pd.Timestamp(summary["end_exclusive"])
    h = hourly.loc[(hourly.index >= start) & (hourly.index < end)]
    assert h.index.tolist() == pd.date_range(start, end - HOUR, freq="h").tolist()
    assert summary["funding_window_verified"] is False and summary["price_only_diagnostic"] is True
    assert summary["funding_paid"] == 0 and not (directory / "funding.csv").exists()
    equal(len(trades), summary["trades"], "trade count")
    for kind, times, prices in (("open", h.index, h.open), ("hour_close", h.index + HOUR, h.close)):
        one = marks.loc[marks.kind == kind]
        assert one.timestamp.tolist() == times.tolist(), "Missing/extra hourly equity marks"
        assert np.allclose(one.price, prices, rtol=2e-10, atol=1e-14), "Mark source price mismatch"
    for kind, field in (("entry", "entry_time"), ("exit", "exit_time")):
        expected_times = trades[field].tolist() if len(trades) else []
        assert marks.loc[marks.kind == kind, "timestamp"].tolist() == expected_times
    assert marks.kind.isin(["open", "hour_close", "entry", "exit"]).all()
    if len(trades):
        assert set(stops.trade_id) == set(trades.trade_id), "Unassigned stop records"
    result = audit_entry_lifecycle(trades, daily, h, summary, read_frame(directory / "entry_events.csv"))
    cash, previous_exit, previous_interval_end = 10000.0, None, None
    fees, carry_total, verified_marks, exposure_hours = 0.0, 0.0, 0, 0
    for expected_id, trade in enumerate(trades.itertuples(index=False), 1):
        assert trade.trade_id == expected_id
        side, fee, slip = int(trade.side), summary["fee"], summary["slip"]
        if previous_exit is not None:
            assert trade.entry_time > previous_exit and trade.entry_time >= previous_interval_end
        equal(trade.entry_equity, cash, "next entry capital")
        equal(trade.entry_reference, h.loc[trade.entry_time, "open"], "entry reference")
        equal(trade.entry_price, trade.entry_reference * (1 + side * slip), "entry slippage")
        equal(trade.exit_price, trade.exit_reference * (1 - side * slip), "exit slippage")
        audit_quantity(trade, summary, cash)
        equal(trade.entry_fee, trade.qty * trade.entry_price * fee, "entry fee")
        equal(trade.exit_fee, trade.qty * trade.exit_price * fee, "exit fee")
        held = h.loc[(h.index >= trade.entry_time) & ((h.index < trade.exit_time)
                         | ((h.index == trade.exit_time) & (trade.exit_reason == "stop_intrahour")))]
        carry = held.open.to_numpy() * trade.qty * carry_daily / 24
        equal(trade.carry_paid, carry.sum(), "hourly carry cost")
        equal(trade.funding_paid, 0.0, "unverified funding not imputed")
        gross = side * trade.qty * (trade.exit_price - trade.entry_price)
        net = gross - trade.entry_fee - trade.exit_fee - trade.carry_paid
        equal(trade.gross_pnl, gross, "gross PnL")
        equal(trade.net_pnl, net, "net PnL")
        equal(trade.end_equity, cash + net, "settled capital")
        audit_account_return(trade.return_on_entry_equity, cash, trade.end_equity, net,
                             trade.entry_fee, trade.exit_fee, gross, carry)
        own_stops = stops.loc[stops.trade_id == trade.trade_id].reset_index(drop=True)
        audit_stop_path(trade, own_stops, daily, summary)
        before_exit = h.loc[(h.index >= trade.entry_time) & (h.index < trade.exit_time)]
        which = np.searchsorted(own_stops.timestamp.astype("int64"), before_exit.index.asi8,
                                side="right") - 1
        assert (which >= 0).all()
        effective = own_stops.new_stop.to_numpy()[which]
        adverse = before_exit.low.to_numpy() if side == 1 else before_exit.high.to_numpy()
        assert (side * (adverse - effective) > 0).all(), "Earlier stop hit ignored"
        if trade.exit_reason == "sample_end":
            equal(trade.exit_time, end, "sample settlement time")
            equal(trade.exit_reference, h.iloc[-1].close, "sample settlement price")
        else:
            bar = h.loc[trade.exit_time]
            if trade.exit_reason == "stop_gap":
                assert side * (bar.open - trade.stop) <= 0
                equal(trade.exit_reference, bar.open, "gap fill")
            elif trade.exit_reason == "stop_intrahour":
                assert side * (bar.open - trade.stop) > 0
                assert bar.low <= trade.stop if side == 1 else bar.high >= trade.stop
                equal(trade.exit_reference, trade.stop, "native stop fill")
                equal(trade.exit_interval_end, trade.exit_time + HOUR, "stop uncertainty interval")
            else:
                assert trade.exit_reason == summary["short_exit"] and side == -1
                signal = daily.loc[pd.Timestamp(trade.tp_signal_day)]
                assert tp_eligible(trade,signal,summary)
                assert trade.exit_time == signal.timestamp + DAY
                expected = trade.qty * (trade.entry_price - signal.close * (1 + slip))
                expected -= trade.entry_fee + trade.qty * signal.close * (1 + slip) * fee + trade.carry_paid
                assert (not summary["require_tp_profit"] or expected > 0) and side * (bar.open - trade.stop) > 0
                equal(trade.exit_reference, bar.open, "RSI exit fill")
        if trade.exit_reason != "stop_intrahour":
            equal(trade.exit_interval_end, trade.exit_time, "exact exit boundary")
        selected = marks.loc[(marks.side == side) & (marks.timestamp >= trade.entry_time)
                             & (marks.timestamp <= trade.exit_time)]
        assert selected.kind.isin(["entry", "open", "hour_close"]).all()
        carry_prefix = np.r_[0.0, np.cumsum(carry)]
        paid = carry_prefix[np.searchsorted(held.index.asi8, selected.timestamp.astype("int64"), side="left")]
        expected_marks = cash - trade.entry_fee - paid + side * trade.qty * (selected.price.to_numpy() - trade.entry_price)
        assert np.allclose(selected.equity, expected_marks, rtol=2e-10, atol=1e-9), "Held equity marks differ"
        verified_marks += len(selected)
        for record in own_stops.iloc[1:].itertuples(index=False):
            prior_carry = carry_prefix[np.searchsorted(held.index.asi8, record.timestamp.value, side="left")]
            close = h.loc[record.timestamp - HOUR, "close"]
            fill = close * (1 - side * slip)
            profit = side * trade.qty * (fill - trade.entry_price) - trade.entry_fee - trade.qty * fill * fee - prior_carry
            equal(record.expected_profit_at_close, profit, "closed-day expected profit")
            favorable = side * (close - trade.entry_price)
            equal(record.favorable_move_atr, favorable / trade.entry_atr, "favorable ATR distance")
            equal(record.profit_eligible, profit > 0 and favorable >= 0, "profit eligibility")
            day = daily.loc[record.signal_day]
            if tp_eligible(trade,day,summary):
                assert trade.exit_time == record.timestamp and trade.exit_reason in {"stop_gap", summary["short_exit"]}, (
                    "First eligible short RSI exit ignored or lost priority to intrahour stop")
        cash, previous_exit, previous_interval_end = trade.end_equity, trade.exit_time, trade.exit_interval_end
        fees += trade.entry_fee + trade.exit_fee
        carry_total += trade.carry_paid
        exposure_hours += len(held)
    flat = marks.loc[marks.side == 0]
    if len(trades):
        exits = trades.exit_time.astype("int64").to_numpy()
        flat_times = flat.timestamp.astype("int64").to_numpy()
        indexes = np.searchsorted(exits, flat_times, side="left")
        is_exit = flat.kind.to_numpy() == "exit"
        indexes[is_exit] = np.searchsorted(exits, flat_times[is_exit], side="right")
        ends = np.r_[10000.0, trades.end_equity.to_numpy()]
        expected_flat = ends[indexes]
    else:
        expected_flat = np.full(len(flat), 10000.0)
        assert stops.empty
    assert np.allclose(flat.equity, expected_flat, rtol=2e-10, atol=1e-9), "Flat equity marks differ"
    verified_marks += len(flat)
    assert verified_marks == len(marks)
    equal(cash, summary["ending_equity"], "ending account")
    equal(marks.equity.iloc[-1], cash, "last mark")
    equal((cash / 10000 - 1) * 100, summary["return_pct"], "account return")
    equity = marks.equity.to_numpy()
    mdd = np.min(equity / np.maximum.accumulate(np.r_[10000.0, equity])[1:] - 1) * 100
    equal(mdd, summary["max_drawdown_pct"], "mark drawdown")
    equal(fees, summary["fee_total"], "fees total")
    equal(carry_total, summary["carry_paid"], "carry total")
    equal(exposure_hours / len(h) * 100, summary["exposure_pct"], "exposure")
    equal(summary["delayed_entries"], int(trades.entry_reason.eq("delayed_cross").sum()) if len(trades) else 0,
          "delayed trade count")
    if len(trades):
        for field, expected in {
            "tightening_days": int(trades.tightening_days.sum()),
            "tightened_trades": int(trades.tightening_days.gt(0).sum()),
            "armed_trades": int(trades.armed.sum()), "floor_trades": int(trades.stop_floor_reached.sum()),
            "progress_armed_trades": int(trades.arm_day.notna().sum()),
            "short_tp_exits": int(trades.exit_reason.isin(["accel1_rsi30","rsi30"]).sum()),
            "win_rate_pct": float(trades.net_pnl.gt(0).mean() * 100),
            "ever_armed_trades": int(trades.ever_armed.sum()),
            "arm_count": int(trades.arm_count.sum()), "reset_count": int(trades.reset_count.sum()),
            "initial_stop_nonpositive_trades": int(trades.initial_stop_price_nonpositive.sum()),
        }.items():
            equal(summary[field], expected, "summary " + field)
        for side, prefix in ((1, "long"), (-1, "short")):
            group = trades.loc[trades.side == side]
            equal(summary[prefix + "_trades"], len(group), prefix + " count")
            equal(summary[prefix + "_pnl"], float(group.net_pnl.sum()), prefix + " PnL")
    if summary['short_exit']=='accel1_rsi30_protect':
        for field,col in [('short_protection_activated_trades','tp_protect_active'),('short_protection_eligible_signals','tp_protect_eligible_signal_count'),('short_protection_suppressed_tp_calls','tp_protect_suppressed_count')]:
            equal(summary[field],int(trades[col].sum()) if len(trades) else 0,'TP aggregate '+field)
    return {**result, "trades": len(trades), "stop_records": len(stops),
            "equity_marks_independently_rebuilt": verified_marks, "status": "PASS"}


def main():
    frozen=read_json(R/'started.json');raw=pd.read_parquet(R/'input_daily.parquet');hourly=pd.read_parquet(R/'input_hourly.parquet').set_index('timestamp',drop=False)
    out=[]
    for i,c in enumerate(frozen['cases']):
        daily=indicators(raw,c['config'])
        out.append({'case_id':c['case_id'],**audit_run(R/'accounts'/c['case_id'],daily,hourly)})
        if i%10==0:print('audit',i+1,'/',len(frozen['cases']),flush=True)
    write_json(R/'audit.json',{'complete':True,'accounts':out,'count':len(out),'trades':sum(x['trades'] for x in out),'stop_records':sum(x['stop_records'] for x in out),'equity_marks':sum(x['equity_marks_independently_rebuilt'] for x in out)})
    print('AUDIT PASS',len(out),flush=True)
if __name__=='__main__':main()
