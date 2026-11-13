"""Base class for module controllers (the Python side of each Command Center page).

A controller exposes one ``data`` map (bound from QML as ``controller.data.xyz``),
``busy``/``error`` state and slots. Controllers are created lazily the first time a
page is opened and receive activate()/deactivate() when the page is shown/hidden, so
polling timers only run while the page is visible.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nexus_core import activity, notifications
from pydantic import BaseModel
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from nexus_center.tasks import TaskRunner


def to_qml(value: Any) -> Any:
    """Convert pydantic models / tuples into plain QML-friendly structures."""
    if isinstance(value, BaseModel):
        return to_qml(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): to_qml(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_qml(v) for v in value]
    return value


class ModuleController(QObject):
    dataChanged = Signal()
    busyChanged = Signal()
    errorChanged = Signal()
    toast = Signal(str, str)  # severity, message

    poll_interval_ms = 0  # >0: refresh() runs periodically while the page is visible

    def __init__(self, tasks: TaskRunner, app: Any = None) -> None:
        super().__init__()
        self.tasks = tasks
        self.app = app
        self._data: dict[str, Any] = {}
        self._busy = 0
        self._error = ""
        self._active = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)

    # ------------------------------------------------------------ properties
    def _get_data(self) -> dict:
        return self._data

    def _get_busy(self) -> bool:
        return self._busy > 0

    def _get_error(self) -> str:
        return self._error

    data = Property("QVariantMap", _get_data, notify=dataChanged)
    busy = Property(bool, _get_busy, notify=busyChanged)
    error = Property(str, _get_error, notify=errorChanged)

    def set(self, **values: Any) -> None:
        self._data = {**self._data, **{k: to_qml(v) for k, v in values.items()}}
        self.dataChanged.emit()

    def set_error(self, message: str, hint: str = "") -> None:
        self._error = message + (f"\n{hint}" if hint else "")
        self.errorChanged.emit()

    # ------------------------------------------------------------ lifecycle
    @Slot()
    def activate(self) -> None:
        self._active = True
        self.refresh()
        interval = self.effective_interval()
        if interval > 0:
            self._timer.start(interval)

    @Slot()
    def deactivate(self) -> None:
        self._active = False
        self._timer.stop()

    def effective_interval(self) -> int:
        if self.poll_interval_ms and self.app is not None:
            return int(self.app.monitoring_interval_ms)
        return self.poll_interval_ms

    @Slot()
    def refresh(self) -> None:  # override
        pass

    # ------------------------------------------------------------ helpers
    def run(
        self,
        fn: Callable[[], Any],
        on_done: Callable[[Any], None],
        *,
        label: str = "",
        progress: Callable[[Any], None] | None = None,
        record: tuple[str, str] | None = None,
        notify_category: str | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> int:
        """Run *fn* in the background with busy/error handling and optional activity/notification records."""
        self._busy += 1
        self.busyChanged.emit()
        self._error = ""
        self.errorChanged.emit()

        def done(result: Any) -> None:
            self._busy -= 1
            self.busyChanged.emit()
            if record:
                activity.record(record[0], record[1], "ok")
            on_done(result)

        def failed(message: str, hint: str) -> None:
            self._busy -= 1
            self.busyChanged.emit()
            self.set_error(message, hint)
            self.toast.emit("error", message)
            if on_error:
                on_error(message, hint)
            if record:
                activity.record(record[0], record[1], "failed", message)
            if notify_category:
                notifications.notify(
                    f"{label or 'Operation'} failed",
                    message,
                    severity="error",
                    category=notify_category,
                    source="command-center",
                    dedupe_key=f"{notify_category}:{label}:{message[:60]}",
                )

        wrapped = (lambda emit, cancel: fn(emit, cancel)) if progress else fn
        return self.tasks.submit(wrapped, done, failed, progress)
