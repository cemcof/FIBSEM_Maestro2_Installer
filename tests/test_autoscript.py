# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Tests for Autoscript detection and validation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from fibsem_maestro_installer.autoscript import (
    looks_like_autoscript,
    validate_import,
)
from fibsem_maestro_installer.errors import AutoscriptError


@pytest.fixture
def fake_autoscript(tmp_path: Path) -> Path:
    """
    Create a directory that mimics an Autoscript installation.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        Directory containing an importable stub client package.
    """
    package = tmp_path / "autoscript_sdb_microscope_client"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "sdb_microscope_client.py").write_text(
        "class SdbMicroscopeClient:\n    pass\n", encoding="utf-8"
    )
    return tmp_path


def test_looks_like_autoscript_detects_the_client_package(
    fake_autoscript: Path,
) -> None:
    assert looks_like_autoscript(fake_autoscript) is True


def test_looks_like_autoscript_rejects_an_unrelated_directory(
    tmp_path: Path,
) -> None:
    assert looks_like_autoscript(tmp_path) is False


def test_validate_import_accepts_a_working_installation(
    fake_autoscript: Path,
) -> None:
    validate_import(Path(sys.executable), fake_autoscript)


def test_validate_import_rejects_a_wrong_directory(tmp_path: Path) -> None:
    with pytest.raises(AutoscriptError, match="could not be imported"):
        validate_import(Path(sys.executable), tmp_path)
