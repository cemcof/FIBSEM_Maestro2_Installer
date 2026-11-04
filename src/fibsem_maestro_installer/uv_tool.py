# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Provisioning and invocation of a private uv binary."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tarfile
import zipfile
from typing import TYPE_CHECKING

from fibsem_maestro_installer import paths
from fibsem_maestro_installer.download import download_file, sha256
from fibsem_maestro_installer.errors import InstallError
from fibsem_maestro_installer.progress import ProgressReporter, check_cancelled

if TYPE_CHECKING:
    import threading
    from pathlib import Path

UV_VERSION = "0.13.7"
UV_RELEASE_URL = "https://github.com/astral-sh/uv/releases/download"

_INHERITED_UV_VARIABLES = frozenset({"UV_NATIVE_TLS", "UV_SYSTEM_CERTS"})
"""uv variables kept from the user's environment: certificates for TLS proxies."""


def uv_asset_name() -> str:
    """
    Return the uv release asset for the current platform.

    Returns:
        Asset file name published by the uv project.

    Raises:
        InstallError: If the platform is not supported by the installer.
    """
    machine = platform.machine().lower()

    if paths.is_windows():
        if machine in {"amd64", "x86_64"}:
            return "uv-x86_64-pc-windows-msvc.zip"
        if machine in {"arm64", "aarch64"}:
            return "uv-aarch64-pc-windows-msvc.zip"
    else:
        if machine in {"x86_64", "amd64"}:
            return "uv-x86_64-unknown-linux-gnu.tar.gz"
        if machine in {"aarch64", "arm64"}:
            return "uv-aarch64-unknown-linux-gnu.tar.gz"

    raise InstallError(
        f"Unsupported platform: {platform.system()} {platform.machine()}"
    )


