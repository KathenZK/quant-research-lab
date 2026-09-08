"""Frozen, causal, fixed-unit linear-perpetual ablation engine. No data reads."""
import math
import baseline_engine as baseline

VARIANTS = ('long', 'short', 'both', 'reverse')


def signal_arrays(bars, indicator_override=None, valid_mask=None):
    ma, atr, _, slope = indicator_override or baseline.indicators(bars)
    signals = [0] * len(bars)
    for i in range(14, len(bars)):
        if valid_mask is not None and not valid_mask[i]:
            continue
        if any(x is None for x in (ma[i-1], ma[i], atr[i], slope[i])):
            continue
        if bars[i-1]['close'] < ma[i-1] and bars[i]['close'] > ma[i] and slope[i] > 0:
            signals[i] = 1
        elif bars[i-1]['close'] > ma[i-1] and bars[i]['close'] < ma[i] and slope[i] < 0:
            signals[i] = -1
    return ma, atr, signals


def drawdown(nav):
    peak, worst = 1., 0.
    for x in nav:
        peak = max(peak, x)
        worst = max(worst, 1-x/peak)
    return 100*worst


def execute(bars, variant='long', fee=.001, slip=.0004, force_end=True,
            indicator_override=None, valid_mask=None):
    assert variant in VARIANTS and bars
    ma, atr, signals = signal_arrays(bars, indicator_override, valid_mask)
    cash, pos, pending = 1., None, None
    trades, events, nav, stops, sides = [], [], [], [], []
    bankrupt = False

    def enter(i, side, signal_idx, stop, reversal):
        nonlocal pos
        fill = bars[i]['open'] * (1+side*slip)
        units = cash / (fill*(1+fee))
        pos = dict(side=side, entry_idx=i, signal_idx=signal_idx, entry_price=fill,
                   entry_raw_price=bars[i]['open'], entry_equity=cash, units=units,
                   entry_fee=units*fill*fee, stop=stop, reversal_entry=reversal)
        events.append(dict(i=i, action='entry', side=side, signal_idx=signal_idx,
                           price=fill, stop=stop, reversal_entry=reversal))

    def close(i, raw, reason):
        nonlocal cash, pos, bankrupt
        s, u = pos['side'], pos['units']
        fill = raw*(1-s*slip)
        exit_fee = u*fill*fee
        uncapped = pos['entry_equity']-pos['entry_fee']+s*u*(fill-pos['entry_price'])-exit_fee
        bankrupt = uncapped <= 0 or reason == 'economic_bankruptcy'
        cash = 0. if bankrupt else uncapped
        trades.append(dict(trade_id=len(trades)+1, side=s, signal_idx=pos['signal_idx'],
            entry_idx=pos['entry_idx'], exit_idx=i, entry_date=baseline.iso(bars[pos['entry_idx']]['ts']),
            signal_date=baseline.iso(bars[pos['signal_idx']]['ts']), exit_date=baseline.iso(bars[i]['ts']),
            entry_price=pos['entry_price'], exit_price=fill, entry_raw_price=pos['entry_raw_price'],
            exit_raw_price=raw, units=u, entry_fee=pos['entry_fee'], exit_fee=exit_fee,
            equity_before=pos['entry_equity'], equity_after=cash, uncapped_equity_after=uncapped,
            ret_pct=(cash/pos['entry_equity']-1)*100, reason=reason,
            reversal_entry=pos['reversal_entry'], hold_days=i-pos['entry_idx'],
            stop_at_exit=pos['stop'], economic_bankruptcy=bankrupt))
        events.append(dict(i=i, action='exit', side=s, price=fill, reason=reason))
        pos = None

    for i, b in enumerate(bars):
        # The old resting stop already exists when an opening reversal executes.
        if pos is not None and pos['side']*(b['open']-pos['stop']) <= 0:
            close(i, b['open'], 'gap_stop')
        if pending is not None and not bankrupt:
            target, j, stop, reversal = pending
            if pos is not None:
                assert variant == 'reverse' and pos['side'] == -target
                close(i, b['open'], 'reverse_signal')
            if not bankrupt:
                enter(i, target, j, stop, reversal)
        pending = None
        stops.append(pos['stop'] if pos else None)
        sides.append(pos['side'] if pos else 0)
        if pos is not None:
            s, u = pos['side'], pos['units']
            # Economic zero-equity barrier, including the modelled exit costs.
            zero_fill = (s*u*pos['entry_price']-pos['entry_equity']+pos['entry_fee'])/(u*(s-fee))
            zero_raw = zero_fill/(1-s*slip)
            stop = pos['stop']
            barrier = max(stop, zero_raw) if s == 1 else min(stop, zero_raw)
            barrier_is_bankruptcy = s*(zero_raw-stop) > 0
            if s*(b['open']-barrier) <= 0:
                close(i, b['open'], 'gap_stop')
            elif (b['low'] <= barrier if s == 1 else b['high'] >= barrier):
                close(i, barrier, 'economic_bankruptcy' if barrier_is_bankruptcy else 'stop')
        if pos is not None and ma[i] is not None and atr[i] is not None:
            candidate = ma[i]-pos['side']*1.5*atr[i]
            pos['stop'] = max(pos['stop'], candidate) if pos['side'] == 1 else min(pos['stop'], candidate)
        sig = signals[i]
        allowed = sig and (variant in ('both', 'reverse') or (variant == 'long' and sig == 1) or (variant == 'short' and sig == -1))
        if not bankrupt and allowed:
            if pos is None or (variant == 'reverse' and pos['side'] == -sig):
                pending = (sig, i, ma[i]-sig*1.5*atr[i], pos is not None)
        if force_end and i == len(bars)-1 and pos is not None:
            close(i, b['close'], 'end_of_test')
        value = cash if pos is None else cash-pos['entry_fee']+pos['side']*pos['units']*(b['close']-pos['entry_price'])
        assert math.isfinite(value) and value >= 0
        nav.append(value)
    logs = [math.log(t['equity_after']/t['equity_before']) if t['equity_after'] > 0 else None for t in trades]
    metrics = dict(return_pct=(nav[-1]-1)*100, equity=nav[-1], mdd_pct=drawdown(nav),
        n_trades=len(trades), n_long=sum(t['side']==1 for t in trades),
        n_short=sum(t['side']==-1 for t in trades),
        win_rate_pct=100*sum(t['ret_pct']>0 for t in trades)/len(trades) if trades else 0.,
        reversal_exits=sum(t['reason']=='reverse_signal' for t in trades),
        reversal_entries=sum(t['reversal_entry'] for t in trades),
        terminal_valuations=sum(t['reason']=='end_of_test' for t in trades),
        bankrupt=bankrupt, exposure_pct=100*sum(s!=0 for s in sides)/len(bars),
        long_log_growth_pct=sum(x for t,x in zip(trades,logs) if t['side']==1)*100 if all(x is not None for t,x in zip(trades,logs) if t['side']==1) else None,
        short_log_growth_pct=sum(x for t,x in zip(trades,logs) if t['side']==-1)*100 if all(x is not None for t,x in zip(trades,logs) if t['side']==-1) else None)
    return dict(metrics=metrics, nav=nav, trades=trades, events=events, active_stops=stops, active_sides=sides)


