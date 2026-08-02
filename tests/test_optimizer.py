import csv
import json
import tempfile
import unittest
from pathlib import Path

from trading_wfo import (
    CategoricalParameter,
    FloatParameter,
    IntParameter,
    TPEOptimizer,
)


class TPEOptimizerTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
