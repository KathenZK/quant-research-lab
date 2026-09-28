"""Read finished adaptation evidence and publish auditable tables and local HTML.

No strategy is fitted or replayed here. Fixed-period account returns retain
their producer's inherited-position boundaries; hypothetical matched episodes
are reported separately. Incomplete periods are never pooled into a success
rate or an apparently comparable return distribution.
"""
from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
import pandas as pd

from common import BASE, ROOT, sha, write_json

R = BASE / 'artifacts/adaptation_20260911'
OLD = BASE / 'artifacts/state_machine_20260910'
ARMS = ['U_READY', 'A_ASSET', 'B_ENTRY', 'C_ROUTE', 'D_JOINT']
ARM_NAMES = {'U_READY': '同90日准备期的V3', 'A_ASSET': '标的条件过滤',
             'B_ENTRY': '穿越条件过滤', 'C_ROUTE': '只选择退出方式', 'D_JOINT': '条件过滤＋退出选择',
             'FIXED_V3': '统一V3（同入场）', 'FIXED_DEFENSE': '统一S1（同入场）',
             'FIXED_EXTENSION': '统一S3（同入场）'}
PHASES = ['phase_2023_2024', 'phase_2025_2026']
PHASE_NAMES = {'phase_2023_2024': '2023–2024', 'phase_2025_2026': '2025–2026-09-04'}
ROUTE_NAMES = {'v3': '原V3', 'defense': 'S1防守', 'extension': 'S3延伸'}
FEATURE_NAMES = {
    'asset_observed_days_capped90': '本段已观察日数（最多90）',
    'asset_efficiency60': '60日价格路径效率', 'asset_cross_frequency60': '60日MA7穿越次数／60',
    'asset_return_autocorr60': '60日收盘收益一阶相关', 'asset_wick_ratio60': '60日上下影线占比中位数',
    'asset_atr_pct_median60': '60日ATR／收盘价中位数', 'asset_gap_atr_p95_60': '60日开盘跳空／前ATR的95分位',
    'asset_log10_quote_volume_median60': '60日成交额中位数的log10',
    'asset_cost_to_tr60': '往返成本／60日典型真实波幅', 'asset_v3_closed_count12': '此前已结束V3交易数（最多12笔）',
    'asset_v3_mean_return12': '此前已结束V3最近12笔平均收益',
    'asset_v3_pf_bounded12': '此前正收益／正收益与亏损绝对值之和',
    'asset_v3_win_rate12': '此前已结束V3最近12笔胜率',
    'entry_slope': '顺势MA7斜率／ATR', 'entry_previous_slope': '前日顺势MA7斜率／前ATR',
    'entry_slope_deceleration': '顺势归一斜率降速', 'entry_rsi': '方向×(RSI6−50)／50',
    'entry_ma7_distance_atr': '顺势偏离MA7／ATR', 'entry_ma30_distance_atr': '顺势偏离MA30／ATR',
    'entry_ma30_slope_atr': '顺势MA30斜率／ATR', 'entry_body_atr': '顺势K线实体／ATR',
    'entry_close_location': '顺势收盘位置（0至1）', 'entry_favorable_wick_atr': '顺势端影线／ATR',
    'entry_adverse_wick_atr': '逆势端影线／ATR', 'entry_pre_displacement5_atr': '穿越前5日顺势位移／前ATR',
    'entry_pre_displacement10_atr': '穿越前10日顺势位移／前ATR',
    'entry_pre_displacement20_atr': '穿越前20日顺势位移／前ATR',
    'entry_pre_efficiency20': '穿越前20日价格路径效率', 'entry_pre_tr_ratio5_20': '穿越前5日／20日真实波幅比',
    'entry_pre_cross_count20': '穿越前20日MA7穿越次数',
    'entry_signal_stop_distance_pct': '按信号收盘估算初始止损距离／收盘价',
    'entry_btc_return20': 'BTC顺势20日收益', 'entry_btc_return60': 'BTC顺势60日收益',
    'entry_btc_ma30_distance': 'BTC顺势偏离MA30比例',
}
SCOPE_NAMES = {'ELIGIBLE': '有90日条件的回放段', 'INSUFFICIENT_HISTORY90': '本期不足90日',
               'NO_EVALUATION_OVERLAP': '无2023年以后重叠段', 'NO_ORIGINAL_TRADING_WINDOW': '原输入不足交易准备期'}


class Source:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.manifest_path = self.directory / 'artifact_checksums.json'
        self.manifest = json.loads(self.manifest_path.read_text())
        assert json.loads((self.directory / 'completion.json').read_text())['complete'], directory
        self.used = {}

    def path(self, rel):
        p = self.directory / rel
        assert rel in self.manifest and sha(p) == self.manifest[rel], p
        self.used[rel] = self.manifest[rel]
        return p

    def csv(self, rel, *, allow_empty=False):
        p = self.path(rel)
        try:
            return pd.read_csv(p, float_precision='round_trip')
        except pd.errors.EmptyDataError:
            assert allow_empty
            return pd.DataFrame()

    def parquet(self, rel):
        return pd.read_parquet(self.path(rel))

    def json(self, rel):
        return json.loads(self.path(rel).read_text())

    def record(self):
        return {'directory': str(self.directory.relative_to(ROOT)),
                'manifest_sha256': sha(self.manifest_path), 'consumed_files': self.used}


def records(frame):
    return json.loads(frame.to_json(orient='records', date_format='iso', double_precision=15))


def number(value):
    return None if value is None or pd.isna(value) or not np.isfinite(float(value)) else float(value)


def fraction(a, b):
    return float(a / b) if b else None


def natural_case_metrics(g):
    """Equal-entry episode outcomes, never stitched into account equity."""
    ok = g.loc[g.ready90 & ~g.terminal_any].copy()
    win = ok.loc[ok.u_v3.gt(0)]
    loss = ok.loc[ok.u_v3.lt(0)]
    per_coin = ok.groupby('slug')[['u_v3', 'selected_u', 'delta_u']].mean()
    top = win.sort_values(['slug', 'u_v3', 'case_id'], ascending=[True, False, True]).groupby('slug').head(5)
    return {'all_cases': len(g), 'natural_ready_cases': len(ok), 'coins': ok.slug.nunique(),
        'terminal_cases': int(g.terminal_any.sum()), 'insufficient90_cases': int((~g.ready90).sum()),
        'kept': int(ok.allow.sum()), 'rejected': int((~ok.allow).sum()),
        'retained_ratio': fraction(ok.allow.sum(), len(ok)),
        'original_winners': len(win), 'winners_rejected': int((~win.allow).sum()),
        'winners_turned_loss': int(win.selected_u.lt(0).sum()),
        'original_losers': len(loss), 'losers_improved': int(loss.delta_u.gt(1e-12).sum()),
        'losers_avoided_by_rejection': int((~loss.allow).sum()),
        'mean_original_return_pct': number(ok.u_v3.mean() * 100),
        'mean_selected_return_pct': number(ok.selected_u.mean() * 100),
        'mean_improvement_pp': number(ok.delta_u.mean() * 100),
        'equal_coin_mean_original_return_pct': number(per_coin.u_v3.mean() * 100),
        'equal_coin_mean_selected_return_pct': number(per_coin.selected_u.mean() * 100),
        'equal_coin_mean_improvement_pp': number(per_coin.delta_u.mean() * 100),
        'coins_improved': int(per_coin.delta_u.gt(1e-12).sum()),
        'coins_worsened': int(per_coin.delta_u.lt(-1e-12).sum()),
        'positive_winner_retention': fraction(win.selected_u.clip(lower=0).sum(), win.u_v3.sum()),
        'top5_original_winners': len(top),
        'top5_positive_profit_retention': fraction(top.selected_u.clip(lower=0).sum(), top.u_v3.sum())}


