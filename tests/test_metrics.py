import unittest

from trading_wfo.metrics import calculate_metrics


class MetricsTest(unittest.TestCase):
    def test_trade_and_drawdown_metrics(self):
        metrics = calculate_metrics(
            initial_balance=100,
            final_balance=120,
            trades=[
                {"realized_profit": 30},
                {"realized_profit": -10},
            ],
            equity_curve=[
                {"equity": 100},
                {"equity": 120},
                {"equity": 90},
                {"equity": 120},
            ],
        )

        self.assertEqual(metrics["net_profit"], 20)
        self.assertEqual(metrics["return_pct"], 20)
        self.assertEqual(metrics["total_trades"], 2)
        self.assertEqual(metrics["winning_trades"], 1)
        self.assertEqual(metrics["losing_trades"], 1)
        self.assertEqual(metrics["win_rate"], 50)
        self.assertEqual(metrics["gross_profit"], 30)
        self.assertEqual(metrics["gross_loss"], 10)
        self.assertEqual(metrics["profit_factor"], 3)
        self.assertEqual(metrics["max_drawdown"], 30)
        self.assertEqual(metrics["max_drawdown_pct"], 25)


if __name__ == "__main__":
    unittest.main()
