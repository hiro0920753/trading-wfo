# trading-wfo
A Python library for backtesting, walk-forward optimization, and out-of-sample
robustness checks of trading strategies. Supply your own market data and strategy;
optionally train a machine-learning model before each optimization window.

Requires Python 3.10 or newer.

> **Alpha release:** validate results independently before using them for any
> trading decision. This package does not provide investment advice.

## Current release: 0.6.2

Version **0.6.2** updates this documentation and PyPI description. Runtime behavior
is unchanged from **0.6.1**, which includes:

- Per-order margin checks that account for earlier fills, commissions, and
  unrealized losses in the same order batch.
- Scheduled capital contributions, separate cash-flow records, and
  contribution-adjusted profit and time-weighted return metrics.
- Full or partial position closes by lot size or fraction.
- Configurable profit reinvestment, reserve refills, and opt-in temporary
  reserve funding for orders, including rejection and repayment fixes.
- Delayed-entry stress scenarios for both callable and `on_bar` strategies,
  plus consistent contribution scheduling for timezone-naive market data.

## What you can do

- Run one backtest or chronological training / optimization / validation windows.
- Search parameters with TPE or a finite grid, apply constraints, and inspect
  parameter stability without selecting a new winner from validation results.
- Model market and limit orders, spread, commission, slippage, margin, and stop-out.
- Evaluate frozen out-of-sample spread, entry-delay, and parameter-offset
  scenarios; optionally inspect trade-PnL Monte Carlo diagnostics.
- Export trades, equity curves, optimization trials, and training artifacts to
  JSON/CSV, and inspect results in a local dashboard.

Each simulator trades **one configured instrument**. Additional symbols are
observation inputs; shared multi-currency execution and currency conversion
require an external portfolio engine.

## Installation

```bash
python -m pip install --upgrade trading-wfo
```

Documentation:

