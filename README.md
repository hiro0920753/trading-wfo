# trading-wfo
A Python library for walk-forward validation and optimization of trading strategies.

Requires Python 3.10 or newer.

> **Alpha release:** validate results independently before using them for any
> trading decision. This package does not provide investment advice.

## Installation

```bash
pip install trading-wfo
```

Documentation:

- [Quick start](docs/quickstart.md)
- [Strategy API](docs/strategy-api.md)
- [Simulator semantics and look-ahead prevention](docs/simulator-semantics.md)
- [Changelog](CHANGELOG.md)

Users can provide CSV files or one `pandas.DataFrame`. The library does not
resample the supplied timeframe. `TradingDataset` creates chronological AI
training, optimization, and validation sections, and `TradingSimulator`
receives only the section used for that simulation run.

```python
from trading_wfo import AccountConfig, TradingDataset, TradingSimulator

account_config = AccountConfig(
    initial_balance=10_000,
    leverage=25,
    units_per_lot=100_000,
    price_per_pip=0.01,
    stop_out_level=50,
    reinvestment_rate=0.5,
)

dataset = TradingDataset.from_csv(
    ["2026_06.csv", "2026_07.csv"],
    training_period="1mo",       # optional
    optimization_period="2w",
    validation_period="1w",
)

for window in dataset:
    optimization_simulator = TradingSimulator(
        params, log, window.optimization_data, account_config=account_config
    )
    validation_simulator = TradingSimulator(
        params, log, window.validation_data, account_config=account_config
    )
```

Supported period suffixes are `min`, `h`, `d`, `w`, `mo`, and `y`. The default
step period equals the validation period. A warning is emitted when validation
windows overlap or contain gaps.

With no periods, `TradingDataset` is in backtest mode and exposes all supplied
data through `backtest_data`:

```python
dataset = TradingDataset.from_csv("mt5_data/USDJPY-/M15")
result = simulator.run(strategy, data=dataset.backtest_data)
```

Use `backtest_period` to select the latest calendar period:

```python
dataset = TradingDataset.from_csv(
    "mt5_data/USDJPY-/M15",
    backtest_period="1mo",
)
```

Backtest periods cannot be combined with walk-forward periods. The dataset mode
is available as `DatasetMode.BACKTEST` or `DatasetMode.WALK_FORWARD`.

`Account`, `Portfolio`, and `Execution` are internal implementation details.
Account behavior is configured through the public `AccountConfig` class.

Strategies return dataclasses defined by the library:

```python
from trading_wfo import Action, CloseRequest, Order, Side

action = Action(
    orders=[
        Order(
            side=Side.LONG,
            lot_size=0.1,
            metadata={"strategy_type": "pullback", "rsi": 0.35},
        )
    ],
    close_requests=[CloseRequest(position_id=3)],
)
```

A single simulation runs the strategy on each confirmed bar. An action decided
on bar `t` is held as pending and executed with the Bid/Ask values from bar
`t+1`.

```python
simulator = TradingSimulator(params, log, data)
result = simulator.run(strategy)
```

By default, positions still open at the end of the supplied data are closed at
the final Bid (long) or Ask (short). The resulting trade has
`exit_reason="end_of_data"`. Pass `close_positions_at_end=False` only when an
open-ended simulation is intentionally required.

`SimulationResult.metrics` includes `net_profit`, `return_pct`, trade and win
counts, `profit_factor`, `max_drawdown`, and `max_drawdown_pct`, while `trades`
and `equity_curve` retain the underlying records.

TPE optimization and the complete walk-forward sequence can be run together:

```python
from trading_wfo import (
    CategoricalParameter,
    TPEOptimizer,
    WalkForwardRunner,
)

optimizer = TPEOptimizer(
    {"lot_size": CategoricalParameter([0.01, 0.02, 0.05])},
    seed=42,
)
runner = WalkForwardRunner(
    simulator_factory=lambda data: TradingSimulator(params, log, data),
    strategy_factory=lambda best_params, model: MyStrategy(
        **best_params, model=model
    ),
    optimizer=optimizer,
    trainer=my_ai_trainer,  # omit when training_period is not configured
    n_trials=50,
    optimization_workers=4,
    progress=True,
    progress_path="results/wfo_result.progress.json",
)
result = runner.run(dataset)
```

