# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Tests for installer orchestration helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from fibsem_maestro_installer import installer, paths
from fibsem_maestro_installer.errors import InstallError
from fibsem_maestro_installer.manifest import Manifest
from fibsem_maestro_installer.releases import Release


def test_wheel_version_reads_the_version_segment() -> None:
    wheel = Path("fibsem_maestro-1.4.0-py3-none-any.whl")

    assert installer.wheel_version(wheel) == "1.4.0"


def test_wheel_version_reads_the_version_segment_beta() -> None:
    wheel = Path("fibsem_maestro-1.4.0b1-py3-none-any.whl")

    assert installer.wheel_version(wheel) == "1.4.0b1"


def test_wheel_version_returns_empty_for_an_odd_name() -> None:
    assert installer.wheel_version(Path("nonsense.whl")) == ""


def test_bundled_wheel_picks_the_application_wheel(tmp_path: Path) -> None:
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    (wheels / "numpy-2.0.0-cp312-cp312-linux_x86_64.whl").write_bytes(b"")
    (wheels / "fibsem_maestro-1.4.0-py3-none-any.whl").write_bytes(b"")

    found = installer.bundled_wheel(tmp_path)

    assert found.name.startswith("fibsem_maestro-")


def test_bundled_wheel_prefers_the_highest_version(tmp_path: Path) -> None:
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    (wheels / "fibsem_maestro-1.3.0-py3-none-any.whl").write_bytes(b"")
    (wheels / "fibsem_maestro-1.4.0-py3-none-any.whl").write_bytes(b"")

    assert installer.bundled_wheel(tmp_path).name.startswith("fibsem_maestro-1.4.0")


def test_bundled_wheel_prefers_the_highest_version_numerically(tmp_path: Path) -> None:
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    (wheels / "fibsem_maestro-1.12.0-py3-none-any.whl").write_bytes(b"")
    (wheels / "fibsem_maestro-1.8.0-py3-none-any.whl").write_bytes(b"")

    assert installer.bundled_wheel(tmp_path).name.startswith("fibsem_maestro-1.12.0")


def test_bundled_wheel_prefers_the_highest_beta_version(tmp_path: Path) -> None:
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    (wheels / "fibsem_maestro-1.4.0b7-py3-none-any.whl").write_bytes(b"")
    (wheels / "fibsem_maestro-1.4.0b12-py3-none-any.whl").write_bytes(b"")

    assert installer.bundled_wheel(tmp_path).name.startswith("fibsem_maestro-1.4.0b12")


def test_bundled_wheel_raises_when_absent(tmp_path: Path) -> None:
    (tmp_path / "wheels").mkdir()

    with pytest.raises(InstallError, match="no fibsem-maestro wheel"):
        installer.bundled_wheel(tmp_path)


def test_install_plan_reports_offline_when_bundled(tmp_path: Path) -> None:
    plan = installer.InstallPlan(
        root=tmp_path,
        autoscript_path=tmp_path,
        repository="cemcof/fibsem-maestro",
        bundle=tmp_path / "bundle",
    )

    assert plan.offline is True


def test_existing_installation_returns_none_for_a_clean_root(
    tmp_path: Path,
) -> None:
    assert installer.existing_installation(tmp_path) is None


def test_existing_installation_reads_a_written_manifest(tmp_path: Path) -> None:
    Manifest(
        app_version="1.4.0",
        root=str(tmp_path),
        python_version="3.12",
        autoscript_path=str(tmp_path),
    ).save(paths.manifest_file(tmp_path))

    manifest = installer.existing_installation(tmp_path)

    assert manifest is not None
    assert manifest.app_version == "1.4.0"


def test_check_for_update_detects_a_newer_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = Manifest(
        app_version="1.3.0",
        root=str(tmp_path),
        python_version="3.12",
        autoscript_path=str(tmp_path),
    )
    release = Release("1.4.0", "w.whl", "https://dl/w.whl")
    monkeypatch.setattr(
        installer.releases,
        "latest_release",
        lambda repo, token=None: release,  # noqa: ARG005
    )

    assert installer.check_for_update(manifest, "cemcof/fibsem-maestro") is release


def test_check_for_update_returns_none_when_current(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest = Manifest(
        app_version="1.4.0",
        root=str(tmp_path),
        python_version="3.12",
        autoscript_path=str(tmp_path),
    )
    release = Release("1.4.0", "w.whl", "https://dl/w.whl")
    monkeypatch.setattr(
        installer.releases,
        "latest_release",
        lambda repo, token=None: release,  # noqa: ARG005
    )

    assert installer.check_for_update(manifest, "cemcof/fibsem-maestro") is None
