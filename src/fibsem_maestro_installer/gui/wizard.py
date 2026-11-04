# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""The wizard window."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from fibsem_maestro_installer import icons, installer, paths, resources
from fibsem_maestro_installer.config import read_links
from fibsem_maestro_installer.errors import InstallError
from fibsem_maestro_installer.gui.library_row import LibraryRow
from fibsem_maestro_installer.gui.worker import TaskWorker
from fibsem_maestro_installer.libraries import LIBRARIES, library

if TYPE_CHECKING:
    import threading
    from collections.abc import Mapping

    from fibsem_maestro_installer.libraries import LinkStatus
    from fibsem_maestro_installer.progress import ProgressReporter

PAGE_WELCOME = 0
PAGE_LOCATION = 1
PAGE_PROGRESS = 2
PAGE_LIBRARIES = 3
PAGE_FINISH = 4

ACTION_INSTALL = "install"
ACTION_UPDATE = "update"
ACTION_REPAIR = "repair"
ACTION_LIBRARIES = "libraries"
ACTION_UNINSTALL = "uninstall"

_MUTED_COLOR = "#8b949e"


def _library_name(key: str) -> str:
    """
    Return the display name of a library key.

    Args:
        key: Identifier of the library.

    Returns:
        The library's name, or the key for a library this installer does not know.
    """
    lib = library(key)
    return lib.name if lib is not None else key


def _links_summary(links: Mapping[str, object]) -> str:
    """
    Describe which libraries are linked, for the welcome and finish pages.

    Args:
        links: Linked libraries, by library key.

    Returns:
        A sentence listing them, or explaining that none is linked.
    """
    if not links:
        return (
            "No microscope library is linked; FIBSEM Maestro runs with the "
            "simulated microscope only."
        )
    return "Linked microscope libraries: " + ", ".join(
        _library_name(key) for key in sorted(links)
    )


class WelcomePage(QWizardPage):
    """Entry point offering either a fresh install or maintenance actions."""

    def __init__(self, wizard: InstallerWizard) -> None:
        """
        Initialize the page.

        Args:
            wizard: Owning wizard.
        """
        super().__init__()
        self._wizard = wizard
        self.setTitle(f"{paths.APP_NAME} Installer")

        layout = QVBoxLayout(self)
        self._intro = QLabel()
        self._intro.setWordWrap(True)
        layout.addWidget(self._intro)

        self.update_choice = QRadioButton("Update to the latest version")
        self.repair_choice = QRadioButton("Repair this installation")
        self.libraries_choice = QRadioButton("Manage microscope libraries")
        self.uninstall_choice = QRadioButton("Uninstall")

        for button in self._choices():
            layout.addWidget(button)
        layout.addStretch(1)

    def _choices(self) -> list[QRadioButton]:
        """
        Return the maintenance radio buttons.

        Returns:
            The four maintenance options.
        """
        return [
            self.update_choice,
            self.repair_choice,
            self.libraries_choice,
            self.uninstall_choice,
        ]

    def initializePage(self) -> None:
        """
        Adapt the page to whether an installation already exists.
        """
        existing = self._wizard.existing
        show = existing is not None

        for button in self._choices():
            button.setVisible(show)

        if existing is None:
            source = "an offline bundle" if self._wizard.bundle else "GitHub"
            self._intro.setText(
                f"This wizard will install {paths.APP_NAME} for the current "
                f"user from {source}.\n\n"
                "After the installation, you can link the microscope libraries "
                "installed on this computer, such as Thermo Fisher Autoscript. "
                "Linking is optional and can also be done later by running the "
                "installer again."
            )
            self._wizard.action = ACTION_INSTALL
        else:
            self._intro.setText(
                f"{paths.APP_NAME} {existing.app_version} is installed in\n"
                f"{existing.root}\n\n"
                f"{_links_summary(existing.libraries)}\n\n"
                "Choose what to do:"
            )
            self.update_choice.setChecked(True)

    def nextId(self) -> int:
        """
        Route to the page appropriate for the selected action.

        Returns:
            Identifier of the next page.
        """
        if self._wizard.existing is None:
            self._wizard.action = ACTION_INSTALL
            return PAGE_LOCATION

        if self.uninstall_choice.isChecked():
            self._wizard.action = ACTION_UNINSTALL
            return PAGE_PROGRESS
        if self.libraries_choice.isChecked():
            self._wizard.action = ACTION_LIBRARIES
            return PAGE_LIBRARIES
        if self.repair_choice.isChecked():
            self._wizard.action = ACTION_REPAIR
            return PAGE_PROGRESS

        self._wizard.action = ACTION_UPDATE
        return PAGE_PROGRESS


