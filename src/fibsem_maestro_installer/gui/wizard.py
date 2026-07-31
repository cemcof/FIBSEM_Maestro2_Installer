# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""The wizard window."""

from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
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

from fibsem_maestro_installer import installer, paths
from fibsem_maestro_installer.autoscript import (
    looks_like_autoscript,
    validate_import,
)
from fibsem_maestro_installer.config import write_config
from fibsem_maestro_installer.errors import InstallError
from fibsem_maestro_installer.gui.worker import TaskWorker
from fibsem_maestro_installer.progress import ProgressReporter

PAGE_WELCOME = 0
PAGE_LOCATION = 1
PAGE_AUTOSCRIPT = 2
PAGE_PROGRESS = 3
PAGE_FINISH = 4

ACTION_INSTALL = "install"
ACTION_UPDATE = "update"
ACTION_REPAIR = "repair"
ACTION_RELINK = "relink"
ACTION_UNINSTALL = "uninstall"


def _browse_row(edit: QLineEdit, caption: str) -> QHBoxLayout:
    """
    Build a line edit paired with a directory browse button.

    Args:
        edit: The line edit to populate.
        caption: Title of the directory dialog.

    Returns:
        Layout containing both widgets.
    """
    button = QPushButton("Browse...")
    layout = QHBoxLayout()
    layout.addWidget(edit)
    layout.addWidget(button)

    def choose() -> None:
        chosen = QFileDialog.getExistingDirectory(edit, caption, edit.text())
        if chosen:
            edit.setText(chosen)

    button.clicked.connect(choose)
    return layout


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
        self.relink_choice = QRadioButton("Change the Autoscript location")
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
            self.relink_choice,
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
                "You will be asked for the location of your Autoscript "
                "installation, which is required to control the microscope "
                "and is not distributed with this software."
            )
            self._wizard.action = ACTION_INSTALL
        else:
            self._intro.setText(
                f"{paths.APP_NAME} {existing.app_version} is already "
                f"installed in\n{existing.root}\n\nChoose what to do:"
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
        if self.relink_choice.isChecked():
            self._wizard.action = ACTION_RELINK
            return PAGE_AUTOSCRIPT
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
        layout.addLayout(_browse_row(self.path_edit, "Installation folder"))

        self._source = QLabel()
        self._source.setWordWrap(True)
        layout.addWidget(self._source)
        layout.addStretch(1)

        self.path_edit.textChanged.connect(self.completeChanged)

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
        Continue to the Autoscript page.

        Returns:
            Identifier of the next page.
        """
        return PAGE_AUTOSCRIPT


class AutoscriptPage(QWizardPage):
    """Collects and pre-checks the Autoscript location."""

    def __init__(self, wizard: InstallerWizard) -> None:
        """
        Initialize the page.

        Args:
            wizard: Owning wizard.
        """
        super().__init__()
        self._wizard = wizard
        self.setTitle("Autoscript location")
        self.setSubTitle("Select the folder of your existing Autoscript installation.")

        layout = QVBoxLayout(self)
        self.path_edit = QLineEdit()
        layout.addLayout(_browse_row(self.path_edit, "Autoscript folder"))

        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self.path_edit.textChanged.connect(self._revalidate)

    def initializePage(self) -> None:
        """Prefill from an existing installation when repointing."""
        existing = self._wizard.existing
        if existing is not None and not self.path_edit.text():
            self.path_edit.setText(existing.autoscript_path)
        self._revalidate()

    def _revalidate(self) -> None:
        """Update the inline status message and the Next button."""
        text = self.path_edit.text().strip()
        if not text:
            self._status.setText("")
        elif looks_like_autoscript(Path(text)):
            self._status.setText("Autoscript client package found.")
        else:
            self._status.setText(
                "This folder does not contain "
                "'autoscript_sdb_microscope_client'. It is usually inside "
                "the Autoscript installation directory."
            )
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        """
        Report whether the selected folder looks like Autoscript.

        Returns:
            True when the client package is present.
        """
        text = self.path_edit.text().strip()
        return bool(text) and looks_like_autoscript(Path(text))

    def nextId(self) -> int:
        """
        Continue to the progress page.

        Returns:
            Identifier of the next page.
        """
        return PAGE_PROGRESS


class ProgressPage(QWizardPage):
    """Runs the selected operation and shows its progress."""

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
        """Show the summary produced by the worker."""
        self._summary.setText(self._wizard.summary)
        launchable = self._wizard.action != ACTION_UNINSTALL
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
        assets: Path,
        bundle: Path | None,
        token: str | None = None,
    ) -> None:
        """
        Initialize the wizard.

        Args:
            repository: GitHub repository in `owner/name` form.
            assets: Directory containing bundled icons.
            bundle: Offline bundle directory, or None.
            token: GitHub token for private repositories, or None.
        """
        super().__init__()
        self.repository = repository
        self.assets = assets
        self.bundle = bundle
        self.token = token
        self.action = ACTION_INSTALL
        self.summary = ""
        self.existing = installer.existing_installation(paths.default_install_root())

        self.setWindowTitle(f"{paths.APP_NAME} Installer")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.resize(620, 460)

        icon = assets / "icon.svg"
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))

        self.welcome_page = WelcomePage(self)
        self.location_page = LocationPage(self)
        self.autoscript_page = AutoscriptPage(self)
        self.progress_page = ProgressPage(self)
        self.finish_page = FinishPage(self)

        self.setPage(PAGE_WELCOME, self.welcome_page)
        self.setPage(PAGE_LOCATION, self.location_page)
        self.setPage(PAGE_AUTOSCRIPT, self.autoscript_page)
        self.setPage(PAGE_PROGRESS, self.progress_page)
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

    @property
    def autoscript_path(self) -> Path:
        """
        Return the chosen Autoscript directory.

        Returns:
            The entered path, falling back to the existing installation's.
        """
        text = self.autoscript_page.path_edit.text().strip()
        if text:
            return Path(text)
        if self.existing is not None:
            return Path(self.existing.autoscript_path)
        return Path()

    def build_plan(self) -> installer.InstallPlan:
        """
        Assemble an install plan from the collected state.

        Returns:
            The plan to hand to the core installer.
        """
        return installer.InstallPlan(
            root=self.install_root,
            autoscript_path=self.autoscript_path,
            assets=self.assets,
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
        action = self.action

        if action == ACTION_UNINSTALL:
            manifest = self.existing

            def uninstall_task(
                report: ProgressReporter, cancel: threading.Event
            ) -> str:
                assert manifest is not None
                installer.uninstall(manifest, report)
                return f"{paths.APP_NAME} has been removed."

            return uninstall_task

        if action == ACTION_RELINK:
            root = self.install_root
            autoscript = self.autoscript_path

            def relink_task(report: ProgressReporter, cancel: threading.Event) -> str:
                report("Verifying the Autoscript installation", 30)
                validate_import(paths.venv_python(root), autoscript)
                report("Writing configuration", 70)
                write_config(paths.config_file(root), autoscript)
                manifest = installer.existing_installation(root)
                if manifest is not None:
                    manifest.autoscript_path = str(autoscript)
                    manifest.save(paths.manifest_file(root))
                report("Done", 100)
                return f"Autoscript is now linked from\n{autoscript}"

            return relink_task

        plan = self.build_plan()
        reinstall = action in {ACTION_UPDATE, ACTION_REPAIR}

        def install_task(report: ProgressReporter, cancel: threading.Event) -> str:
            manifest = installer.install(plan, report, cancel, reinstall)
            return (
                f"{paths.APP_NAME} {manifest.app_version} was installed in\n"
                f"{manifest.root}"
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
        """Cancel a running operation before closing."""
        self.progress_page.cancel_worker()
        super().reject()

    def accept(self) -> None:
        """Optionally start the application when finishing."""
        if self.finish_page.launch_check.isChecked():
            try:
                self.launch_application()
            except (InstallError, OSError) as error:
                QMessageBox.warning(self, "Could not start", str(error))
        super().accept()