For each window, the runner optionally trains the AI model, performs TPE only
on `optimization_data`, and runs the selected parameters once on
`validation_data`. Trial history is available through
`window_result.optimization_result`; validation metrics are in
`window_result.validation_result.metrics`.

Windows always run sequentially so validation capital and chronology cannot be
mixed. `optimization_workers` parallelizes only the independent optimization
trials inside the active window. The progress JSON is written atomically and
can be displayed while the run is active:

```bash
trading-wfo dashboard --result results/wfo_result.json
```

The dashboard automatically reads `results/wfo_result.progress.json` and shows
window/trial completion, worker count, elapsed time, remaining time, and the
estimated completion timestamp in the Progress tab. Use `--progress-file` when
the tracker is stored elsewhere.

To inspect whether the optimized point sits on a stable parameter region,
configure additive offsets for selected numeric parameters:

```python
runner = WalkForwardRunner(
    ...,
    parameter_variations={
        "fast_period": [-2, 0, 2],
        "slow_period": [-4, 0, 4],
    },
    max_parameter_variations=100,
)
```

For every window this evaluates the Cartesian product around the selected
parameters on `validation_data`. The optimized center is reused rather than
simulated twice. These runs are diagnostic only: the runner never selects a
new parameter set from validation results. Non-numeric parameters remain
unchanged. Parameter and result constraints also apply to every variation.
Results are available from `window_result.parameter_stability_result` and are
saved to JSON and CSV. Use `max_parameter_variations` to prevent accidental
combination explosion.

Enable terminal progress with `progress=True`, or pass a `CLIProgress` instance
when output should be redirected to another stream:

```python
runner = WalkForwardRunner(
    ...,
    progress=True,
)
result = runner.run(dataset)
```

Both a single `SimulationResult` and a complete `WalkForwardResult` can be
saved. CSV output uses `rowlogger`; JSON retains nested trials, trades, and
equity curves.

```python
result.save_csv("results/wfo.csv")
result.save_json("results/wfo.json")
```

The WFO result contains `aggregate_metrics` calculated by chronologically
joining validation equity curves. Every window result also records the start
and end of its training, optimization, and validation periods.

Parameter and simulation-result constraints are supplied by the user. A
constraint may return `True`/`None` for acceptance, `False` for rejection, a
rejection message, or an explicit `ConstraintResult`.

```python
def periods_are_ordered(params):
    if params["fast_period"] >= params["slow_period"]:
        return "fast_period must be smaller than slow_period"

def drawdown_is_acceptable(result):
    if result.metrics["max_drawdown_pct"] > 20:
        return "max_drawdown_pct exceeds 20"

runner = WalkForwardRunner(
    ...,
    parameter_constraints=[periods_are_ordered],
    result_constraints=[drawdown_is_acceptable],
)
```

Rejected trials remain in `OptimizationResult.trials` with `feasible=False`, a
status, and violation messages. They are also retained as `trial` rows in CSV
and as nested trial objects in JSON. Custom optimization algorithms can be used
by implementing the public `Optimizer` protocol and returning an
`OptimizationResult` from `optimize()`.

```python
optimization_result.save_csv("results/trials.csv")
optimization_result.save_json("results/trials.json")
```

## USDJPY M15 end-to-end example

The repository includes a confirmed-bar EMA crossover example that runs the
included MT5 CSV data through dataset creation, constrained TPE optimization,
walk-forward validation, aggregate metrics, result serialization, and
validation-only trade logging.

```powershell
python examples/run_usdjpy_m15_wfo.py
```

It writes the following user-selectable output paths:

```text
results/usdjpy_m15_ema_cross/
├── wfo_result.csv
├── wfo_result.json
└── validation_trades.csv
```

The example is intentionally a verification strategy, not a recommendation to
trade or an assertion that the EMA parameters will remain profitable.

