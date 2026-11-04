# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Tests for installer orchestration helpers."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

from fibsem_maestro_installer import installer, paths
from fibsem_maestro_installer.config import read_links
from fibsem_maestro_installer.errors import InstallError
from fibsem_maestro_installer.manifest import Manifest
from fibsem_maestro_installer.progress import null_reporter
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
    )
    release = Release("1.4.0", "w.whl", "https://dl/w.whl")
    monkeypatch.setattr(
        installer.releases,
        "latest_release",
        lambda repo, token=None: release,  # noqa: ARG005
    )

    assert installer.check_for_update(manifest, "cemcof/fibsem-maestro") is None


def _wheel(directory: Path, version: str, requires_python: str | None) -> Path:
    """
    Write a minimal application wheel.

    Args:
        directory: Where to put it.
        version: Version of the wheel.
        requires_python: Its `Requires-Python`, or None for none.

    Returns:
        Path of the wheel.
    """
    wheel = directory / f"fibsem_maestro-{version}-py3-none-any.whl"
    metadata = f"Metadata-Version: 2.1\nName: fibsem-maestro\nVersion: {version}\n"
    if requires_python is not None:
        metadata += f"Requires-Python: {requires_python}\n"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"fibsem_maestro-{version}.dist-info/METADATA", metadata)
    return wheel


@pytest.mark.parametrize("requires_python", [">=3.14", None])
def test_python_requirement_accepts_a_supported_interpreter(
    tmp_path: Path, requires_python: str | None
) -> None:
    installer.check_python_requirement(
        _wheel(tmp_path, "2.0.0", requires_python), "3.14.7"
    )


def test_python_requirement_rejects_a_too_old_interpreter(tmp_path: Path) -> None:
    with pytest.raises(InstallError, match="latest installer"):
        installer.check_python_requirement(
            _wheel(tmp_path, "3.0.0", ">=3.15"), "3.14.7"
        )


def test_bundle_python_version_is_read_from_the_bundle_manifest(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"python_version": "3.14.7"}), encoding="utf-8"
    )

    assert installer.bundle_python_version(tmp_path) == "3.14.7"


def test_bundle_python_version_is_none_without_a_manifest(tmp_path: Path) -> None:
    assert installer.bundle_python_version(tmp_path) is None


def _interpreters(root: Path, *names: str) -> None:
    for name in names:
        (paths.python_install_dir(root) / name).mkdir(parents=True)


def test_interpreter_dir_matches_the_exact_version(tmp_path: Path) -> None:
    _interpreters(
        tmp_path,
        "cpython-3.11.9-linux-x86_64-gnu",
        "cpython-3.14.7-linux-x86_64-gnu",
        "cpython-3.14.70-linux-x86_64-gnu",
    )

    found = installer._interpreter_dir(tmp_path, "3.14.7")

    assert found.name == "cpython-3.14.7-linux-x86_64-gnu"


def test_updating_removes_the_previous_interpreter(tmp_path: Path) -> None:
    """An update from Python 3.11 must not leave the old interpreter behind."""
    _interpreters(
        tmp_path, "cpython-3.11.9-linux-x86_64-gnu", "cpython-3.14.7-linux-x86_64-gnu"
    )
    keep = installer._interpreter_dir(tmp_path, "3.14.7")

    installer._remove_other_interpreters(tmp_path, keep)

    assert [p.name for p in paths.python_install_dir(tmp_path).iterdir()] == [keep.name]


def test_set_links_writes_config_and_manifest(tmp_path: Path) -> None:
    Manifest(app_version="2.0.0", root=str(tmp_path), python_version="3.14.7").save(
        paths.manifest_file(tmp_path)
    )

    installer.set_links(tmp_path, {"autoscript": Path("/opt/autoscript")})

    assert read_links(paths.config_file(tmp_path)) == {
        "autoscript": Path("/opt/autoscript")
    }
    manifest = installer.existing_installation(tmp_path)
    assert manifest is not None
    assert manifest.libraries == {"autoscript": str(Path("/opt/autoscript"))}


def test_check_links_skips_libraries_this_installer_does_not_know(
    tmp_path: Path,
) -> None:
    assert installer.check_links(tmp_path, {"from-a-newer-installer": tmp_path}) == {}


@pytest.fixture
def offline_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """
    Stub out uv, the interpreter, the venv and the launchers of `install()`.

    The environment's interpreter is the one running the tests, so link
    checks really run.

    Returns:
        The offline bundle to install from.
    """
    bundle = tmp_path / "bundle"
    (bundle / "wheels").mkdir(parents=True)
    _wheel(bundle / "wheels", "2.0.0", ">=3.14")
    (bundle / "manifest.json").write_text(
        json.dumps({"python_version": "3.14.7"}), encoding="utf-8"
    )

    monkeypatch.setattr(installer, "ensure_uv", lambda *_: tmp_path / "uv")
    monkeypatch.setattr(installer, "_extract_python", lambda *_: Path(sys.executable))
    monkeypatch.setattr(installer, "run_uv", lambda *_, **__: "")
    monkeypatch.setattr(installer.launchers, "create_launchers", lambda _: [])
    monkeypatch.setattr(paths, "venv_python", lambda _: Path(sys.executable))
    return bundle


def test_install_reports_a_broken_link_without_failing(
    offline_install: Path, tmp_path: Path
) -> None:
    """A link that stops working (e.g. a Python upgrade) must not break an update."""
    root = tmp_path / "root"
    root.mkdir()
    paths.config_file(root).write_text(
        f'[autoscript]\npath = "{(tmp_path / "gone").as_posix()}"\n', encoding="utf-8"
    )
    plan = installer.InstallPlan(root=root, repository="x/y", bundle=offline_install)

    result = installer.install(plan, null_reporter, reinstall=True)

    assert list(result.link_problems) == ["autoscript"]
    assert result.manifest.libraries == {"autoscript": str(tmp_path / "gone")}
    assert installer.existing_installation(root) == result.manifest


def test_install_without_links_has_no_problems(
    offline_install: Path, tmp_path: Path
) -> None:
    plan = installer.InstallPlan(
        root=tmp_path / "root", repository="x/y", bundle=offline_install
    )

    result = installer.install(plan, null_reporter)

    assert result.link_problems == {}
    assert result.manifest.libraries == {}
    assert result.manifest.python_version == "3.14.7"


def test_install_refuses_a_release_for_another_python_before_touching_anything(
    offline_install: Path, tmp_path: Path
) -> None:
    for wheel in (offline_install / "wheels").iterdir():
        wheel.unlink()
    _wheel(offline_install / "wheels", "3.0.0", ">=3.15")
    root = tmp_path / "root"
    runtime = paths.venv_dir(root)
    runtime.mkdir(parents=True)
    plan = installer.InstallPlan(root=root, repository="x/y", bundle=offline_install)

    with pytest.raises(InstallError, match="latest installer"):
        installer.install(plan, null_reporter, reinstall=True)

    assert runtime.is_dir()
