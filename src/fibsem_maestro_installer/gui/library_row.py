# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""One manufacturer library on the libraries page: its folder and a live link check."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from fibsem_maestro_installer.libraries import LinkStatus, check_link

if TYPE_CHECKING:
    from fibsem_maestro_installer.libraries import Library

CHECK_DELAY_MS = 400
"""Pause after the last keystroke before the folder is checked."""

_OK_COLOR = "#3fb950"
_ERROR_COLOR = "#f85149"
_MUTED_COLOR = "#8b949e"


class LinkState(Enum):
    """Where the link of a row stands."""

    UNLINKED = "unlinked"
    CHECKING = "checking"
    LINKED = "linked"
    BROKEN = "broken"


class _CheckWorker(QThread):
    """Checks one folder off the GUI thread, since the check starts an interpreter."""

    checked = pyqtSignal(int, object)

    def __init__(
        self, generation: int, python: Path, library: Library, folder: Path
    ) -> None:
        """
        Initialize the worker.

        Args:
            generation: Number of the request, to recognise stale results.
            python: Interpreter of the application's environment.
            library: The library to check.
            folder: The folder to check.
        """
        super().__init__()
        self._generation = generation
        self._python = python
        self._library = library
        self._folder = folder

    def run(self) -> None:
        """Run the check and report its status."""
        status = check_link(self._python, self._library, self._folder)
        self.checked.emit(self._generation, status)


class LibraryRow(QFrame):
    """
    A library's folder with Browse and Unlink, checked as it is edited.

    Attributes:
        changed: Emitted whenever the state of the row changes.
    """

    changed = pyqtSignal()

    def __init__(self, library: Library) -> None:
        """
        Initialize the row.

        Args:
            library: The library this row links.
        """
        super().__init__()
        self.library = library
        self._python: Path | None = None
        self._state = LinkState.UNLINKED
        self._generation = 0
        self._workers: list[_CheckWorker] = []
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self._title = QLabel(
            f"<b>{library.name}</b>&nbsp;&nbsp;"
            f"<span style='color:{_MUTED_COLOR}'>{library.vendor}</span>"
        )
        self._status = QLabel()
        self._status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Not linked; leave empty to skip")
        self._browse = QPushButton("Browse...")
        self._unlink = QPushButton("Unlink")

        self._details = QLabel()
        self._details.setWordWrap(True)
        self._details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._details.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        self._details.setVisible(False)

        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit)
        path_row.addWidget(self._browse)
        path_row.addWidget(self._unlink)

        layout = QGridLayout(self)
        layout.addWidget(self._title, 0, 0)
        layout.addWidget(self._status, 0, 1)
        layout.addLayout(path_row, 1, 0, 1, 2)
        layout.addWidget(self._details, 2, 0, 1, 2)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(CHECK_DELAY_MS)
        self._timer.timeout.connect(self._start_check)

        self.path_edit.textChanged.connect(self._on_text_changed)
        self._browse.clicked.connect(self._choose_folder)
        self._unlink.clicked.connect(self.path_edit.clear)
        self._show_state(LinkState.UNLINKED)

    @property
    def state(self) -> LinkState:
        """Where the link of this row stands."""
        return self._state

    @property
    def folder(self) -> Path | None:
        """The entered folder, or None if the library is to be unlinked."""
        text = self.path_edit.text().strip()
        return Path(text) if text else None

    @property
    def acceptable(self) -> bool:
        """True if the row can be saved: unlinked, or linked and working."""
        return self._state in (LinkState.UNLINKED, LinkState.LINKED)

    def set_python(self, python: Path) -> None:
        """
        Set the interpreter the link is checked with.

        Args:
            python: Interpreter of the application's environment.
        """
        self._python = python

    def set_folder(self, folder: Path | None) -> None:
        """
        Show a folder and check it right away.

        Args:
            folder: The linked folder, or None for none.
        """
        self.path_edit.setText("" if folder is None else str(folder))
        # show the start of a long path: where it is, rather than its last folder
        self.path_edit.setCursorPosition(0)
        if self._timer.isActive():
            self._timer.stop()
            self._start_check()

    def shutdown(self) -> None:
        """Wait for running checks; call before the row is destroyed."""
        self._timer.stop()
        for worker in list(self._workers):
            worker.wait()

    def _choose_folder(self) -> None:
        """Let the user pick the folder."""
        chosen = QFileDialog.getExistingDirectory(
            self, f"{self.library.name} folder", self.path_edit.text()
        )
        if chosen:
            self.path_edit.setText(chosen)

    def _on_text_changed(self) -> None:
        """Check the folder once the user stops typing."""
        self._generation += 1
        self._unlink.setEnabled(self.folder is not None)
        if self.folder is None:
            self._timer.stop()
            self._show_state(LinkState.UNLINKED)
            return
        self._show_state(LinkState.CHECKING)
        self._timer.start()

    def _start_check(self) -> None:
        """Check the current folder in a worker thread."""
        folder = self.folder
        if folder is None:
            return
        if self._python is None:
            self._show_state(
                LinkState.BROKEN,
                LinkStatus(ok=False, error="The application is not installed."),
            )
            return

        worker = _CheckWorker(self._generation, self._python, self.library, folder)
        worker.checked.connect(self._on_checked)
        worker.finished.connect(lambda: self._workers.remove(worker))
        self._workers.append(worker)
        worker.start()

    def _on_checked(self, generation: int, status: LinkStatus) -> None:
        """
        Show the result of a check, unless the folder changed since it started.

        Args:
            generation: Number of the request the result belongs to.
            status: The result.
        """
        if generation != self._generation:
            return
        self._show_state(LinkState.LINKED if status.ok else LinkState.BROKEN, status)

    def _show_state(self, state: LinkState, status: LinkStatus | None = None) -> None:
        """
        Display a state.

        Args:
            state: The new state.
            status: The check result, for linked and broken links.
        """
        self._state = state
        self._details.setVisible(state is LinkState.BROKEN)

        match state:
            case LinkState.UNLINKED:
                text, color = "○ Not linked", _MUTED_COLOR
            case LinkState.CHECKING:
                text, color = "Checking…", _MUTED_COLOR
            case LinkState.LINKED:
                version = status.version if status is not None else None
                text = f"✔ Linked ({version})" if version else "✔ Linked"
                color = _OK_COLOR
            case LinkState.BROKEN:
                text, color = "✘ Does not work", _ERROR_COLOR
                self._details.setText(status.error if status is not None else "")

        self._status.setText(f"<span style='color:{color}'>{text}</span>")
        self.changed.emit()
