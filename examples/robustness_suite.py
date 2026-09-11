"""Small synthetic WFO demo, not evidence of a profitable trading strategy.

Run: python examples/robustness_suite.py
Then: trading-wfo dashboard --help  (point its result option at the saved JSON)
"""
from pathlib import Path
import numpy as np
import pandas as pd
from trading_wfo import (Action, CloseRequest, Order, Side, TradingSimulator,
    TradingDataset, WalkForwardRunner, GridOptimizer, CategoricalParameter,
    RobustnessConfig, StressScenario)

PARAMS={'common':{'symbol':'DEMO','units_per_lot':100000,'price_per_pip':.01},
        'strategy_base':{'lookback_bars':10,'leverage':25},
        'asset':{'balance':100000}}


class Momentum:
    def __init__(self, lookback): self.lookback=lookback
    def on_bar(self, context):
        close=context['bars']['close']
        rising=close.iloc[-1]>close.iloc[-self.lookback]
        if context['long_positions']:
            return Action(close_requests=[] if rising else [
                CloseRequest(p['position_id'],reason='momentum_reversal') for p in context['long_positions']])
        return Action(orders=[Order(Side.LONG,.03)] if rising else [])


def main():
    rng=np.random.default_rng(42)
    price=150+np.cumsum(rng.normal(.005,.18,400))
    spread=rng.uniform(.005,.015,len(price))
    data=pd.DataFrame({'time':pd.date_range('2025-01-01',periods=len(price),freq='D'),
        'open':price,'high':price+.1,'low':price-.1,'close':price,'bid':price,'ask':price+spread})
    dataset=TradingDataset.from_dataframe(data,optimization_period='90d',validation_period='60d',warmup_bars=10)
    runner=WalkForwardRunner(
        simulator_factory=lambda frame:TradingSimulator(PARAMS,None,frame),
        strategy_factory=lambda params,model:Momentum(params['lookback']),
        optimizer=GridOptimizer({'lookback':CategoricalParameter([4,6])}),n_trials=2,
        robustness=RobustnessConfig(scenarios=(
            StressScenario('spread_x1.25',spread_multiplier=1.25),
            StressScenario('spread_x1.5',spread_multiplier=1.5),
            StressScenario('spread_x2',spread_multiplier=2),
            StressScenario('entry_1bar_later',entry_delay_bars=1),
            StressScenario('lookback_plus1',parameter_offsets={'lookback':1}),
        ),monte_carlo_samples=200,seed=42))
    result=runner.run(dataset)
    path=Path('results/robustness_demo.json')
    result.save_json(path);result.save_csv(path.with_suffix('.csv'))
    print(path)


if __name__=='__main__':main()
