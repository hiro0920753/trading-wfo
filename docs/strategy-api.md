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

The strategy receives confirmed bars and the current executable quote.
Important context fields include:

- `time`, the current quote time `t`, plus its `bid`, `ask`, and `spread`;
- `open`, `high`, `low`, and `close` from the latest confirmed bar `t-1`;
- `bars`, ending at `t-1` and containing the configured `lookback_bars` rows;
- `balance`, `equity`, `used_margin`, `free_margin`, and `margin_level`;
- `realized_profit`, `unrealized_profit`, `realized_pips`, and
  `unrealized_pips`;
- `long_positions`, `short_positions`, and `active_position_count`.

Orders and close requests returned at time `t` execute immediately using the
same `context["bid"]` and `context["ask"]`, adjusted for configured slippage.
Close requests execute before new orders in the same `Action`.
Strategy-specific values belong in `Order.metadata`; the simulator preserves
them without interpreting them.

The current quote already includes configured spread stress. Execution then
applies adverse entry or exit slippage:

```python
from trading_wfo import ExecutionConfig

execution = ExecutionConfig(
    additional_spread_pips=0.5,
    entry_slippage_pips=0.2,
    exit_slippage_pips=0.3,
)
```

With no slippage, a close request uses the same Bid/Ask used by the strategy
to calculate its decision-time profit. CSV Bid/Ask values remain unchanged in
the user's input DataFrame; only the simulation context and execution quote
are adjusted.

An exception raised by strategy code is wrapped in `StrategyExecutionError`
with the step index and timestamp where it occurred.
