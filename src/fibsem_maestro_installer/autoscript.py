# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Validation of the user-supplied Autoscript installation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fibsem_maestro_installer import paths
from fibsem_maestro_installer.errors import AutoscriptError

CLIENT_PACKAGE = "autoscript_sdb_microscope_client"

_IMPORT_CHECK = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from autoscript_sdb_microscope_client.sdb_microscope_client import "
    "SdbMicroscopeClient\n"
    "print('ok')\n"
)


def looks_like_autoscript(path: Path) -> bool:
    """
    Quickly check whether a directory resembles an Autoscript install.

    Used for live feedback in the wizard, before an interpreter exists to
    perform a real import.

    Args:
        path: Candidate directory.

    Returns:
        True if the client package is present.
    """
    return (path / CLIENT_PACKAGE).is_dir()


def validate_import(python: Path, autoscript_path: Path) -> None:
    """
    Verify that Autoscript imports in the target environment.

    The check runs in the freshly created virtual environment rather than in
    the wizard's own frozen interpreter, which has an unrelated `sys.path`.

    Args:
        python: Interpreter of the application's virtual environment.
        autoscript_path: Directory the user selected.

    Raises:
        AutoscriptError: If the import fails.
    """
    completed = subprocess.run(
        [str(python), "-c", _IMPORT_CHECK, str(autoscript_path)],
        capture_output=True,
        text=True,
        creationflags=(
            getattr(subprocess, "CREATE_NO_WINDOW", 0) if paths.is_windows() else 0
        ),
        check=False,
    )

    if completed.returncode != 0:
        raise AutoscriptError(
            "Autoscript could not be imported from\n"
            f"    {autoscript_path}\n\n"
            "Check that this is the directory containing "
            f"'{CLIENT_PACKAGE}'.\n\n"
            f"{completed.stderr.strip()}"
        )