class LocationPage(QWizardPage):
    """Collects the installation directory."""

    def __init__(self, wizard: InstallerWizard) -> None:
        """
        Initialize the page.

        Args:
            wizard: Owning wizard.
        """
        super().__init__()
        self._wizard = wizard
        self.setTitle("Installation folder")
        self.setSubTitle(
            "Everything is installed under this folder, including a private "
            "Python interpreter. Administrator rights are not required."
        )

        layout = QVBoxLayout(self)
        self.path_edit = QLineEdit(str(paths.default_install_root()))
        button = QPushButton("Browse...")
        row = QHBoxLayout()
        row.addWidget(self.path_edit)
        row.addWidget(button)
        layout.addLayout(row)

        self._source = QLabel()
        self._source.setWordWrap(True)
        layout.addWidget(self._source)
        layout.addStretch(1)

        button.clicked.connect(self._choose_folder)
        self.path_edit.textChanged.connect(self.completeChanged)

    def _choose_folder(self) -> None:
        """Let the user pick the installation folder."""
        chosen = QFileDialog.getExistingDirectory(
            self, "Installation folder", self.path_edit.text()
        )
        if chosen:
            self.path_edit.setText(chosen)

    def initializePage(self) -> None:
        """Describe where the application will be fetched from."""
        if self._wizard.bundle is not None:
            self._source.setText(
                f"Offline bundle detected in {self._wizard.bundle}.\n"
                "No internet connection is required."
            )
        else:
            self._source.setText(
                f"The application will be downloaded from "
                f"{self._wizard.repository} on GitHub."
            )

    def isComplete(self) -> bool:
        """
        Report whether a plausible directory has been entered.

        Returns:
            True when the path is absolute.
        """
        text = self.path_edit.text().strip()
        return bool(text) and Path(text).is_absolute()

    def nextId(self) -> int:
        """
        Continue to the installation.

        Returns:
            Identifier of the next page.
        """
        return PAGE_PROGRESS


