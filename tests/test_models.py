import unittest

from trading_wfo import Action, CloseRequest, Order, Position, Side
from trading_wfo.models import make_position_snapshot


class TradingModelsTest(unittest.TestCase):
    def test_dataclass_action_contract(self):
        action = Action(
            orders=[
                Order(
                    side=Side.LONG,
                    lot_size=0.1,
                    metadata={"strategy_type": "pullback", "rsi": -0.08},
                )
            ],
            close_requests=[CloseRequest(position_id=3)],
        )

        self.assertIs(action.orders[0].side, Side.LONG)
        self.assertEqual(action.orders[0].metadata["rsi"], -0.08)
        self.assertEqual(action.close_requests[0].position_id, 3)

    def test_position_snapshot_is_independent(self):
        position = Position(
            position_id=1,
            side=Side.LONG,
            entry_price=150.0,
            lot_size=0.1,
            time=0,
            symbol="TEST",
            metadata={"strategy_type": "pullback"},
        )

        snapshot = make_position_snapshot(position)
        snapshot["metadata"]["strategy_type"] = "changed"

        self.assertEqual(position.metadata["strategy_type"], "pullback")
        self.assertEqual(snapshot["side"], "long")
        self.assertNotIn("peak_profit_pips", snapshot)
        self.assertNotIn("is_peak_updated", snapshot)

    def test_side_accepts_only_long_and_short(self):
        self.assertIs(Side.from_value("long"), Side.LONG)
        self.assertIs(Side.from_value("short"), Side.SHORT)
        with self.assertRaises(ValueError):
            Side.from_value("ask")


if __name__ == "__main__":
    unittest.main()