def account_period_metrics(trades, events, a, b, account_end):
    a, b, account_end = pd.Timestamp(a), pd.Timestamp(b), pd.Timestamp(account_end)
    if len(trades):
        participating = trades.loc[trades.entry_time.lt(b) &
            (trades.exit_interval_end.gt(a) | trades.exit_time.eq(a))]
        # The producer settles the final open trade at its segment end. A
        # calendar boundary inside an account excludes fees at that boundary.
        mask = trades.exit_time.ge(a) & (trades.exit_time.lt(b) |
            (trades.exit_time.eq(b) & trades.exit_reason.eq('sample_end') & (b == account_end)))
        closed = trades.loc[mask]
        opened = trades.loc[trades.entry_time.ge(a) & trades.entry_time.lt(b)]
        pnl = closed.net_pnl
        wins, losses = pnl[pnl.gt(0)], -pnl[pnl.lt(0)]
        pf = fraction(wins.sum(), losses.sum())
        payoff = fraction(wins.mean(), losses.mean()) if len(wins) and len(losses) else None
    else:
        participating = closed = opened = trades
        wins = losses = pd.Series(dtype=float)
        pf = payoff = None
    e = events.loc[events.timestamp.ge(a) & events.timestamp.lt(b)] if len(events) else events
    attempts = e.loc[e.stage.isin(['filter', 'fill', 'sizing', 'admission'])] if len(e) else e
    rejected = attempts.loc[attempts.reason.eq('admission_rejected')] if len(attempts) else attempts
    cold = int(rejected.admission_rule_id.eq('INSUFFICIENT_HISTORY90').sum()) if len(rejected) else 0
    pre = int(rejected.admission_rule_id.eq('BEFORE_EVALUATION').sum()) if len(rejected) else 0
    fills = int(attempts.status.eq('filled').sum()) if len(attempts) else 0
    inherited = int((participating.entry_time.lt(a)).sum()) if len(participating) else 0
    return {'participating_trades': len(participating), 'entered_trades': len(opened),
        'closed_trades': len(closed), 'inherited_trades': inherited,
        'zero_trades': len(participating) == 0,
        'closed_trade_win_rate_pct': fraction(len(wins) * 100, len(closed)),
        'closed_trade_profit_factor': pf, 'closed_trade_payoff_ratio': payoff,
        'closed_trade_mean_win': number(wins.mean()), 'closed_trade_mean_loss': number(losses.mean()),
        'terminal_trades': int(closed.exit_reason.eq('sample_end').sum()) if len(closed) else 0,
        'qualified_flat_attempts': len(attempts), 'admission_rejected': len(rejected),
        'history90_rejected': cold, 'before_evaluation_rejected': pre,
        'learning_rejected': len(rejected) - cold - pre,
        'admission_passed': len(attempts) - len(rejected), 'entry_fills': fills,
        'other_fill_rejected': len(attempts) - len(rejected) - fills,
        'admission_passed_ratio': fraction(len(attempts) - len(rejected), len(attempts)),
        'entry_fill_ratio': fraction(fills, len(attempts)),
        **{'route_' + action + '_entries': int(opened.exit_route.eq(action).sum()) if len(opened) else 0
           for action in ROUTE_NAMES}}


def attach_periods(summary, blocks, source):
    rows = []
    grouped = {key: g for key, g in blocks.groupby(['run_key', 'case_id'])}
    for i, ((key, arm), g) in enumerate(summary.groupby(['run_key', 'case_id']), 1):
        assert len(g) == 1
        account = g.iloc[0]
        stem = f'runs/{key}/{arm}/full/'
        t = source.csv(stem + 'trades.csv', allow_empty=True)
        if len(t):
            for col in ['entry_time', 'exit_time', 'exit_interval_end']:
                t[col] = pd.to_datetime(t[col], utc=True)
        else:
            assert account.trades == 0
        e = source.csv(stem + 'entry_events.csv', allow_empty=True)
        if len(e):
            e['timestamp'] = pd.to_datetime(e.timestamp, utc=True)
        for _, row in grouped[(key, arm)].iterrows():
            if row.status == 'NO_OVERLAP':
                continue
            metrics = account_period_metrics(t, e, row.actual_start, row.actual_end, account.end_exclusive)
            rows.append({**row.to_dict(), 'readiness_status': account.readiness_status, **metrics})
        if i % 500 == 0:
            print(f'Period analysis {i}/{len(summary)} accounts', flush=True)
    periods = pd.DataFrame(rows)
    keys = ['run_key', 'block', 'status', 'actual_start', 'actual_end']
    base = periods.loc[periods.case_id.eq('U_READY'), keys + ['return_pct', 'max_drawdown_pct', 'participating_trades']]
    base = base.rename(columns={c: 'baseline_' + c for c in ['return_pct', 'max_drawdown_pct', 'participating_trades']})
    assert not base.duplicated(keys).any()
    periods = periods.merge(base, on=keys, how='left', validate='many_to_one', indicator=True)
    assert periods['_merge'].eq('both').all()
    periods = periods.drop(columns='_merge')
    periods['return_change_pp'] = periods.return_pct - periods.baseline_return_pct
    periods['drawdown_reduction_pp'] = periods.baseline_max_drawdown_pct.abs() - periods.max_drawdown_pct.abs()
    periods['return_improved'] = periods.return_change_pp.gt(1e-10)
    periods['return_worsened'] = periods.return_change_pp.lt(-1e-10)
    periods['outcome'] = np.select([periods.return_pct.isna(), periods.zero_trades, periods.return_pct.gt(1e-10), periods.return_pct.lt(-1e-10)],
        ['UNAVAILABLE_NONPOSITIVE_START_EQUITY', 'NO_TRADES', 'PROFIT', 'LOSS'], default='FLAT_WITH_TRADES')
    return periods


