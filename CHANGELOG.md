# Changelog

All notable changes to this project are documented in this file.

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
