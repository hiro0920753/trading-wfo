import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd

from trading_wfo import (Action, Order, OrderType, Side, CloseRequest,
    RobustnessConfig, StressScenario, WalkForwardRunner, TradingDataset,
    TradingSimulator, SimulationResult)
from trading_wfo.stress import (DelayedEntryStrategy, stress_quotes,
    period_performance, monte_carlo)
from test_wfo import FixedCustomOptimizer, OneTradeStrategy, make_data, PARAMS


class StressTest(unittest.TestCase):
    def test_validation(self):
        for kwargs in ({'name':'baseline'}, {'name':'x','spread_multiplier':float('nan')},
                       {'name':'x','entry_delay_bars':.5}, {'name':'x','parameter_offsets':{'a':float('inf')}}):
            with self.assertRaises(ValueError): StressScenario(**kwargs)
        with self.assertRaises(ValueError):
            RobustnessConfig(scenarios=[StressScenario('x'),StressScenario('x')])
        with self.assertRaises(ValueError): RobustnessConfig(monte_carlo_samples=-1)

    def test_historical_spread_mid_and_source_preserved(self):
        data=make_data(5); original=data.copy(deep=True)
        data.loc[2,'ask'] = data.loc[2,'bid']+.5
        expected=data.copy(deep=True)
        result=stress_quotes({'A':data},2)['A']
        np.testing.assert_allclose(result.ask-result.bid,2*(data.ask-data.bid))
        np.testing.assert_allclose(result.ask+result.bid,data.ask+data.bid)
        pd.testing.assert_frame_equal(result[['open','high','low','close']],data[['open','high','low','close']])
        pd.testing.assert_frame_equal(data,expected)
        pd.testing.assert_frame_equal(stress_quotes(original,1),original)

    def test_delay_executes_at_later_quote_without_duplicate_batch(self):
        q=make_data(6)
        s=DelayedEntryStrategy(OneTradeStrategy(.01),1)
        result=TradingSimulator(PARAMS,None,q).run(s)
        self.assertEqual(len(result.trades),1)
        self.assertAlmostEqual(result.trades[0]['entry_price'],q.ask.iloc[2])
        self.assertEqual(result.trades[0]['time'],q.time.iloc[2].timestamp())
        repeating=Mock()
        repeating.on_bar.return_value=Action(orders=[Order(Side.LONG,.01)])
        wrapped=DelayedEntryStrategy(repeating,1)
        self.assertEqual(wrapped.on_bar({'time':1}).orders,[])
        self.assertEqual(len(wrapped.on_bar({'time':2}).orders),1)
        self.assertEqual(wrapped.on_bar({'time':3}).orders,[])

    def test_delay_expiry_stop_and_unsupported_limit(self):
        s=Mock();s.on_bar.side_effect=[Action(orders=[Order(Side.LONG,.01,expires_at=2)]),Action()]
        d=DelayedEntryStrategy(s,1)
        d.on_bar({'time':1})
        self.assertEqual(d.on_bar({'time':2}).orders,[])
        s=Mock();s.on_bar.side_effect=[Action(orders=[Order(Side.LONG,.01)]),Action(stop_trading=True)]
        d=DelayedEntryStrategy(s,1);d.on_bar({'time':1})
        self.assertTrue(d.on_bar({'time':2}).stop_trading)
        self.assertIsNone(d.pending)
        s=Mock();s.on_bar.return_value=Action(orders=[Order(Side.LONG,.01,order_type=OrderType.LIMIT,limit_price=100)])
        with self.assertRaisesRegex(ValueError,'MARKET'):
            DelayedEntryStrategy(s,1).on_bar({'time':1})

    def test_calendar_and_reproducible_monte_carlo(self):
        result=SimulationResult(trades=[
            {'exit_time':pd.Timestamp('2025-12-31',tz='UTC').timestamp(),'realized_profit':10,'realized_pips':2},
            {'exit_time':pd.Timestamp('2026-01-01',tz='UTC').timestamp(),'realized_profit':-20,'realized_pips':-4}])
        self.assertEqual([x['net_profit'] for x in period_performance(result,'Y')],[10,-20])
        a=monte_carlo(result,100,7)
        self.assertEqual(a,monte_carlo(result,100,7))
        self.assertEqual(a['permutation']['total_profit_p05_p50_p95'],[-10]*3)
        self.assertEqual(monte_carlo(SimulationResult(),100,7),{})

    def test_wfo_no_reoptimization_and_export(self):
        optimizer=FixedCustomOptimizer()
        optimize=Mock(wraps=optimizer.optimize)
        optimizer.optimize=optimize
        kwargs=dict(simulator_factory=lambda data:TradingSimulator(PARAMS,None,data),
            strategy_factory=lambda params,model:OneTradeStrategy(params['lot_size']),optimizer=optimizer,n_trials=1)
        dataset=TradingDataset.from_dataframe(make_data(16),optimization_period='4d',validation_period='4d')
        baseline=WalkForwardRunner(**kwargs).run(dataset)
        optimize.reset_mock()
        result=WalkForwardRunner(**kwargs,robustness=RobustnessConfig(scenarios=(
            StressScenario('spread',spread_multiplier=2),StressScenario('delay',entry_delay_bars=1),
            StressScenario('offset',parameter_offsets={'lot_size':.01})),monte_carlo_samples=20)).run(dataset)
        self.assertEqual(optimize.call_count,len(result.windows))
        self.assertEqual(result.aggregate_metrics,baseline.aggregate_metrics)
        self.assertEqual(len(result.robustness_summary['scenarios']),4)
        for old,window in zip(baseline.windows,result.windows):
            self.assertEqual(window.best_params,old.best_params)
            self.assertEqual(window.validation_result.metrics,old.validation_result.metrics)
            rows=window.robustness_result['scenarios']
            self.assertEqual(len(rows),4)
            self.assertLess(rows[1]['delta_net_profit'],0)
            self.assertLess(rows[2]['delta_net_profit'],0)
            self.assertEqual(rows[3]['params']['lot_size'],.02)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'result.json';c=Path(td)/'result.csv'
            result.save_json(p);result.save_csv(c)
            saved=json.loads(p.read_text())
            self.assertIn('robustness_summary',saved)
            with c.open(newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
            self.assertEqual(sum(r['record_type']=='stress_scenario' for r in rows),12)


if __name__ == '__main__': unittest.main()
