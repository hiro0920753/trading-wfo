from typing import Optional

from .models import Action, Side
from .execution import ExecutionConfig


class Execution:
    """Internal execution rules and the action waiting for the next bar."""

    def __init__(self, config: ExecutionConfig, price_per_pip: float):
        self._pending_action: Optional[Action] = None
        self.config = config
        self._slippage = config.slippage_pips * float(price_per_pip)

    @property
    def has_pending_action(self):
        return self._pending_action is not None

    def submit(self, action: Action):
        if self._pending_action is not None:
            raise RuntimeError("a pending action already exists")
        self._pending_action = action

    def take_pending(self):
        action = self._pending_action
        self._pending_action = None
        return action

    def clear(self):
        self._pending_action = None

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
