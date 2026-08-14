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


class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"

    @classmethod
    def from_value(cls, value: Union["OrderType", str]) -> "OrderType":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).lower())
        except ValueError as exc:
            raise ValueError(f"unsupported order type: {value}") from exc


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
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    symbol: Optional[str] = None
    expires_at: Any = None

    def __post_init__(self):
        object.__setattr__(self, "side", Side.from_value(self.side))
        object.__setattr__(self, "lot_size", float(self.lot_size))
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))
        object.__setattr__(self, "order_type", OrderType.from_value(self.order_type))
        if self.limit_price is not None:
            object.__setattr__(self, "limit_price", float(self.limit_price))
        if self.symbol is not None:
            symbol = str(self.symbol).strip()
            if not symbol:
                raise ValueError("symbol must not be empty")
            object.__setattr__(self, "symbol", symbol)
        if not math.isfinite(self.lot_size) or self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        if self.order_type is OrderType.LIMIT:
            if self.limit_price is None or not math.isfinite(self.limit_price):
                raise ValueError("limit orders require a finite limit_price")
        elif self.limit_price is not None:
            raise ValueError("market orders must not specify limit_price")


@dataclass
class PendingOrder:
    pending_order_id: int
    side: Side
    lot_size: float
    limit_price: float
    symbol: str
    submitted_time: Any
    expires_at: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.pending_order_id = int(self.pending_order_id)
        self.side = Side.from_value(self.side)
        self.lot_size = float(self.lot_size)
        self.limit_price = float(self.limit_price)
        self.symbol = str(self.symbol)
        self.metadata = normalize_metadata(self.metadata)


@dataclass(frozen=True)
class CloseRequest:
    position_id: int
    reason: str = "close_request"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "position_id", int(self.position_id))
        reason = str(self.reason).strip()
        if not reason:
            raise ValueError("close request reason must not be empty")
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True)
class Action:
    orders: List[Order] = field(default_factory=list)
    close_requests: List[CloseRequest] = field(default_factory=list)
    stop_trading: bool = False
    cancel_order_ids: List[int] = field(default_factory=list)

    def __post_init__(self):
        object.__setattr__(self, "orders", list(self.orders))
        object.__setattr__(self, "close_requests", list(self.close_requests))
        object.__setattr__(self, "cancel_order_ids", [int(value) for value in self.cancel_order_ids])


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
    mfe_pips: float = 0.0
    mae_pips: float = 0.0
    mfe_time: Any = None
    mae_time: Any = None

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
        "mfe_pips": position.mfe_pips,
        "mae_pips": position.mae_pips,
        "mfe_time": position.mfe_time,
        "mae_time": position.mae_time,
    }
    return to_serializable(snapshot)
