from pathlib import Path

from rowlogger import RowLogger

from .errors import ResultSaveError


class TradeLogger:
    """Persist one trading event per CSV row using rowlogger."""

    def __init__(self, filepath, *, append=False):
        self.filepath = Path(filepath)
        self.append = append
        self._logger = RowLogger()

    def add(self, event):
        self._logger.add(event)
        self._logger.next_row()

    def save(self):
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            self._logger.save_csv(self.filepath, append=self.append)
            self._logger.reset()
        except OSError as error:
            raise ResultSaveError(self.filepath, error) from error

    def reset(self):
        self._logger.reset()
