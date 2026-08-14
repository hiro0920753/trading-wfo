import unittest

import pandas as pd

from trading_wfo import Action, Order, OrderType, Side, TradingSimulator


def data():
    return pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=5, freq="5min"),
        "bid": [100, 100, 100, 105, 105],
        "ask": [101, 101, 101, 106, 106],
        "open": [100, 100, 100, 105, 105],
        "high": [101, 101, 104, 106, 106],
        "low": [99, 99, 98, 104, 104],
        "close": [100, 100, 103, 105, 105],
    })


PARAMS = {
    "common": {"units_per_lot": 100, "symbol": "TEST", "price_per_pip": 1},
    "strategy_base": {"lookback_bars": 1, "leverage": 10},
    "asset": {"balance": 10_000},
}


class LimitOrderTest(unittest.TestCase):
    def test_limit_order_fills_only_after_submission_bar_is_confirmed(self):
        contexts = []

        def strategy(context):
            contexts.append(context)
            if context["step_index"] == 0:
                return Action(orders=[Order(
                    Side.LONG, 0.01, order_type=OrderType.LIMIT, limit_price=99
                )])
            return Action()

        simulator = TradingSimulator(PARAMS, None, data())
        simulator.run(strategy, close_positions_at_end=False)
        position = simulator._portfolio.positions()[0]
        self.assertEqual(99, position.entry_price)
        self.assertEqual(data().iloc[2]["time"].timestamp(), position.time)
        self.assertEqual(0, len(contexts[0]["pending_orders"]))

    def test_pending_limit_can_be_cancelled(self):
        def strategy(context):
            if context["step_index"] == 0:
                return Action(orders=[Order(
                    Side.LONG, 0.01, order_type="limit", limit_price=90
                )])
            if context["step_index"] == 1:
                return Action(cancel_order_ids=[1])
            return Action()

        simulator = TradingSimulator(PARAMS, None, data())
        simulator.run(strategy, close_positions_at_end=False)
        self.assertEqual([], simulator._pending_orders)
        self.assertEqual((), simulator._portfolio.positions())

    def test_short_limit_fills_and_datetime_expiry_is_respected(self):
        expires_at = data().iloc[1]["time"]

        def strategy(context):
            if context["step_index"] == 0:
                return Action(orders=[
                    Order(Side.SHORT, 0.01, order_type="limit", limit_price=103),
                    Order(
                        Side.LONG, 0.01, order_type="limit", limit_price=90,
                        expires_at=expires_at,
                    ),
                ])
            return Action()

        simulator = TradingSimulator(PARAMS, None, data())
        result = simulator.run(strategy, close_positions_at_end=False)
        positions = simulator._portfolio.positions()
        self.assertEqual(1, len(positions))
        self.assertEqual(Side.SHORT, positions[0].side)
        self.assertEqual(103, positions[0].entry_price)
        self.assertEqual(0, result.metrics["pending_order_count"])


if __name__ == "__main__":
    unittest.main()
