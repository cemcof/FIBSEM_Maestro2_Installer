# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Tests for the install manifest."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fibsem_maestro_installer.manifest import Manifest, load_manifest

if TYPE_CHECKING:
    from pathlib import Path


def _manifest(root: Path) -> Manifest:
    """
    Build a manifest for tests.

    Args:
        root: Installation root to record.

    Returns:
        A populated manifest.
    """
    return Manifest(
        app_version="1.4.0",
        root=str(root),
        python_version="3.12",
        libraries={"autoscript": str(root / "autoscript")},
        launchers=[str(root / "shortcut.lnk")],
    )


def test_manifest_roundtrips_through_disk(tmp_path: Path) -> None:
    path = tmp_path / "install.json"
    original = _manifest(tmp_path)
    original.save(path)

    loaded = load_manifest(path)

    assert loaded == original


def test_manifest_stamps_installation_time(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)

    assert manifest.installed_at.endswith("+00:00")


def test_load_manifest_returns_none_when_absent(tmp_path: Path) -> None:
    assert load_manifest(tmp_path / "missing.json") is None


def test_load_manifest_returns_none_for_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "install.json"
    path.write_text("{not json", encoding="utf-8")

    assert load_manifest(path) is None


def test_load_manifest_rejects_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "install.json"
    manifest = _manifest(tmp_path)
    manifest.schema = 99
    manifest.save(path)

    assert load_manifest(path) is None


def test_load_manifest_ignores_unexpected_keys(tmp_path: Path) -> None:
    path = tmp_path / "install.json"
    _manifest(tmp_path).save(path)
    text = path.read_text(encoding="utf-8").replace(
        '"schema"', '"future_field": 1, "schema"'
    )
    path.write_text(text, encoding="utf-8")

    assert load_manifest(path) is not None


def test_manifest_of_an_older_installer_is_migrated(tmp_path: Path) -> None:
    """Installations made before linking became optional must still be recognised."""
    path = tmp_path / "install.json"
    path.write_text(
        json.dumps(
            {
                "app_version": "1.4.0",
                "root": str(tmp_path),
                "python_version": "3.11",
                "autoscript_path": "C:/Autoscript",
                "launchers": [],
                "installed_at": "2026-01-01T00:00:00+00:00",
                "offline_install": False,
                "schema": 1,
            }
        ),
        encoding="utf-8",
    )

    manifest = load_manifest(path)

    assert manifest is not None
    assert manifest.libraries == {"autoscript": "C:/Autoscript"}
    assert manifest.schema == 2


def test_manifest_without_links_has_no_libraries(tmp_path: Path) -> None:
    path = tmp_path / "install.json"
    Manifest(app_version="1.4.0", root=str(tmp_path), python_version="3.14.7").save(
        path
    )

    manifest = load_manifest(path)

    assert manifest is not None
    assert manifest.libraries == {}
