"""Frozen market probes and strict admission for formal ResearchEvidence.

Raw-unaccepted output is private diagnostic evidence only. It is never submitted
as REAL_MARKET_BACKTEST and cannot enter the formal market backtest counter.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'src'))
from strategy_lab.research.trials import TrialRegistry  # noqa: E402
from strategy_lab.research.accounting import digest  # noqa: E402
from strategy_lab.research.statistics import assemble_dsr, evaluate_pbo  # noqa: E402


def load_module(name, path):
    expected = {'qg_market_v1': 'fc2161abeef0cc06303e0e41945f875e11c9c75758bfa125971a709ab770254b',
                'qg_statistics_v2': 'f562a427036b10b679fcbba9ebccba2aba614aaa8a8d818751262471c1792c8d'}
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected[name]:
        raise ValueError('Frozen kernel changed; create a new version before use')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ENGINE_PATH = ROOT/'research/_shared-kernels/quantgraph-market/v1/engine.py'
METRICS_PATH = ROOT/'research/_shared-kernels/quantgraph-diagnostics/v2/metrics.py'
engine = load_module('qg_market_v1', ENGINE_PATH)
metrics = load_module('qg_statistics_v2', METRICS_PATH)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def read_market(manifest_path, contract):
    manifest = json.loads(manifest_path.read_text())
    if manifest['symbol'] != contract['symbol'] or manifest['minutes'] != contract['minutes'] or manifest['exchange'] != contract['exchange']:
        raise ValueError('Data identity differs from frozen contract')
    observations = []
    for page in manifest['pages']:
        path = manifest_path.parent/page['path']
        if sha(path) != page['sha256']:
            raise ValueError('Raw bytes changed')
        observations.extend(json.loads(path.read_bytes()))
    frame = pd.DataFrame(observations, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    if frame.empty:
        raise ValueError('No historical market observations returned')
    frame['ts'] = pd.to_datetime(frame.timestamp, unit='ms', utc=True)
    # End is fixed before download. Never declare native trade counts or infer
    # trusted closure flags. Historical probes use only bars fully before it.
    end = pd.Timestamp(contract['end_exclusive'])
    frame = frame[(frame.ts >= pd.Timestamp(contract['requested_start'])) &
                  (frame.ts + pd.Timedelta(minutes=contract['minutes']) <= end)].sort_values('ts').reset_index(drop=True)
    duplicate_observations = int(frame.ts.duplicated().sum())
    if duplicate_observations:
        for _, group in frame[frame.ts.duplicated(keep=False)].groupby('ts'):
            if len(group.drop_duplicates()) != 1:
                raise ValueError('Conflicting repeated raw observations')
        # Preserve both raw snapshots; collapse only byte-equivalent decoded
        # candle values for computation, with explicit multiplicity in audit.
        frame = frame.drop_duplicates().reset_index(drop=True)
    audit = dict(status='UNVERIFIED', acceptance_status=manifest['acceptance_status'],
                 rows=len(frame), start=str(frame.ts.min()), end=str(frame.ts.max()),
                 missing_native_fields=manifest['missing_native_fields'],
                 raw_hashes=[r['sha256'] for r in manifest['pages']], manifest_sha256=sha(manifest_path),
                 normalized_written=False, trusted_loader_used=False,
                 identical_repeated_observations=duplicate_observations,
                 reason='Provider has no native trade_count; quote volume/vwap and trusted closure not established. Private raw diagnostic only.',
                 requested_start=contract['requested_start'], requested_end_exclusive=contract['end_exclusive'])
    audit['requested_history_fully_covered'] = frame.ts.min() == pd.Timestamp(contract['requested_start'])
    return frame, manifest, audit


def summarize(account, trades, periods):
    if len(account) < 3:
        return dict(status='INSUFFICIENT_SAMPLE', observations=len(account))
    result = metrics.performance(account.return_net.to_numpy(), periods)
    result.update(volatility=float(account.return_net.std(ddof=1)*np.sqrt(periods)),
                  turnover=float(account.turnover.sum()), turnover_annualized=float(account.turnover.mean()*periods),
                  exposure=float(account.exposure.mean()), fees=float(account.fee.sum()), slippage_cost=float(account.slippage_cost.sum()),
                  closed_trades=len(trades), win_rate=float((trades.pnl > 0).mean()) if len(trades) else None,
                  ambiguous_bracket_bars=int(account.ambiguous_bracket.sum()),
                  start=str(account.ts.iloc[0]), end=str(account.ts.iloc[-1]))
    return result


def optional(fn):
    try:
        return {'status': 'COMPUTED', **fn()}
    except ValueError as e:
        return {'status': 'NOT_COMPUTABLE', 'value': None, 'reason': str(e)}


def study(bars, contract, out, *, trial_context=None):
    grid = contract['parameter_grid']
    out.mkdir(parents=True, exist_ok=False)
    per_year = 365*1440/contract['minutes']
    split = pd.Timestamp(contract['oos_start'])
    ctx = trial_context or {}
    registry = TrialRegistry(ctx.get('registry_path', out.parent / 'trial-registry.jsonl'))
    experiment_id = ctx.get('experiment_id', 'legacy-' + digest(contract))
    campaign_id = ctx.get('selection_campaign_id', experiment_id)
    scope_campaigns = ctx.get('selection_campaign_ids', [campaign_id])
    if campaign_id not in scope_campaigns:
        raise ValueError('Selection scope must include the current campaign')
    if not ctx.get('selection_campaign_id'):
        registry.register_campaign(campaign_id, selection_goal='Legacy fixed-grid replay',
            scope_definition='Only this invocation is known; broader selection history has not been established',
            history_reason='Historical searches and cross-family selection scope unknown')
    dataset_pin = ctx.get('dataset_fingerprint', hashlib.sha256(pd.util.hash_pandas_object(bars, index=False).values.tobytes()).hexdigest())
    sample_pin = digest({'dataset': dataset_pin, 'timestamps': [str(t) for t in bars.loc[bars.ts >= split, 'ts']]})
    package = ROOT / 'src/strategy_lab/research'
    code_pin = digest({str(p.relative_to(ROOT)): sha(p) for p in
        [Path(__file__), Path(engine.__file__), METRICS_PATH, package/'statistics.py', package/'trials.py', package/'exposure.py']})
    surface, returns, accounts, attempt_ids = [], [], [], []

    def registered_replay(parameters, *, multiplier=1, role='CANDIDATE'):
        spec = dict(hypothesis_family_id=ctx.get('hypothesis_family_id', experiment_id),
            selection_campaign_id=campaign_id, identity=ctx.get('identity', contract['signal']),
            parameters=parameters, label_horizon=ctx.get('label_horizon', 'NO_PREDICTIVE_LABEL'),
            objective='Sharpe of net account returns', selection_rule=ctx.get('selection_rule', 'Frozen baseline; inspect full parameter surface'),
            dataset_fingerprint=dataset_pin, sample_fingerprint=sample_pin, code_hash=code_pin,
            config_hash=digest(contract), parent_experiment_id=ctx.get('parent_experiment_id'),
            cost_multiplier=multiplier, trial_role=role)
        aid = registry.plan(experiment_id, spec)
        prior = next(a for a in registry.snapshot([campaign_id])['attempts'] if a['attempt_id'] == aid)
        # An already completed replay is still the same statistical trial.
        if prior['state'] != 'completed':
            registry.record(aid, event_id='start-' + str(len(prior['events'])), state='started',
                results_observed=prior['results_observed'], affects_selection=prior['affects_selection'], reason='Replay started/retried')
        try:
            account, fills, trades = engine.replay(bars, contract, parameters, cost_multiplier=multiplier)
        except BaseException as exc:
            if prior['state'] != 'completed':
                registry.record(aid, event_id='failure-' + str(len(prior['events'])),
                    state='aborted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                    results_observed=prior['results_observed'], affects_selection=prior['affects_selection'], reason=type(exc).__name__ + ': ' + str(exc))
            raise
        return aid, account, fills, trades

    def complete(aid, account_path, *, diagnostic=False):
        refs = dict(account_path=str(account_path.resolve()), account_sha256=sha(account_path),
            dataset_fingerprint=dataset_pin, sample_fingerprint=sample_pin, periods_per_year=per_year,
            oos_start=contract['oos_start'])
        registry.record(aid, event_id='complete-' + digest(refs), state='completed', results_observed='OBSERVED',
            affects_selection='NO' if diagnostic else 'YES', reason='Results persisted; diagnostics explicitly excluded from candidate selection' if diagnostic else 'Candidate result available for subsequent research',
            result_refs=refs)

    for i, p in enumerate(grid):
        aid, account, fills, trades = registered_replay(p)
        attempt_ids.append(aid)
        accounts.append(account)
        returns.append(account.return_net.to_numpy())
        account.to_csv(out/f'account-{i}.csv', index=False)
        fills.to_csv(out/f'fills-{i}.csv', index=False)
        trades.to_csv(out/f'trades-{i}.csv', index=False)
        complete(aid, out/f'account-{i}.csv')
        closed = pd.to_datetime(trades.exit_ts, utc=True) if len(trades) else pd.Series([], dtype='datetime64[ns, UTC]')
        ins = account.ts < split
        surface.append(dict(parameters=p, full=summarize(account, trades, per_year),
                            in_sample=summarize(account[ins], trades[closed < split], per_year),
                            oos=summarize(account[~ins], trades[closed >= split], per_year)))
    baseline = grid.index(contract['parameters'])
    base = accounts[baseline]
    osmask = (base.ts >= split).to_numpy()
    matrix = np.column_stack(returns)
    scope = registry.snapshot(scope_campaigns)
    scoped_returns = {}
    for attempt in scope['attempts']:
        if attempt['attempt_id'] not in scope['selection_trial_ids']:
            continue
        events = [e['data'] for e in attempt['events'] if e['data']['state'] == 'completed']
        if not events:
            continue
        refs = events[-1]['result_refs']
        path = Path(refs.get('account_path', ''))
        if not path.is_file() or sha(path) != refs.get('account_sha256'):
            continue  # Missing history remains explicit in assemble_dsr.
        frame = pd.read_csv(path)
        values = frame.loc[pd.to_datetime(frame.ts, utc=True) >= pd.Timestamp(refs['oos_start']), 'return_net']
        scoped_returns[attempt['attempt_id']] = dict(kind='STRATEGY_RETURNS', values=values.tolist(),
            dataset_fingerprint=refs['dataset_fingerprint'], sample_fingerprint=refs['sample_fingerprint'],
            periods_per_year=refs['periods_per_year'])
    ins = matrix[~osmask]
    usable = len(ins)//8*8
    pbo = evaluate_pbo(ins[:usable], blocks=8, context=dict(
        input_kind='FIXED_CANDIDATE_RETURNS', synchronous=True, future_information=False,
        preprocessing='NONE_OR_CAUSAL', overlapping_labels=False,
        boundary_policy='CONTINUOUS_CAUSAL_ACCOUNT', selection_scope_complete=False,
        protocol_frozen_before_results=False,
        block_justification='Legacy fixed eight blocks; dependence adequacy has not been established',
        dependence_review=None, evidence_refs=[]))
    pbo.update(sample='IN_SAMPLE_ONLY', dropped_tail_observations=len(ins)-usable,
               limitation='Fixed causal rule/account returns; cross-block holdings alone do not mandate purge. Scope/dependence not verified; diagnostic only')
    # An unordered multi-axis grid has no defined adjacent plateau. Never report
    # a 1-D plateau for zscore/EMA grids whose ordering is arbitrary.
    scores = [r['oos'].get('sharpe') for r in surface]
    local = {'status': 'REPORTED_FULL_SURFACE', 'oos_sharpe_range': [min(x for x in scores if x is not None), max(x for x in scores if x is not None)] if any(x is not None for x in scores) else None,
             'plateau': optional(lambda: metrics.plateau(scores)) if contract['signal'] == 'PRICE_SMA' else
             {'value': None, 'status': 'NOT_COMPUTED', 'reason': 'Multi-axis grid: adjacency not frozen; full surface reported'}}
    stress = []
    for m in contract['stress_cost_multipliers']:
        aid, a, _, t = registered_replay(contract['parameters'], multiplier=m, role='PRESPECIFIED_DIAGNOSTIC')
        stress_path = out / ('stress-account-' + str(m) + '.csv')
        a.to_csv(stress_path, index=False)
        complete(aid, stress_path, diagnostic=True)
        stress.append(dict(multiplier=m, full=summarize(a, t, per_year)))
    slices = {}
    anchor = base.ts.iloc[-1] + pd.Timedelta(minutes=contract['minutes'])
    for label, days in [('1d', 1), ('7d', 7), ('1m', 30), ('3m', 90), ('6m', 180), ('1y', 365)]:
        window = base[base.ts >= anchor-pd.Timedelta(days=days)]
        slices[label] = {**summarize(window, pd.DataFrame(), per_year), 'win_rate': None,
                         'closed_trades': None, 'purpose': 'AUDIT_ONLY_NOT_SELECTION'}
    scope = registry.snapshot(scope_campaigns)
    dsr = assemble_dsr(scope, scoped_returns, selected_attempt_id=attempt_ids[baseline],
                       dependence=ctx.get('dependence'), return_assumptions=ctx.get('return_assumptions'))
    result = dict(trial_registry=scope, attempt_ids=attempt_ids, baseline_parameters=contract['parameters'], parameter_grid=grid, trial_count=len(grid),
                  in_sample=surface[baseline]['in_sample'], oos=surface[baseline]['oos'],
                  full=surface[baseline]['full'], costs=stress, turnover=surface[baseline]['full']['turnover'],
                  robustness=dict(surface=surface, local_plateau=local, selection='baseline fixed before market download; no OOS retuning'),
                  deflated_sharpe=dsr, pbo=pbo, recent_slices=slices,
                  walk_forward={'status': 'NOT_COMPUTED', 'reason': 'Frozen IS/OOS; no fitted model or expanding-window selection'},
                  limitations=contract['limitations'])
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--contract', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--private-diagnostic', action='store_true')
    a = p.parse_args()
    contract = json.loads(a.contract.read_text())
    bars, manifest, audit = read_market(a.manifest, contract)
    if not a.private_diagnostic:
        raise ValueError('UPSTREAM_CONTRACT_UNSUPPORTED: this raw adapter has no trusted dataset; formal research rejected')
    try:
        results = study(bars, contract, a.output)
    except ValueError as exc:
        a.output.mkdir(parents=True, exist_ok=True)
        write_json(a.output/'data-audit.json', audit)
        write_json(a.output/'failure.json', dict(status='DATA_OR_REPRODUCTION_FAILURE', reason=str(exc),
                   formal_market_backtest_count=0, real_market_data=True, promotion_allowed=False))
        raise
    write_json(a.output/'data-audit.json', audit)
    write_json(a.output/'diagnostic.json', dict(schema_version='private-market-probe-v3',
        status='EXPLORE_UNTRUSTED', formal_market_backtest_count=0, real_market_data=True,
        evidence_kind='PRIVATE_DIAGNOSTIC_PROBE', promotion_allowed=False,
        contract_sha256=sha(a.contract), code_sha256=sha(ENGINE_PATH), metrics_sha256=sha(METRICS_PATH),
        runner_sha256=sha(Path(__file__)), data_audit=audit, results=results,
        rights=manifest['rights'], not_submitted_to_quantgraph=True))
    print(json.dumps(dict(status='EXPLORE_UNTRUSTED', formal_market_backtest_count=0, output=str(a.output))))


if __name__ == '__main__':
    main()
