"""M1358 ADAPTED daily cold-start diagnostic. Offline; no original forum code.
Daily cash formulas adapted from pinned M0215; metrics from pinned M0216.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import pandas as pd
from metrics import metrics

FAMILY = Path(__file__).resolve().parents[1]
CASES = [('base', 8, 1), ('fee0', 0, 1), ('fee20', 20, 1), ('lag2', 8, 2)]
DAY = 86400000
NAV_FIELDS = ['bar_index','date','close_time_utc','equity','cash','quantity','raw_close','drawdown','ready','signal','pending_count']
FILL_FIELDS = ['intent_id','bar_index','date','signal_bar_index','signal_date','signal_close_utc','execution_time_utc','phase','side','quantity','raw_open','price','notional','fee','fee_currency','cash_before','cash_after','position_before','position_after']
DECISION_FIELDS = ['bar_index','date','decision_time_utc','ready','ema13','ema48','holding_quantity','action','intent_id','due_bar_index','due_time_utc']
PENDING_FIELDS = ['event','intent_id','event_bar_index','event_time_utc','signal_bar_index','due_bar_index','due_time_utc','side','reason']
FEATURE_FIELDS = ['bar_index','date','close_time_utc','sample_count','ema13','ema48','fast_ready','slow_ready','comparison']


def utc(ms):
    return pd.Timestamp(ms, unit='ms', tz='UTC').strftime('%Y-%m-%dT%H:%M:%SZ')


def features(frame):
    """Float64 mathematical EMA: SMA seed; unready value zero. No prefeed."""
    values = frame.close.to_numpy(dtype=float)
    states = {}
    for period in (13, 48):
        result = []
        prev = 0.0
        alpha = 2.0 / (period + 1)
        for i, value in enumerate(values):
            if i + 1 < period:
                prev = 0.0
            elif i + 1 == period:
                prev = math.fsum(values[:period]) / period
            else:
                prev = value * alpha + prev * (1 - alpha)
            result.append(prev)
        states[period] = result
    records = []
    for i, row in enumerate(frame.itertuples(index=False)):
        a, b = states[13][i], states[48][i]
        records.append(dict(bar_index=i, date=utc(row.open_time)[:10],
                            close_time_utc=utc(row.open_time + DAY), sample_count=i+1,
                            ema13=a, ema48=b, fast_ready=i+1 >= 13,
                            slow_ready=i+1 >= 48, comparison=1 if a>b else -1 if a<b else 0))
    return records


def source_action(ready, quantity, fast, slow):
    if not ready:
        return 0
    if quantity <= 0 and fast > slow:
        return 1
    if quantity > 0 and fast < slow:
        return -1
    return 0


def run(frame, fee_bps, lag, name='synthetic', feature_rows=None):
    assert lag in (1, 2) and fee_bps in (0, 8, 20)
    fs = features(frame) if feature_rows is None else feature_rows
    assert len(fs) == len(frame)
    cash, qty, peak = 100000.0, 0.0, 100000.0
    pending, nav, fills, decisions, events = {}, [], [], [], []
    for i, row in enumerate(frame.itertuples(index=False)):
        open_ms = int(row.open_time)
        for intent in pending.pop(i, []):
            action = intent['action']
            before_cash, before_qty = cash, qty
            side = 'BUY' if action == 1 else 'SELL'
            if action == 1 and qty == 0:
                price = float(row.open) * 1.0002
                amount = cash * .95
                delta = amount / price
            elif action == -1 and qty > 0:
                price = float(row.open) * .9998
                delta = -qty
                amount = -delta * price
            else:
                delta = 0.0
            if delta:
                charge = amount * fee_bps / 10000
                cash -= delta * price + charge
                qty += delta
                if side == 'SELL':
                    qty = 0.0
                fills.append(dict(intent_id=intent['id'], bar_index=i, date=utc(open_ms)[:10],
                                  signal_bar_index=intent['signal_index'], signal_date=intent['signal_date'],
                                  signal_close_utc=intent['decision_time'], execution_time_utc=utc(open_ms),
                                  phase='OPEN', side=side, quantity=abs(delta), raw_open=float(row.open),
                                  price=price, notional=amount, fee=charge, fee_currency='USDT',
                                  cash_before=before_cash, cash_after=cash, position_before=before_qty, position_after=qty))
            events.append(dict(event='FILLED' if delta else 'SKIPPED_STALE', intent_id=intent['id'],
                               event_bar_index=i,event_time_utc=utc(open_ms), signal_bar_index=intent['signal_index'],
                               due_bar_index=i,due_time_utc=utc(open_ms),side=side,
                               reason='due intent applied' if delta else 'BUY while long or SELL while flat'))
        equity = cash + qty * float(row.close)
        peak = max(peak, equity)
        f = fs[i]
        action = source_action(f['slow_ready'], qty, f['ema13'], f['ema48'])
        intent_id, due, due_time = '', '', ''
        if action:
            due = i + lag
            due_time = utc(open_ms + lag * DAY)
            intent_id = f'{name}:{i}:{"BUY" if action == 1 else "SELL"}'
            intent = dict(id=intent_id, action=action, signal_index=i,signal_date=f['date'],
                          decision_time=f['close_time_utc'],due_time=due_time)
            pending.setdefault(due, []).append(intent)
            events.append(dict(event='QUEUED',intent_id=intent_id,event_bar_index=i,
                               event_time_utc=f['close_time_utc'],signal_bar_index=i,due_bar_index=due,
                               due_time_utc=due_time,side='BUY' if action == 1 else 'SELL',reason='source state gate'))
        decisions.append(dict(bar_index=i,date=f['date'],decision_time_utc=f['close_time_utc'],
                              ready=f['slow_ready'],ema13=f['ema13'],ema48=f['ema48'],holding_quantity=qty,
                              action=action,intent_id=intent_id,due_bar_index=due,due_time_utc=due_time))
        assert cash >= 0 and qty >= 0 and math.isfinite(equity)
        nav.append(dict(bar_index=i,date=f['date'],close_time_utc=f['close_time_utc'],equity=equity,
                        cash=cash,quantity=qty,raw_close=float(row.close),drawdown=equity/peak-1,
                        ready=f['slow_ready'],signal=action,pending_count=sum(map(len,pending.values()))))
    terminal = [dict(due_bar_index=due, **intent) for due, intents in sorted(pending.items()) for intent in intents]
    return dict(nav=nav,fills=fills,decisions=decisions,pending=events,terminal_pending=terminal)


def load_input(path, protocol):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == protocol['input']['sha256']
    f = pd.read_csv(path)
    expected = pd.date_range('2022-12-01','2024-12-31',tz='UTC',freq='D').asi8 // 1000000
    assert len(f)==762 and (f.open_time.to_numpy()==expected).all()
    assert ((f.close_time-f.open_time)==DAY-1).all()
    numeric = f.to_numpy(dtype=float)
    assert __import__('numpy').isfinite(numeric).all()
    assert (f.low>0).all() and (f.high>=f[['open','close','low']].max(axis=1)).all()
    assert (f.low<=f[['open','close','high']].min(axis=1)).all()
    assert (f.volume>0).all() and (f.quote_volume>0).all()
    cut = f[f.open_time >= pd.Timestamp(protocol['evaluation']['start']).value//1000000].reset_index(drop=True)
    assert len(cut)==731
    return cut


def write_csv(path, rows, fields):
    with path.open('x', newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)


def main(input_path, out):
    protocol=json.loads((FAMILY/'specs/protocol-v1.json').read_text())
    f=load_input(input_path,protocol)
    out.mkdir(parents=True,exist_ok=False)
    fs=features(f);write_csv(out/'features.csv',fs,FEATURE_FIELDS)
    summary={}
    for name,fee,lag in CASES:
        r=run(f,fee,lag,name,fs)
        for kind,fields in [('nav',NAV_FIELDS),('fills',FILL_FIELDS),('decisions',DECISION_FIELDS),('pending',PENDING_FIELDS)]:
            write_csv(out/f'{name}-{kind}.csv',r[kind],fields)
        (out/f'{name}-terminal-pending.json').write_text(json.dumps(r['terminal_pending'],indent=2)+'\n')
        nav=pd.DataFrame(r['nav']); periods={}
        for year in ('2023','2024'):
            section=nav[nav.date.str.startswith(year)];first=section.index[0]
            periods[year]=metrics(section,100000 if first==0 else nav.iloc[first-1].equity)
        summary[name]={'metrics':metrics(nav,100000),'periods':periods,'fills':len(r['fills']),
                       'completed_round_trips':sum(x['side']=='SELL' for x in r['fills']),
                       'queued_intents':sum(x['event']=='QUEUED' for x in r['pending']),
                       'skipped_stale_intents':sum(x['event']=='SKIPPED_STALE' for x in r['pending']),
                       'terminal_pending':len(r['terminal_pending']),'terminal_quantity':r['nav'][-1]['quantity'],
                       'terminal_cash':r['nav'][-1]['cash'],'fee_bps':fee,'lag_days':lag}
    (out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    manifest=[{'path':x.name,'bytes':x.stat().st_size,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in sorted(out.iterdir())]
    (out/'RESULT-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'strategy_configurations':4,'new_controls':0,'output_files':len(manifest),'output_dir':str(out)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();main(a.input,a.output)
