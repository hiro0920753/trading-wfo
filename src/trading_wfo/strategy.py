"""Public strategy interface used by :class:`TradingSimulator`."""

from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from .models import Action


StrategyContext = Mapping[str, Any]


@runtime_checkable
class Strategy(Protocol):
    """Protocol for stateful strategies evaluated once per confirmed bar."""

    def on_bar(self, context: StrategyContext) -> Optional[Action]:
        """Return an action for execution on the following bar."""
        ...
