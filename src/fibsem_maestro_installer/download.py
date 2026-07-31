# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Minimal HTTP helpers."""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fibsem_maestro_installer.errors import InstallError
from fibsem_maestro_installer.progress import ProgressReporter, check_cancelled

_CHUNK = 64 * 1024
_TIMEOUT = 30


def _request(url: str, token: str | None, accept: str) -> urllib.request.Request:
    """
    Build a request with optional GitHub authentication.

    Args:
        url: Target URL.
        token: GitHub token for private repositories, or None.
        accept: Value of the `Accept` header.

    Returns:
        The prepared request.
    """
    headers = {"Accept": accept, "User-Agent": "fibsem-maestro-installer"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    return urllib.request.Request(url, headers=headers)


def fetch_json(url: str, token: str | None = None) -> Any:
    """
    Fetch and decode a JSON document.

    Args:
        url: Target URL.
        token: GitHub token for private repositories, or None.

    Returns:
        The decoded document.

    Raises:
        InstallError: If the request or decoding fails.
    """
    request = _request(url, token, "application/vnd.github+json")

    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise InstallError(f"Could not reach {url}: {error}") from error


def download_file(
    url: str,
    destination: Path,
    report: ProgressReporter,
    base_percent: int,
    span_percent: int,
    token: str | None = None,
    cancel: threading.Event | None = None,
) -> Path:
    """
    Download a file, reporting progress into a slice of the overall bar.

    Args:
        url: Source URL.
        destination: Destination file.
        report: Progress reporter.
        base_percent: Overall progress at the start of this download.
        span_percent: Share of the overall progress this download occupies.
        token: GitHub token for private repositories, or None.
        cancel: Cancellation event.

    Returns:
        The destination path.

    Raises:
        InstallError: If the download fails.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = _request(url, token, "application/octet-stream")
    name = destination.name

    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            total = int(response.headers.get("Content-Length") or 0)
            received = 0
            with destination.open("wb") as handle:
                while True:
                    check_cancelled(cancel)
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    handle.write(chunk)
                    received += len(chunk)
                    if total:
                        fraction = received / total
                        report(
                            f"Downloading {name}",
                            base_percent + int(span_percent * fraction),
                        )
    except (urllib.error.URLError, OSError) as error:
        destination.unlink(missing_ok=True)
        raise InstallError(f"Could not download {name}: {error}") from error

    return destination


def sha256(path: Path) -> str:
    """
    Compute the SHA-256 digest of a file.

    Args:
        path: File to hash.

    Returns:
        Lower-case hexadecimal digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)

    return digest.hexdigest()