def summarize_periods(periods):
    rows = []
    for (block, status, arm), g in periods.groupby(['block', 'status', 'case_id']):
        complete = status == 'COMPLETE'
        if complete:
            assert not g.slug.duplicated().any(), 'Two independent segments cannot both cover one complete period'
        row = {'block': block, 'status': status, 'case_id': arm, 'segments': len(g), 'coins': g.slug.nunique(),
            'zero_trade_segments': int(g.zero_trades.sum()), 'profitable_segments': int(g.outcome.eq('PROFIT').sum()),
            'losing_segments': int(g.outcome.eq('LOSS').sum()), 'flat_trading_segments': int(g.outcome.eq('FLAT_WITH_TRADES').sum()),
            'unavailable_return_segments': int(g.return_pct.isna().sum()),
            'profitable_fraction_all_segments': fraction(g.outcome.eq('PROFIT').sum(), len(g)) if complete else None,
            'profitable_fraction_traded_segments': fraction(g.outcome.eq('PROFIT').sum(), (~g.zero_trades).sum()) if complete else None,
            'median_return_pct': number(g.return_pct.median()) if complete else None,
            'median_drawdown_pct': number(g.max_drawdown_pct.abs().median()) if complete else None,
            'median_closed_trade_payoff': number(g.closed_trade_payoff_ratio.median()) if complete else None,
            'median_closed_trade_pf': number(g.closed_trade_profit_factor.median()) if complete else None,
            'median_closed_trade_win_rate_pct': number(g.closed_trade_win_rate_pct.median()) if complete else None,
            'total_entered_trades': int(g.entered_trades.sum()), 'total_closed_trades': int(g.closed_trades.sum()),
            'qualified_flat_attempts': int(g.qualified_flat_attempts.sum()), 'admission_passed': int(g.admission_passed.sum()),
            'learning_rejected': int(g.learning_rejected.sum()), 'history90_rejected': int(g.history90_rejected.sum()),
            'actual_entry_fills': int(g.entry_fills.sum()),
            'admission_passed_ratio': fraction(g.admission_passed.sum(), g.qualified_flat_attempts.sum()),
            'return_improved_segments': int(g.return_improved.sum()), 'return_worsened_segments': int(g.return_worsened.sum()),
            'median_return_change_pp': number(g.return_change_pp.median()) if complete else None,
            'median_drawdown_reduction_pp': number(g.drawdown_reduction_pp.median()) if complete else None,
            'changed_lengths_pooled_into_profit_rate': False,
            **{f'route_{a}_entries': int(g[f'route_{a}_entries'].sum()) for a in ROUTE_NAMES}}
        rows.append(row)
    return pd.DataFrame(rows)


def universe_scope(scope):
    parts = []
    source_pins = {}
    for directory in ['history_inputs', 'history_inputs_unknown_verified']:
        path = OLD / directory / 'scope.csv'
        expected = json.loads((OLD / directory / 'checksums.json').read_text())
        assert sha(path) == expected['scope.csv']
        source_pins[str(path.relative_to(ROOT))] = sha(path)
        q = pd.read_csv(path)
        q['input_group'] = directory
        parts.append(q[['slug', 'symbol', 'input_group', 'segments_with_trading_window', 'status']])
    universe = pd.concat(parts, ignore_index=True).rename(columns={'status': 'original_input_status'})
    assert len(universe) == 680 and not universe.slug.duplicated().any()
    grouped = {slug: g for slug, g in scope.groupby('slug')}
    records_out = []
    for row in universe.to_dict('records'):
        g = grouped.get(row['slug'], pd.DataFrame())
        statuses = set(g.status) if len(g) else set()
        chosen = ('ELIGIBLE' if 'ELIGIBLE' in statuses else
                  'INSUFFICIENT_HISTORY90' if 'INSUFFICIENT_HISTORY90' in statuses else
                  'NO_EVALUATION_OVERLAP' if len(g) else 'NO_ORIGINAL_TRADING_WINDOW')
        if not len(g):
            assert row['segments_with_trading_window'] == 0
        records_out.append({**row, 'adaptation_status': chosen, 'status_cn': SCOPE_NAMES[chosen],
            'source_segments': len(g), 'eligible_segments': int(g.status.eq('ELIGIBLE').sum()) if len(g) else 0,
            'insufficient90_segments': int(g.status.eq('INSUFFICIENT_HISTORY90').sum()) if len(g) else 0,
            'no_evaluation_segments': int(g.status.eq('NO_EVALUATION_OVERLAP').sum()) if len(g) else 0})
    return pd.DataFrame(records_out), source_pins


def condition_cn(condition):
    key = condition['feature']
    missing = key.endswith('__missing')
    stem = key.removesuffix('__missing')
    label = FEATURE_NAMES.get(stem, stem)
    if missing:
        return label + (' 有记录' if condition['operator'] == '<=' else ' 缺失')
    return f"{label} {condition['operator']} {condition['threshold']:.8g}"


def enrich_rules(rules, decisions):
    out = []
    for r in rules:
        g = decisions.loc[decisions.rule_id.eq(r['rule_id'])]
        z = {**r, 'conditions_cn': ' 且 '.join(condition_cn(c) for c in r.get('conditions', [])) or '全部符合条件的案例',
             'arm_cn': ARM_NAMES[r['arm']], 'advice_cn': '跳过' if not r['allow'] else ROUTE_NAMES[r['action']]}
        z.update({'validation_' + k: v for k, v in natural_case_metrics(g).items()})
        z['validation_assessment'] = ('验证案例不足' if z['validation_natural_ready_cases'] < 120 or z['validation_coins'] < 20
            else '验证中改善' if z['validation_equal_coin_mean_improvement_pp'] > 1e-10
            else '验证中变差' if z['validation_equal_coin_mean_improvement_pp'] < -1e-10 else '保持基准')
        out.append(z)
    return out


CSS = r'''
:root{color-scheme:light;--ink:#182027;--muted:#59636e;--line:#d9dee1;--green:#17654c;--red:#a33230}
*{box-sizing:border-box}body{margin:0;background:#f8f8f5;color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1500px;margin:auto;padding:30px 28px 70px}h1{font-size:27px;line-height:1.25;margin:10px 0 18px}h2{font-size:19px;margin:28px 0 12px}
p{max-width:1100px}.sub,.note{color:var(--muted)}.notice{border-left:3px solid #bd8d3c;padding:10px 15px;background:#f1eee6;margin:18px 0}
nav{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:20px}a{color:#16567c;text-decoration:none}a:hover{text-decoration:underline}
.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:end;margin:15px 0}label{display:grid;gap:4px;color:var(--muted);font-size:12px}select,input{font:14px inherit;padding:7px 10px;border:1px solid #bcc6cd;border-radius:3px;background:white;color:var(--ink)}
input{min-width:200px}.scroll{overflow:auto;max-height:620px;border:1px solid var(--line);background:#fff}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{border-bottom:1px solid #e3e6e8;padding:9px 11px;text-align:right;white-space:nowrap}th{position:sticky;top:0;background:#edf0ee;font-weight:600;z-index:1}th:first-child,td:first-child{text-align:left}tr:hover td{background:#f1f5f3}.wrap{white-space:normal;text-align:left;min-width:280px;max-width:540px}button{border:1px solid #aab8c1;background:white;border-radius:3px;padding:5px 9px;color:#16567c;cursor:pointer}
.pos{color:var(--green)}.neg{color:var(--red)}.pill{padding:3px 7px;background:#e9ede9;font-size:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:18px;margin:22px 0}.stat{border-top:2px solid #6e8075;padding-top:9px}.stat b{display:block;font-size:25px}.detail{margin:15px 0;background:white;border:1px solid var(--line);padding:18px}.detail:empty{display:none}.small{font-size:12px}.count{color:var(--muted);margin:7px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}.hidden{display:none}@media(max-width:680px){main{padding:20px 12px}h1{font-size:23px}.scroll{max-height:520px}th,td{padding:8px}}
'''


