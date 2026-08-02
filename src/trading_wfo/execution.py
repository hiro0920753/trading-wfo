from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ExecutionConfig:
    """Market execution costs; both defaults match commission-free accounts."""

    commission_per_lot_per_side: float = 0.0
    slippage_pips: float = 0.0
    minimum_lot_size: float = 0.01

    def __post_init__(self):
        values = (
            self.commission_per_lot_per_side,
            self.slippage_pips,
            self.minimum_lot_size,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("execution configuration values must be finite")
        if self.commission_per_lot_per_side < 0:
            raise ValueError(
                "commission_per_lot_per_side must not be negative"
            )
        if self.slippage_pips < 0:
            raise ValueError("slippage_pips must not be negative")
        if self.minimum_lot_size <= 0:
            raise ValueError("minimum_lot_size must be positive")
