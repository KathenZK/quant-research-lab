"""Calendar reports inherit positions and assign boundary costs consistently."""
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts'))
from run_exit_state_history_20260910 import time_blocks


def test_calendar_costs_are_assigned_to_new_period_except_terminal_settlement():
    frame=pd.DataFrame({'timestamp':pd.to_datetime([
        '2020-01-01T00:00Z','2020-01-01T00:00Z','2021-01-01T00:00Z',
        '2021-01-01T00:00Z','2022-01-01T00:00Z','2022-01-01T00:00Z']),
        'equity':[10000,9990,11000,10990,12000,11990]})
    for unit in ['us','ns']:
        frame.timestamp=frame.timestamp.dt.as_unit(unit)
        rows={r['block']:r for r in time_blocks(frame,pd.Timestamp('2020-01-01T00:00Z'),pd.Timestamp('2022-01-01T00:00Z'))}
        assert rows['year_2020']['start_equity']==10000
        assert rows['year_2020']['end_equity']==11000
        assert rows['year_2021']['start_equity']==11000
        assert rows['year_2021']['end_equity']==11990
        assert rows['phase_2020_2021']['complete_coverage']
        assert not rows['cycle_2020_2024']['complete_coverage']
        assert rows['year_2022']['status']=='NO_OVERLAP'
        assert rows['year_2020']['max_drawdown_pct']<0
