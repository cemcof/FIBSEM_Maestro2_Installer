# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Discovery of application releases published as GitHub release assets."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path

from fibsem_maestro_installer.download import download_file, fetch_json
from fibsem_maestro_installer.errors import InstallError
from fibsem_maestro_installer.progress import ProgressReporter

GITHUB_API = "https://api.github.com"


@dataclass(frozen=True)
class Release:
    """
    A published release containing an installable wheel.

    Attributes:
        version: Version string with any leading `v` removed.
        wheel_name: File name of the wheel asset.
        wheel_url: URL from which the wheel can be downloaded.
    """

    version: str
    wheel_name: str
    wheel_url: str


def parse_version(text: str) -> tuple[int, ...]:
    """
    Convert a version string into a comparable tuple.

    Only the numeric release segment is considered, which is sufficient for
    deciding whether an update is available.

    Args:
        text: Version string such as `"v1.4.0"` or `"1.4.0rc1"`.

    Returns:
        Tuple of integers, empty when no numbers are present.
    """
    match = re.match(r"v?(\d+(?:\.\d+)*)", text.strip())
    if match is None:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(candidate: str, installed: str) -> bool:
    """
    Report whether one version supersedes another.

    Args:
        candidate: Version offered by the release.
        installed: Version currently installed.

    Returns:
        True if the candidate is strictly newer.
    """
    return parse_version(candidate) > parse_version(installed)


def latest_release(repository: str, token: str | None = None) -> Release:
    """
    Look up the newest release of the application.

    Args:
        repository: Repository in `owner/name` form.
        token: GitHub token for private repositories, or None.

    Returns:
        The latest release.

    Raises:
        InstallError: If the release has no wheel asset.
    """
    data = fetch_json(f"{GITHUB_API}/repos/{repository}/releases/latest", token)
    tag = str(data.get("tag_name", "")).lstrip("v")

    for asset in data.get("assets", []):
        name = str(asset.get("name", ""))
        if name.endswith(".whl"):
            url = (
                asset["url"]
                if token
                else asset.get("browser_download_url", asset["url"])
            )
            return Release(version=tag, wheel_name=name, wheel_url=url)

    raise InstallError(
        f"Release {tag or 'latest'} of {repository} has no wheel attached."
    )


def download_wheel(
    release: Release,
    destination_dir: Path,
    report: ProgressReporter,
    base_percent: int,
    span_percent: int,
    token: str | None = None,
    cancel: threading.Event | None = None,
) -> Path:
    """
    Download the wheel belonging to a release.

    Args:
        release: Release to download.
        destination_dir: Directory to place the wheel in.
        report: Progress reporter.
        base_percent: Overall progress at the start of this download.
        span_percent: Share of overall progress this download occupies.
        token: GitHub token for private repositories, or None.
        cancel: Cancellation event.

    Returns:
        Path of the downloaded wheel.
    """
    return download_file(
        release.wheel_url,
        destination_dir / release.wheel_name,
        report,
        base_percent,
        span_percent,
        token=token,
        cancel=cancel,
    )
