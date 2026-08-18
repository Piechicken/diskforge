"""Qt worker helpers for long-running, cancellable core operations."""
from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from diskforge.core.models import Progress
from diskforge.core.storage import CancellationToken


class WorkerSignals(QObject):
    started = Signal(str)
    progress = Signal(object)
    result = Signal(object)
    error = Signal(str, str)
    finished = Signal()


class FunctionWorker(QRunnable):
    """Run a callable on the global QThreadPool and forward core progress events."""

    def __init__(self, title: str, function: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.title = title
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.token = CancellationToken()

    def cancel(self) -> None:
        self.token.cancel()

    def run(self) -> None:
        self.signals.started.emit(self.title)
        try:
            if "progress" not in self.kwargs:
                self.kwargs["progress"] = self.signals.progress.emit
            if "token" not in self.kwargs:
                self.kwargs["token"] = self.token
            value = self.function(*self.args, **self.kwargs)
            self.signals.result.emit(value)
        except Exception as exc:
            self.signals.error.emit(str(exc), traceback.format_exc())
        finally:
            self.signals.finished.emit()
