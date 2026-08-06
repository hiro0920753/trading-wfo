from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ExecutionConfig:
    """Market execution costs applied to user-supplied Bid/Ask quotes."""

    commission_per_lot_per_side: float = 0.0
    additional_spread_pips: float = 0.0
    entry_slippage_pips: float = 0.0
    exit_slippage_pips: float = 0.0
    minimum_lot_size: float = 0.01

    def __post_init__(self):
        values = (
            self.commission_per_lot_per_side,
            self.additional_spread_pips,
            self.entry_slippage_pips,
            self.exit_slippage_pips,
            self.minimum_lot_size,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("execution configuration values must be finite")
        if self.commission_per_lot_per_side < 0:
            raise ValueError(
                "commission_per_lot_per_side must not be negative"
            )
        if self.additional_spread_pips < 0:
            raise ValueError("additional_spread_pips must not be negative")
        if self.entry_slippage_pips < 0:
            raise ValueError("entry_slippage_pips must not be negative")
        if self.exit_slippage_pips < 0:
            raise ValueError("exit_slippage_pips must not be negative")
        if self.minimum_lot_size <= 0:
            raise ValueError("minimum_lot_size must be positive")
