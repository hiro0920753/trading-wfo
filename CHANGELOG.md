# Changelog

All notable changes to this project are documented in this file.

## 0.3.0 - 2026-08-07

- Changed simulation timing so strategies receive confirmed bars through
  `t-1`, together with the executable Bid/Ask quote at `t`.
- Market orders and close requests now execute immediately at the same quote
  shown to the strategy, with close requests processed before new orders.
- Added spread stress through `ExecutionConfig.additional_spread_pips`; the
  effective quote is shared by strategies, Account, Margin, StopOut, and
  Execution.
- Split adverse slippage into `entry_slippage_pips` and
  `exit_slippage_pips`, and record all execution-cost settings in results.
- Added parallel optimization trials while keeping walk-forward windows
  sequential.
- Added live WFO and backtest result refresh, progress, elapsed time, and
  estimated completion information to the dashboard.
- Added direct dashboard support for single `SimulationResult` backtests and
  improved Windows-safe atomic progress-file updates.

### Migration from 0.2

- Replace `ExecutionConfig(slippage_pips=value)` with
  `ExecutionConfig(entry_slippage_pips=value, exit_slippage_pips=value)`.
- Strategies no longer receive the current row's OHLC. `bars`, `row`, and the
  top-level OHLC fields end at confirmed bar `t-1`; `time`, `bid`, `ask`, and
  `spread` describe the executable quote at `t`.
- Actions are no longer queued for another row. They execute at the current
  context quote, adjusted by the configured spread stress and slippage.

## 0.2.0 - 2026-08-02

- Reorganized the dashboard into Overview, Windows, Robustness, and Trades.
- Added cross-window validation trade metrics, pips distribution, cumulative
  profit/pips charts, and performance breakdowns.
- Added trade filters for window, side, result, exit reason, and metadata.
- Added an interactive Trade Inspector for execution details and strategy
  metadata.

## 0.1.0 - 2026-08-02

Initial alpha release.

- Backtest and rolling walk-forward datasets with time-based periods.
- Confirmed-bar strategy decisions and next-bar market execution.
- Long and short portfolios, margin, StopOut, commission, slippage, and
  configurable profit reinvestment.
- TPE and custom optimizers with parameter and result constraints.
- Per-window validation, parameter-stability analysis, aggregate metrics, and
  rowlogger CSV/JSON output.
- Local FastAPI dashboard for equity, pips, windows, trials, trades, and
  robustness distributions.
