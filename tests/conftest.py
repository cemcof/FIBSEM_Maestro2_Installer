# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Shared pytest fixtures."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def qt_application() -> Iterator[None]:
    """
    Provide the single QGuiApplication that icon rendering requires.

    Yields:
        None, once the application exists.
    """
    from PyQt6.QtGui import QGuiApplication

    application = QGuiApplication.instance() or QGuiApplication([])
    yield
    del application