APP_JS = r'''
"use strict";
const DATA=JSON.parse(document.getElementById('report-data').textContent);
const ARM=DATA.armNames, PHASE=DATA.phaseNames, ROUTE=DATA.routeNames;
const $=id=>document.getElementById(id);
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function num(v,d=2){return v===null||v===undefined||!Number.isFinite(Number(v))?'—':Number(v).toFixed(d);}
function signed(v){return `<span class="${Number(v)>0?'pos':Number(v)<0?'neg':''}">${num(v)}</span>`;}
function ratio(v){return v===null||v===undefined?'—':num(v*100,1)+'%';}
function table(headers,rows){return '<table><thead><tr>'+headers.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')+'</tbody></table>';}
function matches(r){return (!$('block')||r.block===$('block').value)&&(!$('coverage')||r.status===$('coverage').value)&&(!$('arm')||!$('arm').value||r.case_id===$('arm').value)&&(!$('coinSearch')||r.slug.toUpperCase().includes($('coinSearch').value.trim().toUpperCase()));}
function accountRows(rows){return rows.map(r=>[
  `<a href="${DATA.kind==='index'?'coins/'+encodeURIComponent(r.slug)+'.html':'#'}">${esc(r.slug)}</a>`,esc(ARM[r.case_id]),esc(r.run_key.split('__').slice(1).join('__')),
  esc(String(r.actual_start).slice(0,10)+' → '+String(r.actual_end).slice(0,10)),num(r.days,0),signed(r.return_pct),num(Math.abs(r.max_drawdown_pct)),signed(r.return_change_pp),signed(r.drawdown_reduction_pp),
  num(r.entered_trades,0)+' / '+num(r.closed_trades,0),num(r.inherited_trades,0),num(r.closed_trade_win_rate_pct),num(r.closed_trade_payoff_ratio),num(r.closed_trade_profit_factor),
  ratio(r.admission_passed_ratio),num(r.learning_rejected,0),num(r.history90_rejected,0),num(r.route_v3_entries,0)+' / '+num(r.route_defense_entries,0)+' / '+num(r.route_extension_entries,0),r.outcome==='UNAVAILABLE_NONPOSITIVE_START_EQUITY'?'期初权益非正，收益比不可用':r.zero_trades?'无交易':r.outcome==='PROFIT'?'盈利':r.outcome==='LOSS'?'亏损':'交易后持平']);}
const ACCOUNT_HEAD=['币种','方案','独立段','实际时间（结束日不含）','天数','净值收益%','最大回撤%','比对照收益变化pp','回撤减少pp','入场/退出笔数','期初继承笔数','退出整笔胜率%','退出整笔盈亏比','退出整笔利润因子','准入通过比例','学习拒绝','不足90日拒绝','入场V3/S1/S3','结果'];
function renderAccounts(){let rows=DATA.periods.filter(matches);if($('outcome')&&$('outcome').value)rows=rows.filter(r=>r.outcome===$('outcome').value);$('accounts').innerHTML=table(ACCOUNT_HEAD,accountRows(rows));$('accountCount').textContent=rows.length+' 个独立段账户；不同段不拼接成账户。';if($('periodSummary')){const s=DATA.periodSummary.filter(r=>r.block===$('block').value&&r.status===$('coverage').value);$('periodSummary').innerHTML=table(['方案','代码数/段数','盈利/亏损/无交易','盈利占全部段','收益中位数%','回撤中位数%','比对照改善/变差','准入通过','学习拒绝','V3/S1/S3入场'],s.map(r=>[esc(ARM[r.case_id]),r.coins+' / '+r.segments,r.profitable_segments+' / '+r.losing_segments+' / '+r.zero_trade_segments,ratio(r.profitable_fraction_all_segments),num(r.median_return_pct),num(r.median_drawdown_pct),r.return_improved_segments+' / '+r.return_worsened_segments,ratio(r.admission_passed_ratio),num(r.learning_rejected,0),r.route_v3_entries+' / '+r.route_defense_entries+' / '+r.route_extension_entries]));$('coverageNote').textContent=$('coverage').value==='COMPLETE'?'本表每币都完整覆盖所选时间，盈利比例包含无交易币作为分母；无交易不算盈利。':'部分覆盖的时间不同，只显示数量与逐段结果，不汇总收益中位数或适配盈利比例。';}}
function renderUniverse(){const needle=$('scopeSearch').value.trim().toUpperCase();const rows=DATA.universe.filter(r=>r.slug.toUpperCase().includes(needle)&&(!$('scopeStatus').value||r.adaptation_status===$('scopeStatus').value));$('universe').innerHTML=table(['币种','本轮范围','原可交易段','本轮有条件段','不足90日段','无本期重叠段'],rows.map(r=>[`<a href="coins/${encodeURIComponent(r.slug)}.html">${esc(r.slug)}</a>`,esc(r.status_cn),r.segments_with_trading_window,r.eligible_segments,r.insufficient90_segments,r.no_evaluation_segments]));$('scopeCount').textContent=rows.length+' / '+DATA.universe.length+' 个代码。范围由输入和日期确定，不按回测最终收益删币。';}
function renderFixed(){if(!$('fixed'))return;const rows=DATA.fixedSummary.filter(r=>r.phase===$('block').value);$('fixed').innerHTML=table(['方案','自然退出且90日案例','保留比例','原赢家/被拒/转亏','原亏单/改善/被拒','等币原V3/选中均值%','每币等权平均改善pp','原赢家正盈利保留','每币前5赢家正盈利保留'],rows.map(r=>[esc(ARM[r.arm]),r.natural_ready_cases,ratio(r.retained_ratio),r.original_winners+' / '+r.winners_rejected+' / '+r.winners_turned_loss,r.original_losers+' / '+r.losers_improved+' / '+r.losers_avoided_by_rejection,num(r.equal_coin_mean_original_return_pct)+' / '+num(r.equal_coin_mean_selected_return_pct),signed(r.equal_coin_mean_improvement_pp),ratio(r.positive_winner_retention),ratio(r.top5_positive_profit_retention)]));}
function ruleRows(){const arm=$('ruleArm').value,year=$('ruleYear').value,choice=$('ruleChoice').value,needle=$('ruleSearch').value.toLowerCase();return DATA.rules.filter(r=>(!arm||r.arm===arm)&&(!year||String(r.cutoff).startsWith(year))&&(!choice||(choice==='reject'?!r.allow:choice==='route'?r.allow&&r.action!=='v3':r.allow&&r.action==='v3'))&&(!needle||(r.rule_id+' '+r.conditions_cn).toLowerCase().includes(needle)));}
function renderRules(){const rows=ruleRows();$('rules').innerHTML=table(['规则','方案/币组','中文条件（且）','建议','训练案例/币数','训练V3/S1/S3均值%','验证案例/币数','验证等币原V3/选中均值%','验证等币改善pp','原赢家被拒/转亏','前5赢家盈利保留','验证表现'],rows.map(r=>[`<button data-rule="${esc(r.rule_id)}">${esc(r.rule_id)}</button>`,esc(ARM[r.arm])+' / '+r.fold,`<div class="wrap">${esc(r.conditions_cn)}</div>`,esc(r.advice_cn),r.rows+' / '+r.coins,r.means?['v3','defense','extension'].map(a=>num(r.means[a]*100)).join(' / '):'—',r.validation_natural_ready_cases+' / '+r.validation_coins,num(r.validation_equal_coin_mean_original_return_pct)+' / '+num(r.validation_equal_coin_mean_selected_return_pct),signed(r.validation_equal_coin_mean_improvement_pp),r.validation_winners_rejected+' / '+r.validation_winners_turned_loss,ratio(r.validation_top5_positive_profit_retention),esc(r.validation_assessment)]));$('ruleCount').textContent=rows.length+' 条叶子规则；三币组采用各自另外两组训练，代码不能进入自己的训练。';}
function showRule(id){const r=DATA.rules.find(x=>x.rule_id===id);if(!r)return;$('ruleDetail').innerHTML='<b>'+esc(r.rule_id)+'</b><p>'+esc(r.conditions_cn)+'</p><p>建议：'+esc(r.advice_cn)+'。训练支持：'+r.rows+' 笔、'+r.coins+' 币；验证：'+r.validation_natural_ready_cases+' 笔、'+r.validation_coins+' 币。</p><p>例子：'+(DATA.ruleExamples[id]||[]).map(x=>`<a href="coins/${encodeURIComponent(x.slug)}.html#${encodeURIComponent(x.case_id)}">${esc(x.slug+' '+x.case_id.split('::').pop())}</a>`).join(' · ')+'</p><p class="note">原始阈值、训练各币结果与全部验证案例都在分析文件中；小样本改善不等于稳定规律。</p>';}
function renderCases(){const arm=$('caseArm').value,kind=$('caseOutcome').value,needle=$('caseSearch').value.toLowerCase();const rows=DATA.cases.filter(r=>(!arm||r.arm===arm)&&(!needle||(r.case_id+' '+r.rule_id).toLowerCase().includes(needle))&&(!kind||(kind==='rejected'?!r.allow:kind==='winner_lost'?r.u_v3>0&&r.selected_u<0:kind==='loss_improved'?r.u_v3<0&&r.delta_u>0:r.terminal_any)));$('cases').innerHTML=table(['原入场案例','时间/方向','方案','原V3收益%','相同入场S1/S3%','决定','实际选择结果%','变化pp','规则','标签状态'],rows.map(r=>[`<button data-case="${esc(r.case_id)}">${esc(r.case_id)}</button>`,esc(r.entry_time.slice(0,10))+' '+(r.side===1?'多':'空'),esc(ARM[r.arm]),signed(r.u_v3*100),num(r.u_defense*100)+' / '+num(r.u_extension*100),r.allow?esc(ROUTE[r.action]):'跳过',signed(r.selected_u*100),signed(r.delta_u*100),esc(r.rule_id),r.terminal_any?'含终点结算':!r.ready90?'不足90日':'三动作自然退出']));$('caseCount').textContent=rows.length+' 条方案决定；它们沿用原V3相同入场，不是可拼接的真实账户。';}
function showCase(id){const x=DATA.details[id];if(!x)return;const names=DATA.featureNames;let rows=[];for(const [k,v] of Object.entries(x.features))rows.push([esc(names[k]||k),v===null?'缺失（由该训练模型填补）':num(v,8)]);$('caseDetail').innerHTML='<b>'+esc(id)+'</b><p>原入场：'+esc(x.entry_time)+'；'+(x.side===1?'多单':'空单')+'。三种管理的退出时刻与结果：</p>'+table(['管理','退出时间','退出原因','权益收益%'],['v3','defense','extension'].map(a=>[esc(ROUTE[a]),esc(x['exit_'+a]),esc(x['reason_'+a]),signed(x['u_'+a]*100)]))+'<p><a href="'+esc(x.history_link)+'">查看这段原历史交易路径</a>（旧路径用于价格上下文，本轮准入判断见本页。）</p><h3>信号收盘时已经知道的特征</h3>'+table(['特征','值'],rows);}
function refresh(){if(DATA.kind==='index'||DATA.kind==='coin'){renderAccounts();renderFixed();}if(DATA.kind==='index')renderUniverse();if(DATA.kind==='rules')renderRules();if(DATA.kind==='coin')renderCases();}
document.addEventListener('input',refresh);document.addEventListener('change',refresh);document.addEventListener('click',event=>{const target=event.target;if(target.dataset&&target.dataset.rule)showRule(target.dataset.rule);if(target.dataset&&target.dataset.case)showCase(target.dataset.case);});
refresh();if(DATA.kind==='coin'&&typeof location!=='undefined'&&location.hash)showCase(decodeURIComponent(location.hash.slice(1)));
'''