- [Quick start](https://github.com/hiro0920753/trading-wfo/blob/v0.6.2/docs/quickstart.md)
- [Strategy API](https://github.com/hiro0920753/trading-wfo/blob/v0.6.2/docs/strategy-api.md)
- [Simulator semantics and look-ahead prevention](https://github.com/hiro0920753/trading-wfo/blob/v0.6.2/docs/simulator-semantics.md)
- [Changelog](https://github.com/hiro0920753/trading-wfo/blob/v0.6.2/CHANGELOG.md)

## Minimal runnable backtest

This example uses a small synthetic quote series and requires no downloaded data.
It opens one long position on the first executable bar and closes it at the end.

```python
import pandas as pd
from trading_wfo import Action, Order, Side, TradingSimulator

prices = [150.00, 150.02, 150.05, 150.03, 150.08]
data = pd.DataFrame({
    "time": pd.date_range("2026-01-01", periods=5, freq="15min", tz="UTC"),
    "bid": prices,
    "ask": [price + 0.01 for price in prices],
    "open": prices, "high": prices, "low": prices, "close": prices,
})
params = {
    "common": {"symbol": "USDJPY", "units_per_lot": 100_000, "price_per_pip": 0.01},
    "strategy_base": {"lookback_bars": 1, "leverage": 25},
    "asset": {"balance": 100_000},
}

def strategy(context):
    if context["step_index"] == 0:
        return Action(orders=[Order(side=Side.LONG, lot_size=0.01)])
    return Action()

result = TradingSimulator(params, None, data).run(strategy)
print(result.metrics["total_trades"])          # 1
print(round(result.metrics["net_profit"], 2))  # 50.0, in quote-currency units (JPY)
```

## Walk-forward datasets

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

## Scheduled contributions

Periodic external contributions can be applied before order processing at the
first available bar on or after each scheduled timestamp:

```python
from trading_wfo import AccountConfig, ContributionSchedule

account_config = AccountConfig(
    initial_balance=100_000,
    leverage=25,
    units_per_lot=100_000,
    price_per_pip=0.01,
    contribution_schedules=(
        ContributionSchedule(
            amount=50_000,
            period="1mo",
            start="2026-01-25T00:00:00+09:00",
        ),
    ),
)
```

When `start` is omitted, the first contribution is one `period` after the
simulation's first executable bar. `end` is optional and inclusive. Results
record each event in `cash_flows`; `net_profit` excludes contributions, while
`balance_change`, `total_contributions`, and `time_weighted_return_pct` report
cash growth and contribution-adjusted performance separately. JSON parameters
may supply the same fields under `asset.contribution_schedules`.
For contribution schedules, market timestamps without a timezone are interpreted
as UTC. Schedule dates without a timezone use the market data's timezone;
explicit timezone offsets are converted to that timezone before comparison.


## Orders and partial closes

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

Omit the size to close the entire position, or specify one partial-close mode:

```python
Action(close_requests=[CloseRequest(position_id=3)])                 # all
Action(close_requests=[CloseRequest(position_id=3, lot_size=0.02)]) # fixed size
Action(close_requests=[CloseRequest(position_id=3, fraction=0.5)])  # 50%
```

`lot_size` and `fraction` are mutually exclusive. A partial close records one
trade fragment with `is_partial_close=true` and `remaining_lot_size`, charges
commission only on the closed size, and keeps the remaining position's ID,
entry price, metadata, and MFE/MAE path. Both the closed and remaining sizes
must respect `ExecutionConfig.minimum_lot_size`.

A single simulation calls the strategy at time `t` with confirmed bars through
`t-1` and the current Bid/Ask from `t`. Market orders and close requests are
executed immediately using that same `t` Bid/Ask, adjusted for configured
slippage. The current, still-forming bar is never included in `bars`.

```python
simulator = TradingSimulator(params, log, data)
result = simulator.run(
    strategy,
    result_path="results/backtest.json",
    live_update_interval=2.0,
)
```

Open the same dashboard for a single backtest result:

```bash
trading-wfo dashboard --result results/backtest.json
```

Backtest mode shows Overview, Equity, Pips, Trades, and Trade Inspector while
hiding the WFO-only Windows, Robustness, and Progress sections.
While the simulation runs, its compact progress file updates every two seconds
and after a trade closes. The full result snapshot refreshes every 60 seconds by
default (`live_result_interval`), and is written again when the run completes.

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
    result_path="results/wfo_result.json",
)
result = runner.run(dataset)
```

For each window, the runner optionally trains the AI model, performs TPE only
on `optimization_data`, and runs the selected parameters once on
`validation_data`. Trial history is available through
`window_result.optimization_result`; validation metrics are in
`window_result.validation_result.metrics`.

Windows run sequentially. Each simulator is created by your factory with its
own initial account; the runner does not carry account state or open positions
between validation windows. Aggregate results join window profit and equity
changes additively and are not a shared-account or compounded portfolio.
`optimization_workers` parallelizes only the optimization trials inside the
active window. After each validation window, `result_path` is
atomically replaced with the latest partial result. Its companion progress JSON
is updated as trials complete and both can be displayed while the run is active:

```bash
trading-wfo dashboard --result results/wfo_result.json
```

The dashboard refreshes profit, pips, equity, windows, robustness, and trades
after each completed window. It also reads `results/wfo_result.progress.json`
for trial completion, worker count, elapsed/remaining time, and the estimated
completion timestamp. Use `progress_path` and `--progress-file` only when the
tracker should be stored elsewhere.

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
locally supplied MT5 CSV data through dataset creation, constrained TPE optimization,
walk-forward validation, aggregate metrics, result serialization, and
validation-only trade logging.

```powershell
python examples/run_usdjpy_m15_wfo.py
```

Run repository examples from a checkout, with market CSVs in the expected input
directory. The wheel does not bundle market history; the synthetic example above
works directly after installation.

It writes the following user-selectable output paths:

```text
results/usdjpy_m15_ema_cross/
├── wfo_result.csv
├── wfo_result.json
└── validation_trades.csv
```

The example is intentionally a verification strategy, not a recommendation to
trade or an assertion that the EMA parameters will remain profitable.

## Machine-learning training -> optimization -> validation example

`WalkForwardRunner` can fit a user-supplied machine-learning or DNN model before
the trading-parameter search in every chronological window. The fitted model is
passed to every optimization trial in that window and then to the selected
strategy for one validation run. The next window repeats the complete sequence
with its own earlier training section.

```powershell
python examples/ml_direction_wfo.py
python examples/ml_direction_wfo.py --validation-ratio 0.30 --epochs 500
```

This self-contained example uses a tiny NumPy logistic classifier so it needs no
ML dependency beyond the package requirements. Replace `LogisticDirectionTrainer.fit`
with a scikit-learn estimator or a PyTorch/TensorFlow training function and return
the fitted model. Return `TrainingResult(model, artifacts)` to save per-window
weights, train/valid loss, sample counts, seeds, or other JSON-serializable audit
data in both WFO JSON and the window rows of WFO CSV. Model architecture and training settings should be frozen before
the run; the built-in optimizer searches the subsequent trading parameters and
does not retrain the model for every trial.

The example's `--validation-ratio` reserves the chronological tail of each AI
training section for internal model validation. It is not the WFO forward
section. The selected ratio, epoch count, and learning rate are recorded in
every window's `training_artifacts`.

## Local dashboard

Open a saved WFO result in the read-only FastAPI dashboard:

```powershell
trading-wfo dashboard `
  --result results/usdjpy_m15_ema_cross/wfo_result.json `
  --market-data-dir mt5_data/USDJPY- `
  --log-dir results/usdjpy_m15_ema_cross/logs
```

Then visit `http://127.0.0.1:8000`. The WFO dashboard is organized into five
sections:

- **Overview** joins validation equity and pips and compares optimization with
  validation profit across windows.
- **Windows** shows periods, best parameters, constraints, and optimization
  trials for the selected window.
- **Robustness** shows parameter stability, frozen stress scenarios, and
  optional Monte Carlo diagnostics.
- **Progress** shows optimization progress, workers, and elapsed/remaining time.
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

### Reserve refill and temporary order funding

```python
account_config = AccountConfig(
    initial_balance=100_000,
    leverage=25,
    units_per_lot=100_000,
    price_per_pip=0.01,
    reinvestment_rate=0.5,
    reserve_refill_threshold=50_000,
    reserve_refill_target=100_000,
    reserve_margin_topup_metadata_key="use_reserve",
)

# Pass account_config to TradingSimulator(..., account_config=account_config).
order = Order(Side.LONG, 0.01, metadata={"use_reserve": True})
```

After realized profit or loss, the refill rule moves available reserve into
trading capital when it is below the threshold, up to the target. A zero
threshold disables refills. Temporary order funding is separately opt-in through
the configured metadata key: it covers only the shortfall, and only if both the
reserve and account free margin can cover the full requirement. An unfundable
order is rejected without transferring reserve. Unused temporary funding is
returned on close, with losses reducing the repayment; partial closes allocate
funding proportionally. These internal transfers are not external contributions.

Results expose `final_trading_capital`, `reserved_profit`, `reserve_refill_total`,
`reserve_margin_topup_total`, `reserve_margin_topup_count`, and
`reserve_margin_topup_returned` for inspection.

## Execution costs and logging

Spread is represented by the supplied Bid and Ask columns. Optional spread
stress, commission, and adverse market-order slippage are configured
separately; all default to zero for commission-free Japanese FX accounts.

```python
from trading_wfo import ExecutionConfig

execution_config = ExecutionConfig(
    commission_per_lot_per_side=0,  # account-currency units per lot per fill
    additional_spread_pips=0,
    entry_slippage_pips=0,
    exit_slippage_pips=0,
)
simulator = TradingSimulator(
    params,
    trade_logger,
    data,
    execution_config=execution_config,
)
```

Additional spread increases Ask while leaving Bid unchanged, and the effective
quote is also passed to the strategy. Slippage increases long entry/short exit
prices and decreases short entry/long exit prices. Commission is charged on
both entry and exit. Closed trade records
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

## Multiple market inputs and limit orders

The simulator accepts either one DataFrame or a mapping keyed by symbol. The
configured `common.symbol` is the execution instrument; the remaining markets
are causal information inputs. At quote time `t`, each market context exposes
only OHLC bars confirmed before `t`:

```python
simulator = TradingSimulator(params, logger, {
    "USDJPY-": usdjpy,
    "EURJPY-": eurjpy,
    "EURUSD-": eurusd,
})

def strategy(context):
    return Action(orders=[Order(
        Side.LONG, 0.1,
        order_type=OrderType.LIMIT,
        limit_price=context["bid"] - 0.05,
        expires_at=context["time"] + 3600,
    )])
```

Pending orders are visible in `context["pending_orders"]` and can be removed
with `Action(cancel_order_ids=[...])`. Numeric epoch seconds and datetime-like
expiration values are supported. A submitted limit is not matched against the
same bar's unknown high/low; matching starts when a later bar is confirmed.
Long limits fill when that bar's low reaches the limit, and short limits when
its high reaches the limit. The conservative fill price is exactly the limit.

Orders for an auxiliary symbol are rejected explicitly. Supporting portfolio
execution across instruments requires per-symbol pip size, contract size,
margin currency, and account-currency conversion; accepting such orders
without those specifications would produce incorrect P&L and margin.

## Frozen OOS robustness suite

Use `robustness=` to evaluate stress scenarios **after** each window selects its
parameters. This adds no optimization trials and never chooses a new winner
from stressed OOS results. Existing `parameter_variations` can still be used.

```python
from trading_wfo import RobustnessConfig, StressScenario, WalkForwardRunner

runner = WalkForwardRunner(
    simulator_factory=simulator_factory,
    strategy_factory=strategy_factory,
    optimizer=optimizer,
    robustness=RobustnessConfig(
        scenarios=(
            StressScenario("spread_x1.25", spread_multiplier=1.25),
            StressScenario("spread_x1.5", spread_multiplier=1.5),
            StressScenario("spread_x2", spread_multiplier=2.0),
            StressScenario("entry_1bar_later", entry_delay_bars=1),
            # Only when your optimized parameter is expressed in minutes:
            StressScenario("start_plus15m", parameter_offsets={"start_minute": 15}),
            StressScenario("start_minus15m", parameter_offsets={"start_minute": -15}),
        ),
        monte_carlo_samples=1000,  # optional; 0 disables it
        seed=42,
    ),
)
result = runner.run(dataset)
result.save_json("results/robustness.json")
result.save_csv("results/robustness.csv")
```

Each window's `robustness_result` contains baseline/stress metrics, the profit
change versus baseline, constraint status, and UTC year/month realized PnL.
`result.robustness_summary` compares window sums, negative window counts,
worst **individual-window** DD, and profit excluding the best calendar year.
These appear on the dashboard's **Robustness** page. Old result files and
`robustness=None` remain supported. Extra full trade logs/equity curves are not
stored per scenario, keeping result files compact.

The spread multiplier expands the historical bid/ask around the same midpoint;
OHLC is untouched. Existing configured commissions and extra execution costs
still apply. Quote-based signals and spread filters see the stressed quotes,
so the set of trades can change; profit need not decline monotonically.
The raw input's separate `spread` column is not reinterpreted: strategies should
use the simulator's current `spread`/bid/ask rather than assume that column's units.

An entry delay waits for `entry_delay_bars` subsequent strategy evaluations.
One means approximately 15 minutes on regular M15 data, but gaps can make it
longer. The delayed market order uses the quote at release, not the old price.
Exits remain immediate. One entry batch is queued at a time; repeated entry
signals while waiting or releasing are suppressed. Close requests or
`stop_trading` discard the queued batch, and expired orders are discarded.
`context["delayed_entry_orders"]` exposes that queue to compatible strategies.
Signals are not re-qualified against proprietary filters on release. Custom
entry invalidation requires strategy-specific logic. LIMIT orders fail explicitly
in delayed scenarios; this is not a simulator for broker latency of pending orders.

Offset keys must be numeric keys in the selected parameters. Their units belong
to your strategy: use minutes for a minute-valued start time, not for an hour.
Parameter-constraint failures are recorded as skipped, not zero-profit tests.
Result-constraint failures retain their measured results and status. Exceptions
abort the run rather than silently producing successful-looking diagnostics.
Fitted models must support `deepcopy` when robustness is enabled; each scenario
receives an isolated copy. Randomness inside strategy/model factories must be
seeded by the caller for controlled comparisons.

Year/month rows attribute net trade PnL to **exit date**, not marked-to-market
period returns. Warmup rows do not become trades. Window sums are not a compounded
portfolio; overlapping validation windows are flagged because their sums count
observations repeatedly. A single partial calendar year cannot establish yearly
stability. Inspect its actual validation dates and trade counts.

Optional Monte Carlo reports per-window permutations and IID resampling of
baseline realized trade PnL, in account currency. Permutations keep total profit
constant; their DD changes with ordering. Bootstrap negative-profit frequency is
a sample diagnostic, **not** a forecast of future loss probability. Neither
method recovers intratrade risk or preserves market serial dependence.

Run `python examples/robustness_suite.py` for a small synthetic end-to-end example.
