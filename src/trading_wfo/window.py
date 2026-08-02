import re
import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Iterator, Optional, Union

import pandas as pd

from ._data import prepare_market_data


_PERIOD_PATTERN = re.compile(r"^(?P<value>[1-9]\d*)(?P<unit>min|h|d|w|mo|y)$")


@dataclass(frozen=True)
class WindowPeriod:
    value: int
    unit: str

    @classmethod
    def parse(cls, period: Union["WindowPeriod", str]) -> "WindowPeriod":
        if isinstance(period, cls):
            return period
        if not isinstance(period, str):
            raise TypeError("period must be a string such as '12h', '7d', or '3mo'")
        match = _PERIOD_PATTERN.fullmatch(period.strip().lower())
        if match is None:
            raise ValueError(
                "invalid period; use min, h, d, w, mo, or y (for example '30min' or '3mo')"
            )
        return cls(value=int(match.group("value")), unit=match.group("unit"))

    def add_to(self, timestamp: pd.Timestamp) -> pd.Timestamp:
        if self.unit == "min":
            return timestamp + pd.Timedelta(minutes=self.value)
        if self.unit == "h":
            return timestamp + pd.Timedelta(hours=self.value)
        if self.unit == "d":
            return timestamp + pd.Timedelta(days=self.value)
        if self.unit == "w":
            return timestamp + pd.Timedelta(weeks=self.value)
        if self.unit == "mo":
            return timestamp + pd.DateOffset(months=self.value)
        return timestamp + pd.DateOffset(years=self.value)

    def subtract_from(self, timestamp: pd.Timestamp) -> pd.Timestamp:
        if self.unit == "min":
            return timestamp - pd.Timedelta(minutes=self.value)
        if self.unit == "h":
            return timestamp - pd.Timedelta(hours=self.value)
        if self.unit == "d":
            return timestamp - pd.Timedelta(days=self.value)
        if self.unit == "w":
            return timestamp - pd.Timedelta(weeks=self.value)
        if self.unit == "mo":
            return timestamp - pd.DateOffset(months=self.value)
        return timestamp - pd.DateOffset(years=self.value)


class DatasetMode(str, Enum):
    BACKTEST = "backtest"
    WALK_FORWARD = "walk_forward"


@dataclass(frozen=True)
class WalkForwardWindow:
    index: int
    training_data: Optional[pd.DataFrame]
    optimization_data: pd.DataFrame
    validation_data: pd.DataFrame
    training_start: Optional[pd.Timestamp]
    training_end: Optional[pd.Timestamp]
    optimization_start: pd.Timestamp
    optimization_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp


