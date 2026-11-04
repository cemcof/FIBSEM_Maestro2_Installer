# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Orchestration of install, update and uninstall."""

from __future__ import annotations

import email.parser
import json
import os
import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import parse_wheel_filename

from fibsem_maestro_installer import launchers, paths, releases
from fibsem_maestro_installer.config import read_links, write_links
from fibsem_maestro_installer.errors import InstallError
from fibsem_maestro_installer.libraries import LinkStatus, check_link, library
from fibsem_maestro_installer.manifest import Manifest, load_manifest
from fibsem_maestro_installer.progress import ProgressReporter, check_cancelled
from fibsem_maestro_installer.uv_tool import ensure_uv, run_uv

if TYPE_CHECKING:
    import threading
    from collections.abc import Mapping

WHEEL_PATTERN = re.compile(r"^(?P<name>[^-]+)-(?P<version>[^-]+)-")


@dataclass
class InstallPlan:
    """
    Everything the installer needs to perform an installation.

    Manufacturer libraries are not part of the plan: an installation keeps the
    links it already has, and links are changed separately (`set_links`).

    Attributes:
        root: Installation root directory.
        repository: GitHub repository in `owner/name` form.
        bundle: Offline bundle directory, or None for an online install.
        token: GitHub token for private repositories, or None.
        python_version: Interpreter version to provision.
    """

    root: Path
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


@dataclass
class InstallResult:
    """
    Outcome of a completed installation.

    Attributes:
        manifest: The manifest of the installation.
        link_problems: Linked libraries that no longer import in the new
            environment, by library key. The installation itself is complete
            and usable; these links need fixing or unlinking.
    """

    manifest: Manifest
    link_problems: dict[str, LinkStatus] = field(default_factory=dict)


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


def bundle_python_version(bundle: Path) -> str | None:
    """
    Read the interpreter version an offline bundle was built with.

    Args:
        bundle: Offline bundle directory.

    Returns:
        The version recorded in the bundle's `manifest.json`, or None if absent.
    """
    try:
        data = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    version = data.get("python_version") if isinstance(data, dict) else None
    return version if isinstance(version, str) and version else None


def required_python(wheel: Path) -> SpecifierSet | None:
    """
    Read the Python versions a wheel supports.

    Args:
        wheel: The application wheel.

    Returns:
        The wheel's `Requires-Python`, or None if it declares none or cannot be read.
    """
    try:
        with zipfile.ZipFile(wheel) as archive:
            name = next(
                (n for n in archive.namelist() if n.endswith(".dist-info/METADATA")),
                None,
            )
            if name is None:
                return None
            metadata = email.parser.HeaderParser().parsestr(
                archive.read(name).decode("utf-8", errors="replace")
            )
    except OSError, zipfile.BadZipFile:
        return None

    value = metadata.get("Requires-Python")
    if not value:
        return None
    try:
        return SpecifierSet(value)
    except InvalidSpecifier:
        return None


def check_python_requirement(wheel: Path, python_version: str) -> None:
    """
    Verify that the interpreter the installer provisions can run a wheel.

    Runs before the existing environment is replaced, so an installer that is
    too old for a release fails without breaking the current installation.

    Args:
        wheel: The application wheel.
        python_version: Interpreter version that will be provisioned.

    Raises:
        InstallError: If the wheel requires a different Python version.
    """
    specifier = required_python(wheel)
    if specifier is None or specifier.contains(python_version, prereleases=True):
        return

    raise InstallError(
        f"{paths.APP_NAME} {wheel_version(wheel)} requires Python {specifier}, "
        f"but this installer provides Python {python_version}.\n\n"
        "Download the latest installer and run it again. The current "
        "installation was not changed."
    )


def _interpreter_dirs(root: Path) -> list[Path]:
    """
    List the managed interpreter directories (not uv's minor-version links).

    Args:
        root: Installation root.

    Returns:
        Directories named like `cpython-3.14.7-<platform>`.
    """
    pattern = re.compile(r"^cpython-\d+\.\d+\.\d+")
    directory = paths.python_install_dir(root)
    if not directory.is_dir():
        return []
    return [
        path
        for path in directory.iterdir()
        if pattern.match(path.name)
        and path.is_dir()
        and not path.is_symlink()
        and not os.path.isjunction(path)
    ]


def _interpreter_dir(root: Path, python_version: str) -> Path:
    """
    Locate the managed interpreter of a version.

    Args:
        root: Installation root.
        python_version: Interpreter version, e.g. `3.14.7`.

    Returns:
        The interpreter's directory.

    Raises:
        InstallError: If it is not installed.
    """
    prefix = f"cpython-{python_version}"
    candidates = sorted(
        path
        for path in _interpreter_dirs(root)
        if path.name.startswith(prefix) and path.name[len(prefix)] in ".-"
    )
    if not candidates:
        raise InstallError("The Python interpreter could not be located.")
    return candidates[-1]


def _remove_other_interpreters(root: Path, keep: Path) -> None:
    """
    Delete managed interpreters other than the one the environment uses.

    Removes e.g. the Python 3.11 an older version installed. Best effort: a
    directory that cannot be deleted is left behind.

    Args:
        root: Installation root.
        keep: The interpreter directory in use.
    """
    for path in _interpreter_dirs(root):
        if path != keep:
            shutil.rmtree(path, ignore_errors=True)


def check_links(root: Path, links: Mapping[str, Path]) -> dict[str, LinkStatus]:
    """
    Check every link in the installation's environment.

    Links to libraries this installer does not know (written by a newer one)
    are not checked.

    Args:
        root: Installation root.
        links: Folder of each linked library, by library key.

    Returns:
        The status of each checked link, by library key.
    """
    python = paths.venv_python(root)
    return {
        key: check_link(python, lib, folder)
        for key, folder in links.items()
        if (lib := library(key)) is not None
    }


