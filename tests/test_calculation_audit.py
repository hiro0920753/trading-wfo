import unittest

import pandas as pd

from trading_wfo import (
    AccountConfig,
    Action,
    CloseRequest,
    ExecutionConfig,
    OptimizationResult,
    Order,
    Side,
    SimulationResult,
    TradingSimulator,
    WalkForwardWindowResult,
)
from trading_wfo.wfo import WalkForwardRunner


def market_data(bids, spread=1.0):
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=len(bids), freq="15min"),
            "bid": bids,
            "ask": [value + spread for value in bids],
            "open": bids,
            "high": [value + spread for value in bids],
            "low": bids,
            "close": bids,
        }
    )


PARAMS = {
    "common": {"units_per_lot": 100, "symbol": "TEST", "price_per_pip": 1},
    "strategy_base": {"lookback_bars": 1, "leverage": 100},
    "asset": {"balance": 1_000, "stop_out_level": 0},
}


class OpenThenClose:
    def __init__(self, side=Side.LONG, lot_size=1.0, replacement_lot=None):
        self.side = side
        self.lot_size = lot_size
        self.replacement_lot = replacement_lot
        self.calls = 0

    def on_bar(self, context):
        self.calls += 1
        if self.calls == 1:
            return Action(orders=[Order(self.side, self.lot_size)])
        if self.calls == 2:
            orders = (
                []
                if self.replacement_lot is None
                else [Order(self.side, self.replacement_lot)]
            )
            return Action(
                orders=orders,
                close_requests=[CloseRequest(1)],
            )
        return Action()


class CalculationAuditTest(unittest.TestCase):
    def test_spread_only_long_loss_matches_hand_calculation(self):
        simulator = TradingSimulator(PARAMS, None, market_data([100] * 4))

        result = simulator.run(OpenThenClose())

        trade = result.trades[0]
        self.assertEqual(trade["entry_price"], 101)
        self.assertEqual(trade["exit_price"], 100)
        self.assertEqual(trade["realized_pips"], -1)
        self.assertEqual(trade["realized_profit"], -100)
        self.assertEqual(result.metrics["final_balance"], 900)

    def test_commission_compounding_and_same_bar_reentry(self):
        params = {
            **PARAMS,
            "asset": {
                "balance": 1_000,
                "stop_out_level": 0,
                "reinvestment_rate": 0.5,
            },
        }
        simulator = TradingSimulator(
            params,
            None,
            market_data([100, 100, 100, 121]),
            execution_config=ExecutionConfig(
                commission_per_lot_per_side=10
            ),
        )

        result = simulator.run(
            OpenThenClose(replacement_lot=8), close_positions_at_end=False
        )
        account = simulator.account_snapshot()

        self.assertEqual(result.trades[0]["gross_profit"], 2_000)
        self.assertEqual(result.trades[0]["commission"], 20)
        self.assertEqual(result.trades[0]["realized_profit"], 1_980)
        self.assertEqual(result.metrics["total_commission"], 100)
        self.assertEqual(account["balance"], 2_900)
        self.assertEqual(account["trading_capital"], 1_900)
        self.assertEqual(account["reserved_profit"], 1_000)
        self.assertEqual(simulator._portfolio.long_positions()[0].lot_size, 8)
        self.assertEqual(simulator._portfolio.long_positions()[0].entry_price, 122)

    def test_unrealized_loss_margin_and_margin_level(self):
        class OpenOnly:
            def __init__(self):
                self.called = False

            def on_bar(self, context):
                if not self.called:
                    self.called = True
                    return Action(orders=[Order(Side.LONG, 0.5)])
                return Action()

        simulator = TradingSimulator(
            PARAMS, None, market_data([100, 100, 100, 90])
        )

        simulator.run(OpenOnly(), close_positions_at_end=False)
        account = simulator.account_snapshot()

        self.assertEqual(account["unrealized_profit"], -550)
        self.assertEqual(account["equity"], 450)
        self.assertEqual(account["used_margin"], 45.5)
        self.assertEqual(account["free_margin"], 404.5)
        self.assertAlmostEqual(account["margin_level"], 450 / 45.5 * 100)

    def test_stop_out_closes_multiple_positions(self):
        params = {
            **PARAMS,
            "asset": {"balance": 1_000, "stop_out_level": 50},
        }

        class OpenTwoLongs:
            def __init__(self):
                self.called = False

            def on_bar(self, context):
                if not self.called:
                    self.called = True
                    return Action(
                        orders=[Order(Side.LONG, 0.5), Order(Side.LONG, 0.5)]
                    )
                return Action()

        simulator = TradingSimulator(
            params, None, market_data([100, 100, 100, 90, 90])
        )
        result = simulator.run(OpenTwoLongs())

        self.assertEqual(len(result.trades), 2)
        self.assertTrue(all(
            trade["exit_reason"] == "stop_out" for trade in result.trades
        ))
        self.assertEqual(result.metrics["final_balance"], -100)
        self.assertEqual(simulator._portfolio.positions(), ())

    def test_wfo_aggregate_metrics_match_hand_joined_equity(self):
        def window(index, final, equity, profit):
            return WalkForwardWindowResult(
                index=index,
                optimization_result=OptimizationResult({}, 0, []),
                validation_result=SimulationResult(
                    metrics={"initial_balance": 100, "net_profit": final - 100},
                    trades=[{"realized_profit": profit}],
                    equity_curve=[
                        {"time": index * 10 + offset, "balance": value, "equity": value}
                        for offset, value in enumerate(equity)
                    ],
                ),
            )

        metrics = WalkForwardRunner._aggregate_metrics(
            [window(0, 110, [100, 120, 110], 10), window(1, 120, [100, 95, 120], 20)]
        )

        self.assertEqual(metrics["net_profit"], 30)
        self.assertEqual(metrics["final_balance"], 130)
        self.assertEqual(metrics["max_drawdown"], 15)
        self.assertEqual(metrics["max_drawdown_pct"], 12.5)
        self.assertEqual(metrics["profit_factor"], float("inf"))


if __name__ == "__main__":
    unittest.main()
