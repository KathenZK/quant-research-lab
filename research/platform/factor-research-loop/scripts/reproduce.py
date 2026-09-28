"""One explicit command: select collected definitions -> freeze -> study -> read back.

Requires an already accepted private core-market manifest and its original
acquisition contract. Never downloads data or writes a shared database.
"""
import argparse
import json
from pathlib import Path
from quantgraph import FactorDB
from quantgraph.factor_study import draft_request
from strategy_lab.factor_study.pipeline import freeze, run, write


def main():
    p = argparse.ArgumentParser()
    for name in ('graph-root', 'manifest', 'acquisition-contract', 'output', 'journal'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--exposure-ledger', type=Path)
    a = p.parse_args()
    lab_root = Path(__file__).resolve().parents[4]
    settings = json.loads((Path(__file__).resolve().parents[1] / 'specs/settings-v1.json').read_text())
    a.output.mkdir(parents=True, exist_ok=False)
    db = FactorDB(a.graph_root, profile='commercial')
    selection = draft_request(db, settings['names'], 'factor-research-loop-v1', settings)
    selected = write(a.output / 'graph-selection.json', selection)
    study = a.output / 'study'
    freeze(selected, a.manifest, a.acquisition_contract, study, graph_root=a.graph_root,
           lab_root=lab_root, exposure_ledger=a.exposure_ledger)
    kwargs = dict(graph_root=a.graph_root, lab_root=lab_root, journal=a.journal)
    first = run(study / 'plan.json', only='KMID', **kwargs)
    if first[0]['study_status'] != 'SUCCESS':
        raise RuntimeError('First factor failed; evidence retained. No expansion.')
    receipts = run(study / 'plan.json', **kwargs)
    readback = {v['factor_variant_id']: db.factor_studies(v['factor_variant_id'], journal=a.journal, profile='research')
                for v in selection['definitions']}
    write(a.output / 'graph-readback.json', readback)
    print(json.dumps({'receipts': receipts, 'private_report': str(study / 'report.md'),
                      'readback': str(a.output / 'graph-readback.json')}, indent=2))


if __name__ == '__main__':
    main()
