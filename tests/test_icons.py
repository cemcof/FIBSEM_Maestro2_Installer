# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Tests for icon rendering."""

from __future__ import annotations

import struct
import sys
from typing import TYPE_CHECKING

from PIL import Image

from fibsem_maestro_installer import icons, paths, resources

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_render_image_produces_the_requested_size() -> None:
    image = icons.render_image(resources.icon_svg(), 48)

    assert (image.width(), image.height()) == (48, 48)


def test_render_image_draws_something() -> None:
    image = icons.render_image(resources.icon_svg(), 64)
    corner = image.pixelColor(32, 32)

    assert corner.alpha() > 0


def test_build_ico_writes_every_requested_frame(tmp_path: Path) -> None:
    target = icons.build_ico(resources.icon_svg(), tmp_path / "app.ico")
    header = target.read_bytes()[:6]
    reserved, kind, count = struct.unpack("<HHH", header)

    assert (reserved, kind) == (0, 1)
    assert count == len(icons.ICO_SIZES)


def test_build_ico_offsets_stay_inside_the_file(tmp_path: Path) -> None:
    target = icons.build_ico(resources.icon_svg(), tmp_path / "app.ico")
    data = target.read_bytes()
    count = struct.unpack("<H", data[4:6])[0]

    for index in range(count):
        entry = data[6 + 16 * index : 22 + 16 * index]
        length, offset = struct.unpack("<II", entry[8:16])
        assert offset + length <= len(data)


def test_build_ico_is_readable_by_an_independent_decoder(
    tmp_path: Path,
) -> None:
    target = icons.build_ico(resources.icon_svg(), tmp_path / "app.ico")

    with Image.open(target) as image:
        assert sorted(image.info["sizes"]) == [
            (size, size) for size in sorted(icons.ICO_SIZES)
        ]


def test_install_linux_icons_populates_the_hicolor_theme(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))

    created = icons.install_linux_icons(resources.icon_svg())

    theme = paths.icon_theme_dir()
    assert theme / "48x48" / "apps" / f"{paths.DESKTOP_ID}.png" in created
    assert theme / "scalable" / "apps" / f"{paths.DESKTOP_ID}.svg" in created
    assert all(path.is_file() for path in created)


def test_install_linux_icons_copies_the_vector_verbatim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    source = resources.icon_svg()

    icons.install_linux_icons(source)

    scalable = paths.icon_theme_dir() / "scalable" / "apps" / f"{paths.DESKTOP_ID}.svg"
    assert scalable.read_bytes() == source.read_bytes()
