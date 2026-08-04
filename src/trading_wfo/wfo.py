from .metrics import calculate_metrics
from .constraints import evaluate_constraints
from .optimizer import Optimizer
from .progress import CLIProgress, CompositeProgress, ProgressTracker
from .result import (
    ObjectiveResult,
    ParameterStabilityResult,
    ParameterVariationResult,
    WalkForwardResult,
    WalkForwardWindowResult,
)
from .robustness import generate_parameter_variations
from .window import DatasetMode, TradingDataset


class WalkForwardRunner:
    """Run chronological windows sequentially; an optimizer may parallelize trials."""

    def __init__(
        self,
        *,
        simulator_factory,
        strategy_factory,
        optimizer,
        score=None,
        trainer=None,
        n_trials=50,
        progress=False,
        parameter_constraints=(),
        result_constraints=(),
        validation_simulator_factory=None,
        parameter_variations=None,
        max_parameter_variations=100,
        optimization_workers=None,
        progress_path=None,
    ):
        self.simulator_factory = simulator_factory
        self.validation_simulator_factory = (
            simulator_factory
            if validation_simulator_factory is None
            else validation_simulator_factory
        )
        self.strategy_factory = strategy_factory
        self.optimizer = optimizer
        if not isinstance(optimizer, Optimizer):
            raise TypeError("optimizer must implement optimize()")
        self.score = (
            (lambda result: result.metrics["net_profit"])
            if score is None
            else score
        )
        self.trainer = trainer
        self.n_trials = n_trials
        self.parameter_constraints = tuple(parameter_constraints)
        self.result_constraints = tuple(result_constraints)
        self.parameter_variations = (
            None if parameter_variations is None else dict(parameter_variations)
        )
        self.max_parameter_variations = max_parameter_variations
        if optimization_workers is not None:
            if optimization_workers <= 0:
                raise ValueError("optimization_workers must be positive")
            if not hasattr(self.optimizer, "workers"):
                raise TypeError("optimization_workers requires an optimizer with workers support")
            self.optimizer.workers = optimization_workers
        self.optimization_workers = getattr(self.optimizer, "workers", 1)
        console_progress = (
            CLIProgress()
            if progress is True
            else None if progress is False else progress
        )
        file_progress = (
            None if progress_path is None else
            ProgressTracker(progress_path, workers=self.optimization_workers)
        )
        reporters = [item for item in (console_progress, file_progress) if item is not None]
        self.progress = None if not reporters else reporters[0] if len(reporters) == 1 else CompositeProgress(*reporters)

    def run(self, dataset: TradingDataset):
        if not isinstance(dataset, TradingDataset):
            raise TypeError("dataset must be a TradingDataset")
        if dataset.mode is not DatasetMode.WALK_FORWARD:
            raise ValueError("WalkForwardRunner requires a walk-forward dataset")

        windows = list(dataset.windows())
        total_windows = len(windows)
        if self.progress is not None:
            self.progress.wfo_started(total_windows)
        window_results = []
        for window in windows:
            if self.progress is not None:
                self.progress.window_started(window.index, total_windows)
            model = self._train_model(window.training_data)

            def objective(params):
                strategy = self.strategy_factory(params, model)
                simulator = self.simulator_factory(window.optimization_data)
                simulation_result = simulator.run(strategy)
                constraint_result = evaluate_constraints(
                    self.result_constraints, simulation_result
                )
                return ObjectiveResult(
                    score=(
                        self.score(simulation_result)
                        if constraint_result.feasible
                        else None
                    ),
                    metrics=simulation_result.metrics,
                    constraint_result=constraint_result,
                )

            optimization = self.optimizer.optimize(
                objective,
                n_trials=self.n_trials,
                parameter_constraints=self.parameter_constraints,
                progress=self.progress,
            )
            validation_strategy = self.strategy_factory(
                optimization.best_params, model
            )
            validation_simulator = self.validation_simulator_factory(
                window.validation_data
            )
            validation_result = validation_simulator.run(validation_strategy)
            validation_constraint_result = evaluate_constraints(
                self.result_constraints, validation_result
            )
            stability_result = self._evaluate_parameter_stability(
                window=window,
                model=model,
                center_params=optimization.best_params,
                center_result=validation_result,
                center_constraint_result=validation_constraint_result,
            )
            window_results.append(
                WalkForwardWindowResult(
                    index=window.index,
                    optimization_result=optimization,
                    validation_result=validation_result,
                    training_start=window.training_start,
                    training_end=window.training_end,
                    optimization_start=window.optimization_start,
                    optimization_end=window.optimization_end,
                    validation_start=window.validation_start,
                    validation_end=window.validation_end,
                    validation_constraint_result=validation_constraint_result,
                    parameter_stability_result=stability_result,
                )
            )
            if self.progress is not None:
                self.progress.window_completed(
                    window.index,
                    total_windows,
                    self.score(validation_result),
                )

        if self.progress is not None:
            self.progress.wfo_completed(total_windows)
        return WalkForwardResult(
            windows=window_results,
            aggregate_metrics=self._aggregate_metrics(window_results),
        )

    def _evaluate_parameter_stability(
        self,
        *,
        window,
        model,
        center_params,
        center_result,
        center_constraint_result,
    ):
        if self.parameter_variations is None:
            return None
        parameter_sets = generate_parameter_variations(
            center_params,
            self.parameter_variations,
            max_variations=self.max_parameter_variations,
        )
        results = []
        for params, offsets, is_center in parameter_sets:
            parameter_constraint = evaluate_constraints(
                self.parameter_constraints, params
            )
            if not parameter_constraint.feasible:
                results.append(
                    ParameterVariationResult(
                        params=params,
                        offsets=offsets,
                        score=None,
                        feasible=False,
                        status="parameter_constraint_failed",
                        violations=list(parameter_constraint.violations),
                        is_center=is_center,
                    )
                )
                continue
            if is_center:
                simulation_result = center_result
                constraint_result = center_constraint_result
            else:
                strategy = self.strategy_factory(params, model)
                simulator = self.simulator_factory(window.validation_data)
                simulation_result = simulator.run(strategy)
                constraint_result = evaluate_constraints(
                    self.result_constraints, simulation_result
                )
            results.append(
                ParameterVariationResult(
                    params=params,
                    offsets=offsets,
                    score=(
                        self.score(simulation_result)
                        if constraint_result.feasible
                        else None
                    ),
                    metrics=simulation_result.metrics,
                    feasible=constraint_result.feasible,
                    status=(
                        "completed"
                        if constraint_result.feasible
                        else "result_constraint_failed"
                    ),
                    violations=list(constraint_result.violations),
                    is_center=is_center,
                )
            )
        return ParameterStabilityResult(
            center_params=dict(center_params), variations=results
        )

    @staticmethod
    def _aggregate_metrics(window_results):
        if not window_results:
            return {"window_count": 0, "optimization_trial_count": 0}
        first_metrics = window_results[0].validation_result.metrics
        initial_balance = float(first_metrics["initial_balance"])
        running_balance = initial_balance
        combined_curve = []
        combined_trades = []
        for window in window_results:
            result = window.validation_result
            local_initial = float(result.metrics["initial_balance"])
            offset = running_balance - local_initial
            for point in result.equity_curve:
                combined_curve.append(
                    {
                        "time": point["time"],
                        "balance": float(point["balance"]) + offset,
                        "equity": float(point["equity"]) + offset,
                    }
                )
            combined_trades.extend(result.trades)
            running_balance += float(result.metrics["net_profit"])
        metrics = calculate_metrics(
            initial_balance=initial_balance,
            final_balance=running_balance,
            trades=combined_trades,
            equity_curve=combined_curve,
        )
        metrics.update(
            {
                "window_count": len(window_results),
                "optimization_trial_count": sum(
                    len(window.optimization_result.trials)
                    for window in window_results
                ),
                "parameter_variation_count": sum(
                    len(window.parameter_stability_result.variations)
                    if window.parameter_stability_result is not None
                    else 0
                    for window in window_results
                ),
            }
        )
        return metrics

    def _train_model(self, training_data):
        if training_data is None:
            return None
        if self.trainer is None:
            raise ValueError(
                "trainer is required when training_period is configured"
            )
        if hasattr(self.trainer, "fit"):
            return self.trainer.fit(training_data)
        if callable(self.trainer):
            return self.trainer(training_data)
        raise TypeError("trainer must be callable or define fit(data)")
