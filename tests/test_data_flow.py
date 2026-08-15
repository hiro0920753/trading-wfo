import unittest

import pandas as pd

from trading_wfo import (
    Action,
    DatasetMode,
    TradingDataset,
    TradingSimulator,
    WindowPeriod,
)


class DummyTradingLog:
    def add(self, entry):
        pass


def make_bars(size=10, frequency="5min"):
    times = pd.date_range("2026-01-01", periods=size, freq=frequency)
    prices = [100.0 + index for index in range(size)]
    return pd.DataFrame(
        {
            "time": times,
            "bid": prices,
            "ask": [price + 0.1 for price in prices],
            "open": prices,
            "high": [price + 1.0 for price in prices],
            "low": [price - 1.0 for price in prices],
            "close": [price + 0.5 for price in prices],
            "signal": list(range(size)),
        }
    )


class TradingDatasetTest(unittest.TestCase):
    def test_no_periods_uses_all_data_for_backtest(self):
        data = make_bars(size=20, frequency="1D")
        dataset = TradingDataset.from_dataframe(data)

        self.assertIs(dataset.mode, DatasetMode.BACKTEST)
        pd.testing.assert_frame_equal(dataset.backtest_data, dataset.data)

    def test_backtest_period_uses_latest_calendar_month(self):
        data = make_bars(size=100, frequency="1D")
        dataset = TradingDataset.from_dataframe(data, backtest_period="1mo")

        self.assertEqual(dataset.backtest_data["time"].min(), pd.Timestamp("2026-03-11"))
        self.assertEqual(dataset.backtest_data["time"].max(), pd.Timestamp("2026-04-10"))

    def test_backtest_mode_does_not_generate_windows(self):
        dataset = TradingDataset.from_dataframe(make_bars(size=20))

        with self.assertRaisesRegex(RuntimeError, "walk-forward mode"):
            list(dataset.windows())

    def test_walk_forward_mode_does_not_expose_backtest_data(self):
        dataset = TradingDataset.from_dataframe(
            make_bars(size=20, frequency="1D"),
            optimization_period="10d",
            validation_period="5d",
        )

        self.assertIs(dataset.mode, DatasetMode.WALK_FORWARD)
        with self.assertRaisesRegex(RuntimeError, "backtest mode"):
            _ = dataset.backtest_data

    def test_training_period_without_optimization_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "requires optimization_period"):
            TradingDataset.from_dataframe(
                make_bars(size=20, frequency="1D"),
                training_period="5d",
            )

    def test_backtest_and_walk_forward_periods_cannot_be_combined(self):
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            TradingDataset.from_dataframe(
                make_bars(size=20, frequency="1D"),
                backtest_period="10d",
                optimization_period="5d",
                validation_period="5d",
            )

    def test_splits_training_optimization_and_validation_by_time(self):
        data = make_bars(size=40, frequency="1D")
        dataset = TradingDataset.from_dataframe(
            data,
            training_period="5d",
            optimization_period="10d",
            validation_period="5d",
        )

        windows = list(dataset)

        self.assertEqual(len(windows), 5)
        self.assertEqual(windows[0].training_data["signal"].tolist(), list(range(5)))
        self.assertEqual(windows[0].optimization_data["signal"].tolist(), list(range(5, 15)))
        self.assertEqual(windows[0].validation_data["signal"].tolist(), list(range(15, 20)))
        self.assertEqual(windows[1].training_data["signal"].tolist(), list(range(5, 10)))
        self.assertEqual(windows[1].validation_data["signal"].tolist(), list(range(20, 25)))

    def test_training_period_is_optional(self):
        dataset = TradingDataset.from_dataframe(
            make_bars(size=20, frequency="1D"),
            optimization_period="10d",
            validation_period="5d",
        )

        window = next(iter(dataset))

        self.assertIsNone(window.training_data)
        self.assertEqual(window.optimization_data["signal"].tolist(), list(range(10)))
        self.assertEqual(window.validation_data["signal"].tolist(), list(range(10, 15)))

    def test_warmup_bars_are_prepended_without_changing_window_dates(self):
        dataset = TradingDataset.from_dataframe(
            make_bars(size=20, frequency="1D"),
            optimization_period="10d",
            validation_period="5d",
            warmup_bars=3,
        )

        window = next(iter(dataset))

        self.assertEqual(window.optimization_data["signal"].tolist(), list(range(10)))
        self.assertEqual(window.validation_data["signal"].tolist(), list(range(7, 15)))
        self.assertEqual(window.validation_start, pd.Timestamp("2026-01-11"))

    def test_negative_warmup_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "warmup_bars"):
            TradingDataset.from_dataframe(make_bars(), warmup_bars=-1)

    def test_warns_when_validation_windows_overlap(self):
        dataset = TradingDataset.from_dataframe(
            make_bars(size=30, frequency="1D"),
            optimization_period="10d",
            validation_period="5d",
            step_period="2d",
        )

        with self.assertWarnsRegex(UserWarning, "overlap"):
            list(dataset)

    def test_warns_when_validation_windows_have_gaps(self):
        dataset = TradingDataset.from_dataframe(
            make_bars(size=40, frequency="1D"),
            optimization_period="10d",
            validation_period="5d",
            step_period="7d",
        )

        with self.assertWarnsRegex(UserWarning, "gaps"):
            list(dataset)

    def test_calendar_month_is_not_treated_as_thirty_days(self):
        data = make_bars(size=100, frequency="1D")
        dataset = TradingDataset.from_dataframe(
            data,
            training_period="1mo",
            optimization_period="1mo",
            validation_period="1mo",
        )

        window = next(iter(dataset))

        self.assertEqual(window.training_start, pd.Timestamp("2026-01-01"))
        self.assertEqual(window.optimization_start, pd.Timestamp("2026-02-01"))
        self.assertEqual(window.validation_start, pd.Timestamp("2026-03-01"))
        self.assertEqual(window.validation_end, pd.Timestamp("2026-04-01"))

    def test_period_units_are_unambiguous(self):
        self.assertEqual(WindowPeriod.parse("30min").unit, "min")
        self.assertEqual(WindowPeriod.parse("3mo").unit, "mo")
        with self.assertRaises(ValueError):
            WindowPeriod.parse("3m")


