# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""The install manifest."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA_VERSION = 2


@dataclass
class Manifest:
    """
    Description of an existing installation.

    Attributes:
        app_version: Version of the installed application.
        root: Installation root directory.
        python_version: Interpreter version used for the environment.
        libraries: Folder of each linked manufacturer library, by library key.
        launchers: Every shortcut or desktop entry created by the installer.
        installed_at: UTC timestamp in ISO 8601 format.
        offline_install: Whether the installation came from an offline bundle.
        schema: Manifest format version.
    """

    app_version: str
    root: str
    python_version: str
    libraries: dict[str, str] = field(default_factory=dict)
    launchers: list[str] = field(default_factory=list)
    installed_at: str = ""
    offline_install: bool = False
    schema: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Stamp the creation time when it was not supplied."""
        if not self.installed_at:
            self.installed_at = datetime.now(UTC).isoformat(timespec="seconds")

    def save(self, path: Path) -> None:
        """Write the manifest as JSON.

        Args:
            path: Destination file.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")


def _migrate(data: dict[str, Any]) -> dict[str, Any] | None:
    """
    Bring a manifest written by an older installer to the current schema.

    Schema 1 linked Autoscript unconditionally (`autoscript_path`).

    Args:
        data: The manifest as read from disk.

    Returns:
        The data in the current schema, or None if the schema is unknown.
    """
    schema = data.get("schema")
    if schema == SCHEMA_VERSION:
        return data
    if schema == 1:
        migrated = {k: v for k, v in data.items() if k != "autoscript_path"}
        autoscript = data.get("autoscript_path")
        migrated["libraries"] = (
            {"autoscript": autoscript}
            if isinstance(autoscript, str) and autoscript
            else {}
        )
        migrated["schema"] = SCHEMA_VERSION
        return migrated
    return None


def load_manifest(path: Path) -> Manifest | None:
    """
    Read a manifest from disk.

    A manifest of an older schema is migrated. A malformed or future-schema
    manifest is treated as absent rather than raising, so that a damaged
    installation can still be repaired.

    Args:
        path: Manifest file to read.

    Returns:
        The manifest, or None if it is missing or unusable.
    """
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return None

    if not isinstance(data, dict) or (data := _migrate(data)) is None:
        return None

    known = Manifest.__dataclass_fields__.keys()
    try:
        return Manifest(**{k: v for k, v in data.items() if k in known})
    except TypeError:
        return None
