# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Creation and removal of platform launchers."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import TYPE_CHECKING

from fibsem_maestro_installer import icons, paths, resources
from fibsem_maestro_installer.errors import InstallError

if TYPE_CHECKING:
    from pathlib import Path

ICON_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256, 512)

_DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Version=2.0
Name={name}
Comment=Control software for FIB SEM microscopes
Exec={executable}
Icon={icon}
Terminal=false
Categories=Science;Education;
StartupWMClass={wm_class}
"""


def create_launchers(root: Path) -> list[Path]:
    """
    Create the launchers appropriate to the current platform.

    Args:
        root: Installation root.

    Returns:
        Every path created, for recording in the manifest.

    Raises:
        InstallError: If a launcher cannot be created.
    """
    if paths.is_windows():
        return _create_windows_launchers(root)

    return _create_linux_launchers(root)


def remove_launchers(recorded: list[Path]) -> None:
    """
    Delete launchers previously recorded in the manifest.

    Missing files are ignored so that uninstall is idempotent and survives a
    user having tidied up by hand.

    Args:
        recorded: Paths listed in the manifest.
    """
    for path in recorded:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue

    if not paths.is_windows():
        _refresh_linux_caches()


def _create_windows_launchers(root: Path) -> list[Path]:
    """
    Render the ICO and create a Start Menu shortcut.

    Args:
        root: Installation root.

    Returns:
        Paths created.

    Raises:
        InstallError: If the COM call fails.
    """
    icon = icons.build_ico(resources.icon_svg(), root / "app.ico")

    link = paths.start_menu_dir() / f"{paths.APP_NAME}.lnk"
    link.parent.mkdir(parents=True, exist_ok=True)
    target = paths.app_executable(root)

    try:
        from win32com.client import Dispatch  # type: ignore
    except ImportError as error:
        raise InstallError(
            "pywin32 is required to create the Start Menu shortcut."
        ) from error

    try:
        shortcut = Dispatch("WScript.Shell").CreateShortCut(str(link))
        shortcut.Targetpath = str(target)
        shortcut.WorkingDirectory = str(target.parent)
        shortcut.Description = paths.APP_NAME
        shortcut.IconLocation = str(icon)
        shortcut.save()
    except Exception as error:
        raise InstallError(f"Could not create the shortcut: {error}") from error

    return [link]


def _create_linux_launchers(root: Path) -> list[Path]:
    """
    Install icons into the hicolor theme and write a desktop entry.

    Args:
        root: Installation root.

    Returns:
        Paths created.
    """
    created = icons.install_linux_icons(resources.icon_svg())

    entry = paths.desktop_entry_dir() / f"{paths.DESKTOP_ID}.desktop"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(desktop_entry_text(root), encoding="utf-8")
    entry.chmod(0o755)
    created.append(entry)

    _refresh_linux_caches()
    return created


def _refresh_linux_caches() -> None:
    """Refresh the icon and desktop databases, ignoring absent tools."""
    commands = [
        ["gtk-update-icon-cache", "-f", "-t", str(paths.icon_theme_dir())],
        ["update-desktop-database", str(paths.desktop_entry_dir())],
    ]
    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        subprocess.run(command, capture_output=True, check=False)


def desktop_entry_text(root: Path) -> str:
    """
    Render the desktop entry without writing it.

    Args:
        root: Installation root.

    Returns:
        Contents of the `.desktop` file.
    """
    return _DESKTOP_ENTRY.format(
        name=paths.APP_NAME,
        executable=paths.app_executable(root),
        icon=paths.DESKTOP_ID,
        wm_class=paths.APP_SLUG,
    )


def sanitise_wm_class(value: str) -> str:
    """
    Normalise a WM_CLASS candidate.

    Args:
        value: Raw value, typically `argv[0]`.

    Returns:
        The value reduced to characters valid in a desktop entry key.
    """
    return re.sub(r"[^A-Za-z0-9._-]", "", value)
