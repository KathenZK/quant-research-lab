"""Future perturbation and hand computed indicator fixtures."""
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


def check(source):
    location = Path(__file__).parent/'run_replay.py'
    spec = importlib.util.spec_from_file_location('m0215', location)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    assert engine.rsi2(np.array([10.,10.,10.,10.]))[-1] == 50
    assert engine.rsi2(np.array([10.,11.,12.,13.]))[-1] == 100
    assert engine.rsi2(np.array([13.,12.,11.,10.]))[-1] == 0
    fixture = engine.rsi2(np.array([10.,12.,11.,9.]))
    np.testing.assert_allclose(fixture[2:], [200/3,200/7])
    frame = engine.load(source)
    report = {}
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
        report[cutoff] = 'PASS all five configurations: pre-cutoff NAV/fills unchanged'
    return dict(rsi_hand_fixtures='PASS four fixtures',future_perturbation=report)


if __name__ == '__main__':
    print(json.dumps(check(Path(sys.argv[1])),indent=2))
