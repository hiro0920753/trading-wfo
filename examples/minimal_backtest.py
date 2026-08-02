"""Self-contained trading-wfo backtest example."""

import pandas as pd

from trading_wfo import Action, Order, Side, TradingDataset, TradingSimulator


PARAMS = {
    "common": {
        "units_per_lot": 100,
        "symbol": "DEMO",
        "price_per_pip": 1,
    },
    "strategy_base": {"lookback_bars": 2, "leverage": 10},
    "asset": {"balance": 10_000},
}


class BuyOnce:
    def __init__(self):
        self.ordered = False

    def on_bar(self, context):
        if not self.ordered:
            self.ordered = True
            return Action(orders=[Order(Side.LONG, lot_size=0.01)])
        return Action()


def main():
    close = [100.0, 100.5, 101.0, 101.5, 102.0]
    data = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=len(close), freq="1h", tz="UTC"),
            "bid": close,
            "ask": [price + 0.1 for price in close],
            "open": close,
            "high": [price + 0.2 for price in close],
            "low": [price - 0.2 for price in close],
            "close": close,
        }
    )
    dataset = TradingDataset.from_dataframe(data)
    simulator = TradingSimulator(PARAMS, None, dataset.backtest_data)
    result = simulator.run(BuyOnce())
    print(result.metrics)


if __name__ == "__main__":
    main()