def _extract_uv(archive: Path, destination: Path) -> Path:
    """
    Extract the uv executable from a release archive.

    The archive layout differs between platforms, so the executable is
    located by name rather than by a hard-coded path.

    Args:
        archive: Downloaded `.zip` or `.tar.gz`.
        destination: Path the executable should end up at.

    Returns:
        The destination path.

    Raises:
        InstallError: If no uv executable is found in the archive.
    """
    wanted = "uv.exe" if paths.is_windows() else "uv"
    staging = destination.parent / "_extract"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(staging)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(staging, filter="data")

    found = next((path for path in staging.rglob(wanted) if path.is_file()), None)
    if found is None:
        raise InstallError(f"No {wanted} found inside {archive.name}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(found, destination)
    destination.chmod(0o755)
    shutil.rmtree(staging, ignore_errors=True)
    return destination


def ensure_uv(
    root: Path,
    bundle: Path | None,
    report: ProgressReporter,
    cancel: threading.Event | None = None,
) -> Path:
    """
    Make a private uv executable available.

    Uses the copy from an offline bundle when one is present. Otherwise an
    existing uv is kept if it is the pinned release; if not, the pinned release
    is downloaded, its checksum verified, and the existing uv replaced.

    Args:
        root: Installation root.
        bundle: Offline bundle directory, or None for an online install.
        report: Progress reporter.
        cancel: Cancellation event.

    Returns:
        Path of the uv executable.

    Raises:
        InstallError: If uv cannot be provisioned.
    """
    target = paths.uv_binary(root)
    target.parent.mkdir(parents=True, exist_ok=True)

    if bundle is not None:
        # always the bundle's copy: it matches the interpreter shipped beside it
        source = bundle / ("uv.exe" if paths.is_windows() else "uv")
        if not source.is_file():
            raise InstallError(f"Offline bundle is missing {source.name}")
        report("Installing uv from the offline bundle", 5)
        shutil.copy2(source, target)
        target.chmod(0o755)
        return target

    # an older uv may not know the pinned interpreter,
    # so only the pinned release is reused
    if target.is_file() and installed_uv_version(target) == UV_VERSION:
        return target

    asset = uv_asset_name()

    report(f"Downloading uv {UV_VERSION}", 2)
    archive = download_file(
        f"{UV_RELEASE_URL}/{UV_VERSION}/{asset}",
        root / "bin" / asset,
        report,
        base_percent=2,
        span_percent=6,
        cancel=cancel,
    )

    check_cancelled(cancel)
    checksum = download_file(
        f"{UV_RELEASE_URL}/{UV_VERSION}/{asset}.sha256",
        root / "bin" / f"{asset}.sha256",
        report,
        base_percent=8,
        span_percent=0,
        cancel=cancel,
    )
    expected = checksum.read_text(encoding="utf-8").split()[0].lower()
    if sha256(archive) != expected:
        archive.unlink(missing_ok=True)
        raise InstallError(
            "Checksum of the downloaded uv archive does not match the "
            "published value; the download may be corrupted."
        )

    report("Unpacking uv", 9)
    _extract_uv(archive, target)
    archive.unlink(missing_ok=True)
    checksum.unlink(missing_ok=True)
    return target


def uv_environment(root: Path, offline: bool, managed_python: bool) -> dict[str, str]:
    """
    Build the environment for uv invocations.

    The user's own `UV_*` variables are dropped, as `UV_NO_CONFIG` drops their
    configuration files: a `UV_PYTHON_DOWNLOADS=never` or `UV_PYTHON_INSTALL_DIR`
    meant for their projects would otherwise change what the installer does.
    Only the certificate settings are kept, which a TLS-intercepting proxy needs.

    Args:
        root: Installation root.
        offline: Whether network access should be refused outright.
        managed_python: Whether to expose the private intepreter directory.

    Returns:
        Environment mapping to pass to `subprocess.run`.
    """
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.upper().startswith("UV_") or name.upper() in _INHERITED_UV_VARIABLES
    }

    env.update(
        {
            "UV_CACHE_DIR": str(paths.cache_dir(root)),
            "UV_NO_CONFIG": "1",
            "UV_NO_PROGRESS": "1",
        }
    )

    if managed_python:
        env["UV_PYTHON_INSTALL_DIR"] = str(paths.python_install_dir(root))

    if offline:
        env["UV_OFFLINE"] = "1"
        env["UV_PYTHON_DOWNLOADS"] = "never"

    return env


def run_uv(
    uv: Path,
    arguments: list[str],
    root: Path,
    offline: bool,
    managed_python: bool,
    description: str,
) -> str:
    """
    Run a uv command and return its output.

    Args:
        uv: Path of the uv executable.
        arguments: Arguments following the executable.
        root: Installation root.
        offline: Whether to forbid network access.
        managed_python: Whether to expose the private intepreter directory.
        description: Phrase used in the error message on failure.

    Returns:
        Combined stdout of the command.

    Raises:
        InstallError: If the command exits non-zero.
    """
    completed = subprocess.run(
        [str(uv), *arguments],
        env=uv_environment(root, offline, managed_python),
        capture_output=True,
        text=True,
        creationflags=_no_window_flag(),
        check=False,
    )

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise InstallError(f"{description} failed:\n{detail}")

    return completed.stdout


def _no_window_flag() -> int:
    """
    Return the flag that suppresses console windows on Windows.

    Returns:
        `CREATE_NO_WINDOW` on Windows, 0 elsewhere.
    """
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if paths.is_windows() else 0


def installed_uv_version(uv: Path) -> str | None:
    """
    Ask a uv executable for its version.

    Args:
        uv: Path of the uv executable.

    Returns:
        The version, such as `0.13.7`, or None if uv cannot be run.
    """
    try:
        completed = subprocess.run(
            [str(uv), "--version"],
            capture_output=True,
            text=True,
            creationflags=_no_window_flag(),
            check=False,
            timeout=30,
        )
    except OSError, subprocess.TimeoutExpired:
        return None

    words = completed.stdout.split()
    if completed.returncode != 0 or len(words) < 2 or words[0] != "uv":
        return None
    return words[1]
