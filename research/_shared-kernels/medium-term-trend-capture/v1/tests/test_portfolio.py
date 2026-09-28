"""资金再利用、共同候选及中断资金占用的合成场景检查。"""
import sys
from pathlib import Path
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio import simulate_portfolio, portfolio_metrics
from inference import paired_statistics


def path_row(day, value=1., release=False, gap=False, qty=.5, cash=.5, entry=False):
    return dict(ts=pd.Timestamp(day, tz='UTC'), open_before=value, open_after=value, close_value=value,
                cash_open_before=cash, cash_open_after=cash, cash_close=cash,
                qty_open_before=qty, qty_open_after=qty, qty_close=qty,
                release_open=release, entry_open=entry, exit_open=release and qty>0,
                fee_open=0., slippage_open=0., carry_close=0., data_gap=gap,
                intraday_low_value=value, reason='test')


class PortfolioScenarios(unittest.TestCase):
    def setUp(self):
        self.config = dict(start='2020-01-01T00:00:00Z', end='2020-01-05T00:00:00Z',
                           initial_equity=10000., budget_fraction=.1, max_slots=1, recent_days=[1, 2])

    def origins(self, dates=('2020-01-01', '2020-01-02'), symbols=('X', 'Y')):
        return pd.DataFrame([dict(origin_id=str(i), symbol=s, origin_ts=pd.Timestamp(d,tz='UTC'),
                                  liquidity=100-i) for i,(d,s) in enumerate(zip(dates,symbols))])

    def test_exit_releases_money_before_next_admission(self):
        paths = {'0':pd.DataFrame([path_row('2020-01-02',1.1,entry=True),path_row('2020-01-03',1.2,release=True)]),
                 '1':pd.DataFrame([path_row('2020-01-03',entry=True),path_row('2020-01-04',release=True)])}
        daily, acts = simulate_portfolio(self.origins(),paths,'A','base',self.config)
        admissions = acts[acts.event.eq('ADMIT')]
        self.assertEqual(len(admissions),2)
        self.assertAlmostEqual(admissions.budget.iloc[0],1000.)
        self.assertAlmostEqual(admissions.budget.iloc[1],1020.)
        self.assertAlmostEqual(daily.equity.iloc[-1],10200.)
        self.assertEqual(daily.active_slots.max(),1)
        m=portfolio_metrics(daily,acts,self.config)
        self.assertAlmostEqual(m['recent']['2']['return_'],10200/10100-1)

    def test_admission_does_not_pick_future_winner(self):
        roots = self.origins(dates=('2020-01-01','2020-01-01'))
        paths = {'0':pd.DataFrame([path_row('2020-01-02',.5,entry=True),path_row('2020-01-03',.5,release=True)]),
                 '1':pd.DataFrame([path_row('2020-01-02',10.,entry=True),path_row('2020-01-03',10.,release=True)])}
        _, acts = simulate_portfolio(roots,paths,'A','base',self.config)
        self.assertEqual(acts.loc[acts.event.eq('ADMIT'),'origin_id'].tolist(),['0'])
        self.assertEqual(acts.loc[acts.event.eq('REJECT'),'reason'].tolist(),['SLOTS_FULL'])

    def test_gap_keeps_funds_and_blocks_symbol(self):
        paths = {'0':pd.DataFrame([path_row('2020-01-02',entry=True),path_row('2020-01-03',gap=True)]),
                 '1':pd.DataFrame([path_row('2020-01-03',entry=True)])}
        daily, acts = simulate_portfolio(self.origins(symbols=('X','X')),paths,'B','base',self.config)
        self.assertEqual(daily.unresolved_positions.iloc[-1],1)
        self.assertEqual(daily.free_cash.iloc[-1],9000.)
        self.assertEqual(daily.unresolved_zero_value_equity.iloc[-1],9500.)
        self.assertIn('SYMBOL_DATA_UNRESOLVED',acts.reason.dropna().tolist())

    def test_waiting_money_is_reserved_then_released(self):
        paths = {'0':pd.DataFrame([path_row('2020-01-02',qty=0,cash=1),
                                   path_row('2020-01-03',qty=0,cash=1,release=True)]),
                 '1':pd.DataFrame([path_row('2020-01-03',qty=0,cash=1),
                                   path_row('2020-01-04',qty=0,cash=1,release=True)])}
        daily, acts = simulate_portfolio(self.origins(),paths,'C','base',self.config)
        self.assertEqual(daily.equity.iloc[-1],10000.)
        self.assertEqual(daily.positions.max(),0)
        self.assertEqual(len(acts[acts.event.eq('ADMIT')]),2)

    def test_cash_shortfall_is_explicit(self):
        paths={'0':pd.DataFrame([path_row('2020-01-02',cash=-20,qty=21,entry=True)])}
        daily,_ = simulate_portfolio(self.origins().iloc[:1],paths,'B','stress',self.config)
        self.assertTrue(daily.cost_cash_shortfall.any())

    def test_known_slot_cash_debt_is_not_spent_twice(self):
        cfg=dict(self.config,initial_equity=100.,budget_fraction=.8,max_slots=2)
        paths={'0':pd.DataFrame([path_row('2020-01-02',cash=-.1,qty=1.1,entry=True),
                                 path_row('2020-01-03',cash=-.1,qty=1.1)]),
               '1':pd.DataFrame([path_row('2020-01-03',entry=True)])}
        _,acts=simulate_portfolio(self.origins(),paths,'B','stress',cfg)
        allocations=acts.loc[acts.event.eq('ADMIT'),'budget'].tolist()
        self.assertEqual(allocations,[80.,12.])


class PairedInference(unittest.TestCase):
    def test_identical_policies_have_zero_increment(self):
        cfg=dict(start='2020-01-01T00:00:00Z',end='2020-05-01T00:00:00Z',
                 bootstrap=dict(blocks=[20,40],seed=20260909,repetitions=1000,confidence=.95))
        dates=pd.date_range(cfg['start'], periods=100)
        vals=[.01 if i%2 else -.003 for i in range(100)]
        frame=pd.DataFrame(dict(origin_ts=dates,A=vals,B=vals,C=vals))
        result=paired_statistics(frame,cfg)
        self.assertEqual(result['points'][3:],[0.,0.])
        for lo,hi in zip(result['lower'][3:],result['upper'][3:]):
            self.assertAlmostEqual(lo,0.,places=12)
            self.assertAlmostEqual(hi,0.,places=12)
        self.assertTrue(result['lower'][0] <= result['points'][0] <= result['upper'][0])


if __name__ == '__main__':
    unittest.main()
