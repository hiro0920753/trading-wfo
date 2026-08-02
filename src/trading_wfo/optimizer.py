from dataclasses import dataclass
from typing import Any, Callable, Dict, Protocol, Sequence, Union, runtime_checkable

import optuna

from .constraints import evaluate_constraints
from .result import ObjectiveResult, OptimizationResult, OptimizationTrial


@runtime_checkable
class Optimizer(Protocol):
    def optimize(
        self,
        objective: Callable,
        *,
        n_trials: int = 50,
        parameter_constraints=(),
        progress=None,
    ) -> OptimizationResult:
        ...


@dataclass(frozen=True)
class FloatParameter:
    low: float
    high: float
    step: float = None
    log: bool = False

    def suggest(self, trial, name):
        return trial.suggest_float(
            name, self.low, self.high, step=self.step, log=self.log
        )


@dataclass(frozen=True)
class IntParameter:
    low: int
    high: int
    step: int = 1
    log: bool = False

    def suggest(self, trial, name):
        return trial.suggest_int(
            name, self.low, self.high, step=self.step, log=self.log
        )


@dataclass(frozen=True)
class CategoricalParameter:
    choices: Sequence[Any]

    def __post_init__(self):
        if not self.choices:
            raise ValueError("choices must not be empty")

    def suggest(self, trial, name):
        return trial.suggest_categorical(name, list(self.choices))


SearchParameter = Union[FloatParameter, IntParameter, CategoricalParameter]


class TPEOptimizer:
    """Optuna-backed Tree-structured Parzen Estimator optimizer."""

    def __init__(
        self,
        search_space: Dict[str, SearchParameter],
        *,
        direction="maximize",
        seed=42,
        n_startup_trials=10,
        n_jobs=1,
    ):
        if direction not in {"maximize", "minimize"}:
            raise ValueError("direction must be 'maximize' or 'minimize'")
        if not search_space:
            raise ValueError("search_space must not be empty")
        if not all(
            isinstance(spec, (FloatParameter, IntParameter, CategoricalParameter))
            for spec in search_space.values()
        ):
            raise TypeError("search_space values must be parameter definitions")
        self.search_space = dict(search_space)
        self.direction = direction
        self.seed = seed
        self.n_startup_trials = n_startup_trials
        self.n_jobs = n_jobs
        self.study = None

    def optimize(
        self,
        objective: Callable,
        *,
        n_trials=50,
        parameter_constraints=(),
        progress=None,
    ):
        if n_trials <= 0:
            raise ValueError("n_trials must be positive")

        sampler = optuna.samplers.TPESampler(
            seed=self.seed,
            n_startup_trials=self.n_startup_trials,
        )
        previous_verbosity = optuna.logging.get_verbosity()
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def wrapped(trial):
            params = {
                name: specification.suggest(trial, name)
                for name, specification in self.search_space.items()
            }
            parameter_result = evaluate_constraints(
                parameter_constraints, params
            )
            if not parameter_result.feasible:
                self._set_constraint_attrs(
                    trial,
                    feasible=False,
                    status="parameter_constraint_failed",
                    violations=parameter_result.violations,
                )
                raise optuna.TrialPruned()
            outcome = objective(params)
            if isinstance(outcome, ObjectiveResult):
                score = outcome.score
                metrics = outcome.metrics
                constraint_result = outcome.constraint_result
            elif isinstance(outcome, tuple):
                score, metrics = outcome
                constraint_result = None
            else:
                score = outcome
                metrics = {}
                constraint_result = None
            for key, value in metrics.items():
                trial.set_user_attr(f"metric:{key}", value)
            if constraint_result is not None and not constraint_result.feasible:
                self._set_constraint_attrs(
                    trial,
                    feasible=False,
                    status="result_constraint_failed",
                    violations=constraint_result.violations,
                )
                raise optuna.TrialPruned()
            if score is None:
                raise ValueError("a feasible objective must provide a score")
            self._set_constraint_attrs(
                trial, feasible=True, status="completed", violations=()
            )
            return float(score)

        callbacks = []
        if progress is not None:
            def report_progress(current_study, trial):
                completed_values = [
                    item.value
                    for item in current_study.trials
                    if item.value is not None
                ]
                best_score = (
                    None
                    if not completed_values
                    else (
                        max(completed_values)
                        if self.direction == "maximize"
                        else min(completed_values)
                    )
                )
                progress.trial_completed(
                    trial.number,
                    n_trials,
                    None if trial.value is None else float(trial.value),
                    best_score,
                    status=trial.user_attrs.get(
                        "status", trial.state.name.lower()
                    ),
                )
            callbacks.append(report_progress)
        try:
            study = optuna.create_study(
                direction=self.direction, sampler=sampler
            )
            study.optimize(
                wrapped,
                n_trials=n_trials,
                n_jobs=self.n_jobs,
                show_progress_bar=False,
                callbacks=callbacks,
            )
        finally:
            optuna.logging.set_verbosity(previous_verbosity)
        self.study = study
        trials = [
            OptimizationTrial(
                number=trial.number,
                params=dict(trial.params),
                score=None if trial.value is None else float(trial.value),
                metrics={
                    key.removeprefix("metric:"): value
                    for key, value in trial.user_attrs.items()
                    if key.startswith("metric:")
                },
                feasible=bool(trial.user_attrs.get("feasible", False)),
                status=trial.user_attrs.get(
                    "status", trial.state.name.lower()
                ),
                violations=list(trial.user_attrs.get("violations", [])),
            )
            for trial in study.trials
        ]
        feasible_trials = [trial for trial in trials if trial.feasible]
        if not feasible_trials:
            raise ValueError("optimization produced no feasible trials")
        return OptimizationResult(
            best_params=dict(study.best_params),
            best_score=float(study.best_value),
            trials=trials,
        )

    @staticmethod
    def _set_constraint_attrs(
        trial, *, feasible, status, violations
    ):
        trial.set_user_attr("feasible", feasible)
        trial.set_user_attr("status", status)
        trial.set_user_attr("violations", list(violations))
