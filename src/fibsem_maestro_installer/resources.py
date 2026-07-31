# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Location of assets and of an optional offline bundle."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """
    Report whether the installer is running as a frozen executable.

    Returns:
        True when running under PyInstaller.
    """
    return getattr(sys, "frozen", False)


def asset_dir() -> Path:
    """
    Return the directory containing the icon.

    Returns:
        Directory holding ``icon.svg``.
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS")) / "assets"
    return Path(__file__).resolve().parents[2] / "assets"


def executable_dir() -> Path:
    """
    Return the directory containing the wizard executable.

    Returns:
        Directory of the running executable, or of the source tree when not
        frozen.
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