class TradingSimulatorDataTest(unittest.TestCase):
    def setUp(self):
        self.params = {
            "common": {
                "units_per_lot": 100_000,
                "symbol": "TEST",
                "price_per_pip": 0.01,
            },
            "strategy_base": {
                "lookback_bars": 2,
                "leverage": 25,
            },
            "asset": {"balance": 10_000},
        }

    def test_uses_supplied_timeframe_without_resampling(self):
        data = make_bars(size=5, frequency="15min")
        simulator = TradingSimulator(self.params, DummyTradingLog(), data)

        self.assertEqual(len(simulator._data), 5)
        self.assertEqual(
            simulator._data["time"].diff().dropna().unique().tolist(),
            [pd.Timedelta(minutes=15)],
        )
        self.assertEqual(simulator._step_count, 3)

    def test_simulator_receives_one_window_and_preserves_user_columns(self):
        data = make_bars(size=8)
        window = next(iter(TradingDataset.from_dataframe(
            data,
            optimization_period="20min",
            validation_period="15min",
        )))
        simulator = TradingSimulator(
            self.params, DummyTradingLog(), window.validation_data
        )

        contexts = []
        simulator.run(lambda context: contexts.append(context) or Action())
        info = contexts[0]

        self.assertEqual(len(simulator._data), 3)
        self.assertEqual(info["row"]["signal"], 5)
        self.assertEqual(info["bars"].iloc[-1]["signal"], 5)
        self.assertEqual(info["bid"], data.iloc[6]["bid"])

    def test_warmup_makes_first_simulated_quote_equal_validation_start(self):
        data = make_bars(size=8)
        window = next(iter(TradingDataset.from_dataframe(
            data,
            optimization_period="20min",
            validation_period="15min",
            warmup_bars=2,
        )))
        simulator = TradingSimulator(
            self.params, DummyTradingLog(), window.validation_data
        )
        contexts = []

        simulator.run(lambda context: contexts.append(context) or Action())

        self.assertEqual(pd.Timestamp(contexts[0]["time"], unit="s"), window.validation_start)
        self.assertEqual(contexts[0]["row"]["signal"], 3)
        self.assertEqual(contexts[0]["bid"], data.iloc[4]["bid"])

    def test_rejects_unsorted_data_instead_of_reordering_it(self):
        data = make_bars(size=4).iloc[::-1]

        with self.assertRaisesRegex(ValueError, "sorted by time"):
            TradingSimulator(self.params, DummyTradingLog(), data)


if __name__ == "__main__":
    unittest.main()
