# Strategy API

A strategy is either a callable or an object implementing `on_bar(context)`.
It must return an `Action` or `None`. Returning `None` is equivalent to an
empty `Action`.

```python
from trading_wfo import Action, CloseRequest, Order, Side, StrategyContext

class MyStrategy:
    def on_bar(self, context: StrategyContext) -> Action:
        if not context["long_positions"]:
            return Action(orders=[Order(Side.LONG, lot_size=0.01)])
        return Action(
            close_requests=[
                CloseRequest(context["long_positions"][0]["position_id"])
            ]
        )
```

The strategy receives only confirmed data. Important context fields include:

- `time`, `bid`, `ask`, `spread`, `open`, `high`, `low`, and `close`;
- `bars`, containing at most the configured `lookback_bars` confirmed rows;
- `balance`, `equity`, `used_margin`, `free_margin`, and `margin_level`;
- `realized_profit`, `unrealized_profit`, `realized_pips`, and
  `unrealized_pips`;
- `long_positions`, `short_positions`, and `active_position_count`.

Orders and close requests returned at bar `t` become pending. The simulator
executes them using bar `t+1` prices before calling the strategy again.
Strategy-specific values belong in `Order.metadata`; the simulator preserves
them without interpreting them.

An exception raised by strategy code is wrapped in `StrategyExecutionError`
with the step index and timestamp where it occurred.
