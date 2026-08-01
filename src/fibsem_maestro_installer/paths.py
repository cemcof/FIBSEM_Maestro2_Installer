# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Filesystem locations used by the installer."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "FIBSEM Maestro"
APP_SLUG = "fibsem-maestro"
DESKTOP_ID = "cz.cemcof.FibsemMaestro"
DISTRIBUTION = "fibsem-maestro"
PYTHON_VERSION = "3.11"


def is_windows() -> bool:
    """
    Report whether the installer is running on Windows.

    Returns:
        True on Windows, False otherwise.
    """
    return sys.platform == "win32"


def default_install_root() -> Path:
    """
    Return the default per-user installation directory.

    Returns:
        Directory that will contain the whole installation.
    """
    if is_windows():
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / "FibsemMaestro"

    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / APP_SLUG


def uv_binary(root: Path) -> Path:
    """
    Return the path of the private uv executable.

    Args:
        root: Installation root.

    Returns:
        Path to `uv` inside the installation.
    """
    return root / "bin" / ("uv.exe" if is_windows() else "uv")


def python_install_dir(root: Path) -> Path:
    """
    Return the directory holding the managed Python interpreter.

    Args:
        root: Installation root.

    Returns:
        Directory passed to uv as `UV_PYTHON_INSTALL_DIR`.
    """
    return root / "python"


def cache_dir(root: Path) -> Path:
    """
    Return the private uv cache directory.

    Args:
        root: Installation root.

    Returns:
        Directory passed to uv as `UV_CACHE_DIR`.
    """
    return root / "cache"


def venv_dir(root: Path) -> Path:
    """
    Return the application's virtual environment directory.

    Args:
        root: Installation root.

    Returns:
        Path of the virtual environment.
    """
    return root / "runtime"


def venv_bin_dir(root: Path) -> Path:
    """
    Return the executable directory inside the virtual environment.

    Args:
        root: Installation root.

    Returns:
        `Scripts` on Windows, `bin` elsewhere.
    """
    return venv_dir(root) / ("Scripts" if is_windows() else "bin")


def venv_python(root: Path) -> Path:
    """
    Return the interpreter inside the virtual environment.

    Args:
        root: Installation root.

    Returns:
        Path of the virtual environment's Python executable.
    """
    return venv_bin_dir(root) / ("python.exe" if is_windows() else "python")


def app_executable(root: Path) -> Path:
    """
    Return the launcher generated from the application's gui-script.

    Args:
        root: Installation root.

    Returns:
        Path of the application entry point.
    """
    name = f"{APP_SLUG}.exe" if is_windows() else APP_SLUG
    return venv_bin_dir(root) / name


def config_file(root: Path) -> Path:
    """
    Return the application configuration file.

    Args:
        root: Installation root.

    Returns:
        Path of `config.toml`.
    """
    return root / "config.toml"


def manifest_file(root: Path) -> Path:
    """
    Return the install manifest.

    Args:
        root: Installation root.

    Returns:
        Path of `install.json`.
    """
    return root / "install.json"


def start_menu_dir() -> Path:
    """
    Return the per-user Start Menu programs directory.

    Returns:
        Directory in which to create the shortcut. Windows only.
    """
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def desktop_entry_dir() -> Path:
    """
    Return the per-user XDG applications directory.

    Returns:
        Directory in which to create the `.desktop` file. Linux only.
    """
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "applications"


def icon_theme_dir() -> Path:
    """
    Return the per-user hicolor icon theme directory.

    Returns:
        Root of the hicolor theme. Linux only.
    """
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "icons" / "hicolor"


def is_frozen() -> bool:
    """
    Report whether the installer is running as a frozen executable.

    Returns:
        True when running under PyInstaller.
    """
    return getattr(sys, "frozen", False)


def executable_dir() -> Path:
    """
    Return the directory containing the wizard executable.

    Returns:
        Directory of the running executable, or the project root when the
        installer is run from a source checkout.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def find_offline_bundle() -> Path | None:
    """
    Locate an offline bundle shipped next to the wizard.

    Returns:
        Path of a directory named `bundle` containing a `wheels`
        subdirectory, or None when no usable bundle is present.
    """
    candidate = executable_dir() / "bundle"
    if (candidate / "wheels").is_dir():
        return candidate
    return None
