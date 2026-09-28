"""冻结结果的只读核算审计；不生成信号或重新回测，不导入费用研究入口。"""
from pathlib import Path
import datetime as dt
import hashlib
import json
import sys

import numpy as np
import pandas as pd

LAB = Path('/Users/ZK/OpenCode/quant-strategy-lab')
sys.path.insert(0, str(LAB / 'src'))
from strategy_lab.data.funding_v2 import load_funding_v2  # noqa: E402

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY / 'artifacts/funding'
RUN = FAMILY / 'artifacts/research-20260909'
OUTPUT = FAMILY / 'artifacts/funding-independent-verification.json'
if OUTPUT.exists():
    raise FileExistsError(OUTPUT)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(2**20), b''):
            h.update(block)
    return h.hexdigest()


checks = {}
manifest = json.loads((ROOT / 'artifact-manifest.json').read_text())
assert manifest['input_pins_unchanged']
for name, digest in manifest['files'].items():
    assert sha(ROOT / name) == digest, name
checks['artifact_hashes'] = len(manifest['files'])
started = json.loads((ROOT / 'started.json').read_text())
for name, digest in started['input_pins'].items():
    assert sha(name) == digest, name
checks['current_input_pins'] = len(started['input_pins'])
source = pd.read_parquet(RUN / 'opportunities.parquet')
fee = pd.read_csv(ROOT / 'opportunities.csv')
events = pd.read_csv(ROOT / 'events.csv.gz')
paired = pd.read_csv(ROOT / 'paired.csv')
den = pd.read_csv(ROOT / 'denominators.csv')
for col in ['event_ts', 'proxy_bar_open_ts', 'proxy_close_known_ts']:
    # 原生结算事件含0ms与非0ms；保留精度，不把时间列统一取整。
    events[col] = pd.to_datetime(events[col], utc=True, format='mixed')
key = ['origin_id', 'cost_id', 'policy']
source = source.set_index(key)
fee = fee.set_index(key)
assert source.index.is_unique and fee.index.is_unique
for cost in ['base', 'slippage_stress']:
    original = pd.read_parquet(RUN / f'paired-{cost}.parquet').set_index('origin_id')
    saved = paired[paired.cost_id == cost].set_index('origin_id')
    assert set(saved.index) == set(original.index)
    saved = saved.reindex(original.index)
    assert np.allclose(saved[['price_A', 'price_B', 'price_C']], original[['A', 'B', 'C']], rtol=0, atol=1e-12)
    assert len(den[den.cost_id == cost]) == 1658
assert np.allclose(fee.price_return, source.loc[fee.index]['return'], rtol=0, atol=1e-12)
checks['primary_pair_origins_per_cost'] = 1561
checks['fee_opportunity_rows_price_reconciled'] = len(fee)
unknown = fee.funding_status.str.startswith('UNKNOWN')
assert fee.loc[unknown, ['funding_real_cash', 'funding_with_daily_close_proxy_cash']].isna().all().all()
structural = fee.funding_status.eq('NO_POSITION_NO_FUNDING_DUE')
assert not source.loc[fee[structural].index].entered.any()
assert (fee.loc[structural, ['funding_real_cash', 'funding_with_daily_close_proxy_cash']] == 0).all().all()
checks['unknown_rows_remain_nan'] = int(unknown.sum())
checks['structural_no_position_zero_rows'] = int(structural.sum())
fd = load_funding_v2(LAB / 'data/derived/datasets/binance_perp_funding_v3_inputs_v2',
                     expected_manifest_sha256=started['funding_manifest_sha256'])
native_index = fd.events.set_index('event_id')
assert native_index.index.is_unique
native = native_index.loc[events.event_id]
assert np.allclose(native.funding_rate.to_numpy(float), events.funding_rate.to_numpy(float), rtol=0, atol=1e-12)
assert (native.ts.to_numpy() == events.event_ts.to_numpy()).all()
assert np.array_equal(native.symbol.to_numpy(), events.symbol.to_numpy())
assert native.event_unambiguous.all()
assert native.mark_price.isna().all() and events.native_mark_price.isna().all()
assert events.price_method.eq('PREVIOUS_UTC_DAY_CLOSED_TRADE_PRICE_PROXY').all()
checks['event_rows_against_verified_native_snapshot'] = len(events)
checks['unique_native_events'] = int(events.event_id.nunique())
checks['native_actual_mark_event_rows'] = 0
fm = json.loads((FAMILY / 'artifacts/p0-inputs/frame-manifest.json').read_text())
frames = {symbol: pd.read_pickle(FAMILY / 'artifacts/p0-inputs' / fm[symbol]['path'], compression='gzip').set_index('ts')
          for symbol in events.symbol.unique()}
