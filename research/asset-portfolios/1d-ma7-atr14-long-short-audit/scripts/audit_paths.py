"""Descriptive accounting of changes to original long entry/exit paths."""
from pathlib import Path
import argparse
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',default='20260908-r1');args=parser.parse_args()
    out=ROOT/'artifacts'/args.run_id
    assert not (out/'long-path-changes.csv.gz').exists()
    t=pd.read_csv(out/'main-window-trades.csv.gz');m=pd.read_csv(out/'main-symbol-results.csv')
    ids=set(m.loc[m.asset_class.eq('COIN')&m.full_requested_window,'run_id'])
    rows=[]
    for ident,g in t.groupby('run_id',sort=False):
        base=g.loc[g.variant.eq('long')]
        for variant in ['both','reverse']:
            ext=g.loc[g.variant.eq(variant)]
            for _,a in base.iterrows():
                match=ext.loc[ext.side.eq(1)&ext.entry_idx.eq(a.entry_idx)]
                alive=ext.loc[ext.entry_idx.le(a.signal_idx)&ext.exit_idx.gt(a.signal_idx)]
                assert len(alive)<=1 and len(match)<=1
                b=match.iloc[0] if len(match) else None
                rows.append(dict(run_id=ident,coin=a.symbol.split('/')[0],full244=ident in ids,
                    variant=variant,original_trade_id=int(a.trade_id),original_entry_date=a.entry_date,
                    original_exit_date=a.exit_date,original_return_pct=a.ret_pct,
                    same_long_entry=b is not None,side_held_at_signal_close=int(alive.iloc[0].side) if len(alive) else 0,
                    earlier_exit=(bool(b.exit_idx<a.exit_idx) if b is not None else None),
                    actual_exit_reason=b.reason if b is not None else None,
                    actual_exit_date=b.exit_date if b is not None else None,
                    actual_trade_return_pct=b.ret_pct if b is not None else None))
    d=pd.DataFrame(rows);d.to_csv(out/'long-path-changes.csv.gz',index=False,compression='gzip')
    summaries=[]
    groups={'full244':d.loc[d.full244]}
    groups.update({c:d.loc[d.coin.eq(c)] for c in ['BTC','ETH','SOL','BNB','UNI','ARB','LIT','HYPE','ZEC']})
    for label,g in groups.items():
        for v,h in g.groupby('variant',sort=False):
            summaries.append(dict(cohort=label,variant=v,original_long_entries=len(h),
                same_long_entry=int(h.same_long_entry.sum()),
                original_entry_absent_with_short_at_signal=int((~h.same_long_entry&h.side_held_at_signal_close.eq(-1)).sum()),
                already_long_with_different_entry=int((~h.same_long_entry&h.side_held_at_signal_close.eq(1)).sum()),
                matched_entry_exited_earlier=int(h.earlier_exit.eq(True).sum()),
                matched_entry_earlier_reverse_exit=int((h.earlier_exit.eq(True)&h.actual_exit_reason.eq('reverse_signal')).sum())))
    pd.DataFrame(summaries).to_csv(out/'long-path-summary.csv',index=False)
    print(pd.DataFrame(summaries).to_string(index=False))


if __name__=='__main__':main()
