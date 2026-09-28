"""Explicit local operator command; consume a DRAFT, review settings, register and run."""
import argparse
from pathlib import Path
from strategy_lab.factor_study.request_adapter import resolve_request
from strategy_lab.factor_study.registered_trials import RegisteredTrialAdapter
from strategy_lab.factor_study.pipeline import freeze, run, write


def main():
    parser = argparse.ArgumentParser()
    for name in ('request', 'settings', 'graph-root', 'manifest', 'acquisition-contract', 'output', 'journal'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--exposure-ledger', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    lab_root = Path(__file__).resolve().parents[4]
    try:
        selection = resolve_request(args.request, args.settings, args.graph_root)
        path = write(args.output / 'selection.json', selection)
        adapter = RegisteredTrialAdapter(args.output / 'trial-registry.jsonl')
        freeze(path, args.manifest, args.acquisition_contract, args.output / 'study',
               graph_root=args.graph_root, lab_root=lab_root,
               exposure_ledger=args.exposure_ledger, trial_adapter=adapter)
        receipts = run(args.output / 'study/plan.json', graph_root=args.graph_root,
                       lab_root=lab_root, journal=args.journal, trial_adapter=adapter)
        write(args.output / 'receipts.json', receipts)
        if not all(r['study_status'] == 'SUCCESS' for r in receipts):
            raise RuntimeError('Failed/invalid outcomes retained; integration not accepted')
    except Exception as exc:
        write(args.output / 'failure.json', {'type': type(exc).__name__, 'reason': str(exc)})
        raise


if __name__ == '__main__':
    main()
