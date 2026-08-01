# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Tests for launcher creation."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from fibsem_maestro_installer import launchers, paths

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_desktop_entry_names_the_venv_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    text = launchers.desktop_entry_text(tmp_path)

    assert f"Exec={paths.app_executable(tmp_path)}" in text
    assert f"Icon={paths.DESKTOP_ID}" in text


def test_desktop_entry_sets_startup_wm_class(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    text = launchers.desktop_entry_text(tmp_path)

    assert f"StartupWMClass={paths.APP_SLUG}" in text


def test_remove_launchers_tolerates_missing_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    present = tmp_path / "entry.desktop"
    present.write_text("", encoding="utf-8")

    launchers.remove_launchers([present, tmp_path / "gone.desktop"])

    assert not present.exists()


def test_sanitise_wm_class_strips_invalid_characters() -> None:
    assert launchers.sanitise_wm_class("fibsem maestro!/v2") == "fibsemmaestrov2"
