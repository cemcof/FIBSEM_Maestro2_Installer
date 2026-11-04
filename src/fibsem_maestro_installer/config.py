# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""
The application configuration file, `config.toml`, as far as the installer manages it.

Linked libraries are stored as one table each:

    [libraries.autoscript]
    path = "C:/Program Files/.../Autoscript"

An unlinked library has no table. Other content of the file is preserved.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tomli_w

if TYPE_CHECKING:
    from collections.abc import Mapping

LIBRARIES_TABLE = "libraries"

LEGACY_AUTOSCRIPT_TABLE = "autoscript"
"""Table older installers wrote (`[autoscript] path = ...`); migrated on write."""


def _load(path: Path) -> dict[str, Any]:
    """
    Read the configuration file.

    Args:
        path: The `config.toml` to read.

    Returns:
        Its content; empty if the file is missing or unreadable.
    """
    if not path.is_file():
        return {}

    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except OSError, tomllib.TOMLDecodeError:
        return {}


def read_links(path: Path) -> dict[str, Path]:
    """
    Read the linked libraries.

    A link in the legacy `[autoscript]` table is reported as `autoscript`.

    Args:
        path: The `config.toml` to read.

    Returns:
        The folder of each linked library, by library key.
    """
    data = _load(path)
    links: dict[str, Path] = {}

    legacy = data.get(LEGACY_AUTOSCRIPT_TABLE)
    if isinstance(legacy, dict) and isinstance(legacy.get("path"), str):
        links["autoscript"] = Path(legacy["path"])

    tables = data.get(LIBRARIES_TABLE)
    if isinstance(tables, dict):
        for key, table in tables.items():
            if isinstance(table, dict) and isinstance(table.get("path"), str):
                links[key] = Path(table["path"])

    return links


def write_links(path: Path, links: Mapping[str, Path]) -> None:
    """
    Store the linked libraries, replacing the previous links.

    Content other than the links is kept. The legacy `[autoscript]` table is removed.

    Args:
        path: The `config.toml` to write.
        links: The folder of each linked library, by library key; libraries
            not listed are unlinked.
    """
    data = _load(path)
    data.pop(LEGACY_AUTOSCRIPT_TABLE, None)
    data.pop(LIBRARIES_TABLE, None)
    if links:
        data[LIBRARIES_TABLE] = {
            key: {"path": str(folder)} for key, folder in sorted(links.items())
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        tomli_w.dump(data, handle)
