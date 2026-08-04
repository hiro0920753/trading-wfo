import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from trading_wfo import (
    Action,
    CategoricalParameter,
    CLIProgress,
    ConstraintResult,
    Order,
    Side,
    ObjectiveResult,
    OptimizationResult,
    OptimizationTrial,
    ProgressTracker,
    TPEOptimizer,
    TradingDataset,
    TradingSimulator,
    WalkForwardRunner,
)


class DummyTradingLog:
    def add(self, entry):
        pass


def make_data(size=14):
    prices = [100.0 + index for index in range(size)]
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=size, freq="1D"),
            "bid": prices,
            "ask": [price + 0.1 for price in prices],
            "open": prices,
            "high": [price + 1 for price in prices],
            "low": [price - 1 for price in prices],
            "close": prices,
        }
    )


PARAMS = {
    "common": {
        "units_per_lot": 100,
        "symbol": "TEST",
        "price_per_pip": 1,
    },
    "strategy_base": {"lookback_bars": 1, "leverage": 10},
    "asset": {"balance": 10_000},
}


class OneTradeStrategy:
    def __init__(self, lot_size, model=None):
        self.lot_size = lot_size
        self.model = model
        self.calls = 0

    def on_bar(self, context):
        self.calls += 1
        if self.calls == 1:
            return Action(
                orders=[Order(side=Side.LONG, lot_size=self.lot_size)]
            )
        return Action()


class RecordingTrainer:
    def __init__(self):
        self.training_ranges = []

    def fit(self, data):
        time_range = (data["time"].min(), data["time"].max())
        self.training_ranges.append(time_range)
        return {"training_end": time_range[1]}


class FixedCustomOptimizer:
    def __init__(self):
        self.received_constraints = None

    def optimize(
        self, objective, *, n_trials=50, parameter_constraints=(), progress=None
    ):
        self.received_constraints = tuple(parameter_constraints)
        outcome = objective({"lot_size": 0.01})
        if not isinstance(outcome, ObjectiveResult):
            raise AssertionError("runner must return ObjectiveResult")
        return OptimizationResult(
            best_params={"lot_size": 0.01},
            best_score=outcome.score,
            trials=[
                OptimizationTrial(
                    number=0,
                    params={"lot_size": 0.01},
                    score=outcome.score,
                    metrics=outcome.metrics,
                )
            ],
        )


