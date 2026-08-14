import copy
from datetime import date, datetime
from pathlib import Path
from time import monotonic

from tqdm.auto import tqdm

from ._account import Account
from ._data import prepare_market_data_bundle
from ._execution import Execution
from ._portfolio import Portfolio
from .account import AccountConfig
from .execution import ExecutionConfig
from .errors import StrategyExecutionError
from .metrics import calculate_metrics
from .models import Action, OrderType, PendingOrder, Position, make_position_snapshot
from .result import SimulationResult


class TradingSimulator:
    def __init__(
        self,
        params,
        trading_log,
        data,
        *,
        account_config=None,
        execution_config=None,
    ):
        if account_config is None:
            account_config = AccountConfig(
                initial_balance=params["asset"]["balance"],
                leverage=params["strategy_base"]["leverage"],
                units_per_lot=params["common"]["units_per_lot"],
                price_per_pip=params["common"]["price_per_pip"],
                stop_out_level=params.get("asset", {}).get(
                    "stop_out_level", 50.0
                ),
                reinvestment_rate=params.get("asset", {}).get(
                    "reinvestment_rate", 1.0
                ),
            )
        elif not isinstance(account_config, AccountConfig):
            raise TypeError("account_config must be an AccountConfig")
        if execution_config is None:
            execution_config = ExecutionConfig()
        elif not isinstance(execution_config, ExecutionConfig):
            raise TypeError("execution_config must be an ExecutionConfig")

        self._account_config = account_config
        self._execution_config = execution_config
        self._symbol = params["common"]["symbol"]
        self._lookback_bars = params["strategy_base"]["lookback_bars"]
        if self._lookback_bars <= 0:
            raise ValueError("lookback_bars must be positive")

        self._trading_log = trading_log
        self.set_data(data)
        self._reset_simulation_state()

    def _reset_simulation_state(self):
        self._account = Account(self._account_config)
        self._portfolio = Portfolio()
        self._execution = Execution(
            self._execution_config, self._account_config.price_per_pip
        )
        self._next_position_id = 1
        self._next_pending_order_id = 1
        self._pending_orders = []
        self._trade_records = []
        self._total_commission = 0.0
        self._rejected_orders = []

    @staticmethod
    def _prepare_data(data, primary_symbol):
        return prepare_market_data_bundle(data, primary_symbol=primary_symbol)

    def set_data(self, data):
        self._market_data = self._prepare_data(data, self._symbol)
        self._data = self._market_data[self._symbol]
        if len(self._data) <= self._lookback_bars:
            raise ValueError(
                "data contains insufficient rows: requires more than "
                f"lookback_bars={self._lookback_bars}, got {len(self._data)}"
            )
        self._step_count = max(0, len(self._data) - self._lookback_bars)

    def _build_market_contexts(self, current_time):
        markets = {}
        unavailable = []
        for symbol, frame in self._market_data.items():
            current_index = int(frame["time"].searchsorted(current_time, side="right") - 1)
            if current_index < self._lookback_bars:
                unavailable.append(symbol)
                continue
            current = frame.iloc[current_index]
            confirmed = frame.iloc[current_index - 1]
            markets[symbol] = {
                "symbol": symbol,
                "time": current["time"].timestamp(),
                "bid": float(current["bid"]),
                "ask": float(current["ask"]),
                "spread": float(current["ask"] - current["bid"]),
                "open": float(confirmed["open"]),
                "high": float(confirmed["high"]),
                "low": float(confirmed["low"]),
                "close": float(confirmed["close"]),
                "bars": frame.iloc[current_index - self._lookback_bars:current_index].copy(),
                "row": confirmed.copy(),
            }
        return markets, tuple(unavailable)

    def account_snapshot(self):
        return self._account.snapshot()

    def _open_order(self, order, time, ask, bid, *, entry_price=None):
        if order.lot_size < self._execution_config.minimum_lot_size:
            raise ValueError(
                f"lot_size {order.lot_size} is below minimum_lot_size "
                f"{self._execution_config.minimum_lot_size}"
            )
        symbol = order.symbol or self._symbol
        if symbol != self._symbol:
            raise ValueError(
                f"order symbol {symbol!r} does not match simulator symbol {self._symbol!r}"
            )
        if entry_price is None:
            entry_price = self._execution.entry_price(order.side, ask, bid)
        required_margin = self._account.required_margin(entry_price, order.lot_size)
        entry_commission = self._execution.commission(order.lot_size)
        if not self._account.can_open(required_margin + entry_commission):
            rejection = {
                "time": float(time), "symbol": symbol, "side": order.side.value,
                "lot_size": order.lot_size, "reason": "insufficient_margin",
                "required_funds": required_margin + entry_commission,
                "available_funds": self._account.allocatable_free_margin,
                "metadata": copy.deepcopy(order.metadata),
            }
            self._rejected_orders.append(rejection)
            self._log_event(
                "order_rejected", time=time, side=order.side.value,
                lot_size=order.lot_size, execution_price=entry_price,
                metadata=order.metadata, exit_reason="insufficient_margin",
            )
            return None
        position = Position(
            position_id=self._next_position_id, side=order.side,
            entry_price=entry_price, lot_size=order.lot_size, time=time,
            symbol=symbol, metadata=copy.deepcopy(order.metadata),
            entry_commission=entry_commission,
        )
        self._portfolio.open_position(position)
        self._account.reserve_margin(required_margin)
        self._account.charge_commission(entry_commission)
        self._total_commission += entry_commission
        self._next_position_id += 1
        self._log_event(
            "position_opened", time=time, position=position,
            execution_price=entry_price, commission=entry_commission,
        )
        return position

    def _execute_orders(self, action, time, ask, bid):
        opened_positions = []
        for order in action.orders:
            if order.order_type is OrderType.LIMIT:
                symbol = order.symbol or self._symbol
                if symbol != self._symbol:
                    raise ValueError(
                        f"order symbol {symbol!r} does not match simulator symbol {self._symbol!r}"
                    )
                self._pending_orders.append(PendingOrder(
                    pending_order_id=self._next_pending_order_id,
                    side=order.side, lot_size=order.lot_size,
                    limit_price=order.limit_price, symbol=symbol,
                    submitted_time=time, expires_at=order.expires_at,
                    metadata=copy.deepcopy(order.metadata),
                ))
                self._next_pending_order_id += 1
                continue
            position = self._open_order(order, time, ask, bid)
            if position is not None:
                opened_positions.append(position)

        self._account.refresh(self._portfolio, bid, ask)
        return opened_positions

    def _process_pending_orders(self, time, confirmed_row, ask, bid):
        remaining = []
        for pending in self._pending_orders:
            if pending.expires_at is not None and self._time_value(time) > self._time_value(pending.expires_at):
                continue
            touched = (
                float(confirmed_row["low"]) <= pending.limit_price
                if pending.side.value == "long"
                else float(confirmed_row["high"]) >= pending.limit_price
            )
            if not touched:
                remaining.append(pending)
                continue
            order = type("FilledLimitOrder", (), {
                "side": pending.side, "lot_size": pending.lot_size,
                "symbol": pending.symbol, "metadata": pending.metadata,
            })()
            self._open_order(order, time, ask, bid, entry_price=pending.limit_price)
        self._pending_orders = remaining

    @staticmethod
    def _time_value(value):
        """Return a comparable timestamp for numeric and datetime-like values."""
        if isinstance(value, (datetime, date)):
            return value.timestamp()
        timestamp = getattr(value, "timestamp", None)
        if callable(timestamp):
            return float(timestamp())
        return float(value)

    def _cancel_pending_orders(self, order_ids):
        requested = set(order_ids)
        active = {order.pending_order_id for order in self._pending_orders}
        missing = sorted(requested.difference(active))
        if missing:
            raise ValueError(f"cannot cancel unknown pending_order_id(s): {missing}")
        self._pending_orders = [
            order for order in self._pending_orders if order.pending_order_id not in requested
        ]

    def _execute_close_requests(self, action, time, ask, bid):
        position_ids = [request.position_id for request in action.close_requests]
        reasons_by_position_id = {
            request.position_id: request.reason for request in action.close_requests
        }
        metadata_by_position_id = {
            request.position_id: request.metadata for request in action.close_requests
        }
        active_ids = {
            position.position_id for position in self._portfolio.positions()
        }
        missing_ids = sorted(set(position_ids).difference(active_ids))
        if missing_ids:
            raise ValueError(
                f"cannot close unknown position_id(s): {missing_ids}"
            )
        closed_positions = self._portfolio.close_positions(position_ids)
        for position in closed_positions:
            exit_price = self._execution.exit_price(position.side, ask, bid)
            realized_profit, realized_pips = self._account.close_position(
                position, exit_price
            )
            exit_commission = self._execution.commission(position.lot_size)
            self._account.charge_commission(exit_commission)
            self._total_commission += exit_commission
            self._record_closed_trade(
                position=position,
                exit_price=exit_price,
                exit_time=time,
                gross_profit=realized_profit,
                realized_pips=realized_pips,
                exit_commission=exit_commission,
                exit_reason=reasons_by_position_id[position.position_id],
                exit_metadata=metadata_by_position_id[position.position_id],
            )
        self._account.refresh(self._portfolio, bid, ask)
        return closed_positions

    def _update_position_excursions(self, time, ask, bid):
        """Record path-dependent diagnostics without affecting decisions."""
        pip = self._account_config.price_per_pip
        for position in self._portfolio.positions():
            if position.side.value == "long":
                unrealized_pips = (bid - position.entry_price) / pip
            else:
                unrealized_pips = (position.entry_price - ask) / pip
            if unrealized_pips > position.mfe_pips:
                position.mfe_pips = float(unrealized_pips)
                position.mfe_time = float(time)
            if unrealized_pips < position.mae_pips:
                position.mae_pips = float(unrealized_pips)
                position.mae_time = float(time)

    def _liquidate_all(self, time, ask, bid, *, exit_reason):
        closed_positions = self._portfolio.close_all()
        for position in closed_positions:
            exit_price = self._execution.exit_price(position.side, ask, bid)
            realized_profit, realized_pips = self._account.close_position(
                position, exit_price
            )
            exit_commission = self._execution.commission(position.lot_size)
            self._account.charge_commission(exit_commission)
            self._total_commission += exit_commission
            self._record_closed_trade(
                position=position,
                exit_price=exit_price,
                exit_time=time,
                gross_profit=realized_profit,
                realized_pips=realized_pips,
                exit_commission=exit_commission,
                exit_reason=exit_reason,
                exit_metadata={},
            )
        self._account.refresh(self._portfolio, bid, ask)
        return closed_positions

    def _record_closed_trade(
        self,
        *,
        position,
        exit_price,
        exit_time,
        gross_profit,
        realized_pips,
        exit_commission,
        exit_reason,
        exit_metadata,
    ):
        trade = make_position_snapshot(position)
        total_commission = position.entry_commission + exit_commission
        realized_profit = gross_profit - total_commission
        trade.update(
            {
                "exit_price": float(exit_price),
                "exit_time": float(exit_time),
                "realized_profit": float(realized_profit),
                "realized_pips": float(realized_pips),
                "gross_profit": float(gross_profit),
                "commission": float(total_commission),
                "exit_commission": float(exit_commission),
                "additional_spread_pips": (
                    self._execution_config.additional_spread_pips
                ),
                "entry_slippage_pips": (
                    self._execution_config.entry_slippage_pips
                ),
                "exit_slippage_pips": (
                    self._execution_config.exit_slippage_pips
                ),
                "exit_reason": exit_reason,
                "exit_metadata": copy.deepcopy(exit_metadata),
                "holding_seconds": float(exit_time) - float(position.time),
                "profit_peak_drawdown_pips": float(position.mfe_pips)
                - float(realized_pips),
            }
        )
        self._trade_records.append(trade)
        self._log_event(
            "position_closed",
            time=exit_time,
            position=position,
            execution_price=exit_price,
            realized_profit=realized_profit,
            realized_pips=realized_pips,
            commission=exit_commission,
            exit_reason=exit_reason,
        )

    def _log_event(
        self,
        event,
        *,
        time,
        position=None,
        side=None,
        lot_size=None,
        execution_price,
        metadata=None,
        realized_profit=None,
        realized_pips=None,
        exit_reason=None,
        commission=0.0,
    ):
        if self._trading_log is None:
            return
        snapshot = (
            make_position_snapshot(position) if position is not None else {}
        )
        account = self._account.snapshot()
        self._trading_log.add(
            {
                "event": event,
                "time": float(time),
                "position_id": snapshot.get("position_id"),
                "symbol": snapshot.get("symbol", self._symbol),
                "side": snapshot.get("side", side),
                "lot_size": snapshot.get("lot_size", lot_size),
                "entry_price": snapshot.get("entry_price"),
                "execution_price": float(execution_price),
                "realized_profit": realized_profit,
                "realized_pips": realized_pips,
                "commission": float(commission),
                "exit_reason": exit_reason,
                "balance": account["balance"],
                "cumulative_realized_profit": account["realized_profit"],
                "cumulative_realized_pips": account["realized_pips"],
                "metadata": snapshot.get("metadata", metadata or {}),
            }
        )

    def _execute_action(self, action, time, ask, bid):
        self._cancel_pending_orders(action.cancel_order_ids)
        self._execute_close_requests(action, time, ask, bid)
        self._execute_orders(action, time, ask, bid)

    def _build_context(self, step_index, ask, bid):
        data_index = step_index + self._lookback_bars
        current_row = self._data.iloc[data_index]
        confirmed_row = self._data.iloc[data_index - 1]
        time = current_row["time"].timestamp()
        self._account.refresh(self._portfolio, bid, ask)
        account = self._account.snapshot()
        markets, unavailable_markets = self._build_market_contexts(current_row["time"])
        if self._symbol in markets:
            markets[self._symbol]["ask"] = ask
            markets[self._symbol]["bid"] = bid
            markets[self._symbol]["spread"] = ask - bid

        return {
            "step_index": step_index,
            "symbol": self._symbol,
            "time": time,
            "bid": bid,
            "ask": ask,
            "spread": ask - bid,
            "open": float(confirmed_row["open"]),
            "high": float(confirmed_row["high"]),
            "low": float(confirmed_row["low"]),
            "close": float(confirmed_row["close"]),
            "bars": self._data.iloc[
                data_index - self._lookback_bars : data_index
            ].copy(),
            "row": confirmed_row.copy(),
            "balance": account["balance"],
            "equity": account["equity"],
            "used_margin": account["used_margin"],
            "free_margin": account["free_margin"],
            "margin_level": account["margin_level"],
            "buying_power": account["buying_power"],
            "trading_capital": account["trading_capital"],
            "reserved_profit": account["reserved_profit"],
            "reinvested_profit": account["reinvested_profit"],
            "allocatable_free_margin": account["allocatable_free_margin"],
            "realized_profit": account["realized_profit"],
            "realized_pips": account["realized_pips"],
            "unrealized_profit": account["unrealized_profit"],
            "unrealized_pips": account["unrealized_pips"],
            "total_profit": account["realized_profit"]
            + account["unrealized_profit"],
            "total_pips": account["realized_pips"]
            + account["unrealized_pips"],
            "long_positions": tuple(
                make_position_snapshot(position)
                for position in self._portfolio.long_positions()
            ),
            "short_positions": tuple(
                make_position_snapshot(position)
                for position in self._portfolio.short_positions()
            ),
            "active_position_count": len(self._portfolio.positions()),
            "markets": markets,
            "unavailable_markets": unavailable_markets,
            "pending_orders": tuple(
                {
                    "pending_order_id": order.pending_order_id,
                    "side": order.side.value,
                    "lot_size": order.lot_size,
                    "limit_price": order.limit_price,
                    "symbol": order.symbol,
                    "submitted_time": order.submitted_time,
                    "expires_at": order.expires_at,
                    "metadata": copy.deepcopy(order.metadata),
                }
                for order in self._pending_orders
            ),
        }

    @staticmethod
    def _call_strategy(strategy, context):
        try:
            if hasattr(strategy, "on_bar"):
                action = strategy.on_bar(context)
            elif callable(strategy):
                action = strategy(context)
            else:
                raise TypeError(
                    "strategy must be callable or define on_bar(context)"
                )
        except Exception as error:
            raise StrategyExecutionError(
                context["step_index"], context["time"], error
            ) from error

        if action is None:
            return Action()
        if not isinstance(action, Action):
            raise TypeError("strategy must return an Action or None")
        return action

    def run(
        self,
        strategy,
        data=None,
        *,
        close_positions_at_end=True,
        result_path=None,
        live_update_interval=2.0,
        live_result_interval=60.0,
        show_progress=False,
    ):
        """Run one simulation using confirmed bars through t-1 at quote t."""
        if live_update_interval <= 0:
            raise ValueError("live_update_interval must be positive")
        if live_result_interval <= 0:
            raise ValueError("live_result_interval must be positive")
        if data is not None:
            self.set_data(data)
        self._reset_simulation_state()

        equity_curve = []
        trading_stopped = False
        last_live_update = monotonic()
        last_result_update = last_live_update
        live_trade_count = 0
        progress_path = None
        if result_path is not None:
            result_path = Path(result_path)
            progress_path = result_path.with_suffix(".progress.json")
            self._make_result(equity_curve, 0, status="running").save_json(
                result_path
            )
            self._make_progress_result(0, status="running").save_json(
                progress_path, indent=None
            )

        steps = tqdm(
            range(self._step_count),
            desc="Backtest",
            unit="bar",
            dynamic_ncols=True,
            disable=not show_progress,
        )
        for step_index in steps:
            data_index = step_index + self._lookback_bars
            row = self._data.iloc[data_index]
            time = row["time"].timestamp()
            ask, bid = self._execution.effective_quote(
                ask=row["ask"], bid=row["bid"]
            )

            confirmed_row = self._data.iloc[data_index - 1]
            self._process_pending_orders(time, confirmed_row, ask, bid)

            self._update_position_excursions(time, ask, bid)

            context = self._build_context(step_index, ask, bid)

            if self._account.is_stop_out:
                self._liquidate_all(
                    time, ask, bid, exit_reason="stop_out"
                )
                context = self._build_context(step_index, ask, bid)
                context["stop_out_triggered"] = True
            else:
                context["stop_out_triggered"] = False

            if not trading_stopped:
                action = self._call_strategy(strategy, context)
                self._execute_action(action, time, ask, bid)
                trading_stopped = action.stop_trading

            equity_curve.append(
                {
                    "time": time,
                    "balance": float(self._account.balance),
                    "equity": float(self._account.equity),
                    "trading_capital": float(self._account.trading_capital),
                    "reserved_profit": float(self._account.reserved_profit),
                }
            )

            if result_path is not None:
                now = monotonic()
                trade_completed = len(self._trade_records) != live_trade_count
                if trade_completed or now - last_live_update >= live_update_interval:
                    self._make_progress_result(
                        step_index + 1, status="running"
                    ).save_json(progress_path, indent=None)
                    last_live_update = now
                    live_trade_count = len(self._trade_records)
                if now - last_result_update >= live_result_interval:
                    self._make_result(
                        equity_curve, step_index + 1, status="running"
                    ).save_json(result_path)
                    last_result_update = now

        if close_positions_at_end and self._portfolio.positions() and self._step_count:
            final_row = self._data.iloc[-1]
            final_ask, final_bid = self._execution.effective_quote(
                ask=final_row["ask"], bid=final_row["bid"]
            )
            self._liquidate_all(
                time=final_row["time"].timestamp(),
                ask=final_ask,
                bid=final_bid,
                exit_reason="end_of_data",
            )
            equity_curve[-1].update(
                {
                    "balance": float(self._account.balance),
                    "equity": float(self._account.equity),
                    "trading_capital": float(self._account.trading_capital),
                    "reserved_profit": float(self._account.reserved_profit),
                }
            )

        result = self._make_result(
            equity_curve, self._step_count, status="completed"
        )
        if result_path is not None:
            result.save_json(result_path)
            self._make_progress_result(
                self._step_count, status="completed"
            ).save_json(progress_path, indent=None)
        if self._trading_log is not None and hasattr(self._trading_log, "save"):
            self._trading_log.save()
        return result

    def _make_progress_result(self, steps_processed, *, status):
        """Create a bounded live snapshot without copying the full result."""
        metrics = {
            "steps_processed": steps_processed,
            "total_steps": self._step_count,
            "progress_pct": (
                100.0 * steps_processed / self._step_count
                if self._step_count else 100.0
            ),
            "status": status,
            "total_trades": len(self._trade_records),
            "realized_profit": float(self._account.realized_profit),
            "realized_pips": float(self._account.realized_pips),
            "balance": float(self._account.balance),
            "equity": float(self._account.equity),
        }
        return SimulationResult(metrics=metrics)

    def _make_result(self, equity_curve, steps_processed, *, status):
        metrics = calculate_metrics(
            initial_balance=self._account_config.initial_balance,
            final_balance=self._account.balance,
            trades=self._trade_records,
            equity_curve=equity_curve,
        )
        metrics.update(
            {
                "final_equity": float(self._account.equity),
                "realized_profit": float(self._account.realized_profit),
                "realized_pips": float(self._account.realized_pips),
                "final_trading_capital": float(self._account.trading_capital),
                "reserved_profit": float(self._account.reserved_profit),
                "reinvested_profit": float(self._account.reinvested_profit),
                "total_commission": float(self._total_commission),
                "additional_spread_pips": float(
                    self._execution_config.additional_spread_pips
                ),
                "entry_slippage_pips": float(
                    self._execution_config.entry_slippage_pips
                ),
                "exit_slippage_pips": float(
                    self._execution_config.exit_slippage_pips
                ),
                "steps_processed": steps_processed,
                "total_steps": self._step_count,
                "progress_pct": (
                    100.0 * steps_processed / self._step_count
                    if self._step_count else 100.0
                ),
                "status": status,
                "rejected_order_count": len(self._rejected_orders),
                "pending_order_count": len(self._pending_orders),
            }
        )
        return SimulationResult(
            metrics=metrics,
            trades=copy.deepcopy(self._trade_records),
            equity_curve=equity_curve,
            rejected_orders=copy.deepcopy(self._rejected_orders),
        )
