# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""
Manufacturer libraries FIBSEM Maestro can use, and checks of their links.

None of them is required: FIBSEM Maestro runs without any (with the simulated
microscope), and each library the user has installed can be linked, changed or
unlinked at any time by running the installer again.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fibsem_maestro_installer import paths

if TYPE_CHECKING:
    from pathlib import Path

CHECK_TIMEOUT_S = 120
"""Longest a link check may take; importing a vendor library can be slow."""


@dataclass(frozen=True)
class Library:
    """
    A manufacturer library the application can be linked to.

    Attributes:
        key: Identifier used in `config.toml` (`[libraries.<key>]`) and in the
            install manifest. Must match what the application reads.
        name: Product name shown to the user.
        vendor: Manufacturer shown to the user.
        package: Package directory that must be inside the linked folder.
        check_import: Module imported to verify that the link works.
        distribution: Distribution whose version is shown after a successful check.
    """

    key: str
    name: str
    vendor: str
    package: str
    check_import: str
    distribution: str


AUTOSCRIPT = Library(
    key="autoscript",
    name="Autoscript",
    vendor="Thermo Fisher Scientific",
    package="autoscript_sdb_microscope_client",
    check_import="autoscript_sdb_microscope_client.sdb_microscope_client",
    distribution="autoscript-sdb-microscope-client",
)

LIBRARIES: tuple[Library, ...] = (AUTOSCRIPT,)
"""Every library the application supports, in the order the wizard lists them."""


def library(key: str) -> Library | None:
    """
    Look up a supported library by its key.

    Args:
        key: Identifier of the library.

    Returns:
        The library, or None if the key is unknown (e.g. written by a newer installer).
    """
    return next((lib for lib in LIBRARIES if lib.key == key), None)


@dataclass(frozen=True)
class LinkStatus:
    """
    Outcome of checking a link.

    Attributes:
        ok: True if the library imports from the linked folder.
        version: Version of the library, if it could be determined.
        error: Why the check failed; empty when it succeeded.
    """

    ok: bool
    version: str | None = None
    error: str = ""


_CHECK_SCRIPT = (
    "import importlib, importlib.metadata, json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "importlib.import_module(sys.argv[2])\n"
    "try:\n"
    "    version = importlib.metadata.version(sys.argv[3])\n"
    "except importlib.metadata.PackageNotFoundError:\n"
    "    version = None\n"
    "print(json.dumps({'version': version}))\n"
)


def looks_like(lib: Library, folder: Path) -> bool:
    """
    Quickly check whether a folder contains a library.

    A cheap pre-check before the import check, which starts an interpreter.

    Args:
        lib: The library.
        folder: Candidate folder.

    Returns:
        True if the library's package directory is in the folder.
    """
    return (folder / lib.package).is_dir()


def check_link(python: Path, lib: Library, folder: Path) -> LinkStatus:
    """
    Check that a library imports from a folder in the application's environment.

    The import runs in the application's interpreter, not in the installer's
    own, so it also catches a library built for another Python version.
    A failed check is reported in the result, never raised.

    Args:
        python: Interpreter of the application's virtual environment.
        lib: The library to check.
        folder: The folder to link.

    Returns:
        Whether the library imports, its version, or why it does not.
    """
    if not looks_like(lib, folder):
        return LinkStatus(
            ok=False,
            error=(
                f"This folder does not contain '{lib.package}'. Select the folder "
                f"of the {lib.name} installation that contains it."
            ),
        )

    try:
        completed = subprocess.run(
            [
                str(python),
                "-c",
                _CHECK_SCRIPT,
                str(folder),
                lib.check_import,
                lib.distribution,
            ],
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_S,
            creationflags=(
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if paths.is_windows() else 0
            ),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return LinkStatus(ok=False, error=f"The check could not run: {error}")

    if completed.returncode != 0:
        return LinkStatus(
            ok=False,
            error=f"{lib.name} could not be imported:\n{completed.stderr.strip()}",
        )

    try:
        version = json.loads(completed.stdout.strip().splitlines()[-1])["version"]
    except IndexError, KeyError, ValueError:
        version = None
    return LinkStatus(ok=True, version=version)
