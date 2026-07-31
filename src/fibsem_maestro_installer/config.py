# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""The application configuration file written by the installer."""

from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w


def write_config(path: Path, autoscript_path: Path) -> None:
    """
    Write the application configuration.

    Args:
        path: Destination `config.toml`.
        autoscript_path: Root of the Autoscript installation to link.
    """
    document = {"autoscript": {"path": str(autoscript_path)}}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        tomli_w.dump(document, handle)


def read_autoscript_path(path: Path) -> Path | None:
    """
    Read the configured Autoscript path.

    Args:
        path: The `config.toml` to read.

    Returns:
        The configured path, or None if unset or unreadable.
    """
    if not path.is_file():
        return None

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None

    value = data.get("autoscript", {}).get("path")
    return Path(value) if isinstance(value, str) else None
