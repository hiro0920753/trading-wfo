import csv
import json
import tempfile
import unittest
from pathlib import Path

from examples.run_usdjpy_m15_wfo import run


REPOSITORY = Path(__file__).resolve().parents[1]
MT5_DIRECTORY = REPOSITORY / "mt5_data" / "USDJPY-" / "M15"


@unittest.skipUnless(
    MT5_DIRECTORY.exists(),
    "repository-local MT5 fixture is not included in distributions",
)
class UsdJpyM15WfoEndToEndTest(unittest.TestCase):
    def test_real_mt5_data_runs_through_wfo_and_saves_all_results(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "wfo"
            result = run(
                MT5_DIRECTORY, output, n_trials=6, progress=False
            )

            json_path = output / "wfo_result.json"
            csv_path = output / "wfo_result.csv"
            trade_path = output / "validation_trades.csv"
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            with csv_path.open(encoding="utf-8", newline="") as file:
                result_rows = list(csv.DictReader(file))
            with trade_path.open(encoding="utf-8", newline="") as file:
                trade_rows = list(csv.DictReader(file))

        self.assertGreater(len(result.windows), 0)
        self.assertEqual(
            result.aggregate_metrics["window_count"], len(result.windows)
        )
        self.assertAlmostEqual(
            result.aggregate_metrics["net_profit"],
            sum(
                window.validation_result.metrics["net_profit"]
                for window in result.windows
            ),
        )
        for window in result.windows:
            self.assertLess(
                window.best_params["fast_period"],
                window.best_params["slow_period"],
            )
            self.assertEqual(window.optimization_end, window.validation_start)
            self.assertLess(window.validation_start, window.validation_end)
            self.assertIsNotNone(window.validation_start.tzinfo)
            self.assertAlmostEqual(
                window.validation_result.metrics["final_balance"],
                window.validation_result.metrics["final_equity"],
            )
            for trade in window.validation_result.trades:
                self.assertGreaterEqual(trade["time"], window.validation_start.timestamp())
                self.assertLess(trade["exit_time"], window.validation_end.timestamp())

        self.assertEqual(
            payload["aggregate_metrics"]["window_count"], len(result.windows)
        )
        self.assertTrue(payload["windows"][0]["validation_start"].endswith("+00:00"))
        self.assertEqual(result_rows[0]["record_type"], "summary")
        self.assertTrue(any(row["record_type"] == "trial" for row in result_rows))
        self.assertTrue(trade_rows)
        self.assertTrue(all(
            row["event"] in {"position_opened", "position_closed"}
            for row in trade_rows
        ))


if __name__ == "__main__":
    unittest.main()
