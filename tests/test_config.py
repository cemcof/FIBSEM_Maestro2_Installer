# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Tests for the links stored in the application's `config.toml`."""

from __future__ import annotations

import tomllib
from pathlib import Path

from fibsem_maestro_installer.config import read_links, write_links


def _read(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def test_read_links_of_a_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_links(tmp_path / "config.toml") == {}


def test_written_links_are_read_back(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"

    write_links(path, {"autoscript": Path("/opt/autoscript")})

    assert read_links(path) == {"autoscript": Path("/opt/autoscript")}
    assert _read(path) == {
        "libraries": {"autoscript": {"path": str(Path("/opt/autoscript"))}}
    }


def test_legacy_autoscript_table_is_read(tmp_path: Path) -> None:
    """`config.toml` as older installers wrote it."""
    path = tmp_path / "config.toml"
    path.write_text('[autoscript]\npath = "/opt/autoscript"\n', encoding="utf-8")

    assert read_links(path) == {"autoscript": Path("/opt/autoscript")}


def test_writing_migrates_the_legacy_table(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[autoscript]\npath = "/opt/autoscript"\n', encoding="utf-8")

    write_links(path, read_links(path))

    assert _read(path) == {
        "libraries": {"autoscript": {"path": str(Path("/opt/autoscript"))}}
    }


def test_writing_no_links_unlinks_everything(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    write_links(path, {"autoscript": Path("/opt/autoscript")})

    write_links(path, {})

    assert read_links(path) == {}
    assert "libraries" not in _read(path)


def test_writing_links_keeps_other_settings(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[logging]\nlevel = "debug"\n', encoding="utf-8")

    write_links(path, {"autoscript": Path("/opt/autoscript")})

    assert _read(path)["logging"] == {"level": "debug"}


def test_unreadable_file_has_no_links(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("this is [not toml", encoding="utf-8")

    assert read_links(path) == {}
