# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Background execution of installer steps."""

from __future__ import annotations

import threading
from collections.abc import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from fibsem_maestro_installer.errors import InstallCancelled, InstallError
from fibsem_maestro_installer.progress import ProgressReporter

Task = Callable[[ProgressReporter, threading.Event], str]


class TaskWorker(QThread):
    """
    Runs one installer task and reports its outcome via signals.

    Attributes:
        progressed: Emitted with a message and an overall percentage.
        succeeded: Emitted with a closing message when the task completes.
        failed: Emitted with an error message when the task raises.
        cancelled: Emitted when the user aborts the task.
    """

    progressed = pyqtSignal(str, int)
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, task: Task) -> None:
        """
        Initialize the worker.

        Args:
            task: Callable receiving a reporter and a cancellation event.
        """
        super().__init__()
        self._task = task
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Request cancellation at the next checkpoint."""
        self._cancel.set()

    def run(self) -> None:
        """Execute the task and translate its outcome into signals."""
        try:
            message = self._task(self._report, self._cancel)
        except InstallCancelled:
            self.cancelled.emit()
        except InstallError as error:
            self.failed.emit(str(error))
        except Exception as error:  # noqa: BLE001 - last line of defence
            self.failed.emit(f"Unexpected error: {error}")
        else:
            self.succeeded.emit(message)

    def _report(self, message: str, percent: int) -> None:
        """
        Forward a progress update to the GUI thread.

        Args:
            message: Description of the current step.
            percent: Overall completion between 0 and 100.
        """
        self.progressed.emit(message, max(0, min(100, percent)))