def selects(options, selected):
    return ''.join(f'<option value="{html.escape(str(k))}"' + (' selected' if k == selected else '') + '>' + html.escape(str(v)) + '</option>' for k, v in options)


def account_filters(blocks):
    items = [(b, PHASE_NAMES.get(b, b.replace('year_', '') if b.startswith('year_') else b)) for b in blocks]
    return '<div class="filters"><label>时间<select id="block">' + selects(items, 'phase_2025_2026') + '</select></label>' \
        '<label>覆盖<select id="coverage"><option value="COMPLETE">完整覆盖</option><option value="PARTIAL">部分覆盖</option></select></label>' \
        '<label>方案<select id="arm">' + selects([('', '全部')] + [(x, ARM_NAMES[x]) for x in ARMS], '') + '</select></label>' \
        '<label>币种<input id="coinSearch" placeholder="输入币种"></label>' \
        '<label>结果<select id="outcome">' + selects([('', '全部'), ('PROFIT', '盈利'), ('LOSS', '亏损'), ('NO_TRADES', '无交易'), ('FLAT_WITH_TRADES', '交易后持平')], '') + '</select></label></div>'


def page(path, title, body, data, prefix=''):
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('</', '<\\/')
    text = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' \
        f'<title>{html.escape(title)}</title><style>{CSS}</style><main><nav><a href="{prefix}index.html">全市场与分期</a><a href="{prefix}rules.html">学到的条件与反例</a></nav><h1>{html.escape(title)}</h1>' + body + \
        '</main><script id="report-data" type="application/json">' + payload + f'</script><script src="{prefix}app.js"></script></html>'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


NOTICE = '<p class="notice">单边手续费0.1%、滑点0.04%，约1倍仓位；未计真实资金费。所有历史此前已经研究过，本轮按币组与训练截止日期分开检验。2024-10-28官方数据来源冲突仍未解决，不能据此宣称完整牛熊历史已可靠验证。</p>'
ACCOUNT_NOTE = '<p class="note small">收益和回撤来自所选时期内的实际账户净值。盈亏比、利润因子、胜率统计本期退出交易的整笔结果，可能含上期带入的盈利或亏损，不能当成本期收益的直接拆分。最大回撤显示正的跌幅；回撤减少为正表示改善。没有交易的币保留且不算盈利。</p>'
FIXED_NOTE = '<p class="note">以下只比较原V3相同入场的三种退出结果；全部三动作自然结束且已有90日数据才用于数值比较。被拒绝等于这笔不做，结果为0。它们可能互相重叠，不能相加当作账户收益。“前5”按每币在该入场时期的原赢家收益率选出，正盈利保留不计负数。</p>'


