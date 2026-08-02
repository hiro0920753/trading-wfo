from dataclasses import dataclass


@dataclass(frozen=True)
class AccountConfig:
    """Public configuration for the simulator's internal account."""

    initial_balance: float
    leverage: float
    units_per_lot: float
    price_per_pip: float
    stop_out_level: float = 50.0
    reinvestment_rate: float = 1.0

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
