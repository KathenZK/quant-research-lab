"""Independent artifact/report acceptance; does not run or select strategies."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[4]
FAMILY=Path(__file__).resolve().parents[1]
A=FAMILY/'artifacts'
REPORT=FAMILY/'diagnostics/report-20260910.md'
TERMINAL={'terminal_mark','audit_terminal_close','data_end','end_of_data','window_end','end_of_sample','terminal_close','end_mark'}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv(path):
    try:return pd.read_csv(path)
    except pd.errors.EmptyDataError:return pd.DataFrame()


def artifact_paths(row):
    p=Path(row['equity_path'])
    if not p.is_absolute():p=ROOT/p
    if p.name.endswith('_equity.csv'):
        return p,p.with_name(p.name.replace('_equity.csv','_monthly.csv')),p.with_name(p.name.replace('_equity.csv','_trades.csv'))
    if p.name.startswith('equity_'):
        return p,p.with_name(p.name.replace('equity_','monthly_')),p.with_name(p.name.replace('equity_','trades_'))
    return p,p.parent/'monthly.csv',p.parent/'trades.csv'


def visibility_shift(row,source):
    """Known source semantics only; never infer from curve values."""
    p=str(row['equity_path'])
    if '/hype_legacy/' in p:return pd.Timedelta(minutes=15),'bar_open_label_close_valuation'
    if '/other_assets/' in p and re.search(r'/(BTC|ETH|SOL|BNB|TRX)/',p):return pd.Timedelta(0),'actual_close_timestamp'
    if '/other_assets/unregistered_observations/' in p:return pd.Timedelta(0),'actual_valuation_timestamp_from_observation_adapter'
    if '/ensemble/' in p:return pd.Timedelta(0),'actual_close_timestamp'
    if '/AS6S_V6/' in p:return pd.Timedelta(0),'actual_close_timestamp'
    # Worker can declare semantics per case; this takes precedence over map.
    semantic=row.get('equity_timestamp_semantics') or (source.get('equity_timestamp_semantics',source.get('curve_timestamp_semantics','')) if isinstance(source,dict) else '')
    if isinstance(semantic,dict):
        if semantic.get('label')=='bar_open':return pd.Timedelta(minutes=float(semantic['bar_duration_minutes'])),semantic
        if semantic.get('label') in ('valuation_time','actual_close','close_time'):return pd.Timedelta(0),semantic
        minutes=semantic.get('valuation_delay_minutes')
        if minutes is not None:return pd.Timedelta(minutes=float(minutes)),semantic
    if isinstance(semantic,str) and ('actual_close' in semantic or 'close_time' in semantic or 'valuation_time' in semantic):return pd.Timedelta(0),semantic
    case=Path(p).parent.name
    known={'ar_v4':60,'keltner_v3':30,'mmtf_1h_v3':60,'mmtf_15m_v3':15,'mdtp_v1':15,'bksb_15m':15,'bksb_1h':60}
    if case.startswith('keltner15_'):known[case]=15
    if case in known:return pd.Timedelta(minutes=known[case]),'bar_open_label_close_valuation'
    if case.startswith('mhef_1h_buffer'):return pd.Timedelta(0),'open_to_open_equity_at_timestamp'
    return None,'source_timestamp_semantics_not_yet_declared'


def main():
    rows=read(A/'all_results.json')
    report=REPORT.read_text()
    issues=[];checks=[];observations=[]
    def issue(level,code,**extra):issues.append({'level':level,'code':code,**extra})
    identities=[(x['name'],x.get('start')) for x in rows]
    if len(set(identities))!=len(identities):issue('error','DUPLICATE_AGGREGATE_ROW')
    for row in rows:
        name=row['name'];p,mp,tp=artifact_paths(row)
        source_path=ROOT/row['source'] if row.get('source') else None
        source=read(source_path) if source_path and source_path.exists() else {}
        if not p.is_file():issue('error','MISSING_EQUITY',name=name,path=str(p));continue
        frame=csv(p);tc='ts' if 'ts' in frame else frame.columns[0]
        ec=next((c for c in ('equity','net_equity','equity_net') if c in frame),None)
        if ec is None:issue('error','MISSING_EQUITY_COLUMN',name=name);continue
        times=pd.to_datetime(frame[tc],utc=True,format='mixed')
        values=pd.to_numeric(frame[ec])
        if not np.isfinite(values).all():issue('error','NONFINITE_EQUITY',name=name)
        s=pd.Series(values.values,index=times).sort_index()
        s=s[s.index>=pd.Timestamp(row['start'])]
        assert len(s)
        end_return=float(s.iloc[-1]-1)
        total_error=abs(end_return-float(row['return']))
        if total_error>1e-9:issue('error','RETURN_CURVE_MISMATCH',name=name,reported=row['return'],curve_return=end_return)
        close_dd=float((s/s.cummax().clip(lower=1)-1).min())
        if float(row['drawdown'])>close_dd+1e-9:issue('error','DRAWDOWN_UNDERSTATED_VS_CURVE',name=name,reported=row['drawdown'],curve_drawdown=close_dd)
        monthly_error=None;monthly=None;scaling=1;col=None
        if mp.is_file():
            monthly=csv(mp)
            col=next((c for c in ('return','monthly_return','return_pct','monthly_return_pct') if c in monthly),None)
            if col:
                scaling=100 if '/hype_legacy/' in str(mp) or col.endswith('_pct') else 1
                monthly_values=pd.to_numeric(monthly[col])
                if not np.isfinite(monthly_values).all():issue('error','NONFINITE_MONTHLY_RETURN',name=name)
                compounded=float(np.prod(1+monthly_values/scaling))
                monthly_error=abs(compounded-float(s.iloc[-1]))
                if monthly_error>1e-9:issue('error','MONTHLY_COMPOUND_MISMATCH',name=name,difference=monthly_error)
            else:issue('warning','UNKNOWN_MONTHLY_SCHEMA',name=name,columns=list(monthly))
        else:issue('warning','MISSING_MONTHLY_FILE',name=name,path=str(mp))
        trade_details={}
        if tp.is_file():
            trades=csv(tp)
            reason=next((c for c in ('exit_reason','reason') if c in trades),None)
            if reason:
                labels=trades[reason].astype(str)
                terminal=labels.isin(TERMINAL) | labels.str.contains('terminal|force_flatten',case=False,regex=True)
                nterminal=int(terminal.sum());natural=len(trades)-nterminal
                trade_details={'ledger_rows':len(trades),'natural_closed':natural,'terminal_settlements':nterminal,'exit_reasons':labels.value_counts().to_dict()}
                if int(row['trades'])!=len(trades):issue('error','TRADE_COUNT_MISMATCH',name=name,reported=row['trades'],ledger=len(trades))
                if nterminal and not ('期末结算' in report or '期末估值' in report):issue('error','TERMINAL_COUNT_NOT_EXPLAINED',name=name)
                if isinstance(source,dict) and source.get('open_position') and not nterminal:issue('error','END_POSITION_WITHOUT_TERMINAL_SETTLEMENT',name=name,open_position=source['open_position'])
            elif len(trades) and 'position' in trades:
                sign=np.sign(pd.to_numeric(trades.position))
                count=int(((sign!=0)&(sign!=sign.shift(1).fillna(0))).sum())
                trade_details={'unit':'directional position segments, not natural round trips','directional_entries':count,'rebalance_rows':len(trades)}
                if int(row['trades'])!=count:issue('warning','DIRECTIONAL_COUNT_DIFFERENCE',name=name,reported=row['trades'],computed=count)
            elif trades.empty and int(row['trades'])==0:
                trade_details={'ledger_rows':0,'natural_closed':0,'terminal_settlements':0}
            else:issue('warning','UNKNOWN_TRADE_UNIT',name=name,columns=list(trades))
        else:issue('warning','MISSING_TRADE_FILE',name=name,path=str(tp))
        shift,semantic=visibility_shift(row,source)
        if shift is not None:
            visible=s.copy();visible.index=visible.index+shift
            # Explicit terminal rows represent final valuation already at END.
            end=pd.Timestamp('2026-09-05T15:00:00Z')
            visible.index=pd.DatetimeIndex([min(t,end) for t in visible.index])
            cut=pd.Timestamp(row['start'])+pd.Timedelta(days=30)
            if visible.index[-1]>=cut:
                before=visible[visible.index<=cut]
                first=float(before.iloc[-1]-1) if len(before) else 0.
                after=float(visible.iloc[-1]/before.iloc[-1]-1) if len(before) else end_return
                if row.get('first30_return') is not None and abs(first-row['first30_return'])>1e-9:issue('error','FIRST30_TIMESTAMP_BOUNDARY',name=name,reported=row['first30_return'],expected=first,semantics=semantic)
                if row.get('after30_return') is not None and abs(after-row['after30_return'])>1e-9:issue('error','AFTER30_TIMESTAMP_BOUNDARY',name=name,reported=row['after30_return'],expected=after)
            elif row.get('first30_return') is not None:issue('warning','FIRST30_WINDOW_NOT_COMPLETE',name=name)
            july=visible[visible.index<=pd.Timestamp('2026-08-01T00:00Z')]
            august=visible[visible.index<=pd.Timestamp('2026-09-01T00:00Z')]
            august_return=float(august.iloc[-1]/(july.iloc[-1] if len(july) else 1.)-1) if len(august) else None
            if august_return is not None and row.get('august_return') is not None and abs(august_return-row['august_return'])>1e-9:issue('error','AUGUST_TIMESTAMP_BOUNDARY',name=name,reported=row['august_return'],expected=august_return)
            if monthly is not None and col is not None:
                month_col='month' if 'month' in monthly else monthly.columns[0]
                for record in monthly.to_dict('records'):
                    month=str(record[month_col])[:7]
                    left=pd.Timestamp(month+'-01',tz='UTC');right=left+pd.offsets.MonthBegin(1)
                    before=visible[visible.index<=left];after=visible[visible.index<=right]
                    expected_month=float((after.iloc[-1] if len(after) else 1.)/(before.iloc[-1] if len(before) else 1.)-1)
                    actual_month=float(record[col])/scaling
                    if abs(actual_month-expected_month)>1e-9:issue('error','SOURCE_MONTH_TIMESTAMP_BOUNDARY',name=name,month=month,reported=actual_month,expected=expected_month)
        if name not in report:issue('error','RESULT_MISSING_FROM_REPORT',name=name,positive=row['return']>0,registered=row['registered'])
        # Report should display the same decimal-to-percentage conversion.
        expected_pct=f"{100*float(row['return']):+.2f}%"
        matching=[line for line in report.splitlines() if line.startswith('| '+name+' |')]
        if matching and not any(expected_pct in line for line in matching):issue('error','REPORT_PERCENT_DISPLAY_MISMATCH',name=name,expected=expected_pct)
        if not row['registered'] and row['return']>0:observations.append({'name':name,'return':row['return'],'trades_or_segments':row['trades'],'present_in_report':name in report})
        checks.append({'name':name,'curve_sha256':sha(p),'return_curve_abs_difference':total_error,'monthly_compound_abs_difference':monthly_error,'reported_drawdown':row['drawdown'],'curve_drawdown':close_dd,'timestamp_semantics':semantic,**trade_details})
    primary=[r for r in rows if r['primary']]
    counts={'registered_rows':len(primary),'positive':sum(r['return']>1e-12 for r in primary),'negative':sum(r['return']<-1e-12 for r in primary),'zero':sum(abs(r['return'])<=1e-12 for r in primary),'zero_trade_rows':sum(int(r['trades'])==0 for r in primary),'all_rows':len(rows),'observation_rows':sum(not r['primary'] for r in rows),'positive_observation_rows':len(observations)}
    expected=f"{counts['positive']} 组期末盈利、{counts['negative']} 组亏损、{counts['zero']} 组没有交易"
    if expected not in report:issue('error','REPORT_COUNTS_STALE_OR_WRONG',expected=expected)
    if counts['zero']!=counts['zero_trade_rows']:issue('error','ZERO_RETURN_IS_NOT_ZERO_TRADES',counts=counts)
    if '不宣称已跑完整仓库' not in report and '未覆盖全部仓库' not in report:issue('error','COVERAGE_LIMIT_NOT_STATED')
    coverage_checks=[]
    if not (A/'coverage_inventory.json').exists():issue('warning','COVERAGE_INVENTORY_PENDING')
    else:
        coverage=read(A/'coverage_inventory.json')
        if not coverage:issue('error','EMPTY_COVERAGE_INVENTORY')
        for item in coverage.get('rows',[]):
            pins=dict(item.get('evidence_sha256',{}))
            if item.get('source_path') and item.get('source_sha256'):
                pins[item['source_path']]=item['source_sha256']
            for rel,expected in pins.items():
                path=ROOT/rel
                matched=path.is_file() and sha(path)==expected
                coverage_checks.append({'family':item['family'],'source':rel,'sha256_matches':matched})
                if not matched:issue('error','REGISTRATION_EVIDENCE_HASH_DRIFT',family=item['family'],source=rel)
            registration=item.get('registration')
            if isinstance(registration,str) and item.get('start'):
                saved=pd.Timestamp(registration)
                if saved.tzinfo is None:saved=saved.tz_localize('UTC')
                earliest=saved+pd.Timedelta(days=1) if len(registration)==10 else saved
                if pd.Timestamp(item['start'])<earliest:issue('error','START_PRECEDES_REGISTRATION_BOUNDARY',family=item['family'])
    cc=[r for r in primary if r['name']=='HYPE-CC-V35']
    if cc and not ('歧义' in cc[0].get('limitation','') or 'disagree' in cc[0].get('limitation','')):issue('error','CC_TIMING_AMBIGUITY_OMITTED')
    as6s_checks=[]
    as6s=A/'other_assets/AS6S_V6'
    if (as6s/'results.json').exists():
        recovery=read(A/'other_assets/as6s_recovery.json')
        pinned=[{'path':str(p),'matches':Path(p).exists() and sha(Path(p))==expected} for p,expected in recovery['source_pins'].items()]
        if not all(r['matches'] for r in pinned):issue('error','AS6S_RECOVERED_SOURCE_PIN_DRIFT')
        if not recovery.get('original_lab_freeze_json_missing'):issue('error','AS6S_ORIGINAL_FREEZE_MISSING_NOT_DECLARED')
        for route,settings in recovery['routes'].items():
            if settings['account_scale']!=.75 or len(settings['sleeves'])!=15:issue('error','AS6S_FROZEN_ROUTE_IDENTITY_MISMATCH',route=route)
        native=read(as6s/'results.json')
        if not any('not rerun historical parity' in limitation for limitation in native['limitations']):issue('error','AS6S_RECOVERY_PARITY_BOUNDARY_NOT_DECLARED')
        for row in native['results']:
            prefix=row['route']+'_'+row['scenario'];trades=csv(as6s/f'{prefix}_trades.csv');curve=csv(as6s/f'{prefix}_equity.csv')
            entered=pd.to_datetime(trades.entry_ts,utc=True,format='mixed');exited=pd.to_datetime(trades.exit_ts,utc=True,format='mixed')
            overlaps=int((entered.iloc[1:].reset_index(drop=True)<exited.iloc[:-1].reset_index(drop=True)).sum())
            compounded=float(np.prod(1+.75*trades.exposure*trades.net_return_1x)-1)
            start=pd.Timestamp(row['start']);end=pd.Timestamp(row['end'])
            bounds=bool((entered>=start).all() and (entered<end).all() and (exited<=end).all())
            if overlaps or not bounds or abs(compounded-row['return'])>1e-9:issue('error','AS6S_ACCOUNT_LEDGER_MISMATCH',route=prefix,overlaps=overlaps,bounds_pass=bounds)
            if row['trades']!=len(trades):issue('error','AS6S_TRADE_COUNT_MISMATCH',route=prefix)
            if abs(float(curve.equity.iloc[-1])-float(curve.closed_balance.iloc[-1]))>1e-12:issue('error','AS6S_UNSETTLED_END_POSITION',route=prefix)
            months=csv(as6s/f'{prefix}_monthly.csv');s=pd.Series(curve.equity.values,index=pd.to_datetime(curve.ts,utc=True,format='mixed'))
            for record in months.to_dict('records'):
                month=str(record['month'])[:7];left=pd.Timestamp(month+'-01',tz='UTC');right=left+pd.offsets.MonthBegin(1)
                before=s[s.index<=left];after=s[s.index<=right]
                value=float((after.iloc[-1] if len(after) else 1.)/(before.iloc[-1] if len(before) else 1.)-1)
                if abs(value-record['return'])>1e-9:issue('error','AS6S_MONTH_TIMESTAMP_BOUNDARY',route=prefix,month=month,reported=record['return'],expected=value)
            as6s_checks.append({'route_scenario':prefix,'trades':len(trades),'overlaps':overlaps,'bounds_pass':bounds,'terminal_settlements':int((exited==end).sum()),'last_natural_exit':exited.max(),'scale':.75,'maximum_scaled_exposure':float((.75*trades.exposure).max()),'trade_compounding_abs_difference':abs(compounded-row['return']),'end_equity_equals_closed_balance':bool(curve.equity.iloc[-1]==curve.closed_balance.iloc[-1])})
    errors=[x for x in issues if x['level']=='error']
    result={'reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'status':'PASS' if not errors else 'FAIL','scope':'Independent aggregate, source-artifact arithmetic and presentation review; no additional strategy tests or parameter selection','all_results_sha256':sha(A/'all_results.json'),'build_report_sha256':sha(FAMILY/'scripts/build_report.py'),'report_sha256':sha(REPORT),'coverage_inventory_sha256':sha(A/'coverage_inventory.json') if (A/'coverage_inventory.json').exists() else None,'counts':counts,'issues':issues,'checks':checks,'positive_observations':observations,'registration_evidence_hash_checks':coverage_checks,'as6s_recovered_account_review':as6s_checks}
    (A/'acceptance_independent.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str)+'\n')
    print(json.dumps({'status':result['status'],'counts':counts,'errors':errors,'warnings':sum(x['level']=='warning' for x in issues)},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
