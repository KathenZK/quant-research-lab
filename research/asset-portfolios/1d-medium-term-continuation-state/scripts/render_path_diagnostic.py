"""固定完整20日队列的事后均值路径；描述性作图，不增加检验或退出规则。"""
from pathlib import Path
import datetime as dt
import hashlib
import json
import argparse

import numpy as np
import pandas as pd

FAMILY=Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export-only',action='store_true')
    parser.add_argument('--render-only',action='store_true')
    args=parser.parse_args()
    if args.export_only and args.render_only:
        raise ValueError('choose one stage')
    inp=FAMILY/'artifacts/p1-research'
    out=FAMILY/'artifacts/path-illustration'
    if args.render_only:
        render(out)
        return
    if out.exists():
        raise FileExistsError(out)
    manifest=json.loads((inp/'panel-manifest.json').read_text())
    assert digest(inp/'panel.pkl.gz')==manifest['sha256']
    panel=pd.read_pickle(inp/'panel.pkl.gz',compression='gzip')
    points=pd.read_csv(inp/'point-summary.csv').set_index('group')
    units=list(points.index)
    rows=[]
    g=panel.groupby(['symbol','research_segment_id'],sort=False)
    for day in range(1,21):
        q=(g.close.shift(-day)-panel.entry_open)/panel.atr14
        for unit in units:
            mask=panel.valid20 & panel[unit]
            vals=q[mask]*(1 if unit.endswith('LONG') else -1)
            assert np.isfinite(vals).all()
            if day==20:
                np.testing.assert_allclose(vals.mean(),points.loc[unit,'q20'],rtol=1e-12,atol=1e-12)
            rows.append({'group':unit,'day':day,'events':len(vals),
                         'mean_q':float(vals.mean()),'median_q':float(vals.median())})
    out.mkdir(parents=True)
    paths=pd.DataFrame(rows)
    paths.to_csv(out/'fixed-cohort-paths.csv',index=False)
    (out/'export-receipt.json').write_text(json.dumps({'panel_sha256':manifest['sha256'],
        'script_sha256':digest(Path(__file__)),'csv_sha256':digest(out/'fixed-cohort-paths.csv')},indent=2)+'\n')
    if not args.export_only:
        render(out)


def render(out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    receipt=json.loads((out/'export-receipt.json').read_text())
    assert digest(out/'fixed-cohort-paths.csv')==receipt['csv_sha256']
    paths=pd.read_csv(out/'fixed-cohort-paths.csv')
    colors={'U':'#89909a','M':'#263d52','S1':'#087f8c','S2':'#c9563a','S3':'#8860a6'}
    labels={'U':'U: prior 20-day direction','M':'M: all MA7 crossings',
            'S1':'S1: direction established','S2':'S2: new-direction candidate',
            'S3':'S3: pullback restart'}
    plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False,
                         'figure.facecolor':'#fcfcfa','axes.facecolor':'#fcfcfa'})
    fig,axes=plt.subplots(1,2,figsize=(12,6),sharey=True)
    for ax,side in zip(axes,('LONG','SHORT')):
        for prefix in ('U','M','S1','S2','S3'):
            p=paths.loc[paths.group.eq(prefix+'_'+side)]
            ax.plot(p.day,p.mean_q,color=colors[prefix],label=labels[prefix],
                    linewidth=2.6 if prefix.startswith('S') else 1.7,
                    linestyle='--' if prefix=='U' else '-')
        ax.axhline(0,color='#777777',linewidth=.7)
        ax.axvline(5,color='#b7b7b7',linewidth=.8,linestyle=':')
        ax.set(title=side.title()+' signals',xlabel='Completed days since next-open entry',
               xlim=(1,20),xticks=[1,5,10,15,20])
        ax.grid(axis='y',alpha=.16)
    axes[0].set_ylabel('Mean signed price displacement / signal-day ATR14')
    fig.suptitle('MA7 mixes continuation and new-direction events',fontsize=17,x=.08,ha='left')
    handles,legend=axes[0].get_legend_handles_labels()
    fig.legend(handles,legend,loc='lower left',bbox_to_anchor=(.065,.05),ncol=3,frameon=False,fontsize=10)
    fig.text(.08,.015,'Same complete-20-day cohort at every point. Overlapping historical events; no confidence bands or trading-profit claim.',fontsize=9,color='#555555')
    fig.subplots_adjust(left=.08,right=.98,top=.84,bottom=.25,wspace=.15)
    fig.savefig(out/'continuation-paths.png',dpi=180)
    fig.savefig(out/'continuation-paths.svg')
    plt.close(fig)
    result={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'panel_sha256':receipt['panel_sha256'],
            'script_sha256':digest(Path(__file__)),'cohort':'valid20 fixed within unit',
            'hypotheses_added':False,'kind':'POST_RESULT_DESCRIPTIVE_PATH_ILLUSTRATION',
            'files':{p.name:digest(p) for p in out.iterdir() if p.is_file()}}
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