class TradingDataset:
    """Prepare either one backtest dataset or walk-forward windows."""

    def __init__(
        self,
        data: pd.DataFrame,
        *,
        optimization_period=None,
        validation_period=None,
        training_period=None,
        step_period=None,
        backtest_period=None,
    ):
        self.data = prepare_market_data(data, sort=True)
        if len(self.data) < 2:
            raise ValueError("data must contain at least two rows")

        has_optimization = optimization_period is not None
        has_validation = validation_period is not None
        has_training = training_period is not None
        has_wfo_period = has_training or has_optimization or has_validation

        if backtest_period is not None and has_wfo_period:
            raise ValueError(
                "backtest_period cannot be combined with training, optimization, or validation periods"
            )
        if has_training and not has_optimization:
            raise ValueError("training_period requires optimization_period")
        if has_optimization != has_validation:
            raise ValueError(
                "optimization_period and validation_period must be specified together"
            )
        if step_period is not None and not has_optimization:
            raise ValueError("step_period is only valid in walk-forward mode")

        if not has_wfo_period:
            self.mode = DatasetMode.BACKTEST
            self.backtest_period = (
                None
                if backtest_period is None
                else WindowPeriod.parse(backtest_period)
            )
            self.training_period = None
            self.optimization_period = None
            self.validation_period = None
            self.step_period = None
            self._backtest_data = self._create_backtest_data()
        else:
            self.mode = DatasetMode.WALK_FORWARD
            self.backtest_period = None
            self.training_period = (
                None
                if training_period is None
                else WindowPeriod.parse(training_period)
            )
            self.optimization_period = WindowPeriod.parse(optimization_period)
            self.validation_period = WindowPeriod.parse(validation_period)
            self.step_period = WindowPeriod.parse(
                validation_period if step_period is None else step_period
            )
            self._backtest_data = None

    @classmethod
    def from_dataframe(cls, data, **window_options):
        return cls(data, **window_options)

    @classmethod
    def from_csv(
        cls,
        paths,
        *,
        optimization_period=None,
        validation_period=None,
        training_period=None,
        step_period=None,
        backtest_period=None,
        read_csv_kwargs=None,
    ):
        csv_paths = cls._resolve_csv_paths(paths)
        options = {} if read_csv_kwargs is None else dict(read_csv_kwargs)
        frames = [pd.read_csv(path, **options) for path in csv_paths]
        data = pd.concat(frames, ignore_index=True)
        return cls(
            data,
            training_period=training_period,
            optimization_period=optimization_period,
            validation_period=validation_period,
            step_period=step_period,
            backtest_period=backtest_period,
        )

    @staticmethod
    def _resolve_csv_paths(paths):
        if isinstance(paths, (str, Path)):
            paths = [paths]
        elif not isinstance(paths, Iterable):
            raise TypeError("paths must be a CSV path, directory, or iterable of paths")

        resolved = []
        for value in paths:
            path = Path(value)
            if path.is_dir():
                resolved.extend(sorted(path.glob("*.csv")))
            elif path.is_file():
                resolved.append(path)
            else:
                raise FileNotFoundError(path)
        if not resolved:
            raise ValueError("no CSV files were found")
        return resolved

    def windows(self) -> Iterator[WalkForwardWindow]:
        if self.mode is DatasetMode.BACKTEST:
            raise RuntimeError("windows() is only available in walk-forward mode")
        window_start = self.data["time"].iloc[0]
        coverage_end = self._coverage_end()
        previous_validation_end = None
        overlap_warned = False
        gap_warned = False
        window_index = 0

        while True:
            if self.training_period is None:
                training_start = None
                training_end = None
                optimization_start = window_start
            else:
                training_start = window_start
                training_end = self.training_period.add_to(training_start)
                optimization_start = training_end

            optimization_end = self.optimization_period.add_to(optimization_start)
            validation_start = optimization_end
            validation_end = self.validation_period.add_to(validation_start)
            if validation_end > coverage_end:
                break

            if previous_validation_end is not None:
                if validation_start < previous_validation_end and not overlap_warned:
                    warnings.warn(
                        "Validation windows overlap because step_period is shorter than the validation progression.",
                        UserWarning,
                        stacklevel=2,
                    )
                    overlap_warned = True
                elif validation_start > previous_validation_end and not gap_warned:
                    warnings.warn(
                        "Validation windows contain gaps because step_period is longer than the validation progression.",
                        UserWarning,
                        stacklevel=2,
                    )
                    gap_warned = True

            training_data = (
                None
                if training_start is None
                else self._slice(training_start, training_end, "training")
            )
            optimization_data = self._slice(
                optimization_start, optimization_end, "optimization"
            )
            validation_data = self._slice(
                validation_start, validation_end, "validation"
            )
            yield WalkForwardWindow(
                index=window_index,
                training_data=training_data,
                optimization_data=optimization_data,
                validation_data=validation_data,
                training_start=training_start,
                training_end=training_end,
                optimization_start=optimization_start,
                optimization_end=optimization_end,
                validation_start=validation_start,
                validation_end=validation_end,
            )

            previous_validation_end = validation_end
            window_start = self.step_period.add_to(window_start)
            window_index += 1

    def __iter__(self):
        return self.windows()

    @property
    def backtest_data(self):
        if self.mode is not DatasetMode.BACKTEST:
            raise RuntimeError(
                "backtest_data is only available in backtest mode"
            )
        return self._backtest_data.copy()

    def _create_backtest_data(self):
        if self.backtest_period is None:
            return self.data.copy()
        end = self._coverage_end()
        start = self.backtest_period.subtract_from(end)
        return self._slice(start, end, "backtest")

    def _coverage_end(self):
        minimum_interval = self.data["time"].diff().dropna().min()
        return self.data["time"].iloc[-1] + minimum_interval

    def _slice(self, start, end, section_name):
        section = self.data.loc[
            (self.data["time"] >= start) & (self.data["time"] < end)
        ].copy()
        if section.empty:
            raise ValueError(
                f"{section_name} period contains no rows: {start} to {end}"
            )
        return section.reset_index(drop=True)