expected_cash = []
for row in events.itertuples(index=False):
    k = (row.origin_id, row.cost_id, row.policy)
    trade = source.loc[k]
    assert trade.entry_ts < row.event_ts <= trade.exit_ts
    assert abs(trade.qty - row.quantity_before_event) < 1e-12
    timestamp = row.event_ts.floor('D') - pd.Timedelta(days=1)
    price = frames[row.symbol].loc[timestamp]
    entry = frames[row.symbol].loc[trade.entry_ts]
    assert price.eligible and price.research_segment_id == entry.research_segment_id
    assert timestamp == row.proxy_bar_open_ts
    assert timestamp + pd.Timedelta(days=1) == row.proxy_close_known_ts <= row.event_ts
    assert abs(price.close - row.cashflow_price) < 1e-10
    expected_cash.append(-trade.qty * price.close * row.funding_rate)
expected_cash = np.array(expected_cash)
assert np.allclose(expected_cash, events.funding_cash, rtol=0, atol=1e-12)
checks['all_event_cash_max_abs_error'] = float(np.max(np.abs(expected_cash - events.funding_cash)))
checks['all_event_prior_close_segment_and_holding_windows_checked'] = len(events)
sums = events.groupby(key).funding_cash.sum()
known = fee[fee.events.gt(0)]
assert set(sums.index) == set(known.index)
assert np.allclose(sums.reindex(known.index), known.funding_with_daily_close_proxy_cash, rtol=0, atol=1e-12)
checks['nonempty_funding_opportunity_sums_checked'] = len(known)
segments_by_symbol = dict(tuple(fd.segments.groupby('symbol')))
events_by_symbol = dict(tuple(fd.events.groupby('symbol')))
expected_by_segment = dict(tuple(fd.expected.groupby('segment_id')))
attributed_by_position = dict(tuple(events.groupby(key)))
for k, row in fee.iterrows():
    trade = source.loc[k]
    if not trade.entered:
        continue
    sg = segments_by_symbol.get(trade.symbol, fd.segments.iloc[:0])
    hit = sg[(sg.start <= trade.entry_ts) & (sg.end >= trade.exit_ts)]
    if row.funding_status == 'UNKNOWN_CALENDAR_FULL_WINDOW_UNPROVEN':
        assert len(hit) != 1
    else:
        assert len(hit) == 1
        native_symbol = events_by_symbol[trade.symbol]
        actual = native_symbol[(native_symbol.ts > trade.entry_ts) & (native_symbol.ts <= trade.exit_ts)]
        expected_segment = expected_by_segment[hit.segment_id.iloc[0]]
        expected = expected_segment[(expected_segment.ts > trade.entry_ts) & (expected_segment.ts <= trade.exit_ts)]
        attributed = attributed_by_position[k]
        assert set(actual.event_id) == set(expected.event_id) == set(attributed.event_id)
checks['all_entered_windows_calendar_status_independently_checked'] = int(source.loc[fee.index].entered.sum())
base = paired[(paired.cost_id == 'base') & paired.all_three_proxy_cash_available].copy()
base.origin_ts = pd.to_datetime(base.origin_ts, utc=True, format='mixed')
by_year = {str(int(y)): int(n) for y, n in base.groupby(base.origin_ts.dt.year).size().items()}
by_symbol = {symbol: {'n': len(group), 'first_origin': group.origin_ts.min().isoformat(),
                       'last_origin': group.origin_ts.max().isoformat()} for symbol, group in base.groupby('symbol')}
partial = known.reset_index()
partial = partial[(partial.cost_id == 'base') & ~partial.origin_id.isin(set(base.origin_id))]
result = {
    'status': 'FUNDING_RETAINED_CASH_AND_COHORT_INDEPENDENTLY_RECONCILED',
    'checked_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'checks': checks,
    'common_proxy_base_origin_year_counts': by_year, 'common_proxy_base_symbols': by_symbol,
    'individual_verified_positions_outside_common_fee_cohort': partial[['origin_id', 'symbol', 'policy', 'events']].to_dict('records'),
    'primary_coverage_fraction': len(base) / 1561,
    'scope': '全部保留事件现金、原始数量、实际持仓窗、前一UTC日P0同段代理、完整结算事件集合、全部费用Unknown状态、原价格配对母集与当前来源/输出hash复核；不认证PIT身份、交易所成交或资金费再投资账户。',
    'artifact_manifest_sha256': sha(ROOT / 'artifact-manifest.json'),
    'funding_summary_sha256': sha(ROOT / 'summary.json'), 'independent_verifier_sha256': sha(__file__),
    'prior_attempt': 'Ad hoc审计首次遇混合毫秒CSV解析错误；采用format=mixed保留原生时间后复核，不涉及研究入口或结果修改。',
}
OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
