# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Orchestration of install, update and uninstall."""

from __future__ import annotations

import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from packaging.utils import parse_wheel_filename

from fibsem_maestro_installer import launchers, paths, releases
from fibsem_maestro_installer.autoscript import validate_import
from fibsem_maestro_installer.config import write_config
from fibsem_maestro_installer.errors import InstallError
from fibsem_maestro_installer.manifest import Manifest, load_manifest
from fibsem_maestro_installer.progress import ProgressReporter, check_cancelled
from fibsem_maestro_installer.uv_tool import ensure_uv, run_uv

if TYPE_CHECKING:
    import threading

WHEEL_PATTERN = re.compile(r"^(?P<name>[^-]+)-(?P<version>[^-]+)-")


@dataclass
class InstallPlan:
    """
    Everything the installer needs to perform an installation.

    Attributes:
        root: Installation root directory.
        autoscript_path: Directory of the user's Autoscript installation.
        repository: GitHub repository in `owner/name` form.
        bundle: Offline bundle directory, or None for an online install.
        token: GitHub token for private repositories, or None.
        python_version: Interpreter version to provision.
    """

    root: Path
    autoscript_path: Path
    repository: str
    bundle: Path | None = None
    token: str | None = None
    python_version: str = paths.PYTHON_VERSION

    @property
    def offline(self) -> bool:
        """
        Report whether this plan installs from an offline bundle.

        Returns:
            True when a bundle directory was supplied.
        """
        return self.bundle is not None


def existing_installation(root: Path) -> Manifest | None:
    """
    Load the manifest of an installation already present at a root.

    Args:
        root: Candidate installation root.

    Returns:
        The manifest, or None when nothing is installed there.
    """
    return load_manifest(paths.manifest_file(root))


def wheel_version(wheel: Path) -> str:
    """
    Extract the version from a wheel file name.

    Args:
        wheel: Path of the wheel.

    Returns:
        The version segment, or an empty string if unparseable.
    """
    match = WHEEL_PATTERN.match(wheel.name)
    return match.group("version") if match else ""


def bundled_wheel(bundle: Path) -> Path:
    """
    Locate the application wheel inside an offline bundle.

    Args:
        bundle: Offline bundle directory.

    Returns:
        Path of the application's own wheel.

    Raises:
        InstallError: If no matching wheel is present.
    """
    prefix = paths.DISTRIBUTION.replace("-", "_")
    matches = list((bundle / "wheels").glob(f"{prefix}-*.whl"))
    if not matches:
        raise InstallError(f"Offline bundle contains no {paths.DISTRIBUTION} wheel.")

    return max(matches, key=lambda p: parse_wheel_filename(p.name)[1])


def _extract_python(bundle: Path, root: Path) -> Path:
    """
    Extract the standalone interpreter shipped in an offline bundle.

    `uv python install` needs network access, so an offline installation
    unpacks the interpreter directly and points uv at the result.

    Args:
        bundle: Offline bundle directory.
        root: Installation root.

    Returns:
        Path of the extracted interpreter executable.

    Raises:
        InstallError: If the archive is missing or contains no interpreter.
    """
    archives = sorted((bundle / "python").glob("*"))
    archives = [path for path in archives if path.is_file()]
    if not archives:
        raise InstallError("Offline bundle contains no Python interpreter.")

    archive = archives[0]
    destination = paths.python_install_dir(root)
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as data:
            data.extractall(destination)
    else:
        with tarfile.open(archive) as data:
            data.extractall(destination, filter="data")

    names = ("python.exe",) if paths.is_windows() else ("python3", "python")
    for name in names:
        found = next((path for path in destination.rglob(name) if path.is_file()), None)
        if found is not None:
            found.chmod(0o755)
            return found

    raise InstallError(
        f"No interpreter found inside {archive.name}. The offline bundle may "
        "have been built for a different platform."
    )


