import tempfile
import unittest
from pathlib import Path

import pandas as pd

from trading_wfo import (
    Action,
    CategoricalParameter,
    CloseRequest,
    ExecutionConfig,
    Order,
    ResultSaveError,
    Side,
    SimulationResult,
    StrategyExecutionError,
    TPEOptimizer,
    TradingDataset,
    TradingSimulator,
)

from tests.test_simulator_run import make_data, make_params


class ErrorHandlingTest(unittest.TestCase):
    def test_rejects_empty_data(self):
        empty = make_data().iloc[:0]
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            TradingSimulator(make_params(), None, empty)

    def test_rejects_nan_and_infinite_prices(self):
        for value in [float("nan"), float("inf"), float("-inf")]:
            with self.subTest(value=value):
                data = make_data()
                data.loc[1, "bid"] = value
                with self.assertRaisesRegex(ValueError, "NaN or infinity"):
                    TradingSimulator(make_params(), None, data)

    def test_rejects_ask_below_bid(self):
        data = make_data()
        data.loc[1, "ask"] = data.loc[1, "bid"] - 0.01
        with self.assertRaisesRegex(ValueError, "ask price"):
            TradingSimulator(make_params(), None, data)

    def test_rejects_lot_below_user_minimum(self):
        simulator = TradingSimulator(
            make_params(),
            None,
            make_data(),
            execution_config=ExecutionConfig(minimum_lot_size=0.1),
        )
        with self.assertRaisesRegex(ValueError, "below minimum_lot_size"):
            simulator.run(
                lambda context: Action(orders=[Order(Side.LONG, 0.01)])
            )

    def test_insufficient_balance_is_returned_as_rejected_order(self):
        params = make_params()
        params["asset"]["balance"] = 1
        params["strategy_base"]["leverage"] = 1
        simulator = TradingSimulator(params, None, make_data())

        result = simulator.run(
            lambda context: Action(orders=[Order(Side.LONG, 1)])
        )

        self.assertGreater(result.metrics["rejected_order_count"], 0)
        self.assertEqual(result.rejected_orders[0]["reason"], "insufficient_margin")
        self.assertGreater(
            result.rejected_orders[0]["required_funds"],
            result.rejected_orders[0]["available_funds"],
        )

    def test_unknown_position_close_request_raises(self):
        simulator = TradingSimulator(make_params(), None, make_data())
        with self.assertRaisesRegex(ValueError, "unknown position_id"):
            simulator.run(
                lambda context: Action(
                    close_requests=[CloseRequest(position_id=999)]
                )
            )

    def test_rejects_data_shorter_than_lookback(self):
        params = make_params()
        params["strategy_base"]["lookback_bars"] = 4
        with self.assertRaisesRegex(ValueError, "insufficient rows"):
            TradingSimulator(params, None, make_data())

    def test_rejects_wfo_section_shorter_than_simulator_lookback(self):
        data = make_data()
        data["time"] = pd.date_range(
            "2026-01-01", periods=len(data), freq="1D"
        )
        dataset = TradingDataset.from_dataframe(
            data, optimization_period="2d", validation_period="1d"
        )
        optimization_data = next(dataset.windows()).optimization_data
        params = make_params()
        params["strategy_base"]["lookback_bars"] = 2

        with self.assertRaisesRegex(ValueError, "insufficient rows"):
            TradingSimulator(params, None, optimization_data)

    def test_all_constrained_trials_raise_clear_error(self):
        optimizer = TPEOptimizer(
            {"value": CategoricalParameter([1, 2])}, seed=1
        )
        with self.assertRaisesRegex(ValueError, "no feasible trials"):
            optimizer.optimize(
                lambda params: params["value"],
                parameter_constraints=[lambda params: False],
                n_trials=3,
            )

    def test_strategy_exception_contains_step_and_time(self):
        simulator = TradingSimulator(make_params(), None, make_data())

        def broken_strategy(context):
            raise RuntimeError("indicator failed")

        with self.assertRaises(StrategyExecutionError) as raised:
            simulator.run(broken_strategy)

        self.assertEqual(raised.exception.step_index, 0)
        self.assertIn("indicator failed", str(raised.exception))
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)

    def test_save_failure_contains_target_path(self):
        result = SimulationResult(metrics={"net_profit": 0})
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory) / "not_a_directory"
            blocker.write_text("file", encoding="utf-8")
            target = blocker / "result.json"
            with self.assertRaises(ResultSaveError) as raised:
                result.save_json(target)

        self.assertEqual(raised.exception.filepath, target)
        self.assertIn(str(target), str(raised.exception))


if __name__ == "__main__":
    unittest.main()
