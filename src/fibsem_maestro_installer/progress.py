# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Progress reporting shared by the core installer and the GUI."""

from __future__ import annotations

import threading
from typing import Protocol

from fibsem_maestro_installer.errors import InstallCancelled


class ProgressReporter(Protocol):
    """Receives progress updates from long-running installer steps."""

    def __call__(self, message: str, percent: int) -> None:
        """
        Report progress.

        Args:
            message: Human-readable description of the current step.
            percent: Overall completion between 0 and 100.
        """


def null_reporter(message: str, percent: int) -> None:
    """
    Discard progress updates.

    Args:
        message: Ignored.
        percent: Ignored.
    """


def check_cancelled(cancel: threading.Event | None) -> None:
    """
    Abort the current operation if cancellation was requested.

    Args:
        cancel: Event set by the GUI when the user presses Cancel.

    Raises:
        InstallCancelled: If the event is set.
    """
    if cancel is not None and cancel.is_set():
        raise InstallCancelled("Installation cancelled by the user")
