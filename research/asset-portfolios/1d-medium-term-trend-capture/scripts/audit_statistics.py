"""MTTC 统计独立复算：展开共同日历行，不导入生产推断、引擎或账户代码。"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[2]
NAMES = ['A', 'B', 'C', 'B_minus_A', 'C_minus_B']
ATOL = 1e-12
RTOL = 1e-10


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def numeric_equal(actual, expected, name):
    left, right = np.asarray(actual, float), np.asarray(expected, float)
    if left.shape != right.shape or not np.allclose(left, right, atol=ATOL, rtol=RTOL,
                                                  equal_nan=False):
        raise AssertionError(f'{name}: mismatch {actual!r} != {expected!r}')
    return float(np.max(np.abs(left - right), initial=0.))


def five_means(frame):
    if not len(frame):
        raise ValueError('No complete paired observations')
    values = frame[['A', 'B', 'C']].to_numpy(float)
    if not np.isfinite(values).all():
        raise ValueError('Nonfinite paired opportunity return')
    # 明确逐机会配对差值，避免从两个不同母集的均值相减。
    columns = [values[:, i] for i in range(3)]
    columns += [values[:, 1] - values[:, 0], values[:, 2] - values[:, 1]]
    return np.array([math.fsum(column) / len(frame) for column in columns])


def calendar_data(frame, config):
    start, end = pd.Timestamp(config['start']), pd.Timestamp(config['end'])
    day = pd.Timedelta(days=1)
    if start.tzinfo is None or end.tzinfo is None or start != start.normalize() or end != end.normalize():
        raise ValueError('Calendar boundary is not an aware daily open')
    n = int((end - start) / day)
    dates = pd.to_datetime(frame.origin_ts, utc=True)
    offsets = ((dates - start) / day).to_numpy(float)
    indices = offsets.astype(np.int64)
    if not np.array_equal(indices, offsets) or (indices < 0).any() or (indices >= n).any():
        raise ValueError('Origin not on the frozen daily calendar')
    daily = np.zeros((n, 4), dtype=float)
    values = frame[['A', 'B', 'C']].to_numpy(float)
    # 与生产的 groupby + prefix sum 分开：逐原始机会直接加到所属日期。
    np.add.at(daily[:, :3], indices, values)
    np.add.at(daily[:, 3], indices, 1.)
    if int(daily[:, 3].sum()) != len(frame):
        raise AssertionError('Lost origins while constructing common calendar')
    return daily


def reconstruct(frame, config, progress=True):
    daily = calendar_data(frame, config)
    points = five_means(frame)
    n, bootstrap = len(daily), config['bootstrap']
    records = []
    for length in bootstrap['blocks']:
        if not 0 < length <= n:
            raise ValueError('Invalid frozen block size')
        rng = np.random.default_rng(int(bootstrap['seed']) + length)
        full, tail_length = divmod(n, length)
        repetitions = int(bootstrap['repetitions'])
        draws = np.empty((repetitions, 5), float)
        counts = np.empty(repetitions, np.int64)
        for offset in range(0, repetitions, 250):
            size = min(250, repetitions - offset)
            # 同一冻结随机抽样协议；每次显式展开 n 个日历日，完全不计算块前缀和。
            starts = rng.integers(0, n, size=(size, full))
            calendar = (starts[:, :, None] + np.arange(length)[None, None, :]) % n
            calendar = calendar.reshape(size, full * length)
            if tail_length:
                tail = rng.integers(0, n, size=size)
                tail_days = (tail[:, None] + np.arange(tail_length)[None, :]) % n
                calendar = np.concatenate([calendar, tail_days], axis=1)
            if calendar.shape != (size, n):
                raise AssertionError('Resampled calendar changed length')
            aggregate = daily[calendar].sum(axis=1)
            if (aggregate[:, 3] <= 0).any():
                raise ValueError('Bootstrap replicate contains no opportunities')
            means = aggregate[:, :3] / aggregate[:, 3, None]
            draws[offset:offset + size, :3] = means
            draws[offset:offset + size, 3] = means[:, 1] - means[:, 0]
            draws[offset:offset + size, 4] = means[:, 2] - means[:, 1]
            counts[offset:offset + size] = aggregate[:, 3].astype(np.int64)
        # 直接以样本均值为中心计算样本标准差，避免调用生产 draws.std。
        centered = draws - draws.mean(axis=0)
        standard_error = np.sqrt(np.sum(centered * centered, axis=0) / (repetitions - 1))
        safe = np.where(standard_error > 0, standard_error, 1.)
        maximum = np.max(np.abs(draws - points) / safe, axis=1)
        # NumPy 默认 linear 分位数的显式次序统计量重建。
        ordered = np.sort(maximum)
        rank = float(bootstrap['confidence']) * (repetitions - 1)
        lo, hi = math.floor(rank), math.ceil(rank)
        critical = float(ordered[lo] + (rank - lo) * (ordered[hi] - ordered[lo]))
        lower, upper = points - critical * standard_error, points + critical * standard_error
        record = dict(block_days=length, repetitions=repetitions, critical=critical,
                      standard_error=standard_error.tolist(), lower=lower.tolist(), upper=upper.tolist(),
                      resampled_opportunities_min=int(counts.min()),
                      resampled_opportunities_max=int(counts.max()),
                      draws_sha256=hashlib.sha256(draws.astype('<f8').tobytes()).hexdigest())
        records.append(record)
        if progress:
            print(f'STATISTICS block={length} repetitions={repetitions} independently reconstructed', flush=True)
    return dict(n=len(frame), names=NAMES, points=points.tolist(), blocks=records,
                lower=np.min([r['lower'] for r in records], axis=0).tolist(),
                upper=np.max([r['upper'] for r in records], axis=0).tolist(),
                calendar_days=n, nonempty_origin_days=int(np.count_nonzero(daily[:, 3])))


def verify_statistics(actual, expected):
    for name in ['n', 'names', 'calendar_days', 'nonempty_origin_days']:
        if actual[name] != expected[name]:
            raise AssertionError(f'Statistic identity differs: {name}')
    differences = {name: numeric_equal(actual[name], expected[name], name)
                   for name in ['points', 'lower', 'upper']}
    if len(actual['blocks']) != len(expected['blocks']):
        raise AssertionError('Different block configurations')
    for rebuilt, saved in zip(actual['blocks'], expected['blocks'], strict=True):
        for key in ['block_days', 'repetitions']:
            if rebuilt[key] != saved[key]:
                raise AssertionError(f'Block identity differs: {key}')
        for key in ['critical', 'standard_error', 'lower', 'upper']:
            name = f"block{rebuilt['block_days']}.{key}"
            differences[name] = numeric_equal(rebuilt[key], saved[key], name)
    return differences


def compare_cohort(frame, opportunities, origins, cost_id):
    if frame.origin_id.duplicated().any():
        raise AssertionError('Paired origin duplicates')
    origin_index = origins.set_index('origin_id', verify_integrity=True)
    cost_rows = opportunities.loc[opportunities.cost_id.eq(cost_id)]
    policy_ids = {}
    for policy in ['A', 'B', 'C']:
        rows = cost_rows.loc[cost_rows.policy.eq(policy)]
        if rows.origin_id.duplicated().any() or set(rows.origin_id) != set(origin_index.index):
            raise AssertionError('Original opportunity universe changed across policies')
        common = rows.loc[rows.complete_window_60 & rows.normal_complete]
        policy_ids[policy] = set(common.origin_id)
    common_ids = policy_ids['A'] & policy_ids['B'] & policy_ids['C']
    if common_ids != set(frame.origin_id):
        raise AssertionError('Saved paired cohort is not the three-policy complete intersection')
    errors = {}
    for policy in ['A', 'B', 'C']:
        source = cost_rows.loc[cost_rows.policy.eq(policy)].set_index('origin_id')
        aligned = source.loc[frame.origin_id]
        errors[policy] = numeric_equal(frame[policy], aligned['return'], f'{cost_id}.{policy} paired return')
        if not aligned.complete_window_60.all() or not aligned.normal_complete.all():
            raise AssertionError('Censored opportunity leaked into primary estimates')
    origin_rows = origin_index.loc[frame.origin_id]
    if not origin_rows.complete_window_60.all():
        raise AssertionError('Common future window false in saved origins')
    if not np.array_equal(frame.symbol.to_numpy(), origin_rows.symbol.to_numpy()):
        raise AssertionError('Paired symbol attribution mismatch')
    if not np.array_equal(frame.origin_ts.to_numpy(), origin_rows.origin_ts.to_numpy()):
        raise AssertionError('Paired date attribution mismatch')
    return dict(n=len(frame), original_origins=len(origins), excluded=len(origins) - len(frame),
                independently_common_ids_equal=all(ids == common_ids for ids in policy_ids.values()),
                policy_common_counts={p: len(ids) for p, ids in policy_ids.items()},
                max_return_error=max(errors.values()))


def metrics(values):
    values = np.asarray(values, float)
    if not len(values) or not np.isfinite(values).all():
        raise ValueError('Invalid descriptive cohort')
    wins, losses = values[values > 0], values[values < 0]
    return dict(n=len(values), mean=math.fsum(values) / len(values), median=float(np.median(values)),
                win_fraction=float(np.count_nonzero(values > 0) / len(values)),
                mean_win=math.fsum(wins) / len(wins) if len(wins) else None,
                mean_loss=math.fsum(losses) / len(losses) if len(losses) else None,
                q05=float(np.quantile(values, .05)), q95=float(np.quantile(values, .95)),
                profit_factor=math.fsum(wins) / abs(math.fsum(losses)) if len(losses) else None)


def verify_metric_row(row, values, name):
    for key, value in metrics(values).items():
        if value is None:
            if not pd.isna(row[key]):
                raise AssertionError(f'{name}.{key} should be absent')
        else:
            numeric_equal(row[key], value, f'{name}.{key}')


def verify_interpretation(root, paired_frames, opportunities):
    yearly = pd.read_csv(root / 'yearly-opportunities.csv')
    deletion = pd.read_csv(root / 'largest-contributor-removal.csv')
    expected_year_rows = 0
    year_records = []
    for cost_id, frame in paired_frames.items():
        for year, group in frame.groupby(frame.origin_ts.dt.year):
            expected_year_rows += 3
            summary = dict(cost_id=cost_id, year=int(year), n=len(group))
            summary.update(dict(zip(NAMES, five_means(group).tolist(), strict=True)))
            year_records.append(summary)
            for policy in ['A', 'B', 'C']:
                found = yearly.loc[yearly.cost_id.eq(cost_id) & yearly.policy.eq(policy) & yearly.year.eq(year)]
                if len(found) != 1:
                    raise AssertionError('Missing or duplicate yearly row')
                row = found.iloc[0]
                verify_metric_row(row, group[policy], f'{cost_id}.{policy}.{year}')
                raw = opportunities.loc[opportunities.cost_id.eq(cost_id) & opportunities.policy.eq(policy)]
                raw = raw.set_index('origin_id').loc[group.origin_id]
                if int(row.entered) != int(raw.entered.sum()):
                    raise AssertionError('Yearly entered population mismatch')
    if len(yearly) != expected_year_rows:
        raise AssertionError('Unexpected yearly rows')
    frame = paired_frames['base'].copy()
    frame['year'] = frame.origin_ts.dt.year
    frame['B_minus_A'], frame['C_minus_B'] = frame.B - frame.A, frame.C - frame.B
    removals = []
    for key in NAMES:
        for grouping in ['symbol', 'year']:
            contributions = {name: math.fsum(g[key]) for name, g in frame.groupby(grouping, sort=True)}
            largest = max(contributions, key=contributions.get)
            kept = frame.loc[frame[grouping].ne(largest)]
            found = deletion.loc[deletion.metric.eq(key) & deletion.removed_group.eq(grouping)]
            if len(found) != 1:
                raise AssertionError('Missing or duplicate contributor removal row')
            row = found.iloc[0]
            if str(row.removed_value) != str(largest):
                raise AssertionError('Wrong contribution maximum removed')
            if int(row.removed_n) != len(frame) - len(kept):
                raise AssertionError('Removal count changed')
            numeric_equal(row.original_mean, five_means(frame)[NAMES.index(key)], 'removal original mean')
            verify_metric_row(row, kept[key], f'{key}.{grouping}.removal')
            removals.append(dict(metric=key, removed_group=grouping, removed_value=str(largest),
                                 removed_n=len(frame) - len(kept), retained_n=len(kept),
                                 retained_mean=math.fsum(kept[key]) / len(kept),
                                 removed_sum=contributions[largest]))
    if len(deletion) != 10:
        raise AssertionError('Unexpected contributor-removal family size')
    return dict(year_rows=len(yearly), yearly_five_means=year_records, removals=removals,
                interpretation=['年度表使用同一完整配对机会母集，年份按 origin 日归属，并非该年账户收益。',
                                '剔除最高贡献币和年份按每个指标分别选择，属于事后集中度诊断，未重新建立置信区间。',
                                '保留均值为正不能单独证明跨年份稳定、单币重复性或未读样本有效。'])


def synthetic_check():
    config = dict(start='2020-01-01T00:00:00Z', end='2020-01-18T00:00:00Z',
                  bootstrap=dict(blocks=[3, 7], repetitions=1000, seed=9, confidence=.95))
    dates = pd.date_range(config['start'], periods=17)
    frame = pd.DataFrame(dict(origin_ts=np.repeat(dates, 2), A=np.tile([-.1, .2], 17)))
    frame['B'], frame['C'] = frame.A, frame.A
    result = reconstruct(frame, config, progress=False)
    numeric_equal(result['points'], [.05, .05, .05, 0., 0.], 'synthetic common mean')
    for block in result['blocks']:
        if block['resampled_opportunities_min'] != 34 or block['resampled_opportunities_max'] != 34:
            raise AssertionError('Synthetic full calendar length not preserved')
        numeric_equal(block['lower'][3:], [0., 0.], 'identical-policy difference bounds')
        numeric_equal(block['upper'][3:], [0., 0.], 'identical-policy difference bounds')
    print('SYNTHETIC PASS: paired identity, circular tail, exact calendar length, zero contrasts', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        synthetic_check()
        return
    out = FAMILY / 'artifacts/statistics-independent.json'
    if out.exists():
        raise FileExistsError(out)
    config_path = FAMILY / 'specs/config.json'
    config = json.loads(config_path.read_text())
    run = FAMILY / 'artifacts' / config['run_id']
    completed_path = run / 'completed.json'
    completed = json.loads(completed_path.read_text())
    started = time.time()
    source_hashes = {str(config_path.relative_to(FAMILY)): sha(config_path),
                     str(completed_path.relative_to(FAMILY)): sha(completed_path)}
    report = dict(status='RUNNING', audit_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  script_sha256=sha(Path(__file__)), source_hashes=source_hashes,
                  independent_method='explicit resampled calendar rows; direct original-observation pairing; no production imports',
                  tolerance=dict(absolute=ATOL, relative=RTOL))
    try:
        for name, expected in completed['files'].items():
            actual = sha(run / name)
            if actual != expected:
                raise AssertionError(f'Completed manifest hash mismatch: {name}')
            source_hashes[str((run / name).relative_to(FAMILY))] = actual
        lock_path = FAMILY / 'specs/computation-lock.json'
        lock = json.loads(lock_path.read_text())
        if sha(lock_path) != completed['lock_reverified']['sha256']:
            raise AssertionError('Completed run lock mismatch')
        for relative, expected in lock['files'].items():
            if sha(REPO / relative) != expected:
                raise AssertionError(f'Frozen source mismatch: {relative}')
        report['completed_manifest_files_verified'] = len(completed['files'])
        report['computation_lock_files_verified'] = len(lock['files'])
        saved = json.loads((run / 'paired-statistics.json').read_text())
        opportunities = pd.read_parquet(run / 'opportunities.parquet')
        origins = pd.read_parquet(run / 'origins.parquet')
        frames, cohorts, means = {}, {}, {}
        for cost in config['costs']:
            name = cost['id']
            frame = pd.read_parquet(run / f'paired-{name}.parquet')
            frames[name] = frame
            cohorts[name] = compare_cohort(frame, opportunities, origins, name)
            expected = saved[name]['points']
            expected = [expected[key] for key in NAMES] if isinstance(expected, dict) else expected
            means[name] = five_means(frame).tolist()
            numeric_equal(means[name], expected, f'{name}.points')
            if saved[name]['n'] != len(frame):
                raise AssertionError('Saved opportunity count differs')
        if not all(set(frame.origin_id) == set(frames['base'].origin_id) for frame in frames.values()):
            raise AssertionError('Cost scenarios changed paired opportunity identity')
        report['cohorts'], report['scenario_points'] = cohorts, means
        rebuilt = reconstruct(frames['base'], config)
        report['maximum_absolute_errors'] = verify_statistics(rebuilt, saved['base'])
        report['reconstructed'] = rebuilt
        interpretation = FAMILY / 'artifacts/interpretation'
        for name in ['yearly-opportunities.csv', 'largest-contributor-removal.csv']:
            source_hashes[str((interpretation / name).relative_to(FAMILY))] = sha(interpretation / name)
        report['descriptive_checks'] = verify_interpretation(interpretation, frames, opportunities)
        for relative, expected in source_hashes.items():
            if sha(FAMILY / relative) != expected:
                raise AssertionError(f'Input changed during independent audit: {relative}')
        report['status'] = 'PASS'
    except Exception as error:
        report['status'] = 'FAIL'
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report['elapsed_seconds'] = time.time() - started
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': report['status'], 'output': str(out),
                      'max_absolute_error': max(report['maximum_absolute_errors'].values()),
                      'elapsed_seconds': report['elapsed_seconds']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
