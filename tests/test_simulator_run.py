import unittest
import json
import tempfile
from pathlib import Path

import pandas as pd

from trading_wfo import (
    Action,
    CloseRequest,
    ExecutionConfig,
    Order,
    Side,
    TradingSimulator,
)


class DummyTradingLog:
    def add(self, entry):
        pass


def make_data():
    bid = [100.0, 110.0, 120.0, 130.0]
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=4, freq="5min"),
            "bid": bid,
            "ask": [price + 1.0 for price in bid],
            "open": bid,
            "high": [price + 2.0 for price in bid],
            "low": [price - 2.0 for price in bid],
            "close": [price + 0.5 for price in bid],
        }
    )


def make_params():
    return {
        "common": {
            "units_per_lot": 100,
            "symbol": "TEST",
            "price_per_pip": 1.0,
        },
        "strategy_base": {"lookback_bars": 1, "leverage": 10},
        "asset": {"balance": 10_000, "stop_out_level": 50},
    }


class OpenThenCloseStrategy:
    def __init__(self):
        self.calls = 0

    def on_bar(self, context):
        self.calls += 1
        if self.calls == 1:
            return Action(orders=[Order(side=Side.LONG, lot_size=0.01)])
        if self.calls == 2:
            return Action(close_requests=[CloseRequest(position_id=1)])
        return Action()


class OpenThenCloseShortStrategy:
    def __init__(self):
        self.calls = 0

    def on_bar(self, context):
        self.calls += 1
        if self.calls == 1:
            return Action(orders=[Order(side=Side.SHORT, lot_size=0.01)])
        if self.calls == 2:
            return Action(close_requests=[CloseRequest(position_id=1)])
        return Action()


class TradingSimulatorRunTest(unittest.TestCase):
    def test_live_backtest_result_is_available_during_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backtest.json"

            class ObservingStrategy(OpenThenCloseStrategy):
                saw_running_result = False

                def on_bar(self, context):
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    self.saw_running_result = payload["metrics"]["status"] == "running"
                    return super().on_bar(context)

            strategy = ObservingStrategy()
            result = TradingSimulator(
                make_params(), DummyTradingLog(), make_data()
            ).run(
                strategy,
                result_path=path,
                live_update_interval=999,
            )
            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertTrue(strategy.saw_running_result)
        self.assertEqual(saved["metrics"]["status"], "completed")
        self.assertEqual(saved["metrics"]["progress_pct"], 100)
        self.assertEqual(saved["trades"], result.trades)

    def test_closes_remaining_position_at_final_bid(self):
        class OpenOnceStrategy:
            def __init__(self):
                self.called = False

            def on_bar(self, context):
                if not self.called:
                    self.called = True
                    return Action(orders=[Order(side=Side.LONG, lot_size=0.01)])
                return Action()

        simulator = TradingSimulator(make_params(), DummyTradingLog(), make_data())
        result = simulator.run(OpenOnceStrategy())

        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0]["exit_reason"], "end_of_data")
        self.assertEqual(result.trades[0]["exit_price"], make_data().iloc[-1]["bid"])
        self.assertEqual(result.metrics["total_trades"], 1)
        self.assertEqual(simulator._portfolio.positions(), ())

    def test_executes_open_and_close_on_the_following_bar(self):
        data = make_data()
        simulator = TradingSimulator(make_params(), DummyTradingLog(), data)

        result = simulator.run(OpenThenCloseStrategy())

        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade["entry_price"], 121.0)
        self.assertEqual(trade["exit_price"], 130.0)
        self.assertEqual(trade["time"], data.loc[2, "time"].timestamp())
        self.assertEqual(trade["exit_time"], data.loc[3, "time"].timestamp())
        self.assertEqual(trade["realized_profit"], 9.0)
        self.assertEqual(result.metrics["final_balance"], 10_009.0)

    def test_does_not_execute_an_action_from_the_last_bar(self):
        data = make_data().iloc[:3]
        simulator = TradingSimulator(make_params(), DummyTradingLog(), data)

        simulator.run(
            lambda context: Action(
                orders=[Order(side=Side.LONG, lot_size=0.01)]
            ),
            close_positions_at_end=False,
        )

        self.assertEqual(len(simulator._portfolio.long_positions()), 1)

    def test_rejects_dict_actions_at_strategy_boundary(self):
        data = make_data().iloc[:3]
        simulator = TradingSimulator(make_params(), DummyTradingLog(), data)

        with self.assertRaisesRegex(TypeError, "return an Action"):
            simulator.run(lambda context: {"orders": []})

    def test_commission_and_slippage_are_applied_to_long_trade(self):
        simulator = TradingSimulator(
            make_params(),
            DummyTradingLog(),
            make_data(),
            execution_config=ExecutionConfig(
                commission_per_lot_per_side=100,
                slippage_pips=2,
            ),
        )

        result = simulator.run(OpenThenCloseStrategy())
        trade = result.trades[0]

        self.assertEqual(trade["entry_price"], 123.0)
        self.assertEqual(trade["exit_price"], 128.0)
        self.assertEqual(trade["gross_profit"], 5.0)
        self.assertEqual(trade["commission"], 2.0)
        self.assertEqual(trade["realized_profit"], 3.0)
        self.assertEqual(trade["realized_pips"], 5.0)
        self.assertEqual(result.metrics["total_commission"], 2.0)
        self.assertEqual(result.metrics["final_balance"], 10_003.0)

    def test_slippage_moves_short_execution_prices_against_trader(self):
        simulator = TradingSimulator(
            make_params(),
            None,
            make_data(),
            execution_config=ExecutionConfig(slippage_pips=2),
        )

        result = simulator.run(OpenThenCloseShortStrategy())
        trade = result.trades[0]

        self.assertEqual(trade["entry_price"], 118.0)
        self.assertEqual(trade["exit_price"], 133.0)
        self.assertEqual(trade["realized_pips"], -15.0)

    def test_execution_cost_defaults_are_zero_and_reject_negative_values(self):
        config = ExecutionConfig()
        self.assertEqual(config.commission_per_lot_per_side, 0.0)
        self.assertEqual(config.slippage_pips, 0.0)
        with self.assertRaisesRegex(ValueError, "commission"):
            ExecutionConfig(commission_per_lot_per_side=-1)
        with self.assertRaisesRegex(ValueError, "slippage"):
            ExecutionConfig(slippage_pips=-1)


if __name__ == "__main__":
    unittest.main()
