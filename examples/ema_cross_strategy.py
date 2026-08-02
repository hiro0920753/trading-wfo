from trading_wfo import Action, CloseRequest, Order, Side


class EmaCrossStrategy:
    """Confirmed-bar EMA crossover example using next-bar market orders."""

    def __init__(self, fast_period, slow_period, lot_size, model=None):
        self.fast_period = int(fast_period)
        self.slow_period = int(slow_period)
        self.lot_size = float(lot_size)
        self.model = model
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be smaller than slow_period")

    def on_bar(self, context):
        closes = context["bars"]["close"]
        if len(closes) < self.slow_period + 1:
            return Action()

        fast = closes.ewm(span=self.fast_period, adjust=False).mean()
        slow = closes.ewm(span=self.slow_period, adjust=False).mean()
        crossed_up = fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]
        crossed_down = fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]

        if crossed_up:
            closes_to_submit = [
                CloseRequest(position["position_id"])
                for position in context["short_positions"]
            ]
            orders = [] if context["long_positions"] else [
                Order(
                    side=Side.LONG,
                    lot_size=self.lot_size,
                    metadata={
                        "strategy": "ema_cross",
                        "fast_period": self.fast_period,
                        "slow_period": self.slow_period,
                    },
                )
            ]
            return Action(orders=orders, close_requests=closes_to_submit)

        if crossed_down:
            closes_to_submit = [
                CloseRequest(position["position_id"])
                for position in context["long_positions"]
            ]
            orders = [] if context["short_positions"] else [
                Order(
                    side=Side.SHORT,
                    lot_size=self.lot_size,
                    metadata={
                        "strategy": "ema_cross",
                        "fast_period": self.fast_period,
                        "slow_period": self.slow_period,
                    },
                )
            ]
            return Action(orders=orders, close_requests=closes_to_submit)

        return Action()

