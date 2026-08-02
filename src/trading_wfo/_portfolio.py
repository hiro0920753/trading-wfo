from .models import Position, Side


class Portfolio:
    """Internal position container; not part of the public API."""

    def __init__(self):
        self._long_positions = []
        self._short_positions = []

    def positions(self):
        return tuple([*self._long_positions, *self._short_positions])

    def long_positions(self):
        return tuple(self._long_positions)

    def short_positions(self):
        return tuple(self._short_positions)

    def open_position(self, position):
        if not isinstance(position, Position):
            raise TypeError("position must be a Position")
        if position.side is Side.LONG:
            self._long_positions.append(position)
        elif position.side is Side.SHORT:
            self._short_positions.append(position)

    def close_position(self, position_id):
        closed = self.close_positions([position_id])
        return closed[0] if closed else None

    def close_positions(self, position_ids):
        ids = set(position_ids)
        closed = [p for p in self.positions() if p.position_id in ids]
        self._long_positions = [
            p for p in self._long_positions if p.position_id not in ids
        ]
        self._short_positions = [
            p for p in self._short_positions if p.position_id not in ids
        ]
        return closed

    def close_all(self):
        closed = list(self.positions())
        self._long_positions.clear()
        self._short_positions.clear()
        return closed
