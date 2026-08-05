# Simulator semantics

## Data contract

`TradingSimulator` accepts user-supplied tabular market data. It does not
download, resample, or generate indicators. Required columns are `time`,
`bid`, `ask`, `open`, `high`, `low`, and `close`. Timestamps are sorted and
retain timezone information. Prices must be finite and `ask >= bid`.

## Decision and execution order

At each current quote time `t`, processing is deterministic:

1. expose only bars confirmed through `t-1`;
2. refresh Account, Portfolio, margin, and unrealized P&L with the Bid/Ask at
   `t`;
3. apply StopOut when the configured margin level is breached;
4. call the strategy with confirmed bars through `t-1` and the current quote
   at `t`;
5. execute its close requests and then new market orders using that same `t`
   Bid/Ask, adjusted for slippage;
6. append the equity point.

This prevents the close of the still-forming bar at `t` from leaking into the
decision while keeping the decision quote and market-order execution price on
the same timestamp.

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
