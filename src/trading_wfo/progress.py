import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


class CLIProgress:
    """Small stdout progress reporter for TPE and walk-forward runs."""

    def __init__(self, stream=None):
        if stream is None:
            import sys

            stream = sys.stdout
        self.stream = stream
        self._lock = threading.Lock()

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
        with self._lock:
            print(message, file=self.stream, flush=True)


class ProgressTracker:
    """Thread-safe live WFO progress writer consumed by the dashboard."""

    def __init__(self, path, *, workers=1):
        self.path = Path(path)
        self.workers = workers
        self._lock = threading.Lock()
        self._started = None
        self._state = {}

    def wfo_started(self, total_windows):
        with self._lock:
            self._started = time.monotonic()
            self._state = {
                "status": "running", "total_windows": total_windows,
                "completed_windows": 0, "current_window": None,
                "total_trials": 0, "completed_trials": 0,
                "completed_trials_all_windows": 0,
                "optimization_workers": self.workers,
                "started_at": self._now(), "last_score": None,
                "best_score": None, "message": "Preparing first window",
            }
            self._save()

    def window_started(self, index, total_windows):
        with self._lock:
            self._state.update(current_window=index + 1, total_windows=total_windows,
                               completed_trials=0, message="Optimizing trials")
            self._save()

    def trial_completed(self, number, total_trials, score, best_score, *, status="completed"):
        with self._lock:
            self._state["total_trials"] = total_trials
            self._state["completed_trials"] += 1
            self._state["completed_trials_all_windows"] += 1
            self._state.update(last_trial=number + 1, last_score=score,
                               best_score=best_score, trial_status=status)
            self._save()

    def window_completed(self, index, total_windows, score):
        with self._lock:
            self._state.update(completed_windows=index + 1, current_window=index + 1,
                               validation_score=score, message="Window completed")
            self._save()

    def wfo_completed(self, total_windows):
        with self._lock:
            self._state.update(status="completed", completed_windows=total_windows,
                               message="Walk-forward run completed")
            self._save(force_remaining=0)

    def _save(self, force_remaining=None):
        elapsed = max(0.0, time.monotonic() - self._started) if self._started else 0.0
        total = self._state.get("total_windows", 0) * self._state.get("total_trials", 0)
        completed = self._state.get("completed_trials_all_windows", 0)
        remaining = force_remaining
        if remaining is None and completed and total >= completed:
            remaining = elapsed / completed * (total - completed)
        payload = dict(self._state, elapsed_seconds=elapsed,
                       estimated_remaining_seconds=remaining, updated_at=self._now())
        payload["estimated_completion"] = (
            None if remaining is None else
            (datetime.now(timezone.utc) + timedelta(seconds=remaining)).isoformat()
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        # Windows denies replace() while the dashboard or an indexer briefly
        # holds the destination open. Progress reporting must never abort WFO.
        for attempt in range(20):
            try:
                temporary.replace(self.path)
                break
            except PermissionError:
                if attempt == 19:
                    return
                time.sleep(0.025)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()


class CompositeProgress:
    """Forward progress events to multiple reporters."""

    def __init__(self, *reporters):
        self.reporters = tuple(reporter for reporter in reporters if reporter is not None)

    def __getattr__(self, name):
        def forward(*args, **kwargs):
            for reporter in self.reporters:
                getattr(reporter, name)(*args, **kwargs)
        return forward
