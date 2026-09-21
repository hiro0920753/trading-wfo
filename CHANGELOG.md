# Changelog

All notable changes to this project are documented in this file.

## 0.6.2 - 2026-09-21

- Documentation-only release; runtime behavior is unchanged from 0.6.1.
- Updated the PyPI overview with current features, fixes, and a runnable example.
- Documented reserve refill and temporary funding, dashboard refresh intervals,
  independent WFO account state, and single-instrument execution scope.
- Replaced relative README documentation links with versioned GitHub URLs.

## 0.6.1 - 2026-09-13

- Fixed per-order margin checks to include earlier fills, commissions, and
  unrealized losses in market and pending-limit order batches.
- Fixed delayed-entry robustness scenarios for callable strategies.
- Fixed contribution scheduling for timezone-naive market data (interpreted
  as UTC), while retaining timezone-aware market calendar behavior.
- Prevented reserve transfers for orders whose full funding cannot be covered,
  and prevented negative reserve repayments after losses exhaust capital.
- Added reserve refill and opt-in temporary order funding, with proportional
  repayment on partial closes and explicit account diagnostics.
- Added causal periodic account contributions with calendar schedules, separate
  cash-flow records, contribution-adjusted net profit, and time-weighted return.
- Added backward-compatible full and partial position closes by explicit lot
  size or fraction, with proportional commission and remaining-position state.

## 0.6.0 - 2026-09-11

- Added opt-in frozen OOS robustness scenarios: historical-spread multipliers,
  market-entry delay and explicit parameter offsets, with no reoptimization.
- Added compact per-window JSON/CSV diagnostics, calendar attribution, optional
  seeded trade Monte Carlo and aggregate comparisons on the Robustness dashboard.
- Parameter-stability evaluation now uses the validation simulator factory,
  matching the center result when a custom validation factory is supplied.

## 0.5.0 - 2026-08-23

- Added `TrainingResult` so each walk-forward window can persist JSON-safe
  model weights, train/validation losses, sample counts, seeds, and other
  training audit artifacts alongside its chronological period boundaries.
- Added a self-contained machine-learning example that retrains a NumPy
  logistic model, optimizes a trading threshold, and performs forward
  validation in every window.

## 0.4.0 - 2026-08-14

- Added warmup context to walk-forward windows so indicators can be initialized
  from earlier bars without leaking warmup rows into optimization or validation.
- Added causal multi-market inputs. Pass a `{symbol: DataFrame}` mapping and
  read confirmed auxiliary-market bars from `context["markets"]`.
- Added market and limit orders, pending-order cancellation and expiration.
  A limit submitted at quote time `t` is first evaluated against the next
  confirmed bar, preventing current-bar high/low look-ahead.
- Added explicit order symbols. Execution remains tied to the configured
  primary instrument; auxiliary symbols are information inputs until
  instrument-specific contract and currency-conversion rules are supplied.
- Added `pending_order_count` to simulation metrics.

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
