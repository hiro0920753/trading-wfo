from pathlib import Path

from trading_wfo import (
    CategoricalParameter,
    ExecutionConfig,
    IntParameter,
    TPEOptimizer,
    TradeLogger,
    TradingDataset,
    TradingSimulator,
    WalkForwardRunner,
)

try:
    from examples.ema_cross_strategy import EmaCrossStrategy
except ModuleNotFoundError:  # direct: python examples/run_usdjpy_m15_wfo.py
    from ema_cross_strategy import EmaCrossStrategy


PARAMS = {
    "common": {
        "units_per_lot": 100_000,
        "symbol": "USDJPY",
        "price_per_pip": 0.01,
    },
    "strategy_base": {"lookback_bars": 41, "leverage": 25},
    "asset": {"balance": 1_000_000, "stop_out_level": 50},
}


def run(
    data_directory,
    output_directory,
    *,
    n_trials=20,
    progress=True,
    parameter_variations=None,
):
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    dataset = TradingDataset.from_csv(
        data_directory,
        optimization_period="2w",
        validation_period="1w",
    )
    execution_config = ExecutionConfig(
        commission_per_lot_per_side=0,
        slippage_pips=0,
    )
    validation_log_path = output_directory / "validation_trades.csv"
    validation_log_path.unlink(missing_ok=True)
    validation_log = TradeLogger(validation_log_path, append=True)
    optimizer = TPEOptimizer(
        {
            "fast_period": IntParameter(5, 20),
            "slow_period": IntParameter(10, 40),
            "lot_size": CategoricalParameter([0.01, 0.02, 0.05]),
        },
        seed=42,
        n_startup_trials=5,
    )
    runner = WalkForwardRunner(
        simulator_factory=lambda data: TradingSimulator(
            PARAMS, None, data, execution_config=execution_config
        ),
        validation_simulator_factory=lambda data: TradingSimulator(
            PARAMS, validation_log, data, execution_config=execution_config
        ),
        strategy_factory=lambda params, model: EmaCrossStrategy(**params),
        optimizer=optimizer,
        parameter_constraints=[
            lambda params: (
                None
                if params["fast_period"] < params["slow_period"]
                else "fast_period must be smaller than slow_period"
            )
        ],
        score=lambda result: (
            result.metrics["net_profit"]
            - 1.5 * result.metrics["max_drawdown"]
        ),
        n_trials=n_trials,
        progress=progress,
        parameter_variations=parameter_variations,
    )
    result = runner.run(dataset)
    result.save_csv(output_directory / "wfo_result.csv")
    result.save_json(output_directory / "wfo_result.json")
    return result


if __name__ == "__main__":
    repository = Path(__file__).resolve().parents[1]
    run(
        repository / "mt5_data" / "USDJPY-" / "M15",
        repository / "results" / "usdjpy_m15_ema_cross",
        parameter_variations={
            "fast_period": [-2, 0, 2],
            "slow_period": [-4, 0, 4],
        },
    )
