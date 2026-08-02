"""Data types exchanged between strategies and the simulator."""

from __future__ import annotations

import copy
import dataclasses
import enum
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Mapping, Optional, Union

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore


class Side(str, enum.Enum):
    LONG = "long"
    SHORT = "short"

    @classmethod
    def from_value(cls, value: Union["Side", str]) -> "Side":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).lower())
        except ValueError as exc:
            raise ValueError(f"unsupported side: {value}") from exc


def to_serializable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if np is not None:
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return [to_serializable(item) for item in value.tolist()]
    if isinstance(value, enum.Enum):
        return to_serializable(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if dataclasses.is_dataclass(value):
        return to_serializable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): to_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_serializable(item) for item in value]
    return value


def normalize_metadata(metadata: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping")
    return {
        str(key): to_serializable(copy.deepcopy(value))
        for key, value in metadata.items()
    }


@dataclass(frozen=True)
class Order:
    side: Side
    lot_size: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "side", Side.from_value(self.side))
        object.__setattr__(self, "lot_size", float(self.lot_size))
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))
        if not math.isfinite(self.lot_size) or self.lot_size <= 0:
            raise ValueError("lot_size must be positive")


@dataclass(frozen=True)
class CloseRequest:
    position_id: int

    def __post_init__(self):
        object.__setattr__(self, "position_id", int(self.position_id))


@dataclass(frozen=True)
class Action:
    orders: List[Order] = field(default_factory=list)
    close_requests: List[CloseRequest] = field(default_factory=list)
    stop_trading: bool = False

    def __post_init__(self):
        object.__setattr__(self, "orders", list(self.orders))
        object.__setattr__(self, "close_requests", list(self.close_requests))


@dataclass
class Position:
    position_id: int
    side: Side
    entry_price: float
    lot_size: float
    time: Any
    symbol: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    environment: str = "sim"
    entry_commission: float = 0.0

    def __post_init__(self):
        self.side = Side.from_value(self.side)
        self.entry_price = float(self.entry_price)
        self.lot_size = float(self.lot_size)
        self.entry_commission = float(self.entry_commission)
        self.metadata = normalize_metadata(self.metadata)


def make_position_snapshot(position: Position) -> Dict[str, Any]:
    snapshot = {
        "position_id": position.position_id,
        "side": position.side.value,
        "entry_price": position.entry_price,
        "lot_size": position.lot_size,
        "time": position.time,
        "symbol": position.symbol,
        "environment": position.environment,
        "metadata": normalize_metadata(position.metadata),
        "entry_commission": position.entry_commission,
    }
    return to_serializable(snapshot)