def install(
    plan: InstallPlan,
    report: ProgressReporter,
    cancel: threading.Event | None = None,
    reinstall: bool = False,
) -> Manifest:
    """
    Perform a full installation.

    Online and offline installs follow the same sequence; only the source of
    uv, the interpreter and the wheels differs.

    Args:
        plan: Description of what to install and where.
        report: Progress reporter.
        cancel: Cancellation event.
        reinstall: Force replacement of an already-installed application.

    Returns:
        The manifest describing the completed installation.

    Raises:
        InstallError: If any step fails.
    """
    root = plan.root
    root.mkdir(parents=True, exist_ok=True)

    report("Preparing", 1)
    uv = ensure_uv(root, plan.bundle, report, cancel)

    check_cancelled(cancel)
    if plan.offline:
        if plan.bundle is None:
            raise InstallError("Offline installation requires a bundle directory.")
        report("Unpacking the bundled Python interpreter", 12)
        interpreter: str = str(_extract_python(plan.bundle, root))
    else:
        report(f"Installing Python {plan.python_version}", 12)
        run_uv(
            uv,
            [
                "python",
                "install",
                plan.python_version,
                "--no-bin",
                "--no-registry",
            ],
            root,
            offline=False,
            description="Installing Python",
            managed_python=True,
        )

        candidates = sorted(
            paths.python_install_dir(root).glob(f"cpython-{plan.python_version}.*")
        )
        if not candidates:
            raise InstallError("The Python interpreter could not be located.")
        name = "python.exe" if paths.is_windows() else "bin/python3"
        interpreter = str(candidates[-1] / name)

    check_cancelled(cancel)
    report("Creating the application environment", 32)
    venv = paths.venv_dir(root)
    shutil.rmtree(venv, ignore_errors=True)
    venv_arguments = ["venv", "--relocatable", "--python", interpreter, str(venv)]
    run_uv(
        uv,
        venv_arguments,
        root,
        offline=plan.offline,
        description="Creating the virtual environment",
        managed_python=False,
    )

    check_cancelled(cancel)
    report("Preparing FIBSEM Maestro", 45)
    if plan.offline:
        if plan.bundle is None:
            raise InstallError("Offline installation requires a bundle directory.")

        wheel = bundled_wheel(plan.bundle)
        version = wheel_version(wheel)
        install_arguments = [
            "pip",
            "install",
            "--python",
            str(paths.venv_python(root)),
            "--offline",
            "--no-index",
            "--find-links",
            str(plan.bundle / "wheels"),
        ]
    else:
        release = releases.latest_release(plan.repository, plan.token)
        version = release.version
        wheel = releases.download_wheel(
            release,
            root / "downloads",
            report,
            base_percent=45,
            span_percent=15,
            token=plan.token,
            cancel=cancel,
        )
        install_arguments = [
            "pip",
            "install",
            "--python",
            str(paths.venv_python(root)),
        ]

    if reinstall:
        install_arguments.append("--reinstall")
    install_arguments.append(str(wheel))

    report("Installing FIBSEM Maestro", 62)
    run_uv(
        uv,
        install_arguments,
        root,
        offline=plan.offline,
        description="Installing the application",
        managed_python=False,
    )

    check_cancelled(cancel)
    report("Writing configuration", 78)
    write_config(paths.config_file(root), plan.autoscript_path)

    report("Verifying the Autoscript installation", 82)
    validate_import(paths.venv_python(root), plan.autoscript_path)

    check_cancelled(cancel)
    report("Creating shortcuts", 90)
    created = launchers.create_launchers(root)

    report("Finishing", 97)
    shutil.rmtree(root / "downloads", ignore_errors=True)

    manifest = Manifest(
        app_version=version,
        root=str(root),
        python_version=plan.python_version,
        autoscript_path=str(plan.autoscript_path),
        launchers=[str(path) for path in created],
        offline_install=plan.offline,
    )
    manifest.save(paths.manifest_file(root))

    report("Installation complete", 100)
    return manifest


def check_for_update(
    manifest: Manifest, repository: str, token: str | None = None
) -> releases.Release | None:
    """
    Determine whether a newer release is available.

    Args:
        manifest: Manifest of the current installation.
        repository: GitHub repository in ``owner/name`` form.
        token: GitHub token for private repositories, or None.

    Returns:
        The newer release, or None when the installation is current.
    """
    release = releases.latest_release(repository, token)
    if releases.is_newer(release.version, manifest.app_version):
        return release
    return None


def uninstall(manifest: Manifest, report: ProgressReporter) -> None:
    """
    Remove an installation and everything it created.

    Args:
        manifest: Manifest of the installation to remove.
        report: Progress reporter.

    Raises:
        InstallError: If the installation directory cannot be removed.
    """
    report("Removing shortcuts", 20)
    launchers.remove_launchers([Path(path) for path in manifest.launchers])

    report("Removing the application", 60)
    root = Path(manifest.root)
    try:
        shutil.rmtree(root, ignore_errors=False)
    except OSError as error:
        raise InstallError(
            f"Could not remove {root}: {error}\n\n"
            "Close FIBSEM Maestro if it is still running and try again."
        ) from error

    report("Uninstall complete", 100)
