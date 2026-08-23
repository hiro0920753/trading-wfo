"""Self-contained machine-learning WFO example.

For every chronological window this example:
1. fits a tiny logistic model on the training section,
2. optimizes the probability threshold on the optimization section, and
3. evaluates the selected threshold once on the validation section.

The synthetic prices and model are educational, not a trading recommendation.
"""
from __future__ import annotations

import argparse
import numpy as np
import pandas as pd

from trading_wfo import (
    Action,
    CategoricalParameter,
    CloseRequest,
    GridOptimizer,
    Order,
    Side,
    TradingDataset,
    TradingSimulator,
    TrainingResult,
    WalkForwardRunner,
)


PARAMS = {
    "common": {
        "units_per_lot": 100,
        "symbol": "ML-DEMO",
        "price_per_pip": 1,
    },
    "strategy_base": {"lookback_bars": 5, "leverage": 10},
    "asset": {"balance": 10_000},
}


def feature_matrix(close: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Build causal return features and the following-bar direction label."""
    returns = np.diff(close) / close[:-1]
    rows, labels = [], []
    for index in range(3, len(returns)):
        rows.append([returns[index - 1], returns[index - 3:index].mean()])
        labels.append(float(returns[index] > 0))
    return np.asarray(rows, dtype=float), np.asarray(labels, dtype=float)


class LogisticDirectionTrainer:
    """Small NumPy-only trainer; replace this with sklearn, PyTorch, etc."""

    def __init__(self, validation_ratio=0.2, epochs=300, learning_rate=0.2):
        self.validation_ratio = float(validation_ratio)
        self.epochs = int(epochs)
        self.learning_rate = float(learning_rate)
        if not 0 < self.validation_ratio < 1:
            raise ValueError("validation_ratio must be between 0 and 1")
        if self.epochs <= 0:
            raise ValueError("epochs must be positive")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")

    def fit(self, data: pd.DataFrame) -> TrainingResult:
        x, y = feature_matrix(data["close"].to_numpy(dtype=float))
        split = int(len(x) * (1.0 - self.validation_ratio))
        split = min(max(1, split), len(x) - 1)
        x_train, y_train = x[:split], y[:split]
        x_valid, y_valid = x[split:], y[split:]
        mean = x_train.mean(axis=0)
        scale = x_train.std(axis=0)
        scale[scale == 0] = 1.0
        normalized = (x_train - mean) / scale
        design = np.column_stack([np.ones(len(normalized)), normalized])
        weights = np.zeros(design.shape[1])
        for _ in range(self.epochs):
            probability = 1.0 / (1.0 + np.exp(-(design @ weights)))
            gradient = design.T @ (probability - y_train) / len(y_train)
            gradient[1:] += 0.01 * weights[1:]
            weights -= self.learning_rate * gradient
        model = {"mean": mean, "scale": scale, "weights": weights}

        def binary_cross_entropy(features, labels):
            normalized_features = (features - mean) / scale
            matrix = np.column_stack([np.ones(len(normalized_features)), normalized_features])
            probability = 1.0 / (1.0 + np.exp(-(matrix @ weights)))
            probability = np.clip(probability, 1e-9, 1 - 1e-9)
            return float(-np.mean(labels * np.log(probability) + (1 - labels) * np.log(1 - probability)))

        return TrainingResult(
            model=model,
            artifacts={
                "model_type": "numpy_logistic_regression",
                "weights": weights,
                "feature_mean": mean,
                "feature_scale": scale,
                "train_loss": binary_cross_entropy(x_train, y_train),
                "valid_loss": binary_cross_entropy(x_valid, y_valid),
                "train_samples": len(x_train),
                "valid_samples": len(x_valid),
                "validation_ratio": self.validation_ratio,
                "internal_validation": "tail_of_training_period",
                "epochs": self.epochs,
                "learning_rate": self.learning_rate,
            },
        )


class MLDirectionStrategy:
    def __init__(self, probability_threshold: float, lot_size: float, model):
        self.threshold = float(probability_threshold)
        self.lot_size = float(lot_size)
        self.model = model

    def predict_up_probability(self, closes: np.ndarray) -> float:
        returns = np.diff(closes) / closes[:-1]
        features = np.asarray([returns[-1], returns[-3:].mean()])
        normalized = (features - self.model["mean"]) / self.model["scale"]
        score = np.r_[1.0, normalized] @ self.model["weights"]
        return float(1.0 / (1.0 + np.exp(-score)))

    def on_bar(self, context):
        closes = context["bars"]["close"].to_numpy(dtype=float)
        if len(closes) < 4:
            return Action()
        probability = self.predict_up_probability(closes)
        if probability >= self.threshold:
            close_requests = [
                CloseRequest(position["position_id"])
                for position in context["short_positions"]
            ]
            orders = [] if context["long_positions"] else [
                Order(Side.LONG, self.lot_size, metadata={"p_up": probability})
            ]
            return Action(orders=orders, close_requests=close_requests)
        if probability <= 1.0 - self.threshold:
            close_requests = [
                CloseRequest(position["position_id"])
                for position in context["long_positions"]
            ]
            orders = [] if context["short_positions"] else [
                Order(Side.SHORT, self.lot_size, metadata={"p_up": probability})
            ]
            return Action(orders=orders, close_requests=close_requests)
        return Action()


def make_demo_data() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    direction = 1.0
    changes = []
    for index in range(180):
        if index % 30 == 0:
            direction *= -1
        changes.append(0.18 * direction + rng.normal(0, 0.35))
    close = 100.0 + np.cumsum(changes)
    return pd.DataFrame({
        "time": pd.date_range("2025-01-01", periods=len(close), freq="1D", tz="UTC"),
        "bid": close,
        "ask": close + 0.05,
        "open": close,
        "high": close + 0.20,
        "low": close - 0.20,
        "close": close,
    })


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validation-ratio", type=float, default=0.2,
        help="Tail fraction of each AI training section used for internal validation (default: 0.2)",
    )
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--learning-rate", type=float, default=0.2)
    return parser.parse_args()


def main(args=None):
    args = parse_args() if args is None else args
    dataset = TradingDataset.from_dataframe(
        make_demo_data(),
        training_period="60d",
        optimization_period="30d",
        validation_period="30d",
        warmup_bars=5,
    )
    runner = WalkForwardRunner(
        trainer=LogisticDirectionTrainer(
            validation_ratio=args.validation_ratio,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
        ),
        simulator_factory=lambda data: TradingSimulator(PARAMS, None, data),
        strategy_factory=lambda params, model: MLDirectionStrategy(
            **params, model=model
        ),
        optimizer=GridOptimizer({
            "probability_threshold": CategoricalParameter([0.52, 0.56, 0.60]),
            "lot_size": CategoricalParameter([0.01]),
        }),
        n_trials=3,
        progress=True,
        result_path="results/ml_direction_wfo.json",
    )
    result = runner.run(dataset)
    for window in result.windows:
        print(
            window.index,
            window.training_start.date(), "training ->",
            window.optimization_start.date(), "optimization ->",
            window.validation_start.date(), "validation",
            window.best_params,
        )
    print(result.aggregate_metrics)
    return result


if __name__ == "__main__":
    main()