def build_html(out, analysis, universe, periods, period_summary, fixed_summary, rules, decisions):
    assert not out.exists()
    out.mkdir(parents=True)
    (out / 'app.js').write_text(APP_JS)
    blocks = PHASES + sorted(set(periods.block) - set(PHASES))
    common = {'armNames': ARM_NAMES, 'phaseNames': PHASE_NAMES, 'routeNames': ROUTE_NAMES}
    shown = ['slug', 'case_id', 'run_key', 'block', 'status', 'actual_start', 'actual_end', 'days',
        'return_pct', 'max_drawdown_pct', 'return_change_pp', 'drawdown_reduction_pp',
        'entered_trades', 'closed_trades', 'inherited_trades', 'closed_trade_win_rate_pct',
        'closed_trade_payoff_ratio', 'closed_trade_profit_factor', 'admission_passed_ratio',
        'learning_rejected', 'history90_rejected', 'route_v3_entries', 'route_defense_entries',
        'route_extension_entries', 'zero_trades', 'outcome']
    index_data = {**common, 'kind': 'index', 'universe': records(universe),
                  'periods': records(periods.loc[periods.block.isin(PHASES), shown]),
                  'periodSummary': records(period_summary.loc[period_summary.block.isin(PHASES)]),
                  'fixedSummary': records(fixed_summary)}
    counts = universe.adaptation_status.value_counts()
    tiles = '<div class="grid">' + ''.join(f'<div class="stat"><span>{label}</span><b>{value}</b></div>' for label, value in [
        ('全部代码', len(universe)), ('有至少一个90日可参与段', int(counts.get('ELIGIBLE', 0))),
        ('本期不足90日', int(counts.get('INSUFFICIENT_HISTORY90', 0))),
        ('无本期段或原交易窗口', int(counts.get('NO_EVALUATION_OVERLAP', 0) + counts.get('NO_ORIGINAL_TRADING_WINDOW', 0)))]) + '</div>'
    links = '<p><a href="../analysis/period_accounts.csv">全部分期账户</a> · <a href="../analysis/period_summary.csv">完整覆盖汇总</a> · <a href="../analysis/universe_scope.csv">680代码范围</a> · <a href="../analysis/rules_with_validation.json">全部规则与验证</a></p>'
    body = '<p>这轮学习哪些标的状态、哪些穿越状态值得参与，并为已接受的交易选择退出方式。每个目标币均由另外两组币的历史训练规则；模型在2023和2025年各更新一次，已有仓位不换规则。首页按两个生效阶段比较，单币页面还能切换固定年份及跨年区间。</p>' + NOTICE + tiles + links + account_filters(PHASES) + \
        '<h2>同一时间的全市场比较</h2><p id="coverageNote" class="note"></p><div id="periodSummary" class="scroll"></div>' + \
        '<h2>每币每段结果</h2>' + ACCOUNT_NOTE + '<p id="accountCount" class="count"></p><div id="accounts" class="scroll"></div>' + \
        '<h2>少亏了多少，又错过了多少赢家</h2>' + FIXED_NOTE + '<div id="fixed" class="scroll"></div>' + \
        '<h2>全部680代码，包含无交易与不能参与者</h2><div class="filters"><label>币种<input id="scopeSearch"></label><label>范围<select id="scopeStatus">' + selects([('', '全部')] + list(SCOPE_NAMES.items()), '') + '</select></label></div><p id="scopeCount" class="count"></p><div id="universe" class="scroll"></div>'
    page(out / 'index.html', '从成功与失败案例学习全市场适配条件', body, index_data)

    rule_examples = {}
    for rule_id, g in decisions.groupby('rule_id'):
        # Deterministic first examples within each factual outcome type; no
        # choice of the visually most persuasive chart after the results.
        kinds = [g.loc[g.u_v3.gt(0) & ~g.allow], g.loc[g.u_v3.lt(0) & g.delta_u.gt(0)], g.loc[g.u_v3.gt(0) & g.selected_u.lt(0)], g]
        examples = pd.concat([x.sort_values('case_id').head(2) for x in kinds]).drop_duplicates('case_id').head(8)
        rule_examples[str(rule_id)] = records(examples[['slug', 'case_id']])
    rule_data = {**common, 'kind': 'rules', 'rules': rules, 'ruleExamples': rule_examples}
    body = '<p>先看条件、训练中支持它的币数，再看这些条件在训练外的币和未来时期怎样。训练中的正收益不等于规则已经有效。</p>' + NOTICE + \
        '<div class="filters"><label>生效模型<select id="ruleYear">' + selects([('', '全部'), ('2023', '2023模型，用于2023–2024'), ('2025', '2025模型，用于2025以后')], '') + '</select></label><label>方案<select id="ruleArm">' + selects([('', '全部')] + [(x, ARM_NAMES[x]) for x in ARMS if x != 'U_READY'], '') + '</select></label><label>建议<select id="ruleChoice">' + selects([('', '全部'), ('reject', '跳过'), ('route', '换退出方式'), ('v3', '沿用V3')], '') + '</select></label><label>查条件<input id="ruleSearch"></label></div>' + \
        '<p class="note">条件之间全部是“且”。缺失状态独立列出。数值缺失用该训练集的中位数填补，因此数值条件须连同缺失标记理解。标准误只用于训练中的保守建议，不代表独立显著性检验。验证不足120笔或20币明确显示案例不足。</p><p id="ruleCount" class="count"></p><div id="rules" class="scroll"></div><div id="ruleDetail" class="detail"></div>' + \
        '<p><a href="../analysis/rules_with_validation.json">下载完整规则、训练支持与验证结果</a> · <a href="../learning/models.json">原始阈值与每币训练结果</a> · <a href="../analysis/fixed_case_summary.csv">原入场方案对照</a></p>'
    page(out / 'rules.html', '学到的条件：哪些成立，哪些留下反例', body, rule_data)

    all_g = {slug: g for slug, g in decisions.groupby('slug')}
    p_g = {slug: g for slug, g in periods.groupby('slug')}
    case_fields = ['case_id', 'run_key', 'entry_time', 'side', 'u_v3', 'u_defense', 'u_extension',
                   'selected_u', 'delta_u', 'arm', 'allow', 'action', 'rule_id', 'terminal_any', 'ready90']
    for item in universe.to_dict('records'):
        slug = item['slug']
        g = all_g.get(slug, decisions.iloc[:0])
        p = p_g.get(slug, periods.iloc[:0])
        details = {}
        for case in g.drop_duplicates('case_id').to_dict('records'):
            label = 'verified28' if 'history_verified_results' in case['source_result'] else 'original652'
            old_page = OLD / 'html_current/history' / label / (case['run_key'] + '.html')
            assert old_page.exists(), old_page
            obj = {k: case[k] for k in ['entry_time', 'side'] + [s + '_' + a for a in ROUTE_NAMES for s in ['exit', 'reason', 'u']]}
            obj['features'] = {k: case[k] for k in FEATURE_NAMES}
            obj['history_link'] = os.path.relpath(old_page, out / 'coins')
            details[case['case_id']] = json.loads(pd.Series(obj).to_json(date_format='iso', double_precision=15))
        coin_fixed = []
        for (phase, arm), sub in g.groupby(['phase', 'arm']):
            coin_fixed.append({'phase': phase, 'arm': arm, **natural_case_metrics(sub)})
        data = {**common, 'kind': 'coin', 'periods': records(p[shown]), 'fixedSummary': coin_fixed,
                'cases': records(g[case_fields]), 'details': details, 'featureNames': FEATURE_NAMES}
        body = '<p>输入范围：' + html.escape(item['status_cn']) + '；原可交易段 ' + str(item['segments_with_trading_window']) + '。该代码始终保留在全市场范围中。</p>' + NOTICE + account_filters(blocks) + \
            '<h2>实际连续账户的分期结果</h2>' + ACCOUNT_NOTE + '<p id="accountCount" class="count"></p><div id="accounts" class="scroll"></div>' + \
            '<h2>同入场的退出与过滤效果</h2>' + FIXED_NOTE + '<div id="fixed" class="scroll"></div>' + \
            '<h2>打开成功或失败案例</h2><div class="filters"><label>方案<select id="caseArm">' + selects([('', '全部')] + [(x, ARM_NAMES[x]) for x in ARMS if x != 'U_READY'], '') + '</select></label><label>案例<select id="caseOutcome">' + selects([('', '全部'), ('rejected', '被拒绝'), ('winner_lost', '原赢家转亏'), ('loss_improved', '原亏单改善'), ('terminal', '包含终点结算')], '') + '</select></label><label>规则或案例号<input id="caseSearch"></label></div><p id="caseCount" class="count"></p><div id="cases" class="scroll"></div><div id="caseDetail" class="detail"></div>'
        page(out / 'coins' / (slug + '.html'), slug + '：适配条件与全部案例', body, data, '../')


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if 'href' in d:
            self.links.append(d['href'])
        if 'src' in d:
            self.links.append(d['src'])
        if 'id' in d:
            self.ids.append(d['id'])


