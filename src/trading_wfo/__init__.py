"""Walk-forward validation and optimization for trading strategies."""

from .account import AccountConfig
from .constraints import ConstraintResult
from .execution import ExecutionConfig
from .errors import ResultSaveError, StrategyExecutionError, TradingWFOError
from .models import Action, CloseRequest, Order, Position, Side
from .optimizer import (
    CategoricalParameter,
    FloatParameter,
    IntParameter,
    Optimizer,
    TPEOptimizer,
)
from .progress import CLIProgress, CompositeProgress, ProgressTracker
from .result import (
    OptimizationResult,
    OptimizationTrial,
    ObjectiveResult,
    SimulationResult,
    WalkForwardResult,
    WalkForwardWindowResult,
    ParameterStabilityResult,
    ParameterVariationResult,
)
from .simulator import TradingSimulator
from .strategy import Strategy, StrategyContext
from .trade_logger import TradeLogger
from .wfo import WalkForwardRunner
from .window import DatasetMode, TradingDataset, WalkForwardWindow, WindowPeriod

__all__ = [
    "AccountConfig",
    "Action",
    "CloseRequest",
    "CategoricalParameter",
    "CLIProgress",
    "CompositeProgress",
    "ProgressTracker",
    "ConstraintResult",
    "ExecutionConfig",
    "ResultSaveError",
    "StrategyExecutionError",
    "Strategy",
    "StrategyContext",
    "TradingWFOError",
    "FloatParameter",
    "IntParameter",
    "Order",
    "OptimizationResult",
    "OptimizationTrial",
    "ObjectiveResult",
    "Optimizer",
    "Position",
    "SimulationResult",
    "Side",
    "TradingSimulator",
    "TradeLogger",
    "TPEOptimizer",
    "WalkForwardResult",
    "WalkForwardRunner",
    "WalkForwardWindowResult",
    "ParameterStabilityResult",
    "ParameterVariationResult",
    "DatasetMode",
    "TradingDataset",
    "WalkForwardWindow",
    "WindowPeriod",
]

__version__ = "0.3.0"