def gross_oracle(bars, variant, force_end=True):
    """Separate daily loop with independent gross trade-factor accounting."""
    ma, atr, _, slope = baseline.indicators(bars)
    equity, holding, pending = 1., None, 0
    curve, tape = [], []

    def exit_position(i, price):
        nonlocal equity, holding
        s, entry, j, stop = holding
        equity = max(0., equity*(1+s*(price/entry-1)))
        tape.append((j, i, s, entry, price))
        holding = None

    for i,b in enumerate(bars):
        if holding and holding[0]*(b['open']-holding[3]) <= 0:
            exit_position(i,b['open'])
        if pending and equity > 0:
            if holding:
                exit_position(i,b['open'])
            if equity > 0:
                holding=[pending,b['open'],i,ma[i-1]-pending*1.5*atr[i-1]]
        pending=0
        if holding:
            s,entry,j,stop=holding
            threshold=max(0.,stop) if s==1 else min(2*entry,stop)
            raw = b['open'] if s*(b['open']-threshold)<=0 else threshold if (b['low']<=threshold if s==1 else b['high']>=threshold) else None
            if raw is not None:
                exit_position(i,raw)
        if holding:
            candidate=ma[i]-holding[0]*1.5*atr[i]
            holding[3]=max(holding[3],candidate) if holding[0]==1 else min(holding[3],candidate)
        sig=0
        if i>=14 and bars[i-1]['close']<ma[i-1] and b['close']>ma[i] and slope[i]>0: sig=1
        if i>=14 and bars[i-1]['close']>ma[i-1] and b['close']<ma[i] and slope[i]<0: sig=-1
        if sig and equity>0 and (variant in ('both','reverse') or (variant=='long' and sig==1) or (variant=='short' and sig==-1)):
            if holding is None or (variant=='reverse' and sig==-holding[0]): pending=sig
        if force_end and i==len(bars)-1 and holding:
            exit_position(i,b['close'])
        curve.append(equity if holding is None else equity*(1+holding[0]*(b['close']/holding[1]-1)))
    return tape,curve