class WalkForwardRunnerTest(unittest.TestCase):
    def make_runner(
        self, trainer=None, progress=False, parameter_variations=None
    ):
        return WalkForwardRunner(
            simulator_factory=lambda data: TradingSimulator(
                PARAMS, DummyTradingLog(), data
            ),
            strategy_factory=lambda params, model: OneTradeStrategy(
                params["lot_size"], model
            ),
            optimizer=TPEOptimizer(
                {"lot_size": CategoricalParameter([0.01, 0.02])},
                seed=4,
                n_startup_trials=2,
            ),
            trainer=trainer,
            n_trials=6,
            progress=progress,
            parameter_variations=parameter_variations,
        )

    def test_optimizes_then_validates_each_window(self):
        dataset = TradingDataset.from_dataframe(
            make_data(16),
            optimization_period="4d",
            validation_period="4d",
        )

        result = self.make_runner().run(dataset)

        self.assertEqual(len(result.windows), 3)
        self.assertEqual(result.aggregate_metrics["window_count"], 3)
        self.assertEqual(result.aggregate_metrics["optimization_trial_count"], 18)
        self.assertGreater(result.aggregate_metrics["net_profit"], 0)
        for window in result.windows:
            self.assertEqual(window.best_params["lot_size"], 0.02)
            self.assertGreater(window.validation_result.metrics["net_profit"], 0)
            self.assertLess(window.optimization_start, window.optimization_end)
            self.assertLess(window.validation_start, window.validation_end)

    def test_saves_nested_json_and_rowlogger_csv(self):
        dataset = TradingDataset.from_dataframe(
            make_data(16), optimization_period="4d", validation_period="4d"
        )
        result = self.make_runner().run(dataset)

        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "nested" / "result.json"
            csv_path = Path(directory) / "nested" / "result.csv"
            result.save_json(json_path)
            result.save_csv(csv_path)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            with csv_path.open(encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(payload["aggregate_metrics"]["window_count"], 3)
        self.assertEqual(len(payload["windows"][0]["optimization_result"]["trials"]), 6)
        self.assertEqual(rows[0]["record_type"], "summary")
        self.assertEqual(
            len([row for row in rows if row["record_type"] == "window"]), 3
        )
        self.assertEqual(
            len([row for row in rows if row["record_type"] == "trial"]), 18
        )
        first_window = next(row for row in rows if row["record_type"] == "window")
        self.assertTrue(first_window["validation_start"])

    def test_cli_progress_reports_windows_and_trials(self):
        output = io.StringIO()
        dataset = TradingDataset.from_dataframe(
            make_data(8), optimization_period="4d", validation_period="4d"
        )

        self.make_runner(progress=CLIProgress(output)).run(dataset)

        text = output.getvalue()
        self.assertIn("[WFO] Starting 1 window(s)", text)
        self.assertIn("[TPE] Trial 1/6", text)
        self.assertIn("[WFO] Completed 1 window(s)", text)

    def test_writes_dashboard_progress_and_keeps_windows_sequential(self):
        dataset = TradingDataset.from_dataframe(
            make_data(16), optimization_period="4d", validation_period="4d"
        )
        with tempfile.TemporaryDirectory() as directory:
            progress_path = Path(directory) / "run.progress.json"
            runner = WalkForwardRunner(
                simulator_factory=lambda data: TradingSimulator(PARAMS, DummyTradingLog(), data),
                strategy_factory=lambda params, model: OneTradeStrategy(params["lot_size"], model),
                optimizer=TPEOptimizer(
                    {"lot_size": CategoricalParameter([0.01, 0.02])}, seed=4,
                    n_startup_trials=2,
                ),
                n_trials=6, optimization_workers=2, progress_path=progress_path,
            )
            result = runner.run(dataset)
            progress = json.loads(progress_path.read_text(encoding="utf-8"))

        self.assertEqual([window.index for window in result.windows], [0, 1, 2])
        self.assertEqual(progress["status"], "completed")
        self.assertEqual(progress["completed_windows"], 3)
        self.assertEqual(progress["completed_trials_all_windows"], 18)
        self.assertEqual(progress["optimization_workers"], 2)
        self.assertEqual(progress["estimated_remaining_seconds"], 0)

    def test_result_constraints_reject_trials_and_are_saved(self):
        dataset = TradingDataset.from_dataframe(
            make_data(16), optimization_period="4d", validation_period="4d"
        )
        runner = WalkForwardRunner(
            simulator_factory=lambda data: TradingSimulator(PARAMS, None, data),
            strategy_factory=lambda params, model: OneTradeStrategy(params["lot_size"]),
            optimizer=TPEOptimizer(
                {"lot_size": CategoricalParameter([0.01, 0.02])},
                seed=4,
                n_startup_trials=2,
            ),
            result_constraints=[
                lambda result: (
                    None
                    if result.metrics["net_profit"] >= 1
                    else "net_profit must be at least 1"
                )
            ],
            n_trials=6,
        )

        result = runner.run(dataset)

        rejected = [
            trial
            for trial in result.windows[0].optimization_result.trials
            if not trial.feasible
        ]
        self.assertTrue(rejected)
        self.assertEqual(rejected[0].status, "result_constraint_failed")
        self.assertIn("net_profit must be at least 1", rejected[0].violations)
        self.assertTrue(result.windows[0].validation_constraint_result.feasible)

        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "constrained.json"
            csv_path = Path(directory) / "constrained.csv"
            result.save_json(json_path)
            result.save_csv(csv_path)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            with csv_path.open(encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))

        saved_trials = payload["windows"][0]["optimization_result"]["trials"]
        self.assertTrue(any(not trial["feasible"] for trial in saved_trials))
        self.assertIn("validation_feasible", rows[0])
        window_row = next(row for row in rows if row["record_type"] == "window")
        rejected_row = next(
            row
            for row in rows
            if row["record_type"] == "trial"
            and row["trial_feasible"] == "False"
        )
        self.assertEqual(window_row["validation_feasible"], "True")
        self.assertEqual(rejected_row["trial_status"], "result_constraint_failed")
        self.assertIn("net_profit must be at least 1", rejected_row["trial_violations"])

    def test_accepts_user_defined_optimizer_protocol(self):
        optimizer = FixedCustomOptimizer()
        constraint = lambda params: params["lot_size"] > 0
        dataset = TradingDataset.from_dataframe(
            make_data(8), optimization_period="4d", validation_period="4d"
        )
        runner = WalkForwardRunner(
            simulator_factory=lambda data: TradingSimulator(PARAMS, None, data),
            strategy_factory=lambda params, model: OneTradeStrategy(params["lot_size"]),
            optimizer=optimizer,
            parameter_constraints=[constraint],
            n_trials=1,
        )

        result = runner.run(dataset)

        self.assertEqual(result.windows[0].best_params, {"lot_size": 0.01})
        self.assertEqual(optimizer.received_constraints, (constraint,))

    def test_trains_model_before_optimization_when_training_data_exists(self):
        trainer = RecordingTrainer()
        dataset = TradingDataset.from_dataframe(
            make_data(14),
            training_period="2d",
            optimization_period="4d",
            validation_period="2d",
        )

        result = self.make_runner(trainer=trainer).run(dataset)

        self.assertEqual(len(trainer.training_ranges), len(result.windows))
        self.assertGreater(len(result.windows), 0)

    def test_training_period_requires_trainer(self):
        dataset = TradingDataset.from_dataframe(
            make_data(10),
            training_period="2d",
            optimization_period="4d",
            validation_period="2d",
        )

        with self.assertRaisesRegex(ValueError, "trainer is required"):
            self.make_runner().run(dataset)

    def test_evaluates_parameter_variations_on_validation_data(self):
        dataset = TradingDataset.from_dataframe(
            make_data(8), optimization_period="4d", validation_period="4d"
        )

        result = self.make_runner(
            parameter_variations={"lot_size": [-0.01, 0]}
        ).run(dataset)

        stability = result.windows[0].parameter_stability_result
        self.assertIsNotNone(stability)
        self.assertEqual(len(stability.variations), 2)
        self.assertEqual(result.aggregate_metrics["parameter_variation_count"], 2)
        self.assertEqual(sum(item.is_center for item in stability.variations), 1)
        self.assertEqual(
            {item.params["lot_size"] for item in stability.variations},
            {0.01, 0.02},
        )
        center = next(item for item in stability.variations if item.is_center)
        self.assertEqual(
            center.metrics,
            result.windows[0].validation_result.metrics,
        )

        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "result.json"
            csv_path = Path(directory) / "result.csv"
            result.save_json(json_path)
            result.save_csv(csv_path)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            with csv_path.open(encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))

        saved = payload["windows"][0]["parameter_stability_result"]
        self.assertEqual(len(saved["variations"]), 2)
        self.assertEqual(
            len([row for row in rows if row["record_type"] == "parameter_variation"]),
            2,
        )


if __name__ == "__main__":
    unittest.main()