QA_JS = r'''
const fs=require('fs'),vm=require('vm'),path=require('path');
const root=process.argv[2], app=fs.readFileSync(path.join(root,'app.js'),'utf8');
function check(file){const text=fs.readFileSync(file,'utf8');const found=text.match(/<script id="report-data" type="application\/json">([\s\S]*?)<\/script>/);if(!found)throw Error('no data');const data=JSON.parse(found[1]);const elements={};for(const m of text.matchAll(/id="([^"]+)"/g))elements[m[1]]={value:'',innerHTML:'',textContent:''};elements['report-data'].textContent=found[1];
 for(const m of text.matchAll(/<select id="([^"]+)">([\s\S]*?)<\/select>/g)){const opts=[...m[2].matchAll(/<option value="([^"]*)"([^>]*)>/g)];elements[m[1]].value=(opts.find(x=>x[2].includes('selected'))||opts[0])[1];}
 const listeners={};const ctx={document:{getElementById:id=>elements[id]||null,addEventListener:(event,f)=>listeners[event]=f},location:{hash:''},console};vm.createContext(ctx);vm.runInContext(app,ctx);const assert=(condition,label)=>{if(!condition)throw Error(file+': '+label);};let checks=1;
 if(data.kind==='index'||data.kind==='coin'){assert(elements.accounts.innerHTML.includes('<table>'),'account table');elements.coinSearch.value='NO_SUCH_SYNTHETIC_CODE_999';listeners.input();assert(elements.accountCount.textContent.startsWith('0 '),'coin filter');elements.coinSearch.value='';for(const phase of ['phase_2023_2024','phase_2025_2026'])for(const status of ['COMPLETE','PARTIAL']){elements.block.value=phase;elements.coverage.value=status;listeners.change();assert(elements.accounts.innerHTML.includes('<table>'),'phase coverage render');checks++;}}
 if(data.kind==='index'){elements.scopeSearch.value='NO_SUCH_SYNTHETIC_CODE_999';listeners.input();assert(elements.scopeCount.textContent.startsWith('0 /'),'universe filter');elements.scopeSearch.value='';listeners.input();assert(elements.scopeCount.textContent.startsWith(data.universe.length+' /'),'all scope retained');checks+=2;}
 if(data.kind==='rules'){elements.ruleSearch.value='NO_SUCH_SYNTHETIC_RULE_999';listeners.input();assert(elements.ruleCount.textContent.startsWith('0 '),'rule filter');elements.ruleSearch.value='';listeners.input();if(data.rules.length){listeners.click({target:{dataset:{rule:data.rules[0].rule_id}}});assert(elements.ruleDetail.innerHTML.includes(data.rules[0].rule_id),'rule click');}checks+=2;}
 if(data.kind==='coin'&&data.cases.length){elements.caseSearch.value='NO_SUCH_CASE_999';listeners.input();assert(elements.caseCount.textContent.startsWith('0 '),'case filter');elements.caseSearch.value='';listeners.input();listeners.click({target:{dataset:{case:data.cases[0].case_id}}});assert(elements.caseDetail.innerHTML.includes('信号收盘时已经知道的特征'),'case detail');checks+=2;}
 return {file:path.relative(root,file),kind:data.kind,checks,cases:data.cases?data.cases.length:0};}
const files=[path.join(root,'index.html'),path.join(root,'rules.html'),...fs.readdirSync(path.join(root,'coins')).filter(x=>x.endsWith('.html')).map(x=>path.join(root,'coins',x))];const result=files.map(check);process.stdout.write(JSON.stringify({passed:true,method:'offline JavaScript VM with simulated DOM; no browser render claim',pages:result.length,checks:result.reduce((n,x)=>n+x.checks,0),case_pages:result.filter(x=>x.cases>0).length}));
'''


def qa_html(out):
    links, pages = 0, 0
    for file in out.rglob('*.html'):
        parser = LinkParser()
        parser.feed(file.read_text())
        assert len(parser.ids) == len(set(parser.ids)), file
        for link in parser.links:
            if not link or link.startswith('#'):
                continue
            assert not re.match(r'^[a-z]+:', link), 'Report must not depend on a remote resource'
            target = (file.parent / link.split('#')[0]).resolve()
            assert target.exists(), (file, link)
            links += 1
        pages += 1
    node = shutil.which('node')
    assert node, 'Node is required for offline JavaScript verification'
    subprocess.run([node, '--check', str(out / 'app.js')], check=True, capture_output=True, text=True)
    (out / 'qa_dom.cjs').write_text(QA_JS)
    result = subprocess.run([node, str(out / 'qa_dom.cjs'), str(out)], check=True, capture_output=True, text=True)
    report = json.loads(result.stdout)
    report.update(local_links_checked=links, unique_id_pages=pages, browser_rendered=False)
    write_json(out / 'qa_report.json', report)
    return report


