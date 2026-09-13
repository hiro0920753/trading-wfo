"""Post-selection OOS stress scenarios. Never optimize on stressed results."""
from copy import deepcopy
from dataclasses import dataclass, field
from numbers import Integral, Real
from collections.abc import Mapping
import math

import numpy as np
import pandas as pd

from .models import Action, OrderType
from .constraints import evaluate_constraints


@dataclass(frozen=True)
class StressScenario:
    name: str
    spread_multiplier: float = 1.0
    entry_delay_bars: int = 0
    parameter_offsets: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip() or self.name == 'baseline':
            raise ValueError('scenario name must be nonempty and not baseline')
        if not math.isfinite(self.spread_multiplier) or self.spread_multiplier < 1:
            raise ValueError('spread_multiplier must be finite and >= 1')
        if isinstance(self.entry_delay_bars, bool) or not isinstance(self.entry_delay_bars, Integral) or self.entry_delay_bars < 0:
            raise ValueError('entry_delay_bars must be a nonnegative integer')
        offsets = dict(self.parameter_offsets)
        for value in offsets.values():
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                raise ValueError('parameter offsets must be finite numbers')
        object.__setattr__(self, 'parameter_offsets', offsets)


@dataclass(frozen=True)
class RobustnessConfig:
    scenarios: tuple = ()
    monte_carlo_samples: int = 0
    seed: int = 42

    def __post_init__(self):
        scenarios = tuple(self.scenarios)
        if any(not isinstance(s, StressScenario) for s in scenarios):
            raise TypeError('scenarios must contain StressScenario objects')
        if len({s.name for s in scenarios}) != len(scenarios):
            raise ValueError('scenario names must be unique')
        if isinstance(self.monte_carlo_samples, bool) or not isinstance(self.monte_carlo_samples, Integral) or not 0 <= self.monte_carlo_samples <= 10000:
            raise ValueError('monte_carlo_samples must be an integer between 0 and 10000')
        if isinstance(self.seed, bool) or not isinstance(self.seed, Integral) or self.seed < 0:
            raise ValueError('seed must be a nonnegative integer')
        object.__setattr__(self, 'scenarios', scenarios)


def stress_quotes(data, multiplier):
    """Preserve mid and OHLC; transform observed bid/ask for all symbols."""
    if isinstance(data, Mapping):
        return {symbol: stress_quotes(frame, multiplier) for symbol, frame in data.items()}
    result = data.copy(deep=True)
    if multiplier != 1:
        half_extra = (result['ask'] - result['bid']) * ((multiplier - 1) / 2)
        result['ask'] = result['ask'] + half_extra
        result['bid'] = result['bid'] - half_extra
    return result


class DelayedEntryStrategy:
    """Delay one market-order batch; keep exits immediate and do not use old prices.

    A bar means one on_bar evaluation, not wall-clock time. New entry batches
    while waiting (including the release bar) are suppressed. Strategy exits or
    stop_trading cancel the queued batch. Expired orders are discarded. LIMIT
    orders cannot be delayed by this wrapper and fail explicitly.
    """
    def __init__(self, strategy, bars):
        self.strategy, self.bars = strategy, bars
        self.index = 0
        self.pending = None

    def on_bar(self, context):
        self.index += 1
        had_pending = self.pending is not None
        ctx = dict(context)
        ctx['delayed_entry_orders'] = () if not had_pending else tuple(self.pending[1])
        if hasattr(self.strategy, "on_bar"):
            action = self.strategy.on_bar(ctx)
        elif callable(self.strategy):
            action = self.strategy(ctx)
        else:
            raise TypeError("strategy must be callable or define on_bar(context)")
        if action is None:
            action = Action()
        if any(order.order_type is not OrderType.MARKET for order in action.orders):
            raise ValueError('entry delay supports MARKET orders only')
        if action.stop_trading or action.close_requests:
            self.pending = None
            return Action(close_requests=action.close_requests, stop_trading=action.stop_trading,
                          cancel_order_ids=action.cancel_order_ids)
        due = []
        if had_pending:
            step, orders = self.pending
            if self.index >= step:
                due = [o for o in orders if o.expires_at is None or
                       _timestamp(o.expires_at).timestamp() > float(context['time'])]
                self.pending = None
        elif action.orders:
            self.pending = self.index + self.bars, deepcopy(action.orders)
        return Action(orders=due, close_requests=action.close_requests,
                      cancel_order_ids=action.cancel_order_ids)


def _timestamp(value):
    return pd.to_datetime(value, unit='s', utc=True) if isinstance(value, Real) else pd.to_datetime(value, utc=True)


def period_performance(result, frequency):
    """UTC exit-date attribution of realized PnL (not marked-to-market returns)."""
    times = [_timestamp(p['time']) for p in result.equity_curve]
    trades = result.trades
    times += [_timestamp(t['exit_time']) for t in trades]
    if not times:
        return []
    periods = pd.period_range(min(times).tz_localize(None), max(times).tz_localize(None), freq=frequency)
    groups = {str(p): [] for p in periods}
    for trade in trades:
        key = str(_timestamp(trade['exit_time']).tz_localize(None).to_period(frequency))
        groups[key].append(trade)
    rows = []
    for key, group in groups.items():
        profits = np.array([t['realized_profit'] for t in group], dtype=float)
        gross_profit, gross_loss = profits[profits > 0].sum(), -profits[profits < 0].sum()
        rows.append({'period': key, 'net_profit': float(profits.sum()),
            'realized_pips': float(sum(t.get('realized_pips', 0) for t in group)),
            'total_trades': len(group), 'gross_profit': float(gross_profit),
            'gross_loss': float(gross_loss), 'winning_trades': int((profits > 0).sum()),
            'profit_factor': float(gross_profit/gross_loss) if gross_loss else None})
    return rows


