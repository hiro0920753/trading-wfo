from .models import Side
from .execution import ExecutionConfig


class Execution:
    """Internal market-order pricing and commission rules."""

    def __init__(self, config: ExecutionConfig, price_per_pip: float):
        self.config = config
        pip_size = float(price_per_pip)
        self._additional_spread = config.additional_spread_pips * pip_size
        self._entry_slippage = config.entry_slippage_pips * pip_size
        self._exit_slippage = config.exit_slippage_pips * pip_size

    def effective_quote(self, ask, bid):
        """Return the executable quote after the spread stress adjustment."""
        return float(ask) + self._additional_spread, float(bid)

    def entry_price(self, side, ask, bid):
        side = Side.from_value(side)
        if side is Side.LONG:
            return float(ask) + self._entry_slippage
        return float(bid) - self._entry_slippage

    def exit_price(self, side, ask, bid):
        side = Side.from_value(side)
        if side is Side.LONG:
            return float(bid) - self._exit_slippage
        return float(ask) + self._exit_slippage

    def commission(self, lot_size):
        return (
            float(lot_size) * self.config.commission_per_lot_per_side
        )
