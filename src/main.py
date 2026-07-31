# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Entry point for the installation wizard."""

from __future__ import annotations

import ctypes
import os
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from fibsem_maestro_installer import paths, resources

DEFAULT_REPOSITORY = "Ladme/FIBSEM_Maestro"


def main() -> int:
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "CEMCOF.FibsemMaestro.Installer"
        )

    from fibsem_maestro_installer.gui.wizard import InstallerWizard

    app = QApplication(sys.argv)
    app.setApplicationName(f"{paths.APP_NAME} setup")
    app.setDesktopFileName(f"{paths.DESKTOP_ID}.Installer")

    assets = resources.asset_dir()
    icon = assets / "app.ico"
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))

    wizard = InstallerWizard(
        repository=os.environ.get("FIBSEM_MAESTRO_REPO", DEFAULT_REPOSITORY),
        assets=assets,
        bundle=resources.find_offline_bundle(),
        token=os.environ.get("GITHUB_TOKEN") or None,
    )
    wizard.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