def monte_carlo(result, samples, seed):
    """Realized cash PnL diagnostics; permutation keeps total PnL constant."""
    if not samples or not result.trades:
        return {}
    profits = np.array([t['realized_profit'] for t in result.trades], dtype=float)
    rng = np.random.default_rng(seed)
    output = {'samples': samples, 'seed': seed, 'unit': 'account_currency',
              'scope': 'realized_trade_pnl_not_intratrade_risk'}
    for kind in ('permutation', 'iid_bootstrap'):
        totals, drawdowns = [], []
        for _ in range(samples):
            p = rng.permutation(profits) if kind == 'permutation' else rng.choice(profits, len(profits), replace=True)
            curve = np.r_[0., p.cumsum()]
            totals.append(float(p.sum()))
            drawdowns.append(float((np.maximum.accumulate(curve)-curve).max()))
        output[kind] = {'total_profit_p05_p50_p95': np.quantile(totals,[.05,.5,.95]).tolist(),
            'max_drawdown_p50_p95_p99': np.quantile(drawdowns,[.5,.95,.99]).tolist()}
        if kind == 'iid_bootstrap':
            output[kind]['negative_profit_fraction'] = float((np.asarray(totals) < 0).mean())
    return output


def evaluate_robustness(*, config, center_params, model, baseline, data,
                        simulator_factory, strategy_factory, parameter_constraints,
                        result_constraints, window_index):
    """Fresh strategy and simulator per scenario, zero optimizer calls."""
    rows = []
    def pack(name, params, result, status='completed', violations=(), settings=None):
        checks = evaluate_constraints(result_constraints, result)
        return {'name':name, 'params':deepcopy(params), 'settings':settings or {},
            'status':status if checks.feasible else 'result_constraint_failed',
            'violations':list(violations)+list(checks.violations),
            'metrics':deepcopy(result.metrics),
            'delta_net_profit':float(result.metrics['net_profit']-baseline.metrics['net_profit']),
            'yearly':period_performance(result,'Y'), 'monthly':period_performance(result,'M')}
    rows.append(pack('baseline',center_params,baseline))
    for scenario in config.scenarios:
        params = deepcopy(center_params)
        for key, offset in scenario.parameter_offsets.items():
            if key not in params or isinstance(params[key], bool) or not isinstance(params[key], Real):
                raise ValueError(f'offset requires numeric selected parameter: {key}')
            params[key] += offset
        constraint = evaluate_constraints(parameter_constraints, params)
        settings = {'spread_multiplier':scenario.spread_multiplier,
            'entry_delay_bars':scenario.entry_delay_bars,
            'parameter_offsets':dict(scenario.parameter_offsets)}
        if not constraint.feasible:
            rows.append({'name':scenario.name,'params':params,'settings':settings,
                'status':'parameter_constraint_failed','violations':list(constraint.violations),
                'metrics':{},'delta_net_profit':None,'yearly':[],'monthly':[]})
            continue
        strategy = strategy_factory(deepcopy(params), deepcopy(model))
        if scenario.entry_delay_bars:
            strategy = DelayedEntryStrategy(strategy, scenario.entry_delay_bars)
        simulator = simulator_factory(stress_quotes(data, scenario.spread_multiplier))
        result = simulator.run(strategy)
        rows.append(pack(scenario.name,params,result,settings=settings))
    return {'scenarios':rows, 'monte_carlo':monte_carlo(baseline,config.monte_carlo_samples,config.seed+window_index),
            'selection_policy':'diagnostics_only_no_reoptimization'}


def summarize_robustness(windows):
    """Sum disjoint-window diagnostics; do not invent a compounded DD."""
    if not any(w.robustness_result is not None for w in windows):
        return None
    grouped = {}
    overlap = any(_timestamp(b.validation_start) < _timestamp(a.validation_end)
                  for a,b in zip(windows,windows[1:]))
    for window in windows:
        for row in (window.robustness_result or {}).get('scenarios',[]):
            grouped.setdefault(row['name'],[]).append(row)
    summaries = []
    for name, rows in grouped.items():
        valid = [r for r in rows if r['metrics']]
        periods = {}
        for row in valid:
            for year in row['yearly']:
                p=periods.setdefault(year['period'],{'period':year['period'],'net_profit':0.,'total_trades':0})
                p['net_profit'] += year['net_profit'];p['total_trades'] += year['total_trades']
        profits = [r['metrics']['net_profit'] for r in valid]
        gross_profit=sum(r['metrics'].get('gross_profit',0) for r in valid)
        gross_loss=sum(r['metrics'].get('gross_loss',0) for r in valid)
        summaries.append({'name':name,'evaluated_windows':len(valid),
            'skipped_windows':len(rows)-len(valid), 'net_profit':sum(profits) if valid else None,
            'profit_factor':gross_profit/gross_loss if gross_loss else None,
            'total_trades':sum(r['metrics'].get('total_trades',0) for r in valid),
            'negative_windows':sum(p<0 for p in profits),
            'worst_window_dd_pct':max((r['metrics'].get('max_drawdown_pct',0) for r in valid),default=None),
            'yearly':list(periods.values()),
            'without_best_year_profit':sum(p['net_profit'] for p in periods.values())-max(p['net_profit'] for p in periods.values()) if len(periods)>1 else None})
    return {'scenarios':summaries, 'overlapping_validation_windows':overlap,
            'aggregation':'sum_of_window_results_not_compounded_portfolio',
            'warning':'Overlapping validation windows double-count observations.' if overlap else None}
