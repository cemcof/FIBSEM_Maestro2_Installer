# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Entry point for the installation wizard."""

from __future__ import annotations

import ctypes
import os
import sys

import qdarkstyle
from PyQt6.QtWidgets import QApplication

from fibsem_maestro_installer import icons, paths, resources
from fibsem_maestro_installer.gui.wizard import InstallerWizard

DEFAULT_REPOSITORY = "Ladme/FIBSEM_Maestro"


def main() -> int:
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "CEMCOF.FibsemMaestro.Installer"
        )

    app = QApplication(sys.argv)
    app.setApplicationName(f"{paths.APP_NAME} Installer")
    app.setDesktopFileName(f"{paths.DESKTOP_ID}.Installer")

    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyqt6"))

    app.setWindowIcon(icons.load_window_icon(resources.icon_svg()))

    wizard = InstallerWizard(
        repository=os.environ.get("FIBSEM_MAESTRO_REPO", DEFAULT_REPOSITORY),
        bundle=paths.find_offline_bundle(),
        token=os.environ.get("GITHUB_TOKEN") or None,
    )
    wizard.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
