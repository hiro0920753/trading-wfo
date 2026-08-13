import csv
import json
import tempfile
import unittest
from pathlib import Path

from trading_wfo import Action, Order, Side, TradeLogger

from tests.test_simulator_run import OpenThenCloseStrategy, TradingSimulator, make_data, make_params


class TradeLoggerTest(unittest.TestCase):
    def test_saves_open_and_close_as_separate_csv_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trades.csv"
            logger = TradeLogger(path)
            simulator = TradingSimulator(make_params(), logger, make_data())

            simulator.run(OpenThenCloseStrategy())

            with path.open(encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual([row["event"] for row in rows], [
            "position_opened",
            "position_closed",
        ])
        self.assertEqual(rows[0]["execution_price"], "111.0")
        self.assertEqual(rows[1]["execution_price"], "120.0")
        self.assertEqual(rows[1]["exit_reason"], "take_profit_trend_reversal")
        self.assertEqual(rows[1]["realized_profit"], "9.0")

    def test_none_logger_does_not_require_a_log_file(self):
        simulator = TradingSimulator(make_params(), None, make_data())
        result = simulator.run(OpenThenCloseStrategy())
        self.assertEqual(result.metrics["total_trades"], 1)

    def test_saves_end_of_data_liquidation_reason(self):
        class OpenOnce:
            def __init__(self):
                self.opened = False

            def on_bar(self, context):
                if not self.opened:
                    self.opened = True
                    return Action(orders=[Order(Side.LONG, 0.01)])
                return Action()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trades.csv"
            simulator = TradingSimulator(
                make_params(), TradeLogger(path), make_data()
            )
            simulator.run(OpenOnce())
            with path.open(encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(rows[-1]["exit_reason"], "end_of_data")

    def test_simulation_result_saves_csv_with_rowlogger_and_json(self):
        simulator = TradingSimulator(make_params(), None, make_data())
        result = simulator.run(OpenThenCloseStrategy())

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "result.csv"
            json_path = Path(directory) / "result.json"
            result.save_csv(csv_path)
            result.save_json(json_path)
            with csv_path.open(encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(rows[0]["record_type"], "metrics")
        self.assertIn("trade", [row["record_type"] for row in rows])
        self.assertIn("equity", [row["record_type"] for row in rows])
        self.assertEqual(payload["metrics"]["total_trades"], 1)


if __name__ == "__main__":
    unittest.main()
