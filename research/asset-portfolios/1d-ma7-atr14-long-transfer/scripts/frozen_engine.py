"""Frozen HYPE spec replay. Standard library only. Run: python3 backtest.py.

The default reuses saved data. --fetch obtains a fresh snapshot, and is intended
for a COPY of this artifact directory to avoid changing the audited snapshot.
"""
import argparse
import ast
import csv
import datetime as dt
import hashlib
import json
import math
import statistics
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DAY = 86_400_000


def iso(ms):
    return dt.datetime.fromtimestamp(ms/1000, dt.timezone.utc).strftime('%Y-%m-%d')


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))


def fetch(contract):
    folder = ROOT/'data'
    folder.mkdir(exist_ok=True)
    collected, requests_log = {}, []
    start, end = contract['start_ms'], contract['end_ms_inclusive']
    cur = start
    duplicates = 0
    while cur <= end:
        stop = min(cur+60*DAY-1, end)
        payload = {'type':'candleSnapshot', 'req': {'coin':'HYPE','interval':'1d','startTime':cur,'endTime':stop}}
        errors = []
        for attempt in range(5):
            try:
                req = urllib.request.Request(contract['api'], data=json.dumps(payload).encode(), headers={'Content-Type':'application/json','User-Agent':'HypeSpecAudit/1.0'})
                with urllib.request.urlopen(req, timeout=35) as response:
                    raw = response.read()
                values = json.loads(raw)
                if not isinstance(values, list):
                    raise ValueError(f'Unexpected response: {str(values)[:200]}')
                break
            except Exception as exc:
                errors.append(str(exc))
                if attempt == 4:
                    write_json(folder/'fetch_failure.json', {'payload':payload,'errors':errors})
                    raise
                time.sleep(0.6*(attempt+1))
        stamp = dt.datetime.now(dt.timezone.utc).isoformat()
        filename = f"raw_{iso(cur)}_{iso(stop)}.json"
        (folder/filename).write_bytes(raw)
        times = [int(v['t']) for v in values]
        if times != sorted(times) or len(times) != len(set(times)):
            raise ValueError('Response order or duplicate timestamps invalid before normalization')
        for v in values:
            t = int(v['t'])
            if not start <= t <= end:
                raise ValueError('Returned candle outside overall requested interval')
            if t in collected:
                duplicates += 1
                if collected[t] != v:
                    raise ValueError('Conflicting duplicate candle')
            collected[t] = v
        requests_log.append({'request':payload, 'retrieved_at_utc':stamp, 'file':filename,'sha256':hashlib.sha256(raw).hexdigest(),'rows':len(values),'failed_attempts':errors})
        print('fetched', iso(cur), iso(stop), len(values), flush=True)
        cur = stop+1
        time.sleep(0.12)
    candles = [collected[t] for t in sorted(collected)]
    write_json(folder/'candles.json',candles)
    write_json(folder/'fetch_manifest.json',{'requests':requests_log,'duplicates':duplicates,'completed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat()})


def normalize(candles):
    bars = []
    for c in candles:
        if c['s'] != 'HYPE' or c['i'] != '1d':
            raise ValueError('Wrong instrument or interval')
        b = {'ts':int(c['t']), 'end_ts':int(c['T']), **{k:float(c[v]) for k,v in [('open','o'),('high','h'),('low','l'),('close','c')]}}
        if not all(math.isfinite(b[k]) and b[k] > 0 for k in ['open','high','low','close']):
            raise ValueError('Nonpositive or nonfinite OHLC')
        if not b['low'] <= min(b['open'],b['close']) <= max(b['open'],b['close']) <= b['high']:
            raise ValueError('Invalid OHLC ordering')
        if b['ts'] % DAY or b['end_ts'] != b['ts']+DAY-1:
            raise ValueError('Not a full UTC daily interval')
        bars.append(b)
    if not bars:
        raise ValueError('No candles')
    for a,b in zip(bars,bars[1:]):
        if b['ts']-a['ts'] != DAY:
            raise ValueError(f"Daily discontinuity: {iso(a['ts'])} -> {iso(b['ts'])}")
    return bars


def indicators(bars, ma_period=7, atr_period=14):
    close = [b['close'] for b in bars]
    ma, atr, tr, slope = [None]*len(bars),[None]*len(bars),[],[None]*len(bars)
    for i,b in enumerate(bars):
        if i >= ma_period-1:
            ma[i] = sum(close[i-ma_period+1:i+1])/ma_period
        tr.append(b['high']-b['low'] if i == 0 else max(b['high']-b['low'],abs(b['high']-close[i-1]),abs(b['low']-close[i-1])))
        if i == atr_period-1:
            atr[i] = sum(tr[:atr_period])/atr_period
        elif i >= atr_period:
            atr[i] = (atr[i-1]*(atr_period-1)+tr[i])/atr_period
        if i > 0 and ma[i-1] is not None and ma[i] is not None:
            slope[i] = (ma[i]-ma[i-1])/ma[i-1]*100
    return ma, atr, tr, slope


def execute(bars, mode='literal', threshold=0.0, fee=0.0, slip=0.0, force_end=True, indicator_override=None):
    assert mode in ('literal','lagged_stop','causal')
    ma, atr, tr, slope = indicator_override or indicators(bars)
    cash, pos, pending = 1.0, None, None
    trades, nav, events = [], [], []
    active_stops = []
    in_market_days = 0

    def buy(i, raw_price, signal_idx, stop):
        nonlocal pos
        fill = raw_price*(1+slip)
        units = cash/(fill*(1+fee))
        pos = {'entry_idx':i,'signal_idx':signal_idx,'entry_price':fill,'entry_raw_price':raw_price,'entry_equity':cash,'units':units,'stop':stop,'entry_fee':units*fill*fee}
        events.append({'i':i,'action':'entry','price':fill,'signal_idx':signal_idx,'stop':stop})

    def sell(i, raw_price, reason, stop_before=None, stop_after=None):
        nonlocal pos,cash
        fill = raw_price*(1-slip)
        cash = pos['units']*fill*(1-fee)
        trades.append({'entry_date':iso(bars[pos['entry_idx']]['ts']),'signal_date':iso(bars[pos['signal_idx']]['ts']),
                       'entry_price':pos['entry_price'],'exit_date':iso(bars[i]['ts']),'exit_price':fill,
                       'ret_pct':(cash/pos['entry_equity']-1)*100,'price_ret_pct':(fill/pos['entry_price']-1)*100,
                       'hold_days':i-pos['entry_idx'],'entry_idx':pos['entry_idx'],'exit_idx':i,
                       'reason':reason,'equity_before':pos['entry_equity'],'equity_after':cash,
                       'entry_fee':pos['entry_fee'],'exit_fee':pos['units']*fill*fee,
                       'stop_before':stop_before,'stop_after':stop_after})
        events.append({'i':i,'action':'exit','price':fill,'reason':reason})
        pos = None

    for i,b in enumerate(bars):
        if mode == 'causal' and pending is not None:
            buy(i,b['open'],pending['signal_idx'],pending['stop'])
            pending = None
        was_exposed = pos is not None
        stop_for_day = pos['stop'] if pos else None
        if pos is not None and (mode == 'causal' or i > pos['entry_idx']):
            before = pos['stop']
            if mode == 'literal' and ma[i] is not None and atr[i] is not None:
                pos['stop'] = max(pos['stop'],ma[i]-1.5*atr[i])
            stop = pos['stop']
            if mode != 'literal' and b['open'] <= stop:
                sell(i,b['open'],'gap_stop',before,stop)
            elif b['low'] <= stop:
                sell(i,stop,'stop',before,stop)
            elif mode == 'literal' and b['close'] <= stop:
                sell(i,b['close'],'close_stop',before,stop)
        if pos is not None and mode != 'literal' and ma[i] is not None and atr[i] is not None:
            pos['stop'] = max(pos['stop'],ma[i]-1.5*atr[i])
        signal = (i >= 14 and ma[i-1] is not None and ma[i] is not None and atr[i] is not None and
                  bars[i-1]['close'] < ma[i-1] and b['close'] > ma[i] and slope[i] is not None and slope[i] > threshold)
        if pos is None and signal:
            if mode == 'causal':
                pending = {'signal_idx':i,'stop':ma[i]-1.5*atr[i]}
            else:
                buy(i,b['close'],i,ma[i]-1.5*atr[i])
        if was_exposed:
            in_market_days += 1
        active_stops.append(stop_for_day)
        if force_end and i == len(bars)-1 and pos is not None:
            sell(i,b['close'],'end_of_test')
        nav.append(cash if pos is None else cash+pos['units']*(b['close']-pos['entry_price'])-pos['entry_fee'])
    peak, max_dd, peak_i, dd_peak, dd_trough = 1.0,0.0,0,0,0
    drawdowns = []
    for i,value in enumerate(nav):
        if value > peak:
            peak,peak_i = value,i
        dd = 1-value/peak
        drawdowns.append(dd)
        if dd > max_dd:
            max_dd,dd_peak,dd_trough = dd,peak_i,i
    n = len(trades)
    wins = sum(t['ret_pct'] > 0 for t in trades)
    days = (bars[-1]['ts']-bars[0]['ts'])/DAY
    equity = nav[-1]
    loss = sum(-t['ret_pct'] for t in trades if t['ret_pct'] < 0)
    gain = sum(t['ret_pct'] for t in trades if t['ret_pct'] > 0)
    recovery = next((iso(bars[i]['ts']) for i in range(dd_trough+1,len(nav)) if nav[i] >= nav[dd_peak]), None)
    metrics = {'equity':equity,'total_return_pct':(equity-1)*100,'cagr_pct':(equity**(365/days)-1)*100 if days else 0,
               'max_drawdown_pct':max_dd*100,'n_trades':n,'n_wins':wins,'win_rate_pct':wins/n*100 if n else 0,
               'avg_hold_days':statistics.mean(t['hold_days'] for t in trades) if n else 0,
               'avg_return_pct':statistics.mean(t['ret_pct'] for t in trades) if n else 0,
               'trade_return_profit_factor':gain/loss if loss else None,
               'buyhold_return_pct':(bars[-1]['close']/bars[0]['close']-1)*100,
               'exposure_days':in_market_days,'exposure_pct':in_market_days/len(bars)*100,
               'dd_peak_date':iso(bars[dd_peak]['ts']),'dd_trough_date':iso(bars[dd_trough]['ts']),'dd_recovery_date':recovery,
               'first_date':iso(bars[0]['ts']),'last_date':iso(bars[-1]['ts']),'n_bars':len(bars),
               'fee_bps_per_fill':fee*10000,'slippage_bps_per_fill':slip*10000,'funding_included':False}
    return {'metrics':metrics,'trades':trades,'nav':nav,'drawdowns':drawdowns,'events':events,'active_stops':active_stops}


def original_function_parity(bars, ours):
    # Only the reviewed original backtest function is executed; no download or
    # file-writing top-level code from the user's original script is executed.
    tree = ast.parse((ROOT/'source'/'hype_backtest.py').read_text())
    fn = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == 'backtest')
    ma,atr,_,_ = indicators(bars)
    env = {'bars':bars,'n':len(bars),'closes':[b['close'] for b in bars],'ma7':ma,'atr':atr}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<original-backtest-function>','exec'),env)
    worst = 0.0
    for threshold in [0.0,0.3,0.5,1.0]:
        old = env['backtest'](threshold)
        new = ours[str(threshold)]
        assert len(old['trades']) == len(new['trades'])
        for ot,nt in zip(old['trades'],new['trades']):
            assert ot[:2] == (nt['entry_idx'],nt['exit_idx'])
            assert max(abs(ot[2]-nt['entry_price']),abs(ot[3]-nt['exit_price'])) < 1e-10
        err = max(abs(a-b) for a,b in zip(old['nav'],new['nav']))
        worst = max(worst,err)
        assert err < 1e-10
    return {'status':'PASS','thresholds_checked':[0.0,0.3,0.5,1.0],'max_nav_abs_error':worst}


def acceptance(live, source, bars):
    r = live['0.0']; m = r['metrics']; m05 = live['0.5']['metrics']
    checks = []
    def check(name, actual, expected, tolerance=0):
        passed = abs(actual-expected) <= tolerance if isinstance(actual,(float,int)) else actual == expected
        checks.append({'check':name,'actual':actual,'expected':expected,'tolerance':tolerance,'status':'PASS' if passed else 'FAIL'})
    check('bars',len(bars),642)
    check('first_close_rounded',round(bars[0]['close'],2),12.72)
    check('last_close_live',bars[-1]['close'],87.51,0.5)
    check('buyhold_pct',m['buyhold_return_pct'],585.9,0.5)
    check('trades',m['n_trades'],14)
    check('wins',m['n_wins'],7)
    check('return_pct',m['total_return_pct'],464.9,1)
    check('max_drawdown_pct',m['max_drawdown_pct'],26.9,0.5)
    check('average_hold_days',m['avg_hold_days'],22.4,1)
    for idx,ed,ep,xd,xp in [(0,'2025-01-21',23.18,'2025-02-24',21.58),(1,'2025-03-18',14.18,'2025-03-26',13.07),(2,'2025-04-09',13.57,'2025-05-30',30.94),(-1,'2026-08-08',55.07,'2026-09-07',87.28)]:
        t = r['trades'][idx]
        check(f'trade_{idx}_entry_date',t['entry_date'],ed)
        check(f'trade_{idx}_entry_price',t['entry_price'],ep,0.005001)
        check(f'trade_{idx}_exit_date',t['exit_date'],xd)
        check(f'trade_{idx}_exit_price',t['exit_price'],xp,0.005001)
    for name,actual,expected,tol in [('slope05_trades',m05['n_trades'],12,0),('slope05_winrate',m05['win_rate_pct'],58.3,0.05),('slope05_return',m05['total_return_pct'],493.0,1),('slope05_drawdown',m05['max_drawdown_pct'],26.1,0.5)]:
        check(name,actual,expected,tol)
    original = source['nav0']
    peak = 1
    original_dd = 0
    for value in original:
        peak = max(peak,value)
        original_dd = max(original_dd,1-value/peak)
    # Do not relabel this old, unfinished-day snapshot as fresh official data.
    saved = {'original_saved_return_pct':(original[-1]-1)*100,'original_saved_max_drawdown_pct':original_dd*100,
             'original_saved_n_trades':len(source['trades']),
             'closed_close_max_abs_difference':max(abs(b['close']-c) for b,c in zip(bars[:-1],source['close'][:-1])),
             'closed_nav_max_abs_difference':max(abs(a-b) for a,b in zip(r['nav'][:-1],original[:-1])),
             'current_last_close':bars[-1]['close'],'original_last_close':source['close'][-1]}
    return {'live_checks':checks,'saved_snapshot_comparison':saved}


def save_run(name,result,bars):
    folder = ROOT/'results'
    folder.mkdir(exist_ok=True)
    write_json(folder/f'{name}.json',result)
    with (folder/f'{name}_trades.csv').open('w',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=list(result['trades'][0]))
        writer.writeheader(); writer.writerows(result['trades'])
    with (folder/f'{name}_nav.csv').open('w',newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['date','close','nav','buyhold_nav','drawdown_pct','active_stop_before_day'])
        for i,b in enumerate(bars):
            writer.writerow([iso(b['ts']),b['close'],result['nav'][i],b['close']/bars[0]['close'],result['drawdowns'][i]*100,result['active_stops'][i]])


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--fetch',action='store_true')
    opt = args.parse_args()
    contract = json.loads((ROOT/'frozen_contract.json').read_text())
    if opt.fetch:
        fetch(contract)
    candles = json.loads((ROOT/'data'/'candles.json').read_text())
    bars = normalize(candles)
    closed = [b for b in bars if b['ts'] < contract['closed_cutoff_ms_exclusive']]
    source = json.loads((ROOT/'source'/'original_snapshot.json').read_text())
    assert source['dates'] == [iso(b['ts']) for b in bars]
    data_audit = {'requested_first_date':iso(contract['start_ms']),'actual_first_date':iso(bars[0]['ts']),
                  'unavailable_leading_dates':[iso(v) for v in range(contract['start_ms'],bars[0]['ts'],DAY)],
                  'internal_missing_dates':[],'duplicates':0,'ohlc_valid':True,'utc_aligned':True,
                  'n_snapshot_bars':len(bars),'n_closed_bars':len(closed),'last_closed_date':iso(closed[-1]['ts']),
                  'unfinished_dates':[iso(b['ts']) for b in bars if b['ts'] >= contract['closed_cutoff_ms_exclusive']]}
    write_json(ROOT/'data_audit.json',data_audit)
    thresholds = contract['thresholds_pct_per_day']
    live = {str(t):execute(bars,threshold=t) for t in thresholds}
    original_closed = {str(t):execute(closed,threshold=t) for t in thresholds}
    causal_sensitivity = {str(t):execute(closed,mode='causal',threshold=t) for t in thresholds}
    runs = {'literal_live_snapshot':live['0.0'],'literal_closed':original_closed['0.0'],
            'lagged_stop_closed':execute(closed,mode='lagged_stop'),
            'causal_closed':causal_sensitivity['0.0'],
            'causal_cost_scenario':execute(closed,mode='causal',fee=0.0005,slip=0.0005)}
    for name,r in runs.items():
        save_run(name,r,bars if name == 'literal_live_snapshot' else closed)
    summary = {name:r['metrics'] for name,r in runs.items()}
    write_json(ROOT/'summary.json',summary)
    write_json(ROOT/'sensitivity.json',{name:{t:r['metrics'] for t,r in v.items()} for name,v in [('literal_live_snapshot',live),('literal_closed',original_closed),('causal_closed',causal_sensitivity)]})
    parity = original_function_parity(bars,live)
    write_json(ROOT/'original_function_parity.json',parity)
    write_json(ROOT/'acceptance.json',acceptance(live,source,bars))
    rows = [f"数据：{iso(closed[0]['ts'])} — {iso(closed[-1]['ts'])}，{len(closed)} 根已收盘 UTC 日K。",
            '原 Spec 斜率敏感性：阈值 | 交易数 | 胜率 | 平均持仓 | 累计收益 | 年化 | 买入持有 | 最大回撤 | 单笔平均']
    for t,r in original_closed.items():
        m = r['metrics']
        rows.append(f"{t}% | {m['n_trades']} | {m['win_rate_pct']:.2f}% | {m['avg_hold_days']:.2f} 天 | {m['total_return_pct']:+.2f}% | {m['cagr_pct']:+.2f}% | {m['buyhold_return_pct']:+.2f}% | {m['max_drawdown_pct']:.2f}% | {m['avg_return_pct']:+.2f}%")
    rows += ['', '基线逐笔：入场日 | 入场价 | 离场日 | 离场价 | 收益 | 持仓天数']
    for t in runs['literal_closed']['trades']:
        rows.append(f"{t['entry_date']} | {t['entry_price']:.4f} | {t['exit_date']} | {t['exit_price']:.4f} | {t['ret_pct']:+.2f}% | {t['hold_days']}")
    rows += ['', '注：最后一笔为终点结算；所有口径未计资金费率。', f"与原函数的一致性：{parity['status']}；最大净值误差 {parity['max_nav_abs_error']:.2e}。"]
    console = '\n'.join(rows)+'\n'
    (ROOT/'console_summary.txt').write_text(console)
    print(console)


if __name__ == '__main__':
    main()
