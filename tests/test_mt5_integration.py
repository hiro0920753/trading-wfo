import json
import unittest
from pathlib import Path

import pandas as pd

from trading_wfo import (
    Action,
    CloseRequest,
    Order,
    Side,
    TradingSimulator,
    TradingDataset,
    DatasetMode,
)


DATA_DIRECTORY = Path(__file__).parents[1] / "mt5_data" / "USDJPY-" / "M15"


class DummyTradingLog:
    def add(self, entry):
        pass


class OpenThenCloseStrategy:
    def __init__(self, side=Side.LONG):
        self.calls = 0
        self.side = side
        self.contexts = []

    def on_bar(self, context):
        self.calls += 1
        self.contexts.append(context)
        if self.calls == 1:
            return Action(
                orders=[
                    Order(
                        side=self.side,
                        lot_size=0.01,
                        metadata={"source": "mt5_m15"},
                    )
                ]
            )
        if self.calls == 2:
            return Action(close_requests=[CloseRequest(position_id=1)])
        return Action()


@unittest.skipUnless(DATA_DIRECTORY.exists(), "local MT5 fixture is not available")
class Mt5IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = sorted(DATA_DIRECTORY.glob("*.csv"))
        cls.data = pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)

    def test_m15_data_quality(self):
        times = pd.to_datetime(self.data["time"], utc=True)

        self.assertGreater(len(self.data), 1000)
        self.assertFalse(times.duplicated().any())
        self.assertTrue(times.is_monotonic_increasing)
        self.assertFalse(self.data.isna().any().any())
        self.assertTrue((self.data["bid"] <= self.data["ask"]).all())
        self.assertEqual(times.diff().dropna().min(), pd.Timedelta(minutes=15))

    def test_builds_time_based_windows_directly_from_mt5_csv(self):
        dataset = TradingDataset.from_csv(
            DATA_DIRECTORY,
            training_period="2w",
            optimization_period="2w",
            validation_period="1w",
        )

        windows = list(dataset)
        first = windows[0]

        self.assertGreater(len(windows), 1)
        self.assertEqual(first.training_start, pd.Timestamp("2026-06-01", tz="UTC"))
        self.assertEqual(first.optimization_start, pd.Timestamp("2026-06-15", tz="UTC"))
        self.assertEqual(first.validation_start, pd.Timestamp("2026-06-29", tz="UTC"))
        self.assertEqual(first.validation_end, pd.Timestamp("2026-07-06", tz="UTC"))
        self.assertLess(first.training_data["time"].max(), first.optimization_start)
        self.assertLess(first.optimization_data["time"].max(), first.validation_start)
        self.assertLess(first.validation_data["time"].max(), first.validation_end)

    def test_full_and_latest_month_backtest_data_from_mt5_csv(self):
        full_dataset = TradingDataset.from_csv(DATA_DIRECTORY)
        month_dataset = TradingDataset.from_csv(
            DATA_DIRECTORY, backtest_period="1mo"
        )

        self.assertIs(full_dataset.mode, DatasetMode.BACKTEST)
        self.assertEqual(len(full_dataset.backtest_data), 4_320)
        self.assertEqual(str(full_dataset.backtest_data["time"].dt.tz), "UTC")
        self.assertEqual(
            month_dataset.backtest_data["time"].min(),
            pd.Timestamp("2026-07-01", tz="UTC"),
        )
        self.assertEqual(
            month_dataset.backtest_data["time"].max(),
            pd.Timestamp("2026-07-31 23:45:00", tz="UTC"),
        )
        self.assertEqual(len(month_dataset.backtest_data), 2_208)

    def test_mt5_backtest_data_runs_directly_in_simulator(self):
        dataset = TradingDataset.from_csv(
            DATA_DIRECTORY, backtest_period="1mo"
        )
        simulator = TradingSimulator(
            self._params(), DummyTradingLog(), dataset.backtest_data
        )

        result = simulator.run(lambda context: Action())

        self.assertEqual(
            result.metrics["steps_processed"],
            len(dataset.backtest_data) - 10,
        )

    def test_uses_previous_confirmed_bar_and_current_mt5_quote(self):
        params = {
            "common": {
                "units_per_lot": 100_000,
                "symbol": "USDJPY-",
                "price_per_pip": 0.01,
            },
            "strategy_base": {"lookback_bars": 10, "leverage": 25},
            "asset": {"balance": 10_000, "stop_out_level": 50},
        }
        simulator = TradingSimulator(params, DummyTradingLog(), self.data)
        strategy = OpenThenCloseStrategy()

        result = simulator.run(strategy)

        trade = result.trades[0]
        first_context = strategy.contexts[0]
        self.assertEqual(
            first_context["bars"].iloc[-1]["time"],
            pd.Timestamp(self.data.iloc[9]["time"]),
        )
        self.assertEqual(first_context["bid"], self.data.iloc[10]["bid"])
        self.assertEqual(first_context["ask"], self.data.iloc[10]["ask"])
        self.assertEqual(trade["entry_price"], self.data.iloc[10]["ask"])
        self.assertEqual(trade["exit_price"], self.data.iloc[11]["bid"])
        self.assertEqual(trade["exit_time"] - trade["time"], 15 * 60)
        self.assertEqual(len(result.equity_curve), len(self.data) - 10)
        json.dumps(result.trades)
        json.dumps(result.equity_curve)

    def test_long_prices_equity_balance_profit_and_pips(self):
        params = self._params()
        strategy = OpenThenCloseStrategy(Side.LONG)
        simulator = TradingSimulator(params, DummyTradingLog(), self.data)

        result = simulator.run(strategy)

        entry_bid = float(self.data.iloc[10]["bid"])
        entry_ask = float(self.data.iloc[10]["ask"])
        exit_bid = float(self.data.iloc[11]["bid"])
        expected_profit = (exit_bid - entry_ask) * 0.01 * 100_000
        expected_pips = (exit_bid - entry_ask) / 0.01
        expected_entry_equity = 10_000 + (entry_bid - entry_ask) * 0.01 * 100_000

        self.assertEqual(result.trades[0]["entry_price"], entry_ask)
        self.assertEqual(result.trades[0]["exit_price"], exit_bid)
        self.assertAlmostEqual(result.trades[0]["realized_profit"], expected_profit)
        self.assertAlmostEqual(result.equity_curve[0]["balance"], 10_000)
        self.assertAlmostEqual(result.equity_curve[0]["equity"], expected_entry_equity)
        self.assertAlmostEqual(result.equity_curve[1]["balance"], 10_000 + expected_profit)
        self.assertAlmostEqual(result.equity_curve[1]["equity"], 10_000 + expected_profit)
        self.assertAlmostEqual(result.metrics["realized_profit"], expected_profit)
        self.assertAlmostEqual(result.metrics["realized_pips"], expected_pips)
        self.assertAlmostEqual(result.metrics["final_balance"], 10_000 + expected_profit)
        self.assertAlmostEqual(result.metrics["final_equity"], 10_000 + expected_profit)

    def test_short_prices_equity_balance_profit_and_pips(self):
        params = self._params()
        strategy = OpenThenCloseStrategy(Side.SHORT)
        simulator = TradingSimulator(params, DummyTradingLog(), self.data)

        result = simulator.run(strategy)

        entry_bid = float(self.data.iloc[10]["bid"])
        entry_ask = float(self.data.iloc[10]["ask"])
        exit_ask = float(self.data.iloc[11]["ask"])
        expected_profit = (entry_bid - exit_ask) * 0.01 * 100_000
        expected_pips = (entry_bid - exit_ask) / 0.01
        expected_entry_equity = 10_000 + (entry_bid - entry_ask) * 0.01 * 100_000

        self.assertEqual(result.trades[0]["entry_price"], entry_bid)
        self.assertEqual(result.trades[0]["exit_price"], exit_ask)
        self.assertAlmostEqual(result.trades[0]["realized_profit"], expected_profit)
        self.assertAlmostEqual(result.equity_curve[0]["balance"], 10_000)
        self.assertAlmostEqual(result.equity_curve[0]["equity"], expected_entry_equity)
        self.assertAlmostEqual(result.equity_curve[1]["balance"], 10_000 + expected_profit)
        self.assertAlmostEqual(result.equity_curve[1]["equity"], 10_000 + expected_profit)
        self.assertAlmostEqual(result.metrics["realized_profit"], expected_profit)
        self.assertAlmostEqual(result.metrics["realized_pips"], expected_pips)
        self.assertAlmostEqual(result.metrics["final_balance"], 10_000 + expected_profit)
        self.assertAlmostEqual(result.metrics["final_equity"], 10_000 + expected_profit)

    @staticmethod
    def _params():
        return {
            "common": {
                "units_per_lot": 100_000,
                "symbol": "USDJPY-",
                "price_per_pip": 0.01,
            },
            "strategy_base": {"lookback_bars": 10, "leverage": 25},
            "asset": {"balance": 10_000, "stop_out_level": 50},
        }


if __name__ == "__main__":
    unittest.main()
