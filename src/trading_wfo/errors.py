class TradingWFOError(Exception):
    """Base exception for trading-wfo."""


class StrategyExecutionError(TradingWFOError):
    """Raised when user strategy code fails while processing a bar."""

    def __init__(self, step_index, time, original_error):
        self.step_index = step_index
        self.time = time
        self.original_error = original_error
        super().__init__(
            f"strategy failed at step_index={step_index}, time={time}: "
            f"{original_error}"
        )


class ResultSaveError(TradingWFOError):
    """Raised when a result or trade log cannot be written."""

    def __init__(self, filepath, original_error):
        self.filepath = filepath
        self.original_error = original_error
        super().__init__(f"could not save to {filepath}: {original_error}")

