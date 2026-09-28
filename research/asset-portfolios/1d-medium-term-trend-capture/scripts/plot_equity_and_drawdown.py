"""从本轮已留账户结果制作可分享研究图；不重跑交易或修改生产结果。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
from matplotlib import dates as mdates, font_manager, pyplot as plt, ticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

FAMILY = Path(__file__).resolve().parents[1]
RUN = FAMILY / 'artifacts/research-20260909'
OUTPUT = FAMILY / 'artifacts/interpretation'
START = pd.Timestamp('2019-09-09T00:00:00Z')
END = pd.Timestamp('2026-09-05T00:00:00Z')
INITIAL = 10000.
COLORS = {'A': '#27649A', 'B': '#C05936', 'C': '#317E68'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select_font():
    candidates = font_manager.findSystemFonts()
    for needle in ['PingFang', 'Arial Unicode', 'STHeiti', 'NotoSansCJK']:
        for path in candidates:
            if needle.lower() in path.lower():
                try:
                    font_manager.fontManager.addfont(path)
                except (RuntimeError, OSError):
                    continue
                return font_manager.FontProperties(fname=path).get_name(), True
    return 'DejaVu Sans', False


def main():
    paths = [RUN / 'portfolio_daily.parquet', RUN / 'account-metrics.json']
    source_hashes = {str(path.relative_to(FAMILY)): sha(path) for path in paths}
    png, svg = OUTPUT / 'equity-and-drawdown.png', OUTPUT / 'equity-and-drawdown.svg'
    if png.exists() or svg.exists():
        raise FileExistsError('Research figure already exists; explicit review is required before replacing it')
    rows = pd.read_parquet(paths[0])
    saved = json.loads(paths[1].read_text())
    rows = rows.loc[rows.cost_id.eq('base')]
    if set(rows.policy) != {'A', 'B', 'C'}:
        raise AssertionError('Figure requires precisely the three base-cost accounts')
    series = {}
    for policy in ['A', 'B', 'C']:
        frame = rows.loc[rows.policy.eq(policy)].sort_values('close_ts').copy()
        times = pd.to_datetime(frame.close_ts, utc=True)
        values = frame.equity.to_numpy(float)
        if times.duplicated().any() or not times.diff().dropna().eq(pd.Timedelta(days=1)).all():
            raise AssertionError('Account calendar is duplicated or discontinuous')
        if times.iloc[0] != START + pd.Timedelta(days=1) or times.iloc[-1] != END:
            raise AssertionError('Account dates do not match the frozen observation scope')
        if not np.isfinite(values).all() or (values <= 0).any():
            raise AssertionError('Invalid account values cannot be silently omitted')
        drawdown = values / np.maximum.accumulate(np.r_[INITIAL, values])[1:] - 1
        np.testing.assert_allclose(drawdown, frame.drawdown.to_numpy(float), rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose([values[-1], drawdown.min()],
                                   [saved[f'base.{policy}']['end_equity'], saved[f'base.{policy}']['max_drawdown']],
                                   rtol=1e-12, atol=1e-12)
        series[policy] = (pd.DatetimeIndex([START]).append(pd.DatetimeIndex(times)),
                          np.r_[INITIAL, values], np.r_[0., drawdown])
    font, chinese = select_font()
    plt.rcParams.update({'font.family': font, 'font.size': 10.5, 'axes.unicode_minus': False,
                         'axes.edgecolor': '#BAC2C6', 'axes.labelcolor': '#34444D',
                         'xtick.color': '#52636D', 'ytick.color': '#52636D',
                         'svg.fonttype': 'path', 'savefig.facecolor': 'white'})
    labels = ({'A': 'A  立即进入 · 固定20日', 'B': 'B  立即进入 · 趋势失效退出',
               'C': 'C  等待回撤恢复 · 趋势失效退出'} if chinese else
              {'A': 'A  Immediate / 20-day hold', 'B': 'B  Immediate / trend exit',
               'C': 'C  Pullback restart / trend exit'})
    figure, axes = plt.subplots(2, 1, figsize=(13.7, 9.2), sharex=True,
                                gridspec_kw={'height_ratios': [1.7, 1], 'hspace': .14})
    figure.subplots_adjust(left=.082, right=.962, top=.785, bottom=.175)
    figure.text(.082, .951, '三种中期趋势做法：账户收益与回撤' if chinese else
                'Three trend strategies: account equity and drawdown',
                fontsize=23, fontweight='bold', color='#182D3B', ha='left')
    figure.text(.083, .918, 'Binance 日线观测合约  |  2019-09-09 至 2026-09-05 UTC  |  初始资金 10,000 USDT'
                if chinese else 'Binance daily observed contracts  |  2019-09-09 to 2026-09-05 UTC  |  Initial equity: 10,000 USDT',
                fontsize=11.5, color='#52636D')
    for position, policy in enumerate(['A', 'B', 'C']):
        left = .083 + position * .305
        metric = saved[f'base.{policy}']
        figure.text(left, .865, labels[policy], fontsize=11.5, fontweight='bold', color=COLORS[policy])
        description = (f"累计收益 {metric['total_return']:+.1%}   最大回撤 {metric['max_drawdown']:.1%}" if chinese else
                       f"Total {metric['total_return']:+.1%}   Max drawdown {metric['max_drawdown']:.1%}")
        figure.text(left, .836, description, fontsize=10.7, color='#52636D')
    for axis in axes:
        axis.set_axisbelow(True)
        axis.grid(axis='y', color='#E8EDEF', linewidth=.8)
        axis.spines[['top', 'right']].set_visible(False)
        axis.tick_params(length=3, width=.6)
        axis.axvspan(pd.Timestamp('2026-08-01', tz='UTC'), pd.Timestamp('2026-09-01', tz='UTC'),
                     color='#F0DCC0', alpha=.72, zorder=1)
    for policy in ['A', 'B', 'C']:
        times, values, drawdown = series[policy]
        axes[0].plot(times, values, color=COLORS[policy], lw=1.6, zorder=3)
        axes[1].plot(times, drawdown, color=COLORS[policy], lw=1.4, zorder=3)
        axes[0].scatter([times[-1]], [values[-1]], color=COLORS[policy], s=18, zorder=4)
    axes[0].axhline(INITIAL, color='#9AA7AF', lw=.8, ls=(0, (4, 4)), zorder=0)
    axes[0].set_ylabel('账户权益（USDT）' if chinese else 'Account equity (USDT)', labelpad=13)
    axes[0].yaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
    axes[0].set_ylim(0, max(values.max() for _, values, _ in series.values()) * 1.14)
    axes[1].set_ylabel('距此前高点的回撤' if chinese else 'Drawdown from prior peak', labelpad=13)
    axes[1].yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1, decimals=0))
    axes[1].set_yticks([0, -.1, -.2, -.3, -.4, -.5])
    axes[1].set_ylim(-.515, .025)
    axes[1].set_xlim(START, END)
    axes[1].xaxis.set_major_locator(mdates.YearLocator())
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    axes[1].set_xlabel('日收盘权益的估值时刻（UTC）' if chinese else 'Daily close valuation time (UTC)', labelpad=11)
    august = rows.loc[pd.to_datetime(rows.close_ts, utc=True).between(
        pd.Timestamp('2026-08-01', tz='UTC'), pd.Timestamp('2026-09-01', tz='UTC'), inclusive='left')]
    peak = august.loc[august.equity.idxmax()]
    note = '2026年8月：三账户均出现大幅回撤\n着色仅标记同一日历区间，不表示因果检验' if chinese else (
        'August 2026: large drawdowns in all three accounts\nShading identifies a period, not a causal test')
    axes[0].annotate(note, xy=(pd.Timestamp(peak.close_ts), float(peak.equity)),
                     xytext=(.43, .86), textcoords='axes fraction', fontsize=10.7,
                     color='#705A3D', ha='left', va='top', linespacing=1.55,
                     arrowprops={'arrowstyle': '-', 'color': '#A28B6D', 'lw': .9,
                                 'connectionstyle': 'angle,angleA=0,angleB=90,rad=6'})
    footnotes = ([
        '费用口径：每次成交手续费 0.1%，单边不利滑点 0.04%；本图未扣完整历史资金费。',
        '重复使用历史（ITERATIVE_REUSED_DIAGNOSTIC）；仅为历史研究，不代表已通过独立验证。',
        '三套账户各自顺序执行、最多10槽；期末未平仓按最后观察价格估值。累计盈利不等于趋势信号已获验证。',
    ] if chinese else [
        'Costs: 0.1% fee and 0.04% adverse slippage per fill. Complete historical funding is not deducted.',
        'ITERATIVE_REUSED_DIAGNOSTIC: reused historical evidence; independent future validation remains outstanding.',
        'Separate sequential accounts, at most 10 slots; open positions are marked. Profits do not establish signal increment.',
    ])
    for index, line in enumerate(footnotes):
        figure.text(.083, .103 - index * .025, line, fontsize=9.7, color='#596970', ha='left')
    metadata = {'Title': 'BIN-1D-MTTC account equity and drawdown',
                'Description': json.dumps({'sources': source_hashes, 'script_sha256': sha(__file__),
                                            'font': font, 'history': 'ITERATIVE_REUSED_DIAGNOSTIC'},
                                           ensure_ascii=False)}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    figure.savefig(png, dpi=190, metadata=metadata)
    figure.savefig(svg, metadata=metadata)
    plt.close(figure)
    for relative, expected in source_hashes.items():
        if sha(FAMILY / relative) != expected:
            raise AssertionError('Saved account data changed during plotting')
    print(json.dumps({'png': str(png), 'svg': str(svg), 'font': font,
                      'png_sha256': sha(png), 'svg_sha256': sha(svg), 'sources': source_hashes},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