class ProgressPage(QWizardPage):
    """
    Runs the selected operation and shows its progress.

    A commit page: once the operation has run, the wizard cannot go back to it,
    which would run it again.
    """

    def __init__(self, wizard: InstallerWizard) -> None:
        """
        Initialize the page.

        Args:
            wizard: Owning wizard.
        """
        super().__init__()
        self._wizard = wizard
        self._worker: TaskWorker | None = None
        self._done = False
        self.setTitle("Working")
        self.setCommitPage(True)
        self.setButtonText(QWizard.WizardButton.CommitButton, "&Next >")

        layout = QVBoxLayout(self)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        layout.addWidget(self._bar)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        layout.addWidget(self._log)

    def initializePage(self) -> None:
        """Start the worker for the selected action."""
        self._done = False
        self._log.clear()
        self._bar.setValue(0)
        self.setSubTitle(f"Running: {self._wizard.action}")

        worker = TaskWorker(self._wizard.build_task())
        worker.progressed.connect(self._on_progress)
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        worker.cancelled.connect(self._on_cancelled)
        self._worker = worker
        worker.start()

    def cancel_worker(self) -> None:
        """Ask a running worker to stop and wait briefly for it."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(10_000)

    def _on_progress(self, message: str, percent: int) -> None:
        """
        Show a progress update.

        Args:
            message: Description of the current step.
            percent: Overall completion.
        """
        self._bar.setValue(percent)
        if self._log.toPlainText().endswith(message):
            return
        self._log.appendPlainText(message)

    def _on_success(self, message: str) -> None:
        """
        Advance the wizard once the operation completes.

        Args:
            message: Closing message for the summary page.
        """
        self._done = True
        self._wizard.summary = message
        self._bar.setValue(100)
        self.completeChanged.emit()
        self._wizard.next()

    def _on_failure(self, message: str) -> None:
        """
        Report a failure without leaving the page.

        Args:
            message: Error text.
        """
        self._log.appendPlainText("\nFAILED\n" + message)
        QMessageBox.critical(self, "Installation failed", message)

    def _on_cancelled(self) -> None:
        """Report that the user aborted the operation."""
        self._log.appendPlainText("\nCancelled.")

    def isComplete(self) -> bool:
        """
        Report whether the operation finished successfully.

        Returns:
            True once the worker has succeeded.
        """
        return self._done

    def nextId(self) -> int:
        """
        Continue to the libraries after a fresh install or when a link broke.

        Returns:
            Identifier of the next page.
        """
        action = self._wizard.action
        if action == ACTION_INSTALL or (
            action in {ACTION_UPDATE, ACTION_REPAIR} and self._wizard.link_problems
        ):
            return PAGE_LIBRARIES
        return PAGE_FINISH


class LibrariesPage(QWizardPage):
    """Links the manufacturer libraries; every one of them is optional."""

    def __init__(self, wizard: InstallerWizard) -> None:
        """
        Initialize the page.

        Args:
            wizard: Owning wizard.
        """
        super().__init__()
        self._wizard = wizard
        self.setTitle("Microscope libraries (optional)")

        layout = QVBoxLayout(self)
        self.rows = [LibraryRow(lib) for lib in LIBRARIES]
        for row in self.rows:
            layout.addWidget(row)
            row.changed.connect(self.completeChanged)

        note = QLabel(
            f"<span style='color:{_MUTED_COLOR}'>Without a linked library, "
            f"{paths.APP_NAME} runs with the simulated microscope only.</span>"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

    def initializePage(self) -> None:
        """Show the current links of the installation and check them."""
        if self._wizard.link_problems:
            self.setSubTitle(
                "The update finished, but a linked library does not work with "
                "the new version. Select the correct folder or unlink it."
            )
        else:
            self.setSubTitle(
                f"{paths.APP_NAME} controls a microscope through its "
                "manufacturer's library. Link the libraries installed on this "
                "computer, or leave them empty and link them later by running "
                "the installer again."
            )

        root = self._wizard.install_root
        links = read_links(paths.config_file(root))
        for row in self.rows:
            row.set_python(paths.venv_python(root))
            row.set_folder(links.get(row.library.key))

    def isComplete(self) -> bool:
        """
        Report whether every library is either unlinked or works.

        Returns:
            True when no link is being checked or broken.
        """
        return all(row.acceptable for row in self.rows)

    def validatePage(self) -> bool:
        """
        Save the links.

        Links to libraries this installer does not know (written by a newer
        installer) are kept.

        Returns:
            True if the links were saved.
        """
        root = self._wizard.install_root
        known = {row.library.key for row in self.rows}
        links = {
            key: folder
            for key, folder in read_links(paths.config_file(root)).items()
            if key not in known
        }
        links |= {
            row.library.key: folder
            for row in self.rows
            if (folder := row.folder) is not None
        }

        try:
            installer.set_links(root, links)
        except OSError as error:
            QMessageBox.critical(self, "Could not save the links", str(error))
            return False

        self._wizard.link_problems = {}
        if self._wizard.action == ACTION_LIBRARIES:
            self._wizard.summary = "The microscope libraries were updated."
        return True

    def shutdown(self) -> None:
        """Wait for running link checks before the wizard closes."""
        for row in self.rows:
            row.shutdown()

    def nextId(self) -> int:
        """
        Continue to the summary page.

        Returns:
            Identifier of the next page.
        """
        return PAGE_FINISH


class FinishPage(QWizardPage):
    """Summarises the outcome."""

    def __init__(self, wizard: InstallerWizard) -> None:
        """
        Initialise the page.

        Args:
            wizard: Owning wizard.
        """
        super().__init__()
        self._wizard = wizard
        self.setTitle("Done")

        layout = QVBoxLayout(self)
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._summary)

        self.launch_check = QCheckBox(f"Start {paths.APP_NAME} now")
        layout.addWidget(self.launch_check)
        layout.addStretch(1)

    def initializePage(self) -> None:
        """Show the summary produced by the operation, and the linked libraries."""
        launchable = self._wizard.action != ACTION_UNINSTALL
        parts = [self._wizard.summary]
        if launchable:
            links = read_links(paths.config_file(self._wizard.install_root))
            parts.append(_links_summary(links))
        self._summary.setText("\n\n".join(part for part in parts if part))
        self.launch_check.setVisible(launchable)
        self.launch_check.setChecked(False)

    def nextId(self) -> int:
        """
        Mark this as the final page.

        Returns:
            `-1`.
        """
        return -1


class InstallerWizard(QWizard):
    """Top-level wizard window holding the collected state."""

    def __init__(
        self,
        repository: str,
        bundle: Path | None,
        token: str | None = None,
    ) -> None:
        """
        Initialize the wizard.

        Args:
            repository: GitHub repository in `owner/name` form.
            bundle: Offline bundle directory, or None.
            token: GitHub token for private repositories, or None.
        """
        super().__init__()
        self.repository = repository
        self.bundle = bundle
        self.token = token
        self.action = ACTION_INSTALL
        self.summary = ""
        self.link_problems: dict[str, LinkStatus] = {}
        self.existing = installer.existing_installation(paths.default_install_root())

        self.setWindowTitle(f"{paths.APP_NAME} Installer")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.resize(680, 500)

        self.setWindowIcon(icons.load_window_icon(resources.icon_svg()))

        self.welcome_page = WelcomePage(self)
        self.location_page = LocationPage(self)
        self.progress_page = ProgressPage(self)
        self.libraries_page = LibrariesPage(self)
        self.finish_page = FinishPage(self)

        self.setPage(PAGE_WELCOME, self.welcome_page)
        self.setPage(PAGE_LOCATION, self.location_page)
        self.setPage(PAGE_PROGRESS, self.progress_page)
        self.setPage(PAGE_LIBRARIES, self.libraries_page)
        self.setPage(PAGE_FINISH, self.finish_page)

    @property
    def install_root(self) -> Path:
        """
        Return the chosen installation root.

        Returns:
            Root of an existing installation when maintaining one, otherwise
            the directory entered on the location page.
        """
        if self.existing is not None and self.action != ACTION_INSTALL:
            return Path(self.existing.root)
        return Path(self.location_page.path_edit.text().strip())

    def build_plan(self) -> installer.InstallPlan:
        """
        Assemble an install plan from the collected state.

        Returns:
            The plan to hand to the core installer.
        """
        return installer.InstallPlan(
            root=self.install_root,
            repository=self.repository,
            bundle=self.bundle,
            token=self.token,
        )

    def build_task(self):
        """
        Return the callable implementing the selected action.

        Returns:
            A task suitable for `TaskWorker`.
        """
        if self.action == ACTION_UNINSTALL:
            manifest = self.existing

            def uninstall_task(
                report: ProgressReporter, _cancel: threading.Event
            ) -> str:
                assert manifest is not None
                installer.uninstall(manifest, report)
                return f"{paths.APP_NAME} has been removed."

            return uninstall_task

        plan = self.build_plan()
        reinstall = self.action in {ACTION_UPDATE, ACTION_REPAIR}

        def install_task(report: ProgressReporter, cancel: threading.Event) -> str:
            result = installer.install(plan, report, cancel, reinstall)
            # read in the GUI thread after `succeeded`, which is emitted later
            self.link_problems = result.link_problems
            return (
                f"{paths.APP_NAME} {result.manifest.app_version} was installed in\n"
                f"{result.manifest.root}"
            )

        return install_task

    def launch_application(self) -> None:
        """
        Start the installed application if the user asked for it.

        Raises:
            InstallError: If the executable is missing.
        """
        import subprocess

        executable = paths.app_executable(self.install_root)
        if not executable.is_file():
            raise InstallError(f"{executable} was not found.")
        subprocess.Popen([str(executable)], close_fds=True)

    def reject(self) -> None:
        """Cancel running work before closing."""
        self.progress_page.cancel_worker()
        self.libraries_page.shutdown()
        super().reject()

    def accept(self) -> None:
        """Optionally start the application when finishing."""
        self.libraries_page.shutdown()
        if self.finish_page.launch_check.isChecked():
            try:
                self.launch_application()
            except (InstallError, OSError) as error:
                QMessageBox.warning(self, "Could not start", str(error))
        super().accept()
