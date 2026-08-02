class CLIProgress:
    """Small stdout progress reporter for TPE and walk-forward runs."""

    def __init__(self, stream=None):
        if stream is None:
            import sys

            stream = sys.stdout
        self.stream = stream

    def wfo_started(self, total_windows):
        self._write(f"[WFO] Starting {total_windows} window(s)")

    def window_started(self, index, total_windows):
        self._write(f"[WFO] Window {index + 1}/{total_windows}: optimizing")

    def trial_completed(
        self, number, total_trials, score, best_score, *, status="completed"
    ):
        if score is None:
            self._write(
                f"[TPE] Trial {number + 1}/{total_trials}: {status}"
            )
            return
        self._write(
            f"[TPE] Trial {number + 1}/{total_trials}: "
            f"score={score:.6g}, best={best_score:.6g}"
        )

    def window_completed(self, index, total_windows, score):
        self._write(
            f"[WFO] Window {index + 1}/{total_windows}: "
            f"validation_score={score:.6g}"
        )

    def wfo_completed(self, total_windows):
        self._write(f"[WFO] Completed {total_windows} window(s)")

    def _write(self, message):
        print(message, file=self.stream, flush=True)
