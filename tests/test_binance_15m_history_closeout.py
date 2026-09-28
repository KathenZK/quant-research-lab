import importlib.util
from pathlib import Path

import pandas as pd
import pytest

PATH = Path(__file__).resolve().parents[1] / 'research/platform/data-lake-governance/scripts/closeout_binance_15m_history_v3.py'
spec = importlib.util.spec_from_file_location('closeout_v3',PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    inventory = pd.DataFrame([{'symbol':'X/USDT:USDT','first_ts':'2026-01-01T00:00:00Z','last_ts':'2026-01-01T01:00:00Z','rows':4}])
    gaps = pd.DataFrame([{'symbol':'X/USDT:USDT','prev_ts':'2026-01-01T00:15:00Z','next_ts':'2026-01-01T00:45:00Z','missing_bars':1}])
    return inventory,gaps


def test_actual_segment_partition_and_crossing_rejection():
    inventory,gaps = fixture()
    segments = m.make_segments(inventory,gaps)
    assert len(segments)==2 and segments.rows.sum()==4
    assert m.assert_window_within_segment(segments,'X/USDT:USDT','2026-01-01T00:45:00Z','2026-01-01T01:15:00Z').endswith('#1')
    with pytest.raises(ValueError,match='crosses'):
        m.assert_window_within_segment(segments,'X/USDT:USDT','2026-01-01T00:15:00Z','2026-01-01T01:00:00Z')
    with pytest.raises(ValueError,match='off'):
        m.assert_window_within_segment(segments,'X/USDT:USDT','2026-01-01T00:46:00Z','2026-01-01T01:00:00Z')
    inventory.loc[0,'rows']=5
    with pytest.raises(ValueError,match='coverage'):
        m.make_segments(inventory,gaps)


def test_missing_or_inconsistent_boundary_evidence_fails_closed():
    _,gaps = fixture()
    with pytest.raises(ValueError,match='unclassified'):
        m.classify_boundaries(gaps,{'symbols':[]},{'boundaries':[]})
    evidence={'boundaries':[{'symbol':'X/USDT:USDT','launch_utc':'2026-01-01T00:45:00Z','evidence_kind':'FROZEN_EXCHANGE_INFO'}]}
    metadata={'symbols':[{'symbol':'XUSDT','onboardDate':0}]}
    with pytest.raises(ValueError,match='metadata'):
        m.classify_boundaries(gaps,metadata,evidence)
    metadata['symbols'][0]['onboardDate']=m.m.v2.as_ms('2026-01-01T00:45:00Z')
    result=m.classify_boundaries(gaps,metadata,evidence)
    assert result.resolution.tolist()==['EXCLUDED_LAUNCH_OR_RELAUNCH_BOUNDARY']
    assert not result.full_historical_calendar_verified.any()
