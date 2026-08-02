import unittest

from trading_wfo._portfolio import Portfolio
from trading_wfo.models import Position, Side


def position(position_id, side):
    return Position(
        position_id=position_id,
        side=side,
        entry_price=100.0,
        lot_size=0.1,
        time=0,
        symbol="TEST",
    )


class PortfolioTest(unittest.TestCase):
    def test_open_position_routes_long_and_short_positions(self):
        portfolio = Portfolio()
        long_position = position(1, Side.LONG)
        short_position = position(2, Side.SHORT)

        portfolio.open_position(long_position)
        portfolio.open_position(short_position)

        self.assertEqual(portfolio.long_positions(), (long_position,))
        self.assertEqual(portfolio.short_positions(), (short_position,))
        self.assertEqual(portfolio.positions(), (long_position, short_position))

    def test_close_positions_returns_removed_positions(self):
        portfolio = Portfolio()
        positions = [
            position(1, Side.LONG),
            position(2, Side.SHORT),
            position(3, Side.LONG),
        ]
        for item in positions:
            portfolio.open_position(item)

        closed = portfolio.close_positions([1, 2])

        self.assertEqual(closed, positions[:2])
        self.assertEqual(portfolio.long_positions(), (positions[2],))
        self.assertEqual(portfolio.short_positions(), ())

    def test_close_position_returns_one_removed_position(self):
        portfolio = Portfolio()
        item = position(1, Side.LONG)
        portfolio.open_position(item)

        closed = portfolio.close_position(1)

        self.assertEqual(closed, item)
        self.assertEqual(portfolio.positions(), ())

    def test_close_all_empties_portfolio(self):
        portfolio = Portfolio()
        portfolio.open_position(position(1, Side.LONG))
        portfolio.open_position(position(2, Side.SHORT))

        closed = portfolio.close_all()

        self.assertEqual(len(closed), 2)
        self.assertEqual(portfolio.positions(), ())


if __name__ == "__main__":
    unittest.main()
