import unittest

import pandas as pd

from trading_wfo import (
    AccountConfig,
    Action,
    CloseRequest,
    Order,
    Side,
    TradingSimulator,
)
from trading_wfo._account import Account


class DummyTradingLog:
    def add(self, entry):
        pass


def make_data(bids, spread=1.0):
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=len(bids), freq="15min"),
            "bid": bids,
            "ask": [price + spread for price in bids],
            "open": bids,
            "high": [price + spread for price in bids],
            "low": bids,
            "close": bids,
        }
    )


def make_params(balance=10_000, leverage=10, stop_out_level=50):
    return {
        "common": {
            "units_per_lot": 100,
            "symbol": "TEST",
            "price_per_pip": 1.0,
        },
        "strategy_base": {"lookback_bars": 1, "leverage": leverage},
        "asset": {
            "balance": balance,
            "stop_out_level": stop_out_level,
        },
    }


class OpenMultiplePositionsStrategy:
    def __init__(self):
        self.calls = 0
        self.contexts = []

    def on_bar(self, context):
        self.calls += 1
        self.contexts.append(context)
        if self.calls == 1:
            return Action(
                orders=[
                    Order(side=Side.LONG, lot_size=0.1),
                    Order(side=Side.SHORT, lot_size=0.2),
                ]
            )
        return Action()


class OpenLongStrategy:
    def __init__(self):
        self.calls = 0
        self.contexts = []

    def on_bar(self, context):
        self.calls += 1
        self.contexts.append(context)
        if self.calls == 1:
            return Action(orders=[Order(side=Side.LONG, lot_size=1.0)])
        return Action()


class ReinvestAfterCloseStrategy:
    def __init__(self):
        self.calls = 0
        self.contexts = []

    def on_bar(self, context):
        self.calls += 1
        self.contexts.append(context)
        if self.calls == 1:
            return Action(orders=[Order(side=Side.LONG, lot_size=1.0)])
        if self.calls == 2:
            return Action(
                close_requests=[CloseRequest(position_id=1)],
                orders=[Order(side=Side.LONG, lot_size=8.0)],
            )
        return Action()


class AccountRiskTest(unittest.TestCase):
    def test_positive_profit_is_partly_reinvested_before_same_bar_order(self):
        data = make_data([100.0, 100.0, 100.0, 121.0])
        params = make_params(balance=1_000, leverage=100)
        params["asset"]["reinvestment_rate"] = 0.5
        strategy = ReinvestAfterCloseStrategy()
        simulator = TradingSimulator(params, DummyTradingLog(), data)

        result = simulator.run(strategy, close_positions_at_end=False)
        account = simulator.account_snapshot()

        self.assertEqual(len(simulator._portfolio.long_positions()), 1)
        self.assertEqual(simulator._portfolio.long_positions()[0].lot_size, 8.0)
        self.assertEqual(simulator._portfolio.long_positions()[0].entry_price, 122.0)
        self.assertAlmostEqual(account["balance"], 3_000)
        self.assertAlmostEqual(account["trading_capital"], 2_000)
        self.assertAlmostEqual(account["reserved_profit"], 1_000)
        self.assertAlmostEqual(account["reinvested_profit"], 1_000)
        self.assertAlmostEqual(account["allocatable_free_margin"], 224)
        self.assertAlmostEqual(account["buying_power"], 22_400)
        self.assertAlmostEqual(result.metrics["final_trading_capital"], 2_000)
        self.assertAlmostEqual(result.metrics["reserved_profit"], 1_000)
        self.assertAlmostEqual(result.equity_curve[-1]["trading_capital"], 2_000)

    def test_loss_reduces_trading_capital_in_full(self):
        config = AccountConfig(
            initial_balance=1_000,
            leverage=10,
            units_per_lot=100,
            price_per_pip=1,
            reinvestment_rate=0.5,
        )
        account = Account(config)

        account.realize(profit=-200, pips=-2)

        self.assertEqual(account.balance, 800)
        self.assertEqual(account.trading_capital, 800)
        self.assertEqual(account.reserved_profit, 0)

    def test_reinvestment_rate_must_be_between_zero_and_one(self):
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            AccountConfig(
                initial_balance=1_000,
                leverage=10,
                units_per_lot=100,
                price_per_pip=1,
                reinvestment_rate=1.1,
            )

    def test_multiple_positions_margin_equity_and_margin_level(self):
        data = make_data([100.0, 101.0, 102.0, 103.0, 104.0])
        simulator = TradingSimulator(
            make_params(), DummyTradingLog(), data
        )

        simulator.run(
            OpenMultiplePositionsStrategy(), close_positions_at_end=False
        )
        account = simulator.account_snapshot()

        expected_used_margin = (105.0 * 0.1 * 100 / 10) + (104.0 * 0.2 * 100 / 10)
        long_unrealized = (104.0 - 103.0) * 0.1 * 100
        short_unrealized = (102.0 - 105.0) * 0.2 * 100
        expected_equity = 10_000 + long_unrealized + short_unrealized
        expected_free_margin = expected_equity - expected_used_margin

        self.assertEqual(len(simulator._portfolio.long_positions()), 1)
        self.assertEqual(len(simulator._portfolio.short_positions()), 1)
        self.assertAlmostEqual(account["balance"], 10_000)
        self.assertAlmostEqual(account["equity"], expected_equity)
        self.assertAlmostEqual(account["used_margin"], expected_used_margin)
        self.assertAlmostEqual(account["free_margin"], expected_free_margin)
        self.assertAlmostEqual(
            account["margin_level"], expected_equity / expected_used_margin * 100
        )

    def test_combined_order_margin_cannot_exceed_free_margin(self):
        data = make_data([100.0, 100.0, 100.0])
        simulator = TradingSimulator(
            make_params(balance=150, leverage=10), DummyTradingLog(), data
        )

        simulator.run(
            OpenMultiplePositionsStrategy(), close_positions_at_end=False
        )

        self.assertEqual(len(simulator._portfolio.positions()), 1)
        self.assertEqual(len(simulator._portfolio.long_positions()), 1)

    def test_stop_out_force_closes_all_positions(self):
        data = make_data([100.0, 100.0, 100.0, 50.0, 50.0])
        strategy = OpenLongStrategy()
        simulator = TradingSimulator(
            make_params(balance=1_000, leverage=100, stop_out_level=50),
            DummyTradingLog(),
            data,
        )

        result = simulator.run(strategy)

        self.assertEqual(simulator._portfolio.positions(), ())
        self.assertTrue(any(context["stop_out_triggered"] for context in strategy.contexts))
        self.assertEqual(simulator.account_snapshot()["used_margin"], 0)
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0]["exit_price"], 50.0)
        self.assertEqual(result.trades[0]["exit_reason"], "stop_out")
        self.assertAlmostEqual(
            result.metrics["final_balance"],
            1_000 + (50.0 - 101.0) * 1.0 * 100,
        )
        self.assertAlmostEqual(result.metrics["realized_pips"], -51.0)
        self.assertAlmostEqual(
            result.metrics["final_equity"], result.metrics["final_balance"]
        )


if __name__ == "__main__":
    unittest.main()
