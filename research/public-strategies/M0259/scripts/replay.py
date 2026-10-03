#!/usr/bin/env python3
"""M0259 diagnostic port, authored 2026-10-03, GPL-3.0-or-later.
Signal design: Gert Wohlgemuth, freqtrade-strategies BbandRsi.
Execution is an explicit research assumption, not the Freqtrade backtester.
No network, tuning, leverage or trading API calls.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd
import talib

QTP_SHA = '39de0b1a666c05e0c11034c993eb96212eb505d20d630712c4bb503008609760'
INITIAL = 100000.0
FRACTION = 0.95
START = '2023-01-01T00:00:00Z'
END = '2025-01-01T00:00:00Z'
CASES = [('base',8,1,False),('fee0',0,1,False),('fee20',20,1,False),('delay2',8,2,False),('buyhold',8,1,True)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_qtp(path):
    if sha(path) != QTP_SHA:
        raise ValueError('qtpylib source hash MISMATCH')
    spec = importlib.util.spec_from_file_location('locked_qtpylib', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def indicators(frame, qtp):
    out = pd.DataFrame(index=frame.index)
    # Default compatibility and zero unstable period explicitly asserted.
    if talib.get_compatibility() != 0 or talib.get_unstable_period('RSI') != 0:
        raise ValueError('Non-frozen TA-Lib global setting')
    out['rsi'] = talib.RSI(frame.close.to_numpy(dtype=float), timeperiod=14)
    bb = qtp.bollinger_bands(qtp.typical_price(frame), window=20, stds=2)
    out['bb_lower'] = bb['lower']
    out['bb_mid'] = bb['mid']
    out['bb_upper'] = bb['upper']
    out['entry'] = (out['rsi'] < 30) & (frame.close < out.bb_lower)
    out['exit'] = out['rsi'] > 70
    return out


def load_data(path):
    df = pd.read_csv(path)
    required = ['open_time','open','high','low','close','volume','close_time','ts',
                'exchange','market_type','timeframe','symbol','native_symbol','source']
    if not set(required).issubset(df):
        raise ValueError('Missing columns: ' + str(set(required)-set(df)))
    times = pd.to_datetime(df.ts, utc=True)
    expected = pd.date_range('2022-12-01T00:00:00Z', END, inclusive='left',freq='h')
    if len(times) != len(expected) or not np.array_equal(times.astype('int64'),expected.astype('int64')):
        raise ValueError('Input must retain exact sorted duplicate-free full UTC hourly grid')
    if not np.array_equal(df.open_time.astype('int64').values, expected.asi8//1000000):
        raise ValueError('Open time mismatch')
    if not np.array_equal(df.close_time.astype('int64').values, df.open_time.astype('int64').values+3599999):
        raise ValueError('Native close timestamp mismatch')
    for col,value in [('exchange','binance'),('market_type','spot'),('timeframe','1h'),('symbol','BTC/USDT'),('native_symbol','BTCUSDT'),('source','binance_vision')]:
        if not df[col].eq(value).all():
            raise ValueError('Identity mismatch '+col)
    n = df[['open','high','low','close','volume']].to_numpy(dtype=float)
    if not np.isfinite(n).all() or (n[:,:4] <= 0).any() or (n[:,4] < 0).any():
        raise ValueError('Invalid OHLCV')
    if not ((df.high>=df[['open','close','low']].max(axis=1)) & (df.low<=df[['open','close','high']].min(axis=1))).all():
        raise ValueError('OHLC relationship')
    df['ts'] = times.dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    return df


def simulate(df, sig, fee_bps=8, lag=1, buyhold=False):
    """Streaming one-position ledger. Read only i-lag signals at open i.
    ROI target includes both fees; 2bps adverse exit slip follows target trigger.
    Open-gap chronology dominates later high/low, then pessimistic SL before ROI.
    No forced terminal liquidation. Signal after evaluation close cannot execute.
    """
    fee=fee_bps/10000.0
    slip=0.0002
    cash=INITIAL
    peak=INITIAL
    qty=0.0
    position=None
    records=[]
    trades=[]
    events=[]
    ambiguity=[]
    es=np.flatnonzero((df.ts>=START)&(df.ts<END))
    for k,i in enumerate(es):
        r=df.iloc[i]
        previous=i-lag
        valid=previous>=0
        enter=bool(sig.entry.iloc[previous]) if valid else False
        leave=bool(sig.exit.iloc[previous]) if valid else False
        signal_ts=df.ts.iloc[previous] if valid else None
        reason=None
        raw_fill=None
        phase=None
        # Existing position evaluated before entries; no same-bar re-entry.
        held_at_open=qty>0
        if held_at_open and not buyhold:
            target=position['entry_fill']*(1+fee)*1.1/(1-fee)
            stop=position['entry_fill']*0.75
            if leave:
                reason,raw_fill,phase='exit_signal',r.open,'open'
            elif r.open<=stop:
                reason,raw_fill,phase='stop_gap',r.open,'open'
            elif r.open>=target:
                reason,raw_fill,phase='roi_gap',r.open,'open'
            elif r.low<=stop:
                reason,raw_fill,phase='stoploss',stop,'intrabar'
            elif r.high>=target:
                reason,raw_fill,phase='roi',target,'intrabar'
            if r.low<=stop and r.high>=target:
                ambiguity.append({'ts':r.ts,'both_thresholds':True,'new_entry':False,'signal_exit_priority':leave,
                                  'path_ambiguous':not leave and stop<r.open<target,
                                  'resolution':'signal_at_open' if leave else ('gap_at_open' if not stop<r.open<target else 'pessimistic_stop_first')})
        if not held_at_open and ((buyhold and k==0) or (not buyhold and enter and not leave)):
            price=float(r.open)*(1+slip)
            budget=cash*FRACTION
            qty=budget/(price*(1+fee))
            entry_fee=qty*price*fee
            cash-=budget
            position={'entry_ts':r.ts,'entry_signal_ts':None if buyhold else signal_ts,
                      'entry_fill':price,'entry_raw':float(r.open),'qty':qty,'entry_fee':entry_fee,
                      'entry_budget':budget,'entry_index':int(i)}
            events.append({'ts':r.ts,'side':'buy','phase':'open','reason':'buyhold' if buyhold else 'entry_signal',
                           'signal_ts':position['entry_signal_ts'],'raw_price':float(r.open),'fill_price':price,
                           'qty':qty,'fee':entry_fee,'cash_after':cash})
            if not buyhold:
                target=price*(1+fee)*1.1/(1-fee)
                stop=price*0.75
                if r.low<=stop and r.high>=target:
                    ambiguity.append({'ts':r.ts,'both_thresholds':True,'new_entry':True,'signal_exit_priority':False,
                                      'path_ambiguous':True,'resolution':'pessimistic_stop_first'})
                if r.low<=stop:
                    reason,raw_fill,phase='stoploss',stop,'intrabar'
                elif r.high>=target:
                    reason,raw_fill,phase='roi',target,'intrabar'
        if qty>0 and reason:
            fill=float(raw_fill)*(1-slip)
            exit_fee=qty*fill*fee
            proceeds=qty*fill-exit_fee
            cash+=proceeds
            trade={**position,'exit_ts':r.ts,'exit_signal_ts':signal_ts if reason=='exit_signal' else None,
                   'exit_raw':float(raw_fill),'exit_fill':fill,'exit_fee':exit_fee,'exit_reason':reason,
                   'exit_phase':phase,'pnl':proceeds-position['entry_budget'],
                   'return':proceeds/position['entry_budget']-1,'holding_bars':int(i-position['entry_index'])}
            trades.append(trade)
            events.append({'ts':r.ts,'side':'sell','phase':phase,'reason':reason,
                           'signal_ts':trade['exit_signal_ts'],'raw_price':float(raw_fill),'fill_price':fill,
                           'qty':qty,'fee':exit_fee,'cash_after':cash})
            qty=0.0
            position=None
        nav=cash+qty*float(r.close)
        peak=max(peak,nav)
        records.append({'ts':r.ts,'close_ts':(pd.Timestamp(r.ts)+pd.Timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'cash':cash,'qty':qty,'close':float(r.close),'equity':nav,'drawdown':nav/peak-1,'net_liquidation_equity':cash+qty*float(r.close)*(1-slip)*(1-fee)})
    return pd.DataFrame(records),pd.DataFrame(trades),pd.DataFrame(events),ambiguity,position


def stats(curve,trades,events,position,ambiguity):
    x=curve.equity.to_numpy()
    ret=np.diff(np.r_[INITIAL,x])/np.r_[INITIAL,x[:-1]]
    peaks=np.maximum.accumulate(np.r_[INITIAL,x])[1:]
    daily=curve.groupby(curve.ts.str[:10],sort=True).tail(1)
    dr=np.diff(np.r_[INITIAL,daily.equity.to_numpy()])/np.r_[INITIAL,daily.equity.to_numpy()[:-1]]
    std=float(dr.std(ddof=1))
    return {'start':START,'end':'2024-12-31T23:59:59.999Z','observations':len(curve),
            'daily_observations':len(daily),'initial_equity':INITIAL,'final_equity':float(x[-1]),
            'total_return':float(x[-1]/INITIAL-1),'max_drawdown':float(np.min(x/peaks-1)),
            'sharpe':float(dr.mean()/std*np.sqrt(365)) if std else None,
            'sharpe_method':'UTC daily close returns, sample std ddof=1, rf=0, sqrt(365)',
            'annualized_return':float((x[-1]/INITIAL)**(365/len(daily))-1),
            'closed_trades':len(trades),'fills':len(events),
            'win_rate':float((trades.pnl>0).mean()) if len(trades) else None,
            'total_fees':float(events.fee.sum()) if len(events) else 0.,
            'position_close_exposure_fraction':float((curve.qty>0).mean()),
            'open_position':position,'both_threshold_range_overlap_bars':len(ambiguity),
            'ambiguous_intrabar_path_bars':sum(a['path_ambiguous'] for a in ambiguity),
            'ending_net_liquidation_equity':float(curve.net_liquidation_equity.iloc[-1]),
            'max_drawdown_sign':'negative fraction; computed on all hourly closes, initial cash included',
            'hourly_return_observations':len(ret)}


def dump_json(p,obj):
    Path(p).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def write_csv(df,path):
    df.to_csv(path,index=False,float_format='%.12g',lineterminator='\n')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True)
    ap.add_argument('--qtpylib',required=True)
    ap.add_argument('--freeze',required=True)
    ap.add_argument('--out',required=True)
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]
    freeze=json.loads(Path(args.freeze).read_text())
    if freeze['status']!='FROZEN_BEFORE_RETURNS': raise ValueError('Invalid freeze')
    if sha(args.input)!=freeze['input_sha256']: raise ValueError('Input hash MISMATCH')
    for p,h in freeze['code_and_spec_sha256'].items():
        if sha(root/p)!=h: raise ValueError('Frozen file MISMATCH '+p)
    if [np.__version__,pd.__version__,talib.__version__]!=['2.3.5','2.2.3','0.6.8']:raise ValueError('Dependency mismatch')
    if talib.__ta_version__.decode().split()[0]!='0.6.4':raise ValueError('TA-Lib C dependency mismatch')
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=False)
    data=load_data(args.input)
    sig=indicators(data,load_qtp(args.qtpylib))
    write_csv(pd.concat([data[['ts']],sig],axis=1),out/'indicators.csv')
    summary={'id':'M0259','run_id':'M0259-20261003-first-replay','variant_id':'M0259-BTCUSDT-1H-BBRSI-20261003',
             'fidelity_class':'HYPOTHESIS','status':'explore_untrusted_not_promoted','input_sha256':sha(args.input),
             'protocol_sha256':sha(root/'specs/M0259-first-replay.json'),'freeze_sha256':sha(args.freeze),
             'cases':{},'strategy_configurations':1,'strategy_execution_cases':4,'buyhold_controls':1,
             'parameter_searches':0,'old_search_count':'UNKNOWN','oos_claim':False}
    for name,fee,lag,bh in CASES:
        curve,trades,events,ambiguity,position=simulate(data,sig,fee,lag,bh)
        summary['cases'][name]={'fee_bps_per_side':fee,'adverse_slippage_bps_per_side':2,'signal_lag_bars':lag,
                                'metrics':stats(curve,trades,events,position,ambiguity)}
        write_csv(curve,out/(name+'_equity_hourly.csv'))
        daily=curve.groupby(curve.ts.str[:10],sort=True).tail(1)
        write_csv(daily,out/(name+'_equity_daily.csv'))
        write_csv(trades,out/(name+'_trades.csv'))
        write_csv(events,out/(name+'_fills.csv'))
        dump_json(out/(name+'_ambiguities.json'),ambiguity)
    dump_json(out/'summary.json',summary)
    dump_json(out/'curve_meta.json',{'public_curve':'base_equity_daily.csv','sampling':'last hourly close of each UTC day',
                  'raw_hourly_points':len(curve),'published_points':len(daily),'first_point':'2023-01-02T00:00:00Z',
                  'last_point':'2025-01-01T00:00:00Z','ts_semantics':'ts is final hourly bar open; close_ts is valuation instant',
                  'initial_equity':INITIAL,'metrics_computed_on':'hourly curve, except daily-return Sharpe',
                  'terminal_rule':'mark to last close, no forced exit; estimated liquidation marked separately'})
    dump_json(out/'result-manifest.json',{'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()},'self_excluded':True})
    print(json.dumps({k:v['metrics']['total_return'] for k,v in summary['cases'].items()}))

if __name__=='__main__':main()
