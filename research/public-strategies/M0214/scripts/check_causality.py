"""HA seed/recursion, raw fills and future perturbation verification."""
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


def check(source):
    location = Path(__file__).parent/'run_replay.py'
    spec = importlib.util.spec_from_file_location('m0214', location)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    fixture = pd.DataFrame({'open':[10.,11.,12.], 'high':[12.,15.,14.], 'low':[9.,10.,8.], 'close':[11.,13.,10.]})
    hao,hac,*_ = engine.indicators(fixture)
    np.testing.assert_allclose(hao,[10.5,10.5,11.375])
    np.testing.assert_allclose(hac,[10.5,12.25,11.])
    flat = pd.DataFrame({key:[10.]*25 for key in ['open','high','low','close']})
    _,_,fast,slow,entry,leave = engine.indicators(flat)
    assert not entry.any() and leave[19:].all()
    assert fast[-1] == slow[-1] == 10
    frame = engine.load(source)
    report = {}
    rawfillchecks = 0
    for cutoff in ['2023-06-30','2024-06-30']:
        perturbed = frame.copy()
        mask = perturbed.date > cutoff
        for field in ['open','high','low','close']:
            perturbed.loc[mask,field] *= 7
        for name,fee,lag,bench in engine.CASES:
            nav,fills = engine.run(frame,fee,lag,bench)
            changed,changedfills = engine.run(perturbed,fee,lag,bench)
            pd.testing.assert_frame_equal(nav[nav.date<=cutoff],changed[changed.date<=cutoff])
            pd.testing.assert_frame_equal(fills[fills.date<=cutoff],changedfills[changedfills.date<=cutoff])
            prices = frame.set_index('date')['open']
            for trade in fills.itertuples():
                assert trade.price == prices.loc[trade.date]*(1.0002 if trade.side=='BUY' else .9998)
                rawfillchecks += 1
        report[cutoff] = 'PASS all five configurations: pre-cutoff NAV/fills unchanged'
    return dict(ha_seed_and_recursion='PASS manually calculated OHLC fixture',ma_equality_and_flat_ha='PASS no entries; nonbullish exit',raw_open_fill_checks=rawfillchecks,future_perturbation=report)


if __name__ == '__main__':
    print(json.dumps(check(Path(sys.argv[1])),indent=2))
