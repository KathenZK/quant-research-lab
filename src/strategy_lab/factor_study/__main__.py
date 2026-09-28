"""Explicit freeze/run commands; a Graph DRAFT is never itself run authorization."""
import argparse
import json
from pathlib import Path
import sys
from .pipeline import freeze, run, write


def main():
    p = argparse.ArgumentParser(description='Private exploratory factor study')
    sp = p.add_subparsers(dest='command', required=True)
    f = sp.add_parser('freeze')
    for name in ('selection', 'manifest', 'acquisition-contract', 'output', 'graph-root', 'lab-root'):
        f.add_argument('--' + name, type=Path, required=True)
    f.add_argument('--exposure-ledger', type=Path)
    r = sp.add_parser('run')
    for name in ('plan', 'graph-root', 'lab-root', 'journal'):
        r.add_argument('--' + name, type=Path, required=True)
    r.add_argument('--only')
    args = p.parse_args()
    try:
        if args.command == 'freeze':
            plan = freeze(args.selection, args.manifest, args.acquisition_contract, args.output,
                          graph_root=args.graph_root, lab_root=args.lab_root, exposure_ledger=args.exposure_ledger)
            result = {'plan_sha256': plan['plan_sha256'], 'counts': plan['counts'],
                      'status': 'FROZEN_FOR_EXPLORATORY_DIAGNOSTIC'}
        else:
            result = run(args.plan, graph_root=args.graph_root, lab_root=args.lab_root,
                         journal=args.journal, only=args.only)
    except Exception as exc:
        result = {'status': 'FAILED', 'error': type(exc).__name__, 'reason': str(exc)}
        target = args.output if args.command == 'freeze' else args.plan.parent
        # Do not overwrite previous attempts, including startup/admission failures.
        target.mkdir(parents=True, exist_ok=True)
        from uuid import uuid4
        write(target / ('failed-attempt-' + uuid4().hex + '.json'), result)
        print(json.dumps(result, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
