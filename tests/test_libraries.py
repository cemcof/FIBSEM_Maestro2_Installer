# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Tests for the supported manufacturer libraries and their link checks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from fibsem_maestro_installer.libraries import (
    AUTOSCRIPT,
    LIBRARIES,
    check_link,
    library,
    looks_like,
)


@pytest.fixture
def fake_autoscript(tmp_path: Path) -> Path:
    """
    Create a folder that mimics an Autoscript installation.

    Args:
        tmp_path: Temporary directory supplied by pytest.

    Returns:
        Folder with an importable stub client package and its metadata.
    """
    package = tmp_path / "autoscript_sdb_microscope_client"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "sdb_microscope_client.py").write_text(
        "class SdbMicroscopeClient:\n    pass\n", encoding="utf-8"
    )
    info = tmp_path / "autoscript_sdb_microscope_client-4.13.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: autoscript-sdb-microscope-client\n"
        "Version: 4.13.0\n",
        encoding="utf-8",
    )
    return tmp_path


def test_libraries_have_unique_keys() -> None:
    keys = [lib.key for lib in LIBRARIES]

    assert len(keys) == len(set(keys))


def test_library_finds_autoscript_by_key() -> None:
    assert library("autoscript") is AUTOSCRIPT


def test_library_returns_none_for_an_unknown_key() -> None:
    assert library("written-by-a-newer-installer") is None


def test_looks_like_detects_the_client_package(fake_autoscript: Path) -> None:
    assert looks_like(AUTOSCRIPT, fake_autoscript) is True


def test_looks_like_rejects_an_unrelated_folder(tmp_path: Path) -> None:
    assert looks_like(AUTOSCRIPT, tmp_path) is False


def test_check_link_accepts_a_working_installation(fake_autoscript: Path) -> None:
    status = check_link(Path(sys.executable), AUTOSCRIPT, fake_autoscript)

    assert status.ok
    assert status.version == "4.13.0"


def test_check_link_reports_a_wrong_folder(tmp_path: Path) -> None:
    status = check_link(Path(sys.executable), AUTOSCRIPT, tmp_path)

    assert not status.ok
    assert AUTOSCRIPT.package in status.error


def test_check_link_reports_a_library_that_does_not_import(
    fake_autoscript: Path,
) -> None:
    """E.g. a library built for another Python version: reported, never raised."""
    client = fake_autoscript / AUTOSCRIPT.package / "sdb_microscope_client.py"
    client.write_text("import a_module_that_does_not_exist\n", encoding="utf-8")

    status = check_link(Path(sys.executable), AUTOSCRIPT, fake_autoscript)

    assert not status.ok
    assert "a_module_that_does_not_exist" in status.error


def test_check_link_reports_a_missing_interpreter(
    fake_autoscript: Path, tmp_path: Path
) -> None:
    status = check_link(tmp_path / "no-python", AUTOSCRIPT, fake_autoscript)

    assert not status.ok