def self_checks():
    end = pd.Timestamp('2025-01-01', tz='UTC')
    start = end - pd.Timedelta(days=1)
    trades = pd.DataFrame([
        {'entry_time': start - pd.Timedelta(days=1), 'exit_time': start,
         'exit_interval_end': start, 'exit_reason': 'stop_gap', 'net_pnl': -1., 'exit_route': 'v3'},
        {'entry_time': start - pd.Timedelta(days=1), 'exit_time': start - pd.Timedelta(hours=1),
         'exit_interval_end': start, 'exit_reason': 'stop_intrahour', 'net_pnl': -2., 'exit_route': 'v3'},
        {'entry_time': start + pd.Timedelta(hours=1), 'exit_time': end,
         'exit_interval_end': end, 'exit_reason': 'sample_end', 'net_pnl': 3., 'exit_route': 'defense'}])
    metrics = account_period_metrics(trades, pd.DataFrame(), start, end, end)
    assert metrics['participating_trades'] == 2 and metrics['inherited_trades'] == 1
    assert metrics['entered_trades'] == 1 and metrics['closed_trades'] == 2
    assert metrics['closed_trade_profit_factor'] == 3.
    # A calendar boundary inside the account does not include a closing fill
    # at its right endpoint; a real segment's forced final settlement does.
    other = account_period_metrics(trades, pd.DataFrame(), start, end, end + pd.Timedelta(days=1))
    assert other['closed_trades'] == 1 and other['terminal_trades'] == 0
    g = pd.DataFrame([{'case_id': f'{coin}-{i}', 'slug': coin, 'u_v3': value,
         'selected_u': value / 2, 'delta_u': -value / 2, 'allow': True,
         'ready90': True, 'terminal_any': False}
         for coin in ['A', 'B'] for i, value in enumerate([.10, .08, .06, .04, .02, .01])])
    result = natural_case_metrics(g)
    assert result['top5_original_winners'] == 10
    assert result['top5_positive_profit_retention'] == .5
    assert result['positive_winner_retention'] == .5
    g.loc[0, 'terminal_any'] = True
    assert natural_case_metrics(g)['natural_ready_cases'] == 11
    return {'passed': True, 'checks': ['left_boundary_gap_participates', 'prior_intrahour_excluded',
        'inherited_vs_new_positions', 'right_calendar_boundary_excluded', 'forced_terminal_included',
        'top5_per_coin', 'winner_positive_retention', 'terminal_label_excluded'],
        'comparison_is_presentation_arithmetic_not_new_simulation': True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', type=Path, default=R / 'cases')
    ap.add_argument('--learning', type=Path, default=R / 'learning')
    ap.add_argument('--results', type=Path, default=R / 'results')
    ap.add_argument('--analysis', type=Path, default=R / 'analysis')
    ap.add_argument('--html', type=Path, default=R / 'html')
    args = ap.parse_args()
    checks = self_checks()
    # Finished producer evidence is mandatory. Never hash a growing result set.
    cases, learning, results = Source(args.cases), Source(args.learning), Source(args.results)
    assert not args.analysis.exists() and not args.html.exists()
    summary, blocks, scope = [results.csv(name + '.csv') for name in ['summary', 'blocks', 'scope']]
    assert set(summary.case_id) == set(ARMS)
    assert not summary.duplicated(['run_key', 'case_id']).any()
    assert summary.groupby('run_key').case_id.nunique().eq(5).all()
    decisions = learning.parquet('case_decisions.parquet')
    assert not decisions.duplicated(['case_id', 'arm']).any()
    decisions['phase'] = np.where(pd.to_datetime(decisions.decision_time, utc=True).lt(pd.Timestamp('2025-01-01', tz='UTC')),
                                 'phase_2023_2024', 'phase_2025_2026')
    rules = learning.json('rules.json')
    models = learning.json('models.json')
    assert all(m['cutoff'] < '2026' for m in models.values())
    periods = attach_periods(summary, blocks, results)
    period_summary = summarize_periods(periods)
    universe, scope_pins = universe_scope(scope)
    fixed_summary = pd.DataFrame([{'phase': phase, 'arm': arm, **natural_case_metrics(g)}
        for (phase, arm), g in decisions.groupby(['phase', 'arm'])])
    controls = []
    for phase, g in decisions.loc[decisions.arm.eq('C_ROUTE')].groupby('phase'):
        for action in ROUTE_NAMES:
            fixed = g.copy()
            fixed['allow'], fixed['selected_u'] = True, fixed['u_' + action]
            fixed['delta_u'] = fixed.selected_u - fixed.u_v3
            controls.append({'phase': phase, 'arm': 'FIXED_' + action.upper(), **natural_case_metrics(fixed)})
    controls = pd.DataFrame(controls)
    enriched = enrich_rules(rules, decisions)
    args.analysis.mkdir(parents=True)
    write_json(args.analysis / 'self_checks.json', checks)
    outputs = {'segment_accounts.csv': summary, 'segment_scope.csv': scope,
               'period_accounts.csv': periods, 'period_summary.csv': period_summary,
               'universe_scope.csv': universe, 'fixed_case_summary.csv': fixed_summary,
               'fixed_exit_controls.csv': controls}
    for name, frame in outputs.items():
        frame.to_csv(args.analysis / name, index=False)
    decisions.to_parquet(args.analysis / 'fixed_case_decisions.parquet', index=False)
    write_json(args.analysis / 'rules_with_validation.json', enriched)
    write_json(args.analysis / 'source_manifest.json', {'script_sha256': sha(Path(__file__)),
        'cases': cases.record(), 'learning': learning.record(), 'results': results.record(),
        'original_scope_sources': scope_pins, 'simulation_performed': False,
        'complete_coverage_required_for_pooled_profit_rates': True,
        'fixed_examples_are_not_combined_accounts': True})
    (args.analysis / 'source_script.py.txt').write_bytes(Path(__file__).read_bytes())
    write_json(args.analysis / 'summary.json', {'coins_in_universe': len(universe),
        'source_segments': len(scope), 'replayed_accounts': len(summary), 'period_accounts': len(periods),
        'fixed_case_decisions': len(decisions), 'rules': len(enriched),
        'coverage_counts': records(universe.groupby('adaptation_status').size().rename('coins').reset_index()),
        'costs': {'fee_per_side': .001, 'slippage_per_side': .0004}, 'funding_verified': False,
        'historical_source_conflict_resolved': False})
    build_html(args.html, args.analysis, universe, periods, period_summary,
               pd.concat([fixed_summary, controls], ignore_index=True), enriched, decisions)
    qa = qa_html(args.html)
    write_json(args.analysis / 'html_qa.json', qa)
    for directory in [args.analysis, args.html]:
        write_json(directory / 'completion.json', {'complete': True, 'utc': str(pd.Timestamp.now(tz='UTC'))})
        write_json(directory / 'artifact_checksums.json', {str(p.relative_to(directory)): sha(p) for p in directory.rglob('*')
            if p.is_file() and p.name != 'artifact_checksums.json'})
    print(json.dumps({'complete': True, 'coins': len(universe), 'accounts': len(summary), 'rules': len(enriched), 'html_qa': qa}), flush=True)


if __name__ == '__main__':
    main()
