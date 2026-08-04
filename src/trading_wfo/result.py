import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constraints import ConstraintResult

from rowlogger import RowLogger

from .models import to_serializable


def _json_value(value):
    value = to_serializable(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


@dataclass
class SimulationResult:
    """Result of one simulation over one supplied data section."""

    metrics: Dict[str, float] = field(default_factory=dict)
    trades: List[Dict[str, Any]] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    rejected_orders: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self):
        return _json_value(asdict(self))

    def save_json(self, filepath, *, indent=2):
        _save_json(self.to_dict(), filepath, indent=indent)

    def save_csv(self, filepath):
        logger = RowLogger()
        logger.add({"record_type": "metrics", **_json_value(self.metrics)})
        logger.next_row()
        for trade in self.trades:
            logger.add({"record_type": "trade", **_json_value(trade)})
            logger.next_row()
        for rejection in self.rejected_orders:
            logger.add(
                {"record_type": "rejected_order", **_json_value(rejection)}
            )
            logger.next_row()
        for point in self.equity_curve:
            logger.add({"record_type": "equity", **_json_value(point)})
            logger.next_row()
        _save_rowlogger(logger, filepath)


@dataclass
class WalkForwardResult:
    """Combined results from all walk-forward validation windows."""

    windows: List["WalkForwardWindowResult"] = field(default_factory=list)
    aggregate_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return _json_value(asdict(self))

    def save_json(self, filepath, *, indent=2):
        _save_json(self.to_dict(), filepath, indent=indent)

    def save_csv(self, filepath):
        logger = RowLogger()
        summary = {"record_type": "summary", "window_index": None}
        summary.update(
            {f"aggregate_{key}": value for key, value in self.aggregate_metrics.items()}
        )
        logger.add(summary)
        logger.next_row()
        for window in self.windows:
            row = {
                "record_type": "window",
                "window_index": window.index,
                "training_start": window.training_start,
                "training_end": window.training_end,
                "optimization_start": window.optimization_start,
                "optimization_end": window.optimization_end,
                "validation_start": window.validation_start,
                "validation_end": window.validation_end,
                "best_params": window.best_params,
                "optimization_score": window.optimization_score,
                "validation_feasible": window.validation_constraint_result.feasible,
                "validation_violations": list(
                    window.validation_constraint_result.violations
                ),
            }
            row.update(
                {
                    f"validation_{key}": value
                    for key, value in window.validation_result.metrics.items()
                }
            )
            logger.add(_json_value(row))
            logger.next_row()
            for trial in window.optimization_result.trials:
                logger.add(
                    _json_value(
                        {
                            "record_type": "trial",
                            "window_index": window.index,
                            "trial_number": trial.number,
                            "trial_params": trial.params,
                            "trial_score": trial.score,
                            "trial_metrics": trial.metrics,
                            "trial_feasible": trial.feasible,
                            "trial_status": trial.status,
                            "trial_violations": trial.violations,
                        }
                    )
                )
                logger.next_row()
            stability = window.parameter_stability_result
            if stability is not None:
                for variation in stability.variations:
                    logger.add(
                        _json_value(
                            {
                                "record_type": "parameter_variation",
                                "window_index": window.index,
                                "variation_params": variation.params,
                                "variation_offsets": variation.offsets,
                                "variation_score": variation.score,
                                "variation_metrics": variation.metrics,
                                "variation_feasible": variation.feasible,
                                "variation_status": variation.status,
                                "variation_violations": variation.violations,
                                "variation_is_center": variation.is_center,
                            }
                        )
                    )
                    logger.next_row()
        _save_rowlogger(logger, filepath)


@dataclass
class OptimizationTrial:
    number: int
    params: Dict[str, Any]
    score: Optional[float]
    metrics: Dict[str, Any] = field(default_factory=dict)
    feasible: bool = True
    status: str = "completed"
    violations: List[str] = field(default_factory=list)


@dataclass
class ObjectiveResult:
    score: Optional[float]
    metrics: Dict[str, Any] = field(default_factory=dict)
    constraint_result: ConstraintResult = field(
        default_factory=ConstraintResult.accepted
    )


@dataclass
class OptimizationResult:
    best_params: Dict[str, Any]
    best_score: float
    trials: List[OptimizationTrial] = field(default_factory=list)

    def to_dict(self):
        return _json_value(asdict(self))

    def save_json(self, filepath, *, indent=2):
        _save_json(self.to_dict(), filepath, indent=indent)

    def save_csv(self, filepath):
        logger = RowLogger()
        logger.add(
            _json_value(
                {
                    "record_type": "summary",
                    "best_params": self.best_params,
                    "best_score": self.best_score,
                }
            )
        )
        logger.next_row()
        for trial in self.trials:
            logger.add(
                _json_value(
                    {
                        "record_type": "trial",
                        "trial_number": trial.number,
                        "trial_params": trial.params,
                        "trial_score": trial.score,
                        "trial_metrics": trial.metrics,
                        "trial_feasible": trial.feasible,
                        "trial_status": trial.status,
                        "trial_violations": trial.violations,
                    }
                )
            )
            logger.next_row()
        _save_rowlogger(logger, filepath)


@dataclass
class ParameterVariationResult:
    params: Dict[str, Any]
    offsets: Dict[str, Any]
    score: Optional[float]
    metrics: Dict[str, Any] = field(default_factory=dict)
    feasible: bool = True
    status: str = "completed"
    violations: List[str] = field(default_factory=list)
    is_center: bool = False


@dataclass
class ParameterStabilityResult:
    center_params: Dict[str, Any]
    variations: List[ParameterVariationResult] = field(default_factory=list)


@dataclass
class WalkForwardWindowResult:
    index: int
    optimization_result: OptimizationResult
    validation_result: SimulationResult
    training_start: Optional[Any] = None
    training_end: Optional[Any] = None
    optimization_start: Optional[Any] = None
    optimization_end: Optional[Any] = None
    validation_start: Optional[Any] = None
    validation_end: Optional[Any] = None
    validation_constraint_result: ConstraintResult = field(
        default_factory=ConstraintResult.accepted
    )
    parameter_stability_result: Optional[ParameterStabilityResult] = None

    @property
    def best_params(self):
        return self.optimization_result.best_params

    @property
    def optimization_score(self):
        return self.optimization_result.best_score


def _save_json(payload, filepath, *, indent):
    from .errors import ResultSaveError

    path = Path(filepath)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(
                payload, file, ensure_ascii=False, indent=indent, allow_nan=False
            )
        for attempt in range(40):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                if attempt == 39:
                    raise
                time.sleep(0.025)
    except OSError as error:
        raise ResultSaveError(path, error) from error


def _save_rowlogger(logger, filepath):
    from .errors import ResultSaveError

    path = Path(filepath)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.save_csv(path)
    except OSError as error:
        raise ResultSaveError(path, error) from error
