"""Background execution for the UI: blocking backend calls never run on the GUI thread.

Results are delivered back on the GUI thread through Qt signals. Long operations can
stream progress events and be cancelled through a threading.Event.
"""

from __future__ import annotations

import itertools
import threading
import traceback
from collections.abc import Callable
from typing import Any

from nexus_core.errors import NexusError
from nexus_core.log import get_logger
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

log = get_logger("center.tasks")
_ids = itertools.count(1)


class _Signals(QObject):
    done = Signal(int, object)
    failed = Signal(int, str, str)
    progress = Signal(int, object)


class _Job(QRunnable):
    def __init__(
        self, job_id: int, fn: Callable[..., Any], signals: _Signals, cancel: threading.Event, with_progress: bool
    ) -> None:
        super().__init__()
        self.job_id, self.fn, self.signals, self.cancel, self.with_progress = job_id, fn, signals, cancel, with_progress

    def run(self) -> None:
        try:
            if self.with_progress:
                result = self.fn(lambda event: self.signals.progress.emit(self.job_id, event), self.cancel)
            else:
                result = self.fn()
            self.signals.done.emit(self.job_id, result)
        except NexusError as exc:
            self.signals.failed.emit(self.job_id, exc.message, exc.hint or "")
        except Exception as exc:
            log.debug("task failed\n%s", traceback.format_exc())
            self.signals.failed.emit(self.job_id, f"{exc.__class__.__name__}: {exc}", "")


class TaskRunner(QObject):
    """Small bounded pool (4 threads) shared by all modules."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self.pool.setExpiryTimeout(10_000)  # idle threads exit: no permanent workers
        self._callbacks: dict[int, tuple[Callable, Callable | None, Callable | None]] = {}
        self._cancels: dict[int, threading.Event] = {}
        self.signals = _Signals()
        self.signals.done.connect(self._on_done)
        self.signals.failed.connect(self._on_failed)
        self.signals.progress.connect(self._on_progress)

    def submit(
        self,
        fn: Callable[..., Any],
        on_done: Callable[[Any], None],
        on_error: Callable[[str, str], None] | None = None,
        on_progress: Callable[[Any], None] | None = None,
    ) -> int:
        job_id = next(_ids)
        cancel = threading.Event()
        self._callbacks[job_id] = (on_done, on_error, on_progress)
        self._cancels[job_id] = cancel
        self.pool.start(_Job(job_id, fn, self.signals, cancel, on_progress is not None))
        return job_id

    def cancel(self, job_id: int) -> None:
        if job_id in self._cancels:
            self._cancels[job_id].set()

    def wait(self, msecs: int = 5000) -> bool:
        return self.pool.waitForDone(msecs)

    @Slot(int, object)
    def _on_done(self, job_id: int, result: Any) -> None:
        cb = self._callbacks.pop(job_id, None)
        self._cancels.pop(job_id, None)
        if cb:
            cb[0](result)

    @Slot(int, str, str)
    def _on_failed(self, job_id: int, message: str, hint: str) -> None:
        cb = self._callbacks.pop(job_id, None)
        self._cancels.pop(job_id, None)
        if cb and cb[1]:
            cb[1](message, hint)

    @Slot(int, object)
    def _on_progress(self, job_id: int, event: Any) -> None:
        cb = self._callbacks.get(job_id)
        if cb and cb[2]:
            cb[2](event)
