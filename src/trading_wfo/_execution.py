from .models import Side
from .execution import ExecutionConfig


class Execution:
    """Internal market-order pricing and commission rules."""

    def __init__(self, config: ExecutionConfig, price_per_pip: float):
        self.config = config
        self._slippage = config.slippage_pips * float(price_per_pip)

    def entry_price(self, side, ask, bid):
        side = Side.from_value(side)
        if side is Side.LONG:
            return float(ask) + self._slippage
        return float(bid) - self._slippage

    def exit_price(self, side, ask, bid):
        side = Side.from_value(side)
        if side is Side.LONG:
            return float(bid) - self._slippage
        return float(ask) + self._slippage

    def commission(self, lot_size):
        return (
            float(lot_size) * self.config.commission_per_lot_per_side
        )