def set_links(root: Path, links: Mapping[str, Path]) -> None:
    """
    Replace the linked libraries of an installation.

    Writes `config.toml`, which the application reads, and the manifest.

    Args:
        root: Installation root.
        links: Folder of each library to link, by library key; libraries not
            listed are unlinked.
    """
    write_links(paths.config_file(root), links)

    manifest = existing_installation(root)
    if manifest is not None:
        manifest.libraries = {key: str(folder) for key, folder in links.items()}
        manifest.save(paths.manifest_file(root))


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


def _application_wheel(
    plan: InstallPlan,
    root: Path,
    report: ProgressReporter,
    cancel: threading.Event | None,
) -> tuple[Path, str]:
    """
    Locate (offline) or download (online) the application wheel.

    Args:
        plan: The installation plan.
        root: Installation root.
        report: Progress reporter.
        cancel: Cancellation event.

    Returns:
        The wheel and its version.
    """
    if plan.bundle is not None:
        wheel = bundled_wheel(plan.bundle)
        return wheel, wheel_version(wheel)

    release = releases.latest_release(plan.repository, plan.token)
    wheel = releases.download_wheel(
        release,
        root / "downloads",
        report,
        base_percent=10,
        span_percent=15,
        token=plan.token,
        cancel=cancel,
    )
    return wheel, release.version


def install(
    plan: InstallPlan,
    report: ProgressReporter,
    cancel: threading.Event | None = None,
    reinstall: bool = False,
) -> InstallResult:
    """
    Perform a full installation.

    Online and offline installs follow the same sequence; only the source of
    uv, the interpreter and the wheels differs. Linked libraries are kept and
    checked again in the new environment; a link that no longer works does not
    fail the installation, it is reported in the result.

    Args:
        plan: Description of what to install and where.
        report: Progress reporter.
        cancel: Cancellation event.
        reinstall: Force replacement of an already-installed application.

    Returns:
        The manifest of the completed installation and any broken links.

    Raises:
        InstallError: If any step fails.
    """
    # never wipe `root` here: FIBSEM Maestro keeps the user's profiles and logs in
    # `root/config` and `root/logs`, which must survive Update and Repair; only
    # delete the installer's own subfolders (runtime/, python/, downloads/)
    root = plan.root
    root.mkdir(parents=True, exist_ok=True)

    report("Preparing", 1)
    uv = ensure_uv(root, plan.bundle, report, cancel)

    # get the wheel first: whether the release can run on the interpreter this
    # installer provides is checked before the existing environment is touched
    check_cancelled(cancel)
    report("Preparing FIBSEM Maestro", 10)
    wheel, version = _application_wheel(plan, root, report, cancel)
    python_version = plan.python_version
    if plan.bundle is not None:
        python_version = bundle_python_version(plan.bundle) or python_version
    check_python_requirement(wheel, python_version)

    check_cancelled(cancel)
    if plan.bundle is not None:
        report("Unpacking the bundled Python interpreter", 28)
        interpreter_path = _extract_python(plan.bundle, root)
        interpreter_dir: Path | None = None
    else:
        report(f"Installing Python {python_version}", 28)
        run_uv(
            uv,
            [
                "python",
                "install",
                python_version,
                "--no-bin",
                "--no-registry",
            ],
            root,
            offline=False,
            description="Installing Python",
            managed_python=True,
        )
        interpreter_dir = _interpreter_dir(root, python_version)
        name = "python.exe" if paths.is_windows() else "bin/python3"
        interpreter_path = interpreter_dir / name

    check_cancelled(cancel)
    report("Creating the application environment", 45)
    venv = paths.venv_dir(root)
    shutil.rmtree(venv, ignore_errors=True)
    run_uv(
        uv,
        ["venv", "--relocatable", "--python", str(interpreter_path), str(venv)],
        root,
        offline=plan.offline,
        description="Creating the virtual environment",
        managed_python=False,
    )

    check_cancelled(cancel)
    install_arguments = ["pip", "install", "--python", str(paths.venv_python(root))]
    if plan.bundle is not None:
        install_arguments += [
            "--offline",
            "--no-index",
            "--find-links",
            str(plan.bundle / "wheels"),
        ]
    if reinstall:
        install_arguments.append("--reinstall")
    install_arguments.append(str(wheel))

    report("Installing FIBSEM Maestro", 55)
    run_uv(
        uv,
        install_arguments,
        root,
        offline=plan.offline,
        description="Installing the application",
        managed_python=False,
    )

    check_cancelled(cancel)
    report("Writing configuration", 75)
    # keeps the existing links and migrates the format older installers wrote
    links = read_links(paths.config_file(root))
    write_links(paths.config_file(root), links)

    report("Creating shortcuts", 80)
    created = launchers.create_launchers(root)

    report("Finishing", 85)
    shutil.rmtree(root / "downloads", ignore_errors=True)
    if interpreter_dir is not None:
        _remove_other_interpreters(root, interpreter_dir)

    manifest = Manifest(
        app_version=version,
        root=str(root),
        python_version=python_version,
        libraries={key: str(folder) for key, folder in links.items()},
        launchers=[str(path) for path in created],
        offline_install=plan.offline,
    )
    manifest.save(paths.manifest_file(root))

    if links:
        report("Checking the linked microscope libraries", 90)
    problems = {key: s for key, s in check_links(root, links).items() if not s.ok}

    report("Installation complete", 100)
    return InstallResult(manifest, problems)


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
