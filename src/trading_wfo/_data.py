import pandas as pd
import numpy as np


REQUIRED_COLUMNS = {"time", "bid", "ask", "open", "high", "low", "close"}


def prepare_market_data(data, *, sort=False):
    """Validate market data without resampling or filling missing bars."""
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas.DataFrame")

    frame = data.copy()
    if frame.empty:
        raise ValueError("data must not be empty")
    if "time" not in frame.columns:
        if not isinstance(frame.index, pd.DatetimeIndex):
            raise ValueError("data requires a 'time' column or DatetimeIndex")
        frame.insert(0, "time", frame.index)

    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"data is missing required columns: {', '.join(missing)}")

    if pd.api.types.is_numeric_dtype(frame["time"]):
        frame["time"] = pd.to_datetime(frame["time"], unit="s")
    else:
        frame["time"] = pd.to_datetime(frame["time"])

    if frame["time"].isna().any():
        raise ValueError("data contains invalid time values")
    if sort:
        frame = frame.sort_values("time", kind="stable")
    if frame["time"].duplicated().any():
        raise ValueError("data contains duplicate time values")
    if not frame["time"].is_monotonic_increasing:
        raise ValueError("data must be sorted by time")

    numeric_columns = ["bid", "ask", "open", "high", "low", "close"]
    frame[numeric_columns] = frame[numeric_columns].astype(float)
    if not np.isfinite(frame[numeric_columns].to_numpy()).all():
        raise ValueError("market prices must not contain NaN or infinity")
    if (frame["ask"] < frame["bid"]).any():
        raise ValueError("ask price must be greater than or equal to bid price")
    return frame.reset_index(drop=True)
