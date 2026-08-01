# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Tests for GitHub release discovery."""

from __future__ import annotations

from typing import Any

import pytest
from packaging.version import Version

from fibsem_maestro_installer import releases
from fibsem_maestro_installer.errors import InstallError


def test_parse_version_handles_prefix_and_suffix() -> None:
    assert releases.parse_version("v1.4.0") == Version("v1.4.0")
    assert releases.parse_version("1.4.0rc1") == Version("1.4.0rc1")
    assert releases.parse_version("nonsense") is None


@pytest.mark.parametrize(
    ("candidate", "installed", "expected"),
    [
        ("1.4.1", "1.4.0", True),
        ("1.4.0", "1.4.0", False),
        ("1.3.9", "1.4.0", False),
        ("2.0", "1.9.9", True),
        ("2.0.0b1", "2.0.0b7", False),
        ("1.4.5b16", "1.4.5b8", True),
        ("1.4.5b4", "1.4.6", False),
    ],
)
def test_is_newer_compares_release_segments(
    candidate: str, installed: str, expected: bool
) -> None:
    assert releases.is_newer(candidate, installed) is expected


def _release_payload() -> dict[str, Any]:
    """
    Build a minimal GitHub release payload.

    Returns:
        A payload containing one wheel and one unrelated asset.
    """
    return {
        "tag_name": "v1.4.0",
        "assets": [
            {
                "name": "notes.txt",
                "url": "https://api/1",
                "browser_download_url": "https://dl/1",
            },
            {
                "name": "fibsem_maestro-1.4.0-py3-none-any.whl",
                "url": "https://api/2",
                "browser_download_url": "https://dl/2",
            },
        ],
    }


def test_latest_release_selects_the_wheel_asset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        releases,
        "fetch_json",
        lambda url, token=None: _release_payload(),  # noqa: ARG005
    )

    release = releases.latest_release("cemcof/fibsem-maestro")

    assert release.version == "1.4.0"
    assert release.wheel_name.endswith(".whl")
    assert release.wheel_url == "https://dl/2"


def test_latest_release_uses_api_url_when_authenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        releases,
        "fetch_json",
        lambda url, token=None: _release_payload(),  # noqa: ARG005
    )

    release = releases.latest_release("cemcof/fibsem-maestro", token="secret")

    assert release.wheel_url == "https://api/2"


def test_latest_release_raises_without_a_wheel(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"tag_name": "v1.4.0", "assets": [{"name": "notes.txt", "url": "u"}]}
    monkeypatch.setattr(releases, "fetch_json", lambda url, token=None: payload)  # noqa: ARG005

    with pytest.raises(InstallError, match="no wheel"):
        releases.latest_release("cemcof/fibsem-maestro")
