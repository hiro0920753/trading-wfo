# Simulator semantics

## Data contract

`TradingSimulator` accepts user-supplied tabular market data. It does not
download, resample, or generate indicators. Required columns are `time`,
`bid`, `ask`, `open`, `high`, `low`, and `close`. Timestamps are sorted and
retain timezone information. Prices must be finite and `ask >= bid`.

## Decision and execution order

For each confirmed bar `t`, processing is deterministic:

1. execute the `Action` submitted on bar `t-1` at bar `t` Bid/Ask;
2. process close requests before new orders;
3. refresh Account, Portfolio, margin, and unrealized P&L;
4. apply StopOut when the configured margin level is breached;
5. append the equity point;
6. call the strategy with data confirmed through bar `t`;
7. store the returned `Action` for bar `t+1`.

This prevents an action based on a bar's close from filling at an earlier
price from that same bar.

## Price rules

- Long entry: Ask; long exit: Bid.
- Short entry: Bid; short exit: Ask.
- Spread is represented by the supplied Bid and Ask columns.
- Slippage moves executions against the trader.
- Commission is charged per lot on each entry and exit side.

Open positions are closed at the final Bid/Ask by default with
`exit_reason="end_of_data"`. Set `close_positions_at_end=False` only when an
open-ended result is intended.

## Risk and accounting

The internal Account and Portfolio enforce required margin, free margin,
margin level, multiple positions, and StopOut. `reinvestment_rate` controls
the fraction of positive realized profit returned to trading capital. Losses
always reduce trading capital in full. Rejected orders are retained in the
result rather than silently discarded.
