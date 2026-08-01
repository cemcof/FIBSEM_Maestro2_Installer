# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Tests for uv provisioning."""

from __future__ import annotations

import platform
import sys
import tarfile
import zipfile
from typing import TYPE_CHECKING

import pytest

from fibsem_maestro_installer import paths, uv_tool
from fibsem_maestro_installer.errors import InstallError

if TYPE_CHECKING:
    from pathlib import Path


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
    env = uv_tool.uv_environment(tmp_path, offline=False)

    assert env["UV_PYTHON_INSTALL_DIR"] == str(paths.python_install_dir(tmp_path))
    assert env["UV_CACHE_DIR"] == str(paths.cache_dir(tmp_path))
    assert env["UV_NO_CONFIG"] == "1"
    assert "UV_OFFLINE" not in env


def test_uv_environment_forbids_network_when_offline(tmp_path: Path) -> None:
    env = uv_tool.uv_environment(tmp_path, offline=True)

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
