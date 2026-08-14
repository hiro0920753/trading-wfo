import csv
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from trading_wfo import (
    CategoricalParameter,
    FloatParameter,
    GridOptimizer,
    IntParameter,
    TPEOptimizer,
)


class TPEOptimizerTest(unittest.TestCase):
    def test_parallelizes_trials_with_configured_workers(self):
        lock = threading.Lock()
        active = 0
        maximum_active = 0

        def objective(params):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            return float(params["value"])

        optimizer = TPEOptimizer(
            {"value": IntParameter(1, 20)}, workers=3, seed=5
        )
        result = optimizer.optimize(objective, n_trials=6)

        self.assertEqual(len(result.trials), 6)
        self.assertGreater(maximum_active, 1)

    def test_finds_best_categorical_parameter_and_keeps_metrics(self):
        optimizer = TPEOptimizer(
            {"value": CategoricalParameter([1, 2, 3])},
            seed=7,
            n_startup_trials=3,
        )

        result = optimizer.optimize(
            lambda params: (
                -abs(params["value"] - 2),
                {"selected": params["value"]},
            ),
            n_trials=12,
        )

        self.assertEqual(result.best_params, {"value": 2})
        self.assertEqual(result.best_score, 0)
        self.assertEqual(len(result.trials), 12)
        self.assertTrue(all("selected" in trial.metrics for trial in result.trials))

    def test_supports_float_and_integer_parameters(self):
        optimizer = TPEOptimizer(
            {
                "ratio": FloatParameter(0.1, 0.9),
                "period": IntParameter(2, 10, step=2),
            },
            seed=3,
            n_startup_trials=2,
        )

        result = optimizer.optimize(
            lambda params: params["ratio"] + params["period"],
            n_trials=5,
        )

        self.assertEqual(len(result.trials), 5)
        self.assertTrue(0.1 <= result.best_params["ratio"] <= 0.9)
        self.assertIn(result.best_params["period"], [2, 4, 6, 8, 10])

    def test_parameter_constraints_prune_and_record_trials(self):
        optimizer = TPEOptimizer(
            {"value": CategoricalParameter([1, 2])},
            seed=2,
            n_startup_trials=2,
        )

        result = optimizer.optimize(
            lambda params: float(params["value"]),
            parameter_constraints=[
                lambda params: (
                    None if params["value"] == 2 else "value must be 2"
                )
            ],
            n_trials=12,
        )

        self.assertEqual(result.best_params, {"value": 2})
        rejected = [trial for trial in result.trials if not trial.feasible]
        self.assertTrue(rejected)
        self.assertTrue(all(
            trial.status == "parameter_constraint_failed"
            for trial in rejected
        ))
        self.assertTrue(all("value must be 2" in trial.violations for trial in rejected))

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "optimization.csv"
            json_path = Path(directory) / "optimization.json"
            result.save_csv(csv_path)
            result.save_json(json_path)
            with csv_path.open(encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        rejected_rows = [
            row for row in rows
            if row["record_type"] == "trial"
            and row["trial_feasible"] == "False"
        ]
        self.assertTrue(rejected_rows)
        self.assertTrue(any(not trial["feasible"] for trial in payload["trials"]))


class GridOptimizerTest(unittest.TestCase):
    def test_evaluates_each_grid_combination_exactly_once(self):
        seen = []
        optimizer = GridOptimizer(
            {
                "ratio": FloatParameter(0.015, 0.02, step=0.0025),
                "period": IntParameter(2, 4, step=2),
            },
            workers=2,
        )

        result = optimizer.optimize(
            lambda params: seen.append(tuple(params.values())) or sum(params.values()),
            n_trials=6,
        )

        self.assertEqual(len(result.trials), 6)
        self.assertEqual(len(set(seen)), 6)
        self.assertEqual(result.best_params, {"ratio": 0.02, "period": 4})

    def test_rejects_trial_limit_smaller_than_grid(self):
        optimizer = GridOptimizer({"value": IntParameter(1, 3)})
        with self.assertRaisesRegex(ValueError, "exhaustive grid size 3"):
            optimizer.optimize(lambda params: params["value"], n_trials=2)


if __name__ == "__main__":
    unittest.main()
