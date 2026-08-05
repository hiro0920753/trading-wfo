"""Public strategy interface used by :class:`TradingSimulator`."""

from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from .models import Action


StrategyContext = Mapping[str, Any]


@runtime_checkable
class Strategy(Protocol):
    """Protocol for strategies evaluated at quote t with bars through t-1."""

    def on_bar(self, context: StrategyContext) -> Optional[Action]:
        """Return an action for immediate execution at the current quote."""
        ...
