# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Creation and removal of platform launchers."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from fibsem_maestro_installer import paths
from fibsem_maestro_installer.errors import InstallError

ICON_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256, 512)

_DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Version=2.0.0
Name={name}
Comment=Control software for FIB SEM microscopes
Exec={executable}
Icon={icon}
Terminal=false
Categories=Science;Education;
StartupWMClass={wm_class}
"""


def create_launchers(root: Path, assets: Path) -> list[Path]:
    """
    Create the launchers appropriate to the current platform.

    Args:
        root: Installation root.
        assets: Directory containing the bundled icon files.

    Returns:
        Every path created, for recording in the manifest.

    Raises:
        InstallError: If a launcher cannot be created.
    """
    if paths.is_windows():
        return _create_windows_launchers(root, assets)
    return _create_linux_launchers(root, assets)


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


def _create_windows_launchers(root: Path, assets: Path) -> list[Path]:
    """
    Create a Start Menu shortcut.

    Args:
        root: Installation root.
        assets: Directory containing `favicon.ico`.

    Returns:
        Paths created.

    Raises:
        InstallError: If the COM call fails.
    """
    icon = root / "favicon.ico"
    source_icon = assets / "favicon.ico"
    if source_icon.is_file():
        shutil.copy2(source_icon, icon)

    link = paths.start_menu_dir() / f"{paths.APP_NAME}.lnk"
    link.parent.mkdir(parents=True, exist_ok=True)
    target = paths.app_executable(root)

    try:
        from win32com.client import Dispatch
    except ImportError as error:
        raise InstallError(
            "pywin32 is required to create the Start Menu shortcut."
        ) from error

    try:
        shortcut = Dispatch("WScript.Shell").CreateShortCut(str(link))
        shortcut.Targetpath = str(target)
        shortcut.WorkingDirectory = str(target.parent)
        shortcut.Description = paths.APP_NAME
        if icon.is_file():
            shortcut.IconLocation = str(icon)
        shortcut.save()
    except Exception as error:
        raise InstallError(f"Could not create the shortcut: {error}") from error

    return [link]


def _create_linux_launchers(root: Path, assets: Path) -> list[Path]:
    """
    Install icons into the hicolor theme and write a desktop entry.

    Args:
        root: Installation root.
        assets: Directory containing the PNG ladder and ``app.svg``.

    Returns:
        Paths created.
    """
    created = install_linux_icons(assets)

    entry = paths.desktop_entry_dir() / f"{paths.DESKTOP_ID}.desktop"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        _DESKTOP_ENTRY.format(
            name=paths.APP_NAME,
            executable=paths.app_executable(root),
            icon=paths.DESKTOP_ID,
            wm_class=paths.APP_SLUG,
        ),
        encoding="utf-8",
    )
    entry.chmod(0o755)
    created.append(entry)

    _refresh_linux_caches()
    return created


def install_linux_icons(assets: Path) -> list[Path]:
    """Copy the icon ladder into the per-user hicolor theme.

    Args:
        assets: Directory containing ``app_<size>.png`` and ``app.svg``.

    Returns:
        Paths of the installed icon files.
    """
    theme = paths.icon_theme_dir()
    created: list[Path] = []

    for size in ICON_SIZES:
        source = assets / f"app_{size}.png"
        if not source.is_file():
            continue
        target = theme / f"{size}x{size}" / "apps" / f"{paths.DESKTOP_ID}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        created.append(target)

    scalable = assets / "app.svg"
    if scalable.is_file():
        target = theme / "scalable" / "apps" / f"{paths.DESKTOP_ID}.svg"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(scalable, target)
        created.append(target)

    return created


def _refresh_linux_caches() -> None:
    """Refresh the icon and desktop databases, ignoring absent tools.

    Both commands are advisory: the desktop environment will pick the
    changes up on next login regardless, so a missing binary is not an error.
    """
    commands = [
        ["gtk-update-icon-cache", "-f", "-t", str(paths.icon_theme_dir())],
        ["update-desktop-database", str(paths.desktop_entry_dir())],
    ]
    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        subprocess.run(command, capture_output=True, check=False)


def desktop_entry_text(root: Path) -> str:
    """Render the desktop entry without writing it.

    Exposed for testing and for showing the user what will be installed.

    Args:
        root: Installation root.

    Returns:
        Contents of the ``.desktop`` file.
    """
    return _DESKTOP_ENTRY.format(
        name=paths.APP_NAME,
        executable=paths.app_executable(root),
        icon=paths.DESKTOP_ID,
        wm_class=paths.APP_SLUG,
    )


def sanitise_wm_class(value: str) -> str:
    """Normalise a WM_CLASS candidate.

    Args:
        value: Raw value, typically ``argv[0]``.

    Returns:
        The value reduced to characters valid in a desktop entry key.
    """
    return re.sub(r"[^A-Za-z0-9._-]", "", value)
