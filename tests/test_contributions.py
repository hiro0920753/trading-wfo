import unittest

import pandas as pd

from trading_wfo import Action, AccountConfig, ContributionSchedule, TradingSimulator


def make_data():
    return pd.DataFrame({
        "time": pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="5min"),
        "bid": [100.0] * 4, "ask": [100.1] * 4,
        "open": [100.0] * 4, "high": [100.0] * 4,
        "low": [100.0] * 4, "close": [100.0] * 4,
    })


def make_params():
    return {
        "common": {"units_per_lot": 100, "symbol": "TEST", "price_per_pip": 1.0},
        "strategy_base": {"lookback_bars": 1, "leverage": 10},
        "asset": {
            "balance": 10_000,
            "contribution_schedules": [{
                "amount": 500, "period": "1mo",
                "start": "2026-01-01T00:10:00Z",
            }],
        },
    }


class ContributionTest(unittest.TestCase):
    def test_contribution_is_available_before_strategy_and_not_profit(self):
        balances = []

        def strategy(context):
            balances.append((context["time"], context["balance"], context["trading_capital"]))
            return Action()

        result = TradingSimulator(make_params(), None, make_data()).run(strategy)

        self.assertEqual([item[1] for item in balances], [10_000, 10_500, 10_500])
        self.assertEqual(result.metrics["final_balance"], 10_500)
        self.assertEqual(result.metrics["balance_change"], 500)
        self.assertEqual(result.metrics["net_profit"], 0)
        self.assertEqual(result.metrics["total_contributions"], 500)
        self.assertEqual(result.metrics["time_weighted_return_pct"], 0)
        self.assertEqual(len(result.cash_flows), 1)
        self.assertEqual(result.cash_flows[0]["scheduled_time"], "2026-01-01T00:10:00+00:00")
        self.assertEqual(result.equity_curve[1]["cash_flow"], 500)

    def test_schedule_must_have_positive_amount_and_valid_period(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            ContributionSchedule(amount=0, period="1mo")
        with self.assertRaisesRegex(ValueError, "invalid period"):
            ContributionSchedule(amount=100, period="monthly")

    def test_account_config_normalizes_mapping_schedules(self):
        config = AccountConfig(
            initial_balance=1_000, leverage=10, units_per_lot=100,
            price_per_pip=1, contribution_schedules=({"amount": 100, "period": "1mo"},),
        )
        self.assertIsInstance(config.contribution_schedules[0], ContributionSchedule)


if __name__ == "__main__":
    unittest.main()
