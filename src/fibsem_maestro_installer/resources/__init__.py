# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Packaged resources."""

from __future__ import annotations

import atexit
from contextlib import ExitStack
from importlib.resources import as_file, files
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

ICON_NAME = "icon.svg"

_materialised = ExitStack()
atexit.register(_materialised.close)


def icon_svg() -> Path:
    """
    Return a real filesystem path to the packaged icon.

    Returns:
        Path of `icon.svg`.
    """
    assert __package__ is not None
    resource = files(__package__).joinpath(ICON_NAME)
    return _materialised.enter_context(as_file(resource))
