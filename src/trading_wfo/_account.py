from dataclasses import dataclass

from .account import AccountConfig
from .models import Position, Side


@dataclass(frozen=True)
class UnrealizedResult:
    profit: float = 0.0
    pips: float = 0.0


class Account:
    """Internal account state and all account-related calculations."""

    def __init__(self, config: AccountConfig):
        self.config = config
        self.balance = float(config.initial_balance)
        self.equity = self.balance
        self.used_margin = 0.0
        self.free_margin = self.balance
        self.margin_level = float("inf")
        self.realized_profit = 0.0
        self.realized_pips = 0.0
        self.trading_capital = self.balance
        self.reserved_profit = 0.0
        self.reinvested_profit = 0.0
        self.reserve_refill_total = 0.0
        self.reserve_margin_topup_total = 0.0
        self.reserve_margin_topup_count = 0
        self.reserve_margin_topup_returned = 0.0
        self.total_contributions = 0.0
        self.unrealized = UnrealizedResult()
        self.allocatable_free_margin = self.free_margin

    @property
    def buying_power(self):
        return max(0.0, self.allocatable_free_margin * self.config.leverage)

    @property
    def is_stop_out(self):
        return (
            self.used_margin > 0
            and self.margin_level < self.config.stop_out_level
        )

    def required_margin(self, price, lot_size):
        return (
            float(price)
            * float(lot_size)
            * self.config.units_per_lot
            / self.config.leverage
        )

    def can_open(self, required_margin):
        return float(required_margin) <= self.allocatable_free_margin

    def reserve_margin(self, required_margin):
        self.used_margin += float(required_margin)
        self.free_margin = self.equity - self.used_margin
        self.allocatable_free_margin -= float(required_margin)
        self._update_margin_level()

    def realize(self, profit, pips):
        profit = float(profit)
        pips = float(pips)
        self.balance += profit
        self.realized_profit += profit
        self.realized_pips += pips
        if profit > 0:
            reinvested = profit * self.config.reinvestment_rate
            reserved = profit - reinvested
            self.trading_capital += reinvested
            self.reinvested_profit += reinvested
            self.reserved_profit += reserved
        else:
            self.trading_capital += profit
        self._refill_trading_capital_from_reserve()

    def _refill_trading_capital_from_reserve(self):
        threshold = float(self.config.reserve_refill_threshold)
        target = float(self.config.reserve_refill_target)
        if threshold <= 0 or self.trading_capital >= threshold:
            return 0.0
        refill = min(max(0.0, target - self.trading_capital), self.reserved_profit)
        self.trading_capital += refill
        self.reserved_profit -= refill
        self.reserve_refill_total += refill
        return refill

    def top_up_margin_from_reserve(self, required_funds):
        """Fund an order only when the full shortfall can be covered."""
        required_funds = float(required_funds)
        shortfall = max(0.0, required_funds - self.allocatable_free_margin)
        if (
            shortfall <= 0
            or shortfall > self.reserved_profit
            or required_funds > self.free_margin
        ):
            return 0.0
        transfer = shortfall
        self.trading_capital += transfer
        self.reserved_profit -= transfer
        self.reserve_margin_topup_total += transfer
        self.reserve_margin_topup_count += 1
        self.allocatable_free_margin = min(
            self.free_margin,
            self.allocatable_free_margin + transfer,
        )
        return transfer

    def settle_margin_topup(self, funded_amount, realized_profit):
        """Return unused temporary funding; losses consume the reserve first."""
        funded_amount = max(0.0, float(funded_amount))
        realized_profit = float(realized_profit)
        repayment = min(
            max(0.0, self.trading_capital),
            max(0.0, funded_amount + min(0.0, realized_profit)),
        )
        self.trading_capital -= repayment
        self.reserved_profit += repayment
        self.reserve_margin_topup_returned += repayment
        return repayment

    def charge_commission(self, commission):
        commission = float(commission)
        if commission < 0:
            raise ValueError("commission must not be negative")
        if commission:
            self.realize(-commission, 0.0)

    def contribute(self, amount):
        """Add external capital without counting it as trading profit."""
        amount = float(amount)
        if amount <= 0:
            raise ValueError("contribution amount must be positive")
        self.balance += amount
        self.equity += amount
        self.free_margin += amount
        self.trading_capital += amount
        self.allocatable_free_margin += amount
        self.total_contributions += amount
        self._update_margin_level()

    def calculate_unrealized(self, portfolio, bid, ask):
        profit = 0.0
        pips = 0.0
        for position in portfolio.long_positions():
            price_difference = float(bid) - position.entry_price
            profit += price_difference * position.lot_size * self.config.units_per_lot
            pips += price_difference / self.config.price_per_pip
        for position in portfolio.short_positions():
            price_difference = position.entry_price - float(ask)
            profit += price_difference * position.lot_size * self.config.units_per_lot
            pips += price_difference / self.config.price_per_pip
        return UnrealizedResult(profit=profit, pips=pips)

    def refresh(self, portfolio, bid, ask):
        self.unrealized = self.calculate_unrealized(portfolio, bid, ask)
        self.used_margin = sum(
            self.required_margin(ask, position.lot_size)
            for position in portfolio.long_positions()
        ) + sum(
            self.required_margin(bid, position.lot_size)
            for position in portfolio.short_positions()
        )
        self.equity = self.balance + self.unrealized.profit
        self.free_margin = self.equity - self.used_margin
        allocatable_equity = (
            self.trading_capital + min(0.0, self.unrealized.profit)
        )
        self.allocatable_free_margin = min(
            self.free_margin,
            allocatable_equity - self.used_margin,
        )
        self._update_margin_level()
        return self.unrealized

    def close_position(self, position: Position, exit_price):
        exit_price = float(exit_price)
        if position.side is Side.LONG:
            price_difference = exit_price - position.entry_price
        else:
            price_difference = position.entry_price - exit_price
        profit = price_difference * position.lot_size * self.config.units_per_lot
        pips = price_difference / self.config.price_per_pip
        self.realize(profit, pips)
        return profit, pips

    def snapshot(self):
        return {
            "balance": self.balance,
            "equity": self.equity,
            "used_margin": self.used_margin,
            "free_margin": self.free_margin,
            "margin_level": self.margin_level,
            "buying_power": self.buying_power,
            "trading_capital": self.trading_capital,
            "reserved_profit": self.reserved_profit,
            "reinvested_profit": self.reinvested_profit,
            "reserve_refill_total": self.reserve_refill_total,
            "reserve_margin_topup_total": self.reserve_margin_topup_total,
            "reserve_margin_topup_count": self.reserve_margin_topup_count,
            "reserve_margin_topup_returned": self.reserve_margin_topup_returned,
            "total_contributions": self.total_contributions,
            "allocatable_free_margin": self.allocatable_free_margin,
            "realized_profit": self.realized_profit,
            "realized_pips": self.realized_pips,
            "unrealized_profit": self.unrealized.profit,
            "unrealized_pips": self.unrealized.pips,
        }

    def _update_margin_level(self):
        self.margin_level = (
            float("inf")
            if self.used_margin == 0
            else self.equity / self.used_margin * 100
        )
