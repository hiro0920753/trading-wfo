"""Regression coverage for the September 2026 local review."""
import unittest

import pandas as pd

from trading_wfo import Action, AccountConfig, CloseRequest, ExecutionConfig, Order, TradingSimulator
from trading_wfo._account import Account
from trading_wfo.stress import DelayedEntryStrategy


def data(bids=(100., 100., 100., 100.), spread=0., tz=None):
    return pd.DataFrame(dict(
        time=pd.date_range("2026-01-01", periods=len(bids), freq="5min", tz=tz),
        bid=bids, ask=[b + spread for b in bids],
        open=bids, high=bids, low=bids, close=bids,
    ))


def params(balance=1000., leverage=10.):
    return {
        "common": {"units_per_lot": 100, "symbol": "TEST", "price_per_pip": 1},
        "strategy_base": {"lookback_bars": 1, "leverage": leverage},
        "asset": {"balance": balance},
    }


class ReviewRegressions(unittest.TestCase):
    def test_batch_commission_limits_market_and_limit_orders(self):
        for order_type in ("market", "limit"):
            with self.subTest(order_type=order_type):
                options = {} if order_type == "market" else {"order_type": "limit", "limit_price": 100}
                sim = TradingSimulator(params(2100), None, data(),
                    execution_config=ExecutionConfig(commission_per_lot_per_side=100))
                result = sim.run(lambda c: Action(orders=[Order("long", 1, **options), Order("long", 1, **options)])
                    if c["step_index"] == 0 else Action(), close_positions_at_end=False)
                self.assertEqual(len(sim._portfolio.positions()), 1)
                self.assertEqual(result.metrics["rejected_order_count"], 1)
                self.assertEqual(sim.account_snapshot()["free_margin"], 1000)

    def test_batch_spread_loss_reduces_next_order_budget(self):
        sim = TradingSimulator(params(2050), None, data(spread=1))
        result = sim.run(lambda c: Action(orders=[Order("long", 1), Order("long", 1)])
            if c["step_index"] == 0 else Action(), close_positions_at_end=False)
        self.assertEqual(len(sim._portfolio.positions()), 1)
        self.assertEqual(result.metrics["rejected_order_count"], 1)

    def test_delayed_callable_executes_on_later_quote(self):
        quotes = data((100., 100., 110., 120.))
        def strategy(context):
            if context["step_index"] == 0:
                return Action(orders=[Order("long", .01)])
            return None
        result = TradingSimulator(params(), None, quotes).run(DelayedEntryStrategy(strategy, 1))
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0]["entry_price"], 110)
        self.assertEqual(result.trades[0]["time"], quotes.time.iloc[2].timestamp())

    def test_contributions_with_naive_and_aware_data(self):
        for tz in (None, "UTC", "Asia/Tokyo"):
            for explicit in (False, True):
                with self.subTest(tz=tz, explicit=explicit):
                    p = params()
                    schedule = {"amount": 100, "period": "5min", "end": "2026-01-01 00:10:00"}
                    if explicit:
                        schedule["start"] = "2026-01-01 00:10:00"
                    p["asset"]["contribution_schedules"] = [schedule]
                    result = TradingSimulator(p, None, data(tz=tz)).run(lambda c: Action())
                    self.assertEqual(result.metrics["total_contributions"], 100)
                    self.assertEqual(result.metrics["net_profit"], 0)
                    self.assertEqual(len(result.cash_flows), 1)

    def test_aware_schedule_on_naive_market_uses_same_instant(self):
        p = params()
        p["asset"]["contribution_schedules"] = [{"amount": 100, "period": "1mo",
            "start": "2026-01-01T09:10:00+09:00"}]
        result = TradingSimulator(p, None, data()).run(lambda c: Action())
        self.assertEqual(len(result.cash_flows), 1)
        self.assertEqual(result.cash_flows[0]["time"], pd.Timestamp("2026-01-01T00:10:00Z").timestamp())

    def test_rejected_topup_preserves_reserve_and_counters(self):
        p = params()
        p["asset"].update(reinvestment_rate=0, reserve_margin_topup_metadata_key="topup")
        def strategy(c):
            if c["step_index"] == 0:
                return Action(orders=[Order("long", .1)])
            if c["step_index"] == 1:
                return Action(close_requests=[CloseRequest(1)], orders=[Order("long", 2, metadata={"topup": True})])
            return Action()
        result = TradingSimulator(p, None, data((100., 100., 110., 110.))).run(strategy)
        self.assertEqual(result.metrics["rejected_order_count"], 1)
        self.assertEqual(result.metrics["final_trading_capital"], 1000)
        self.assertEqual(result.metrics["reserved_profit"], 100)
        self.assertEqual(result.metrics["reserve_margin_topup_total"], 0)
        self.assertEqual(result.metrics["reserve_margin_topup_count"], 0)

    def test_topup_requires_both_reserve_and_account_free_margin(self):
        for required, free_margin in ((1200, 2000), (1050, 1000)):
            with self.subTest(required=required, free_margin=free_margin):
                account = Account(AccountConfig(initial_balance=1000, leverage=10, units_per_lot=100, price_per_pip=1))
                account.reserved_profit = 100
                account.free_margin = free_margin
                before = account.snapshot()
                self.assertEqual(account.top_up_margin_from_reserve(required), 0)
                self.assertEqual(account.snapshot(), before)

    def test_negative_capital_does_not_produce_negative_repayment(self):
        for funded in (0, 50):
            with self.subTest(funded=funded):
                account = Account(AccountConfig(initial_balance=100, leverage=10, units_per_lot=100, price_per_pip=1))
                account.realize(-200, 0)
                self.assertEqual(account.settle_margin_topup(funded, -200), 0)
                self.assertEqual(account.trading_capital, -100)
                self.assertEqual(account.reserved_profit, 0)
                self.assertEqual(account.reserve_margin_topup_returned, 0)

    def test_stop_out_preserves_negative_balance_in_trading_capital(self):
        result = TradingSimulator(params(100, 1000), None, data((100., 100., 98.))).run(
            lambda c: Action(orders=[Order("long", 1)]) if c["step_index"] == 0 else Action())
        self.assertEqual(result.metrics["final_balance"], -100)
        self.assertEqual(result.metrics["final_trading_capital"], -100)
        self.assertEqual(result.metrics["reserved_profit"], 0)
        self.assertEqual(result.metrics["reserve_margin_topup_returned"], 0)