## Local dashboard

Open a saved WFO result in the read-only FastAPI dashboard:

```powershell
trading-wfo dashboard `
  --result results/usdjpy_m15_ema_cross/wfo_result.json `
  --market-data-dir mt5_data/USDJPY- `
  --log-dir results/usdjpy_m15_ema_cross/logs
```

Then visit `http://127.0.0.1:8000`. The dashboard is organized into four
sections:

- **Overview** joins validation equity and pips and compares optimization with
  validation profit across windows.
- **Windows** shows periods, best parameters, constraints, and optimization
  trials for the selected window.
- **Robustness** shows the validation distribution around each optimized
  parameter set.
- **Trades** analyzes all out-of-sample trades with summary metrics, pips
  distribution, cumulative profit/pips, side/exit/window/metadata breakdowns,
  filters, and an execution/metadata inspector. When `--market-data-dir` is
  set, selecting a trade also shows candles, Bid/Ask, and entry/exit markers.
  Higher-timeframe candle panes can be added or removed in the browser. Numeric
  columns from market data or RowLogger CSV files under `--log-dir` can be
  overlaid on price or displayed in independent panes. The Plotly mode bar and
  mouse controls provide zoom, pan, reset, and PNG export.

Both directory options search CSV files recursively. Candle timeframes must be
equal to or coarser than the source CSV interval; the dashboard never creates a
finer timeframe than the supplied data.

The dashboard reads the JSON again on each browser refresh. The default host
is loopback-only; binding to another host requires the explicit
`--allow-remote` option.

`params["strategy_base"]["lookback_bars"]` controls how many confirmed input
bars are included in `context["bars"]`. Context account fields use standard
trading names such as `realized_profit`, `unrealized_profit`, `buying_power`,
`long_positions`, and `short_positions`.

`reinvestment_rate` controls how much positive realized profit becomes trading
capital. The remainder is recorded as `reserved_profit`; losses always reduce
trading capital in full. Close requests are processed before new orders, so
reinvested profit is available to orders executed on the same bar.

Spread is already represented by the supplied Bid and Ask columns. Optional
commission and adverse market-order slippage are configured separately; both
default to zero for commission-free Japanese FX accounts.

```python
from trading_wfo import ExecutionConfig

execution_config = ExecutionConfig(
    commission_per_lot_per_side=0,  # account-currency units per lot per fill
    slippage_pips=0,
)
simulator = TradingSimulator(
    params,
    trade_logger,
    data,
    execution_config=execution_config,
)
```

Slippage increases long entry/short exit prices and decreases short entry/long
exit prices. Commission is charged on both entry and exit. Closed trade records
contain `gross_profit`, `commission`, and net `realized_profit`; simulation
metrics contain `total_commission`.

`ExecutionConfig.minimum_lot_size` defaults to `0.01` and can be changed for
the user's broker. Invalid market data (empty, non-finite prices, or Ask below
Bid), insufficient rows for `lookback_bars`, and unknown position close
requests raise explicit errors. Strategy failures are wrapped in
`StrategyExecutionError` with bar step and timestamp information.

Insufficient margin is a normal order rejection rather than a fatal simulator
error. It is available in `SimulationResult.rejected_orders` with required and
available funds, and counted by `metrics["rejected_order_count"]`. File-system
write failures raise `ResultSaveError` containing the requested target path.

Trade events can be written directly to CSV with the public `TradeLogger`,
which uses `rowlogger` internally:

```python
from trading_wfo import TradeLogger

trade_logger = TradeLogger("results/trades.csv")
simulator = TradingSimulator(params, trade_logger, data)
result = simulator.run(strategy)  # saves the CSV when the run finishes
```

Each order rejection, position opening, and position closing is stored as one
row. Close rows distinguish `close_request`, `stop_out`, and `end_of_data`, and
include execution price, realized profit/pips, account balance, metadata, and
the cumulative realized result. Pass `None` instead of a logger when no file is
needed. Use `TradeLogger(path, append=True)` to append later simulation runs to
an existing CSV with the same schema.
