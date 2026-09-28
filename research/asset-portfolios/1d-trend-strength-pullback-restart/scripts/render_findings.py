"""一次性导出冻结结果的静态研究图与贡献描述；不选择新策略。"""
from __future__ import annotations

import datetime as dt
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from family_common import FAMILY, save_json, sha, verify_lock


def main():
    verify_lock()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', default='interpretation-figures')
    args = parser.parse_args()
    if Path(args.run_id).name != args.run_id or args.run_id in ('.', '..'):
        raise ValueError('single output directory name required')
    out = FAMILY / 'artifacts' / args.run_id
    if out.exists():
        raise FileExistsError(out)
    out.mkdir()
    primary = FAMILY / 'artifacts/p1-research'
    matrix = pd.read_csv(primary / 'state-matrix.csv')
    paths = pd.read_csv(primary / 'common-sample-path.csv')
    palette = {'ALL': '#8b949e', 'HIGH': '#285f9a', 'HIGH_P': '#c08928', 'HIGH_PM': '#a1423c'}
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'figure.facecolor': 'white', 'axes.facecolor': 'white'})
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), constrained_layout=True)
    for row, side in enumerate(('LONG', 'SHORT')):
        ax = axes[row, 0]
        a = matrix.loc[matrix.direction.eq(side) & matrix.P.eq('ALL')].sort_values('band')
        ax.plot(a.band, a.Q20, marker='o', label='Full 20 days', color='#285f9a')
        ax.plot(a.band, a.Late, marker='s', label='Days 5 to 20', color='#a1423c')
        ax.set_xticks((1, 2, 3), ('LOW', 'MID', 'HIGH'))
        ax.set_title(f'{side}: past strength bins, all eligible days')
        ax.set_ylabel('Mean directional move / lagged ATR')
        ax.axhline(0, color='#c6c6c6', linewidth=.8)
        ax.legend(frameon=False)
        ax = axes[row, 1]
        for prefix, color in palette.items():
            a = paths.loc[paths.group.eq(f'{prefix}_{side}') & paths.common_complete_horizon.eq(20)]
            ax.plot(a.horizon, a.mean_Q, marker='o', color=color, label=prefix)
        ax.axhline(0, color='#c6c6c6', linewidth=.8)
        ax.set_xticks((1, 5, 10, 20))
        ax.set_xlabel('Days after next-open entry')
        ax.set_title(f'{side}: same complete-20-day cohort')
        ax.legend(frameon=False, fontsize=9)
    fig.suptitle('Descriptive historical means — no confidence claim', fontsize=15)
    fig.savefig(out / 'strength-and-path.png', dpi=160)
    fig.savefig(out / 'strength-and-path.pdf')
    plt.close(fig)
    save_json(out / 'receipt.json', {'status': 'PASS', 'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                                    'role': 'static rendering of previously frozen CSV means only',
                                    'source_sha256': sha(Path(__file__)),
                                    'inputs': {n: sha(primary / n) for n in ('state-matrix.csv', 'common-sample-path.csv')},
                                    'files': {p.name: sha(p) for p in out.iterdir() if p.is_file()}})
    print('Descriptive figures written; contribution export uses export_contributions.py')


if __name__ == '__main__':
    main()
