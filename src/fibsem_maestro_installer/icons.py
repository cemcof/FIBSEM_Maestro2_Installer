# Released under MIT License.
# Copyright (c) 2024-2026 CEMCOF

"""Rendering of every icon artefact from the single packaged SVG."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from fibsem_maestro_installer import paths

if TYPE_CHECKING:
    from pathlib import Path

ICON_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)


def render_image(svg: Path, size: int) -> QImage:
    """
    Rasterise the SVG at one size.

    Args:
        svg: Source vector file.
        size: Edge length in pixels.

    Returns:
        A square image with a transparent background.
    """
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    QSvgRenderer(str(svg)).render(painter)
    painter.end()

    return image


def _png_bytes(image: QImage) -> bytes:
    """
    Encode an image as PNG in memory.

    Args:
        image: Image to encode.

    Returns:
        The PNG payload.
    """
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data().data())


def build_ico(svg: Path, destination: Path) -> Path:
    """
    Assemble a multi-resolution ICO from the SVG.

    Args:
        svg: Source vector file.
        destination: Path of the `.ico` to write.

    Returns:
        The destination path.
    """
    frames = [_png_bytes(render_image(svg, size)) for size in ICO_SIZES]

    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(header) + 16 * len(frames)

    directory = bytearray()
    for size, payload in zip(ICO_SIZES, frames):
        # 0 encodes 256 in the ICO format
        edge = 0 if size >= 256 else size
        directory += struct.pack(
            "<BBBBHHII", edge, edge, 0, 0, 1, 32, len(payload), offset
        )
        offset += len(payload)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        handle.write(header)
        handle.write(bytes(directory))
        for payload in frames:
            handle.write(payload)

    return destination


def install_linux_icons(svg: Path) -> list[Path]:
    """
    Populate the per-user hicolor theme from the SVG.

    Args:
        svg: Source vector file.

    Returns:
        Paths of every file written.
    """
    theme = paths.icon_theme_dir()
    written: list[Path] = []

    for size in ICON_SIZES:
        target = theme / f"{size}x{size}" / "apps" / f"{paths.DESKTOP_ID}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        render_image(svg, size).save(str(target), "PNG")
        written.append(target)

    scalable = theme / "scalable" / "apps" / f"{paths.DESKTOP_ID}.svg"
    scalable.parent.mkdir(parents=True, exist_ok=True)
    scalable.write_bytes(svg.read_bytes())
    written.append(scalable)

    return written


def load_window_icon(svg: Path):
    """
    Build a window icon carrying explicit resolutions.

    Args:
        svg: Source vector file.

    Returns:
        A `QIcon`.
    """

    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(render_image(svg, size)))
    return icon
