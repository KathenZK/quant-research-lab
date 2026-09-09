"""一次性贡献与固定删除描述；使用原研究运行时读取已核验面板。"""
from pathlib import Path
import datetime as dt
import numpy as np
import pandas as pd
from family_common import FAMILY, load_panel, save_json, sha, verify_lock

def main():
    verify_lock()
    out = FAMILY / 'artifacts/interpretation-tables'
    if out.exists():
        raise FileExistsError(out)
    out.mkdir()
    panel, identity = load_panel()
    contribution_rows, exclusion_rows, distribution_rows = [], [], []
    for side, d in (('LONG', 1), ('SHORT', -1)):
        for prefix in ('ALL', 'HIGH', 'HIGH_P', 'HIGH_PM'):
            group = f'{prefix}_{side}'
            p = panel.loc[panel[group] & panel.valid20, ['symbol', 'signal_time', 'q20', 'l20', 'ret20']].copy()
            p['month'] = p.signal_time.dt.strftime('%Y-%m')
            p['year'] = p.signal_time.dt.year
            for label in ('q20', 'l20', 'ret20'):
                p[label] *= d
                values = p[label].to_numpy()
                total = values.sum()
                for q in (.01, .05, .25, .5, .75, .95, .99):
                    distribution_rows.append({'group': group, 'label': label, 'quantile': q,
                                              'value': np.quantile(values, q) if len(values) else np.nan})
                for kind in ('symbol', 'month'):
                    by = p.groupby(kind)[label].agg(['sum', 'count']).sort_values('sum', ascending=False)
                    if by.empty:
                        continue
                    for key, row in by.head(5).iterrows():
                        contribution_rows.append({'group': group, 'label': label, 'kind': kind,
                                                  'key': str(key), 'n': int(row['count']),
                                                  'sum': row['sum'], 'whole_sum': total,
                                                  'fraction_of_net_sum': row['sum']/total if total else np.nan})
                    largest = by.iloc[0]
                    remaining_n = len(p) - int(largest['count'])
                    exclusion_rows.append({'group': group, 'label': label, 'kind': 'remove_top_' + kind,
                                           'key': str(by.index[0]), 'remaining_n': remaining_n,
                                           'remaining_mean': (total-largest['sum'])/remaining_n if remaining_n else np.nan,
                                           'identity': 'DESCRIPTIVE_OUTCOME_SELECTED_REMOVAL_NOT_NEW_RULE'})
                for year in sorted(p.year.unique()):
                    remaining = p.loc[p.year.ne(year), label]
                    exclusion_rows.append({'group': group, 'label': label, 'kind': 'leave_year_out',
                                           'key': str(year), 'remaining_n': len(remaining),
                                           'remaining_mean': remaining.mean(), 'identity': 'DESCRIPTIVE_ONLY'})
    pd.DataFrame(contribution_rows).to_csv(out / 'top-contributions.csv', index=False)
    pd.DataFrame(exclusion_rows).to_csv(out / 'fixed-exclusions.csv', index=False)
    pd.DataFrame(distribution_rows).to_csv(out / 'label-distributions.csv', index=False)
    save_json(out / 'receipt.json', {'status': 'PASS', 'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                                    'role': 'descriptive fixed exclusions and static rendering only',
                                    'source_sha256': sha(Path(__file__)), **identity,
                                    'files': {p.name: sha(p) for p in out.iterdir() if p.is_file()}})

if __name__ == '__main__':
    main()
