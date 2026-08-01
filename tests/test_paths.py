# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Tests for platform path resolution."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from fibsem_maestro_installer import paths

if TYPE_CHECKING:
    import pytest


def test_default_install_root_uses_localappdata_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert paths.default_install_root() == tmp_path / "FibsemMaestro"


def test_default_install_root_uses_xdg_data_home_on_linux(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    assert paths.default_install_root() == tmp_path / paths.APP_SLUG


def test_default_install_root_falls_back_without_xdg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    expected = Path.home() / ".local" / "share" / paths.APP_SLUG
    assert paths.default_install_root() == expected


def test_venv_layout_differs_between_platforms(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert paths.venv_python(tmp_path).name == "python.exe"
    assert paths.venv_bin_dir(tmp_path).name == "Scripts"

    monkeypatch.setattr(sys, "platform", "linux")
    assert paths.venv_python(tmp_path).name == "python"
    assert paths.venv_bin_dir(tmp_path).name == "bin"


def test_app_executable_gains_exe_suffix_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert paths.app_executable(tmp_path).name == f"{paths.APP_SLUG}.exe"

    monkeypatch.setattr(sys, "platform", "linux")
    assert paths.app_executable(tmp_path).name == paths.APP_SLUG
