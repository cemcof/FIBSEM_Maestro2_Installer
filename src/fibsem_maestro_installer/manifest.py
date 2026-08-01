# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""The install manifest."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA_VERSION = 1


@dataclass
class Manifest:
    """
    Description of an existing installation.

    Attributes:
        app_version: Version of the installed application.
        root: Installation root directory.
        python_version: Interpreter version used for the environment.
        autoscript_path: Directory of the linked Autoscript installation.
        launchers: Every shortcut or desktop entry created by the installer.
        installed_at: UTC timestamp in ISO 8601 format.
        offline_install: Whether the installation came from an offline bundle.
        schema: Manifest format version.
    """

    app_version: str
    root: str
    python_version: str
    autoscript_path: str
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


def load_manifest(path: Path) -> Manifest | None:
    """
    Read a manifest from disk.

    A malformed or future-schema manifest is treated as absent rather than
    raising, so that a damaged installation can still be repaired.

    Args:
        path: Manifest file to read.

    Returns:
        The manifest, or None if it is missing or unusable.
    """
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
        return None

    known = Manifest.__dataclass_fields__.keys()
    try:
        return Manifest(**{k: v for k, v in data.items() if k in known})
    except TypeError:
        return None
