# Quick start

## Minimal backtest

`TradingDataset` uses the complete DataFrame when no periods are configured.

```python
dataset = TradingDataset.from_dataframe(data)
simulator = TradingSimulator(PARAMS, None, dataset.backtest_data)
result = simulator.run(MyStrategy())
print(result.metrics)
```

See [`examples/minimal_backtest.py`](../examples/minimal_backtest.py) for a
self-contained executable example.

## Minimal walk-forward optimization

```python
dataset = TradingDataset.from_dataframe(
    data,
    optimization_period="14d",
    validation_period="7d",
)

optimizer = TPEOptimizer(
    {
        "fast_period": IntParameter(5, 20),
        "slow_period": IntParameter(10, 40),
    },
    seed=42,
)

runner = WalkForwardRunner(
    simulator_factory=lambda section: TradingSimulator(PARAMS, None, section),
    strategy_factory=lambda params, model: MyStrategy(**params),
    optimizer=optimizer,
    parameter_constraints=[
        lambda params: params["fast_period"] < params["slow_period"]
    ],
    n_trials=50,
    progress=True,
    optimization_workers=4,
    progress_path="results/wfo_result.progress.json",
)

result = runner.run(dataset)
result.save_json("results/wfo_result.json")
```

Optimization sees only `optimization_data`. The selected parameters are then
run once on the chronologically later `validation_data`. A configured training
period occurs before both and requires a user-provided trainer.

Walk-forward windows are deliberately sequential. Only trials within the
current optimization period are parallelized. Start the dashboard with the
same result path to monitor the Progress tab during a run.
