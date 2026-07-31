# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Error types shared across the installer."""

from __future__ import annotations


class InstallError(Exception):
    """Raised when a step of the installation fails."""


class InstallCancelled(Exception):
    """Raised when the user aborts an installation in progress."""


class AutoscriptError(InstallError):
    """Raised when the supplied Autoscript path cannot be imported."""
