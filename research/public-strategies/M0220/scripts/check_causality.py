"""Weekly boundaries, no incomplete week leak, stop fixtures and future tests."""
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


def check(source):
    spec = importlib.util.spec_from_file_location('m0220',Path(__file__).parent/'run_replay.py')
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    assert engine.ratchet(None,100,10,False)==90
    assert engine.ratchet(None,100,10,True)==98
    assert engine.ratchet(99,100,10,True)==99
    assert engine.ratchet(99,90,10,False)==99
    frame = engine.load(source)
    values = engine.indicators(frame)
    ix = frame.index[frame.date=='2023-04-24'][0]
    assert values['weekly_count'][ix]==20 and values['weekly_count'][ix-1]==19
    week = frame.date.between('2023-04-24','2023-04-30')
    assert len(set(values['weekly_ema'][week]))==1
    # Later days in current week must not change EMA available to any day of it.
    changed = frame.copy()
    mask = changed.date.between('2023-04-26','2023-04-30')
    changed.loc[mask,'close'] *= 9
    shifted = engine.indicators(changed)
    np.testing.assert_array_equal(values['weekly_ema'][week],shifted['weekly_ema'][week])
    assert values['weekly_ema'][ix+7]!=shifted['weekly_ema'][ix+7]
    prefix = frame[frame.date<='2023-04-26'].copy()
    truncated = engine.indicators(prefix)
    np.testing.assert_allclose(truncated['weekly_ema'],values['weekly_ema'][:len(prefix)],equal_nan=True)
    reports = {}
    fills_checked = 0
    for cutoff in ['2023-09-30','2024-06-30']:
        future = frame.copy()
        for col in ['open','high','low','close']:
            future.loc[future.date>cutoff,col] *= 7
        for name,fee,lag,bench in engine.CASES:
            nav,trades = engine.run(frame,fee,lag,bench)
            nav2,trades2 = engine.run(future,fee,lag,bench)
            pd.testing.assert_frame_equal(nav[nav.date<=cutoff],nav2[nav2.date<=cutoff])
            pd.testing.assert_frame_equal(trades[trades.date<=cutoff],trades2[trades2.date<=cutoff])
            raw = frame.set_index('date').open
            for t in trades.itertuples():
                assert t.price==raw.loc[t.date]*(1.0002 if t.side=='BUY' else .9998)
                fills_checked += 1
        reports[cutoff]='PASS all five configurations'
    return dict(stop_ratchet_and_prior_caution_fixtures='PASS 4 hand cases',weekly_twentieth_boundary='PASS Sunday19 Monday20',incomplete_week_future_leak='PASS unchanged current week; changed next week only',truncated_incomplete_week='PASS',future_perturbation=reports,raw_open_fills_checked=fills_checked)


if __name__=='__main__':
    print(json.dumps(check(Path(sys.argv[1])),indent=2))
