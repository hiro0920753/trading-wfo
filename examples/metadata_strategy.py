"""Example of the dataclass-based strategy contract."""

from typing import Any, Mapping

from trading_wfo import Action, Order, Position, Side

def make_entry_order(
    *,
    side: Side,
    lot_size: float,
    atr_pips: float,
    rsi: float,
    ma_gap_pips: float,
    strategy_type: str,
    extra: Mapping[str, Any] = None,
) -> Order:
    metadata = {
        "atr_pips": atr_pips,
        "rsi": rsi,
        "ma_gap_pips": ma_gap_pips,
        "strategy_type": strategy_type,
    }
    if extra:
        metadata.update(dict(extra))

    return Order(side=side, lot_size=lot_size, metadata=metadata)


def read_entry_context(position: Position):
    metadata = position.metadata
    return {
        "strategy_type": metadata.get("strategy_type", "unknown"),
        "atr_pips": metadata.get("atr_pips"),
        "rsi": metadata.get("rsi"),
        "ma_gap_pips": metadata.get("ma_gap_pips"),
    }


# Strategy action example:
action = Action(
    orders=[make_entry_order(
        side=Side.LONG,
        lot_size=0.1,
        atr_pips=12.4,
        rsi=-0.08,
        ma_gap_pips=4.2,
        strategy_type="pullback",
        extra={"model_confidence": 0.73},
    )],
)
