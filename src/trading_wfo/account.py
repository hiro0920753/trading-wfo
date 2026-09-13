from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class ContributionSchedule:
    """A positive external cash contribution repeated on a causal schedule."""

    amount: float
    period: str
    start: Optional[str] = None
    end: Optional[str] = None

    def __post_init__(self):
        if self.amount <= 0:
            raise ValueError("contribution amount must be positive")
        from .window import WindowPeriod
        WindowPeriod.parse(self.period)


@dataclass(frozen=True)
class AccountConfig:
    """Public configuration for the simulator's internal account."""

    initial_balance: float
    leverage: float
    units_per_lot: float
    price_per_pip: float
    stop_out_level: float = 50.0
    reinvestment_rate: float = 1.0
    reserve_refill_threshold: float = 0.0
    reserve_refill_target: float = 0.0
    reserve_margin_topup_metadata_key: str = ""
    contribution_schedules: Tuple[ContributionSchedule, ...] = ()

    def __post_init__(self):
        if self.initial_balance < 0:
            raise ValueError("initial_balance must not be negative")
        if self.leverage <= 0:
            raise ValueError("leverage must be positive")
        if self.units_per_lot <= 0:
            raise ValueError("units_per_lot must be positive")
        if self.price_per_pip <= 0:
            raise ValueError("price_per_pip must be positive")
        if self.stop_out_level < 0:
            raise ValueError("stop_out_level must not be negative")
        if not 0 <= self.reinvestment_rate <= 1:
            raise ValueError("reinvestment_rate must be between 0 and 1")
        if self.reserve_refill_threshold < 0:
            raise ValueError("reserve_refill_threshold must not be negative")
        if self.reserve_refill_target < 0:
            raise ValueError("reserve_refill_target must not be negative")
        if (
            self.reserve_refill_threshold > 0
            and self.reserve_refill_target < self.reserve_refill_threshold
        ):
            raise ValueError(
                "reserve_refill_target must be at least reserve_refill_threshold"
            )
        if not isinstance(self.reserve_margin_topup_metadata_key, str):
            raise TypeError("reserve_margin_topup_metadata_key must be a string")
        schedules = tuple(
            item if isinstance(item, ContributionSchedule) else ContributionSchedule(**item)
            for item in self.contribution_schedules
        )
        object.__setattr__(self, "contribution_schedules", schedules)
