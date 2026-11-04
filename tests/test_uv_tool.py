# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Tests for uv provisioning."""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from fibsem_maestro_installer import paths, uv_tool
from fibsem_maestro_installer.errors import InstallError
from fibsem_maestro_installer.progress import null_reporter


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("win32", "AMD64", "uv-x86_64-pc-windows-msvc.zip"),
        ("win32", "ARM64", "uv-aarch64-pc-windows-msvc.zip"),
        ("linux", "x86_64", "uv-x86_64-unknown-linux-gnu.tar.gz"),
        ("linux", "aarch64", "uv-aarch64-unknown-linux-gnu.tar.gz"),
    ],
)
def test_uv_asset_name_maps_supported_platforms(
    monkeypatch: pytest.MonkeyPatch, system: str, machine: str, expected: str
) -> None:
    monkeypatch.setattr(sys, "platform", system)
    monkeypatch.setattr(platform, "machine", lambda: machine)

    assert uv_tool.uv_asset_name() == expected


def test_uv_asset_name_rejects_unknown_architecture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(platform, "machine", lambda: "riscv64")

    with pytest.raises(InstallError, match="Unsupported platform"):
        uv_tool.uv_asset_name()


def test_uv_environment_confines_uv_to_the_install_root(tmp_path: Path) -> None:
    env = uv_tool.uv_environment(tmp_path, offline=False, managed_python=True)

    assert env["UV_PYTHON_INSTALL_DIR"] == str(paths.python_install_dir(tmp_path))
    assert env["UV_CACHE_DIR"] == str(paths.cache_dir(tmp_path))
    assert env["UV_NO_CONFIG"] == "1"
    assert "UV_OFFLINE" not in env


def test_uv_environment_does_not_set_uv_python_install_dir_when_managed_python_is_false(
    tmp_path: Path,
) -> None:
    env = uv_tool.uv_environment(tmp_path, offline=False, managed_python=False)

    assert not env.get("UV_PYTHON_INSTALL_DIR")
    assert env["UV_CACHE_DIR"] == str(paths.cache_dir(tmp_path))
    assert env["UV_NO_CONFIG"] == "1"
    assert "UV_OFFLINE" not in env


def test_uv_environment_forbids_network_when_offline(tmp_path: Path) -> None:
    env = uv_tool.uv_environment(tmp_path, offline=True, managed_python=False)

    assert env["UV_OFFLINE"] == "1"
    assert env["UV_PYTHON_DOWNLOADS"] == "never"


def test_extract_uv_finds_the_executable_in_a_tarball(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    payload = tmp_path / "uv"
    payload.write_text("#!/bin/sh\n", encoding="utf-8")
    archive = tmp_path / "uv-x86_64-unknown-linux-gnu.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(payload, arcname="uv-x86_64-unknown-linux-gnu/uv")

    destination = uv_tool._extract_uv(archive, tmp_path / "bin" / "uv")

    assert destination.is_file()
    assert destination.read_text(encoding="utf-8").startswith("#!")


def test_extract_uv_finds_the_executable_in_a_zip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    archive = tmp_path / "uv-x86_64-pc-windows-msvc.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("uv.exe", "binary")

    destination = uv_tool._extract_uv(archive, tmp_path / "bin" / "uv.exe")

    assert destination.is_file()


def test_extract_uv_reports_a_missing_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    archive = tmp_path / "empty.tar.gz"
    with tarfile.open(archive, "w:gz"):
        pass

    with pytest.raises(InstallError, match="No uv found"):
        uv_tool._extract_uv(archive, tmp_path / "bin" / "uv")


@pytest.fixture
def fake_release(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """
    Serve the pinned uv release without network access.

    Returns:
        The URLs downloaded, in order.
    """
    downloaded: list[str] = []

    def download(
        url: str, destination: Path, *_args: object, **_kwargs: object
    ) -> Path:
        downloaded.append(url)
        if url.endswith(".sha256"):
            digest = hashlib.sha256(b"archive").hexdigest()
            destination.write_text(f"{digest}  uv.tar.gz\n", encoding="utf-8")
        else:
            destination.write_bytes(b"archive")
        return destination

    def extract(_archive: Path, destination: Path) -> Path:
        destination.write_text("pinned", encoding="utf-8")
        return destination

    monkeypatch.setattr(uv_tool, "download_file", download)
    monkeypatch.setattr(uv_tool, "_extract_uv", extract)
    return downloaded


def _existing_uv(root: Path) -> Path:
    """Place a uv from an earlier installation."""
    uv = paths.uv_binary(root)
    uv.parent.mkdir(parents=True)
    uv.write_text("existing", encoding="utf-8")
    return uv


def test_ensure_uv_downloads_the_pinned_release_into_a_new_installation(
    tmp_path: Path, fake_release: list[str]
) -> None:
    uv = uv_tool.ensure_uv(tmp_path, None, null_reporter)

    assert uv.read_text(encoding="utf-8") == "pinned"
    assert f"/{uv_tool.UV_VERSION}/" in fake_release[0]


def test_ensure_uv_replaces_an_outdated_uv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_release: list[str]
) -> None:
    # an old uv does not know newer interpreters ("No download found for request")
    _existing_uv(tmp_path)
    monkeypatch.setattr(uv_tool, "installed_uv_version", lambda _uv: "0.12.1")

    uv = uv_tool.ensure_uv(tmp_path, None, null_reporter)

    assert uv.read_text(encoding="utf-8") == "pinned"
    assert fake_release


def test_ensure_uv_replaces_a_uv_that_does_not_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_release: list[str]
) -> None:
    _existing_uv(tmp_path)
    monkeypatch.setattr(uv_tool, "installed_uv_version", lambda _uv: None)

    uv = uv_tool.ensure_uv(tmp_path, None, null_reporter)

    assert uv.read_text(encoding="utf-8") == "pinned"
    assert fake_release


def test_ensure_uv_keeps_the_pinned_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_release: list[str]
) -> None:
    _existing_uv(tmp_path)
    monkeypatch.setattr(uv_tool, "installed_uv_version", lambda _uv: uv_tool.UV_VERSION)

    uv = uv_tool.ensure_uv(tmp_path, None, null_reporter)

    assert uv.read_text(encoding="utf-8") == "existing"
    assert not fake_release


def test_ensure_uv_takes_the_bundle_uv_over_an_existing_one(
    tmp_path: Path, fake_release: list[str]
) -> None:
    root = tmp_path / "root"
    _existing_uv(root)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / paths.uv_binary(root).name).write_text("bundled", encoding="utf-8")

    uv = uv_tool.ensure_uv(root, bundle, null_reporter)

    assert uv.read_text(encoding="utf-8") == "bundled"
    assert not fake_release


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ("uv 0.13.7\n", "0.13.7"),
        ("uv 0.13.7 (0123abcd 2026-10-20)\n", "0.13.7"),
        ("something else\n", None),
        ("", None),
    ],
)
def test_installed_uv_version_parses_the_version_output(
    monkeypatch: pytest.MonkeyPatch, stdout: str, expected: str | None
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, stdout, ""),
    )

    assert uv_tool.installed_uv_version(Path("uv")) == expected


def test_installed_uv_version_is_none_for_a_missing_executable(tmp_path: Path) -> None:
    assert uv_tool.installed_uv_version(tmp_path / "missing-uv") is None
