import unittest

import trading_wfo


class PublicApiTest(unittest.TestCase):
    def test_expected_types_are_public(self):
        self.assertIn("TradingSimulator", trading_wfo.__all__)
        self.assertIn("AccountConfig", trading_wfo.__all__)
        self.assertIn("Action", trading_wfo.__all__)
        self.assertIn("Order", trading_wfo.__all__)
        self.assertIn("Position", trading_wfo.__all__)
        self.assertIn("Side", trading_wfo.__all__)
        self.assertIn("TradingDataset", trading_wfo.__all__)
        self.assertIn("DatasetMode", trading_wfo.__all__)
        self.assertIn("WalkForwardWindow", trading_wfo.__all__)
        self.assertIn("WindowPeriod", trading_wfo.__all__)
        self.assertIn("SimulationResult", trading_wfo.__all__)
        self.assertIn("TPEOptimizer", trading_wfo.__all__)
        self.assertIn("OptimizationResult", trading_wfo.__all__)
        self.assertIn("WalkForwardRunner", trading_wfo.__all__)
        self.assertIn("WalkForwardResult", trading_wfo.__all__)
        self.assertIn("TradeLogger", trading_wfo.__all__)
        self.assertIn("CLIProgress", trading_wfo.__all__)
        self.assertIn("ConstraintResult", trading_wfo.__all__)
        self.assertIn("ExecutionConfig", trading_wfo.__all__)
        self.assertIn("StrategyExecutionError", trading_wfo.__all__)
        self.assertIn("Strategy", trading_wfo.__all__)
        self.assertIn("StrategyContext", trading_wfo.__all__)
        self.assertIn("ResultSaveError", trading_wfo.__all__)
        self.assertIn("Optimizer", trading_wfo.__all__)
        self.assertIn("ObjectiveResult", trading_wfo.__all__)
        self.assertIn("ParameterStabilityResult", trading_wfo.__all__)
        self.assertIn("ParameterVariationResult", trading_wfo.__all__)

    def test_internal_implementation_types_are_not_public(self):
        self.assertNotIn("Account", trading_wfo.__all__)
        self.assertNotIn("Portfolio", trading_wfo.__all__)
        self.assertNotIn("Execution", trading_wfo.__all__)


if __name__ == "__main__":
    unittest.main()
