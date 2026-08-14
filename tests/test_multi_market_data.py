import unittest

import pandas as pd

from trading_wfo import Action, TradingDataset, TradingSimulator


def bars(start, prices):
    return pd.DataFrame({
        "time": pd.date_range(start, periods=len(prices), freq="5min"),
        "bid": prices,
        "ask": [price + 0.1 for price in prices],
        "open": prices,
        "high": [price + 1 for price in prices],
        "low": [price - 1 for price in prices],
        "close": [price + 0.5 for price in prices],
    })


PARAMS = {
    "common": {"units_per_lot": 100, "symbol": "USDJPY", "price_per_pip": 0.01},
    "strategy_base": {"lookback_bars": 2, "leverage": 10},
    "asset": {"balance": 10_000},
}


class MultiMarketDataTest(unittest.TestCase):
    def test_simulator_exposes_causal_symbol_views(self):
        data = {
            "USDJPY": bars("2026-01-01", [100, 101, 102, 103, 104]),
            "EURJPY": bars("2026-01-01", [150, 151, 152, 153, 154]),
        }
        contexts = []
        TradingSimulator(PARAMS, None, data).run(
            lambda context: contexts.append(context) or Action()
        )
        first = contexts[0]
        self.assertEqual({"USDJPY", "EURJPY"}, set(first["markets"]))
        self.assertEqual(152, first["markets"]["EURJPY"]["bid"])
        self.assertEqual(151.5, first["markets"]["EURJPY"]["close"])
        self.assertEqual(2, len(first["markets"]["EURJPY"]["bars"]))

    def test_dataset_slices_every_market_with_primary_timeline(self):
        data = {
            "USDJPY": bars("2026-01-01", list(range(100, 110))),
            "EURJPY": bars("2026-01-01", list(range(150, 160))),
        }
        dataset = TradingDataset(
            data, primary_symbol="USDJPY",
            optimization_period="20min", validation_period="15min",
        )
        window = next(iter(dataset))
        self.assertEqual({"USDJPY", "EURJPY"}, set(window.validation_data))
        self.assertEqual(3, len(window.validation_data["USDJPY"]))
        self.assertEqual(3, len(window.validation_data["EURJPY"]))


if __name__ == "__main__":
    unittest.main()
